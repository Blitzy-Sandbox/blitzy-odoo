# -*- coding: utf-8 -*-
# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "Bank Reconciliation for Community Edition",
    "summary": """
        Smart bank reconciliation for Odoo Community Edition.
        Supports multi-format bank statement import (CSV, OFX, QIF, CAMT.053),
        algorithmic matching engine with configurable confidence scoring,
        reconciliation rules with regex and amount matching, manual
        reconciliation workflows, and partial reconciliation with write-off
        handling.
    """,
    "version": "19.0.1.0.0",
    "category": "Accounting/Reconciliation",
    "website": "https://github.com/odoo/odoo",
    "author": "Enterprise Accounting Team, Odoo Community Association (OCA)",
    "license": "AGPL-3",
    "application": False,
    "installable": True,
    "auto_install": False,
    # IMPORTANT: Only Community Edition dependencies - NO Enterprise modules
    # This module explicitly excludes account_accountant (Enterprise) and any
    # other Enterprise-only modules to maintain AGPL-3.0 compatibility.
    # Excluded Enterprise modules: account_reports, account_accountant,
    # account_asset, account_budget, account_followup, account_deferred_revenue
    "depends": [
        "account",      # Core accounting module (LGPL-3)
    ],
    "data": [
        # Security
        "security/bank_reconciliation_security.xml",
        "security/ir.model.access.csv",
        # Data
        "data/reconciliation_data.xml",
        # Reports
        "report/reconciliation_report.xml",
        # Wizards
        "wizard/bank_statement_import_wizard_views.xml",
        "wizard/reconciliation_wizard_views.xml",
        # Views
        "views/bank_reconciliation_views.xml",
        "views/menuitem.xml",
    ],
    "demo": [
        "demo/demo_data.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "account_bank_reconciliation_ce/static/src/scss/reconciliation.scss",
        ],
    },
    "external_dependencies": {
        "python": ["ofxparse"],
    },
    # Constraints (per EPIC-001 - Enterprise Accounting Parity):
    # - AGPL-3.0 license required (satisfied)
    # - Zero Enterprise module dependencies (satisfied - only account)
    # - OCA coding standards compliance required
    # - Minimum 80% test coverage required
    # - Bank reconciliation: statement import <10s for 500 lines
    # - Algorithmic matching <5s for 1,000 lines
    # - Rule evaluation <1s per rule
    # - >=95% matching accuracy target
    #
    # Version Compatibility Note:
    # - User stories reference Odoo 18.0
    # - This repository is Odoo 19.0 (per odoo/release.py)
    # - Module written version-agnostic where possible
    # - Python 3.10-3.13 compatibility required (per MIN_PY_VERSION)
}
