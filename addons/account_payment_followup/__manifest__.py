# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "Payment Follow-ups",
    "summary": """
        Automated payment follow-up management for Odoo Community Edition.
        Provides configurable escalation levels, automated email reminders,
        immutable action history (PF-004), per-partner aging aggregation
        (PF-005), and overdue-invoice classification on account.move and
        account.move.line via _inherit extensions.
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
    # Per AAP Rule R-02 (MUST NOT - No Enterprise Dependencies), this module
    # excludes all Enterprise accounting addons:
    #   account_accountant, account_reports, account_asset,
    #   account_budget, account_followup, account_deferred_revenue
    # Per AAP Rule R-01 (Module Independence), this module does NOT
    # depend on any of the other three new modules:
    #   account_asset_management, account_budget_management,
    #   account_deferred_revenue
    "depends": [
        "account",  # Core accounting module (LGPL-3)
        "mail",     # Mail module for mail.template, mail.thread, mail.activity.mixin
    ],
    # Data load ordering rationale (from review Finding 28):
    #   1. security/followup_security.xml FIRST — ir.rule records reference
    #      the models defined in models/__init__.py; they must load before
    #      ir.model.access.csv so PostgreSQL can resolve model FK lookups.
    #   2. security/ir.model.access.csv — defines per-group ACLs on every
    #      new model (account.followup.level, account.followup.line,
    #      account.followup.history).
    #   3. data/mail_template_data.xml — creates the four default
    #      mail.template records referenced by followup_data.xml's
    #      email_template_id fields. MUST come BEFORE followup_data.xml
    #      or the ref="email_template_followup_level_N" lookups will fail
    #      with "External ID not found" at install time.
    #   4. data/followup_data.xml — seeds four default account.followup.level
    #      records (First Reminder 7d, Second Reminder 14d, Warning 21d,
    #      Final Notice 30d) per PF-001 §4.4.
    #   5. data/followup_cron.xml — registers the PF-002 ir.cron record
    #      that dispatches follow-up emails daily at 02:00 AM. Per AAP
    #      Rule R-06 (MUST - ir.cron via XML), the scheduled job is
    #      declared as an XML <record model="ir.cron"> rather than
    #      Python-level scheduling primitives.
    #
    # Checkpoint Scope Note:
    #   At the PF foundation checkpoint, views/*, report/*, and wizard/*
    #   XML files do NOT yet exist on disk. They will be appended to this
    #   data list in subsequent checkpoints when PF-003 report generation,
    #   view wiring, and menu items are implemented. Including non-existent
    #   files here would cause module install to fail with "File not found".
    "data": [
        # Security MUST load first — ir.rule records reference models
        # registered in models/__init__.py, and ir.model.access.csv
        # entries gate the followup wizard's record creation in tests
        # and runtime.
        "security/followup_security.xml",
        "security/ir.model.access.csv",
        # Default mail templates must precede follow-up-level seed data
        # because followup_data.xml references the templates by XID.
        "data/mail_template_data.xml",
        "data/followup_data.xml",
        "data/followup_cron.xml",
        # PF-003 report — the ir.actions.report record in
        # report/followup_report.xml references the wizard model's
        # auto-derived External ID (model_account_followup_report_wizard)
        # and MUST load AFTER the wizard model has been registered by
        # the module loader (which happens when wizard/__init__.py is
        # imported via the parent __init__.py — guaranteed before any
        # data XML is parsed by Odoo's module install workflow).
        "report/followup_report.xml",
        # PF-003 wizard view + window action.
        "views/followup_report_views.xml",
    ],
    # Constraints (per EPIC-001 - Enterprise Accounting Parity):
    #   - AGPL-3.0 license required (satisfied)
    #   - Zero Enterprise module dependencies (satisfied - only account, mail)
    #   - OCA coding standards compliance required
    #   - Minimum 80% test coverage per story (deferred to test checkpoint)
    #   - PF-002 Email batch: processes <=500 partners per cron run
    #     within the default cron timeout.
    #   - PF-005 Aging recomputation: <1s per 10k open invoices.
    #
    # Version Compatibility Note:
    #   - Target: Odoo 19.0 (per odoo/release.py version_info)
    #   - Python: 3.13 (highest version with explicit pins in requirements.txt)
    #   - numbercall field removed from ir.cron in Odoo 19.0 (verified via
    #     odoo/addons/base/models/ir_cron.py). Cron records in
    #     data/followup_cron.xml intentionally omit it.
}
