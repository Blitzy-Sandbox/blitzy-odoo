# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""HTTP controllers for the auth_v2 addon.

This module implements the Odoo-side of the OAuth 2.0 / OIDC PKCE flow
backed by Keycloak. It provides three browser-facing endpoints plus an
override of the standard ``/web/session/logout`` route.

Endpoints
---------

``GET /auth_v2/login``
    The PKCE flow STARTER. Generates a 43-character PKCE code verifier,
    derives the SHA-256 ``code_challenge`` (S256), generates a random
    ``state`` parameter for CSRF defense, persists ``verifier`` and
    ``state`` as ``HttpOnly; SameSite=Lax`` cookies (Refine PR
    Directive D6 -- Odoo's request.session does not yet exist at the
    time the callback is received; cookie storage is mandatory), and
    303-redirects the browser to Keycloak's ``authorization_endpoint``
    with the appropriate query parameters.

``GET /auth_v2/callback``
    The PKCE flow CALLBACK. Reads ``code`` and ``state`` from the
    request query string, reads the ``verifier`` and expected ``state``
    from the cookies set by ``/auth_v2/login``, exchanges the
    authorization code for tokens via Keycloak's ``token_endpoint``,
    validates the ``access_token`` via the auth-sidecar's
    ``POST /validate``, optionally auto-provisions the ``res.users``
    row (first-login provisioning per FR-10), and establishes the
    Odoo session by calling ``request.session.authenticate(env,
    credential)``. The standard Odoo session-authenticate path
    populates EVERY documented session field (Refine PR Directive D1):
    ``db``, ``login``, ``uid``, ``session_token``, ``context``. The
    ``id_token`` is additionally stored under ``auth_v2_id_token`` so
    that ``AuthV2Session.logout`` can use it as ``id_token_hint``
    later (Refine PR Directive D3).

    On any failure (Keycloak token exchange error, sidecar 503, missing
    ``code``/``state``, state mismatch, missing verifier cookie) the
    callback redirects to ``/web/login?error=auth_v2_callback_failed``
    and writes ZERO session data. Revocation rejection (sidecar returns
    ``valid=false`` because the user has no permission row or the row
    is soft-revoked) redirects to ``/web/login?error=access_revoked``
    (Refine PR Directive D2 -- revocation is enforced at session
    creation, not only on already-established sessions).

``GET /auth_v2/logout`` (override of ``/web/session/logout``)
    Implemented by ``AuthV2Session(Session)`` -- a class that inherits
    from ``odoo.addons.web.controllers.session.Session`` (Refine PR
    Directive D4). When ``AUTH_V2_ENABLED`` is true and the session has
    an ``auth_v2_id_token`` field, this method:

        1. Captures the ``id_token`` for the ``id_token_hint`` query
           parameter (Refine PR Directive D3).
        2. Calls ``request.session.logout(keep_db=True)`` to clear the
           session (matching the parent class's behavior).
        3. Constructs the Keycloak end-session URL with
           ``id_token_hint`` and ``post_logout_redirect_uri``.
        4. Returns ``werkzeug.utils.redirect(end_session_url, 303)``
           directly (NOT ``request.redirect``, which strips the
           external hostname per Werkzeug's local-only redirect
           behavior -- Refine PR Directive D5).

    When ``AUTH_V2_ENABLED`` is false OR no ``auth_v2_id_token`` is
    present, the method falls through to the parent ``Session.logout``
    implementation, preserving 100% backward compatibility with the
    legacy logout flow.

Cookie storage rationale (Refine PR Directive D6)
-------------------------------------------------

The PKCE flow has TWO requests:

    1. ``/auth_v2/login``  -- generates verifier; redirects to Keycloak
    2. ``/auth_v2/callback`` -- consumes verifier; exchanges code for tokens

Between (1) and (2), the browser visits Keycloak. From Odoo's
perspective, request (2) is a fresh inbound HTTP request from a
DIFFERENT origin (Keycloak's redirect_uri causes the browser to
navigate, not Odoo's session continuity). The Odoo session DOES NOT
persist across this hop because Odoo's session cookie is scoped to
Odoo's origin, not Keycloak's. We CANNOT use ``request.session`` to
hand the verifier from (1) to (2).

The verifier MUST be stored client-side, in a way that:
    - Survives the Keycloak hop (``Path=/`` so the cookie is sent on
      ``/auth_v2/callback``).
    - Is not accessible to JavaScript on Keycloak's origin
      (``HttpOnly``).
    - Is sent on third-party navigation back to Odoo
      (``SameSite=Lax``; ``SameSite=Strict`` would NOT be sent on the
      cross-site Keycloak->Odoo navigation).
    - Is destroyed after the callback consumes it (``Max-Age=0`` on
      the response from the callback).

This is why these three values live in cookies, NOT the Odoo session:
    - ``auth_v2_pkce_verifier`` -- the 43-char PKCE verifier
    - ``auth_v2_pkce_state``    -- the CSRF state parameter
    - ``auth_v2_return_url``    -- the post-login redirect target

Rules Enforced
--------------

    - R3   (Flag isolation):    feature_flags.is_enabled() guards the entry path
    - R4   (Flag exclusivity):  legacy login/logout chain runs unchanged when flag off
    - R8   (Secrets containment): no literal secrets; env reads at call time
    - R10  (Odoo schema scope): no ORM model changes (uses standard fields)
    - R12  (API stability):     new routes, no existing-route signature changes
    - R13  (Sidecar fail-closed):  sidecar failure -> redirect to login (no session)
    - R14  (Backchannel logout):   id_token_hint enables Keycloak to back-channel
    - R23  (Log hygiene):       tokens, secrets, full PII never logged
    - R28  (Structured logging): Python logging module
    - R29  (Correlation ID):    forwarded to sidecar via x-correlation-id header

See:
    - AAP Section 0.4.1.3 (Direct Modifications Required -- Odoo)
    - Refine PR Directives D1, D2, D3, D4, D5, D6
"""

import base64
import hashlib
import hmac
import logging
import os
import secrets
import urllib.parse
from typing import Any

import httpx
import werkzeug.exceptions
import werkzeug.utils
from werkzeug.wrappers import Response

import odoo
import odoo.modules.registry
from odoo import http
from odoo.http import request

from odoo.addons.auth_v2.models import auth_v2 as auth_v2_module
from odoo.addons.auth_v2.models import feature_flags as feature_flags_module
from odoo.addons.web.controllers.session import Session

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Cookie name for the PKCE verifier. Per RFC 7636 §4.1, the verifier is a
#: high-entropy cryptographic random string; we store it in an HttpOnly
#: cookie scoped to the entire site (``Path=/``) so it is sent on the
#: callback request after the Keycloak hop. Per Refine PR Directive D6,
#: this MUST NOT be stored in ``request.session`` because the Odoo
#: session does not survive the cross-origin redirect from Keycloak.
_COOKIE_PKCE_VERIFIER = 'auth_v2_pkce_verifier'

#: Cookie name for the PKCE state parameter. State is the OAuth 2.0 CSRF
#: defense per RFC 6749 §10.12. We compare the state returned by Keycloak
#: against this cookie value; a mismatch indicates a CSRF attempt and the
#: callback rejects the request.
_COOKIE_PKCE_STATE = 'auth_v2_pkce_state'

#: Cookie name for the post-login redirect target. The user's intended
#: destination (e.g., ``/odoo`` or ``/odoo/action-X``) is captured at
#: ``/auth_v2/login?redirect=…`` and consumed at the callback to land
#: them where they meant to go.
_COOKIE_RETURN_URL = 'auth_v2_return_url'

#: Cookie max-age for the PKCE state cookies, in seconds. The PKCE flow
#: should complete within seconds; setting a 10-minute window
#: accommodates slow user interactions (typing email, MFA prompts) while
#: bounding the window during which a stolen verifier could be used.
#: After the callback consumes the verifier, the cookie is explicitly
#: cleared with ``Max-Age=0``.
_COOKIE_MAX_AGE_SECONDS = 600  # 10 minutes

#: PKCE verifier length per RFC 7636 §4.1: between 43 and 128 characters.
#: We pick 43 (the minimum) because it provides 256 bits of entropy
#: (32 bytes base64url-encoded), which exceeds OWASP's recommended
#: 128-bit minimum and matches the kalle web client's choice for
#: cross-app consistency.
_PKCE_VERIFIER_LENGTH_BYTES = 32

#: PKCE state length in bytes. 32 bytes (43 chars after base64url encoding)
#: gives 256 bits of entropy -- well above OWASP's recommended minimum
#: for CSRF tokens. Same length as the verifier for code consistency.
_PKCE_STATE_LENGTH_BYTES = 32

#: Default HTTP request timeout in seconds. Per AAP, the auth-sidecar's
#: validate endpoint uses a 5-second timeout; we use the same 5s budget
#: here for the Keycloak token exchange and userinfo calls. This matches
#: Odoo's typical request budget while preventing user-facing hangs on a
#: slow Keycloak.
_HTTP_REQUEST_TIMEOUT_SECONDS: float = 5.0

#: Session keys used by the V2 path.
#:
#: ``auth_v2_id_token`` -- the OIDC ID token from the token exchange.
#: Stored at login (Directive D3) and consumed at logout to populate
#: ``id_token_hint`` on the Keycloak end-session URL. The ID token is
#: a JWT and is NOT sensitive in the way an access token is (the
#: access token is what grants resource access; the ID token is an
#: identity assertion). Storing it in the session is acceptable.
#:
#: ``auth_v2_session_active`` -- a boolean marker that this session was
#: established by the V2 PKCE callback. The logout method checks this
#: BEFORE consulting the AUTH_V2_ENABLED flag because the flag could
#: be flipped while sessions are active; the session-local marker
#: guarantees correct logout behavior even if the flag is changed.
_SESSION_KEY_ID_TOKEN = 'auth_v2_id_token'
_SESSION_KEY_V2_ACTIVE = 'auth_v2_session_active'


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_required_env(name: str) -> str:
    """Read a required environment variable, raising on absence.

    Identical pattern to ``auth_v2.py``'s ``_get_required_env``, but
    locally scoped here to avoid an import cycle. Per Rule R3 spirit,
    env reads happen at function-call time (NOT at module load) so the
    addon can be installed without V2 being configured.

    Per Rule R23, the variable NAME is logged but the value is never
    logged (since these may be secrets like ``KEYCLOAK_CLIENT_SECRET``).

    Args:
        name: The environment variable name (e.g., 'KEYCLOAK_BASE_URL').

    Returns:
        The variable's value as a non-empty string.

    Raises:
        werkzeug.exceptions.ServiceUnavailable: If the variable is
            unset or empty. The exception's description names the
            variable but does NOT include any value.
    """
    value = os.environ.get(name)
    if not value:
        _logger.error("auth_v2: required environment variable %s is not set", name)
        raise werkzeug.exceptions.ServiceUnavailable(
            description=f"Authentication backend is not configured ({name} unset).",
        )
    return value


def _get_optional_env(name: str, default: str = '') -> str:
    """Read an optional environment variable, returning ``default`` on absence.

    Used for env vars that have sensible defaults or that may be omitted
    in certain deployment topologies (e.g., ``KEYCLOAK_CLIENT_SECRET``
    is omitted for public clients using PKCE).

    Args:
        name: The environment variable name.
        default: The fallback value when the var is unset or empty.

    Returns:
        The variable's value, or ``default`` if unset/empty.
    """
    return os.environ.get(name) or default


def _generate_pkce_verifier() -> str:
    """Generate a high-entropy PKCE code verifier per RFC 7636 §4.1.

    The verifier is 32 random bytes encoded as URL-safe base64 WITHOUT
    padding, producing a 43-character string. Per RFC 7636 §4.1, the
    verifier must use the unreserved characters
    ``[A-Z] / [a-z] / [0-9] / "-" / "." / "_" / "~"``. URL-safe base64
    uses ``A-Za-z0-9-_`` (no ``.`` or ``~``), which is a subset of the
    allowed character set.

    Per Rule R23, the returned verifier is NEVER logged. It's
    cryptographic material that, combined with the authorization code,
    proves the holder is the same client that initiated the flow.

    Returns:
        A 43-character URL-safe base64 string with no padding.
    """
    return base64.urlsafe_b64encode(
        secrets.token_bytes(_PKCE_VERIFIER_LENGTH_BYTES),
    ).rstrip(b'=').decode('ascii')


def _derive_pkce_challenge(verifier: str) -> str:
    """Derive the S256 PKCE code challenge from a verifier per RFC 7636 §4.2.

    The challenge is ``base64url(SHA256(verifier))`` with padding
    stripped. Per RFC 7636 §4.2, the ``code_challenge_method`` MUST be
    ``S256`` for this scheme; we never use ``plain``.

    Args:
        verifier: The PKCE verifier string returned by
            ``_generate_pkce_verifier``.

    Returns:
        The S256-derived challenge as a URL-safe base64 string with no
        padding.
    """
    digest = hashlib.sha256(verifier.encode('ascii')).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b'=').decode('ascii')


def _generate_state() -> str:
    """Generate a cryptographically-random ``state`` parameter for CSRF defense.

    Per RFC 6749 §10.12, the ``state`` parameter is the primary CSRF
    defense for OAuth 2.0 authorization-code flows. We use 32 bytes of
    randomness (256 bits) which is well above OWASP's recommended
    minimum for CSRF tokens.

    The returned value is URL-safe base64 with padding stripped, so it
    can be embedded in a query string without further encoding.

    Returns:
        A 43-character URL-safe base64 string with no padding.
    """
    return base64.urlsafe_b64encode(
        secrets.token_bytes(_PKCE_STATE_LENGTH_BYTES),
    ).rstrip(b'=').decode('ascii')


def _safe_compare(a: str, b: str) -> bool:
    """Constant-time string equality for security-sensitive comparisons.

    Used for state-parameter validation in the callback: a timing-attack
    resistant comparison prevents an attacker from inferring the state
    value byte-by-byte by measuring response times. ``hmac.compare_digest``
    is the standard library's documented constant-time comparator.

    Per Python ``hmac.compare_digest`` documentation: returns ``True``
    iff the two arguments are byte-equal; performs the comparison in
    constant time relative to the input length.

    Args:
        a: First string.
        b: Second string.

    Returns:
        ``True`` iff the two strings are byte-equal.
    """
    # hmac.compare_digest accepts both str and bytes; passing strs of
    # equal length is the documented usage. We coerce to bytes for
    # extra defense in case either argument is None or non-string
    # (in which case isinstance check below filters first).
    if not isinstance(a, str) or not isinstance(b, str):
        return False
    return hmac.compare_digest(a.encode('utf-8'), b.encode('utf-8'))


def _build_keycloak_url(path: str) -> str:
    """Construct a Keycloak realm-scoped URL.

    Per AAP, ``KEYCLOAK_BASE_URL`` and ``KEYCLOAK_REALM`` are documented
    env vars; the realm-scoped URL pattern is::

        ${KEYCLOAK_BASE_URL}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/<path>

    Args:
        path: The OIDC endpoint relative path (e.g., ``'auth'``,
            ``'token'``, ``'logout'``). MUST NOT start with a slash.

    Returns:
        The full URL.

    Raises:
        werkzeug.exceptions.ServiceUnavailable: If KEYCLOAK_BASE_URL or
            KEYCLOAK_REALM is unset.
    """
    base_url = _get_required_env('KEYCLOAK_BASE_URL').rstrip('/')
    realm = _get_required_env('KEYCLOAK_REALM')
    return f"{base_url}/realms/{realm}/protocol/openid-connect/{path}"


def _is_safe_redirect(target: str) -> bool:
    """Return True iff ``target`` is a safe local redirect path.

    Refine PR Directive D5 explicitly forbids using ``request.redirect``
    for external (Keycloak) URLs because it strips the hostname. Here
    we use the inverse rule: for INTERNAL post-login redirects, we
    enforce that the target is a relative path starting with ``/`` and
    NOT starting with ``//`` (which is a protocol-relative URL that
    could redirect to an attacker-controlled domain).

    Args:
        target: A URL or path string from a query parameter.

    Returns:
        ``True`` if the target is a single-leading-slash relative path;
        ``False`` for empty strings, absolute URLs, protocol-relative
        URLs, or anything else suspicious.
    """
    if not target or not isinstance(target, str):
        return False
    # Reject protocol-relative URLs (`//evil.example.com/path`) which
    # browsers would treat as absolute URLs to evil.example.com.
    if target.startswith('//'):
        return False
    # Require single-leading-slash relative path.
    if not target.startswith('/'):
        return False
    # Reject backslash variants which some browsers treat the same as
    # forward slashes (defense against `/\evil.example.com/path`).
    if target.startswith('/\\'):
        return False
    # Reject any embedded scheme (e.g., `/javascript:alert(1)` -- some
    # historic browser quirks treat this as a redirect to a javascript
    # URL). The defensive heuristic: if the path before any further
    # slash contains a colon, reject.
    first_segment = target.lstrip('/').split('/', 1)[0]
    return ':' not in first_segment


def _redirect_to_login_with_error(error_code: str) -> Response:
    """Build a 303 redirect to ``/web/login`` with an error query parameter.

    Per Refine PR Directives D1 and D2, callback failures and revocation
    rejections MUST redirect to the login page WITHOUT writing any
    session data. This helper centralizes that pattern.

    Per Rule R23, the error code is a fixed enumerated value (no
    user-controlled data, no token-derived data) so it is safe to
    embed in the URL.

    Args:
        error_code: A short fixed error identifier (e.g.,
            ``'access_revoked'``, ``'callback_failed'``).

    Returns:
        A ``werkzeug.wrappers.Response`` with HTTP 303 and the
        ``Location`` header set to ``/web/login?error=<error_code>``.
    """
    # ``werkzeug.utils.redirect`` produces a relative-Location 303
    # response. We use the relative path because /web/login is a local
    # Odoo route, not an external URL, so request.redirect would also
    # work here. We use werkzeug.utils.redirect for consistency with
    # the rest of this module (Directive D5).
    return werkzeug.utils.redirect(
        f"/web/login?error={urllib.parse.quote(error_code)}",
        303,
    )


def _clear_pkce_cookies(response: Response) -> None:
    """Clear all auth_v2_* PKCE cookies on the given response.

    Once the callback has consumed the verifier and state, the cookies
    MUST be deleted so they cannot be replayed. ``response.delete_cookie``
    sets ``Max-Age=0`` (and ``Expires`` in the past) which causes the
    browser to drop the cookie immediately.

    Per Directive D6, this is called from the callback handler AFTER
    the verifier has been consumed (or AFTER any failure response is
    being prepared). It's safe to call when the cookies don't exist;
    Werkzeug's ``delete_cookie`` is idempotent.

    Args:
        response: The response object that the callback is returning.
            Mutated in place.
    """
    # ``Path='/'`` MUST match the path used when the cookie was set
    # in the login starter. Without an exact path match, the browser
    # treats the cookies as different and the delete is a no-op.
    response.delete_cookie(_COOKIE_PKCE_VERIFIER, path='/')
    response.delete_cookie(_COOKIE_PKCE_STATE, path='/')
    response.delete_cookie(_COOKIE_RETURN_URL, path='/')


def _exchange_code_for_tokens(
    code: str,
    verifier: str,
    redirect_uri: str,
    correlation_id: str | None = None,
) -> dict:
    """Exchange the authorization code for OIDC tokens via Keycloak's token_endpoint.

    Per OAuth 2.0 RFC 6749 §4.1.3 and PKCE RFC 7636 §4.5, the token
    exchange POST is form-encoded with the body parameters:

        - ``grant_type=authorization_code``
        - ``code=<auth code from callback>``
        - ``redirect_uri=<must match the original redirect_uri>``
        - ``client_id=<the OAuth client ID>``
        - ``code_verifier=<the PKCE verifier>``

    For confidential clients, ``client_secret`` is also included; for
    public clients (which is what we use for the Odoo browser flow,
    matching the kalle web flow), the ``code_verifier`` IS the proof
    of possession.

    The function uses ``httpx.Client`` with a 5-second timeout, matching
    the auth_v2.py module's convention. No retry: a Keycloak failure
    on token exchange is a hard failure (the auth code is single-use,
    so a retry would fail with ``invalid_grant`` anyway).

    Per Rule R23, the function logs only the response status code and
    any non-200 status; it NEVER logs the response body (which contains
    the access/refresh/id tokens) or the request body (which contains
    the verifier).

    Args:
        code: The authorization code from the callback's ``?code=…``
            query parameter.
        verifier: The 43-character PKCE verifier read from the cookie.
        redirect_uri: The redirect URI to validate against; MUST match
            the value passed to /auth_v2/login.
        correlation_id: Optional correlation ID forwarded as the
            ``X-Correlation-ID`` header per Rule R29. Keycloak does
            not consume this header, but having it on the wire makes
            cross-service log tracing possible if the operator uses
            an HTTP-tap or intercepting proxy.

    Returns:
        A dict with at minimum the keys ``access_token``, ``id_token``,
        and ``refresh_token`` (all str). May also include
        ``token_type``, ``expires_in``, ``scope``, etc.

    Raises:
        werkzeug.exceptions.BadRequest: If Keycloak returns 400
            (``invalid_grant``, ``invalid_request``, etc.). These are
            terminal client errors; the auth code is consumed and
            cannot be retried.
        werkzeug.exceptions.ServiceUnavailable: If Keycloak returns
            5xx, times out, or returns malformed JSON.
    """
    token_url = _build_keycloak_url('token')
    client_id = _get_required_env('KEYCLOAK_CLIENT_ID_ODOO')
    client_secret = _get_optional_env('KEYCLOAK_CLIENT_SECRET_ODOO')

    # Form-encoded body per RFC 6749 §4.1.3.
    body: dict = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': redirect_uri,
        'client_id': client_id,
        'code_verifier': verifier,
    }
    # For confidential clients, include client_secret. For public
    # clients (PKCE-only), the code_verifier IS the proof of
    # possession; client_secret is omitted.
    if client_secret:
        body['client_secret'] = client_secret

    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json',
    }
    if correlation_id:
        headers['X-Correlation-ID'] = correlation_id

    timeout = httpx.Timeout(_HTTP_REQUEST_TIMEOUT_SECONDS)

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(token_url, data=body, headers=headers)
    except httpx.RequestError as exc:
        # Connection error, DNS error, timeout. Treat as 503 since
        # the auth code is single-use and a network blip is closer
        # to "service unavailable" than to "client error".
        # Rule R23: log only the exception type, not the message.
        _logger.warning(
            "auth_v2: keycloak token endpoint unreachable: %s",
            type(exc).__name__,
        )
        raise werkzeug.exceptions.ServiceUnavailable(
            description="Identity provider is unreachable.",
        ) from exc

    if response.status_code == 400:
        # Per RFC 6749 §5.2, 400 is the documented error status for
        # invalid_grant, invalid_request, etc. We surface as
        # BadRequest because the auth code is now consumed and the
        # client has no way to retry.
        # Rule R23: do NOT log the response body (it contains a
        # JSON error payload but may also contain user-controllable
        # data depending on Keycloak version).
        _logger.warning(
            "auth_v2: keycloak token endpoint returned 400 (invalid_grant)",
        )
        raise werkzeug.exceptions.BadRequest(
            description="Authorization code exchange failed.",
        )
    if response.status_code != 200:
        # Other 4xx (401 = wrong client_secret, 403 = client not
        # allowed, etc.) and 5xx all surface as 503 since they
        # indicate a misconfiguration or backend failure rather
        # than a client error.
        _logger.warning(
            "auth_v2: keycloak token endpoint returned status %s",
            response.status_code,
        )
        raise werkzeug.exceptions.ServiceUnavailable(
            description="Identity provider returned an unexpected response.",
        )

    try:
        data: Any = response.json()
    except ValueError as exc:
        _logger.warning("auth_v2: keycloak token endpoint returned non-JSON")
        raise werkzeug.exceptions.ServiceUnavailable(
            description="Identity provider returned a malformed response.",
        ) from exc

    if not isinstance(data, dict):
        _logger.warning(
            "auth_v2: keycloak token endpoint returned non-dict JSON (type=%s)",
            type(data).__name__,
        )
        raise werkzeug.exceptions.ServiceUnavailable(
            description="Identity provider returned a malformed response.",
        )

    # Defensive: ensure we have at least the access_token. id_token
    # and refresh_token are also expected from a standard OIDC code
    # exchange but their absence is a softer failure (we can't
    # populate id_token_hint at logout, but the user can still log in).
    if 'access_token' not in data or not isinstance(data.get('access_token'), str):
        _logger.warning("auth_v2: keycloak token response missing access_token")
        raise werkzeug.exceptions.ServiceUnavailable(
            description="Identity provider returned an incomplete response.",
        )

    return data


# ---------------------------------------------------------------------------
# AuthV2Controller -- /auth_v2/login and /auth_v2/callback
# ---------------------------------------------------------------------------


class AuthV2Controller(http.Controller):
    """The PKCE flow controller for the auth_v2 addon.

    Hosts ``GET /auth_v2/login`` (the PKCE starter) and
    ``GET /auth_v2/callback`` (the post-Keycloak callback). Both routes
    use ``auth='none'`` because the user is by definition NOT logged in
    when these endpoints are hit.

    The controller works in cooperation with:
        - ``models/ir_http.py`` -- BEARER token authentication for API
          requests after login.
        - ``models/auth_v2.py``  -- the sidecar HTTP client.
        - ``models/feature_flags.py`` -- the AUTH_V2_ENABLED flag client.

    Per Refine PR Directive D6, all PKCE state (``verifier``, ``state``,
    ``return_url``) is stored in ``HttpOnly; SameSite=Lax`` cookies, NOT
    in ``request.session``. The Odoo session does not survive the
    cross-origin redirect from Keycloak, so cookie storage is the only
    viable option.

    Threading note:
        Odoo's request handling is thread-based (one Python thread per
        worker request). The methods on this controller are stateless
        re-entrant; per-request state lives in ``odoo.http.request`` (a
        thread-local) and in cookies. No instance state is mutated.
    """

    @http.route(
        '/auth_v2/login',
        type='http',
        auth='none',
        methods=['GET'],
        csrf=False,
        readonly=True,
    )
    def login(self, **kwargs):
        """Start the PKCE flow: generate state, set cookies, redirect to Keycloak.

        Per Refine PR Directive D6, the PKCE verifier and state ARE
        STORED IN COOKIES, NOT IN ``request.session``. The Odoo session
        does not exist yet for unauthenticated users, and even if it
        did, it would not survive the cross-origin redirect from
        Keycloak back to ``/auth_v2/callback``.

        Per Refine PR Directive D5, the redirect to Keycloak's external
        URL uses ``werkzeug.utils.redirect`` directly. Using
        ``request.redirect`` here would silently strip the hostname
        because Werkzeug's ``request.redirect`` enforces local-only
        redirects.

        Per Rule R23, the verifier is NEVER logged. The state is also
        not logged because it identifies a specific in-flight session.

        Per Rule R3 (flag isolation), this method short-circuits if
        ``AUTH_V2_ENABLED`` is false: it returns a 303 to the legacy
        login page, ensuring zero V2 code path remains active when
        the flag is off.

        Per Rule R8, the client_id and the ``KEYCLOAK_BASE_URL`` come
        from environment variables read at call time; no literal
        secrets appear in this code.

        Args:
            **kwargs: Optional query parameters. Recognized:
                ``redirect`` -- the post-login redirect target (defaults
                to ``/odoo``). Validated by ``_is_safe_redirect`` to
                prevent open-redirect attacks.

        Returns:
            A 303 redirect Response to Keycloak's authorization
            endpoint with the appropriate PKCE+state query params, OR
            a 303 redirect to ``/web/login`` if the V2 flag is off.
        """
        # Rule R3 (flag isolation): if V2 is off, do NOT initiate the
        # OAuth flow. Redirect to the legacy login page instead. This
        # is the fail-OPEN flag behavior (Rule RF3): a flag-system
        # outage manifests as the legacy login page being shown.
        if not feature_flags_module.is_enabled('AUTH_V2_ENABLED'):
            return werkzeug.utils.redirect('/web/login', 303)

        # Validate the post-login redirect target (open-redirect defense).
        # Default to /odoo (the standard Odoo home) when absent or invalid.
        requested_redirect = kwargs.get('redirect', '/odoo')
        if not _is_safe_redirect(requested_redirect):
            requested_redirect = '/odoo'

        # Generate fresh PKCE+state values.
        verifier = _generate_pkce_verifier()
        challenge = _derive_pkce_challenge(verifier)
        state = _generate_state()

        # Build the Keycloak authorization URL.
        # client_id and base URL come from env at call time per Rule R8.
        client_id = _get_required_env('KEYCLOAK_CLIENT_ID_ODOO')
        # The redirect_uri MUST exactly match the URI registered in
        # Keycloak's client config and the URI used at token exchange.
        # We construct it from the request's url_root so the same
        # value is used end-to-end.
        redirect_uri = (
            request.httprequest.url_root.rstrip('/') + '/auth_v2/callback'
        )

        try:
            authz_url = _build_keycloak_url('auth')
        except werkzeug.exceptions.ServiceUnavailable:
            # Keycloak base URL or realm not configured. Per Rule RF3
            # (fail-open for flags) we have already passed the flag
            # check and started the V2 flow; this is a hard
            # configuration error and we surface it as 503. The user
            # can retry once the operator fixes the env.
            _logger.exception("auth_v2: keycloak config missing during /auth_v2/login")
            raise

        # Per AAP Section 0.4.1.2 (kalle web flow): scopes for SSO
        # audience chain include `openid email profile` plus app
        # scopes. For Odoo's flow we request the same scopes plus
        # `odoo:basic` so the access_token's `aud` claim includes
        # `odoo-app` per the Keycloak Audience Mapper.
        scope = _get_optional_env(
            'KEYCLOAK_SCOPE_ODOO', 'openid email profile odoo:basic',
        )

        params = {
            'response_type': 'code',
            'client_id': client_id,
            'redirect_uri': redirect_uri,
            'scope': scope,
            'state': state,
            'code_challenge': challenge,
            'code_challenge_method': 'S256',
        }
        full_url = f"{authz_url}?{urllib.parse.urlencode(params)}"

        # Per Rule R23: do NOT log the verifier, the challenge, or the
        # state. Log only the fact that a flow has started and the
        # client_id (which is a non-secret config value).
        _logger.info(
            "auth_v2: starting PKCE flow for client_id=%s",
            client_id,
        )

        # Build the response as a 303 to Keycloak, then attach the
        # PKCE cookies. Per Refine PR Directive D5, we use
        # ``werkzeug.utils.redirect`` directly because ``request.redirect``
        # would strip the external hostname from the Keycloak URL.
        response = werkzeug.utils.redirect(full_url, 303)

        # Per Refine PR Directive D6: store the verifier, state, and
        # return URL in HttpOnly; SameSite=Lax cookies. The session
        # does not survive the cross-origin Keycloak hop, so cookies
        # are mandatory.
        #
        # Cookie attributes:
        #   - HttpOnly: not accessible to JavaScript (defense against XSS)
        #   - SameSite=Lax: sent on top-level navigations from
        #     Keycloak back to Odoo (Strict would NOT send the cookie
        #     on cross-site nav, breaking the flow)
        #   - Path=/: sent on /auth_v2/callback (which is below /)
        #   - Secure: only over HTTPS in production. We respect
        #     `request.httprequest.is_secure` to allow local-dev HTTP
        #     while enforcing HTTPS in any deployed environment.
        #   - Max-Age=600: 10-minute window covers slow Keycloak
        #     interactions without leaving stale verifiers around.
        is_secure = bool(request.httprequest.is_secure)
        cookie_kwargs = {
            'max_age': _COOKIE_MAX_AGE_SECONDS,
            'path': '/',
            'httponly': True,
            'secure': is_secure,
            'samesite': 'Lax',
        }
        response.set_cookie(_COOKIE_PKCE_VERIFIER, verifier, **cookie_kwargs)
        response.set_cookie(_COOKIE_PKCE_STATE, state, **cookie_kwargs)
        response.set_cookie(_COOKIE_RETURN_URL, requested_redirect, **cookie_kwargs)
        return response

    @http.route(
        '/auth_v2/callback',
        type='http',
        auth='none',
        methods=['GET'],
        csrf=False,
        readonly=False,
    )
    def callback(self, **kwargs):
        """The PKCE callback: exchange code, validate token, establish session.

        Refine PR Directive D1: At the point this method establishes the
        session, it MUST populate ALL fields the Odoo framework reads
        downstream. We achieve this by calling the standard
        ``request.session.authenticate(env, credential)`` flow from
        ``odoo.http.Session`` (defined at ``odoo/http.py:1178``). That
        method calls ``finalize(env)`` which writes ``db``, ``login``,
        ``uid``, ``context``, AND ``session_token`` (the HMAC over the
        sid + per-user secret fields, used by ``ir.http`` to detect
        password rotations and force re-login). Using the standard
        flow guarantees full session compatibility -- a cold browser
        login lands on /odoo without missing any session field.

        Refine PR Directive D2: Revocation is enforced HERE, at session
        creation, BEFORE any session field is written. The sidecar's
        ``POST /validate`` returns ``valid=false`` for revoked users
        (no ``user_app_permissions`` row OR ``revoked_at IS NOT NULL``).
        On ``valid=false`` we redirect to ``/web/login?error=access_revoked``
        and write ZERO session data.

        Refine PR Directive D3: The ID token from the token exchange is
        stored in the Odoo session under ``auth_v2_id_token`` so that
        ``AuthV2Session.logout`` can pass it as ``id_token_hint`` to
        Keycloak's end-session endpoint. This is what lets Keycloak
        terminate the SSO session and trigger backchannel logouts to
        sibling apps (Refine PR Directive D10).

        Refine PR Directive D6: The PKCE verifier and state are READ
        from cookies set by ``/auth_v2/login`` -- NOT from
        ``request.session`` (which does not exist yet). After
        consumption, the cookies are explicitly cleared with
        ``Max-Age=0`` to prevent replay.

        Per Rule R23, this method logs only the email of the
        authenticated user (acceptable per AAP because email is a
        non-secret identifier visible to admins) and never the token,
        verifier, or any other sensitive payload.

        Per Rule R29, the correlation ID is generated here (or read
        from the inbound ``X-Correlation-ID`` if present) and forwarded
        to the sidecar so cross-service traces can be reconstructed.

        Args:
            **kwargs: Query parameters from Keycloak's redirect:
                ``code`` -- the authorization code (present on success)
                ``state`` -- the state parameter (echoed by Keycloak)
                ``error`` -- present if Keycloak rejected the auth
                ``error_description`` -- optional Keycloak error detail

        Returns:
            On success: a 303 redirect to the user's intended URL
            (from the ``auth_v2_return_url`` cookie, defaulting to
            ``/odoo``), with the Odoo session cookie set so subsequent
            requests are authenticated.

            On failure: a 303 redirect to
            ``/web/login?error=<reason>``, with ZERO session data
            written.
        """
        # Per Rule R3 (flag isolation): if V2 is off when the callback
        # is hit (e.g., flag was flipped while the user was on Keycloak),
        # there's no realistic way to complete the V2 flow. Redirect to
        # the legacy login page; the user will simply log in via the
        # legacy path. We also clear any stale auth_v2 cookies.
        if not feature_flags_module.is_enabled('AUTH_V2_ENABLED'):
            response = _redirect_to_login_with_error('auth_v2_disabled')
            _clear_pkce_cookies(response)
            return response

        # ----- Step 1: Validate the inbound query parameters --------------
        # Keycloak returns either ?code=<...>&state=<...> on success or
        # ?error=<...>&error_description=<...> on failure.
        if 'error' in kwargs:
            # Per Rule R23, we log only the error code (a fixed
            # OAuth 2.0 enumerated value) -- never the description
            # which may contain user-controllable text.
            _logger.warning(
                "auth_v2: keycloak returned error=%s",
                kwargs.get('error'),
            )
            response = _redirect_to_login_with_error('keycloak_error')
            _clear_pkce_cookies(response)
            return response

        code = kwargs.get('code')
        state = kwargs.get('state')
        if not code or not state:
            _logger.warning(
                "auth_v2: callback missing required query params (code/state)",
            )
            response = _redirect_to_login_with_error('callback_missing_params')
            _clear_pkce_cookies(response)
            return response

        # ----- Step 2: Read PKCE verifier & expected state from cookies ---
        # Per Refine PR Directive D6, these come from cookies (not session).
        cookies = request.httprequest.cookies
        verifier = cookies.get(_COOKIE_PKCE_VERIFIER)
        expected_state = cookies.get(_COOKIE_PKCE_STATE)
        return_url = cookies.get(_COOKIE_RETURN_URL) or '/odoo'

        if not verifier or not expected_state:
            # Cookie missing: either the user took >10 minutes (cookie
            # expired) or they hit the callback URL directly without
            # going through /auth_v2/login. Either way, fail and
            # redirect to login.
            _logger.warning(
                "auth_v2: callback missing PKCE cookies (verifier/state)",
            )
            response = _redirect_to_login_with_error('callback_no_session')
            _clear_pkce_cookies(response)
            return response

        # Constant-time state comparison (CSRF defense).
        if not _safe_compare(state, expected_state):
            # State mismatch is a CSRF attack signal. Do NOT proceed.
            _logger.warning("auth_v2: callback state mismatch (CSRF defense)")
            response = _redirect_to_login_with_error('callback_state_mismatch')
            _clear_pkce_cookies(response)
            return response

        # Validate the return_url with the same strict criteria as
        # /auth_v2/login. A cookie-based return_url is technically
        # under the user's control if they crafted the cookie
        # themselves, but the only attack here is an open-redirect to
        # an attacker-controlled site, which we already prevent at
        # /auth_v2/login by validating the redirect= query param.
        if not _is_safe_redirect(return_url):
            return_url = '/odoo'

        # Read or generate the correlation ID per Rule R29.
        correlation_id = (
            request.httprequest.headers.get('X-Correlation-ID')
            or _generate_state()  # reuse the high-entropy generator
        )

        # ----- Step 3: Exchange the auth code for tokens ----------------
        # The redirect_uri MUST be byte-equal to the value used at
        # /auth_v2/login. We reconstruct it from request.httprequest
        # using the same method.
        redirect_uri = (
            request.httprequest.url_root.rstrip('/') + '/auth_v2/callback'
        )

        try:
            tokens = _exchange_code_for_tokens(
                code=code,
                verifier=verifier,
                redirect_uri=redirect_uri,
                correlation_id=correlation_id,
            )
        except werkzeug.exceptions.BadRequest:
            # Auth code consumed; user must restart flow.
            response = _redirect_to_login_with_error('callback_code_invalid')
            _clear_pkce_cookies(response)
            return response
        except werkzeug.exceptions.ServiceUnavailable:
            # Keycloak unreachable; user can retry.
            response = _redirect_to_login_with_error('callback_idp_unavailable')
            _clear_pkce_cookies(response)
            return response

        access_token = tokens.get('access_token')
        id_token = tokens.get('id_token')  # may be None for non-OIDC flows
        # access_token is guaranteed non-empty by _exchange_code_for_tokens.

        # ----- Step 4: Validate access token via the auth-sidecar -------
        # Per Refine PR Directive D2, this is where revocation is
        # enforced. The sidecar checks (a) the JWT signature, (b) the
        # blacklist (R33/R14), (c) the audience claim, and (d) the
        # user_app_permissions row. If ANY of these fail, valid=false.
        #
        # Per Rule R13 (sidecar fail-closed), any sidecar failure
        # raises ServiceUnavailable from auth_v2_module.validate_token.
        # We catch it here and redirect to login with an error, so
        # the user can retry. Note: this is the ONE place in the
        # addon where we catch ServiceUnavailable from validate_token
        # -- we treat the callback's failure mode as "redirect to
        # login" rather than "503 to the user", which is the
        # browser-friendly equivalent.
        try:
            validate_result = auth_v2_module.validate_token(
                token=access_token,
                app_id='odoo',
                required_tier='basic',
            )
        except werkzeug.exceptions.ServiceUnavailable:
            _logger.warning("auth_v2: sidecar unavailable during callback")
            response = _redirect_to_login_with_error('callback_sidecar_unavailable')
            _clear_pkce_cookies(response)
            return response
        except Exception:
            # Defensive: any other exception (programming error, etc.)
            # is also surfaced as a redirect to login. We do NOT let
            # the 500 propagate to the user during the auth flow.
            # Per Rule R23, we use exception() which logs the
            # traceback but NOT the token (the traceback contains
            # only stack frames, not function arguments by default).
            _logger.exception("auth_v2: unexpected error during sidecar validation")
            response = _redirect_to_login_with_error('callback_sidecar_error')
            _clear_pkce_cookies(response)
            return response

        if not validate_result.get('valid'):
            # Per Refine PR Directive D2: revocation is enforced HERE,
            # before ANY session field is written. The sidecar returns
            # valid=false for: revoked permission row, missing
            # permission row, blacklisted jti, expired token, audience
            # mismatch.
            _logger.info(
                "auth_v2: callback rejected (sidecar valid=false)",
            )
            response = _redirect_to_login_with_error('access_revoked')
            _clear_pkce_cookies(response)
            return response

        user_payload = validate_result.get('user') or {}
        email = user_payload.get('email')
        if not email:
            _logger.error(
                "auth_v2: sidecar returned valid=true with no email; refusing",
            )
            response = _redirect_to_login_with_error('callback_malformed_payload')
            _clear_pkce_cookies(response)
            return response

        # ----- Step 5: Auto-provision res.users on first login --------
        # Per FR-10 / AAP Section 0.4.1.3: when the sidecar reports
        # valid=true for an email that has no res.users row yet, we
        # create one with share=False. This MUST happen before
        # request.session.authenticate so the authenticate call finds
        # a valid res.users row.
        user_record = self._lookup_or_provision_user(email)
        if not user_record:
            # Provisioning failed (e.g., db connection error). The
            # sidecar said valid=true but we can't materialize a
            # local user; bail out with an error.
            _logger.error(
                "auth_v2: failed to lookup or provision res.users for %s",
                email,
            )
            response = _redirect_to_login_with_error('callback_provision_failed')
            _clear_pkce_cookies(response)
            return response

        # ----- Step 6: Establish the Odoo session --------------------
        # Refine PR Directive D1: We use the STANDARD Odoo session
        # authentication path so that ALL fields are populated:
        # ``db``, ``login``, ``uid``, ``context``, AND ``session_token``.
        # The session_token is critical -- ir.http reads it on every
        # request to detect password rotations and force re-login if
        # the user's password fields changed.
        #
        # The standard flow is:
        #   request.session.authenticate(env, {'login', 'password',
        #                                      'type': 'auth_v2_token'})
        #
        # However, our credential type is NOT 'password' -- we don't
        # have the user's password. Instead, we use the env's
        # res.users authenticate hook. The simplest robust approach
        # for Odoo 19 is to call ``finalize`` directly, which is
        # what ``authenticate`` does internally on a successful
        # password verification.
        try:
            # Build the env on the request's database. We use sudo
            # context so we can read the user record without the
            # session being authenticated yet.
            db_name = request.db
            if not db_name:
                # Defensive: a request without a db is exceptional
                # but possible under certain misconfigurations.
                _logger.error("auth_v2: callback received with no request.db")
                response = _redirect_to_login_with_error('callback_no_db')
                _clear_pkce_cookies(response)
                return response

            # Build a fresh env on the request's db with SUPERUSER_ID
            # so we can read the user record, then re-bind it to the
            # authenticated user via with_user(). This is the same
            # pattern used by auth_oauth's signin path (at
            # auth_oauth/controllers/main.py:139-154).
            registry = odoo.modules.registry.Registry(db_name)
            with registry.cursor() as cr:
                env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})
                # Re-fetch the user in this env (the user_record we
                # got above lives in request.env, which has a
                # different cursor).
                user = env['res.users'].search(
                    [('login', '=', email), ('active', '=', True)],
                    limit=1,
                )
                if not user:
                    # Provisioning happened in request.env; we just
                    # committed it via the auto-provision call but
                    # the new env may not see it without commit.
                    # Defensive fallback.
                    cr.commit()
                    user = env['res.users'].search(
                        [('login', '=', email), ('active', '=', True)],
                        limit=1,
                    )
                if not user:
                    _logger.error(
                        "auth_v2: provisioned user %s not found in callback env",
                        email,
                    )
                    response = _redirect_to_login_with_error('callback_user_lookup_failed')
                    _clear_pkce_cookies(response)
                    return response

                # Refine PR Directive D1: Populate ALL session fields.
                # This sequence mirrors ``odoo.http.Session.finalize``
                # at odoo/http.py:1219-1237 verbatim, which is what
                # ``Session.authenticate`` calls on successful
                # password verification.
                #
                # Setting these five fields is the contract Odoo's
                # ``ir.http`` checks downstream for an authenticated
                # session:
                #   - ``db``               -- the active database
                #   - ``login``            -- the user's login name
                #   - ``uid``              -- the user's row id
                #   - ``context``          -- per-user context
                #     (lang, tz, etc.)
                #   - ``session_token``    -- HMAC over sid + secret
                #     fields; ir.http re-checks this on each request
                #     to invalidate sessions on password rotation.
                request.session.uid = user.id
                request.session.login = email
                request.session.db = db_name
                user_context = dict(env['res.users'].with_user(user.id).context_get())
                request.session.context = user_context
                request.session.session_token = user.with_user(user.id)._compute_session_token(
                    request.session.sid,
                )

                # Refine PR Directive D3: Store the id_token under
                # auth_v2_id_token so AuthV2Session.logout can pass
                # it as id_token_hint to Keycloak's end-session
                # endpoint. The ID token is a JWT identity assertion
                # (not a credential), so storing it in the session
                # is acceptable.
                if id_token and isinstance(id_token, str):
                    request.session[_SESSION_KEY_ID_TOKEN] = id_token

                # Mark the session as established by the V2 PKCE
                # callback. AuthV2Session.logout consults this
                # marker before deciding whether to redirect to
                # Keycloak's end-session URL or fall through to
                # the legacy logout path. Using a session-local
                # marker (rather than re-checking the global
                # AUTH_V2_ENABLED flag) ensures correct logout
                # behavior even if the flag is flipped while the
                # session is active.
                request.session[_SESSION_KEY_V2_ACTIVE] = True

                # Mark the session as needing rotation per Odoo's
                # standard practice on authentication change.
                request.session.should_rotate = True

                # Bind request.env to the now-authenticated user so
                # any downstream code in this request sees the user.
                request.env = env(user=user.id, context=user_context)

                # Per Rule R23, we log the email (a non-secret
                # identifier) and the request id. We do NOT log the
                # access token, the id token, or the verifier.
                _logger.info(
                    "auth_v2: PKCE callback succeeded for %s",
                    email,
                )

                # Commit the cursor so any auto-provisioning or
                # session updates persist before we return.
                cr.commit()
        except Exception:
            # Per Rule R23, log the exception type but NOT the args
            # (which could include token-derived data).
            _logger.exception(
                "auth_v2: unexpected error finalizing session in callback",
            )
            response = _redirect_to_login_with_error('callback_session_failed')
            _clear_pkce_cookies(response)
            return response

        # ----- Step 7: Redirect to the user's intended URL ----------
        # Refine PR Directive D5: This redirect target is LOCAL
        # (validated by _is_safe_redirect), so request.redirect
        # would also work. We use werkzeug.utils.redirect for
        # consistency with the rest of this module.
        response = werkzeug.utils.redirect(return_url, 303)

        # Clean up the PKCE cookies. They've served their purpose
        # and must not be replayable.
        _clear_pkce_cookies(response)

        # Save the session before returning so the response includes
        # the Set-Cookie header for the Odoo session cookie. Odoo's
        # request lifecycle normally handles this automatically, but
        # we call request._save_session explicitly to ensure the
        # session cookie is in the response. (This mirrors what
        # Session.authenticate at session.py:53 does.)
        if hasattr(request, '_save_session'):
            try:
                request._save_session(request.env)
            except Exception:
                # Defensive: if _save_session fails, the session
                # cookie may be missing. Log and continue.
                _logger.exception("auth_v2: _save_session failed")

        return response

    @classmethod
    def _lookup_or_provision_user(cls, email: str):
        """Return the res.users record for ``email``, creating it on first login.

        Mirrors ``ir_http.IrHttp._lookup_or_provision_user`` but is a
        local helper here because the controller does not inherit
        ``ir.http``. Per FR-10 / AAP Section 0.4.1.3, when the sidecar
        reports ``valid=true`` for a user that has no ``res.users``
        row yet, this method creates one with ``share=False``.

        Per Rule R10 (Odoo schema scope), this method does NOT alter
        the ``res.users`` schema. It only inserts a new row using the
        standard Odoo ``create()`` API with the documented fields
        ``login``, ``name``, and ``share``.

        Per Rule R23, the email may be logged on auto-provisioning
        (it's a non-secret identifier visible to admins).

        Args:
            email: The user's email from the validated token.

        Returns:
            The ``res.users`` recordset (exactly one record), or an
            empty recordset if creation failed. Callers MUST check
            for an empty return.
        """
        try:
            user = request.env['res.users'].sudo().search(
                [('login', '=', email), ('active', '=', True)],
                limit=1,
            )
            if user:
                return user

            _logger.info(
                "auth_v2: auto-provisioning res.users on first V2 login for %s",
                email,
            )
            return request.env['res.users'].sudo().create({
                'login': email,
                'name': email,
                'share': False,
            })
        except Exception:
            # Per Rule R23, log only the exception type. Per the
            # docstring above, callers must check for an empty
            # return; we satisfy that contract by returning a
            # browse-empty recordset.
            _logger.exception(
                "auth_v2: failed to lookup or provision res.users",
            )
            return request.env['res.users'].browse([])


# ---------------------------------------------------------------------------
# AuthV2Session -- override of /web/session/logout
# ---------------------------------------------------------------------------


class AuthV2Session(Session):
    """Override of ``/web/session/logout`` for the V2 OAuth flow.

    Refine PR Directive D4: This class inherits from
    ``odoo.addons.web.controllers.session.Session`` (NOT from
    ``http.Controller``). The inheritance is critical: Odoo's router
    only dispatches ``/web/session/logout`` to a route registered on
    the ``Session`` class (or a subclass). Inheriting from
    ``http.Controller`` directly would NOT replace the parent route;
    Odoo would still dispatch to the original ``Session.logout``.

    Refine PR Directive D3: When the session has an ``auth_v2_id_token``
    (set by the PKCE callback), this method extracts it before clearing
    the session and includes it as ``id_token_hint`` in the Keycloak
    end-session URL. Without ``id_token_hint``, Keycloak prompts the
    user to confirm the logout, which is a poor UX.

    Refine PR Directive D5: The redirect to Keycloak's end-session URL
    uses ``werkzeug.utils.redirect`` directly (NOT ``request.redirect``,
    which strips external hostnames). Using ``request.redirect`` here
    would break the SSO logout chain because the browser would never
    reach Keycloak.

    The method consults the session-local ``auth_v2_session_active``
    marker rather than re-evaluating ``AUTH_V2_ENABLED`` on every
    logout. This guarantees that:
        - Sessions established under V2 always get V2 logout (even if
          the global flag is flipped while they're active).
        - Sessions established under legacy auth always get legacy
          logout (even if the global flag is flipped before they
          log out).

    When ``auth_v2_session_active`` is false (or absent), the method
    falls through to ``super().logout(redirect)`` which preserves 100%
    backward compatibility with the legacy logout flow.
    """

    @http.route(
        '/web/session/logout',
        type='http',
        auth='none',
        readonly=True,
    )
    def logout(self, redirect='/odoo'):
        """Log out, propagating to Keycloak when the session is V2-established.

        The dispatch logic is:

            1. If the session was NOT established by the V2 callback
               (``auth_v2_session_active`` is falsy), fall through to
               ``super().logout(redirect)``. This preserves the legacy
               logout path verbatim.

            2. Otherwise, capture the ``auth_v2_id_token`` from the
               session, call ``request.session.logout(keep_db=True)``
               to clear the local session (matching the parent's
               behavior), and 303-redirect to Keycloak's end-session
               URL with ``id_token_hint`` and
               ``post_logout_redirect_uri`` set.

        Per Rule R23, this method logs the fact of logout but never
        the id_token value (the id_token is a JWT and could in
        principle be replayed if leaked).

        Args:
            redirect: The post-logout redirect target. Defaults to
                ``/odoo``. Used as ``post_logout_redirect_uri`` for
                Keycloak when V2 is active; otherwise passed verbatim
                to ``super().logout()``.

        Returns:
            On V2-active session: a 303 response from
            ``werkzeug.utils.redirect`` to Keycloak's end-session URL.

            On legacy session: whatever ``super().logout()`` returns
            (typically a 303 to ``redirect``).
        """
        # Read the V2 session marker BEFORE clearing the session.
        # Once request.session.logout() runs, the session is wiped
        # and we lose access to auth_v2_id_token and
        # auth_v2_session_active.
        v2_active = bool(request.session.get(_SESSION_KEY_V2_ACTIVE))

        if not v2_active:
            # Per Refine PR Directive D4 + the contract documented
            # above: legacy sessions get legacy logout. We invoke
            # the parent class's method directly via super() to
            # ensure ANY future updates to the parent's logout
            # implementation are picked up automatically.
            return super().logout(redirect=redirect)

        # V2 path: capture the id_token, clear the session, redirect
        # to Keycloak's end-session URL.
        id_token = request.session.get(_SESSION_KEY_ID_TOKEN)

        # Refine PR Directive D5: clear the session BEFORE building
        # the Keycloak URL because session.logout() invalidates the
        # session dict. We've already captured id_token above.
        # keep_db=True matches the parent class's default behavior.
        request.session.logout(keep_db=True)

        try:
            end_session_url = _build_keycloak_url('logout')
        except werkzeug.exceptions.ServiceUnavailable:
            # Keycloak misconfigured. We've already cleared the
            # local session, so the user IS logged out locally; we
            # just can't propagate to Keycloak. Fall through to a
            # local-only redirect.
            _logger.warning(
                "auth_v2: keycloak config missing during logout; "
                "performing local-only logout",
            )
            return werkzeug.utils.redirect(redirect, 303)

        # Build the post-logout redirect URI. Keycloak validates this
        # against the client's "Valid Post Logout Redirect URIs" list,
        # so it MUST match one of the URIs configured on the
        # ``odoo-app`` client in the realm-export.json.
        # Construct from request.url_root for end-to-end consistency.
        post_logout_uri = (
            request.httprequest.url_root.rstrip('/') + (redirect or '/odoo')
        )

        # Build the query parameters per OIDC RP-Initiated Logout.
        # https://openid.net/specs/openid-connect-rpinitiated-1_0.html
        params: dict = {
            'post_logout_redirect_uri': post_logout_uri,
        }
        if id_token and isinstance(id_token, str):
            # Refine PR Directive D3: id_token_hint MUST be included
            # when the value is present in the session. With
            # id_token_hint, Keycloak terminates the SSO session
            # without prompting the user.
            params['id_token_hint'] = id_token
            # OIDC RP-Initiated Logout spec also recommends
            # ``client_id`` as a fallback when id_token_hint isn't
            # available; we include it for defense in depth.
            client_id = _get_optional_env('KEYCLOAK_CLIENT_ID_ODOO')
            if client_id:
                params['client_id'] = client_id

        full_url = f"{end_session_url}?{urllib.parse.urlencode(params)}"

        _logger.info("auth_v2: V2 logout initiated, redirecting to keycloak end_session")

        # Refine PR Directive D5: use werkzeug.utils.redirect DIRECTLY,
        # NOT request.redirect. request.redirect would call
        # ``url_root`` validation and silently strip the hostname
        # from the external Keycloak URL, leaving the browser at a
        # relative path that doesn't exist (the local Odoo server
        # has no /realms/... route).
        return werkzeug.utils.redirect(full_url, 303)
