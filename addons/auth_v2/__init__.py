# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""auth_v2 addon — Keycloak/OAuth integration for Odoo (Blitzy V2 stack).

This is the addon-level package initializer required by Odoo's module loader.
Without this file, ``odoo-bin --init=auth_v2`` would fail with an ImportError
before any model could be registered.

The addon is gated by the ``AUTH_V2_ENABLED`` feature flag (per AAP Rules R3
and R4). Under ``AUTH_V2_ENABLED=false`` (the default per AAP and per
``__manifest__.py`` ``auto_install: False``), zero V2 code executes:
- ``ir.http._authenticate`` is overridden but the override returns to
  ``super()._authenticate(endpoint)`` immediately on flag=false.
- The sidecar HTTP client (``models/auth_v2.py``) is never invoked.

See:
    - AAP Section 0.5.1.5 (Group 5 — Odoo Addon)
    - AAP Section 0.4.1.3 (Direct Modifications Required — Odoo)
    - AAP Section 0.7.1 R3, R4, R10, R13 (V2 isolation, fail-closed mode)
"""

from . import models
