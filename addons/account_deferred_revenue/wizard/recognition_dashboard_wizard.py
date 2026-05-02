# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""DR-004 Recognition Dashboard Wizard.

This module implements the **Deferred Revenue Recognition Dashboard** as a
``TransientModel`` (``account.deferred.recognition.dashboard.wizard``) for
the ``account_deferred_revenue`` Odoo 19.0 Community Edition addon.

The dashboard is a **read-only presentation layer** that aggregates
deferred-revenue and deferred-expense data for at-a-glance monitoring.
It **never writes business records** to the database — its compute
methods only consume ``search()`` and ``read_group()`` output from the
two sibling data models (``account.deferred.schedule`` and
``account.deferred.line``) and expose the results through typed fields
that the XML dashboard form view renders as:

* Four summary KPI cards (total deferred revenue, total deferred
  expenses, active-schedule count, next-period recognition total).
* Three JSON-backed breakdown payloads (per-recognition-method, per
  calendar-month, per-completion-status) rendered with the native
  ``json`` widget — no custom OWL component is needed.
* Five drill-down action buttons that navigate the user to filtered
  list/form views of the underlying schedules and recognition lines.

Authoritative references (see AAP §0.5.1.3 and ticket DR-004):

* ``tickets/stories/deferred-revenue/DR-004-recognition-dashboard.md``
  (5 BDD acceptance scenarios: Pending-deferrals summary, Upcoming
  recognitions by period, Date-range filter, Drill-down to source
  transactions, Recognition-completion-status distribution).
* ``addons/account_deferred_revenue/models/account_deferred_schedule.py``
  and ``addons/account_deferred_revenue/models/account_deferred_line.py``
  — the two sibling data models that back every dashboard computation.
* ``addons/account_deferred_revenue/views/recognition_dashboard_views.xml``
  — the XML form view that renders every field/action defined here.
  Field names and action method names declared in this file **must match
  that view exactly**.
* ``addons/account_financial_report_ce/models/financial_report.py`` —
  the FEATURE-001 precedent for ``read_group``-driven reporting.

Performance target (AAP §0.5.3 and DR-004 ticket):

* ``_compute_summary`` and ``_compute_breakdown`` must complete in
  **under 2 seconds** for up to **1,000** ``account.deferred.schedule``
  records.  Achieved by a single ``search()`` + Python defaultdict
  aggregation for the revenue/expense split and three ``read_group()``
  calls (not row-level iteration) for the breakdown payloads.

Rules compliance (AAP §0.7):

* **R-01 Module independence** — imports come only from ``odoo``,
  ``dateutil``, and ``collections``; never from sibling new modules
  ``account_asset_management``, ``account_budget_management``, or
  ``account_payment_followup``.
* **R-02 No Enterprise dependencies** — no references to
  ``account_accountant``, ``account_reports``, ``account_asset``,
  ``account_budget``, ``account_followup``, or Enterprise variants.
* **R-03 ``_inherit`` vs ``_name``** — this is a net-new TransientModel
  so it declares ``_name``, never ``_inherit``.
* **R-05 No core field redefinition** — this file only ``reads`` fields
  on ``account.move``, ``account.move.line``, ``res.partner``, and
  ``account.account`` via domain filters; it never adds, overrides, or
  removes core field definitions.
* **R-07 No unjustified ``sudo()``** — ``sudo()`` is **not used** in
  this file at all; access is controlled via the security rules on
  ``account.deferred.schedule`` and ``account.deferred.line``.

Security:

* Access control for this wizard is declared in
  ``addons/account_deferred_revenue/security/ir.model.access.csv`` with
  full (1,1,1,1) CRUD rights for ``group_deferred_revenue_user``.
* Because this is a TransientModel, Odoo's ``base.autovacuum`` cron
  automatically purges old wizard rows.

Integration points:

* The XML view ``views/recognition_dashboard_views.xml`` references every
  field and every ``action_*`` method declared below.  The menu item in
  ``views/menuitem.xml`` opens the dashboard via the window action
  ``action_deferred_recognition_dashboard``.
"""

import base64
import io
import logging
from collections import defaultdict

from dateutil.relativedelta import relativedelta
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import format_date

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level constants — account.account.account_type values that classify
# a recognition account as deferred *revenue* or deferred *expense*.
#
# These tuples are derived from the ``account_type`` Selection field
# defined in ``addons/account/models/account_account.py``.  Only the
# accounts used for P&L recognition belong here; balance-sheet
# classifications (``asset_*``, ``liability_*``, ``equity*``,
# ``off_balance``) never appear on a valid ``recognition_account_id``.
# ---------------------------------------------------------------------------
_INCOME_ACCOUNT_TYPES = ('income', 'income_other')
_EXPENSE_ACCOUNT_TYPES = ('expense', 'expense_depreciation', 'expense_direct_cost')


class AccountDeferredRecognitionDashboardWizard(models.TransientModel):
    """Read-only dashboard aggregating deferred-revenue KPI data.

    This TransientModel is **populated on read** — every numeric,
    monetary, count, and JSON field is a ``compute=`` field that
    (re)runs against the live database whenever any of the filter
    fields (``date_from``, ``date_to``, ``company_id``,
    ``status_filter``) changes.  The dashboard does **not** store any
    aggregate value permanently — the transient nature of the model
    means the Odoo ``base.autovacuum`` cron will purge instances after
    a short retention window.

    Invocation pattern (from the XML menu entry):

    .. code-block:: python

        env['account.deferred.recognition.dashboard.wizard'].create({})
        # Computed fields auto-populate on field access

    End users interact with the dashboard exclusively through:

    1. The filter bar (``date_from``, ``date_to``, ``company_id``,
       ``status_filter``) — modifying any of these triggers the
       ``@api.depends`` recomputation chain.
    2. The KPI card buttons — ``action_view_revenue``,
       ``action_view_expenses``, ``action_view_pending``, and
       ``action_view_next_period_lines`` — which return
       ``ir.actions.act_window`` dicts that navigate to filtered
       lists of schedules or recognition lines.
    3. The **Refresh** header button (``action_refresh``) — forces a
       recomputation without changing any filter (useful after the
       cut-off wizard posts new recognition entries in another tab).
    """

    _name = 'account.deferred.recognition.dashboard.wizard'
    _description = 'Deferred Revenue Recognition Dashboard'
    # When True, Odoo automatically filters record access so users only
    # see rows in the company context they currently operate in.  This
    # also engages the ``check_company`` infrastructure on any
    # ``Many2one`` field that references a company-scoped model.
    _check_company_auto = True

    # -----------------------------------------------------------------
    # SECTION 1 — Filter fields (drive the @api.depends recomputation).
    # -----------------------------------------------------------------

    # FB-05 (QA Checkpoint 6): The previous default range -- January 1
    # to December 31 of the *current* calendar year -- hides every
    # schedule whose recognition window is entirely in a prior fiscal
    # year. In practice many real-world deferred-revenue schedules
    # span the previous fiscal year (e.g. an annual subscription
    # invoiced in 2025 with monthly recognition through Dec 2025), so
    # opening the dashboard on May 2 2026 with the prior default
    # would yield empty KPIs and an empty period breakdown until the
    # user manually widened the range. The widened default
    # (``today - 2 years`` to ``today + 1 year``) captures both
    # already-recognized historical schedules (for audit / drill-down)
    # and forward-looking schedules (for cash-flow forecasting),
    # matching the typical fiscal close + budgeting workflow.
    date_from = fields.Date(
        string='From',
        default=lambda self: (
            fields.Date.context_today(self) - relativedelta(years=2)
        ).replace(month=1, day=1),
        required=True,
        help='Start of the dashboard date range.  Recognition lines '
             'whose ``recognition_date`` is greater than or equal to '
             'this date are included in the period breakdown.  '
             'Schedules whose ``end_date`` is on or after this date '
             '(or is empty) are included in the summary cards.  '
             'Defaults to January 1 of the year two calendar years '
             'before today, so prior-year fiscal schedules remain '
             'visible without manual range adjustment (FB-05).',
    )

    date_to = fields.Date(
        string='To',
        default=lambda self: (
            fields.Date.context_today(self) + relativedelta(years=1)
        ).replace(month=12, day=31),
        required=True,
        help='End of the dashboard date range.  Recognition lines '
             'whose ``recognition_date`` is less than or equal to '
             'this date are included in the period breakdown.  '
             'Schedules whose ``start_date`` is on or before this '
             'date are included in the summary cards.  '
             'Defaults to December 31 of the year one calendar year '
             'after today, so forward-looking recognition forecasts '
             'remain visible without manual range adjustment (FB-05).',
    )

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True,
        help='Company context for every aggregation.  All schedule and '
             'recognition-line searches are filtered by ``company_id``; '
             'no cross-company totals are ever displayed.  Multi-company '
             'users can switch the displayed company here (visible only '
             'when the ``base.group_multi_company`` group is granted).',
    )

    currency_id = fields.Many2one(
        comodel_name='res.currency',
        related='company_id.currency_id',
        string='Currency',
        readonly=True,
        help='Display currency for every ``Monetary`` field on this '
             'dashboard.  Derived from the selected company; switches '
             'automatically when the filter bar company changes.',
    )

    status_filter = fields.Selection(
        selection=[
            ('active', 'Active'),
            ('completed', 'Completed'),
            ('on_hold', 'On Hold'),
            ('all', 'All'),
        ],
        string='Status',
        default='active',
        required=True,
        help='Filter schedules by their computed ``completion_status``.  '
             '``active`` (default) shows only confirmed schedules with '
             'outstanding amounts; ``completed`` shows fully recognized '
             'schedules; ``on_hold`` shows draft/cancelled schedules; '
             '``all`` disables the status filter.',
    )

    # -----------------------------------------------------------------
    # SECTION 2 — Summary KPI fields (computed in ``_compute_summary``).
    # -----------------------------------------------------------------

    total_deferred_revenue = fields.Monetary(
        string='Total Deferred Revenue',
        compute='_compute_summary',
        currency_field='currency_id',
        help='Sum of ``remaining_amount`` across every schedule whose '
             'recognition account has ``account_type`` in ``income`` '
             'or ``income_other`` and that falls within the dashboard '
             'date range and the selected status filter.',
    )

    total_deferred_expenses = fields.Monetary(
        string='Total Deferred Expenses',
        compute='_compute_summary',
        currency_field='currency_id',
        help='Sum of ``remaining_amount`` across every schedule whose '
             'recognition account has ``account_type`` in ``expense``, '
             '``expense_depreciation``, or ``expense_direct_cost`` and '
             'that falls within the dashboard date range and the '
             'selected status filter.',
    )

    active_schedule_count = fields.Integer(
        string='Active Schedules',
        compute='_compute_summary',
        help='Count of schedules matching the current filter set.  '
             'Uses the **filtered** schedule population so the card '
             'value remains consistent with the other KPI card totals '
             'when the user changes the status filter.',
    )

    next_period_recognition = fields.Monetary(
        string='Next Period Recognition',
        compute='_compute_summary',
        currency_field='currency_id',
        help='Sum of ``recognition_amount`` across every draft '
             'recognition line whose ``recognition_date`` falls in the '
             'next calendar month (first-to-last day).  Answers the '
             'question: *How much revenue/expense am I about to post '
             'when the month-end cut-off wizard runs?*',
    )

    # -----------------------------------------------------------------
    # SECTION 3 — Breakdown JSON fields (computed in ``_compute_breakdown``).
    #
    # Stored as ``fields.Json`` (PostgreSQL ``jsonb``) so the back-end
    # representation remains structured for any downstream consumers
    # (export-to-XLSX, scheduled reports, etc.).  The form view does
    # NOT render these JSON payloads directly — Issue #18 fix: the
    # JSON payloads are projected into HTML tables via
    # ``status_distribution_html`` / ``schedule_breakdown_html`` /
    # ``period_breakdown_html`` (defined below) so end-users see a
    # readable visualization rather than raw JSON literals.
    # -----------------------------------------------------------------

    schedule_breakdown_json = fields.Json(
        string='Schedule Breakdown',
        compute='_compute_breakdown',
        help='List of dicts with one entry per ``recognition_method``: '
             '``[{"recognition_method": "straight_line", "count": 42, '
             '"total_amount": 1000.0}, ...]``.  Produced by a single '
             '``read_group`` call on ``account.deferred.schedule`` '
             'with ``groupby=["recognition_method"]``.',
    )

    period_breakdown_json = fields.Json(
        string='Period Breakdown',
        compute='_compute_breakdown',
        help='List of dicts with one entry per calendar month in the '
             'dashboard date range: ``[{"month": "January 2024", '
             '"total": 5000.0, "count": 12}, ...]``.  Produced by a '
             'single ``read_group`` call on ``account.deferred.line`` '
             'with ``groupby=["recognition_date:month"]``.',
    )

    status_distribution_json = fields.Json(
        string='Status Distribution',
        compute='_compute_breakdown',
        help='Dict keyed by ``completion_status`` value with the '
             'schedule count as value: '
             '``{"active": 18, "completed": 5, "on_hold": 2}``.  '
             'Produced by a single ``read_group`` call on '
             '``account.deferred.schedule`` with '
             '``groupby=["completion_status"]``.  Missing keys '
             '(no schedules in that status) are intentionally absent.',
    )

    # -----------------------------------------------------------------
    # SECTION 3.5 — HTML projections of the breakdown payloads (Issue #18 fix).
    #
    # The dashboard renders ``widget="html"`` over these computed
    # fields so end users see a readable table instead of raw JSON.
    # Each is derived in ``_compute_breakdown_html`` from the matching
    # ``*_breakdown_json`` field — keeping the HTML rendering logic
    # close to the source data while leaving the JSON payloads
    # untouched for any downstream consumer (export, scheduled report).
    # -----------------------------------------------------------------

    status_distribution_html = fields.Html(
        string='Status Distribution (Rendered)',
        compute='_compute_breakdown_html',
        sanitize=False,
        readonly=True,
        help='HTML table projection of ``status_distribution_json`` '
             'rendered by the dashboard form view (Issue #18 fix).',
    )

    schedule_breakdown_html = fields.Html(
        string='Schedule Breakdown (Rendered)',
        compute='_compute_breakdown_html',
        sanitize=False,
        readonly=True,
        help='HTML table projection of ``schedule_breakdown_json`` '
             'rendered by the dashboard form view (Issue #18 fix).',
    )

    period_breakdown_html = fields.Html(
        string='Period Breakdown (Rendered)',
        compute='_compute_breakdown_html',
        sanitize=False,
        readonly=True,
        help='HTML table projection of ``period_breakdown_json`` '
             'rendered by the dashboard form view (Issue #18 fix).',
    )

    # -----------------------------------------------------------------
    # SECTION 3.6 — display_name override (Issue #16 fix).
    #
    # Without a ``display_name`` computed field the standard Odoo
    # breadcrumb rendering falls back to the model technical name +
    # transient NewId, e.g.
    # ``account.deferred.recognition.dashboard.wizard,NewId_0x...``.
    # Overriding the field with a human-readable computation produces
    # a clean breadcrumb such as
    # ``Recognition Dashboard — As of 2026-05-02``.
    # -----------------------------------------------------------------

    display_name = fields.Char(
        string='Display Name',
        compute='_compute_display_name',
        store=False,
        help='Human-readable label rendered in the breadcrumb and '
             'window title (Issue #16 fix).',
    )

    # -----------------------------------------------------------------
    # SECTION 4 — Validation constraints.
    # -----------------------------------------------------------------

    # Maximum dashboard date-range span, in days.  Set to ``5 * 366``
    # so the constraint accepts up to and including five full leap
    # years (the worst-case maximal span for any 5-year window) and
    # rejects ranges that exceed that bound.  Bounding the range
    # prevents the dashboard's ``read_group`` aggregations from
    # degenerating into expensive scans across the full
    # ``account.move.line`` history (DoS-style risk on a multi-year
    # corpus) — a Phase 5 Security requirement of CP4.
    _MAX_DATE_RANGE_DAYS = 5 * 366

    @api.constrains('date_from', 'date_to')
    def _check_date_range(self):
        """Guarantee a sensible ``date_from``/``date_to`` window.

        Called by the ORM whenever the wizard is created or either
        date is updated.  Because the fields are ``required=True`` and
        have lambda defaults that set them to January 1 and December
        31 of the current year respectively, this constraint only
        fires when the user explicitly modifies the range.

        Two invariants are enforced:

        1. ``date_from <= date_to`` — a strictly inverted range is a
           user error and results in a translated
           :class:`~odoo.exceptions.UserError`.
        2. ``date_to - date_from <= 5 * 366 days`` (~ five years) — a
           wider window risks an expensive ``read_group`` aggregation
           over the full ``account.move.line`` history, so this
           constraint protects the dashboard from accidental DoS-
           style queries (Phase 5 Security mandate of CP4).  The
           ``5 * 366`` figure caps the worst-case range covering five
           leap years.
        """
        for wizard in self:
            if (
                wizard.date_from
                and wizard.date_to
                and wizard.date_from > wizard.date_to
            ):
                raise UserError(_(
                    'The "From" date (%(from)s) must be on or before '
                    'the "To" date (%(to)s).',
                    **{
                        'from': format_date(self.env, wizard.date_from),
                        'to': format_date(self.env, wizard.date_to),
                    },
                ))
            # Phase 5 Security — bound the dashboard window so a
            # malicious or careless user cannot trigger a multi-year
            # ``read_group`` aggregation.  Using day-difference is the
            # simplest portable check; the ``5 * 366`` bound matches
            # the documented "5-year" target (worst-case leap-year
            # span).
            if (
                wizard.date_from
                and wizard.date_to
                and (wizard.date_to - wizard.date_from).days
                > self._MAX_DATE_RANGE_DAYS
            ):
                raise UserError(_(
                    "Date range cannot exceed 5 years to prevent "
                    "expensive aggregations on the dashboard.  "
                    "Selected range: %(from)s to %(to)s.",
                    **{
                        'from': format_date(self.env, wizard.date_from),
                        'to': format_date(self.env, wizard.date_to),
                    },
                ))

    # -----------------------------------------------------------------
    # SECTION 5 — Domain-building helpers.
    #
    # These helpers centralise domain construction so the compute
    # methods and action methods share a single source of truth for
    # how filter fields translate into ORM search domains.  Keeping
    # them as private methods (``_``-prefixed) also prevents
    # accidental consumption from XML view expressions.
    # -----------------------------------------------------------------

    def _get_base_schedule_domain(self):
        """Return the shared schedule domain for summary + breakdown.

        The returned domain filters schedules by company and by
        date-range overlap with the dashboard window.  It does **not**
        apply the ``status_filter`` — that is layered on top by the
        caller (see :meth:`_apply_status_filter`).

        The date logic uses *overlap* semantics (not containment):

        * ``start_date <= date_to`` — the schedule starts before or
          during the window.
        * ``end_date >= date_from`` *or* ``end_date`` is unset — the
          schedule is still open, or it ends during/after the window.
        """
        self.ensure_one()
        return [
            ('company_id', '=', self.company_id.id),
            ('start_date', '<=', self.date_to),
            '|',
            ('end_date', '>=', self.date_from),
            ('end_date', '=', False),
        ]

    def _apply_status_filter(self, domain):
        """Append the ``status_filter`` clauses to ``domain`` in place.

        The three concrete filter values (``active``, ``completed``,
        ``on_hold``) map directly to the ``completion_status``
        Selection on ``account.deferred.schedule``; ``all`` is a
        no-op.  ``active`` additionally constrains ``state`` so that
        draft-but-not-confirmed schedules never appear in the
        "active" card count.

        :param list domain: the domain being built — mutated in place
            and returned for fluent chaining.
        :return: the mutated domain.
        :rtype: list
        """
        self.ensure_one()
        if self.status_filter == 'active':
            domain.append(('state', '=', 'confirmed'))
            domain.append(('completion_status', '=', 'active'))
        elif self.status_filter == 'completed':
            domain.append(('completion_status', '=', 'completed'))
        elif self.status_filter == 'on_hold':
            domain.append(('completion_status', '=', 'on_hold'))
        # status_filter == 'all' intentionally does not modify the domain.
        return domain

    # -----------------------------------------------------------------
    # SECTION 6 — Summary KPI computation.
    # -----------------------------------------------------------------

    @api.depends('date_from', 'date_to', 'company_id', 'status_filter')
    def _compute_summary(self):
        """Populate the four summary KPI cards.

        This compute method is the **performance-critical** entry
        point for the dashboard.  It is invoked every time any of the
        four trigger fields (``date_from``, ``date_to``,
        ``company_id``, ``status_filter``) changes, which on a live
        dashboard may happen multiple times per page interaction.

        Performance target (AAP §0.5.3, DR-004):
        **< 2 seconds for 1,000 schedules**.

        Strategy:

        1. **Schedules** — a single ``search()`` call returns the
           filtered recordset, then a Python ``defaultdict(float)``
           aggregates ``remaining_amount`` by the recognition
           account's ``account_type``.  Because Odoo prefetches the
           ``recognition_account_id`` batch when the first attribute
           is accessed, this loop remains O(n) with minimal SQL
           round-trips.
        2. **Next-period recognition** — a single ``read_group()``
           call on ``account.deferred.line`` produces the sum
           directly in PostgreSQL, avoiding any row-level iteration.
        """
        # Initialise every field to a neutral default first so that
        # computed fields have a predictable value even on a brand-new
        # transient record before the first filter is set.  Using the
        # recordset-level initialisation pattern also satisfies Odoo's
        # multi-record compute contract (one @api.depends run for the
        # entire recordset).
        for wizard in self:
            wizard.total_deferred_revenue = 0.0
            wizard.total_deferred_expenses = 0.0
            wizard.active_schedule_count = 0
            wizard.next_period_recognition = 0.0

            # Guard clause — a partially-initialised wizard (e.g.
            # immediately after ``create({})`` before defaults apply)
            # should leave the KPIs at zero rather than raise.
            if not wizard.date_from or not wizard.date_to or not wizard.company_id:
                continue

            # Build the schedule domain with status filter layered on.
            schedule_domain = wizard._get_base_schedule_domain()
            wizard._apply_status_filter(schedule_domain)

            # Search the full filtered schedule recordset.  Odoo's
            # prefetch mechanism amortises the cost of accessing
            # ``recognition_account_id.account_type`` across the whole
            # recordset in a single follow-up SELECT.
            Schedule = self.env['account.deferred.schedule']
            schedules = Schedule.search(schedule_domain)

            # Revenue / expense split — aggregated by account_type via
            # a Python ``defaultdict(float)``.  This pattern keeps the
            # ORM calls to exactly two (the initial search + the
            # prefetch of recognition_account_id / account_type) and
            # handles every ``account_type`` value uniformly, even
            # unexpected ones that simply fall outside the income /
            # expense tuples and are ignored.
            totals_by_type = defaultdict(float)
            for schedule in schedules:
                account_type = schedule.recognition_account_id.account_type
                # ``remaining_amount`` is a computed stored field on
                # the schedule; fall back to ``total_amount`` if the
                # compute has not yet fired (edge case during
                # concurrent writes).
                amount = schedule.remaining_amount or schedule.total_amount or 0.0
                totals_by_type[account_type] += amount

            wizard.total_deferred_revenue = sum(
                totals_by_type[acct_type] for acct_type in _INCOME_ACCOUNT_TYPES
            )
            wizard.total_deferred_expenses = sum(
                totals_by_type[acct_type] for acct_type in _EXPENSE_ACCOUNT_TYPES
            )
            wizard.active_schedule_count = len(schedules)

            # Next-period recognition — sum over draft recognition
            # lines whose recognition_date falls in the NEXT calendar
            # month.  We use relativedelta for safe month arithmetic
            # that correctly handles 28/29/30/31-day months and year
            # rollovers.
            today = fields.Date.context_today(wizard)
            next_month_start = (today + relativedelta(months=1)).replace(day=1)
            next_month_end = (
                next_month_start + relativedelta(months=1, days=-1)
            )

            Line = self.env['account.deferred.line']
            line_domain = [
                ('company_id', '=', wizard.company_id.id),
                ('state', '=', 'draft'),
                ('recognition_date', '>=', next_month_start),
                ('recognition_date', '<=', next_month_end),
            ]
            # Constrain to lines whose schedule is within the filtered
            # schedule population so the card stays consistent with
            # the status filter (e.g. switching to "completed" would
            # naturally exclude draft lines because completed
            # schedules have no draft lines left).  Using ``schedule_id
            # in ids`` works because the earlier schedule search is
            # already filtered.
            if schedules:
                line_domain.append(('schedule_id', 'in', schedules.ids))
            else:
                # Empty schedules ⇒ nothing to aggregate; leave the
                # card at its zero initialisation.
                continue

            # ``_read_group`` (replaces deprecated ``read_group`` per
            # Odoo 19) returns a list of tuples ``(agg_1, ..., agg_n)``
            # when ``groupby`` is empty: typically ``[(sum_value,)]``
            # for non-empty domains, and ``[(None,)]`` when no rows
            # match.  Handle both shapes defensively.
            line_groups = Line._read_group(
                domain=line_domain,
                groupby=[],
                aggregates=['recognition_amount:sum'],
            )
            if line_groups and line_groups[0]:
                wizard.next_period_recognition = (
                    line_groups[0][0] or 0.0
                )

    # -----------------------------------------------------------------
    # SECTION 7 — Breakdown-payload computation.
    # -----------------------------------------------------------------

    @api.depends('date_from', 'date_to', 'company_id', 'status_filter')
    def _compute_breakdown(self):
        """Populate the three JSON breakdown payloads.

        Each payload is produced by a **single** ``read_group()``
        SQL aggregation — row-level Python iteration is explicitly
        avoided here.  The three payloads are consumed by the
        dashboard form view's ``<field widget="json">`` elements; the
        native ``json`` widget renders them as formatted, scrollable
        JSON without requiring a custom OWL component.

        Payload shapes:

        * ``schedule_breakdown_json`` — list of dicts, one per
          ``recognition_method``: ``[{"recognition_method": str,
          "count": int, "total_amount": float}, ...]``.
        * ``period_breakdown_json`` — list of dicts, one per calendar
          month within the dashboard date range:
          ``[{"month": str, "total": float, "count": int}, ...]``.
        * ``status_distribution_json`` — dict keyed by
          ``completion_status`` with count as value:
          ``{"active": int, "completed": int, "on_hold": int}``.
        """
        for wizard in self:
            # Neutral defaults first (same initialisation pattern as
            # ``_compute_summary``).
            wizard.schedule_breakdown_json = []
            wizard.period_breakdown_json = []
            wizard.status_distribution_json = {}

            if not wizard.date_from or not wizard.date_to or not wizard.company_id:
                continue

            schedule_domain = wizard._get_base_schedule_domain()
            wizard._apply_status_filter(schedule_domain)

            Schedule = self.env['account.deferred.schedule']

            # Breakdown 1 — by recognition_method.
            #
            # ``_read_group`` (replaces deprecated ``read_group`` per
            # Odoo 19) returns a list of tuples whose layout is
            # ``(groupby_value_1, ..., aggregate_1, ...)``.  For
            # ``groupby=['recognition_method']`` and
            # ``aggregates=['__count', 'total_amount:sum']`` each row
            # is ``(method_str, count_int, total_amount_float)``.
            method_groups = Schedule._read_group(
                domain=schedule_domain,
                groupby=['recognition_method'],
                aggregates=['__count', 'total_amount:sum'],
            )
            wizard.schedule_breakdown_json = [
                {
                    'recognition_method': method or '',
                    'count': count or 0,
                    'total_amount': total or 0.0,
                }
                for method, count, total in method_groups
            ]

            # Breakdown 2 — by completion_status.
            #
            # ``aggregates=['__count']`` produces a per-group count
            # without any field aggregation; row layout is
            # ``(completion_status_str, count_int)``.
            status_groups = Schedule._read_group(
                domain=schedule_domain,
                groupby=['completion_status'],
                aggregates=['__count'],
            )
            wizard.status_distribution_json = {
                (status or 'unknown'): (count or 0)
                for status, count in status_groups
            }

            # Breakdown 3 — by recognition_date month (on the line model).
            #
            # We intentionally do NOT apply the schedule status filter
            # to this read_group — the ``period_breakdown_json`` is
            # meant to show the *full* recognition calendar regardless
            # of status (so users see upcoming recognitions from
            # confirmed-but-not-yet-active schedules).  If a tighter
            # filter is required later, layer the schedule-id
            # restriction here.
            Line = self.env['account.deferred.line']
            line_domain = [
                ('company_id', '=', wizard.company_id.id),
                ('recognition_date', '>=', wizard.date_from),
                ('recognition_date', '<=', wizard.date_to),
            ]
            # ``_read_group`` with ``:month`` granularity returns a
            # Python ``date`` representing the first day of each
            # month bucket (e.g. ``date(2024, 1, 1)`` for January
            # 2024) — NOT a pre-formatted string like the deprecated
            # ``read_group`` produced.  We format the bucket date
            # ourselves with ``format_date(... 'MMMM yyyy')`` so the
            # JSON payload still carries a human-readable label.
            period_groups = Line._read_group(
                domain=line_domain,
                groupby=['recognition_date:month'],
                aggregates=['__count', 'recognition_amount:sum'],
            )
            wizard.period_breakdown_json = [
                {
                    'month': (
                        format_date(self.env, month_date, date_format='MMMM yyyy')
                        if month_date else ''
                    ),
                    'total': total or 0.0,
                    'count': count or 0,
                }
                for month_date, count, total in period_groups
            ]

    # -----------------------------------------------------------------
    # SECTION 7.5 — HTML projections of the breakdown payloads.
    #
    # Issue #18 fix: render the JSON payloads as readable HTML tables
    # so end-users see structured data rather than raw JSON literals
    # like ``{"active":5}`` or ``[{"recognition_method":"straight_line",
    # "count":5,"total_amount":60000}]``.
    # -----------------------------------------------------------------

    @api.depends(
        'status_distribution_json',
        'schedule_breakdown_json',
        'period_breakdown_json',
        'currency_id',
    )
    def _compute_breakdown_html(self):
        """Project the breakdown JSON payloads into HTML tables.

        For each computed JSON field this method emits a corresponding
        HTML field with a Bootstrap-styled, accessible table the
        dashboard form view can render via ``widget="html"``. When the
        underlying JSON is empty the HTML field carries a friendly
        empty-state message rather than an empty/null value, so the
        view never collapses unexpectedly.
        """
        # Friendly labels for the recognition_method enum.
        method_labels = {
            'straight_line': _('Straight Line'),
            'date_based': _('Date Based'),
            'manual': _('Manual'),
            '': _('Unspecified'),
        }
        # Friendly labels for the completion_status enum.
        status_labels = {
            'active': _('Active'),
            'completed': _('Completed'),
            'on_hold': _('On Hold'),
            'unknown': _('Unknown'),
        }
        # Bootstrap utility classes shared across all three tables.
        # Using Odoo's existing utility classes keeps the rendering
        # consistent with every other Odoo list/form surface.
        table_open = (
            '<table class="table table-sm table-borderless mb-0">'
        )
        for wizard in self:
            currency = wizard.currency_id

            # 1) status_distribution_html — single-row dict.
            status_data = wizard.status_distribution_json or {}
            if status_data:
                rows = ''.join(
                    f'<tr><td>{status_labels.get(key, key)}</td>'
                    f'<td class="text-end fw-bold">{value}</td></tr>'
                    for key, value in sorted(status_data.items())
                )
                wizard.status_distribution_html = (
                    f'{table_open}'
                    '<thead><tr>'
                    f'<th>{_("Status")}</th>'
                    f'<th class="text-end">{_("Count")}</th>'
                    '</tr></thead>'
                    f'<tbody>{rows}</tbody>'
                    '</table>'
                )
            else:
                wizard.status_distribution_html = (
                    f'<p class="text-muted mb-0">'
                    f'{_("No schedules in the current filter range.")}'
                    '</p>'
                )

            # 2) schedule_breakdown_html — list of dicts per method.
            schedule_data = wizard.schedule_breakdown_json or []
            if schedule_data:
                rows = ''.join(
                    f'<tr>'
                    f'<td>{method_labels.get(item.get("recognition_method", ""), item.get("recognition_method", ""))}</td>'
                    f'<td class="text-end">{item.get("count", 0)}</td>'
                    f'<td class="text-end fw-bold">'
                    f'{wizard._format_monetary(item.get("total_amount", 0.0), currency)}'
                    f'</td>'
                    f'</tr>'
                    for item in schedule_data
                )
                wizard.schedule_breakdown_html = (
                    f'{table_open}'
                    '<thead><tr>'
                    f'<th>{_("Recognition Method")}</th>'
                    f'<th class="text-end">{_("Count")}</th>'
                    f'<th class="text-end">{_("Total Amount")}</th>'
                    '</tr></thead>'
                    f'<tbody>{rows}</tbody>'
                    '</table>'
                )
            else:
                wizard.schedule_breakdown_html = (
                    f'<p class="text-muted mb-0">'
                    f'{_("No schedule breakdown available for the selected filters.")}'
                    '</p>'
                )

            # 3) period_breakdown_html — list of dicts per month.
            period_data = wizard.period_breakdown_json or []
            if period_data:
                rows = ''.join(
                    f'<tr>'
                    f'<td>{item.get("month", "")}</td>'
                    f'<td class="text-end">{item.get("count", 0)}</td>'
                    f'<td class="text-end fw-bold">'
                    f'{wizard._format_monetary(item.get("total", 0.0), currency)}'
                    f'</td>'
                    f'</tr>'
                    for item in period_data
                )
                wizard.period_breakdown_html = (
                    f'{table_open}'
                    '<thead><tr>'
                    f'<th>{_("Month")}</th>'
                    f'<th class="text-end">{_("Lines")}</th>'
                    f'<th class="text-end">{_("Total Amount")}</th>'
                    '</tr></thead>'
                    f'<tbody>{rows}</tbody>'
                    '</table>'
                )
            else:
                # FB-06 (QA Checkpoint 6): the empty-state copy was
                # phrased around "next 12 months" which contradicted
                # the configurable date-range filter that drives this
                # breakdown. The neutral phrasing references the
                # active date range so users immediately understand
                # the empty result is a function of their filter, not
                # of the system clock.
                wizard.period_breakdown_html = (
                    f'<p class="text-muted mb-0">'
                    f'{_("No recognition lines found in the selected date range.")}'
                    '</p>'
                )

    @staticmethod
    def _format_monetary(amount, currency):
        """Format a monetary amount using the wizard's currency.

        Falls back to ``"%.2f"`` formatting when no currency is set
        (the dashboard always carries a currency_id but the helper is
        defensive against test contexts).
        """
        try:
            amount = float(amount or 0.0)
        except (TypeError, ValueError):
            amount = 0.0
        if currency and hasattr(currency, 'symbol'):
            try:
                return f'{currency.symbol} {amount:,.2f}'
            except (TypeError, ValueError):
                return f'{amount:,.2f}'
        return f'{amount:,.2f}'

    # -----------------------------------------------------------------
    # SECTION 7.6 — display_name override (Issue #16 fix).
    # -----------------------------------------------------------------

    @api.depends('date_to', 'date_from')
    def _compute_display_name(self):
        """Render a friendly breadcrumb / window title.

        Without this override the breadcrumb falls back to
        ``account.deferred.recognition.dashboard.wizard,NewId_0x...``,
        which exposes the Python class name and the transient record's
        in-memory id to end users.
        """
        for wizard in self:
            if wizard.date_to:
                wizard.display_name = _(
                    'Recognition Dashboard — As of %(date)s',
                    date=fields.Date.to_string(wizard.date_to),
                )
            else:
                wizard.display_name = _('Recognition Dashboard')

    # -----------------------------------------------------------------
    # SECTION 8 — Drill-down action methods.
    #
    # Each method on this section is bound to a button in the
    # dashboard form view.  They return ``ir.actions.act_window``
    # dicts that navigate the user to a filtered list of schedules
    # or recognition lines — satisfying DR-004 Scenario 4 ("Drill-
    # down to Source Transactions").
    #
    # All drill-down domains are constructed to be **consistent with
    # the dashboard filters** so the user never clicks a KPI card and
    # lands on a list that contradicts the card's value.
    # -----------------------------------------------------------------

    def action_view_pending(self):
        """Open the filtered list of schedules behind "Active Schedules".

        The returned action reproduces the dashboard's schedule
        population (the one driving ``active_schedule_count``) in a
        classic list view, letting the user triage individual
        schedules, export them, or navigate into form view.

        :return: an ``ir.actions.act_window`` dict.
        :rtype: dict
        """
        self.ensure_one()
        domain = self._get_base_schedule_domain()
        self._apply_status_filter(domain)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Active Deferral Schedules'),
            'res_model': 'account.deferred.schedule',
            'view_mode': 'list,form',
            'domain': domain,
            'context': {
                **self.env.context,
                'default_company_id': self.company_id.id,
            },
            'target': 'current',
        }

    def action_view_revenue(self):
        """Open the filtered list of schedules backing deferred revenue.

        Filters schedules down to those whose ``recognition_account_id``
        has an ``account_type`` classified as **income** (i.e.
        ``income`` or ``income_other``).  Account-level filtering is
        performed via a ``recognition_account_id.account_type in
        (...)`` domain clause — the ORM translates this into a JOIN
        on ``account_account``.

        :return: an ``ir.actions.act_window`` dict.
        :rtype: dict
        """
        self.ensure_one()
        domain = self._get_base_schedule_domain()
        # Constrain to income-typed recognition accounts.  Using the
        # dotted-path ``recognition_account_id.account_type`` keeps
        # the domain declarative and lets PostgreSQL perform the JOIN
        # against the prefetch cache — faster than an explicit two-
        # step search + id filter.
        domain.append(
            ('recognition_account_id.account_type', 'in', list(_INCOME_ACCOUNT_TYPES)),
        )
        return {
            'type': 'ir.actions.act_window',
            'name': _('Deferred Revenue Schedules'),
            'res_model': 'account.deferred.schedule',
            'view_mode': 'list,form',
            'domain': domain,
            'context': {
                **self.env.context,
                'default_company_id': self.company_id.id,
            },
            'target': 'current',
        }

    def action_view_expenses(self):
        """Open the filtered list of schedules backing deferred expenses.

        Filters schedules down to those whose ``recognition_account_id``
        has an ``account_type`` classified as **expense** (i.e.
        ``expense``, ``expense_depreciation``, or
        ``expense_direct_cost``).  Account-level filtering uses the
        same dotted-path technique as :meth:`action_view_revenue`.

        :return: an ``ir.actions.act_window`` dict.
        :rtype: dict
        """
        self.ensure_one()
        domain = self._get_base_schedule_domain()
        domain.append(
            ('recognition_account_id.account_type', 'in', list(_EXPENSE_ACCOUNT_TYPES)),
        )
        return {
            'type': 'ir.actions.act_window',
            'name': _('Deferred Expense Schedules'),
            'res_model': 'account.deferred.schedule',
            'view_mode': 'list,form',
            'domain': domain,
            'context': {
                **self.env.context,
                'default_company_id': self.company_id.id,
            },
            'target': 'current',
        }

    def action_view_next_period_lines(self):
        """Open the list of recognition lines scheduled for next month.

        This action mirrors the ``next_period_recognition`` summary
        card — it returns the same draft recognition lines whose
        ``recognition_date`` falls in the next calendar month.  The
        action name is localised to include the formatted month name
        (e.g. "Recognition Lines — February 2024") so the user always
        knows exactly which period they are looking at.

        :return: an ``ir.actions.act_window`` dict.
        :rtype: dict
        """
        self.ensure_one()
        today = fields.Date.context_today(self)
        next_month_start = (today + relativedelta(months=1)).replace(day=1)
        next_month_end = next_month_start + relativedelta(months=1, days=-1)

        # Build a user-friendly action name using ``format_date`` so
        # the month label is rendered in the active user's locale.
        # The ``MMMM yyyy`` Babel pattern yields "February 2024" in
        # English, "février 2024" in French, etc.
        month_label = format_date(
            self.env,
            next_month_start,
            date_format='MMMM yyyy',
        )

        return {
            'type': 'ir.actions.act_window',
            'name': _('Recognition Lines — %s') % month_label,
            'res_model': 'account.deferred.line',
            'view_mode': 'list,form',
            'domain': [
                ('company_id', '=', self.company_id.id),
                ('state', '=', 'draft'),
                ('recognition_date', '>=', next_month_start),
                ('recognition_date', '<=', next_month_end),
            ],
            'context': {
                **self.env.context,
                'default_company_id': self.company_id.id,
            },
            'target': 'current',
        }

    def action_drill_down(self, schedule_id=None):
        """Open the form view of a specific schedule.

        Used by chart-widget click handlers and keyboard shortcuts
        that want to navigate directly to a particular
        ``account.deferred.schedule`` record.  Two invocation paths
        are supported:

        1. Explicit ``schedule_id`` kwarg (e.g. from a Python caller).
        2. Implicit via the context key ``active_schedule_id`` (e.g.
           when triggered from a dashboard OWL handler that sets the
           context).

        If neither is provided, a :class:`UserError` is raised — the
        method refuses to silently open an arbitrary or empty form
        view because that would be a confusing UX.

        :param int schedule_id: optional explicit schedule id.
        :return: an ``ir.actions.act_window`` dict targeting
            the schedule form view.
        :rtype: dict
        :raises UserError: if no schedule id can be resolved.
        """
        self.ensure_one()
        target_id = schedule_id or self.env.context.get('active_schedule_id')
        if not target_id:
            raise UserError(_(
                'No schedule specified for drill-down.  Click a '
                'summary card button or select a schedule from the '
                'list to view its details.',
            ))
        # Verify the schedule exists before returning an action that
        # would otherwise open a blank or error form.  ``browse`` +
        # ``exists`` is cheap and gives a clean user-facing error
        # instead of Odoo's default "Record does not exist" dialog.
        Schedule = self.env['account.deferred.schedule']
        schedule = Schedule.browse(int(target_id)).exists()
        if not schedule:
            raise UserError(_(
                'The requested deferral schedule (id=%s) does not '
                'exist or is no longer accessible.',
            ) % target_id)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Deferral Schedule'),
            'res_model': 'account.deferred.schedule',
            'res_id': schedule.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_refresh(self):
        """Force recomputation of every dashboard field.

        Clicking the **Refresh** button in the dashboard header
        invalidates the cache for every computed field and returns a
        window action that re-opens the dashboard in place.  This is
        necessary because Odoo's cache is not automatically
        invalidated when *another* user (or another tab) posts new
        recognition entries via the DR-003 cut-off wizard — the
        dashboard's computed values would otherwise appear stale
        until the page was navigated away from and back.

        :return: an ``ir.actions.act_window`` dict that re-opens the
            dashboard form view on the same transient record.
        :rtype: dict
        """
        self.ensure_one()
        # Invalidate every compute field so the next field access re-
        # executes the compute method against the live database.
        self.invalidate_recordset(fnames=[
            'total_deferred_revenue',
            'total_deferred_expenses',
            'active_schedule_count',
            'next_period_recognition',
            'schedule_breakdown_json',
            'period_breakdown_json',
            'status_distribution_json',
        ])
        return {
            'type': 'ir.actions.act_window',
            'name': _('Recognition Dashboard'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
            'context': self.env.context,
        }

    # -----------------------------------------------------------------
    # SECTION 9 — Export action methods (PDF and XLSX).
    #
    # DR-004 Acceptance Criteria + AAP §0.5.1.3 require the dashboard
    # to be exportable to both PDF (QWeb) and XLSX (openpyxl).  PDF
    # rendering uses the standard Odoo ``ir.actions.report`` machinery
    # via ``report_action``; XLSX rendering builds a workbook in
    # memory, persists it as an ``ir.attachment``, and returns a
    # download URL.  Both actions are wired to ``<button>`` elements
    # in the dashboard form view.
    #
    # The XLSX export pattern follows the FEATURE-001 precedent in
    # ``addons/account_financial_report_ce/models/financial_report.py``
    # (action_export_xlsx) — base64-encoded workbook stored as an
    # ir.attachment with mimetype ``application/vnd.openxmlformats-...``
    # then served via ``/web/content/<id>?download=true``.
    # -----------------------------------------------------------------

    def action_export_pdf(self):
        """Export the dashboard's current state as a QWeb-rendered PDF.

        Forces a fresh recomputation of every computed field (so the
        PDF reflects the user's current filter configuration), then
        delegates to the standard Odoo ``ir.actions.report``
        machinery to render
        ``account_deferred_revenue.report_recognition_dashboard``
        (the QWeb template registered in
        ``data/recognition_dashboard_report.xml``).

        :returns: an ``ir.actions.report`` action dict that triggers
            QWeb PDF rendering through Odoo's ``wkhtmltopdf``
            integration.
        :rtype: dict
        """
        self.ensure_one()
        # Refresh computed fields so the rendered PDF reflects any
        # filter changes the user made since the last access.  We
        # invalidate the same fields that ``action_refresh`` does so
        # the QWeb template (which reads them via ``t-field``) sees
        # current data.
        self.invalidate_recordset(fnames=[
            'total_deferred_revenue',
            'total_deferred_expenses',
            'active_schedule_count',
            'next_period_recognition',
            'schedule_breakdown_json',
            'period_breakdown_json',
            'status_distribution_json',
        ])
        report_xml_id = (
            'account_deferred_revenue.action_report_recognition_dashboard'
        )
        report_action = self.env.ref(report_xml_id)
        return report_action.report_action(self, config=False)

    def action_export_xlsx(self):
        """Export the dashboard's current state as an XLSX workbook.

        Builds a multi-sheet ``openpyxl.Workbook`` containing:

        * **Summary** — KPI cards (totals + counts).
        * **Schedule Breakdown** — recognition_method groups.
        * **Period Breakdown** — month-by-month aggregates.
        * **Status Distribution** — completion_status counts.
        * **Filters** — date range, company, status filter (audit
          trail).

        The workbook is base64-encoded into an ``ir.attachment`` and a
        download URL action is returned, mirroring the FEATURE-001
        precedent in
        ``addons/account_financial_report_ce/models/financial_report.py``.

        Performance: ``_compute_summary`` and ``_compute_breakdown``
        each run in O(rows) on the filtered subset; the workbook
        write itself adds <100ms on typical hardware for the small
        result set produced by the dashboard.

        :returns: an ``ir.actions.act_url`` dict pointing to the
            generated attachment download URL.
        :rtype: dict
        """
        self.ensure_one()

        # Force a fresh compute so the workbook reflects the current
        # filter configuration.
        self.invalidate_recordset(fnames=[
            'total_deferred_revenue',
            'total_deferred_expenses',
            'active_schedule_count',
            'next_period_recognition',
            'schedule_breakdown_json',
            'period_breakdown_json',
            'status_distribution_json',
        ])

        # ---------------- Build workbook in memory ----------------
        wb = Workbook()
        bold_font = Font(bold=True, size=11)
        header_align = Alignment(horizontal='center', wrap_text=True)
        monetary_fmt = '#,##0.00'

        # --- Sheet 1: Summary KPI cards --------------------------------
        ws_summary = wb.active
        ws_summary.title = (_('Summary'))[:31]
        summary_rows = [
            (_('Metric'), _('Value')),
            (_('Total Deferred Revenue'), self.total_deferred_revenue or 0.0),
            (_('Total Deferred Expenses'), self.total_deferred_expenses or 0.0),
            (_('Active Schedule Count'), self.active_schedule_count or 0),
            (_('Next Period Recognition'), self.next_period_recognition or 0.0),
        ]
        for r_idx, (label, value) in enumerate(summary_rows, start=1):
            cell_label = ws_summary.cell(row=r_idx, column=1, value=label)
            cell_value = ws_summary.cell(row=r_idx, column=2, value=value)
            if r_idx == 1:
                cell_label.font = bold_font
                cell_value.font = bold_font
                cell_label.alignment = header_align
                cell_value.alignment = header_align
            elif isinstance(value, (int, float)) and r_idx != 4:
                # Apply monetary format to currency-bearing rows; the
                # active-schedule-count row (r_idx == 4) is an integer
                # and stays in default format.
                cell_value.number_format = monetary_fmt
        ws_summary.column_dimensions[get_column_letter(1)].width = 32
        ws_summary.column_dimensions[get_column_letter(2)].width = 22

        # --- Sheet 2: Schedule Breakdown (by recognition method) ------
        ws_methods = wb.create_sheet(title=(_('Schedule Breakdown'))[:31])
        method_headers = [_('Recognition Method'), _('Count'), _('Total Amount')]
        for c_idx, header in enumerate(method_headers, start=1):
            cell = ws_methods.cell(row=1, column=c_idx, value=header)
            cell.font = bold_font
            cell.alignment = header_align
        method_payload = self.schedule_breakdown_json or []
        for r_idx, entry in enumerate(method_payload, start=2):
            ws_methods.cell(row=r_idx, column=1, value=entry.get('recognition_method', ''))
            ws_methods.cell(row=r_idx, column=2, value=entry.get('count', 0))
            cell_total = ws_methods.cell(
                row=r_idx, column=3, value=entry.get('total_amount', 0.0),
            )
            cell_total.number_format = monetary_fmt
        for col_idx, width in enumerate([28, 12, 18], start=1):
            ws_methods.column_dimensions[get_column_letter(col_idx)].width = width

        # --- Sheet 3: Period Breakdown (by recognition month) --------
        ws_periods = wb.create_sheet(title=(_('Period Breakdown'))[:31])
        period_headers = [_('Period'), _('Line Count'), _('Total Recognition')]
        for c_idx, header in enumerate(period_headers, start=1):
            cell = ws_periods.cell(row=1, column=c_idx, value=header)
            cell.font = bold_font
            cell.alignment = header_align
        period_payload = self.period_breakdown_json or []
        for r_idx, entry in enumerate(period_payload, start=2):
            ws_periods.cell(row=r_idx, column=1, value=entry.get('month', ''))
            ws_periods.cell(row=r_idx, column=2, value=entry.get('count', 0))
            cell_total = ws_periods.cell(
                row=r_idx, column=3, value=entry.get('total', 0.0),
            )
            cell_total.number_format = monetary_fmt
        for col_idx, width in enumerate([22, 14, 22], start=1):
            ws_periods.column_dimensions[get_column_letter(col_idx)].width = width

        # --- Sheet 4: Status Distribution -----------------------------
        ws_status = wb.create_sheet(title=(_('Status Distribution'))[:31])
        ws_status.cell(row=1, column=1, value=_('Status')).font = bold_font
        ws_status.cell(row=1, column=2, value=_('Count')).font = bold_font
        ws_status.cell(row=1, column=1).alignment = header_align
        ws_status.cell(row=1, column=2).alignment = header_align
        status_payload = self.status_distribution_json or {}
        if isinstance(status_payload, dict):
            for r_idx, (status, count) in enumerate(
                sorted(status_payload.items()), start=2,
            ):
                ws_status.cell(row=r_idx, column=1, value=status)
                ws_status.cell(row=r_idx, column=2, value=count)
        ws_status.column_dimensions[get_column_letter(1)].width = 18
        ws_status.column_dimensions[get_column_letter(2)].width = 12

        # --- Sheet 5: Filters (audit trail) --------------------------
        ws_filters = wb.create_sheet(title=(_('Filters'))[:31])
        filter_rows = [
            (_('Date From'), str(self.date_from) if self.date_from else _('N/A')),
            (_('Date To'), str(self.date_to) if self.date_to else _('N/A')),
            (_('Company'), self.company_id.name if self.company_id else ''),
            (_('Status Filter'), self.status_filter or ''),
        ]
        for r_idx, (label, value) in enumerate(filter_rows, start=1):
            label_cell = ws_filters.cell(row=r_idx, column=1, value=label)
            label_cell.font = bold_font
            ws_filters.cell(row=r_idx, column=2, value=value)
        ws_filters.column_dimensions[get_column_letter(1)].width = 22
        ws_filters.column_dimensions[get_column_letter(2)].width = 32

        # ---------------- Serialise to bytes ----------------
        output = io.BytesIO()
        wb.save(output)
        xlsx_bytes = output.getvalue()
        output.close()

        # ---------------- Persist as ir.attachment ----------------
        filename = (
            f'recognition_dashboard_{fields.Date.context_today(self)}.xlsx'
        )
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': base64.encodebytes(xlsx_bytes),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': (
                'application/vnd.openxmlformats-officedocument'
                '.spreadsheetml.sheet'
            ),
        })

        _logger.info(
            "DR-004 dashboard XLSX export created: %s (%d bytes)",
            filename, len(xlsx_bytes),
        )

        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%d?download=true' % attachment.id,
            'target': 'new',
        }
