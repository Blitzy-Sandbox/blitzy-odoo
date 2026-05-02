# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    'name': 'Budget Management',
    'summary': (
        'Budget definition, period allocation, actual-vs-budget reporting, '
        'variance analysis, and threshold alerts — Community Edition'
    ),
    'description': """
Budget Management for Odoo Community Edition
============================================

Enterprise-grade budget management capabilities for Odoo 19.0 Community
Edition, delivering the Community/Enterprise gap-closure for budgeting
without any Odoo Enterprise dependency.

This module (FEATURE-003) delivers five user stories:

* **BM-001** Budget Definition — define budgets linked to general ledger
  accounts and analytic dimensions (analytic accounts and analytic plans);
  supports draft → confirmed → closed lifecycle with audit trail.
* **BM-002** Budget Period Allocation — distribute budget amounts across
  monthly, quarterly, or annual periods using equal, manual, percentage,
  or copy-previous distribution strategies.
* **BM-003** Actual vs Budget Reporting — side-by-side comparison of
  planned amounts against posted journal entries, with drill-down,
  multi-period YTD aggregation, and variance indicators.
* **BM-004** Variance Analysis — absolute and percentage variance
  calculations with favorable/unfavorable classification, account-type
  visual cues, and drill-down to source journal entries. Fiscal-year
  variance report renders in under three seconds for up to one thousand
  budget lines via ``read_group`` SQL aggregation.
* **BM-005** Budget Alerts — threshold-based alerts (for example at
  75%, 90%, 100%, and 110% consumption) with severity classification,
  configurable recipients, immutable audit history, and dashboard
  visualization. Alert evaluation is driven by an ``ir.cron`` scheduled
  action defined in ``data/budget_alert_cron.xml``.

All implementations respect the AGPL-3.0 licensing constraint and declare
only Odoo Community Edition dependencies — specifically ``account`` and
``analytic`` — with no imports from Odoo Enterprise modules.
""",
    'version': '19.0.1.0.0',
    'category': 'Accounting/Accounting',
    'website': 'https://github.com/odoo/odoo',
    'author': 'Enterprise Accounting Team, Odoo Community Association (OCA)',
    'license': 'AGPL-3',
    'application': False,
    'installable': True,
    'auto_install': False,
    # IMPORTANT: Only Community Edition dependencies — NO Enterprise modules.
    # This module declares exactly two Odoo Community dependencies and no
    # Enterprise modules, preserving AGPL-3.0 compatibility.
    #
    # ``account`` — core accounting module (LGPL-3) required for account.account,
    #   account.move, and account.move.line.
    # ``analytic`` — analytic accounting module required for
    #   account.analytic.account, account.analytic.plan, and analytic.mixin
    #   (the latter is composed into budget.budget.line for multi-dimensional
    #   budget distribution per BM-001 Scenario 3).
    'depends': [
        'account',
        'analytic',
    ],
    'data': [
        # Security first — ACL records and record rules must exist before any
        # data record or view references the models they govern.
        'security/budget_security.xml',
        'security/ir.model.access.csv',
        # Data — sequences, default configuration records, and scheduled
        # actions. Loaded after security so ir.cron records reference
        # models that already have ir.model.access.csv rows.
        'data/budget_data.xml',
        'data/budget_alert_cron.xml',
        # Views — loaded in dependency order. Every view file references
        # actions and/or search views that must already be registered when
        # the menu hierarchy (``views/menuitem.xml``, loaded LAST) binds
        # menu entries to actions.
        #
        # Load order rationale:
        #   1. ``budget_views.xml``          — BM-001 core budget model views
        #                                      (form/list/kanban/search plus
        #                                      the primary ``action_budget_budget``
        #                                      window).
        #   2. ``budget_period_views.xml``   — BM-002 cross-budget period
        #                                      browsing views + action.
        #   3. ``budget_variance_views.xml`` — BM-003 / BM-004 variance
        #                                      pivot/graph/list views +
        #                                      ``action_budget_vs_actual_report``
        #                                      and ``action_budget_variance_analysis``.
        #   4. ``budget_variance_wizard_views.xml`` — BM-004 wizard form +
        #                                      ``action_budget_variance_wizard``.
        #   5. ``budget_alert_views.xml``    — BM-005 alert views + action.
        #   6. ``menuitem.xml``              — MUST be LAST; every menu entry
        #                                      references an action defined
        #                                      above.
        'views/budget_views.xml',
        'views/budget_period_views.xml',
        'views/budget_variance_views.xml',
        'views/budget_variance_wizard_views.xml',
        'views/budget_alert_views.xml',
        'views/menuitem.xml',
    ],
    # -------------------------------------------------------------------------
    # Backend Assets (SCSS only, no JavaScript per AAP §0.5.3)
    # -------------------------------------------------------------------------
    # Loaded into ``web.assets_backend`` so every backend page rendered after
    # this module installs picks up the QA Issue #3 (Checkpoint 5) focus-
    # visibility fix for primary buttons. The SCSS file is intentionally
    # minimal — only the ``.btn-primary:focus-visible`` rule needed to
    # satisfy WCAG 2.1 AA Success Criterion 2.4.7 "Focus Visible". Mirrors
    # the SCSS-only frontend-contribution precedent of FEATURE-001's
    # ``addons/account_financial_report_ce/`` and FEATURE-002's
    # ``addons/account_bank_reconciliation_ce/`` modules.
    'assets': {
        'web.assets_backend': [
            'account_budget_management/static/src/scss/budget_management.scss',
        ],
    },
    # Constraints (per EPIC-001 — Enterprise Accounting Parity, FEATURE-003):
    # - AGPL-3.0 license required (satisfied)
    # - Zero Enterprise module dependencies (satisfied — only account, analytic)
    # - Zero cross-dependencies on sibling new modules (R-01, satisfied — the
    #   depends list above contains only core Odoo Community modules)
    # - OCA coding standards compliance (ruff.toml target-version py310)
    # - Minimum 80% per-story test coverage (R-04)
    # - Additive extension of core models only via _inherit (R-05)
    # - BM-004 variance report fiscal-year render <3s for ≤1,000 budget lines
    # - BM-005 alert scheduled via ir.cron XML record (data/budget_alert_cron.xml)
}
