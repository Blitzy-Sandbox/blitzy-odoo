# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models
from odoo.http import request


class IrHttp(models.AbstractModel):
    """Override ir.http to enable dark mode detection from the color_scheme cookie.

    Odoo Community Edition's ``ir.http.color_scheme()`` unconditionally
    returns ``"light"`` (see ``addons/web/models/ir_http.py``).  This means
    that the server-side QWeb template variable ``color_scheme`` is always
    ``"light"``; as a consequence the ``web.assets_web_dark`` CSS bundle is
    never loaded and the Carbon G90 dark-theme body class is never set.

    This override reads the ``color_scheme`` cookie that the Carbon Theme
    Toggle component (``carbon_theme_toggle.js``) writes when the user
    switches between light and dark modes.  When the cookie value is
    ``"dark"``, the method returns ``"dark"`` so that:

    1. The server renders ``<body class="o_web_client cds--theme--g90">``
       instead of ``cds--theme--white``.
    2. The ``<t t-if="color_scheme == 'dark'">`` conditional in
       ``web.webclient_bootstrap`` causes the ``web.assets_web_dark`` CSS
       bundle (which contains ``carbon_dark_theme.scss`` and
       ``carbon_dark_components.scss``) to be served.

    This follows the standard Odoo pattern used by the Enterprise web
    module (``web_enterprise``) to enable server-side dark mode support.

    Module Isolation Rule:
        This file resides entirely within ``addons/carbon_ui/``.
        No files under ``addons/web/`` or ``odoo/`` are modified.
        The override is registered through Odoo's standard ``_inherit``
        mechanism and is automatically removed when the module is
        uninstalled — restoring the original ``"light"``-only behavior.
    """

    _inherit = "ir.http"

    def color_scheme(self):
        """Return the user's preferred color scheme from the cookie.

        Returns:
            str: ``"dark"`` when the ``color_scheme`` cookie is ``"dark"``,
                 ``"light"`` in all other cases (missing cookie, unknown
                 value, or no active HTTP request).
        """
        # Guard: During cron jobs, tests, or CLI operations there may be
        # no active HTTP request.  Fall back to the parent implementation
        # (which returns "light") in those situations.
        if request and request.httprequest:
            cookie_value = request.httprequest.cookies.get("color_scheme")
            if cookie_value == "dark":
                return "dark"
        return super().color_scheme()
