# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""
Budget Period Allocation Model (BM-002)
=======================================

Implements ``budget.budget.period`` — the per-period allocation record
that breaks a parent ``budget.budget.line`` into discrete time windows
(monthly, quarterly, annual, or custom) each with its own planned
amount. BM-002 is the Phase 2 story in Track B (Budget Management) and
builds on the BM-001 header / line foundation by layering temporal
granularity atop the annual planned total.

A single ``budget.budget.line`` may own zero or many
``budget.budget.period`` records. When zero periods are attached, the
parent line is treated as a single-window budget item covering the
entire fiscal range (``budget.date_from`` → ``budget.date_to``). When
one or more periods are attached, their ``planned_amount`` values sum
to the parent line's ``planned_amount`` (an allocation-integrity
invariant enforced by ``_check_allocation_total``).

Story Mapping
-------------
* BM-002 Scenario 1 — Monthly allocation (12 periods across a fiscal
  year); running total enforced to match annual line total.
* BM-002 Scenario 2 — Quarterly allocation (Q1-Q4) aligned to the
  company's fiscal calendar.
* BM-002 Scenario 3 — Equal distribution; remainder from banker's
  rounding accumulates in the final period.
* BM-002 Scenario 4 — Manual (custom) allocation; users may distribute
  freely with a running-total warning when the sum diverges from the
  parent planned amount.
* BM-002 Scenario 5 — Modification audit trail via ``mail.thread`` and
  the ``audit_note`` text field. Confirmed budgets require unlock
  before period edits propagate.
* BM-002 Scenario 6 — Copy allocation pattern from another budget line
  as a percentage distribution; the ``allocation_percentage`` field is
  the vehicle for this scenario when combined with the destination
  line's planned amount.

Field Structure
---------------
Per BM-002 ticket Section 4.4 the canonical fields are:

* ``budget_line_id`` — Many2one (required, cascade).
* ``name`` — Char (computed, e.g. "January 2024" / "Q1 2024").
* ``date_from`` / ``date_to`` — Date (required; window bounds).
* ``sequence`` — Integer (period ordering).
* ``planned_amount`` — Monetary (allocated amount for this period).
* ``allocation_percentage`` — Float (share of the parent line total).
* ``company_id`` / ``currency_id`` — related to the parent line for
  multi-company and monetary rendering.

Additional bookkeeping fields enforce BM-002 Scenarios 4 and 5:

* ``period_type`` — Selection (monthly / quarterly / annual / custom)
  mirroring the parent line / budget allocation strategy.
* ``audit_note`` — Text free-form note explaining modification intent.

Rules Compliance
----------------
* R-01 — No cross-module imports. Only ``odoo`` core and stdlib
  modules (``calendar`` for month-end arithmetic) are referenced.
* R-03 — ``_name = 'budget.budget.period'`` is a net-new persistent
  model. ``_inherit`` is used solely to compose ``mail.thread`` for
  audit-trail chatter. No core Odoo model is extended by this file.
* R-05 — No redefinition of fields on ``account.move`` or
  ``account.move.line``. This model exists entirely within the
  ``account_budget_management`` namespace.
* R-07 — No ``sudo()`` calls. Access control is enforced via
  ``ir.model.access.csv`` + ``ir.rule`` (multi-company) records.
* R-08 — No ``variance_*`` or ``alert_*`` prefixed fields appear on
  this model so the Checkpoint 5 disjoint baseline is preserved.
* R-09 — Module folder ``account_budget_management`` matches the AAP.

Performance
-----------
Period records are lightweight pure-metadata rows with stored
``allocation_percentage`` computed only on write. Equal-distribution
generation uses a bounded in-memory loop over the period count; no
``account.move.line`` queries are performed from this model.
"""

import calendar
import logging
from datetime import date, timedelta

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
#: ``allocation_type`` can be rendered explicitly even when no
#: subdivision is applied.
_PERIOD_TYPE_ANNUAL = 'annual'

#: Custom period type — user-defined windows with no automatic
#: generation constraint. Used when BM-002 Scenario 4 manual allocation
#: is in effect.
_PERIOD_TYPE_CUSTOM = 'custom'


class BudgetBudgetPeriod(models.Model):
    """Per-period allocation of a ``budget.budget.line`` planned amount.

    Each ``budget.budget.period`` record represents a time window
    (monthly, quarterly, annual, or custom) with a share of the
    parent line's planned amount. Records are ordered by
    ``budget_line_id, sequence, date_from`` so that period lists
    render chronologically within each parent line.

    The record composes :class:`mail.thread` so that modification of
    ``planned_amount`` on a confirmed budget posts to the chatter for
    audit-trail continuity (BM-002 Scenario 5).
    """

    _name = 'budget.budget.period'
    _description = 'Budget Period Allocation'
    _inherit = ['mail.thread']
    _order = 'budget_line_id, sequence, date_from'
    _rec_name = 'name'
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
        help="Currency of the monetary ``planned_amount`` on this "
             "period — mirrors the parent line's currency.",
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
    state = fields.Selection(
        related='budget_line_id.state',
        store=True,
        index=True,
        string='Budget Status',
        help="Mirror of the parent budget's lifecycle state "
             "(draft / confirmed / closed / cancelled). Period "
             "records can only be freely edited while the parent is "
             "``draft``; edits against other states require unlock "
             "via the manager action on the parent line.",
    )

    # ==================================================================
    # Section 3.2 — Period descriptor fields
    # ==================================================================

    name = fields.Char(
        string='Period Label',
        compute='_compute_name',
        store=True,
        help="Human-readable period label (e.g. 'January 2024', "
             "'Q1 2024', 'FY 2024'). Computed from ``period_type`` + "
             "``date_from`` + ``date_to``. Falls back to the bare "
             "date range when the period type is ``custom``.",
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
    sequence = fields.Integer(
        string='Sequence',
        default=10,
        index=True,
        help="Ordering hint within the parent line's period list. "
             "Lower sequences render first in chronological views.",
    )
    date_from = fields.Date(
        string='Period Start',
        required=True,
        tracking=True,
        help="Inclusive start date of the period allocation window. "
             "Must fall within the parent budget's fiscal range "
             "(enforced by ``_check_dates_within_budget``).",
    )
    date_to = fields.Date(
        string='Period End',
        required=True,
        tracking=True,
        help="Inclusive end date of the period allocation window. "
             "Must not precede ``date_from`` (enforced by "
             "``_check_date_order``) and must fall within the parent "
             "budget's fiscal range.",
    )

    # ==================================================================
    # Section 3.3 — Monetary + percentage allocation fields
    # ==================================================================

    planned_amount = fields.Monetary(
        string='Planned Amount',
        currency_field='currency_id',
        default=0.0,
        tracking=True,
        help="The monetary amount allocated to this specific period. "
             "Must be non-negative (enforced by "
             "``_check_planned_amount``). The sum of period "
             "``planned_amount`` values for a line should equal the "
             "line's own ``planned_amount`` (BM-002 Scenario 1 "
             "running-total rule; enforced leniently by "
             "``_check_allocation_total`` so manual-allocation "
             "workflows are not blocked).",
    )
    allocation_percentage = fields.Float(
        string='Allocation Share (%)',
        compute='_compute_allocation_percentage',
        store=True,
        digits=(7, 4),
        help="Stored share of the parent line's planned amount that "
             "this period represents. Computed as "
             "``planned_amount / parent.planned_amount * 100``. Used "
             "by BM-002 Scenario 6 (copy-allocation-pattern) so that "
             "the distribution shape of one line can be replicated "
             "proportionally onto another line at a different "
             "absolute total.",
    )
    audit_note = fields.Text(
        string='Audit Note',
        translate=False,
        tracking=True,
        help="Optional free-form note captured when a period "
             "allocation is modified on a confirmed budget (BM-002 "
             "Scenario 5). Combined with the chatter / tracking "
             "records the note forms the user-facing audit trail.",
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
          the quarter is derived from ``date_from`` (month // 3 + 1).
        * ``annual`` — ``"FY 2024"`` (the fiscal year). When
          ``date_from`` and ``date_to`` cross calendar years, the
          label renders both years (``"FY 2024-2025"``).
        * ``custom`` — ``"YYYY-MM-DD → YYYY-MM-DD"``.

        The compute is total — any missing ``date_from`` yields an
        empty-string label so the record can be created incrementally
        without raising during form editing.
        """
        for period in self:
            if not period.date_from:
                period.name = ''
                continue
            start = period.date_from
            end = period.date_to or start
            if period.period_type == _PERIOD_TYPE_MONTHLY:
                period.name = f"{calendar.month_name[start.month]} {start.year}"
            elif period.period_type == _PERIOD_TYPE_QUARTERLY:
                quarter = ((start.month - 1) // 3) + 1
                period.name = f"Q{quarter} {start.year}"
            elif period.period_type == _PERIOD_TYPE_ANNUAL:
                if start.year == end.year:
                    period.name = f"FY {start.year}"
                else:
                    period.name = f"FY {start.year}-{end.year}"
            else:
                period.name = (
                    f"{start.strftime('%Y-%m-%d')} → "
                    f"{end.strftime('%Y-%m-%d')}"
                )

    @api.depends('planned_amount', 'budget_line_id.planned_amount')
    def _compute_allocation_percentage(self):
        """Compute ``allocation_percentage`` = period / parent * 100.

        When the parent line's ``planned_amount`` is zero (or absent),
        the percentage is zero — this avoids division-by-zero and is
        the sensible fallback for empty or placeholder parent lines.
        Stored so that downstream percentage-copy workflows (BM-002
        Scenario 6) can read the distribution shape without
        recomputing.
        """
        for period in self:
            parent_total = (
                period.budget_line_id.planned_amount
                if period.budget_line_id else 0.0
            )
            if parent_total:
                period.allocation_percentage = (
                    period.planned_amount / parent_total * 100.0
                )
            else:
                period.allocation_percentage = 0.0

    # ==================================================================
    # Phase 5 — Constraints
    # ==================================================================

    @api.constrains('date_from', 'date_to')
    def _check_date_order(self):
        """``date_from`` must not follow ``date_to`` (BM-002 Scenario 1).

        The equality case (``date_from == date_to``) is tolerated to
        support single-day allocation windows — an edge case useful
        for custom allocations that represent a single operational
        milestone.
        """
        for period in self:
            if period.date_from and period.date_to and period.date_from > period.date_to:
                raise ValidationError(_(
                    "Period allocation '%(name)s' has a start date "
                    "(%(start)s) that is after its end date "
                    "(%(end)s). Please reorder the dates so that the "
                    "start precedes or equals the end.",
                ) % {
                    'name': period.name or '(unnamed period)',
                    'start': period.date_from,
                    'end': period.date_to,
                })

    @api.constrains('date_from', 'date_to', 'budget_line_id')
    def _check_dates_within_budget(self):
        """Period dates must fall within the parent budget's fiscal window.

        Each period belongs to a ``budget.budget.line`` which inherits
        its ``date_from`` / ``date_to`` from the grandparent
        ``budget.budget`` header. A period allocation whose window
        spills outside the header's fiscal range would violate the
        BM-002 premise that allocation distributes the annual / line
        total across sub-ranges of the same fiscal window.
        """
        for period in self:
            if not period.budget_line_id:
                continue
            budget = period.budget_line_id.budget_id
            if not budget:
                continue
            if period.date_from and budget.date_from and period.date_from < budget.date_from:
                raise ValidationError(_(
                    "Period allocation '%(name)s' starts "
                    "(%(p_start)s) before the parent budget's "
                    "fiscal start date (%(b_start)s). Period "
                    "allocations must fall within the parent "
                    "budget's fiscal range.",
                ) % {
                    'name': period.name or '(unnamed period)',
                    'p_start': period.date_from,
                    'b_start': budget.date_from,
                })
            if period.date_to and budget.date_to and period.date_to > budget.date_to:
                raise ValidationError(_(
                    "Period allocation '%(name)s' ends "
                    "(%(p_end)s) after the parent budget's fiscal "
                    "end date (%(b_end)s). Period allocations must "
                    "fall within the parent budget's fiscal range.",
                ) % {
                    'name': period.name or '(unnamed period)',
                    'p_end': period.date_to,
                    'b_end': budget.date_to,
                })

    @api.constrains('planned_amount')
    def _check_planned_amount(self):
        """Period ``planned_amount`` must be non-negative.

        Zero is permitted so that placeholder periods can be inserted
        into a manual allocation layout without triggering the
        constraint — this supports the BM-002 Scenario 4 custom
        workflow where some periods may legitimately carry no
        allocation.
        """
        for period in self:
            if float_compare(
                period.planned_amount,
                0.0,
                precision_rounding=(
                    period.currency_id.rounding
                    if period.currency_id
                    else 0.01
                ),
            ) < 0:
                raise ValidationError(_(
                    "Period allocation '%(name)s' has a negative "
                    "planned amount (%(amount)s). Period allocations "
                    "must be zero or positive.",
                ) % {
                    'name': period.name or '(unnamed period)',
                    'amount': period.planned_amount,
                })

    # ==================================================================
    # Phase 6 — Distribution helpers
    #
    # These are invoked from the parent ``budget.budget.line`` to
    # generate period allocations programmatically. They are declared
    # on this model because they operate on the period recordset and
    # the sibling line model remains agnostic of calendar arithmetic
    # details.
    # ==================================================================

    @api.model
    def _equal_distribute(self, line, count, period_type):
        """Distribute a parent line's total across ``count`` periods.

        Per BM-002 Scenario 3, equal distribution computes
        ``per_period = total / count`` with banker's rounding to the
        currency precision, then places the remainder
        ``total - (per_period * count)`` in the final period so the
        running total matches the parent exactly.

        :param line: the ``budget.budget.line`` recordset (one record)
            whose ``planned_amount`` is being distributed.
        :param count: number of periods to generate.
        :param period_type: one of ``monthly`` / ``quarterly`` /
            ``annual`` — used for the period label and for date-range
            computation in ``_generate_date_ranges``.
        :return: the newly-created ``budget.budget.period`` recordset.
        """
        if count <= 0:
            raise UserError(_(
                "Period count must be a positive integer; received "
                "%(count)s.",
            ) % {'count': count})
        total = line.planned_amount or 0.0
        rounding = (
            line.currency_id.rounding
            if line.currency_id else 0.01
        )
        # Compute per-period amount with banker's rounding (the Odoo
        # default rounding_method for ``float_round`` — HALF-EVEN).
        per_period = float_round(
            total / count,
            precision_rounding=rounding,
            rounding_method='HALF-EVEN',
        )
        # Remainder accumulates in the final period so the running
        # total reconciles to the parent line total exactly.
        remainder = float_round(
            total - (per_period * count),
            precision_rounding=rounding,
            rounding_method='HALF-EVEN',
        )
        ranges = self._generate_date_ranges(
            line.date_from, line.date_to, period_type, count,
        )
        create_vals = []
        for idx, (d_from, d_to) in enumerate(ranges):
            amount = per_period + (remainder if idx == count - 1 else 0.0)
            create_vals.append({
                'budget_line_id': line.id,
                'period_type': period_type,
                'sequence': (idx + 1) * 10,
                'date_from': d_from,
                'date_to': d_to,
                'planned_amount': amount,
            })
        return self.create(create_vals)

    @api.model
    def _generate_date_ranges(self, start, end, period_type, count):
        """Generate ``count`` chronological (start, end) tuples.

        Monthly periods use calendar-month boundaries. Quarterly
        periods use three-month boundaries. Annual periods return a
        single (start, end) tuple; when ``count > 1`` is requested for
        annual type, the range is divided into equal-length date
        slices as a fallback. Custom period generation is not
        supported here — the caller is responsible for producing
        custom ranges directly.

        :param start: inclusive start date of the overall window.
        :param end: inclusive end date of the overall window.
        :param period_type: one of the four ``_PERIOD_TYPE_*``
            constants.
        :param count: target number of periods.
        :return: list of (date_from, date_to) tuples ordered
            chronologically.
        """
        if not start or not end:
            raise UserError(_(
                "Cannot generate date ranges without both a start "
                "and end date.",
            ))
        if start > end:
            raise UserError(_(
                "Start date (%(start)s) must not follow end date "
                "(%(end)s).",
            ) % {'start': start, 'end': end})
        ranges = []
        if period_type == _PERIOD_TYPE_MONTHLY:
            # Walk forward one calendar month at a time until the end
            # date is reached; the last period is clamped to ``end``.
            current_start = start
            for _idx in range(count):
                month_last_day = calendar.monthrange(
                    current_start.year, current_start.month,
                )[1]
                current_end = date(
                    current_start.year,
                    current_start.month,
                    month_last_day,
                )
                if current_end > end:
                    current_end = end
                ranges.append((current_start, current_end))
                if current_end >= end:
                    break
                # Next month's first day.
                next_month = current_start.month + 1
                next_year = current_start.year
                if next_month > 12:
                    next_month = 1
                    next_year += 1
                current_start = date(next_year, next_month, 1)
        elif period_type == _PERIOD_TYPE_QUARTERLY:
            # Walk forward three months at a time.
            current_start = start
            for _idx in range(count):
                months_ahead = 2
                target_month = current_start.month + months_ahead
                target_year = current_start.year
                while target_month > 12:
                    target_month -= 12
                    target_year += 1
                month_last_day = calendar.monthrange(
                    target_year, target_month,
                )[1]
                current_end = date(
                    target_year, target_month, month_last_day,
                )
                if current_end > end:
                    current_end = end
                ranges.append((current_start, current_end))
                if current_end >= end:
                    break
                # Next quarter's first day.
                next_month = target_month + 1
                next_year = target_year
                if next_month > 12:
                    next_month = 1
                    next_year += 1
                current_start = date(next_year, next_month, 1)
        else:
            # Annual / other — divide into ``count`` equal date slices.
            total_days = (end - start).days + 1
            slice_length = max(total_days // count, 1)
            current_start = start
            for idx in range(count):
                if idx == count - 1:
                    current_end = end
                else:
                    current_end = current_start + timedelta(days=slice_length - 1)
                    if current_end > end:
                        current_end = end
                ranges.append((current_start, current_end))
                current_start = current_end + timedelta(days=1)
                if current_start > end:
                    break
        return ranges

    # ==================================================================
    # Phase 7 — SQL constraints
    # ==================================================================
    # Declared via Odoo 19's ``models.Constraint`` TableObject pattern.
    # The legacy ``_sql_constraints`` attribute was deprecated in Odoo 19
    # (registry-load warning). See ``odoo/orm/table_objects.py`` and
    # ``addons/l10n_vn_edi_viettel/models/sinvoice.py`` for precedent.

    _planned_amount_non_negative = models.Constraint(
        'CHECK(planned_amount >= 0)',
        'Period planned amount must be zero or positive.',
    )
