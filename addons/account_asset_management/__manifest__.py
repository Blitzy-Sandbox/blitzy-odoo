# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "Asset Management",
    # ``summary`` is parsed by Odoo's module loader as reStructuredText
    # (rST) for display in the Apps tile. Triple-quoted multi-line
    # strings with leading whitespace are interpreted by docutils as
    # an implicit block quote, which historically emitted two
    # cosmetic warnings during install ("Unexpected indentation."
    # and "Block quote ends without a blank line; unexpected
    # unindent.") with no functional impact. To eliminate these
    # warnings, the summary is expressed using Python's implicit
    # string concatenation (parenthesized adjacent literals) which
    # produces a SINGLE logical line of rST -- no leading whitespace,
    # no embedded newlines, and therefore no block-quote semantics
    # for docutils to flag.
    "summary": (
        "Fixed-asset lifecycle management for Odoo Community Edition. "
        "Supports asset registration with vendor/invoice linkage, "
        "multiple depreciation methods (straight-line, declining "
        "balance, units of production), depreciation board "
        "visualization, scheduled automatic depreciation entry "
        "posting, asset revaluation and impairment per GAAP/IFRS "
        "(IAS 16, IAS 36, ASC 360), and asset disposal by sale, "
        "scrapping, or write-off with automatic gain/loss calculation."
    ),
    "version": "19.0.1.0.0",
    "category": "Accounting/Assets",
    "website": "https://github.com/odoo/odoo",
    "author": "Enterprise Accounting Team, Odoo Community Association (OCA)",
    "license": "AGPL-3",
    "application": False,
    "installable": True,
    "auto_install": False,
    # IMPORTANT: Only Community Edition dependencies - NO Enterprise modules.
    # This module is a complete Community Edition replacement for the
    # Enterprise ``account_asset`` addon; the Enterprise variant is NEVER
    # imported or referenced here. To maintain AGPL-3.0 compatibility, all
    # Enterprise-only accounting modules are explicitly excluded from the
    # ``depends`` list below.
    #
    # Excluded Enterprise modules (per AAP Rule R-02 - No Enterprise
    # Dependencies):
    #     account_asset            - Enterprise fixed-asset management
    #     account_accountant       - Enterprise accounting full-suite
    #     account_reports          - Enterprise financial reporting
    #     account_budget           - Enterprise budget management
    #     account_followup         - Enterprise payment follow-ups
    #     account_deferred_revenue - Enterprise deferred revenue
    #
    # Sibling Community Edition modules delivered in the same EPIC-001
    # effort are ALSO NOT listed here - each of the four new CE modules
    # is strictly independent per AAP Rule R-01 (Module Independence).
    # No cross-imports between sibling CE modules are permitted.
    #
    # Excluded sibling CE modules (per AAP Rule R-01):
    #     account_budget_management
    #     account_deferred_revenue
    #     account_payment_followup
    "depends": [
        "account",  # Core accounting module (LGPL-3) - provides account.move,
                    # account.move.line, account.account, account.journal,
                    # ir.sequence, and mail.thread (transitively via
                    # account -> portal -> mail).
    ],
    # Data-file load ordering rationale (standard Odoo convention):
    #   1. security/asset_security.xml     - res.groups and ir.rule records
    #      MUST load first so that downstream CSV access rules and XML data
    #      records can reference the groups and company-scoped rules.
    #   2. security/ir.model.access.csv    - per-model CRUD permissions for
    #      each new model (account.asset, account.asset.category,
    #      account.asset.depreciation.line, plus the TransientModel wizards).
    #   3. data/asset_sequence.xml         - ir.sequence record supplying
    #      unique asset references per AM-001 Scenario 4 (auto-generation
    #      of asset reference numbers).
    #   4. data/depreciation_cron.xml      - PER AAP RULE R-06 (MUST -
    #      ir.cron via XML), the AM-004 scheduled depreciation posting job
    #      is registered as an <record model="ir.cron"> XML entry rather
    #      than any Python-level scheduling primitive.
    #   5. views/account_asset_category_views.xml - category form/tree loaded
    #      BEFORE asset views because the asset form references the category
    #      model via a Many2one field whose action target must already exist.
    #   6. views/account_asset_views.xml          - asset header form, tree,
    #      kanban, and search views supporting AM-001 registration UX.
    #   7. views/depreciation_board_views.xml     - read-only schedule views
    #      (tree/kanban/graph) for AM-003; stored compute pattern keeps the
    #      full-schedule render under the 2s SLA for <=480 periods.
    #   8. views/asset_modification_views.xml     - AM-005 TransientModel
    #      wizard views for revaluation, impairment, and lifecycle changes.
    #   9. views/asset_disposal_views.xml         - AM-006 TransientModel
    #      wizard views for sale, scrap, and write-off disposal workflows.
    #  10. views/menuitem.xml              - menu items and root action
    #      registrations MUST load LAST because they reference every
    #      ir.actions.act_window record defined in the view files above.
    "data": [
        # Security first - groups and record rules must exist before access rules
        "security/asset_security.xml",
        "security/ir.model.access.csv",
        # Data - sequences and cron jobs (R-06: AM-004 cron as XML ir.cron record)
        "data/asset_sequence.xml",
        "data/depreciation_cron.xml",
        # Views - asset views FIRST so action_account_asset is registered
        # before category_views references it via %(action_account_asset)d.
        "views/account_asset_views.xml",
        "views/account_asset_category_views.xml",
        "views/depreciation_board_views.xml",
        # Wizards - transient models for asset modification and disposal
        "views/asset_modification_views.xml",
        "views/asset_disposal_views.xml",
        # Menus last - reference actions defined by every view above
        "views/menuitem.xml",
    ],
    "external_dependencies": {
        "python": [],  # No new Python dependencies beyond Odoo core.
                       # Per AAP section 0.3.1.2, all required libraries
                       # (lxml, Jinja2, Babel, python-dateutil) are already
                       # pinned by Odoo core and requirements.txt.
    },
    # FEATURE-004: Asset Management - Production Implementation
    #
    # User stories implemented (GAAP/IFRS-compliant per IAS 16 / IAS 36 /
    # ASC 360):
    # - AM-001: Asset Registration with vendor linkage (from account.move
    #           vendor bill), auto-generated unique references via
    #           ir.sequence, required account validation (asset_fixed,
    #           expense_depreciation, accumulated depreciation contra),
    #           and draft -> open -> close state machine with chatter.
    # - AM-002: Depreciation Configuration supporting straight-line
    #           (years or months), declining balance with optional switch
    #           to straight-line when accelerated > linear, and
    #           units-of-production methods; asset category templates
    #           provide default methods, useful life, and accounts.
    # - AM-003: Depreciation Board with complete schedule visualization
    #           (period index, date, depreciation amount, cumulative
    #           depreciation, net book value), filter/sort controls, and
    #           XLSX/CSV export; stored @api.depends computation plus an
    #           indexed asset_id FK achieve <2s render for <=480 periods.
    # - AM-004: Automatic Depreciation Entries via an ir.cron XML record
    #           (per AAP Rule R-06 - MUST - ir.cron via XML); supports
    #           batch processing, draft-vs-auto-post modes, proration for
    #           mid-period start dates, idempotent re-runs, and
    #           fault-tolerant error handling per failed asset.
    # - AM-005: Asset Modification supporting revaluation under the IAS 16
    #           revaluation model, impairment per IAS 36 / ASC 360,
    #           impairment reversal, useful-life adjustments, and salvage
    #           value changes; each modification is logged to the asset's
    #           immutable audit trail via mail.thread.
    # - AM-006: Asset Disposal by sale, scrap, or write-off with automatic
    #           gain/loss calculation against net book value, catch-up
    #           depreciation through the disposal date, partial disposal
    #           support, and state transition to close with full journal
    #           entry posting.
    #
    # Architecture:
    # - Net-new models:
    #     account.asset                        - asset header (mail.thread)
    #     account.asset.category               - category templates
    #     account.asset.depreciation.line      - schedule/execution lines
    #     account.asset.modification           - AM-005 TransientModel
    #     account.asset.disposal               - AM-006 TransientModel
    # - _inherit extensions (computed/relational only per AAP Rule R-05):
    #     account.move      -> asset_id back-reference, and related
    #                          computed/relational fields pointing only
    #                          at new models in this module.
    #     account.move.line -> asset_depreciation_line_id back-reference
    #                          to account.asset.depreciation.line.
    # - Scheduled actions:
    #     ir.cron record in data/depreciation_cron.xml invokes
    #     account.asset._cron_post_depreciation_entries daily; batched and
    #     fault-tolerant, processing 1,000 assets in <5 minutes.
    # - Multi-company isolation:
    #     ir.rule records in security/asset_security.xml scope every new
    #     model by company_id so that multi-company databases keep asset
    #     portfolios strictly isolated.
    # - Security:
    #     security/ir.model.access.csv grants per-group CRUD per AAP Rule
    #     R-07 (no unjustified sudo calls); access is modelled on
    #     account.group_account_user (read/write) and
    #     account.group_account_manager (full) from addons/account.
    #
    # Constraints (per EPIC-001 - Enterprise Accounting Parity):
    # - AGPL-3.0 license (satisfied - declared above).
    # - Zero Enterprise module dependencies (satisfied - depends lists only
    #   'account'; Enterprise addons account_asset, account_accountant,
    #   account_reports, account_budget, account_followup, and
    #   account_deferred_revenue are explicitly excluded).
    # - Zero cross-dependencies on sibling new CE modules (satisfied - per
    #   AAP Rule R-01; depends list contains only Odoo core modules).
    # - OCA coding standards compliance (ruff.toml target-version "py310"
    #   and setup.cfg flake8 configuration both honoured by this module's
    #   Python files).
    # - Per-story test coverage >=80% enforced by AAP Rule R-04 gate via
    #   pytest + coverage on tests/test_am_001.py ... tests/test_am_006.py.
    # - Additive extension of core models only via _inherit per AAP Rule
    #   R-05; no field redefinitions on account.move or account.move.line
    #   that would collide with Odoo core or with FEATURE-001 / FEATURE-002
    #   fields.
    # - Clean --stop-after-init install verified per AAP Rule R-04 gate
    #   condition (b): module installs without error and shuts down cleanly.
    #
    # Performance budgets (per AAP section 0.1.2):
    # - AM-001 asset creation:            <2s per asset; <1s for the
    #                                     confirmation journal entry;
    #                                     supports batch creation of 100+.
    # - AM-003 depreciation board render: <2s full schedule for assets
    #                                     with <=480 periods (AAP target
    #                                     and hard SLA).
    # - AM-004 cron throughput:           1,000 assets processed in
    #                                     <5 minutes via batched
    #                                     account.move.create() calls.
    # - AM-005 modification:              <3s per modification; <2s for
    #                                     schedule recalculation following
    #                                     revaluation, impairment, or
    #                                     useful-life change.
    # - AM-006 disposal:                  <3s per disposal; <5s including
    #                                     catch-up depreciation posting to
    #                                     the disposal date.
    #
    # Version Compatibility Note:
    # - Target: Odoo 19.0 (per odoo/release.py version_info).
    # - Python: 3.13 (highest version with explicit pins in
    #   requirements.txt; MIN_PY_VERSION = (3, 10) remains unchanged).
    # - Module written to be version-agnostic where practical.
}
