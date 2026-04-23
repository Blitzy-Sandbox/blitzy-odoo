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
    # post_init_hook ensures every accounting-manager/accounting-user and
    # bank-reconciliation group member also belongs to base.group_user so
    # that ir.attachment uploads (bank statement files) never raise
    # AccessError.  See addons/account_bank_reconciliation_ce/__init__.py.
    "post_init_hook": "post_init_hook",
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
    # ----------------------------------------------------------------------
    # External Python dependencies
    # ----------------------------------------------------------------------
    #
    # CP10 Issue #1 CRITICAL — Supply-chain residual risk (ofxparse):
    #
    # The ``ofxparse`` package (PyPI https://pypi.org/project/ofxparse/) is
    # declared below because this module supports OFX bank-statement imports
    # (see ``models/bank_statement_import.py`` — conditional import guarded
    # by ``try/except ImportError``).  The CP10 FINAL SECURITY checkpoint
    # flagged the following supply-chain concerns that operators MUST weigh
    # before enabling OFX workflows in production:
    #
    #   * Upstream abandonment — the current PyPI release ``0.21`` was
    #     published on 2021-05-31 and there has been no maintainer activity
    #     since.  Any security defect discovered in the SGML/OFX parser has
    #     NO published upstream fix path.
    #   * No security-review process — the package ships without a security
    #     disclosure policy or a signed release channel.
    #   * Installed-but-optional — ``ofxparse`` is a soft dependency; the
    #     OFX parser guards on ``ofxparse is not None`` and raises a
    #     ``UserError`` when absent.  Operators MAY omit the package from
    #     their deployment requirements to eliminate the attack surface if
    #     OFX imports are not needed.
    #
    # Existing risk-mitigation controls already in place:
    #
    #   * Wizard-level file-size cap (``_MAX_FILE_SIZE = 10 MiB``) enforced
    #     BEFORE parsing — see
    #     ``wizard/bank_statement_import_wizard.py`` constraint.
    #   * ACL gating — OFX import is reachable only via the
    #     ``group_bank_reconciliation_user`` group; no public/portal route.
    #   * Generic UserError messages on parse failure (exception text is
    #     redirected to the server log via ``_logger.exception``), so parser
    #     internals are not exposed to end users.
    #
    # Long-term remediation (tracked in CODE_REVIEW.md §4 Phase 2 Security
    # CP10 addendum) — operators choose exactly ONE of:
    #
    #   (a) Vendor ``ofxparse`` into a maintained internal fork with a
    #       documented security-review process, OR
    #   (b) Replace with a custom SGML/OFX parser that lives inside this
    #       addon (removing the external dependency entirely), OR
    #   (c) Disable the OFX import feature by omitting ``ofxparse`` from
    #       the deployment's ``requirements.txt`` — users then see a
    #       UserError if they attempt an OFX upload.
    #
    # Reference: ``requirements.txt`` has a matching CP10 Issue #1 comment
    # block above the ``ofxparse==0.21`` pin.
    # ----------------------------------------------------------------------
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
