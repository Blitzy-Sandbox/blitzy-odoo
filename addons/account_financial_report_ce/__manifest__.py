# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "Financial Reports for Community Edition",
    "summary": """
        Enterprise-grade financial reporting for Odoo Community Edition.
        Includes Balance Sheet, Profit & Loss, Cash Flow, General Ledger,
        Trial Balance, and Aged AR/AP reports.
    """,
    "version": "19.0.1.1.0",
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
        # Reports (report actions must be defined before paperformat references them)
        "report/report_templates.xml",
        "report/balance_sheet_report.xml",
        "report/profit_loss_report.xml",
        "report/cash_flow_report.xml",
        "report/general_ledger_report.xml",
        "report/trial_balance_report.xml",
        "report/aged_partner_balance_report.xml",
        # Data (paper formats reference report actions above)
        "data/report_paperformat.xml",
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
        "python": [
            "openpyxl",  # Excel (.xlsx) export for financial reports (FR-007)
        ],
    },
    # FEATURE-001: Financial Reporting Engine — Production Implementation
    #
    # Reports implemented (GAAP/IFRS-compliant):
    # - Balance Sheet (FR-001): Assets = Liabilities + Equity validation
    # - Profit & Loss (FR-002): Revenue/COGS/OpEx/Net Income breakdown
    # - Cash Flow Statement (FR-003): Indirect method with activity sections
    # - General Ledger (FR-004): Per-account transaction listing with running balances
    # - Trial Balance (FR-005): Debit/Credit equality verification
    # - Aged AR/AP (FR-006): 30/60/90/120+ day aging buckets
    # - Export support (FR-007): PDF via QWeb and Excel via openpyxl
    #
    # Architecture:
    # - Data sourced from account.move.line via read_group aggregation
    # - Account classification via account.account account_type field (21 types)
    # - Drill-down navigation to source journal entries
    # - Comparative period analysis support
    # - Multi-company isolation via record rules
    #
    # Constraints (per EPIC-001):
    # - AGPL-3.0 license (satisfied)
    # - Zero Enterprise module dependencies (satisfied — only account, analytic)
    # - OCA coding standards compliance (satisfied)
    # - Python 3.10–3.13 compatibility (satisfied)
    # - Odoo 19.0 API (version-agnostic where possible)
}
