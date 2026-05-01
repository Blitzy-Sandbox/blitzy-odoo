# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Follow-up Report Wizard — PF-003 Filter and Export Interface.

Provides a TransientModel-based wizard that collects filter criteria from the
user, delegates aged-receivables aggregation to the AbstractModel parser
(``report.account_payment_followup.followup_aged_receivables``), and dispatches
results as either a QWeb PDF (via the standard ``ir.actions.report`` pipeline)
or a programmatically-generated XLSX workbook (via openpyxl).

Implements:
    - FEATURE-006 PF-003: Follow-up Report Generation (complete story)

Integration Contract
--------------------
* Model ``_name`` is ``account.followup.report.wizard`` — generates the
  auto-derived External ID ``model_account_followup_report_wizard`` that
  is referenced by the report XML record's ``binding_model_id`` attribute
  and that backs the XML's ``print_report_name`` expression
  ``object.report_date or fields.Date.context_today(object)``.
* Exposes form values consumed by
  ``report.account_payment_followup.followup_aged_receivables`` via direct
  attributes AND ``_get_form_values()``. The parser merges this method's
  return dict on top of any flat ``data`` values, treating the wizard
  record as the authoritative filter source of truth.
* ``action_generate_report()`` invokes the report action whose XML ID is
  ``account_payment_followup.action_report_followup_aged_receivables``.
* ``action_export_xlsx()`` produces a base64-encoded XLSX via openpyxl
  and returns an ``ir.actions.act_url`` for browser download — Odoo 19.0
  does NOT support ``report_type='qweb-xlsx'``, so wizard-programmatic
  generation is mandatory.

Performance Targets (PF-003 §6)
-------------------------------
* 500 partners → <10s end-to-end PDF report generation
* 1000 partners → <20s end-to-end PDF report generation
* PDF export of 500 rows → <15s
* XLSX export of 1000 rows → <30s
* Drill-down navigation → <3s
* Effectiveness metrics → <5s

Rules Compliance (AAP §0.7)
---------------------------
* R-01: No cross-module imports; only ``odoo.*`` + standard library +
  ``openpyxl`` (top-level import; pinned at 3.1.2 in
  ``requirements.txt`` and already consumed by FEATURE-001's
  ``account_financial_report_ce`` so the dependency is established).
* R-02: No Enterprise module references; no ``account_followup`` /
  ``account_reports`` / ``account_accountant`` / ``account_asset`` /
  ``account_budget`` / ``account_deferred_revenue`` imports.
* R-03: ``_name`` only (net-new TransientModel); no ``_inherit``.
* R-05: Reads core fields on ``account.move`` / ``account.move.line`` only
  via the parser's ``_read_group``; does not modify them.
* R-07: No ``sudo()`` calls; group-based access enforced through
  ``security/ir.model.access.csv``.
"""

import base64
import io
import logging

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

# The AbstractModel parser model name.
#
# IMPORTANT: this is intentionally NOT the literal "report." prefix +
# "report_followup_aged_receivables" the AAP folder spec text suggests.
# The sibling parser ``report/followup_report.py`` deliberately abbreviates
# the template segment from ``report_followup_aged_receivables`` (35 chars)
# to ``followup_aged_receivables`` (25 chars) so that the auto-derived
# ``_table`` identifier
# (``report_account_payment_followup_followup_aged_receivables``, 57 chars)
# stays within PostgreSQL's 63-character identifier limit enforced by
# ``odoo/orm/utils.py::check_pg_name``. The constant below MUST mirror the
# parser's ``_name`` exactly — otherwise ``self.env[...]`` lookup raises
# ``KeyError`` at runtime.
_PARSER_MODEL = "report.account_payment_followup.followup_aged_receivables"

# The fully qualified External ID of the ir.actions.report record declared
# in ``report/followup_report.xml``. The wizard resolves this via
# ``self.env.ref(...)`` to obtain the report action whose ``report_action``
# method dispatches the QWeb PDF rendering pipeline.
_REPORT_ACTION_XID = (
    "account_payment_followup.action_report_followup_aged_receivables"
)


class FollowupReportWizard(models.TransientModel):
    """Wizard collecting filter parameters for the Follow-up Aged Receivables report.

    Users open this wizard from Accounting → Follow-ups → Follow-up Report,
    select filters (date range, partners, levels, aging buckets, minimum
    amount, grouping), and trigger either a PDF export (via
    ``ir.actions.report`` with the QWeb PDF pipeline) or an XLSX export
    (programmatic via openpyxl).

    The wizard itself holds NO business logic for aging calculation — all
    aggregation is delegated to the parser AbstractModel
    ``report.account_payment_followup.followup_aged_receivables``. The
    wizard only holds filter state, UI orchestration, and the XLSX
    generation code (because Odoo 19.0's ``ir.actions.report`` does not
    support the ``qweb-xlsx`` report type).

    As a TransientModel, records are automatically purged by Odoo's garbage
    collector (typically after a few hours of inactivity); filter state
    does NOT persist beyond the user's session.
    """

    _name = "account.followup.report.wizard"
    _description = "Follow-up Aged Receivables Report Wizard"
    _check_company_auto = True

    # -------------------------------------------------------------------------
    # DEFAULT VALUE METHODS
    # -------------------------------------------------------------------------

    @api.model
    def _default_date_from(self):
        """Return the first day of the current month in the user's timezone.

        Used as the default for the ``date_from`` field. The 90-day fiscal
        window pattern is intentionally narrower (a single calendar month)
        because the PF-003 Scenario 7 rule states the default range is
        configurable but should default to recent activity that fits in
        a single PDF page comfortably.
        """
        today = fields.Date.context_today(self)
        return today.replace(day=1)

    @api.model
    def _default_date_to(self):
        """Return today's date in the user's timezone.

        Used as the default for the ``date_to`` field. Together with
        ``_default_date_from``, this produces an effective default window
        of "first of this month → today" — a useful out-of-box range for
        month-to-date follow-up reports.
        """
        return fields.Date.context_today(self)

    @api.model
    def _default_report_date(self):
        """Return today's date in the user's timezone for the as-of date.

        Used as the default for the ``report_date`` field. The aging
        snapshot defaults to "as of today" — invoices with due dates
        before today are classified into overdue buckets, while those
        with due dates today or later are classified as Current.
        """
        return fields.Date.context_today(self)

    # -------------------------------------------------------------------------
    # IDENTITY & SCOPE FIELDS
    # -------------------------------------------------------------------------

    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
        help="Company scope for the report. Only invoices belonging to this "
             "company are included (multi-company isolation, PF-003 BR-007).",
    )

    currency_id = fields.Many2one(
        comodel_name="res.currency",
        string="Currency",
        related="company_id.currency_id",
        store=False,
        readonly=True,
        help="Display currency for monetary amounts, derived from the "
             "selected company. Used by the ``minimum_amount`` Monetary "
             "field as its ``currency_field`` reference.",
    )

    # -------------------------------------------------------------------------
    # DATE RANGE FILTERS
    # -------------------------------------------------------------------------

    date_from = fields.Date(
        string="Date From",
        required=True,
        default=_default_date_from,
        help="Start of the effectiveness-metrics evaluation window. Also "
             "used as a lower bound for payment-promise and action history "
             "filters. Defaults to the first day of the current month.",
    )

    date_to = fields.Date(
        string="Date To",
        required=True,
        default=_default_date_to,
        help="End of the effectiveness-metrics evaluation window. Must be "
             "greater than or equal to Date From. Defaults to today.",
    )

    report_date = fields.Date(
        string="As Of Date",
        required=True,
        default=_default_report_date,
        help="Reference date for aging calculation. Invoices are considered "
             "overdue relative to this date. CRITICAL: this field is read "
             "by the PDF report's ``print_report_name`` expression, which "
             "renders the date into the downloaded filename.",
    )

    # -------------------------------------------------------------------------
    # PARTNER & LEVEL FILTERS (PF-003 Scenarios 2, 7)
    # -------------------------------------------------------------------------

    partner_ids = fields.Many2many(
        comodel_name="res.partner",
        relation="followup_report_wizard_partner_rel",
        column1="wizard_id",
        column2="partner_id",
        string="Customers",
        domain="[('customer_rank', '>', 0)]",
        help="Optional filter: limit the report to specific customers. "
             "Leave empty to include all customers with overdue invoices.",
    )

    followup_level_ids = fields.Many2many(
        comodel_name="account.followup.level",
        relation="followup_report_wizard_level_rel",
        column1="wizard_id",
        column2="level_id",
        string="Follow-up Levels",
        help="Optional filter: limit the report to customers currently "
             "assigned to one of the selected follow-up levels. Leave "
             "empty to include all levels. Supports the PF-003 Scenario "
             "2 multi-select requirement.",
    )

    # -------------------------------------------------------------------------
    # AGING BUCKET & AMOUNT FILTERS (PF-003 Scenarios 1, 7)
    # -------------------------------------------------------------------------

    aging_bucket_filter = fields.Selection(
        selection=[
            ("all", "All Buckets"),
            ("current_only", "Current (Not Yet Due)"),
            ("overdue_only", "Overdue Only (All Past-Due Buckets)"),
            ("1_30", "1-30 Days Overdue"),
            ("31_60", "31-60 Days Overdue"),
            ("61_90", "61-90 Days Overdue"),
            ("90_plus", "Over 90 Days Overdue"),
        ],
        string="Aging Bucket Filter",
        default="all",
        required=True,
        help="Filter partners by their aging bucket. 'All Buckets' includes "
             "everything; 'Current (Not Yet Due)' shows only not-yet-due "
             "receivables; 'Overdue Only' aggregates all past-due buckets; "
             "specific bucket selections (1-30, 31-60, etc.) show only "
             "partners whose most-overdue invoice falls in that exact "
             "window.",
    )

    minimum_amount = fields.Monetary(
        string="Minimum Overdue Amount",
        default=0.0,
        currency_field="currency_id",
        help="Partners with total overdue amount strictly less than this "
             "threshold are excluded. Set to 0 (default) to include all. "
             "Exposed to the report parser as 'amount_threshold' key via "
             "_get_form_values().",
    )

    include_disputed = fields.Boolean(
        string="Include Disputed Invoices",
        default=False,
        help="When checked, includes invoices flagged as disputed "
             "(``move_id.is_disputed = True``). Default False excludes "
             "them to focus on actionable follow-ups.",
    )

    target_moves = fields.Selection(
        selection=[
            ("posted", "Posted Only"),
            ("all", "All Entries"),
        ],
        string="Target Moves",
        default="posted",
        required=True,
        help="'Posted Only' includes invoices in state='posted' (standard "
             "finance convention). 'All Entries' also includes draft "
             "invoices for preliminary forecasting — use with caution.",
    )

    # -------------------------------------------------------------------------
    # GROUPING OPTIONS (PF-003 Scenario 8)
    # -------------------------------------------------------------------------

    group_by_salesperson = fields.Boolean(
        string="Group by Salesperson",
        default=False,
        help="When checked, groups the report by each customer's assigned "
             "salesperson (``res.partner.user_id``). Mutually exclusive "
             "with ``group_by_country`` at the top level.",
    )

    group_by_country = fields.Boolean(
        string="Group by Country/Region",
        default=False,
        help="When checked, groups the report by each customer's country. "
             "Serves the Region grouping requirement per PF-003 §4.1 "
             "(countries are used as regional aggregation keys when no "
             "explicit region is configured).",
    )

    group_by = fields.Selection(
        selection=[
            ("level", "By Follow-up Level"),
            ("salesperson", "By Salesperson"),
            ("region", "By Country/Region"),
            ("aging_bucket", "By Aging Bucket"),
        ],
        string="Primary Grouping",
        compute="_compute_group_by",
        store=False,
        help="Derived grouping key consumed by the parser AbstractModel. "
             "Computed from the boolean ``group_by_*`` flags with "
             "precedence: salesperson > region > aging_bucket > level "
             "(default).",
    )

    group_by_label = fields.Char(
        string="Grouping Label",
        compute="_compute_group_by_label",
        store=False,
        help="Human-readable label for the current ``group_by`` selection, "
             "consumed by the QWeb report template for display in the "
             "report header.",
    )

    # -------------------------------------------------------------------------
    # DISPLAY METADATA FIELDS (consumed by parser for report headers)
    # -------------------------------------------------------------------------

    include_effectiveness = fields.Boolean(
        string="Include Effectiveness Metrics",
        default=True,
        help="When checked, the report computes and displays effectiveness "
             "metrics (recovery rate, average days to payment, response "
             "rate by level, active follow-ups count) per PF-003 Scenario "
             "6. Disabling improves generation speed for large datasets.",
    )

    followup_level_names = fields.Char(
        string="Selected Level Names",
        compute="_compute_followup_level_names",
        store=False,
        help="Comma-separated names of currently selected follow-up levels "
             "for display in the report header. Consumed by the parser "
             "via ``_get_form_values()``.",
    )

    partner_count = fields.Integer(
        string="Matching Partner Count",
        compute="_compute_partner_count",
        store=False,
        help="Count of partners matching current filter criteria, for "
             "display in the report header and UI preview.",
    )

    # -------------------------------------------------------------------------
    # COMPUTE METHODS
    # -------------------------------------------------------------------------

    @api.depends(
        "group_by_salesperson",
        "group_by_country",
        "aging_bucket_filter",
    )
    def _compute_group_by(self):
        """Derive the single ``group_by`` key from the boolean flag fields.

        Precedence (highest first):
            1. ``group_by_salesperson=True`` → ``'salesperson'``
            2. ``group_by_country=True`` → ``'region'``
            3. ``aging_bucket_filter`` not in ('all', 'current_only')
               → ``'aging_bucket'``
            4. Default → ``'level'``

        The compute reads-only — never writes — to the wizard record. The
        ``store=False`` flag means the value is recomputed on every read,
        which is appropriate for a TransientModel that lives only for the
        user's current session.
        """
        for wizard in self:
            if wizard.group_by_salesperson:
                wizard.group_by = "salesperson"
            elif wizard.group_by_country:
                wizard.group_by = "region"
            elif wizard.aging_bucket_filter not in ("all", "current_only"):
                wizard.group_by = "aging_bucket"
            else:
                wizard.group_by = "level"

    @api.depends("group_by")
    def _compute_group_by_label(self):
        """Build a human-readable label for the current grouping selection.

        Uses the field's own ``selection`` definition as the source of
        labels, ensuring the displayed label matches the technical
        selection key one-to-one.
        """
        labels = dict(self._fields["group_by"].selection)
        for wizard in self:
            wizard.group_by_label = labels.get(wizard.group_by, "")

    @api.depends("followup_level_ids")
    def _compute_followup_level_names(self):
        """Comma-join the names of selected levels for display in the header.

        When no levels are selected, returns the i18n string "All Levels"
        so that the consumer (parser, XLSX header) sees a meaningful
        string rather than an empty field.
        """
        for wizard in self:
            if wizard.followup_level_ids:
                wizard.followup_level_names = ", ".join(
                    wizard.followup_level_ids.mapped("name"),
                )
            else:
                wizard.followup_level_names = _("All Levels")

    @api.depends(
        "partner_ids",
        "followup_level_ids",
        "company_id",
        "minimum_amount",
        "aging_bucket_filter",
    )
    def _compute_partner_count(self):
        """Count partners matching the current filter criteria.

        Uses ``search_count()`` rather than ``len(search(...))`` to honor
        the <3s drill-down / preview SLA from PF-003 §6 — the former emits
        a single ``COUNT(*)`` SQL query while the latter materializes a
        Python recordset proportional to the result size.
        """
        Partner = self.env["res.partner"]
        for wizard in self:
            domain = wizard._prepare_partner_domain()
            wizard.partner_count = (
                Partner.search_count(domain) if domain else 0
            )

    # -------------------------------------------------------------------------
    # ONCHANGE HANDLERS
    # -------------------------------------------------------------------------

    @api.onchange("date_from")
    def _onchange_date_from(self):
        """Ensure ``date_to`` >= ``date_from``; auto-adjust if violated.

        Provides immediate UI feedback when the user picks a Date From
        that is later than the current Date To. This complements the
        ``_check_date_range`` constraint, which fires on save rather
        than at the moment of selection.
        """
        for wizard in self:
            if (
                wizard.date_from
                and wizard.date_to
                and wizard.date_to < wizard.date_from
            ):
                wizard.date_to = wizard.date_from

    @api.onchange("report_date")
    def _onchange_report_date(self):
        """Shift the date range to anchor at ``report_date`` when it drifts.

        If the current ``date_to`` is before the new ``report_date``, move
        ``date_to`` to ``report_date``. This keeps the effectiveness
        window aligned with the as-of date when the user adjusts it,
        avoiding a confusing state where the report's "as of" date is
        in the future relative to the effectiveness window.
        """
        for wizard in self:
            if not wizard.report_date:
                continue
            # Only auto-adjust if date_to is behind report_date
            if (
                wizard.date_to
                and wizard.date_to < wizard.report_date
            ):
                wizard.date_to = wizard.report_date

    @api.onchange("group_by_salesperson")
    def _onchange_group_by_salesperson(self):
        """If salesperson grouping is enabled, disable country grouping.

        Keeps the UI self-consistent: users can only select ONE top-level
        grouping at a time. The ``_compute_group_by`` method also
        handles this precedence at read time, but the onchange gives
        immediate UI feedback so the user sees the country checkbox
        un-tick the moment salesperson is checked.
        """
        for wizard in self:
            if wizard.group_by_salesperson:
                wizard.group_by_country = False

    @api.onchange("group_by_country")
    def _onchange_group_by_country(self):
        """Mirror of ``_onchange_group_by_salesperson`` — mutually exclusive.

        Enabling country grouping disables salesperson grouping. Ensures
        the user cannot have both flags set simultaneously, which would
        produce an ambiguous grouping intent.
        """
        for wizard in self:
            if wizard.group_by_country:
                wizard.group_by_salesperson = False

    # -------------------------------------------------------------------------
    # CONSTRAINTS
    # -------------------------------------------------------------------------

    @api.constrains("date_from", "date_to")
    def _check_date_range(self):
        """Ensure ``date_from`` <= ``date_to``.

        Fires at save time. The companion ``_onchange_date_from`` handler
        provides immediate UI feedback before save, so by the time this
        constraint runs the inputs should already be valid — this is
        a defense-in-depth check for cases where the form is bypassed
        (e.g. programmatic record creation in tests).
        """
        for wizard in self:
            if (
                wizard.date_from
                and wizard.date_to
                and wizard.date_from > wizard.date_to
            ):
                raise ValidationError(_(
                    "Date From (%(start)s) must be less than or equal to "
                    "Date To (%(end)s).",
                    start=wizard.date_from,
                    end=wizard.date_to,
                ))

    @api.constrains("minimum_amount")
    def _check_minimum_amount(self):
        """Ensure ``minimum_amount`` is non-negative.

        Negative thresholds make no semantic sense — a "minimum overdue
        amount" of -100 would include all partners regardless of debt,
        which is equivalent to setting it to 0. We reject this rather
        than silently coerce it because it usually indicates user
        confusion or a programmatic bug.
        """
        for wizard in self:
            if wizard.minimum_amount and wizard.minimum_amount < 0:
                raise ValidationError(_(
                    "Minimum Overdue Amount cannot be negative "
                    "(got %(amount)s).",
                    amount=wizard.minimum_amount,
                ))

    @api.constrains("company_id")
    def _check_company_in_allowed(self):
        """Verify the selected company is in the user's allowed companies.

        Although ``_check_company_auto = True`` enforces multi-company
        FK consistency on Many2one fields targeting company-scoped
        comodels, it does NOT enforce that the wizard's own
        ``company_id`` is one the user can act on. This explicit check
        prevents a determined user from setting an arbitrary
        ``company_id`` via XML-RPC and reading data from a company
        they don't have access to.
        """
        for wizard in self:
            if (
                wizard.company_id
                and wizard.company_id not in self.env.companies
            ):
                raise ValidationError(_(
                    "You do not have access to the selected company "
                    "'%(name)s'.",
                    name=wizard.company_id.name,
                ))

    # -------------------------------------------------------------------------
    # VALIDATION HELPERS
    # -------------------------------------------------------------------------

    def _validate_report_prerequisites(self):
        """Pre-generation validation. Raises UserError on invalid wizard state.

        Called at the top of ``action_generate_report()`` and
        ``action_export_xlsx()`` BEFORE any expensive work begins, so that
        the user sees one consolidated error message rather than a
        cascade of partial failures from downstream layers.

        Checks (overlap with @api.constrains is intentional — this gives
        the user a friendlier consolidated message):

            * ``report_date`` is present.
            * ``company_id`` is set.
            * ``date_from`` <= ``date_to`` when both are present.
            * ``minimum_amount`` >= 0.

        Raises:
            UserError: if any prerequisite is violated; the message
                concatenates all errors so the user can fix them in
                one pass.
        """
        self.ensure_one()
        errors = []
        if not self.report_date:
            errors.append(_("As Of Date (report_date) is required."))
        if not self.company_id:
            errors.append(_("Company is required."))
        if (
            self.date_from
            and self.date_to
            and self.date_from > self.date_to
        ):
            errors.append(_(
                "Date From (%(start)s) must be earlier than Date To "
                "(%(end)s).",
                start=self.date_from,
                end=self.date_to,
            ))
        if self.minimum_amount and self.minimum_amount < 0:
            errors.append(_(
                "Minimum Overdue Amount cannot be negative "
                "(got %(amount)s).",
                amount=self.minimum_amount,
            ))
        if errors:
            raise UserError("\n".join(errors))

    # -------------------------------------------------------------------------
    # DOMAIN PREPARATION HELPER
    # -------------------------------------------------------------------------

    def _prepare_partner_domain(self):
        """Build the ``res.partner`` domain for partner-count and previews.

        Used by ``_compute_partner_count`` and indirectly by the parser
        through the form values to establish a consistent filter across
        wizard UI and backend report — both surfaces should agree on
        which partners are "in scope" for a given filter selection.

        Domain Construction:
            * Always: customer rank > 0, company belongs to scope (or is
              global = False).
            * Optional: explicit partner_ids filter, follow-up level
              filter, minimum overdue amount filter, aging-bucket-window
              filter.

        Returns:
            list: An Odoo domain list suitable for ``res.partner.search``.
        """
        self.ensure_one()
        domain = [
            ("customer_rank", ">", 0),
            ("company_id", "in", (False, self.company_id.id)),
        ]
        if self.partner_ids:
            domain.append(("id", "in", self.partner_ids.ids))
        if self.followup_level_ids:
            domain.append(
                ("followup_level_id", "in", self.followup_level_ids.ids),
            )
        if self.minimum_amount and self.minimum_amount > 0:
            domain.append(("total_overdue", ">=", self.minimum_amount))

        # Aging-bucket filter: translate wizard values to partner buckets.
        # The wizard uses the AAP-spec verbatim selection keys
        # (``1_30``/``31_60``/``61_90``/``90_plus``); the partner model
        # exposes them as separate Monetary fields
        # (``aging_bucket_1_30`` etc.), so we filter by "bucket > 0".
        if self.aging_bucket_filter == "current_only":
            domain.append(("has_overdue_invoices", "=", False))
        elif self.aging_bucket_filter == "overdue_only":
            domain.append(("has_overdue_invoices", "=", True))
        elif self.aging_bucket_filter == "1_30":
            domain.append(("aging_bucket_1_30", ">", 0))
        elif self.aging_bucket_filter == "31_60":
            domain.append(("aging_bucket_31_60", ">", 0))
        elif self.aging_bucket_filter == "61_90":
            domain.append(("aging_bucket_61_90", ">", 0))
        elif self.aging_bucket_filter == "90_plus":
            domain.append(("aging_bucket_90_plus", ">", 0))
        # 'all' → no additional aging filter
        return domain

    # -------------------------------------------------------------------------
    # PARSER INTEGRATION — _get_form_values
    # -------------------------------------------------------------------------

    def _get_form_values(self):
        """Return a dict of filter values in parser-expected format.

        The sibling parser AbstractModel
        ``report.account_payment_followup.followup_aged_receivables``
        defensively calls ``hasattr(docs[0], '_get_form_values')`` and
        invokes this method when present, merging its return on top of
        any flat values in the ``data`` dict (the wizard record is the
        authoritative source of filter state when one is provided).

        Explicit field-name mapping documented for the parser contract:

            * ``minimum_amount`` → ``amount_threshold`` (parser key)
            * ``minimum_amount`` → ``minimum_amount`` (alias for backward
              compatibility with consumers that use the wizard-side name)
            * ``partner_ids`` (recordset) → ``partner_ids`` (list of ids)
            * ``followup_level_ids`` (recordset) → ``followup_level_ids``
              (list of ids)
            * ``company_id`` (recordset) → ``company_id`` (int id)
            * ``group_by`` (computed) → ``group_by``
            * ``group_by_label`` (computed) → ``group_by_label``
            * ``followup_level_names`` (computed) → ``followup_level_names``
            * ``partner_count`` (computed) → ``partner_count``

        Returns:
            dict: keys consumed by the parser's ``_get_report_values()``
            and the QWeb template's ``data`` context.
        """
        self.ensure_one()
        return {
            # Scope identification
            "company_id": self.company_id.id,
            "company_name": self.company_id.name,
            "currency_id": self.currency_id.id,
            # Temporal anchors
            "report_date": self.report_date,
            "date_from": self.date_from,
            "date_to": self.date_to,
            # Filter criteria
            "partner_ids": self.partner_ids.ids,
            "followup_level_ids": self.followup_level_ids.ids,
            "followup_level_names": self.followup_level_names,
            # ``amount_threshold`` is the parser's preferred key;
            # ``minimum_amount`` is kept as an alias because the AAP
            # folder spec and the QWeb template both reference it.
            "amount_threshold": self.minimum_amount,
            "minimum_amount": self.minimum_amount,
            "aging_bucket_filter": self.aging_bucket_filter,
            "include_disputed": self.include_disputed,
            "target_moves": self.target_moves,
            # Grouping (both surfaces — parser uses the consolidated
            # ``group_by``; the booleans are exposed for tooling that
            # wants to introspect the user's exact UI choice).
            "group_by": self.group_by,
            "group_by_label": self.group_by_label,
            "group_by_salesperson": self.group_by_salesperson,
            "group_by_country": self.group_by_country,
            # Effectiveness toggle
            "include_effectiveness": self.include_effectiveness,
            # Display metadata
            "partner_count": self.partner_count,
        }

    # -------------------------------------------------------------------------
    # ACTION METHODS — PDF / XLSX / PREVIEW
    # -------------------------------------------------------------------------

    def action_generate_report(self):
        """Trigger PDF generation via the standard Odoo report pipeline.

        Workflow:
            1. ``ensure_one()`` — wizard is always single-record at this
               point.
            2. ``_validate_report_prerequisites()`` — surface filter
               issues with a friendly error before any expensive work.
            3. Resolve the ``ir.actions.report`` action by External ID.
            4. Build the data dict (``_get_form_values`` combined with
               a ``form`` key for parser back-compat).
            5. Return the report's ``report_action(self, data=data)``
               dispatch dict.

        The returned dict is interpreted by the Odoo web client, which
        triggers the PDF render pipeline:

            client → ``ir.actions.report.report_action(self)``
                   → ``AbstractModel._get_report_values(docids, data=...)``
                   → QWeb template rendering with returned context
                   → wkhtmltopdf conversion
                   → file download to browser

        Returns:
            dict: ``ir.actions.report`` action dictionary.

        Raises:
            UserError: if the report XML record is missing (typically
                indicates an incomplete module install) or the wizard
                state fails prerequisites validation.
        """
        self.ensure_one()
        self._validate_report_prerequisites()

        report_ref = self.env.ref(
            _REPORT_ACTION_XID,
            raise_if_not_found=False,
        )
        if not report_ref:
            raise UserError(_(
                "The follow-up aged receivables report action is not "
                "available. Please verify the 'account_payment_followup' "
                "module is correctly installed.",
            ))

        # Build the data dict that will be forwarded to the parser's
        # ``_get_report_values(docids, data=)``. The parser inspects
        # ``data['form']`` first, then falls through to root-level keys,
        # so spreading the form values both ways gives both invocation
        # paths the same view of the filter state.
        form_values = self._get_form_values()
        data = {
            "ids": self.ids,
            "model": self._name,
            "form": form_values,
            **form_values,
        }

        _logger.info(
            "Generating follow-up aged receivables PDF: company=%s, "
            "report_date=%s, %d partners matching filter",
            self.company_id.display_name,
            self.report_date,
            self.partner_count,
        )

        # ``discard_logo_check=True`` is a defensive context flag that
        # short-circuits Odoo's company-logo re-rendering check during
        # PDF generation — useful for large reports where the logo
        # round-trip is a measurable percentage of total render time.
        return report_ref.with_context(
            discard_logo_check=True,
        ).report_action(self, data=data)

    def action_export_xlsx(self):
        """Generate an XLSX workbook of the follow-up report and return URL.

        Odoo 19.0 does NOT support ``report_type='qweb-xlsx'`` — XLSX
        must be generated programmatically. Workflow:

            1. ``ensure_one()`` and validate prerequisites.
            2. Lazy-import openpyxl (localizes import errors).
            3. Invoke parser AbstractModel to fetch aggregated data.
            4. Build workbook: header rows (styled), data rows, totals
               row, optional Effectiveness sheet, Applied Filters sheet.
            5. Serialize to ``BytesIO``, then base64-encode for
               ``ir.attachment.datas``.
            6. Create ``ir.attachment`` record (``res_model=self._name``,
               ``res_id=self.id``).
            7. Return ``ir.actions.act_url`` pointing at
               ``/web/content/<id>?download=true``.

        Performance: must complete <30s for 1000 rows per the PF-003
        SLA. Achieved via:

            * Single parser invocation (no per-row ORM calls).
            * In-memory ``BytesIO`` (no tempfile disk I/O).
            * Direct openpyxl API (no pandas overhead).

        Returns:
            dict: ``ir.actions.act_url`` triggering browser download.

        Raises:
            UserError: if openpyxl is missing (impossible in stock
                Odoo 19.0 — defensive only) or wizard state fails
                prerequisites validation.
        """
        self.ensure_one()
        self._validate_report_prerequisites()

        # openpyxl is pinned in requirements.txt (3.1.2) and is always
        # available in Odoo 19.0 environments. The top-level imports
        # cover Workbook, Alignment, Font, PatternFill, and
        # get_column_letter — all consumed by ``_build_xlsx_workbook``
        # below. We follow the same pattern as FEATURE-001's
        # ``account_financial_report_ce/models/financial_report.py``.

        # Delegate aggregation to the parser AbstractModel — same source
        # of truth as the PDF report, ensuring numeric parity between
        # exports. The parser merges our ``_get_form_values()`` on top
        # of the supplied ``data`` dict.
        parser_model = self.env[_PARSER_MODEL]
        form_values = self._get_form_values()
        report_data = parser_model._get_report_values(
            docids=self.ids,
            data={**form_values, "form": form_values},
        )

        # Build the workbook using helper for testability/readability.
        workbook = self._build_xlsx_workbook(report_data=report_data)

        # Serialize the workbook to in-memory bytes.
        buffer = io.BytesIO()
        workbook.save(buffer)
        xlsx_bytes = buffer.getvalue()
        buffer.close()

        # Construct a human-friendly filename using the company name and
        # report date. We sanitize spaces to underscores so that some
        # browsers' download handling does not choke on the filename.
        company_slug = (self.company_id.name or "Company").replace(" ", "_")
        date_slug = (
            fields.Date.to_string(self.report_date)
            if self.report_date
            else fields.Date.to_string(fields.Date.context_today(self))
        )
        filename = _(
            "Follow-up_Aged_Receivables_%(company)s_%(date)s.xlsx",
            company=company_slug,
            date=date_slug,
        )

        # Create the ir.attachment record. The ``datas`` field is a
        # Binary that expects base64-encoded bytes, NOT raw bytes — this
        # is a frequent source of "weird PDF / XLSX corruption" bugs in
        # Odoo modules.
        attachment = self.env["ir.attachment"].create({
            "name": filename,
            "type": "binary",
            "datas": base64.b64encode(xlsx_bytes),
            "res_model": self._name,
            "res_id": self.id,
            "mimetype": (
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
        })

        _logger.info(
            "Follow-up aged receivables XLSX generated: %s "
            "(size=%d bytes, attachment_id=%s)",
            filename,
            len(xlsx_bytes),
            attachment.id,
        )

        # ``act_url`` triggers a navigation to the Odoo web content
        # endpoint, which streams the attachment binary to the browser.
        # The ``?download=true`` query param forces a browser save
        # dialog rather than an in-window render attempt.
        return {
            "type": "ir.actions.act_url",
            "name": _("Download XLSX"),
            "url": f"/web/content/{attachment.id}?download=true",
            "target": "self",
        }

    def action_preview(self):
        """Convenience action: alias for ``action_generate_report``.

        Kept as a separate method so that the wizard form can bind a
        distinct UI button label ("Preview" vs "Generate PDF") without
        duplicating the underlying PDF-dispatch logic. From a workflow
        perspective both actions produce the same QWeb PDF — the
        distinction is purely UX.
        """
        self.ensure_one()
        return self.action_generate_report()

    def action_drill_to_invoices(self, partner_id):
        """Return an ``ir.actions.act_window`` listing overdue invoices.

        Drill-down helper invoked from the QWeb PDF / XLSX report's
        clickable partner rows (and exposed as a callable contract for
        :file:`tests/test_pf_003.py`). Returns the standard Odoo list
        action for ``account.move`` filtered to the supplied partner's
        unpaid customer invoices, exactly matching the contract
        documented in Checkpoint 2 instructions:

        ``[('partner_id', '=', partner_id),
           ('payment_state', 'in', ('not_paid', 'partial'))]``

        Note: the partner-form smart button on ``res.partner`` (provided
        by :meth:`res.partner._get_overdue_invoices`) uses a more
        comprehensive domain that also includes ``'in_payment'`` to
        handle the in-flight payment-confirmation grace period. The
        wizard's drill-down here uses the strict literal Checkpoint 2
        domain to keep the PDF/XLSX click-through deterministic.

        :param partner_id: ID of the ``res.partner`` to drill into.
        :return: ``ir.actions.act_window`` dict opening
            ``account.move`` filtered to the partner's overdue invoices.
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Overdue Invoices"),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [
                ('partner_id', '=', partner_id),
                ('payment_state', 'in', ('not_paid', 'partial')),
                ('move_type', 'in', ('out_invoice', 'out_refund')),
                ('state', '=', 'posted'),
            ],
            'context': {
                'default_partner_id': partner_id,
                'search_default_partner_id': partner_id,
            },
            'target': 'current',
        }

    # -------------------------------------------------------------------------
    # XLSX WORKBOOK BUILDER (helper for action_export_xlsx)
    # -------------------------------------------------------------------------

    def _build_xlsx_workbook(self, report_data):
        """Construct the XLSX workbook structure for the follow-up report.

        Workbook structure:

            Sheet 1 ("Aged Receivables"):
                Rows 1-3: Header metadata (title, company, filters)
                Row 5:   Column headers (Customer, Level, Current,
                          1-30, 31-60, 61-90, 90+, Total Overdue,
                          Last Action)
                Rows 6-N: Partner data (sorted by total_overdue desc by
                          the parser).
                Row N+2: Totals / summary row.
            Sheet 2 ("Effectiveness") — only if ``include_effectiveness``:
                Recovery rate, avg days to payment, active follow-ups,
                response rate by level.
            Sheet 3 ("Applied Filters") — always:
                Filter values used for audit / repeatability.

        Args:
            report_data: dict returned by the parser model's
                ``_get_report_values()``. Expected keys: ``partners``,
                ``totals``, ``effectiveness``, ``company``, ``currency``.

        Returns:
            ``openpyxl.Workbook``: fully populated workbook ready to
            serialize via ``workbook.save(buffer)``.
        """
        self.ensure_one()
        workbook = Workbook()

        # Style definitions — defined once and reused across sheets to
        # keep the visual design consistent and reduce object churn.
        header_font = Font(bold=True, color="FFFFFF", size=11)
        header_fill = PatternFill(
            start_color="4472C4",
            end_color="4472C4",
            fill_type="solid",
        )
        title_font = Font(bold=True, size=14)
        totals_font = Font(bold=True, size=11)
        totals_fill = PatternFill(
            start_color="D9E1F2",
            end_color="D9E1F2",
            fill_type="solid",
        )
        center_align = Alignment(
            horizontal="center", vertical="center",
        )
        right_align = Alignment(
            horizontal="right", vertical="center",
        )

        # ------------------------------------------------------------------
        # SHEET 1: Aged Receivables (main data sheet)
        # ------------------------------------------------------------------
        ws = workbook.active
        # openpyxl sheet-name max is 31 chars — guard with [:31] in case
        # an i18n translation produces a longer string.
        ws.title = _("Aged Receivables")[:31]

        # Header metadata rows (1-3)
        ws["A1"] = _("Follow-up Aged Receivables Report")
        ws["A1"].font = title_font
        ws.merge_cells("A1:I1")

        ws["A2"] = _(
            "Company: %(name)s",
            name=self.company_id.display_name or "",
        )
        ws["A3"] = _(
            "As Of: %(date)s   |   Partners: %(count)s   |   "
            "Grouping: %(group)s",
            date=(
                fields.Date.to_string(self.report_date)
                if self.report_date else ""
            ),
            count=self.partner_count,
            group=self.group_by_label or "",
        )

        # Column headers (row 5)
        column_headers = [
            _("Customer"),
            _("Follow-up Level"),
            _("Current"),
            _("1-30 Days"),
            _("31-60 Days"),
            _("61-90 Days"),
            _("Over 90 Days"),
            _("Total Overdue"),
            _("Last Action"),
        ]
        for col_idx, text in enumerate(column_headers, start=1):
            cell = ws.cell(row=5, column=col_idx, value=text)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = center_align

        # Data rows starting at row 6 — iterate the pre-aggregated list
        # produced by the parser. Use ``.get()`` with multiple fallbacks
        # so the writer is resilient to schema drift between the parser
        # and the wizard (e.g., the parser uses ``aging_current`` while
        # some older callers use ``aging_bucket_current``).
        partners_data = report_data.get("partners") or []
        current_row = 6
        totals = {
            "current": 0.0,
            "b_1_30": 0.0,
            "b_31_60": 0.0,
            "b_61_90": 0.0,
            "b_90_plus": 0.0,
            "total": 0.0,
        }
        for partner_info in partners_data:
            name = (
                partner_info.get("partner_name")
                or partner_info.get("name")
                or ""
            )
            level = (
                partner_info.get("level_name")
                or partner_info.get("followup_level")
                or ""
            )
            bucket_current = float(
                partner_info.get("aging_current")
                or partner_info.get("aging_bucket_current")
                or 0.0,
            )
            bucket_1_30 = float(
                partner_info.get("aging_1_30")
                or partner_info.get("aging_bucket_1_30")
                or 0.0,
            )
            bucket_31_60 = float(
                partner_info.get("aging_31_60")
                or partner_info.get("aging_bucket_31_60")
                or 0.0,
            )
            bucket_61_90 = float(
                partner_info.get("aging_61_90")
                or partner_info.get("aging_bucket_61_90")
                or 0.0,
            )
            bucket_90_plus = float(
                partner_info.get("aging_90_plus")
                or partner_info.get("aging_bucket_90_plus")
                or 0.0,
            )
            total_overdue = float(
                partner_info.get("total_overdue") or 0.0,
            )
            last_action = (
                partner_info.get("last_action_summary")
                or partner_info.get("last_followup_date")
                or partner_info.get("oldest_date")
                or ""
            )

            ws.cell(row=current_row, column=1, value=name)
            ws.cell(row=current_row, column=2, value=level)
            cell = ws.cell(row=current_row, column=3, value=bucket_current)
            cell.alignment = right_align
            cell = ws.cell(row=current_row, column=4, value=bucket_1_30)
            cell.alignment = right_align
            cell = ws.cell(row=current_row, column=5, value=bucket_31_60)
            cell.alignment = right_align
            cell = ws.cell(row=current_row, column=6, value=bucket_61_90)
            cell.alignment = right_align
            cell = ws.cell(row=current_row, column=7, value=bucket_90_plus)
            cell.alignment = right_align
            cell = ws.cell(row=current_row, column=8, value=total_overdue)
            cell.alignment = right_align
            ws.cell(row=current_row, column=9, value=str(last_action))

            totals["current"] += bucket_current
            totals["b_1_30"] += bucket_1_30
            totals["b_31_60"] += bucket_31_60
            totals["b_61_90"] += bucket_61_90
            totals["b_90_plus"] += bucket_90_plus
            totals["total"] += total_overdue
            current_row += 1

        # Totals row — placed two rows below the last data row so the
        # blank row provides visual separation between the data table
        # and the summary line.
        totals_row = current_row + 1
        totals_cells = [
            (1, _("TOTALS")),
            (2, ""),
            (3, totals["current"]),
            (4, totals["b_1_30"]),
            (5, totals["b_31_60"]),
            (6, totals["b_61_90"]),
            (7, totals["b_90_plus"]),
            (8, totals["total"]),
            (9, ""),
        ]
        for col_idx, value in totals_cells:
            cell = ws.cell(row=totals_row, column=col_idx, value=value)
            cell.font = totals_font
            cell.fill = totals_fill
            if 3 <= col_idx <= 8:
                cell.alignment = right_align

        # Set sensible column widths — derived empirically from the
        # typical content sizes (customer names up to 28 chars, levels
        # to 22, monetary amounts to 14-16, last-action freeform 28).
        column_widths = [28, 22, 14, 14, 14, 14, 14, 16, 28]
        for col_idx, width in enumerate(column_widths, start=1):
            ws.column_dimensions[get_column_letter(col_idx)].width = width

        # Freeze the first five rows (metadata + column headers) so
        # they remain visible when the user scrolls a long partner
        # list. ``A6`` means "freeze rows 1-5" in openpyxl semantics.
        ws.freeze_panes = "A6"

        # ------------------------------------------------------------------
        # SHEET 2: Effectiveness (only if include_effectiveness=True)
        # ------------------------------------------------------------------
        if self.include_effectiveness:
            self._build_effectiveness_sheet(
                workbook=workbook,
                report_data=report_data,
                title_font=title_font,
                header_font=header_font,
                header_fill=header_fill,
                center_align=center_align,
            )

        # ------------------------------------------------------------------
        # SHEET 3: Applied Filters (always — audit/repeatability)
        # ------------------------------------------------------------------
        self._build_filters_sheet(
            workbook=workbook,
            title_font=title_font,
            header_font=header_font,
        )

        return workbook

    def _build_effectiveness_sheet(
        self,
        workbook,
        report_data,
        title_font,
        header_font,
        header_fill,
        center_align,
    ):
        """Append the Effectiveness sheet to an existing workbook.

        Extracted from ``_build_xlsx_workbook`` to keep that method
        under a reasonable line count and to enable independent unit
        testing of the effectiveness rendering logic.

        Args:
            workbook: ``openpyxl.Workbook`` to append the sheet to.
            report_data: parser output dict (reads
                ``effectiveness`` key).
            title_font / header_font / header_fill / center_align:
                openpyxl style objects produced once in
                ``_build_xlsx_workbook`` and reused here.
        """
        eff_ws = workbook.create_sheet(title=_("Effectiveness")[:31])
        effectiveness = report_data.get("effectiveness") or {}

        eff_ws["A1"] = _("Follow-up Effectiveness Metrics")
        eff_ws["A1"].font = title_font
        eff_ws.merge_cells("A1:C1")

        # Scalar metrics: one row per metric with label + value.
        metrics_rows = [
            (_("Total Overdue"), effectiveness.get("total_overdue", 0.0)),
            (
                _("Total Recovered"),
                effectiveness.get("total_recovered", 0.0),
            ),
            (
                _("Recovery Rate (%)"),
                effectiveness.get("recovery_rate_pct", 0.0),
            ),
            (
                _("Avg Days to Payment"),
                effectiveness.get("avg_days_to_payment", 0.0),
            ),
            (
                _("Active Follow-ups"),
                effectiveness.get("active_followups", 0),
            ),
        ]
        row_idx = 3
        for label, value in metrics_rows:
            cell = eff_ws.cell(row=row_idx, column=1, value=label)
            cell.font = header_font
            eff_ws.cell(row=row_idx, column=2, value=value)
            row_idx += 1

        # Response-rate-by-level sub-table — separator row + sub-title
        # + headers + data.
        row_idx += 2
        cell = eff_ws.cell(
            row=row_idx, column=1,
            value=_("Response Rate by Level"),
        )
        cell.font = title_font
        row_idx += 1

        sub_headers = (
            _("Level"),
            _("Sent"),
            _("Responses"),
            _("Response Rate %"),
        )
        for header_idx, header_text in enumerate(sub_headers, start=1):
            cell = eff_ws.cell(
                row=row_idx, column=header_idx, value=header_text,
            )
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = center_align
        row_idx += 1

        for level_stat in (
            effectiveness.get("response_rate_by_level") or []
        ):
            eff_ws.cell(
                row=row_idx, column=1,
                value=level_stat.get("level_name") or "",
            )
            eff_ws.cell(
                row=row_idx, column=2,
                value=level_stat.get("sent_count") or 0,
            )
            eff_ws.cell(
                row=row_idx, column=3,
                value=level_stat.get("response_count") or 0,
            )
            eff_ws.cell(
                row=row_idx, column=4,
                value=level_stat.get("response_rate_pct") or 0.0,
            )
            row_idx += 1

        for col_idx, width in enumerate([28, 16, 16, 18], start=1):
            eff_ws.column_dimensions[get_column_letter(col_idx)].width = width

    def _build_filters_sheet(self, workbook, title_font, header_font):
        """Append the Applied Filters audit sheet to a workbook.

        Records every filter the user selected so the XLSX export can
        be reproduced or audited later — this satisfies PF-003 BR-006
        ("exports preserve filters").

        Args:
            workbook: ``openpyxl.Workbook`` to append the sheet to.
            title_font: openpyxl ``Font`` for the sheet title.
            header_font: openpyxl ``Font`` for label cells in the
                key/value layout.
        """
        filter_ws = workbook.create_sheet(title=_("Applied Filters")[:31])
        filter_ws["A1"] = _("Applied Filters (for audit/repeatability)")
        filter_ws["A1"].font = title_font
        filter_ws.merge_cells("A1:B1")

        aging_label = dict(
            self._fields["aging_bucket_filter"].selection,
        ).get(self.aging_bucket_filter, self.aging_bucket_filter)
        target_moves_label = dict(
            self._fields["target_moves"].selection,
        ).get(self.target_moves, self.target_moves)

        filter_rows = [
            (_("Company"), self.company_id.display_name or ""),
            (
                _("As Of Date"),
                fields.Date.to_string(self.report_date)
                if self.report_date else "",
            ),
            (
                _("Date From"),
                fields.Date.to_string(self.date_from)
                if self.date_from else "",
            ),
            (
                _("Date To"),
                fields.Date.to_string(self.date_to)
                if self.date_to else "",
            ),
            (
                _("Selected Customers"),
                ", ".join(self.partner_ids.mapped("name"))
                if self.partner_ids else _("All"),
            ),
            (
                _("Selected Levels"),
                self.followup_level_names or _("All"),
            ),
            (_("Aging Bucket Filter"), aging_label),
            (_("Minimum Amount"), self.minimum_amount or 0.0),
            (
                _("Include Disputed"),
                _("Yes") if self.include_disputed else _("No"),
            ),
            (_("Target Moves"), target_moves_label),
            (_("Primary Grouping"), self.group_by_label or ""),
            (
                _("Include Effectiveness"),
                _("Yes") if self.include_effectiveness else _("No"),
            ),
            (
                _("Generated At"),
                fields.Datetime.to_string(fields.Datetime.now()),
            ),
            (_("Generated By"), self.env.user.display_name),
        ]
        for row_idx, (label, value) in enumerate(filter_rows, start=3):
            cell = filter_ws.cell(row=row_idx, column=1, value=label)
            cell.font = header_font
            filter_ws.cell(row=row_idx, column=2, value=value)

        filter_ws.column_dimensions["A"].width = 28
        filter_ws.column_dimensions["B"].width = 60
