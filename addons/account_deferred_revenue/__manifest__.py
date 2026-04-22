# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "Deferred Revenue",
    "summary": """
        ASC 606 / IFRS 15 compliant deferred revenue and deferred expense
        recognition for Odoo Community Edition. Features invoice-driven
        deferral schedule creation, straight-line/date-based/manual allocation
        methods, cut-off entry generation with lock-date enforcement, and a
        recognition dashboard with period-based drill-down.
    """,
    "version": "19.0.1.0.0",
    "category": "Accounting/Accounting",
    "website": "https://github.com/odoo/odoo",
    "author": "Enterprise Accounting Team, Odoo Community Association (OCA)",
    "license": "AGPL-3",
    "application": False,
    "installable": True,
    "auto_install": False,
    # IMPORTANT: Only Community Edition dependencies - NO Enterprise modules.
    # This module is a complete Community Edition replacement for the Enterprise
    # equivalent; the Enterprise variant is NEVER imported or referenced here.
    # To maintain AGPL-3.0 compatibility, all Enterprise-only accounting
    # modules (account_accountant, account_reports, account_asset,
    # account_budget, account_followup) are explicitly excluded from `depends`.
    #
    # Sibling Community Edition modules delivered in the same EPIC-001 effort
    # are ALSO NOT listed here — each of the four new CE modules is strictly
    # independent per R-01 (module independence). No cross-imports between
    # sibling CE modules are permitted.
    "depends": [
        "account",      # Core accounting module (LGPL-3) — provides account.move,
                        # account.move.line, account.account, account.lock_exception,
                        # and mail.thread (transitively via account → portal → mail).
    ],
    "data": [
        # Security (must load first — groups are referenced by ir.model.access.csv)
        "security/deferred_security.xml",
        "security/ir.model.access.csv",
        # Data records (sequences, default configurations) — must exist before
        # views that may reference default values at render time.
        "data/deferred_data.xml",
        # Views — base-model views before wizard views before menus.
        "views/account_deferred_schedule_views.xml",
        "views/account_deferred_line_views.xml",
        "views/cutoff_wizard_views.xml",
        "views/recognition_dashboard_views.xml",
        # Menus LAST — they reference ir.actions.act_window records declared
        # in the view XML files above.
        "views/menuitem.xml",
    ],
    # FEATURE-005: Deferred Revenue / Expenses — Production Implementation
    #
    # Stories implemented (ASC 606 / IFRS 15-compliant):
    # - DR-001: Deferral Schedule Definition (invoice-driven + manual creation)
    # - DR-002: Automatic Period Allocation (straight-line, date-based, manual)
    # - DR-003: Cut-off Entry Generation (single/batch/preview/reversal modes)
    # - DR-004: Recognition Dashboard (period-based drill-down and filters)
    #
    # Architecture:
    # - Net-new models: account.deferred.schedule (header), account.deferred.line (recognition lines)
    # - Additive _inherit on account.move and account.move.line (computed/relational only per R-05)
    # - TransientModel wizards for cut-off generation and recognition dashboard
    # - Multi-company isolation via ir.rule in security/deferred_security.xml
    # - account.lock_exception awareness for lock-date enforcement (DR-003)
    # - Analytic distribution preservation from source invoice lines (DR-001 Scenario 6)
    #
    # Constraints (per EPIC-001 / AAP §0.7):
    # - AGPL-3.0 license (satisfied)
    # - Zero Enterprise module dependencies (satisfied — only `account`)
    # - No cross-dependencies with sibling CE modules (satisfied — R-01)
    # - _inherit-only extension of core models, no _name collisions (R-03)
    # - No redefinition of core fields on account.move/account.move.line (R-05)
    # - No sudo() without inline justification (R-07)
    # - OCA coding standards compliance
    # - Minimum 80% per-story test coverage (R-04)
    # - Python 3.10-3.13 compatibility (per MIN_PY_VERSION)
}
