# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""Sidecar HTTP client for the auth_v2 addon.

This module provides ``validate_token(token, app_id, required_tier)``,
the SOLE Python code path for V2 token validation. The function calls
the ``@blitzy/auth`` sidecar at ``POST {AUTH_SERVICE_URL}/validate``
and returns the parsed JSON response.

Failure mode (Rule R13 -- fail-closed):
    ANY failure -- connection error, timeout, non-200 status, JSON parse
    error -- raises ``werkzeug.exceptions.ServiceUnavailable`` (HTTP 503).
    The function does NOT return a default valid response. Silent fallback
    would create an authentication oracle.

Retry policy:
    Exactly ONE retry on HTTP 503. No retry on other 5xx, no retry on 4xx,
    no retry on connection failures or timeouts. After the retry attempt
    fails, ServiceUnavailable is raised.

Wire format (camelCase per the user's verbatim example):
    Request body:  {"token": str, "appId": str, "requiredTier": str}
    Response body: {"valid": bool, "user": {"email": str, "sub": str, "tier": str}}

    The Python parameter names are snake_case ("app_id", "required_tier")
    but the wire format keys are camelCase ("appId", "requiredTier") to
    match the TypeScript sidecar's contract.

Rules Enforced:
    - R13 (Sidecar fail-closed): all failures -> ServiceUnavailable
    - R23 (Log hygiene):         tokens/secrets never logged
    - R28 (Structured logging):  Python logging module, no print()
    - R8  (Secrets containment): no literal secrets; env reads at call time
    - R3  (Flag isolation):      no module-load side effects
    - R12 (API stability):       (token, app_id, required_tier) signature

Boundary contract:
    This module is a LEAF in the addon's dependency graph. It does NOT
    import any sibling module. The sole caller is ``ir_http.py``'s
    ``_authenticate`` override. The module raises ServiceUnavailable on
    every failure path; it NEVER raises Unauthorized (HTTP 401) directly.
    The caller inspects the returned ``valid`` field and translates
    ``valid is False`` into HTTP 401 itself.

See:
    - AAP Section 0.4.1.3 (Direct Modifications Required -- Odoo)
    - AAP Section 0.5.1.5 (Group 5 -- Odoo Addon)
    - AAP Section 0.7.1 R13 (Sidecar fail-closed -- THE invariant)
    - User Example: {token, appId, requiredTier} -> {valid, user: {email, sub, tier}}
"""

import logging
import os
from typing import Any

import httpx
import werkzeug.exceptions


_logger = logging.getLogger(__name__)

# Per AAP Section 0.4.1.3: "5s timeout, 1 retry on 503".
# httpx.Timeout(5.0) is equivalent to httpx.Timeout(connect=5.0,
# read=5.0, write=5.0, pool=5.0) -- 5 seconds for every phase.
_REQUEST_TIMEOUT_SECONDS: float = 5.0

# Per the AAP retry policy: exactly one retry on HTTP 503 only.
# Other 5xx (502/504/500) and 4xx are NOT retried.
_HTTP_SERVICE_UNAVAILABLE: int = 503

# HTTP 200 is the only success status from the sidecar's POST /validate.
# Token-level rejections come back as HTTP 200 with body {"valid": false},
# NOT as HTTP 401. Sidecar-level errors (wrong AUTH_SIDECAR_SECRET, internal
# errors) come back as 4xx/5xx and are translated to HTTP 503 by this client.
_HTTP_OK: int = 200


def _get_required_env(name: str) -> str:
    """Read a required environment variable, raising descriptive errors on absence.

    Per Gate 12 of the AAP, unset configuration MUST produce a descriptive
    error pointing at the variable name. We raise ServiceUnavailable here
    (not ValueError) because (a) we are in an HTTP request handler and
    (b) the operator's misconfiguration manifests to the client as a 503
    rather than a 500, which is more accurate ("the upstream auth service
    is not reachable" -- true: it's not even configured).

    Per Rule R3 spirit, env reads happen at function-call time (NOT at
    module load), so importing this module without V2 being configured
    does not raise. The error fires only when ``validate_token`` is
    actually invoked.

    Per Rule R23, the variable NAME is included in logs and the error
    description (it is a config key, not a secret), but the variable
    VALUE is never included (it might be a secret).

    Args:
        name: The environment variable name (e.g., 'AUTH_SERVICE_URL').

    Returns:
        The variable's value as a string.

    Raises:
        werkzeug.exceptions.ServiceUnavailable: If the variable is unset
            or empty. The exception's description names the variable but
            does NOT include any value (Rule R23).
    """
    value = os.environ.get(name)
    if not value:
        # Rule R23: do NOT include the secret value in the error message.
        # The variable NAME is acceptable since it's a config key, not a
        # secret. We treat empty strings as also-unset (defensive).
        _logger.error("auth_v2: required environment variable %s is not set", name)
        raise werkzeug.exceptions.ServiceUnavailable(
            description=f"Authentication backend is not configured ({name} unset).",
        )
    return value


def _post_with_timeout(
    url: str,
    payload: dict,
    headers: dict,
    timeout: httpx.Timeout,
) -> httpx.Response:
    """Execute a single POST request and return the response.

    This helper performs ONE request attempt. The retry logic lives in
    the caller (``validate_token``), which wraps this function in a
    try/except for ``httpx.RequestError`` and inspects the returned
    ``status_code`` to decide whether to retry.

    Connection-pool reuse across requests is unnecessary at our request
    volume (one call per Odoo HTTP request) and a fresh client per call
    keeps the function pure (no module-level state, easier to test, no
    risk of resource leaks). The context manager ensures the client is
    closed even on exception.

    Args:
        url: The full URL (e.g., 'http://localhost:4001/validate').
        payload: The JSON-serializable request body.
        headers: The HTTP headers (including Authorization and Content-Type).
        timeout: The httpx.Timeout instance.

    Returns:
        The httpx.Response object. The caller inspects status_code and
        calls .json() on the response.

    Raises:
        httpx.RequestError: On connection failure, timeout, DNS error,
            etc. Caller is responsible for translating these to
            ServiceUnavailable.
    """
    # httpx.Client is the synchronous client (Odoo is sync). Using a
    # context manager guarantees the client is closed on exit.
    with httpx.Client(timeout=timeout) as client:
        return client.post(url, json=payload, headers=headers)


def validate_token(token: str, app_id: str, required_tier: str) -> dict:
    """Validate a bearer token via the auth-sidecar's POST /validate endpoint.

    This is the SOLE entry point for V2 token validation in Odoo. It is
    called from ``ir_http.py``'s ``_authenticate`` override after the
    AUTH_V2_ENABLED flag check has confirmed V2 mode is active.

    The function:
        1. Reads AUTH_SERVICE_URL and AUTH_SIDECAR_SECRET from os.environ
           (raising ServiceUnavailable if either is unset, per Gate 12).
        2. Constructs the request body:
              {"token": ..., "appId": ..., "requiredTier": ...}
           (matching the user's verbatim example).
        3. Calls POST {AUTH_SERVICE_URL}/validate with:
              - Authorization: Bearer {AUTH_SIDECAR_SECRET}
              - Content-Type: application/json
              - 5-second timeout (per AAP)
        4. On HTTP 200: parses and returns the response JSON dict.
        5. On HTTP 503: retries ONCE with no delay. If still 503 (or
           connection error on retry), raises ServiceUnavailable.
        6. On any other failure (timeout, connection error, non-200
           non-503 status, JSON parse error, non-dict JSON): raises
           ServiceUnavailable per Rule R13 (fail-closed).

    Per Rule R13 (THE invariant of this module): the function NEVER
    returns a "default valid" response on failure. Silent fallback
    would create an authentication oracle. Every failure path raises
    ``werkzeug.exceptions.ServiceUnavailable`` (HTTP 503).

    Per Rule R12, the signature is the public contract:
        validate_token(token: str, app_id: str, required_tier: str) -> dict

    Per Rule R23, the function logs status codes, retry counts, and
    exception types -- but NEVER the token, the secret, or the full
    Authorization header.

    Args:
        token: The JWT bearer token (without the "Bearer " prefix).
        app_id: The application identifier ('odoo' for this addon, but
            'kalle' is also a valid value in the sidecar's domain).
        required_tier: The minimum tier required ('basic' or 'admin').

    Returns:
        The parsed JSON response, with shape::

            {
                "valid": bool,
                "user": {"email": str, "sub": str, "tier": str}
            }

        When ``valid`` is ``False``, the ``"user"`` key may be absent.
        The caller (``ir_http.py``) inspects ``valid`` and translates
        ``False`` into HTTP 401 itself.

    Raises:
        werkzeug.exceptions.ServiceUnavailable: On any sidecar failure
            or misconfiguration. (HTTP 503 -- Rule R13 fail-closed.)

    Note:
        The function NEVER raises Unauthorized (HTTP 401) directly. The
        caller (``ir_http.py``) inspects the returned ``valid`` field
        and raises 401 itself when ``valid`` is False. This separation
        keeps this module focused on transport concerns; protocol
        concerns live in the caller.
    """
    # Read config at call time (NOT at module load) per Rule R3.
    # _get_required_env raises ServiceUnavailable on missing config,
    # so this is also the first fail-closed checkpoint.
    base_url = _get_required_env('AUTH_SERVICE_URL')
    secret = _get_required_env('AUTH_SIDECAR_SECRET')

    # Construct the URL by stripping any trailing slash from base_url.
    # This makes the function robust to AUTH_SERVICE_URL=http://...:4001
    # vs AUTH_SERVICE_URL=http://...:4001/ (both common in env configs).
    url = f"{base_url.rstrip('/')}/validate"

    # Build the request payload per the user's verbatim example.
    # CamelCase keys (appId, requiredTier) match the sidecar's
    # TypeScript contract (which is camelCase per JS convention). The
    # Python parameter names are snake_case but the wire format is
    # camelCase.
    payload = {
        'token': token,
        'appId': app_id,
        'requiredTier': required_tier,
    }

    # Headers: bearer auth with the sidecar's pre-shared secret.
    # Per Rule R23, this header value is NEVER logged.
    headers = {
        'Authorization': f"Bearer {secret}",
        'Content-Type': 'application/json',
        # Accept JSON only -- defense in depth against unexpected
        # response types (e.g., HTML error pages from a misconfigured
        # reverse proxy).
        'Accept': 'application/json',
    }

    timeout = httpx.Timeout(_REQUEST_TIMEOUT_SECONDS)

    # ---- First attempt ---------------------------------------------------
    try:
        response = _post_with_timeout(
            url=url, payload=payload, headers=headers, timeout=timeout,
        )
    except httpx.RequestError as exc:
        # Connection error, DNS error, timeout, etc. on the FIRST attempt.
        # Per the retry policy, we do NOT retry on connection errors
        # (only on HTTP 503). One attempt is sufficient -- repeat
        # failures almost certainly indicate the sidecar is fully down.
        # Rule R23: log only the exception TYPE, not its message
        # (the message could conceivably contain the URL or token
        # in some httpx versions).
        _logger.warning(
            "auth_v2: sidecar request failed (first attempt; no retry): %s",
            type(exc).__name__,
        )
        raise werkzeug.exceptions.ServiceUnavailable(
            description="Authentication backend is unreachable.",
        ) from exc

    # ---- HTTP 503 retry (the documented one-time retry) ------------------
    if response.status_code == _HTTP_SERVICE_UNAVAILABLE:
        _logger.info(
            "auth_v2: sidecar returned 503 on first attempt; retrying once",
        )
        try:
            response = _post_with_timeout(
                url=url, payload=payload, headers=headers, timeout=timeout,
            )
        except httpx.RequestError as exc:
            _logger.warning(
                "auth_v2: sidecar request failed on retry attempt: %s",
                type(exc).__name__,
            )
            raise werkzeug.exceptions.ServiceUnavailable(
                description="Authentication backend is unreachable.",
            ) from exc
        if response.status_code == _HTTP_SERVICE_UNAVAILABLE:
            # Both attempts returned 503. Give up per the AAP retry
            # policy ("exactly ONE retry on HTTP 503").
            _logger.warning(
                "auth_v2: sidecar returned 503 after retry; giving up",
            )
            raise werkzeug.exceptions.ServiceUnavailable(
                description="Authentication backend is temporarily unavailable.",
            )

    # ---- All non-200 responses are fail-closed (Rule R13) ----------------
    # 401/403/4xx from the sidecar surface as 503 to the caller because
    # the sidecar's 401/403 represents a SIDECAR-level error (e.g., our
    # AUTH_SIDECAR_SECRET is wrong, or the sidecar's auth middleware
    # rejected our request). Token-level rejections come back as
    # HTTP 200 with body {"valid": false}, NOT as HTTP 401.
    if response.status_code != _HTTP_OK:
        _logger.warning(
            "auth_v2: sidecar returned unexpected status %s",
            response.status_code,
        )
        raise werkzeug.exceptions.ServiceUnavailable(
            description="Authentication backend returned an unexpected response.",
        )

    # ---- Parse the JSON response -----------------------------------------
    try:
        result: Any = response.json()
    except ValueError as exc:
        # response.json() raises json.JSONDecodeError (a ValueError
        # subclass) on parse failure. Catching ValueError is the
        # documented httpx idiom and covers both Python's stdlib
        # json.JSONDecodeError and any future variants.
        # Rule R23: do NOT log the raw response body (might contain
        # token-derived data or other sensitive content).
        _logger.warning("auth_v2: sidecar returned non-JSON response")
        raise werkzeug.exceptions.ServiceUnavailable(
            description="Authentication backend returned a malformed response.",
        ) from exc

    # ---- Defensive: the response MUST be a JSON object (dict) ------------
    # JSON allows top-level scalars, arrays, and objects. Our contract
    # requires an object: {"valid": bool, "user": {...}}. Anything else
    # is a malformed response and fails closed.
    if not isinstance(result, dict):
        _logger.warning(
            "auth_v2: sidecar returned non-dict JSON (type=%s)",
            type(result).__name__,
        )
        raise werkzeug.exceptions.ServiceUnavailable(
            description="Authentication backend returned a malformed response.",
        )

    # Successful response: caller inspects result["valid"] and the
    # nested result["user"] to decide whether to authorize the request.
    return result
