# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""Controller package for the auth_v2 addon.

This package houses HTTP controllers for the Odoo-side OAuth 2.0 / OIDC
flow:

    - ``main`` — Hosts:
        1. The PKCE callback endpoint (``GET /auth_v2/callback``) that
           exchanges the authorization code for OIDC tokens, validates
           the access token via the auth-sidecar, optionally
           auto-provisions the ``res.users`` row, and establishes the
           full Odoo session by calling the standard
           ``request.session.authenticate(env, credential)`` flow which
           populates every documented session field (``uid``, ``login``,
           ``db``, ``session_token``, ``context``).
        2. The PKCE login starter (``GET /auth_v2/login``) that
           generates the PKCE verifier+challenge+state, persists the
           verifier and state as ``HttpOnly; SameSite=Lax`` cookies
           (Refine PR Directive D6), and 303-redirects to Keycloak's
           ``authorization_endpoint``.
        3. The override of ``/web/session/logout`` via
           ``AuthV2Session(Session)`` — when ``AUTH_V2_ENABLED`` is true
           and an ``id_token`` is present in the session, this method
           builds a Keycloak end-session URL with ``id_token_hint`` and
           ``post_logout_redirect_uri`` parameters (Refine PR Directives
           D3, D5) and 303-redirects to it via
           ``werkzeug.utils.redirect`` (NOT ``request.redirect`` which
           strips external hostnames).

The controllers integrate with:
    - ``models/ir_http.py`` — for the ``_authenticate`` override that
      dispatches to V2 once the bearer token is present.
    - ``models/auth_v2.py`` — for the sidecar HTTP client.
    - ``models/feature_flags.py`` — for the AUTH_V2_ENABLED flag check.

See:
    - AAP Section 0.4.1.3 (Direct Modifications Required -- Odoo)
    - Refine PR Directives D3 (id_token_hint), D4 (Session inheritance),
      D5 (werkzeug.utils.redirect), D6 (cookie storage of PKCE state).
"""

from . import main
