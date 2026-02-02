# -*- coding: utf-8 -*-
# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "Financial Reports for Community Edition",
    "summary": """
        Enterprise-grade financial reporting for Odoo Community Edition.
        Includes Balance Sheet, Profit & Loss, Cash Flow, General Ledger,
        Trial Balance, and Aged AR/AP reports.
    """,
    "version": "19.0.1.0.0",
    "category": "Accounting/Reporting",
    "website": "https://github.com/odoo/odoo",
    "author": "Enterprise Accounting Team, Odoo Community Association (OCA)",
    "license": "AGPL-3",
    "application": False,
    "installable": True,
    # IMPORTANT: Only Community Edition dependencies - NO Enterprise modules
    # This module explicitly excludes account_reports (Enterprise) and any
    # other Enterprise-only modules to maintain AGPL-3.0 compatibility
    "depends": [
        "account",      # Core accounting module (LGPL-3)
        "analytic",     # Analytic accounting for multi-dimensional reporting
    ],
    "data": [
        # Security
        "security/account_financial_report_security.xml",
        "security/ir.model.access.csv",
        # Data
        "data/report_paperformat.xml",
        # Reports
        "report/report_templates.xml",
        "report/balance_sheet_report.xml",
        "report/profit_loss_report.xml",
        "report/cash_flow_report.xml",
        "report/general_ledger_report.xml",
        "report/trial_balance_report.xml",
        "report/aged_partner_balance_report.xml",
        # Wizards
        "wizard/financial_report_wizard_views.xml",
        # Views
        "views/menuitem.xml",
    ],
    "demo": [
        "demo/demo_data.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "account_financial_report_ce/static/src/scss/report.scss",
        ],
        "web.report_assets_common": [
            "account_financial_report_ce/static/src/scss/report_print.scss",
        ],
    },
    "external_dependencies": {
        "python": [],
    },
    # Discovery Notes for Implementation:
    # - Analyze existing account.move and account.move.line models for data extraction
    # - Review account.account.type (now embedded in account.account) for classification
    # - Study existing QWeb report patterns in addons/account/report/
    # - Ensure compatibility with OCA account-financial-reporting patterns
    #
    # Constraints (per EPIC-001):
    # - AGPL-3.0 license required (satisfied)
    # - Zero Enterprise module dependencies (satisfied - only account, analytic)
    # - OCA coding standards compliance required
    # - Minimum 80% test coverage required
    #
    # Version Compatibility Note:
    # - User stories reference Odoo 18.0
    # - This repository is Odoo 19.0 (per odoo/release.py)
    # - Module written version-agnostic where possible
    # - Report engine and widget patterns may differ between versions
}
