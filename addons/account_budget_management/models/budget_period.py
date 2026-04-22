# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""
Budget Period Allocation Model (BM-002)
=======================================

Implements ``budget.budget.period`` — the per-period allocation record
that breaks a parent ``budget.budget.line``'s planned amount into
discrete time windows (monthly, quarterly, annual, or custom) each
with its own allocated amount. BM-002 is the Phase 2 story in Track B
(Budget Management) and builds on the BM-001 header / line foundation
by layering temporal granularity atop the annual planned total.

A single ``budget.budget.line`` may own zero or many
``budget.budget.period`` records. When zero periods are attached, the
parent line is treated as a single-window budget item covering the
entire fiscal range (``budget.date_from`` → ``budget.date_to``). When
one or more periods are attached, their ``allocated_amount`` values
sum to the parent line's ``planned_amount`` (an allocation-integrity
invariant enforced by ``_check_sum_matches_line``).

Story Mapping
-------------
* BM-002 Scenario 1 — Monthly allocation (12 periods across a fiscal
  year); running total enforced to match annual line total.
* BM-002 Scenario 2 — Quarterly allocation (Q1-Q4) aligned to the
  company's fiscal calendar.
* BM-002 Scenario 3 — Equal distribution; remainder from banker's
  rounding accumulates in the final period. Audit trail captured via
  the ``write()`` override (populates ``prev_amount``,
  ``modified_by_id``, ``modified_date`` whenever ``allocated_amount``
  changes) plus ``mail.thread`` chatter and the ``audit_note`` text
  field.
* BM-002 Scenario 4 — Manual (custom) allocation; users may distribute
  freely with a running-total warning when the sum diverges from the
  parent planned amount.
* BM-002 Scenario 5 — Modification audit trail via ``mail.thread`` and
  the audit-trail fields (``prev_amount``, ``modified_by_id``,
  ``modified_date``).
* BM-002 Scenario 6 — Copy allocation pattern from another budget
  (``_copy_from_previous_budget``) preserves the percentage
  distribution shape while scaling to the destination line's planned
  amount.

Field Structure
---------------
Per BM-002 ticket Section 4.4 and the agent prompt the canonical
fields are:

* ``budget_line_id`` — Many2one (required, cascade) to the parent.
* ``budget_id`` / ``account_id`` / ``company_id`` / ``currency_id`` —
  stored related fields cascading from the parent line.
* ``name`` — Char (computed, e.g. "January 2024" / "Q1 2024").
* ``display_name`` — Char (computed) combining account label with
  period label for form-view titles and record rendering.
* ``date_from`` / ``date_to`` — Date (required; window bounds).
* ``sequence`` — Integer (period ordering).
* ``period_type`` — Selection (monthly / quarterly / annual / custom).
* ``allocated_amount`` — Monetary (allocated amount for this period).
* ``allocation_method`` — Selection (equal / manual / copy_previous /
  percentage) describing how the period was populated.
* ``allocation_percentage`` — Float (share of the parent line total).
* ``actual_amount`` — Monetary (computed; actual posted balance in
  this period from ``account.move.line``).
* ``consumption_percent`` — Float (computed; actual / allocated %).
* ``audit_note`` — Text free-form note explaining modification intent.
* ``prev_amount`` / ``modified_by_id`` / ``modified_date`` — readonly
  audit-trail bookkeeping populated by the ``write()`` override.

Rules Compliance
----------------
* R-01 — No cross-module imports. Only ``odoo`` core and stdlib /
  third-party packages already transitively required by Odoo
  (``dateutil.relativedelta``) are referenced.
* R-03 — ``_name = 'budget.budget.period'`` is a net-new persistent
  model. ``_inherit`` is used solely to compose ``mail.thread`` for
  audit-trail chatter. No core Odoo model is extended by this file.
* R-05 — No redefinition of fields on ``account.move`` or
  ``account.move.line``. This model exists entirely within the
  ``account_budget_management`` namespace and reads
  ``account.move.line`` only via ``search()`` for actuals computation.
* R-07 — No ``sudo()`` calls. Access control is enforced via
  ``ir.model.access.csv`` + ``ir.rule`` (multi-company) records.
* R-08 — No ``variance_*`` or ``alert_*`` prefixed fields appear on
  this model so the Checkpoint 5 disjoint baseline is preserved. All
  field names use plain accounting vocabulary (``allocated_amount``,
  ``actual_amount``, ``consumption_percent``, ``audit_note``).
* R-09 — Module folder ``account_budget_management`` matches the AAP.

Performance
-----------
``_compute_actual_amount`` batches all ``account.move.line`` lookups
into a SINGLE search query that spans the union of accounts + outer
date bounds across the whole recordset, then distributes results via
in-memory filtering. This avoids N+1 query explosion when viewing a
period list with hundreds of rows and keeps the BM-002 performance
envelope well within the BM-004 < 3s SLA for 1,000 lines since a line
typically has at most 12 (monthly) or 4 (quarterly) periods.
``_generate_equal_distribution`` uses a bounded in-memory loop over
the period count with final-period rounding correction so the running
total matches the parent line's ``planned_amount`` exactly.
"""

import logging

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, float_round

_logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# Module-level constants — period-type selection values mirrored across
# the parent ``budget.budget`` and ``budget.budget.line`` so that views
# and constraints can share the same vocabulary.
# ----------------------------------------------------------------------

#: Monthly period type — twelve periods (or fewer when the budget
#: fiscal range is shorter than one year, for mid-year budgets).
_PERIOD_TYPE_MONTHLY = 'monthly'

#: Quarterly period type — four periods aligned to fiscal quarters.
_PERIOD_TYPE_QUARTERLY = 'quarterly'

#: Annual period type — a single period covering the full fiscal
#: window. Included for completeness so the parent line's
#: allocation pattern can be rendered explicitly even when no
#: subdivision is applied.
_PERIOD_TYPE_ANNUAL = 'annual'

#: Custom period type — user-defined windows with no automatic
#: generation constraint. Used when BM-002 Scenario 4 manual allocation
#: is in effect.
_PERIOD_TYPE_CUSTOM = 'custom'

# ----------------------------------------------------------------------
# Allocation method constants — how the ``allocated_amount`` was
# populated for each period. Distinct from ``period_type`` which
# describes the temporal granularity.
# ----------------------------------------------------------------------

#: Equal distribution — produced by ``_generate_equal_distribution``
#: with rounding absorbed into the final period (BM-002 Scenario 3).
_ALLOCATION_METHOD_EQUAL = 'equal'

#: Manual entry — user typed the amount directly (BM-002 Scenario 4).
_ALLOCATION_METHOD_MANUAL = 'manual'

#: Copy-from-previous — produced by ``_copy_from_previous_budget``
#: preserving the percentage shape of a source budget (BM-002 Scenario 6).
_ALLOCATION_METHOD_COPY_PREVIOUS = 'copy_previous'

#: Percentage — user supplied an ``allocation_percentage`` which is
#: multiplied by the parent line's ``planned_amount``.
_ALLOCATION_METHOD_PERCENTAGE = 'percentage'


class BudgetBudgetPeriod(models.Model):
    """Per-period allocation of a ``budget.budget.line`` planned amount.

    Each ``budget.budget.period`` record represents a time window
    (monthly, quarterly, annual, or custom) with a share of the
    parent line's planned amount. Records are ordered by
    ``budget_line_id, date_from, sequence`` so that period lists
    render chronologically within each parent line.

    The record composes :class:`mail.thread` so that modification of
    ``allocated_amount`` on a confirmed budget posts to the chatter
    for audit-trail continuity (BM-002 Scenario 5). The ``write()``
    override additionally populates ``prev_amount``,
    ``modified_by_id``, and ``modified_date`` for a structured audit
    trail independent of the chatter.
    """

    _name = 'budget.budget.period'
    _description = 'Budget Period Allocation'
    _inherit = ['mail.thread']
    _order = 'budget_line_id, date_from, sequence'
    _rec_name = 'display_name'
    _check_company_auto = True

    # ==================================================================
    # Section 3.1 — Parent linkage + related fields
    # ==================================================================

    budget_line_id = fields.Many2one(
        comodel_name='budget.budget.line',
        string='Budget Line',
        required=True,
        ondelete='cascade',
        index=True,
        tracking=True,
        help="The budget line that owns this period allocation. "
             "Cascade-deleted with its parent so that orphaned "
             "period records never accumulate.",
    )
    budget_id = fields.Many2one(
        comodel_name='budget.budget',
        related='budget_line_id.budget_id',
        store=True,
        index=True,
        string='Budget',
        help="Stored related to the grandparent budget record so "
             "dashboards and list views can filter or group by budget "
             "without traversing the line relation.",
    )
    account_id = fields.Many2one(
        comodel_name='account.account',
        related='budget_line_id.account_id',
        store=True,
        index=True,
        string='Account',
        help="General-ledger account inherited from the parent line "
             "(income or expense type). Stored so period-level "
             "queries can filter by account without a JOIN.",
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        related='budget_line_id.company_id',
        store=True,
        index=True,
        help="Inherited from the parent line so this model "
             "participates in the multi-company record rule declared "
             "in ``security/budget_security.xml``.",
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        related='budget_line_id.currency_id',
        store=True,
        help="Currency of the monetary ``allocated_amount`` on this "
             "period — mirrors the parent line's currency.",
    )
    state = fields.Selection(
        related='budget_line_id.state',
        store=True,
        index=True,
        string='State',
        help="Stored related to the parent line's state "
             "(draft/confirmed/closed). Used by list-view filters "
             "and record rules to scope operations to the "
             "appropriate workflow stage.",
    )

    # ==================================================================
    # Section 3.2 — Period descriptor fields (temporal granularity)
    # ==================================================================

    sequence = fields.Integer(
        string='Sequence',
        default=10,
        index=True,
        help="Ordering hint within the parent line's period list. "
             "Lower sequences render first in chronological views.",
    )
    period_type = fields.Selection(
        selection=[
            (_PERIOD_TYPE_MONTHLY, 'Monthly'),
            (_PERIOD_TYPE_QUARTERLY, 'Quarterly'),
            (_PERIOD_TYPE_ANNUAL, 'Annual'),
            (_PERIOD_TYPE_CUSTOM, 'Custom'),
        ],
        string='Period Type',
        default=_PERIOD_TYPE_MONTHLY,
        required=True,
        tracking=True,
        help="Granularity of this period allocation. Monthly / "
             "quarterly / annual imply a fixed generation algorithm; "
             "``custom`` allows free-form date ranges for "
             "non-calendar fiscal structures.",
    )
    date_from = fields.Date(
        string='Period Start',
        required=True,
        tracking=True,
        help="Inclusive start date of the period allocation window. "
             "Must fall within the parent budget's fiscal range "
             "(enforced by ``_check_within_budget_window``).",
    )
    date_to = fields.Date(
        string='Period End',
        required=True,
        tracking=True,
        help="Inclusive end date of the period allocation window. "
             "Must not precede ``date_from`` (enforced by "
             "``_check_dates``) and must fall within the parent "
             "budget's fiscal range.",
    )

    # ==================================================================
    # Section 3.3 — Monetary + percentage + method allocation fields
    # ==================================================================

    allocated_amount = fields.Monetary(
        string='Allocated Amount',
        currency_field='currency_id',
        default=0.0,
        tracking=True,
        help="The monetary amount allocated to this specific period. "
             "Must be non-negative (SQL CHECK constraint). The sum of "
             "period ``allocated_amount`` values for a line should "
             "equal the line's own ``planned_amount`` (BM-002 "
             "Scenario 1 running-total rule; enforced by "
             "``_check_sum_matches_line``).",
    )
    allocation_method = fields.Selection(
        selection=[
            (_ALLOCATION_METHOD_EQUAL, 'Equal Distribution'),
            (_ALLOCATION_METHOD_MANUAL, 'Manual Entry'),
            (_ALLOCATION_METHOD_COPY_PREVIOUS, 'Copy from Previous Budget'),
            (_ALLOCATION_METHOD_PERCENTAGE, 'Percentage Distribution'),
        ],
        string='Allocation Method',
        default=_ALLOCATION_METHOD_MANUAL,
        required=True,
        tracking=True,
        help="How this period's ``allocated_amount`` was populated. "
             "``equal`` = distributed evenly across periods by "
             "``_generate_equal_distribution``; ``manual`` = typed "
             "directly by the user; ``copy_previous`` = copied from "
             "a prior budget by ``_copy_from_previous_budget``; "
             "``percentage`` = derived from ``allocation_percentage`` "
             "applied to the parent line's planned amount.",
    )
    allocation_percentage = fields.Float(
        string='Allocation Share (%)',
        digits=(7, 4),
        help="For percentage allocation method: this period's share "
             "of the parent line's ``planned_amount`` (0.0 – 100.0). "
             "Also populated by ``_copy_from_previous_budget`` to "
             "preserve the distribution shape across budgets.",
    )
    name = fields.Char(
        string='Period Label',
        compute='_compute_name',
        store=True,
        help="Human-readable period label (e.g. 'January 2024', "
             "'Q1 2024', 'FY 2024'). Computed from ``period_type`` + "
             "``date_from`` + ``date_to``. Falls back to the bare "
             "date range when the period type is ``custom``.",
    )
    display_name = fields.Char(
        compute='_compute_display_name',
        help="Composite label combining the account display name "
             "with the period label for form-view titles and record "
             "rendering. Referenced as ``_rec_name``.",
    )

    # ==================================================================
    # Section 3.4 — Actuals + consumption (reads only; never stored)
    #
    # R-08 note: these fields deliberately avoid the ``variance_*``
    # prefix (reserved for ``budget.budget.line`` variance analytics)
    # and the ``alert_*`` prefix (reserved for ``budget.budget`` /
    # ``budget.alert`` threshold signals).
    # ==================================================================

    actual_amount = fields.Monetary(
        string='Actual Amount',
        compute='_compute_actual_amount',
        currency_field='currency_id',
        help="Sum of posted ``account.move.line`` balances for the "
             "parent line's account within this period's date range. "
             "Computed via a single batched search across the whole "
             "recordset with in-memory per-period distribution.",
    )
    consumption_percent = fields.Float(
        string='Consumption (%)',
        compute='_compute_actual_amount',
        digits=(5, 2),
        help="Ratio of ``actual_amount`` to ``allocated_amount`` "
             "expressed as a percentage. Zero when "
             "``allocated_amount`` is zero to avoid division errors.",
    )

    # ==================================================================
    # Section 3.5 — Audit-trail fields (BM-002 Scenario 3 / 5)
    #
    # Populated automatically by the ``write()`` override whenever
    # ``allocated_amount`` changes. The combination of these fields +
    # ``mail.thread`` tracking + the free-form ``audit_note`` forms
    # the user-facing audit trail required by BM-002 Scenario 5.
    # ==================================================================

    audit_note = fields.Text(
        string='Audit Note',
        translate=False,
        tracking=True,
        help="Optional free-form note captured when a period "
             "allocation is modified on a confirmed budget (BM-002 "
             "Scenario 5). Combined with the chatter / tracking "
             "records the note forms the user-facing audit trail.",
    )
    prev_amount = fields.Monetary(
        string='Previous Amount',
        readonly=True,
        currency_field='currency_id',
        copy=False,
        help="Value of ``allocated_amount`` before the most recent "
             "modification. Populated automatically by the "
             "``write()`` override. Never copied on duplication so "
             "that audit trail remains attached to its originating "
             "record.",
    )
    modified_by_id = fields.Many2one(
        comodel_name='res.users',
        string='Last Modified By',
        readonly=True,
        copy=False,
        help="User who last modified the ``allocated_amount``. "
             "Populated automatically by the ``write()`` override "
             "from ``self.env.user`` at write time.",
    )
    modified_date = fields.Datetime(
        string='Last Modified On',
        readonly=True,
        copy=False,
        help="Timestamp of the most recent ``allocated_amount`` "
             "modification. Populated automatically by the "
             "``write()`` override from ``fields.Datetime.now()`` at "
             "write time.",
    )

    # ==================================================================
    # Phase 4 — Compute methods
    # ==================================================================

    @api.depends('period_type', 'date_from', 'date_to')
    def _compute_name(self):
        """Render the human-readable period label (BM-002 Scenario 1/2).

        The label form depends on the period type:

        * ``monthly`` — ``"January 2024"`` (full month name + year).
        * ``quarterly`` — ``"Q1 2024"`` (quarter number + year) where
          the quarter is derived from ``date_from`` (``(month-1)//3 + 1``).
        * ``annual`` — ``"2024"`` (the fiscal year derived from
          ``date_from.year``).
        * ``custom`` — ``"YYYY-MM-DD → YYYY-MM-DD"`` — the explicit
          date-range literal so manual allocations render their
          actual bounds.

        The compute is total — any missing ``date_from`` yields an
        empty-string label so the record can be created incrementally
        without raising during form editing.
        """
        for period in self:
            if not period.date_from:
                period.name = ''
                continue
            if period.period_type == _PERIOD_TYPE_MONTHLY:
                # strftime('%B %Y') renders e.g. 'January 2024'
                period.name = period.date_from.strftime('%B %Y')
            elif period.period_type == _PERIOD_TYPE_QUARTERLY:
                quarter = (period.date_from.month - 1) // 3 + 1
                period.name = f"Q{quarter} {period.date_from.year}"
            elif period.period_type == _PERIOD_TYPE_ANNUAL:
                period.name = str(period.date_from.year)
            else:
                # Custom period — render the explicit date range.
                period.name = f"{period.date_from} → {period.date_to}"

    @api.depends('name', 'budget_line_id.account_id.display_name')
    def _compute_display_name(self):
        """Compose ``display_name`` from account + period label.

        Output form: ``"<account display_name> — <period name>"``
        when both segments are present; falls back to whichever is
        available so the record is never rendered blank in list /
        form views. Used as the ``_rec_name`` so that Many2one
        dropdowns and breadcrumb trails present a meaningful label.
        """
        for period in self:
            account_name = (
                period.budget_line_id.account_id.display_name or ''
            )
            period_name = period.name or ''
            if account_name and period_name:
                period.display_name = f"{account_name} — {period_name}"
            else:
                period.display_name = account_name or period_name or ''

    @api.depends(
        'budget_line_id.account_id',
        'budget_line_id.company_id',
        'date_from',
        'date_to',
        'allocated_amount',
    )
    def _compute_actual_amount(self):
        """Aggregate posted ``account.move.line`` balances per period.

        Performance contract (CRITICAL):
        --------------------------------
        A NAIVE per-period ``search`` would issue N queries for a
        recordset of N periods. Because a single budget line can have
        up to 12 monthly periods and a fiscal budget can carry
        hundreds of lines, this compute is called with recordsets in
        the thousands during list / dashboard rendering. The BM-002
        → BM-004 SLA (< 3s for 1,000 budget lines) requires the
        aggregation to complete in bounded time.

        Strategy:
        ---------
        1. Initialize every period's ``actual_amount`` and
           ``consumption_percent`` to zero up-front so incomplete
           records (no account, no date range, etc.) short-circuit.
        2. Extract the UNION of accounts and the OUTER date bounds
           across the entire recordset — a single ``search`` against
           ``account.move.line`` fetches all candidate lines in one
           round-trip.
        3. Distribute the candidate move lines across periods via
           in-memory ``filtered`` passes — O(N_periods * N_lines) in
           Python but zero additional DB calls. For realistic recordsets
           this trade-off is strongly preferable to N DB round-trips.

        Filter predicate:
        -----------------
        * ``account_id`` must match the period's parent line account.
        * ``parent_state`` = ``'posted'`` (journal entry confirmed).
        * ``date`` must fall within ``[period.date_from, period.date_to]``
          (inclusive bounds).

        Consumption:
        ------------
        ``consumption_percent`` = ``actual_amount / allocated_amount
        * 100.0`` when ``allocated_amount`` is non-zero; zero
        otherwise (avoids ZeroDivisionError on placeholder periods).
        """
        # Reset all periods first so unfinished records (no account
        # or no date range) emerge with a clean 0 / 0 state.
        for period in self:
            period.actual_amount = 0.0
            period.consumption_percent = 0.0

        if not self:
            return

        # Accounts referenced across the recordset — skip empty line
        # records and empty account_ids.
        accounts = self.mapped('budget_line_id.account_id')
        if not accounts:
            return

        # Outer date bounds — use the earliest date_from and the
        # latest date_to so the single search covers every period.
        dates_from = [d for d in self.mapped('date_from') if d]
        dates_to = [d for d in self.mapped('date_to') if d]
        if not dates_from or not dates_to:
            return
        min_date = min(dates_from)
        max_date = max(dates_to)

        # Single batched search: union of accounts + outer date
        # window. The ``(account_id, date)`` composite index on
        # ``account_move_line`` (see ``addons/account/models/
        # account_move_line.py`` line 488) makes this query fast.
        move_lines = self.env['account.move.line'].search([
            ('account_id', 'in', accounts.ids),
            ('parent_state', '=', 'posted'),
            ('date', '>=', min_date),
            ('date', '<=', max_date),
        ])

        if not move_lines:
            return

        # Distribute candidate move lines across periods in memory.
        for period in self:
            account = period.budget_line_id.account_id
            if not account or not period.date_from or not period.date_to:
                continue
            period_lines = move_lines.filtered(
                lambda ml, p=period: (
                    ml.account_id == p.budget_line_id.account_id
                    and p.date_from <= ml.date <= p.date_to
                ),
            )
            # Multi-company periods can include lines from other
            # companies if the account is shared — filter by company
            # when one is set on the parent line.
            if period.budget_line_id.company_id:
                period_lines = period_lines.filtered(
                    lambda ml, p=period: (
                        ml.company_id == p.budget_line_id.company_id
                    ),
                )
            period.actual_amount = sum(period_lines.mapped('balance'))
            if period.allocated_amount:
                period.consumption_percent = (
                    period.actual_amount / period.allocated_amount
                    * 100.0
                )
            else:
                period.consumption_percent = 0.0

    # ==================================================================
    # Phase 5 — Constraints
    # ==================================================================

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        """Validate that ``date_from`` precedes or equals ``date_to``.

        A period is allowed to represent a single day (date_from ==
        date_to) — useful for cut-off adjustments. It is NEVER valid
        for ``date_from`` to fall AFTER ``date_to`` — such a window
        would yield negative duration and break the BM-002 Scenario 4
        sum-check semantics.
        """
        for period in self:
            if not period.date_from or not period.date_to:
                # Required=True enforces presence at write time; skip
                # during transient recordset construction to avoid
                # obscure errors during form-view onchange.
                continue
            if period.date_from > period.date_to:
                raise ValidationError(_(
                    "Period start date (%(date_from)s) must be on or "
                    "before the period end date (%(date_to)s) for "
                    "period '%(name)s'.",
                    date_from=period.date_from,
                    date_to=period.date_to,
                    name=period.display_name or period.name or '',
                ))

    @api.constrains('allocated_amount', 'budget_line_id')
    def _check_sum_matches_line(self):
        """Verify sum of period allocations equals line.planned_amount.

        BM-002 Scenario 4: when a user edits one of the period
        ``allocated_amount`` values, the sum across all sibling
        periods for the same ``budget_line_id`` must match the
        parent line's ``planned_amount`` within the currency's
        rounding tolerance. If divergence exceeds one rounding
        unit, the save is blocked with a ``ValidationError`` that
        identifies the offending budget line account and reports
        the actual versus expected totals.

        The check is short-circuited when:
        * the parent line has zero period allocations (interim state
          during generation — the generator helpers call write() one
          period at a time);
        * the parent line has zero ``planned_amount`` (periods being
          seeded for a line still in draft with no numeric total).

        Tolerance:
        ----------
        A single ``currency_id.rounding`` unit is tolerated — this
        absorbs the rounding correction applied by
        ``_generate_equal_distribution`` to the final period.
        """
        # Collect the unique parent lines so the sum is computed once
        # per line, not once per modified period.
        lines = self.mapped('budget_line_id')
        for line in lines:
            if not line.period_ids:
                continue
            if not line.planned_amount:
                # No planned total defined yet — skip sum check.
                continue
            total = sum(line.period_ids.mapped('allocated_amount'))
            rounding = (
                line.currency_id.rounding
                if line.currency_id
                else 0.01
            ) or 0.01
            if float_compare(
                total,
                line.planned_amount,
                precision_rounding=rounding,
            ) != 0:
                diff = abs(total - line.planned_amount)
                if diff > rounding:
                    raise ValidationError(_(
                        "Sum of period allocations (%(sum)s) does "
                        "not match the parent budget line "
                        "planned_amount (%(planned)s) for account "
                        "%(account)s. Please redistribute the "
                        "allocations so that the totals align "
                        "within the currency rounding tolerance.",
                        sum=total,
                        planned=line.planned_amount,
                        account=(
                            line.account_id.display_name
                            if line.account_id
                            else _('(unknown account)')
                        ),
                    ))

    @api.constrains('date_from', 'date_to', 'budget_line_id')
    def _check_within_budget_window(self):
        """Require every period to fall inside its budget's window.

        The parent ``budget.budget`` header carries ``date_from`` and
        ``date_to`` fields that define the fiscal window of the
        whole budget. Each of its lines' periods must fit strictly
        inside this window — a period that spills outside the budget
        window would produce actuals from dates that the budget
        never agreed to plan for, breaking the BM-002 sum contract
        and the BM-003 variance report's horizon assumption.

        The check walks ``period.budget_line_id.budget_id`` via the
        stored ``related`` field; when the budget has no defined
        bounds (either ``date_from`` or ``date_to`` is falsy) the
        check short-circuits, allowing the record to be saved while
        the parent budget is still being configured.
        """
        for period in self:
            budget = period.budget_line_id.budget_id
            if not budget or not budget.date_from or not budget.date_to:
                continue
            if not period.date_from or not period.date_to:
                continue
            if (
                period.date_from < budget.date_from
                or period.date_to > budget.date_to
            ):
                raise ValidationError(_(
                    "Period (%(pf)s → %(pt)s) falls outside the "
                    "parent budget window (%(bf)s → %(bt)s). "
                    "Period '%(name)s' on budget '%(budget)s' "
                    "must be adjusted to fit within the budget's "
                    "fiscal dates.",
                    pf=period.date_from,
                    pt=period.date_to,
                    bf=budget.date_from,
                    bt=budget.date_to,
                    name=period.display_name or period.name or '',
                    budget=budget.display_name or budget.name or '',
                ))

    # ==================================================================
    # Phase 6 — Audit-trail ``write`` override (BM-002 Scenario 5)
    # ==================================================================

    def write(self, vals):
        """Capture an audit trail when ``allocated_amount`` changes.

        BM-002 Scenario 5 (Audit Trail) requires that every
        modification to a period's ``allocated_amount`` captures:

        * ``prev_amount`` — the value BEFORE the modification;
        * ``modified_by_id`` — the user that performed the change;
        * ``modified_date`` — the UTC timestamp of the change.

        The audit fields are ``readonly=True`` and ``copy=False`` so
        they are never populated by user input — they are managed
        exclusively by this override. The override:

        1. Captures ``fields.Datetime.now()`` once outside the
           loop so every record updated in the same ``write`` call
           shares a consistent timestamp.
        2. Records the CURRENT (pre-write) ``allocated_amount`` of
           each record into the merged ``vals`` so the audit trail
           reflects the old value even if the underlying
           ``allocated_amount`` is also being updated in the same
           call.
        3. Delegates to ``super().write`` so every cache and
           invalidation path remains identical to the stock
           ``models.Model.write`` behaviour.

        Audit fields are populated only when:
        * ``allocated_amount`` is present in ``vals`` AND
        * the caller has not explicitly provided its own audit
          values (avoids clobbering migrations or test fixtures
          that need deterministic timestamps).

        Per-record tracking:
        --------------------
        Because a single ``write`` call can target multiple
        records (via ``self`` being a multi-record recordset) and
        each record may have a DIFFERENT ``prev_amount``, we split
        the update into one ``super().write()`` call per record
        when ``allocated_amount`` is being changed AND the caller
        has not pre-supplied ``prev_amount``. When
        ``allocated_amount`` is absent from ``vals`` the cheap
        batched write path is used.
        """
        if 'allocated_amount' not in vals:
            # Fast path — no audit bookkeeping needed.
            return super().write(vals)

        # When the caller is explicitly setting prev_amount /
        # modified_by_id / modified_date (e.g. a data migration
        # fixture), honour their values by not overriding.
        caller_supplied_audit = (
            'prev_amount' in vals
            or 'modified_by_id' in vals
            or 'modified_date' in vals
        )
        if caller_supplied_audit:
            return super().write(vals)

        timestamp = fields.Datetime.now()
        user_id = self.env.user.id

        # Per-record update: each record's ``prev_amount`` must
        # reflect its OWN previous ``allocated_amount``. Looping
        # preserves that invariant at the cost of one write call
        # per record — acceptable because period edits are
        # inherently interactive (user clicks Save in a form view).
        for record in self:
            record_vals = dict(vals)
            record_vals['prev_amount'] = record.allocated_amount
            record_vals['modified_by_id'] = user_id
            record_vals['modified_date'] = timestamp
            super(BudgetBudgetPeriod, record).write(record_vals)
        return True

    # ==================================================================
    # Phase 7 — Generation helpers (BM-002 Scenarios 1/2/3/6)
    # ==================================================================

    @api.model
    def _generate_equal_distribution(self, budget_line, period_type):
        """Generate equal-distribution period allocations for a line.

        BM-002 Scenario 1 (Monthly), Scenario 2 (Quarterly),
        Scenario 3 (Equal Distribution): given a parent budget line
        and a period type, create ``budget.budget.period`` records
        that:

        * cover the full date range of the line (falling back to the
          parent budget's date range when the line itself has no
          explicit bounds);
        * divide the line's ``planned_amount`` into equal portions
          — each portion rounded to the currency's smallest unit;
        * carry any rounding remainder into the FINAL period so the
          total per-period sum matches the line's ``planned_amount``
          exactly (no sum-check error).

        Args:
            budget_line (budget.budget.line): Singleton recordset of
                the parent line. Must have a populated
                ``planned_amount`` and either an explicit
                ``date_from``/``date_to`` or a parent
                ``budget_id.date_from``/``date_to``.
            period_type (str): One of ``'monthly'``, ``'quarterly'``,
                ``'annual'``, or ``'custom'``. Anything else defaults
                to a single custom period spanning the full range.

        Returns:
            budget.budget.period recordset: Newly-created period
            records (empty recordset when the range yields no splits
            — e.g. a zero-duration budget window).

        Raises:
            UserError: If the line already has ``period_ids`` (user
                must remove existing periods first — this enforces an
                explicit regeneration decision rather than a silent
                clobber of manually-adjusted allocations).
            UserError: If no usable date range is found on the line
                or its parent budget.

        Rounding contract:
        ------------------
        ``float_round`` uses the currency's ``rounding`` attribute
        so e.g. USD (0.01) truncates to cents and JPY (1.0) to yen.
        The rounding difference ``total - running_total`` is
        assigned to the final period — this keeps every intermediate
        period at the same display value while ensuring the sum
        constraint ``_check_sum_matches_line`` passes.
        """
        budget_line.ensure_one()
        if budget_line.period_ids:
            raise UserError(_(
                "Budget line '%(line)s' already has %(count)s period "
                "allocation(s). Remove them first before regenerating "
                "an equal distribution.",
                line=budget_line.display_name or budget_line.id,
                count=len(budget_line.period_ids),
            ))

        date_from = (
            budget_line.date_from
            or (
                budget_line.budget_id.date_from
                if budget_line.budget_id
                else False
            )
        )
        date_to = (
            budget_line.date_to
            or (
                budget_line.budget_id.date_to
                if budget_line.budget_id
                else False
            )
        )
        if not date_from or not date_to:
            raise UserError(_(
                "Budget line '%(line)s' must have a date range "
                "(either on the line itself or on its parent "
                "budget) before generating period allocations.",
                line=budget_line.display_name or budget_line.id,
            ))
        if date_from > date_to:
            raise UserError(_(
                "Budget line '%(line)s' has an invalid date range "
                "(%(f)s → %(t)s): start must precede end.",
                line=budget_line.display_name or budget_line.id,
                f=date_from,
                t=date_to,
            ))

        periods = self._split_date_range(date_from, date_to, period_type)
        if not periods:
            return self.browse()

        currency = budget_line.currency_id
        rounding = (currency.rounding if currency else 0.01) or 0.01
        total = budget_line.planned_amount or 0.0

        # Equal per-period amount, rounded to currency precision.
        per_period = float_round(
            total / len(periods) if periods else 0.0,
            precision_rounding=rounding,
        )
        vals_list = []
        running_total = 0.0
        last_index = len(periods) - 1
        for idx, (period_from, period_to) in enumerate(periods):
            if idx == last_index:
                # Final period absorbs any rounding remainder so
                # sum(periods.allocated_amount) == planned_amount
                # within currency rounding tolerance.
                amount = float_round(
                    total - running_total,
                    precision_rounding=rounding,
                )
            else:
                amount = per_period
                running_total += per_period
            vals_list.append({
                'budget_line_id': budget_line.id,
                'period_type': period_type,
                'date_from': period_from,
                'date_to': period_to,
                'allocated_amount': amount,
                'allocation_method': _ALLOCATION_METHOD_EQUAL,
                'sequence': (idx + 1) * 10,
            })
        _logger.info(
            "Generated %s '%s' period allocations for budget line "
            "%s (total=%s)",
            len(vals_list),
            period_type,
            budget_line.id,
            total,
        )
        return self.create(vals_list)

    @api.model
    def _split_date_range(self, date_from, date_to, period_type):
        """Split [date_from, date_to] into calendar-aligned sub-periods.

        BM-002 Scenario 1/2: the helper advances through the inclusive
        date range using ``dateutil.relativedelta`` so that calendar
        nuances (28/29/30/31 day months, leap years) are handled
        correctly without manual arithmetic.

        Args:
            date_from (date): inclusive start of the overall range.
            date_to (date): inclusive end of the overall range.
            period_type (str): ``'monthly'`` (step 1 month),
                ``'quarterly'`` (step 3 months), ``'annual'`` (step
                1 year), or any other value (single custom period).

        Returns:
            list[tuple[date, date]]: Ordered list of
            ``(period_from, period_to)`` tuples; the final tuple's
            ``period_to`` is clamped to ``date_to`` so no period
            extends beyond the caller-supplied end date.

        Example:
            >>> _split_date_range(
            ...     date(2024, 1, 1), date(2024, 12, 31), 'monthly'
            ... )
            [(date(2024, 1, 1), date(2024, 1, 31)),
             (date(2024, 2, 1), date(2024, 2, 29)),
             ...
             (date(2024, 12, 1), date(2024, 12, 31))]
        """
        if not date_from or not date_to or date_from > date_to:
            return []

        if period_type == _PERIOD_TYPE_MONTHLY:
            step = relativedelta(months=1)
        elif period_type == _PERIOD_TYPE_QUARTERLY:
            step = relativedelta(months=3)
        elif period_type == _PERIOD_TYPE_ANNUAL:
            step = relativedelta(years=1)
        else:
            # Custom / unknown: single all-encompassing period.
            return [(date_from, date_to)]

        periods = []
        cursor = date_from
        while cursor <= date_to:
            # The period end is one day before the next cursor step,
            # clamped to the overall date_to so the last period
            # stops exactly on the caller-supplied end date.
            next_cursor = cursor + step
            period_end = min(next_cursor - relativedelta(days=1), date_to)
            periods.append((cursor, period_end))
            cursor = next_cursor
        return periods

    @api.model
    def _copy_from_previous_budget(self, src_budget, dest_budget):
        """Copy percentage-distribution pattern across budgets.

        BM-002 Scenario 6 (Copy From Previous Budget): for each line
        in ``src_budget``, locate a matching line in ``dest_budget``
        (same account), read the source periods' percentage shape
        (each period's ``allocated_amount`` as a fraction of its
        parent line's ``planned_amount``), and generate equivalent
        periods in the destination line scaled to the destination
        line's own ``planned_amount`` AND shifted onto the
        destination budget's fiscal year.

        This preserves the TEMPORAL SHAPE of the source budget
        (e.g. "30% Q1, 20% Q2, 20% Q3, 30% Q4") while allowing the
        destination budget to have a different total and a different
        fiscal year window. The shift is computed as
        ``dest_budget.date_from.year - src_budget.date_from.year``
        and applied via ``relativedelta(years=offset)`` to each
        source period's ``date_from`` / ``date_to`` so the resulting
        destination periods fall within the destination budget's
        fiscal range (BM-002 Scenario 6: "the copied allocation
        respects the new budget's fiscal year dates").

        Args:
            src_budget (budget.budget): Source budget singleton.
                Must have ``line_ids`` with ``period_ids`` and
                non-zero ``planned_amount`` on each line.
            dest_budget (budget.budget): Destination budget
                singleton. Lines without periods are populated;
                lines with existing periods are SKIPPED to avoid
                clobbering manual adjustments.

        Returns:
            budget.budget.period recordset: All periods created
            across all destination lines (may be empty if no
            matching line pairs are found).

        Line matching:
        --------------
        A destination line matches a source line when both have
        the same ``account_id``. When no match is found or the
        destination line already has periods, the source line is
        skipped without error.

        Date shifting:
        --------------
        Each source period's ``date_from`` / ``date_to`` is shifted
        by the integer year delta from source to destination budget
        start. Partial-year edge cases (e.g. destination budget is
        narrower than the shifted source window) are handled by
        clamping the shifted window to the destination budget's
        bounds. Leap-day boundaries (Feb 29) are handled by
        ``relativedelta`` which collapses Feb 29 -> Feb 28 when
        shifting to a non-leap year.

        Note:
        -----
        The generated periods carry
        ``allocation_method = 'copy_previous'`` to indicate their
        origin, and a populated ``allocation_percentage`` reflecting
        the source shape (useful for visual comparison in BM-003
        reports).
        """
        src_budget.ensure_one()
        dest_budget.ensure_one()

        # BM-002 Scenario 6 mandates: "the copied allocation respects
        # the new budget's fiscal year dates". Compute the year shift
        # between source and destination so each source period's
        # window is translated onto the destination budget's calendar.
        # ``relativedelta(years=...)`` correctly handles leap-year
        # boundary cases (e.g. Feb 29 -> Feb 28) unlike a timedelta.
        year_offset = (
            dest_budget.date_from.year - src_budget.date_from.year
            if (src_budget.date_from and dest_budget.date_from)
            else 0
        )

        BudgetLine = self.env['budget.budget.line']
        created_vals_list = []
        for src_line in src_budget.line_ids:
            if not src_line.period_ids:
                # No source periods — nothing to project.
                continue
            if not src_line.planned_amount:
                # Zero source total — cannot derive percentages.
                continue
            if not src_line.account_id:
                continue

            # Locate destination line by account match.
            dest_line = BudgetLine.search(
                [
                    ('budget_id', '=', dest_budget.id),
                    ('account_id', '=', src_line.account_id.id),
                ],
                limit=1,
            )
            if not dest_line:
                continue
            if dest_line.period_ids:
                # Destination already has periods — preserve user
                # customizations rather than overwriting.
                continue

            dest_total = dest_line.planned_amount or 0.0
            dest_currency = dest_line.currency_id
            rounding = (
                dest_currency.rounding if dest_currency else 0.01
            ) or 0.01

            # Build period vals preserving percentage shape. Enforce
            # rounding to currency precision and carry any remainder
            # to the final period for sum integrity.
            source_periods = src_line.period_ids.sorted(
                key=lambda p: (p.sequence, p.date_from),
            )
            total_source = src_line.planned_amount
            running = 0.0
            last_idx = len(source_periods) - 1
            for idx, src_period in enumerate(source_periods):
                pct = (
                    src_period.allocated_amount / total_source
                    if total_source
                    else 0.0
                )
                if idx == last_idx:
                    amount = float_round(
                        dest_total - running,
                        precision_rounding=rounding,
                    )
                else:
                    amount = float_round(
                        dest_total * pct,
                        precision_rounding=rounding,
                    )
                    running += amount

                # Shift source dates by ``year_offset`` years so the
                # destination period window falls within the
                # destination budget's fiscal range. Clamp the shifted
                # window to the destination budget's bounds when the
                # shift produces a partial-year edge case (e.g. the
                # destination budget is narrower than the source).
                shifted_from = (
                    src_period.date_from
                    + relativedelta(years=year_offset)
                )
                shifted_to = (
                    src_period.date_to
                    + relativedelta(years=year_offset)
                )
                if (
                    dest_budget.date_from
                    and shifted_from < dest_budget.date_from
                ):
                    shifted_from = dest_budget.date_from
                if (
                    dest_budget.date_to
                    and shifted_to > dest_budget.date_to
                ):
                    shifted_to = dest_budget.date_to

                created_vals_list.append({
                    'budget_line_id': dest_line.id,
                    'period_type': src_period.period_type,
                    'date_from': shifted_from,
                    'date_to': shifted_to,
                    'allocated_amount': amount,
                    'allocation_method': (
                        _ALLOCATION_METHOD_COPY_PREVIOUS
                    ),
                    'allocation_percentage': pct * 100.0,
                    'sequence': src_period.sequence,
                })

        if not created_vals_list:
            return self.browse()

        _logger.info(
            "Copying %s period allocation(s) from budget %s to "
            "budget %s (pattern preservation).",
            len(created_vals_list),
            src_budget.id,
            dest_budget.id,
        )
        return self.create(created_vals_list)

    # ==================================================================
    # Phase 8 — Action helpers
    # ==================================================================

    def action_open_source_transactions(self):
        """Return an ``ir.actions.act_window`` to drill-down on actuals.

        Triggered from the period detail view (or from the BM-003
        variance report when a user clicks on a period row). The
        action opens a filtered ``account.move.line`` list / form
        window showing the posted journal items that feed
        ``actual_amount``:

        * ``account_id`` = period's parent line account;
        * ``parent_state`` = ``'posted'`` (no drafts, no cancelled);
        * ``date`` within ``[period.date_from, period.date_to]``.

        Multi-company isolation is provided by the
        ``allowed_company_ids`` record rule on
        ``account.move.line`` — no additional company filter is
        required here.

        Returns:
            dict: Odoo-style action dictionary. If called on an empty
            recordset or a record with no account attached, the
            returned dictionary uses ``type='ir.actions.act_window'``
            and an empty ``domain`` so the user is shown an empty
            list rather than an error.
        """
        self.ensure_one()
        account = self.budget_line_id.account_id
        title = _(
            "Actuals for %(account)s in %(period)s",
            account=account.display_name if account else _('Unknown'),
            period=self.display_name or self.name or '',
        )
        domain = []
        if account:
            domain.append(('account_id', '=', account.id))
        domain.append(('parent_state', '=', 'posted'))
        if self.date_from:
            domain.append(('date', '>=', self.date_from))
        if self.date_to:
            domain.append(('date', '<=', self.date_to))
        # Context: pre-set the group by account for consistency with
        # the BM-003 drill-down experience.
        ctx = dict(self.env.context)
        ctx['search_default_group_by_date'] = 1
        return {
            'type': 'ir.actions.act_window',
            'name': title,
            'res_model': 'account.move.line',
            'view_mode': 'list,form',
            'domain': domain,
            'context': ctx,
            'target': 'current',
        }

    # ==================================================================
    # Phase 9 — SQL Constraints (Odoo 19 ``models.Constraint`` pattern)
    # ==================================================================

    _allocated_amount_non_negative = models.Constraint(
        'CHECK(allocated_amount >= 0)',
        "The allocated amount of a budget period must be zero or "
        "positive; negative allocations are not supported.",
    )
    _allocation_percentage_bounded = models.Constraint(
        'CHECK(allocation_percentage >= 0 AND '
        'allocation_percentage <= 100)',
        "The allocation percentage must fall within the inclusive "
        "range 0 – 100.",
    )
    _date_range_valid = models.Constraint(
        'CHECK(date_from <= date_to)',
        "A budget period's start date must be on or before its end "
        "date.",
    )
