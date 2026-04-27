# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Auth V2 (Keycloak/OAuth)',
    'version': '19.0.1.0.0',
    'category': 'Authentication',
    'summary': 'OAuth 2.0 / OIDC authentication for Odoo via Keycloak sidecar',
    'description': """
Auth V2 (Keycloak / OAuth 2.0 / OIDC)
=====================================

Implements OAuth 2.0 / OIDC authentication for Odoo by overriding
``ir.http._authenticate()`` and delegating token validation to the
``@blitzy/auth`` HTTP sidecar (default port 4001).

Behavior is controlled by the ``AUTH_V2_ENABLED`` feature flag, evaluated
on every request via the ``@blitzy/admin-ui`` evaluation API (default
port 4003), with cache → API → ``os.environ`` fallback (fail-open).

When the flag is *disabled*, this addon performs **zero** OAuth /
Keycloak / sidecar work — the legacy Odoo authentication path runs
verbatim. When the flag is *enabled*, the bearer token from the
``Authorization`` header is validated by the sidecar's ``POST /validate``
endpoint, and the ``res.users`` row is looked up by email (auto-provisioned
on first login with ``share=False``).

Any sidecar failure with the flag enabled raises
``werkzeug.exceptions.ServiceUnavailable`` (HTTP 503) — the addon does
**not** fall back to the legacy authentication path under failure (fail-closed).

Companion components (out of this addon's scope):

* ``packages/auth/`` — TypeScript ``@blitzy/auth`` library and HTTP sidecar
* ``packages/admin-ui/`` — TypeScript ``@blitzy/admin-ui`` flag platform
* Keycloak 24 realm ``blitzy`` (defined in ``packages/auth/keycloak/realm-export.json``)

This addon is **not** auto-installed; deployments without the V2
environment continue to function unchanged.
""",
    'author': 'Blitzy',
    'website': 'https://github.com/blitzy/blitzy-oauth-v1',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'web',
        'auth_signup',
    ],
    'data': [],
    'auto_install': False,
    'installable': True,
    'application': False,
}
