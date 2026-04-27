# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""Feature-flag client for the auth_v2 addon.

Provides ``is_enabled(flag_name, subject=None)``, the SOLE Python code
path for reading feature flags. The function consults three sources in
order:

    1. In-process cache (TTL = FLAGS_CACHE_TTL_MS / 1000 seconds, default 5s)
    2. Flags evaluation API (GET {FLAGS_API_URL}/flags/{name}, 5s timeout)
    3. os.environ fallback (e.g., os.environ.get('AUTH_V2_ENABLED', 'false'))

Fail mode (Rule RF3 -- fail-open):
    ANY failure in the cache or API path falls back to os.environ. The
    function NEVER raises. This is the OPPOSITE of auth_v2.py's
    fail-closed mode (Rule R13). The asymmetry is intentional:

        - Auth failure  -> fail closed (refuse access, 503) -- preserves integrity
        - Flag failure  -> fail open  (use env default)     -- preserves availability

Local rollout evaluation (Rule RF4):
    When the API returns rollout_percentage < 100, the bucket decision is
    computed LOCALLY using fnv_hash. This ensures retries within the TTL
    window never re-bucket (FNV is deterministic given identical inputs)
    and that the TypeScript and Python implementations agree byte-for-
    byte on every (flag_name, subject, rollout_percentage) triple.

Resolution order (matches packages/admin-ui/src/flags/checkFlag.ts):
    1. Subject override                (resolved by API; reflected in `enabled`)
    2. '*' global override             (resolved by API; reflected in `enabled`)
    3. flag.enabled === false          (handled locally in _evaluate_locally)
    4. FNV-1a bucket vs rollout_pct    (handled locally in _evaluate_locally)

Steps 1 and 2 are resolved on the server side because the flags API is the
only component with database access; the API encodes the result of those
steps into the boolean ``enabled`` field of its response. Steps 3 and 4
are evaluated locally so that retry attempts within the cache TTL window
never re-bucket subjects -- the determinism guarantee of FNV-1a means the
same (flag_name, subject) pair always returns the same boolean.

Rules Enforced:
    - RF3 (Flag fail-open):      no raises; env fallback on every failure path
    - RF4 (FNV-1a parity):       local eval matches TypeScript byte-for-byte
    - R8  (Secrets containment): no literal secrets; env reads at call time
    - R23 (Log hygiene):         secrets/tokens never logged
    - R28 (Structured logging):  Python logging module, no print()
    - R3  (Flag isolation):      no module-load env reads or HTTP calls

Thread safety:
    Odoo's request handling is thread-based (per-request worker threads).
    The module-level ``_FLAG_CACHE`` dict is guarded by ``_CACHE_LOCK``
    (a ``threading.Lock``) for atomic read-modify-write. The lock is
    HELD only during dict access; it is RELEASED before the HTTP call to
    avoid blocking other threads on slow API responses. This means two
    concurrent threads with the same cache miss may both issue an HTTP
    request, but the second writer will simply overwrite the first
    writer's identical resolved value -- no correctness impact.

See:
    - AAP Section 0.4.1.3 (Direct Modifications Required -- Odoo)
    - AAP Section 0.5.1.5 (Group 5 -- Odoo Addon)
    - AAP Section 0.7.2 RF3 (Flag fail-open -- THE asymmetric invariant)
    - AAP Section 0.7.2 RF4 (FNV-1a parity contract)
    - User Example: FNV-1a 32-bit hash of flag_name + ':' + subject
    - Sibling: ``auth_v2.py`` (peer-level fail-CLOSED counterpart, Rule R13)
    - Sibling: ``fnv_hash.py`` (the foundational hash function)
    - Companion: ``packages/admin-ui/src/flags/checkFlag.ts`` (TS counterpart)
    - Companion fixture: ``packages/admin-ui/src/flags/__tests__/fixtures/fnv-vectors.json``
"""

import logging
import os
import threading
import time
from typing import Optional

import httpx

from . import fnv_hash

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

#: Module-level logger. Per Rule R28 (structured logging), all diagnostic
#: output goes through Python's ``logging`` module -- never ``print()``.
#: The logger name follows the dotted-module convention so it can be
#: filtered alongside other auth_v2 modules in production deployments.
_logger = logging.getLogger(__name__)

#: Process-local cache: ``{cache_key: (resolved_value, expires_at_epoch_seconds)}``.
#:
#: Per Rule RF4 (parity), the cache stores the FINAL evaluated boolean
#: (after rollout-percentage application), NOT the raw {enabled,
#: rollout_percentage} response. This means retries within the TTL
#: window never re-bucket users, preserving determinism for sticky
#: rollouts. The cache key format ``f"{flag_name}:{subject or ''}"``
#: matches the TypeScript convention (literal colon, no padding).
#:
#: The dict is lazily populated on first ``is_enabled()`` call. Module
#: import does NOT mutate the dict (an empty dict is the initial state),
#: so import-time side effects are zero (Rule R3 spirit).
_FLAG_CACHE: dict = {}

#: Lock guarding ``_FLAG_CACHE`` read-modify-write operations. Odoo's
#: threaded worker model can call ``is_enabled()`` concurrently from
#: multiple request threads, so the cache MUST be thread-safe. The lock
#: is HELD only while the dict is being read or written; it is RELEASED
#: before any HTTP call so that slow API responses do not block other
#: threads. ``threading.Lock`` is a non-reentrant lock, which is what we
#: want here -- no function in this module recursively re-acquires the
#: lock.
_CACHE_LOCK = threading.Lock()

#: HTTP request timeout in seconds. Per AAP Section 0.4.1.3:
#: "httpx.get(..., timeout=5.0)". The same 5-second timeout is used by
#: ``auth_v2.py`` for the validate endpoint, providing a consistent
#: bound on per-request latency for both auth and flag operations.
_REQUEST_TIMEOUT_SECONDS: float = 5.0

#: Default cache TTL when ``FLAGS_CACHE_TTL_MS`` is unset, per AAP:
#: "default TTL of 5000 ms (FLAGS_CACHE_TTL_MS)". The env var is in
#: milliseconds for symmetry with the TypeScript side; we divide by 1000
#: in ``_get_cache_ttl_seconds()`` to produce the seconds value used by
#: ``time.time()`` arithmetic.
_DEFAULT_CACHE_TTL_MS: int = 5000


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_cache_ttl_seconds() -> float:
    """Return the cache TTL in seconds, reading FLAGS_CACHE_TTL_MS at call time.

    Per AAP Section 0.5.1.2, the default is 5000 ms. The env var is in
    milliseconds for consistency with the TypeScript side; we divide by
    1000 to convert to seconds (the unit used by ``time.time()``).

    Invalid values (non-numeric, negative) fall back to the default with
    a warning log. Per Rule RF3 (fail-open), this helper MUST NOT raise:
    a malformed TTL must not break flag evaluation, only degrade to the
    documented default. The internal ``raise ValueError(...)`` for
    negative values is immediately caught by the surrounding ``except``
    block and converted to a default-with-warning return.

    Reading the env var on every call (rather than caching it once) is
    intentional: it allows test code to mutate ``os.environ`` between
    test cases and have those changes reflected without process restart.
    The cost is a single ``os.environ.get`` lookup, which is sub-microsecond.

    Returns:
        TTL in seconds as a float (e.g., ``5.0`` for the default).
    """
    raw = os.environ.get('FLAGS_CACHE_TTL_MS', str(_DEFAULT_CACHE_TTL_MS))
    try:
        ms = int(raw)
        if ms < 0:
            # Negative TTLs would cause every cache entry to be considered
            # expired immediately, defeating the cache. Treat as malformed
            # and use the default (with a warning so operators notice).
            # The exception message is bound to a local variable to satisfy
            # ruff EM101 (exception message must not be a string literal).
            err_msg = "negative TTL"
            raise ValueError(err_msg)
        return ms / 1000.0
    except (ValueError, TypeError):
        # Per Rule R23, log the raw value (it is a config key, not a
        # secret) so the operator can spot the typo. The %r format
        # quotes strings, making the typo visible (e.g., '5000ms' shows
        # as "'5000ms'" rather than 5000ms).
        _logger.warning(
            "auth_v2: invalid FLAGS_CACHE_TTL_MS=%r; using default %s ms",
            raw, _DEFAULT_CACHE_TTL_MS,
        )
        return _DEFAULT_CACHE_TTL_MS / 1000.0


def _env_fallback(flag_name: str) -> bool:
    """Read the flag's value from os.environ as the fail-open fallback.

    The lookup key is the ``flag_name`` UNCHANGED -- no lowercasing, no
    prefix addition. This is critical for ``AUTH_V2_ENABLED``, which is
    documented in ``kalle/.env.example`` as ``AUTH_V2_ENABLED=false``
    (same casing) and which must be readable byte-for-byte from this
    Python addon when the flags API is unreachable.

    The truthy values are EXACTLY ``'true'`` (case-insensitive). Other
    common-but-rejected values (``'1'``, ``'yes'``, ``'on'``, empty
    string, unset variable) all evaluate to ``False``. This matches the
    AAP's explicit specification:

        "AUTH_V2_ENABLED=true (env, lowercase) -> True
         AUTH_V2_ENABLED=True (env, capitalized) -> True
         AUTH_V2_ENABLED=TRUE (env, uppercase) -> True
         AUTH_V2_ENABLED=1 -> False (the AAP specifies 'true' only)
         AUTH_V2_ENABLED=false -> False
         AUTH_V2_ENABLED= (empty) -> False
         Variable unset -> False"

    The default ``'false'`` (not ``''``, not ``'False'``) ensures that
    ``os.environ.get(flag_name, 'false').lower() == 'true'`` evaluates
    to ``False`` consistently when the variable is unset.

    Per Rule RF3 (fail-open), this function MUST NOT raise. The
    ``str.lower()`` method is total over Python strings, so this
    function is provably non-raising.

    Args:
        flag_name: The flag identifier (UPPERCASE by convention, but
            preserved as-passed for env-var lookup). E.g.,
            ``'AUTH_V2_ENABLED'``.

    Returns:
        Boolean evaluation: ``True`` iff the env var equals ``'true'``
        (case-insensitive). ``False`` for every other value, including
        unset variables and empty strings.
    """
    raw = os.environ.get(flag_name, 'false')
    return raw.lower() == 'true'


def _evaluate_locally(
    flag_name: str,
    subject: Optional[str],
    api_response: dict,
) -> bool:
    """Evaluate the rollout decision locally using FNV-1a hash bucketing.

    This implements steps 3 and 4 of the canonical 4-step evaluation
    order (the order also encoded in
    ``packages/admin-ui/src/flags/checkFlag.ts``):

        1. Subject override                  (resolved by API)
        2. '*' global override               (resolved by API)
        3. flag.enabled == False             (handled here)
        4. FNV-1a bucket < rollout_pct       (handled here)

    Steps 1 and 2 (overrides) are resolved by the flags API because only
    the API has database access for ``flag_overrides`` lookups. The API
    folds those override results into the ``enabled`` field of its
    response. Steps 3 and 4 are computed LOCALLY so retries within the
    TTL window do NOT re-bucket users -- the FNV-1a result is
    deterministic given identical inputs.

    Per Rule RF4 (parity), the FNV-1a computation MUST match the
    TypeScript implementation byte-for-byte. ``fnv_hash.fnv1a32()`` is
    the cross-language parity contract; the 100-vector fixture at
    ``packages/admin-ui/src/flags/__tests__/fixtures/fnv-vectors.json``
    pins the contract.

    Bucket math:
        bucket = fnv1a32(flag_name + ':' + subject) % 100
        enabled = bucket < rollout_percentage

    Note the ``<`` (strict less-than), NOT ``<=``. With
    ``rollout_percentage = 0`` the predicate ``bucket < 0`` is always
    false (correct: 0% rollout means no one); with
    ``rollout_percentage = 100`` the predicate ``bucket < 100`` is
    always true (correct: 100% rollout means everyone). This matches
    the TypeScript implementation exactly.

    Edge cases:
        - ``rollout_percentage >= 100``: short-circuit to ``True`` (no
          hash needed -- everyone is in).
        - ``rollout_percentage <= 0``: short-circuit to ``False`` (no
          hash needed -- no one is in).
        - ``api_response['enabled'] is False``: short-circuit to
          ``False`` regardless of rollout (step 3 of 4-step order).
        - ``api_response['rollout_percentage']`` missing or non-int:
          treat as ``100`` (default to fully-enabled rather than
          fully-disabled, since reaching this code path means the
          API said the flag was ``enabled``).

    Per Rule RF3, this helper MUST NOT raise. Bad input shapes (e.g.,
    ``rollout_percentage`` is a string) are coerced via ``int()`` with a
    fallback default; the only operation that could raise is the dict
    access, which uses ``.get()`` with explicit defaults.

    Args:
        flag_name: The flag identifier (e.g., ``'AUTH_V2_ENABLED'``).
            Used as the prefix in the FNV input ``flag_name + ':' + subject``.
        subject: The user's email, or ``None``. ``None`` is normalized to
            ``''`` (empty string) per the parity contract -- this matches
            the TypeScript expression ``flag_name + ':' + (subject ?? '')``.
        api_response: The parsed ``{enabled, rollout_percentage}`` dict
            returned by the flags API.

    Returns:
        The locally-evaluated boolean. Always a bool, never ``None``,
        never raises.
    """
    # Step 3: explicit disable beats rollout. If the API returned
    # enabled=False (which can happen because the flag itself is off OR
    # because no override flipped it on for this subject), we return
    # False without computing the hash. ``api_response.get('enabled')``
    # without a default returns None for a missing key, which is also
    # falsy and indistinguishable from False under ``bool()`` (ruff
    # RUF056: avoid providing a falsy fallback to ``dict.get()`` when
    # the result is consumed in a boolean test).
    enabled = bool(api_response.get('enabled'))
    if not enabled:
        return False

    # Coerce rollout_percentage to int with a fully-enabled fallback.
    # The flags API contract guarantees an int in [0, 100], but defensive
    # coercion costs nothing and keeps this function total.
    rollout_percentage = api_response.get('rollout_percentage', 100)
    try:
        rollout_percentage = int(rollout_percentage)
    except (ValueError, TypeError):
        # Malformed payload -- default to 100 (fully enabled) since the
        # API already told us enabled=True. This is the more conservative
        # of the two "wrong" interpretations: it errs on the side of
        # giving the user the feature rather than silently denying it.
        rollout_percentage = 100

    # Short-circuits avoid the hash computation for the common cases of
    # 100% (post-rollout) and 0% (pre-rollout) flags.
    if rollout_percentage >= 100:
        return True
    if rollout_percentage <= 0:
        # Symmetrically with TypeScript: bucket % 100 is in [0, 99],
        # never negative, so bucket < 0 is always False.
        return False

    # Step 4: FNV-1a bucket decision (Rule RF4 parity contract).
    # The subject string is None -> '' per the parity contract -- this
    # matches the TypeScript expression `flag_name + ':' + (subject ?? '')`.
    # We pass flag_name and subject SEPARATELY to fnv_hash.fnv1a32; the
    # hash function concatenates them with the ':' separator internally.
    # This keeps the separator definition in one place (fnv_hash.py) and
    # ensures both sides of the parity contract use the exact same bytes.
    subject_for_hash = subject if subject is not None else ''
    bucket = fnv_hash.fnv1a32(flag_name, subject_for_hash) % 100
    return bucket < rollout_percentage


def _fetch_from_api(flag_name: str, subject: Optional[str]) -> Optional[dict]:
    """Fetch the flag's evaluation from the flags API.

    Performs ``GET {FLAGS_API_URL}/flags/{flag_name}?subject=<email>``
    with a 5-second timeout and an ``Authorization: Bearer
    {FLAGS_API_SECRET}`` header. Returns the parsed JSON response on
    success, or ``None`` on ANY failure.

    Per Rule RF3 (fail-open), this function MUST NOT raise -- failures
    return ``None`` and the caller falls back to ``os.environ``. Failure
    modes that map to ``None``:

        - ``FLAGS_API_URL`` is unset or empty
        - ``FLAGS_API_SECRET`` is unset or empty
        - Connection error, DNS failure, refused connection
        - HTTP timeout (5 seconds elapsed without response)
        - Non-200 HTTP status (4xx, 5xx, or even 2xx other than 200)
        - Response body is not valid JSON
        - Response body is JSON but not a JSON object (e.g., a list)

    All failure paths log at WARNING level (not ERROR) because flag-API
    unavailability is expected during admin-ui restarts, planned
    downtime, etc. -- and per Rule RF3 the system continues to function
    via env fallback. Operators monitoring the WARN log stream will
    notice the fallback events without being paged.

    Per Rule R23 (log hygiene), the function NEVER logs the secret value
    or the full Authorization header. It IS acceptable to log the flag
    name, the subject (an email -- non-secret PII), HTTP status codes,
    and the type name of any caught exception.

    The HTTP client uses a fresh ``httpx.Client`` per call (via context
    manager) rather than a module-level pool. Connection-pool reuse is
    unnecessary at this request rate (flag reads are rare and cached),
    and a per-call client keeps the function pure (no module-level state,
    easier to test, no risk of resource leaks across worker restarts).

    Args:
        flag_name: The flag identifier. Used as the path segment in the
            URL (no URL-encoding is applied because flag names are
            constrained to safe ASCII characters by convention --
            specifically the ``[A-Z0-9_]+`` regex enforced by the
            flags-db schema).
        subject: The user's email, or ``None``. When non-None, sent as
            the ``subject`` query parameter; when None, the parameter
            is omitted from the request entirely.

    Returns:
        The parsed dict ``{'enabled': bool, 'rollout_percentage': int}``
        on success, or ``None`` if the API is unreachable, returns a
        non-200 status, or the response is unparseable.
    """
    # Read config at call time (NOT at module load) per Rule R3 spirit.
    # Both env vars are required for an API call; missing either means
    # we cannot make the call and must fall back to env. Empty strings
    # are treated as also-unset (a quirk of how docker compose passes
    # empty .env values -- they appear as empty strings, not unset).
    base_url = os.environ.get('FLAGS_API_URL')
    if not base_url:
        # Debug-level: this is the steady state in environments that
        # have not configured a flags API (e.g., running Odoo against
        # AUTH_V2_ENABLED env var only, no admin-ui deployed). We do
        # NOT want a warning log on every flag check in those setups.
        _logger.debug(
            "auth_v2: FLAGS_API_URL not set; skipping API call for flag %s",
            flag_name,
        )
        return None

    secret = os.environ.get('FLAGS_API_SECRET')
    if not secret:
        # Symmetric with the FLAGS_API_URL check: debug-level because
        # this is the expected steady state in env-only deployments.
        _logger.debug(
            "auth_v2: FLAGS_API_SECRET not set; skipping API call for flag %s",
            flag_name,
        )
        return None

    # Build the URL by stripping any trailing slash from base_url. This
    # makes the function robust to FLAGS_API_URL values with and without
    # a trailing slash (both spellings are common in operator-edited env
    # configs). The flag name is appended verbatim as the path segment.
    url = f"{base_url.rstrip('/')}/flags/{flag_name}"

    # Conditionally include the subject query param. When subject is
    # None we OMIT the param entirely (rather than sending '?subject=')
    # so the server can distinguish "no subject" from "empty subject".
    params = {'subject': subject} if subject is not None else None

    # Per Rule R23, the secret IS embedded in the Authorization header
    # but the header is NEVER logged below. The 'Accept' header tells
    # the server we want JSON, which avoids HTML error pages from
    # confusing the JSON parser.
    headers = {
        'Authorization': f"Bearer {secret}",
        'Accept': 'application/json',
    }

    # httpx.Timeout(5.0) is equivalent to httpx.Timeout(connect=5.0,
    # read=5.0, write=5.0, pool=5.0) -- 5 seconds for every phase. This
    # matches auth_v2.py's timeout configuration.
    timeout = httpx.Timeout(_REQUEST_TIMEOUT_SECONDS)

    try:
        # httpx.Client (synchronous, per Odoo's threading model -- NOT
        # AsyncClient) used as a context manager so the connection is
        # closed even on exception. A fresh client per call is fine at
        # this request volume.
        with httpx.Client(timeout=timeout) as client:
            response = client.get(url, params=params, headers=headers)
    except httpx.RequestError as exc:
        # httpx.RequestError is the base class for connection errors,
        # timeouts, DNS errors, etc. -- everything that prevents getting
        # an HTTP response. Per Rule RF3, fall back silently (return
        # None to caller).
        #
        # We log at WARNING (not ERROR) because this is expected during
        # admin-ui restarts, planned downtime, and similar transient
        # conditions. ERROR-level logging would generate alert noise.
        #
        # Per Rule R23: log the exception TYPE name only, not the
        # exception message (which might echo URL fragments containing
        # the host name -- non-secret but unhelpful to leak in case the
        # log destination is less trusted than the env config).
        _logger.warning(
            "auth_v2: flags API request failed (flag=%s, exc=%s); falling back to env",
            flag_name, type(exc).__name__,
        )
        return None

    # Status check: only HTTP 200 is success. The flags API contract
    # specifies 200 for both "flag exists" and "flag does not exist"
    # (the latter returns enabled=false, rollout_percentage=0). Any
    # other status -- 401 (bad secret), 404 (flag not found), 5xx
    # (server error) -- means we cannot trust the response.
    if response.status_code != 200:
        # Log the status code (not a secret) and the flag name so the
        # operator can identify which flag-API call failed and why.
        # Per Rule R23, do NOT log the response body, which might
        # contain server-side details we should not echo.
        _logger.warning(
            "auth_v2: flags API returned status %s (flag=%s); falling back to env",
            response.status_code, flag_name,
        )
        return None

    # Parse JSON. httpx's .json() raises ValueError (json.JSONDecodeError
    # in Python 3.5+, which is a ValueError subclass) on malformed
    # bodies; we catch ValueError to handle both spellings.
    try:
        result = response.json()
    except ValueError:
        # Malformed JSON. Per Rule RF3, fall back to env. Per Rule R23,
        # do NOT log the body content (might contain HTML error pages,
        # stack traces, or other server internals).
        _logger.warning(
            "auth_v2: flags API returned non-JSON response (flag=%s); falling back to env",
            flag_name,
        )
        return None

    # The flags API contract requires a JSON object with at least the
    # 'enabled' key. A JSON list, scalar, or null indicates a contract
    # violation; treat as a failure and fall back.
    if not isinstance(result, dict):
        _logger.warning(
            "auth_v2: flags API returned non-dict JSON (flag=%s); falling back to env",
            flag_name,
        )
        return None

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_enabled(flag_name: str, subject: Optional[str] = None) -> bool:
    """Return True iff the named feature flag is enabled for the given subject.

    This is the SOLE Python code path for reading feature flags in the
    auth_v2 addon. The function is consumed by ``ir_http.py`` (and any
    future Odoo controllers that need flag-gated behavior) to make
    per-request decisions about whether the V2 OAuth path or the legacy
    Odoo path should run.

    Resolution order (matches packages/admin-ui/src/flags/checkFlag.ts):

        1. In-process cache (TTL = FLAGS_CACHE_TTL_MS / 1000 seconds,
           default 5 seconds). Returns the cached final boolean if the
           entry is still fresh.
        2. Flags evaluation API (``GET {FLAGS_API_URL}/flags/{name}``,
           5-second timeout, Bearer auth via ``FLAGS_API_SECRET``).
           When the API returns ``rollout_percentage < 100``, the bucket
           decision is computed locally via FNV-1a (Rule RF4).
        3. ``os.environ.get(flag_name, 'false').lower() == 'true'``
           fallback when the API fails (Rule RF3 fail-open).

    Per Rule RF3 (fail-open), this function NEVER raises. Any error,
    timeout, or non-2xx response from the API silently falls back to
    ``os.environ``. This is the OPPOSITE of ``auth_v2.validate_token()``,
    which fails closed (raises ServiceUnavailable). The asymmetry is
    intentional:

        - Auth failure  -> fail closed (refuse access, 503) -- protects integrity
        - Flag failure  -> fail open  (use env default)     -- preserves availability

    Per Rule RF4 (parity), when the API returns ``rollout_percentage <
    100``, the bucket decision is computed locally via
    ``fnv_hash.fnv1a32()`` -- the byte-equal Python counterpart of the
    TypeScript implementation. The 100-vector fixture at
    ``packages/admin-ui/src/flags/__tests__/fixtures/fnv-vectors.json``
    is the parity contract.

    The cache stores the FINAL evaluated boolean (post-bucketing), keyed
    by ``(flag_name, subject_or_empty_string)``. This guarantees
    determinism: the same ``(flag_name, subject)`` pair returns the same
    boolean for the duration of the TTL window, regardless of intervening
    API calls or rollout-percentage churn.

    Thread safety: the cache lookup and write are guarded by
    ``_CACHE_LOCK``. The lock is RELEASED before the HTTP call so that
    slow API responses do not block other request threads. Two concurrent
    threads with the same cache miss may both issue an HTTP request, but
    they will compute identical results and the second writer simply
    overwrites the first -- no correctness impact.

    Args:
        flag_name: The flag identifier (e.g., ``'AUTH_V2_ENABLED'``).
            Case-sensitive; UPPERCASE convention but not enforced. Used
            verbatim for both cache key construction, env-var lookup,
            and FNV hash input.
        subject: The user's email, or ``None``. ``None`` means "no
            subject" -- the cache key uses ``''`` (empty string) and the
            FNV bucket also uses ``''``. NO normalization is applied
            (no trim, no lowercase) -- the TypeScript counterpart treats
            the input identically and the parity contract requires
            byte-exact equivalence of the encoded byte sequence.

    Returns:
        Boolean evaluation. Always a ``bool``, never ``None``, NEVER
        raises an exception (Rule RF3 fail-open).

    Examples:
        Default check with no subject (uses '' for hashing/caching):

            >>> # Assuming FLAGS_API_URL is unreachable and
            >>> # AUTH_V2_ENABLED env var is unset:
            >>> is_enabled('AUTH_V2_ENABLED')
            False

        Per-user check (caches with the subject as part of the key):

            >>> is_enabled('NEW_CHECKOUT_FLOW', 'alice@example.com')  # doctest: +SKIP
            # Returns True or False deterministically based on rollout %
    """
    # Construct the cache key. The format ``"{flag_name}:{subject_or_empty}"``
    # matches the TypeScript convention exactly -- both languages use the
    # literal colon with no padding or normalization. Note that for
    # subject=None, ``subject or ''`` evaluates to '', which is also what
    # ``_evaluate_locally`` uses as the FNV input -- so the cache key
    # encodes the full identity of the (flag, subject_for_hash) pair.
    cache_key = f"{flag_name}:{subject or ''}"
    now = time.time()

    # Step 1: Cache lookup (fast path; AAP performance gate is <=20ms p99
    # for cache hits, which this trivially satisfies -- a dict lookup
    # plus two compares is sub-microsecond). The lock is held only for
    # the dict access; we exit the lock before any HTTP work.
    with _CACHE_LOCK:
        entry = _FLAG_CACHE.get(cache_key)
        if entry is not None:
            value, expires_at = entry
            if expires_at > now:
                return value
            # Expired entry remains in the dict; the cache write below
            # will overwrite it. We do NOT pop here because doing so
            # would require holding the lock across the API call, which
            # would defeat the goal of unblocking concurrent threads.

    # Step 2: API call. Lock has been RELEASED so other threads can
    # service their own cache lookups while this thread waits on the
    # network. _fetch_from_api returns None on any failure (Rule RF3).
    api_response = _fetch_from_api(flag_name, subject)

    if api_response is not None:
        # Local evaluation per Rule RF4 -- this applies steps 3 and 4 of
        # the canonical 4-step order (overrides were already resolved
        # by the API and folded into the response's 'enabled' field).
        resolved = _evaluate_locally(flag_name, subject, api_response)
    else:
        # Step 3: env fallback (Rule RF3 fail-open). _env_fallback is
        # provably non-raising and always returns a bool.
        resolved = _env_fallback(flag_name)

    # Cache the resolved boolean with a TTL window starting NOW. We
    # re-read the TTL on every miss so test code mutating
    # FLAGS_CACHE_TTL_MS between calls is honored without process
    # restart. The lock is held only for the dict write, not the network
    # call above.
    expires_at = now + _get_cache_ttl_seconds()
    with _CACHE_LOCK:
        _FLAG_CACHE[cache_key] = (resolved, expires_at)

    return resolved


def clear_cache() -> None:
    """Clear the in-process flag cache. **Test use only.**

    Production code MUST NOT call this -- the cache TTL machinery handles
    invalidation correctly. This function exists solely so unit tests can
    assert clean state between test cases (e.g., to test that a fresh
    HTTP call is made after env-var manipulation, or to ensure one test
    case's cache entry does not leak into the next).

    The function is idempotent: clearing an already-empty cache is a
    no-op. The lock is acquired so concurrent ``is_enabled()`` calls
    cannot observe a partially-cleared cache.

    Returns:
        None. The function clears the cache as a side effect.
    """
    with _CACHE_LOCK:
        _FLAG_CACHE.clear()
