# -*- coding: utf-8 -*-  # noqa: UP009
# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""HTTP authentication override for the auth_v2 addon.

This module overrides ``ir.http._authenticate(endpoint)`` to insert the
``AUTH_V2_ENABLED`` feature-flag check as the FIRST synchronous step.
When the flag is ``False`` (default), the legacy Odoo authentication
pipeline runs unchanged via ``super()._authenticate(endpoint)``. When
the flag is ``True``, the bearer token from the ``Authorization``
header is validated by the auth-sidecar's ``POST /validate`` endpoint.

The two code paths are mutually exclusive per Rule R4 (Flag Exclusivity):
exactly one branch executes per request.

Fail mode (Rule R13 -- Sidecar Fail-Closed):
    Any sidecar failure with the flag enabled raises
    ``werkzeug.exceptions.ServiceUnavailable`` (HTTP 503). The override
    does NOT fall back to the legacy authentication path under failure.
    This is the OPPOSITE of the flags-API failure mode (Rule RF3 fail-open)
    and is intentional: silent legacy fallback under V2 failure would
    create an authentication oracle.

Resolution flow (when AUTH_V2_ENABLED is True):
    1. Extract the bearer token from the ``Authorization`` header. Missing
       or malformed header -> HTTP 401 (Unauthorized).
    2. Determine the required tier (``'admin'`` or ``'basic'``) from the
       endpoint's ``routing.get('auth')``.
    3. Call ``auth_v2.validate_token(token, app_id='odoo', required_tier=...)``
       which proxies to the auth-sidecar's ``POST /validate`` endpoint.
       Per Rule R13 (fail-closed), any sidecar failure raises
       ``ServiceUnavailable`` from inside ``validate_token``; the
       exception bubbles up unchanged from this file.
    4. If ``valid is False``: raise HTTP 401.
    5. Look up or auto-provision the ``res.users`` row by email
       (``share=False`` for internal users; first-login auto-provisioning
       per FR-10).
    6. ``request.update_env(user=user_record.id)`` to install the user
       into the environment so downstream Odoo code (controllers, ORM
       checks, etc.) sees the authenticated user.
    7. Return ``None`` WITHOUT calling ``super()._authenticate(endpoint)``
       (Rule R4 / R13 -- once V2 owns the request, legacy MUST NOT run).

Rules Enforced:
    - R3  (Flag isolation):       feature_flags.is_enabled() is the FIRST line
    - R4  (Flag exclusivity):     strict if/else branching; never both
    - R10 (Odoo schema scope):    no fields added to any ORM model
    - R13 (Sidecar fail-closed):  ServiceUnavailable on any sidecar failure
    - R23 (Log hygiene):          tokens, secrets, full PII never logged
    - R8  (Secrets containment):  no literal secrets

Companion components (out of this file's scope):
    - ``auth_v2.py`` -- the sidecar HTTP client (provides ``validate_token``)
    - ``feature_flags.py`` -- the cache->API->env flag client (provides ``is_enabled``)
    - ``packages/auth/src/sidecar/validate.ts`` -- the server-side ``POST /validate`` handler
    - ``packages/admin-ui/src/api/evaluate.ts`` -- the flags evaluation API

See:
    - AAP Section 0.4.1.3 (Direct Modifications Required -- Odoo)
    - AAP Section 0.5.1.5 (Group 5 -- Odoo Addon)
    - AAP Section 0.7.1 R3, R4, R10, R13, R23, R8
"""

import logging

import werkzeug.exceptions

from odoo import models
from odoo.http import request

from . import auth_v2 as auth_v2_module
from . import feature_flags as feature_flags_module

# Module-level logger per Rule R28 (structured logging). All diagnostic
# output from this file goes through ``_logger``; ``print()`` is forbidden.
# The logger name follows the standard ``__name__`` convention (resolves to
# ``odoo.addons.auth_v2.models.ir_http``) so operators can filter the
# auth_v2 namespace as a whole.
_logger = logging.getLogger(__name__)


class IrHttp(models.AbstractModel):
    """Override Odoo's ir.http to dispatch authentication to the V2 sidecar
    when ``AUTH_V2_ENABLED`` is true.

    The class extends the base ``ir.http`` AbstractModel via ``_inherit``,
    which is Odoo's standard pattern for HTTP-layer customization. The same
    pattern is used by ``auth_signup``, ``auth_oauth``, and ``auth_timeout``.

    Per Rule R3, the override is a pure dispatcher: when the V2 flag is
    false, ``super()._authenticate(endpoint)`` runs unchanged. When the flag
    is true, the V2 path executes and ``super()`` is NEVER called -- this
    is the strict if/else branching that Rule R4 (Flag Exclusivity) requires.

    Threading note:
        Odoo's request handling is thread-based (one Python thread per
        worker request). The classmethods on this model are stateless and
        re-entrant; per-request state lives in ``odoo.http.request`` (a
        thread-local). No instance state is mutated, so the override is
        safe under Odoo's concurrent worker model.
    """

    _inherit = 'ir.http'

    @classmethod
    def _extract_bearer_token(cls) -> str | None:
        """Extract the bearer token from the current request's Authorization header.

        The header is parsed with the case-sensitive ``Bearer `` prefix
        (capital B per OAuth 2.0 RFC 6750 section 2.1). A token value that
        is missing the prefix, has a different prefix (e.g., ``Basic``,
        lowercase ``bearer``), or is empty after trimming, returns ``None``.
        The caller surfaces ``None`` as HTTP 401.

        Per Rule R23 (log hygiene), this helper does NOT log the token
        value on success or on failure. Token contents -- whether valid,
        expired, malformed, or absent -- are never written to logs.

        Returns:
            The token string (without the ``Bearer `` prefix and with
            surrounding whitespace stripped), or ``None`` when the
            Authorization header is missing, has a non-Bearer scheme, or
            contains an empty token after the prefix.
        """
        # ``request.httprequest`` is the underlying werkzeug Request object.
        # ``.headers.get('Authorization', '')`` returns '' when the header
        # is absent, so no None-check is needed before ``startswith``.
        auth_header = request.httprequest.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return None
        # Slice off ``'Bearer '`` (7 characters). Trim any surrounding
        # whitespace defensively -- some clients append a stray newline.
        token = auth_header[len('Bearer '):].strip()
        if not token:
            return None
        return token

    @classmethod
    def _required_tier_for_endpoint(cls, endpoint) -> str:
        """Derive the required_tier parameter from the endpoint's routing config.

        Inspects ``endpoint.routing.get('auth')`` to determine whether the
        route requires admin or basic access. The mapping is:

            - ``'admin'``       -> ``'admin'``
            - ``'user'``        -> ``'basic'`` (default authenticated user)
            - anything else     -> ``'basic'`` (defensive default)

        The sidecar's ``POST /validate`` endpoint uses this tier to
        determine which permission row to check in the
        ``user_app_permissions`` table. ``'basic'`` requires only an
        ungated app permission for ``odoo``; ``'admin'`` additionally
        requires the ``admin`` tier on that permission row.

        Note:
            This is a heuristic mapping driven by the route's existing
            ``auth=`` decorator argument. Routes that need admin access
            should declare ``@http.route(..., auth='admin')`` (or use a
            future custom auth method) so the mapping is explicit. Routes
            using the standard ``auth='user'`` map to the ``'basic'`` tier
            in our two-tier permission model.

        Args:
            endpoint: Odoo's resolved werkzeug endpoint object. Has a
                ``.routing`` dict populated by the ``@http.route(...)``
                decorator at module load time.

        Returns:
            ``'admin'`` for admin-tier routes; ``'basic'`` otherwise. The
            return value is always one of these two literals.
        """
        # ``endpoint.routing`` is a dict set by Odoo's @http.route decorator.
        # ``getattr(..., None) or {}`` defends against malformed endpoints
        # (e.g., during certain test setups) by treating a missing or None
        # ``routing`` attribute as an empty dict.
        routing = getattr(endpoint, 'routing', None) or {}
        auth_value = routing.get('auth', 'user')
        if auth_value == 'admin':
            return 'admin'
        return 'basic'

    @classmethod
    def _lookup_or_provision_user(cls, email: str):
        """Return the res.users record for the given email, creating it on
        first login if absent.

        Per FR-10 / AAP Section 0.4.1.3, when the sidecar reports
        ``valid=true`` for a user that has no ``res.users`` row yet, this
        method creates one with ``share=False``. The created row uses the
        email as the login (matching Odoo's standard convention) and the
        email as the display name (the sidecar may eventually provide a
        ``name`` claim; for now the email is sufficient and unambiguous).

        Per Rule R10 (Odoo schema scope), this method does NOT alter the
        ``res.users`` schema. It only inserts a new row using the standard
        Odoo ``create()`` API with the documented standard fields
        ``login``, ``name``, and ``share``. The lookup uses ``login`` as
        the search key because Odoo's standard convention is that the
        login equals the email for OAuth-provisioned users.

        Per Rule R23, this method MAY log the email on auto-provisioning
        because email is the user's primary identifier and is already
        visible to admins. It does NOT log tokens, secrets, or any
        non-email PII.

        Args:
            email: The user's email from the validated token. Used both
                as the search key (against ``res.users.login``) and as
                the value for the ``login`` and ``name`` fields on the
                new row when auto-provisioning.

        Returns:
            The ``res.users`` recordset containing exactly one record --
            either the existing active user matching the email or the
            newly-created row.
        """
        # Search for an existing active user by login (which equals email
        # per Odoo's standard convention). ``.sudo()`` is required because
        # this code runs BEFORE authentication completes; without sudo,
        # the search would fail with no permissions. ``('active', '=',
        # True)`` filters out archived users -- we want to find the active
        # row only. ``limit=1`` makes the recordset deterministic.
        user = request.env['res.users'].sudo().search(
            [('login', '=', email), ('active', '=', True)],
            limit=1,
        )
        if user:
            return user

        # Auto-provision: first V2 login for this email.
        # ``share=False`` marks this as a standard internal user (NOT a
        # portal/external user). Per Rule R10, the create payload uses
        # ONLY documented Odoo fields; no fields are added to res.users.
        # Per Rule R23, the email is logged (it's a non-secret identifier);
        # the token and any secret are NEVER logged.
        _logger.info(
            "auth_v2: auto-provisioning res.users on first V2 login for %s",
            email,
        )
        return request.env['res.users'].sudo().create({
            'login': email,
            'name': email,
            'share': False,
        })

    @classmethod
    def _authenticate(cls, endpoint):
        """Authenticate the current request, optionally via the V2 sidecar.

        THE FIRST executable line is the ``AUTH_V2_ENABLED`` flag check
        (Rule R3 -- Flag Isolation). When the flag is ``False``,
        ``super()._authenticate(endpoint)`` runs unchanged and zero V2
        code executes. When the flag is ``True``, the V2 path validates
        the bearer token via the auth-sidecar and ``super()`` is NEVER
        called.

        Per Rule R4 (Flag Exclusivity), the override is a strict if/else
        branch: exactly ONE of the two paths runs per request. There is
        no code path where both legacy and V2 auth execute for the same
        request.

        Per Rule R13 (Sidecar Fail-Closed), any sidecar failure with the
        flag enabled raises ``ServiceUnavailable`` (HTTP 503) from
        ``auth_v2.validate_token`` and the exception bubbles up unchanged
        through this method. We do NOT catch it; we do NOT fall back to
        ``super()._authenticate(endpoint)``. Silent legacy fallback under
        V2 failure would create an authentication oracle.

        Args:
            endpoint: Odoo's resolved werkzeug endpoint with a ``.routing``
                dict populated by the ``@http.route(...)`` decorator.

        Returns:
            ``None`` on success in the V2 branch (matching the base class's
            return shape -- the base ``_authenticate`` also returns ``None``
            implicitly). The V2 branch sets ``request.uid`` via
            ``request.update_env(user=...)`` as its side effect.

            On the legacy branch, returns whatever ``super()._authenticate``
            returns (preserving full backward compatibility).

        Raises:
            werkzeug.exceptions.Unauthorized: When the bearer token is
                missing, malformed, expired, blacklisted, has insufficient
                permissions, or has the wrong audience claim. (HTTP 401)
            werkzeug.exceptions.ServiceUnavailable: When the V2 flag is
                true and the sidecar is unreachable, returns non-200,
                returns malformed JSON, or returns ``valid=true`` with no
                email payload. (HTTP 503 -- Rule R13 fail-closed)
        """
        # =====================================================================
        # CRITICAL: This is THE first synchronous statement in the override
        # per Rule R3 (Flag Isolation). NO code may execute before this check.
        #
        # ``is_enabled()`` is the only function called before the flag dispatch.
        # Internally, ``is_enabled()`` reads in the order:
        #     in-process cache -> flags API -> os.environ fallback (Rule RF3 fail-open)
        # Per Rule RF3, a flags-API failure FALLS BACK to ``os.environ``;
        # it does NOT raise. This means a flag-system outage manifests as
        # the legacy path continuing to run (the safe default).
        # =====================================================================
        if not feature_flags_module.is_enabled('AUTH_V2_ENABLED'):
            # Flag is OFF: defer entirely to the legacy Odoo authentication
            # chain. Per Rule R4, NO V2 code below this line will execute.
            # The base class's _authenticate handles CORS preflight, session
            # validation, and dispatch to ``_auth_method_<auth>``.
            return super()._authenticate(endpoint)

        # =====================================================================
        # Flag is ON: V2 authentication via the auth-sidecar.
        #
        # Per Rule R4, ``super()._authenticate(endpoint)`` MUST NOT be
        # called below this point. We are now in the V2 branch and own the
        # entire auth lifecycle for this request. Per Rule R13, any failure
        # in this branch raises ServiceUnavailable; we never fall back to
        # the legacy path.
        # =====================================================================

        # Step 1: Extract the bearer token. Missing/malformed -> HTTP 401.
        token = cls._extract_bearer_token()
        if token is None:
            # Rule R23: do not log the auth header value on missing/malformed.
            # The generic 401 message avoids leaking implementation details
            # while still giving honest clients enough information to fix
            # their requests (e.g., add a ``Bearer `` prefix).
            raise werkzeug.exceptions.Unauthorized(
                description="Missing or malformed Authorization header. Expected: Bearer <token>",
            )

        # Step 2: Determine the required tier from the endpoint's routing
        # configuration. ``'admin'`` for explicitly-admin-gated routes,
        # ``'basic'`` for the standard ``auth='user'`` case.
        required_tier = cls._required_tier_for_endpoint(endpoint)

        # Step 3: Validate the token via the sidecar.
        # Per Rule R13 (fail-closed), any sidecar failure raises
        # ``ServiceUnavailable`` (HTTP 503) which BUBBLES UP unchanged.
        # We do NOT catch it here; ``validate_token`` is responsible for
        # translating all sidecar failures (timeouts, connection errors,
        # non-200 statuses, JSON parse errors) into ServiceUnavailable.
        # The lack of a try/except around this call is INTENTIONAL and
        # is the literal enforcement of Rule R13.
        result = auth_v2_module.validate_token(
            token=token,
            app_id='odoo',
            required_tier=required_tier,
        )

        # Step 4: Interpret the sidecar's response.
        # The sidecar returns ``{valid: bool, user: {email, sub, tier}}``
        # per FR-2. Token-level rejections (signature failure, expired
        # token, blacklisted jti, missing audience claim, missing
        # permission row) come back as ``valid=false`` with a 200 HTTP
        # status; we surface them all as HTTP 401 here. Sidecar-level
        # errors (auth-sidecar misconfigured, etc.) come back as 5xx and
        # are translated to 503 by ``validate_token`` itself, never
        # reaching this branch.
        if not result.get('valid'):
            raise werkzeug.exceptions.Unauthorized(
                description="Token validation failed.",
            )

        # Step 5: Look up or auto-provision the res.users row.
        # Sidecar contract: when ``valid=True``, ``result['user']`` is a
        # dict with at least an ``email`` key. Defensive coding: if the
        # ``user`` payload is absent or missing the email, we treat it as
        # a sidecar protocol violation (Rule R13 spirit -- fail-closed).
        user_payload = result.get('user') or {}
        email = user_payload.get('email')
        if not email:
            # Sidecar returned valid=true but no email -- protocol violation.
            # Per Rule R13 (fail-closed), refuse rather than guess. We use
            # ``ServiceUnavailable`` (NOT ``Unauthorized``) because the
            # token was technically valid; the failure is in the sidecar's
            # response shape, which is an upstream issue.
            # Per Rule R23, we log the protocol-violation event but NOT
            # the token, the secret, or any payload contents.
            _logger.error(
                "auth_v2: sidecar returned valid=true with no email; refusing",
            )
            raise werkzeug.exceptions.ServiceUnavailable(
                description="Authentication backend returned malformed payload.",
            )

        # Look up the res.users row (or auto-provision on first login).
        user_record = cls._lookup_or_provision_user(email)

        # Step 6: Set ``request.uid`` via ``update_env(user=...)`` so Odoo's
        # environment cache is invalidated correctly. Direct mutation of
        # ``request.uid`` is forbidden in Odoo 19 (the property's setter
        # raises ``NotImplementedError`` -- see ``odoo/http.py``);
        # ``update_env(user=...)`` is the canonical pattern, also used by
        # the base class's ``_auth_method_bearer``.
        request.update_env(user=user_record.id)

        # Step 7: CRITICAL -- return WITHOUT calling ``super()._authenticate()``.
        # Per Rule R13 (fail-closed) and Rule R4 (mutual exclusion), once
        # the V2 branch is engaged, the legacy authentication MUST NOT
        # run. Returning here completes the authentication for this
        # request. The base class's ``_authenticate`` also returns None
        # implicitly, so the return shape is consistent across both
        # branches.
        return None
