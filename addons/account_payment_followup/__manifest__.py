# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

# =============================================================================
# Odoo Module Manifest — account_payment_followup
# =============================================================================
#
# FEATURE-006: Payment Follow-ups (PF-001 through PF-005)
#
# Purpose
# -------
# This manifest is the authoritative declarative entry point used by Odoo's
# module loader (``odoo.modules.loading``) to:
#   1. Discover the ``account_payment_followup`` addon during a server boot.
#   2. Resolve the dependency graph against the ``account`` and ``mail`` core
#      modules before any Python code is imported.
#   3. Load all data XML / CSV files in the ``data`` list IN ORDER at module
#      install / upgrade time. The order in the ``data`` list is a hard
#      contract because foreign-key references between records (mail
#      templates → follow-up levels, view actions → menu items, etc.) must
#      resolve in topological order.
#   4. Validate that the external Python package ``openpyxl`` is importable
#      before the wizard's XLSX export action can be invoked at runtime.
#
# Story Coverage
# --------------
#   PF-001 — Follow-up Level Configuration
#   PF-002 — Automated Email Generation (mandatory ir.cron via XML — Rule R-06)
#   PF-003 — Follow-up Report Generation (PDF + XLSX export)
#   PF-004 — Action History Tracking (immutable audit trail)
#   PF-005 — Overdue Calculation (per-partner aging buckets)
#
# Rule Compliance (per AAP §0.7)
# ------------------------------
#   R-01 — Module Independence: ``depends`` lists only ``account`` and
#          ``mail``; no sibling new modules (``account_asset_management``,
#          ``account_budget_management``, ``account_deferred_revenue``).
#   R-02 — No Enterprise Dependencies: ``depends`` excludes every Enterprise
#          accounting addon (``account_followup``, ``account_accountant``,
#          ``account_reports``, ``account_asset``, ``account_budget``,
#          ``account_deferred_revenue``).
#   R-06 — ``ir.cron`` via XML: PF-002 scheduled job is declared in
#          ``data/followup_cron.xml`` (verifiable at Settings → Technical
#          → Automation → Scheduled Actions after install).
#   R-09 — Exact Folder Name: module folder is ``account_payment_followup``.
#
# Version Notes
# -------------
#   - Target: Odoo 19.0 Community Edition (per ``odoo/release.py``
#     ``version_info = (19, 0, 0, FINAL, 0, '')``).
#   - Manifest version pattern ``19.0.1.0.0`` follows the OCA convention
#     ``<odoo_series>.<feature_major>.<feature_minor>.<patch>``.
#   - Python: 3.10 minimum (per ``odoo/release.py`` ``MIN_PY_VERSION``);
#     3.13 is the highest version with explicit pins in ``requirements.txt``.
# =============================================================================
{
    # -------------------------------------------------------------------------
    # Identity
    # -------------------------------------------------------------------------
    "name": "Payment Follow-ups",
    "summary": (
        "Automated payment follow-up management for Odoo Community Edition. "
        "Provides configurable escalation levels (PF-001), automated email "
        "reminders via ir.cron (PF-002), aged-receivables reporting with "
        "PDF/XLSX export (PF-003), immutable action history (PF-004), and "
        "per-partner overdue classification with aging buckets (PF-005)."
    ),
    "version": "19.0.1.0.0",
    "category": "Accounting/Accounting",
    "website": "https://github.com/odoo/odoo",
    "author": "Enterprise Accounting Team, Odoo Community Association (OCA)",
    "license": "AGPL-3",
    # -------------------------------------------------------------------------
    # Lifecycle Flags
    # -------------------------------------------------------------------------
    # ``application=False`` — this is an accounting feature module, not a
    # standalone application; it integrates into the existing Accounting app.
    # ``installable=True`` — module is fully implemented and ready to install.
    # ``auto_install=False`` — module installs only on explicit user request;
    # never auto-installs because of the dependency on ``mail``.
    "application": False,
    "installable": True,
    "auto_install": False,
    # -------------------------------------------------------------------------
    # Module Dependencies (R-01, R-02 enforcement)
    # -------------------------------------------------------------------------
    # IMPORTANT: Only Community Edition dependencies — NO Enterprise modules.
    # Per AAP Rule R-02 (MUST NOT - No Enterprise Dependencies), this module
    # excludes ALL Enterprise accounting addons:
    #   - account_accountant
    #   - account_reports
    #   - account_asset
    #   - account_budget
    #   - account_followup           (Enterprise's follow-up module)
    #   - account_deferred_revenue   (Enterprise's deferred-revenue module)
    #
    # Per AAP Rule R-01 (Module Independence), this module does NOT depend
    # on any of the other three new modules:
    #   - account_asset_management
    #   - account_budget_management
    #   - account_deferred_revenue
    #
    # Verification commands (zero hits expected):
    #   grep -E '(account_accountant|account_reports|account_asset|
    #            account_budget|account_followup|account_deferred_revenue)'
    #            addons/account_payment_followup/__manifest__.py
    #   grep -E '(account_asset_management|account_budget_management|
    #            account_deferred_revenue)'
    #            addons/account_payment_followup/__manifest__.py
    "depends": [
        "account",  # Core accounting (LGPL-3) — provides account.move,
                    # account.move.line, res.partner chain, account.account,
                    # account.group_account_user / group_account_manager /
                    # group_account_readonly, and account.menu_finance_entries.
        "mail",     # Mail (LGPL-3) — provides mail.template (referenced by
                    # account.followup.level.email_template_id), mail.thread
                    # mixin (composed into account.followup.history for
                    # chatter / activity support), and mail.mail (queued via
                    # the PF-002 cron-driven email batch).
    ],
    # -------------------------------------------------------------------------
    # Data Files — Strict Load Order Contract
    # -------------------------------------------------------------------------
    # The order below is a HARD CONTRACT enforced by Odoo's loader. Each file
    # may reference XIDs (External Identifiers) created by files preceding it
    # in this list. Reordering will cause "External ID not found" errors at
    # install time.
    #
    # Topology rationale (top-down):
    #
    # 1. SECURITY (must precede everything because models can't be accessed
    #    without ACL entries and record rules):
    #
    #    - security/followup_security.xml — Defines multi-company ir.rule
    #      records for account.followup.level, account.followup.line,
    #      account.followup.history. Loaded FIRST so the rules are in place
    #      when ir.model.access.csv assigns groups to those models.
    #
    #    - security/ir.model.access.csv — Per-(model, group) ACL rows for the
    #      three new persistent models plus the PF-003 wizard TransientModel.
    #      References core groups account.group_account_user and
    #      account.group_account_manager, which exist after the ``account``
    #      dependency installs.
    #
    # 2. SEED DATA (mail templates BEFORE follow-up levels because levels
    #    reference templates by external ID):
    #
    #    - data/mail_template_data.xml — Seeds 4 mail.template records:
    #      email_template_followup_level_1 (First Reminder),
    #      email_template_followup_level_2 (Second Reminder),
    #      email_template_followup_level_3 (Warning),
    #      email_template_followup_level_4 (Final Notice).
    #      MUST precede followup_data.xml because the level records reference
    #      these templates via the ``email_template_id`` Many2one FK.
    #
    #    - data/followup_data.xml — Seeds 4 default account.followup.level
    #      records per PF-001 §4.4 (First Reminder @ 7 days,
    #      Second Reminder @ 14 days, Warning @ 21 days, Final Notice @ 30
    #      days). Each row references email_template_followup_level_N from
    #      the prior file — load order is therefore mandatory.
    #
    #    - data/followup_cron.xml — PF-002 ir.cron record
    #      (ir_cron_payment_followup) executing
    #      ``model._cron_send_followup_emails()`` daily at 02:00 AM.
    #      MANDATORY per AAP Rule R-06 (no Python-level cron scheduling).
    #      Loaded after the seed data so the cron's reference to the
    #      payment-followup model is resolvable.
    #
    # 3. REPORT ACTIONS (before view files that reference report XIDs):
    #
    #    - report/followup_report.xml — PF-003 ir.actions.report record
    #      (action_report_followup_aged_receivables) bound to
    #      account.followup.report.wizard with QWeb PDF template
    #      report_followup_aged_receivables. Loaded BEFORE the wizard view
    #      file because views reference this action's XID via
    #      <button type="action" name="..."/> patterns.
    #
    # 4. VIEWS (order: base configuration models → operational models →
    #    inheriting models → wizard → menus):
    #
    #    - views/account_followup_level_views.xml — PF-001 list/form/search
    #      views and action_account_followup_level. Loaded first among views
    #      because subsequent files (menu items) reference its action XID.
    #
    #    - views/account_followup_line_views.xml — PF-005 list/form/graph/
    #      pivot views (read-only) and action_account_followup_line. Backs
    #      per-partner aging summaries.
    #
    #    - views/account_followup_history_views.xml — PF-004 list/form/
    #      kanban views with chatter widget; action_account_followup_history
    #      is referenced both by menuitem.xml AND by the smart button on
    #      res_partner_views.xml — so this file MUST precede res_partner.
    #
    #    - views/res_partner_views.xml — Inherits base.view_partner_form etc.
    #      to add the Follow-ups notebook tab, aging-bucket fields, and a
    #      smart button linking to follow-up history. MUST load AFTER
    #      account_followup_history_views.xml because the smart button
    #      references action_account_followup_history.
    #
    #    - views/followup_report_views.xml — PF-003 wizard form view +
    #      window action (action_followup_report_wizard) with target=new
    #      for modal display. Inlines wizard views (no separate
    #      wizard/*_views.xml file is created). The window action is
    #      referenced by menuitem.xml, so this file precedes the menu file.
    #
    # 5. MENUS (LAST — every action XID referenced by menuitems must already
    #    be registered):
    #
    #    - views/menuitem.xml — Root menu under account.menu_finance_entries
    #      (sequence 30) with Operations and Configuration sections wiring
    #      4 menuitems to the actions registered above. Uses
    #      account.group_account_readonly (operations) and
    #      account.group_account_manager (configuration) — both populated
    #      on Odoo CE 19.0 install.
    "data": [
        # --- 1. Security (record rules + ACL) ---
        "security/followup_security.xml",
        "security/ir.model.access.csv",
        # --- 2. Seed data (templates → levels → cron) ---
        "data/mail_template_data.xml",
        "data/followup_data.xml",
        "data/followup_cron.xml",
        # --- 3. Report actions (before view files reference them) ---
        "report/followup_report.xml",
        # --- 4. Views (in dependency order) ---
        "views/account_followup_level_views.xml",
        "views/account_followup_line_views.xml",
        "views/account_followup_history_views.xml",
        "views/res_partner_views.xml",
        "views/followup_report_views.xml",
        # --- 5. Menus (LAST — reference action XIDs from prior view files) ---
        "views/menuitem.xml",
    ],
    # -------------------------------------------------------------------------
    # External Python Dependencies
    # -------------------------------------------------------------------------
    # Declared in the manifest's ``external_dependencies.python`` block to
    # signal Odoo's module loader that ``openpyxl`` is required at install
    # time. Odoo verifies importability and raises a clear error if the
    # package is missing — preventing runtime failures inside the wizard's
    # ``action_export_xlsx()`` method (PF-003).
    #
    # ``openpyxl`` is already pinned at 3.1.2 in repo-root ``requirements.txt``
    # and consumed by FEATURE-001's account_financial_report_ce module, so
    # the dependency is established across the codebase. This declaration
    # mirrors the precedent set by:
    #     addons/account_financial_report_ce/__manifest__.py
    "external_dependencies": {
        "python": [
            "openpyxl",  # XLSX export for PF-003 follow-up report wizard
                         # (wizard/followup_report_wizard.py::action_export_xlsx)
        ],
    },
    # -------------------------------------------------------------------------
    # Constraints (per EPIC-001 — Enterprise Accounting Parity)
    # -------------------------------------------------------------------------
    #   - AGPL-3.0 license required (satisfied — see ``license`` above).
    #   - Zero Enterprise module dependencies (satisfied — only account, mail).
    #   - OCA coding standards compliance (enforced by ruff + manual review).
    #   - Minimum 80% test coverage per story (enforced at story gate, R-04).
    #
    # Performance Targets (per AAP §0.7.3 and PF ticket files)
    # --------------------------------------------------------
    #   - PF-002 Email batch: processes <=500 partners per cron run within
    #     the default cron timeout. Implemented via batched mail.mail.create()
    #     and the existing Odoo mail queue (no synchronous send in cron body).
    #   - PF-003 PDF report: <10s end-to-end for 500 partners.
    #   - PF-003 XLSX export: <30s for 1,000 rows.
    #   - PF-005 Aging recomputation: <1s per 10k open invoices.
    #
    # Audit Hooks
    # -----------
    #   - No ``pre_init_hook``, ``post_init_hook``, or ``uninstall_hook``
    #     defined for this module. The simpler installation profile (no
    #     hooks) follows the AAP guidance which lists hooks only for
    #     account_bank_reconciliation_ce (cross-group user migration);
    #     account_payment_followup does not require any such migration.
    #   - No HTTP controllers (per AAP §0.2.1.2 — ``controllers/`` directory
    #     is intentionally absent).
    #   - No demo data file declared (the AAP does not require demo data;
    #     omitting the ``demo`` key is equivalent to ``"demo": []``).
    #   - No ``assets`` block (no net-new JavaScript or OWL components per
    #     AAP §0.5.3; SCSS is also absent because no custom styling is
    #     required for the standard Odoo views used by this module).
}
