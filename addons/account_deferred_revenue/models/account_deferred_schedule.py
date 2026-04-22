# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
from calendar import monthrange

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, float_is_zero

_logger = logging.getLogger(__name__)


class AccountDeferredSchedule(models.Model):
    """Deferred revenue schedule defining recognition plan for invoice amounts over multiple periods.

    A schedule captures:

    * The deferred amount (``total_amount``) held on a balance-sheet account (``deferred_account_id``).
    * The recognition plan: how that amount flows into a P&L account (``recognition_account_id``)
      between ``start_date`` and ``end_date`` via ``recognition_method``.
    * Lines (``line_ids``): the generated per-period recognition entries that the DR-003 cut-off
      wizard consumes to post journal entries.

    **State machine**:

    ``draft`` -> (:meth:`action_confirm`) -> ``confirmed`` -> (:meth:`action_close`) -> ``closed``
                                                                    ``confirmed`` -> (:meth:`action_draft`) -> ``draft``  *(only if no posted lines)*

    **Net-new model** per R-03: uses ``_name`` for creation and composes abstract mixins via
    ``_inherit = ['mail.thread', 'mail.activity.mixin']`` for chatter/activity tracking.
    """

    _name = 'account.deferred.schedule'
    _description = 'Deferred Revenue Schedule'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'start_date desc, name'
    _check_company_auto = True
    _rec_name = 'name'

    # ------------------------------------------------------------------
    # Identification fields
    # ------------------------------------------------------------------
    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        default=lambda self: _('New'),
        readonly=True,
        tracking=True,
        index=True,
        help=(
            "Unique reference code for this schedule, assigned from the "
            "``account.deferred.schedule`` ``ir.sequence`` on creation. "
            "Format: DEF-YYYY-NNNNN (configured in ``data/deferred_data.xml``)."
        ),
    )

    # ------------------------------------------------------------------
    # Partner / source / company fields
    # ------------------------------------------------------------------
    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Partner',
        tracking=True,
        check_company=True,
        index=True,
        help='Customer (for deferred revenue) or vendor (for deferred expense).',
    )

    source_move_id = fields.Many2one(
        comodel_name='account.move',
        string='Source Invoice',
        domain=(
            "[('move_type', 'in', "
            "('out_invoice', 'in_invoice', 'out_refund', 'in_refund')), "
            "('state', '=', 'posted')]"
        ),
        check_company=True,
        tracking=True,
        copy=False,
        index=True,
        ondelete='restrict',
        help=(
            "Invoice from which this schedule was created. Optional: manual schedules "
            "have no source invoice (DR-001 Scenario 4)."
        ),
    )

    source_move_line_id = fields.Many2one(
        comodel_name='account.move.line',
        string='Source Invoice Line',
        check_company=True,
        copy=False,
        ondelete='set null',
        help=(
            "Specific invoice line the schedule was created from. When set, the "
            "line's ``deferred_schedule_id`` back-reference is populated on "
            "``create()`` (DR-001 Scenario 1)."
        ),
    )

    company_id = fields.Many2one(
        comodel_name='res.company',
        required=True,
        default=lambda self: self.env.company,
        tracking=True,
        index=True,
        help='Company owning this schedule. Determines default accounts and lock dates.',
    )

    # ------------------------------------------------------------------
    # Amount / currency fields
    # ------------------------------------------------------------------
    total_amount = fields.Monetary(
        string='Total Deferred Amount',
        required=True,
        currency_field='currency_id',
        tracking=True,
        help='Total amount to be recognized over the deferral period, in schedule currency.',
    )

    currency_id = fields.Many2one(
        comodel_name='res.currency',
        required=True,
        default=lambda self: self.env.company.currency_id,
        tracking=True,
        help=(
            "Currency of ``total_amount`` and all recognition lines. Defaults to "
            "company currency; override when deferring foreign-currency invoices "
            "(DR-002 Scenario 5)."
        ),
    )

    # ------------------------------------------------------------------
    # Account fields (R-05-aware: read-only reference to core account_type)
    # ------------------------------------------------------------------
    deferred_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Deferred Account',
        required=True,
        check_company=True,
        tracking=True,
        domain=(
            "[('account_type', 'in', ('liability_current', 'liability_non_current', "
            "'asset_current', 'asset_non_current')), ('deprecated', '=', False)]"
        ),
        help=(
            "Balance-sheet account holding the deferred amount until recognition. "
            "Typical choices: 2100 Deferred Revenue (liability) for customer advances; "
            "1200 Prepaid Expenses (asset) for prepaid vendor invoices (DR-001 Scenario 3)."
        ),
    )

    recognition_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Recognition Account',
        required=True,
        check_company=True,
        tracking=True,
        domain=(
            "[('account_type', 'in', ('income', 'income_other', 'expense', "
            "'expense_depreciation', 'expense_direct_cost')), "
            "('deprecated', '=', False)]"
        ),
        help=(
            "P&L account where recognized portions are posted each period. "
            "Typical choices: 4100 Service Revenue (income); 5100 Rent Expense "
            "(expense) (DR-001 Scenario 3)."
        ),
    )

    # ------------------------------------------------------------------
    # Recognition configuration fields
    # ------------------------------------------------------------------
    recognition_method = fields.Selection(
        selection=[
            ('straight_line', 'Straight-line (equal periods)'),
            ('date_based', 'Date-based (prorated by calendar days)'),
            ('manual', 'Manual (user-defined amounts)'),
        ],
        string='Recognition Method',
        default='straight_line',
        required=True,
        tracking=True,
        help=(
            "* **Straight-line**: ``total_amount`` divided equally across "
            "``period_count`` months; rounding adjustment on the last line.\n"
            "* **Date-based**: amounts prorated by calendar days in each period "
            "within [start_date, end_date] (DR-002 Scenario 2).\n"
            "* **Manual**: user enters recognition amounts and dates; schedule "
            "does not regenerate them (DR-002 manual method)."
        ),
    )

    start_date = fields.Date(
        string='Recognition Start Date',
        required=True,
        tracking=True,
        help='First day of the first recognition period.',
    )

    end_date = fields.Date(
        string='Recognition End Date',
        required=True,
        tracking=True,
        help='Last day of the final recognition period.',
    )

    period_count = fields.Integer(
        string='Number of Periods',
        compute='_compute_period_count',
        store=True,
        help=(
            "Computed number of monthly periods between ``start_date`` and ``end_date``. "
            "Warning (log-only) issued when > 60 months (DR-001 Scenario 5 validation)."
        ),
    )

    analytic_distribution = fields.Json(
        string='Analytic Distribution',
        help=(
            "Analytic distribution copied from the source invoice line on create() "
            "(DR-001 Scenario 6). Stored as JSON mapping plan-id -> percentage. "
            "Preserved through recognition lines when cut-off wizard posts."
        ),
    )

    # ------------------------------------------------------------------
    # State / aggregates / dashboard fields
    # ------------------------------------------------------------------
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
            ('closed', 'Closed'),
        ],
        string='Status',
        default='draft',
        required=True,
        copy=False,
        tracking=True,
        index=True,
        help=(
            "**draft**: schedule is being edited; no recognition plan yet.\n"
            "**confirmed**: recognition plan generated (``line_ids`` populated); "
            "cut-off wizard can post lines.\n"
            "**closed**: schedule is finalized; all lines posted or manually closed."
        ),
    )

    line_ids = fields.One2many(
        comodel_name='account.deferred.line',
        inverse_name='schedule_id',
        string='Recognition Lines',
        copy=True,
        help='Auto-generated recognition lines. See ``_compute_recognition_schedule``.',
    )

    line_count = fields.Integer(
        string='Line Count',
        compute='_compute_line_count',
        store=False,
    )

    posted_amount = fields.Monetary(
        string='Posted Amount',
        compute='_compute_amounts',
        store=False,
        currency_field='currency_id',
        help='Sum of ``recognition_amount`` across posted lines.',
    )

    remaining_amount = fields.Monetary(
        string='Remaining Amount',
        compute='_compute_amounts',
        store=False,
        currency_field='currency_id',
        help='``total_amount`` minus ``posted_amount``.',
    )

    completion_status = fields.Selection(
        selection=[
            ('active', 'Active'),
            ('completed', 'Completed'),
            ('on_hold', 'On Hold'),
        ],
        string='Completion',
        compute='_compute_completion_status',
        store=True,
        help=(
            "Dashboard-facing status for DR-004:\n"
            "* **active**: confirmed schedule with lines still pending.\n"
            "* **completed**: ``state='closed'`` OR ``remaining_amount`` fully recognized.\n"
            "* **on_hold**: still in ``draft`` state."
        ),
    )

    # ------------------------------------------------------------------
    # CRUD Overrides
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        """Auto-assign ``name`` from ``ir.sequence`` and backfill line ``deferred_schedule_id``."""
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                seq_code = 'account.deferred.schedule'
                vals['name'] = self.env['ir.sequence'].next_by_code(seq_code) or _('New')
            # If a source line was picked but no analytic_distribution supplied,
            # copy it from the source line (DR-001 Scenario 6)
            if vals.get('source_move_line_id') and not vals.get('analytic_distribution'):
                src = self.env['account.move.line'].browse(vals['source_move_line_id'])
                if src and src.analytic_distribution:
                    vals['analytic_distribution'] = src.analytic_distribution
        schedules = super().create(vals_list)
        # Back-populate the source line's deferred_schedule_id for reverse navigation
        for schedule in schedules:
            if schedule.source_move_line_id and not schedule.source_move_line_id.deferred_schedule_id:
                schedule.source_move_line_id.deferred_schedule_id = schedule.id
        return schedules

    # ------------------------------------------------------------------
    # Computed field methods
    # ------------------------------------------------------------------
    @api.depends('start_date', 'end_date')
    def _compute_period_count(self):
        for schedule in self:
            if not schedule.start_date or not schedule.end_date:
                schedule.period_count = 0
                continue
            if schedule.end_date < schedule.start_date:
                schedule.period_count = 0
                continue
            delta = relativedelta(schedule.end_date, schedule.start_date)
            # +1 because a Jan-1 to Jan-31 span is 1 period, not 0
            months = delta.years * 12 + delta.months + (1 if delta.days >= 0 else 0)
            schedule.period_count = max(months, 1)

    @api.depends('line_ids')
    def _compute_line_count(self):
        for schedule in self:
            schedule.line_count = len(schedule.line_ids)

    @api.depends('line_ids.state', 'line_ids.recognition_amount', 'total_amount')
    def _compute_amounts(self):
        for schedule in self:
            posted = sum(
                line.recognition_amount
                for line in schedule.line_ids
                if line.state == 'posted'
            )
            schedule.posted_amount = posted
            schedule.remaining_amount = schedule.total_amount - posted

    @api.depends('state', 'posted_amount', 'total_amount', 'currency_id')
    def _compute_completion_status(self):
        for schedule in self:
            currency = schedule.currency_id or schedule.company_id.currency_id
            fully_recognized = bool(currency) and float_is_zero(
                schedule.remaining_amount,
                precision_rounding=currency.rounding,
            )
            if schedule.state == 'draft':
                schedule.completion_status = 'on_hold'
            elif schedule.state == 'closed' or fully_recognized:
                schedule.completion_status = 'completed'
            else:
                schedule.completion_status = 'active'

    # ------------------------------------------------------------------
    # Constraint methods
    # ------------------------------------------------------------------
    @api.constrains('start_date', 'end_date')
    def _check_dates(self):
        # DR-001 Scenario 5 admin tunability: read the warning threshold from
        # ir.config_parameter so administrators can tune it without a code change.
        # The default value (60 months) is seeded in data/deferred_data.xml; if the
        # parameter is cleared or invalid, fall back to 60 defensively.
        # sudo required: ir.config_parameter read access is restricted to
        # the admin group; sudo() is the documented pattern (see data/deferred_data.xml
        # lines 88-91) and safe here because the value read is a scalar configuration
        # threshold, not a permission-sensitive payload.
        param = self.env['ir.config_parameter'].sudo().get_param(
            'account_deferred_revenue.max_months_warning',
            default='60',
        )
        try:
            threshold = int(param)
        except (TypeError, ValueError):
            threshold = 60
        if threshold <= 0:
            threshold = 60
        for schedule in self:
            if not schedule.start_date or not schedule.end_date:
                continue
            if schedule.end_date <= schedule.start_date:
                raise ValidationError(_(
                    "Recognition end date (%(end)s) must be AFTER start date (%(start)s) "
                    "(DR-001 Scenario 5).",
                    end=schedule.end_date,
                    start=schedule.start_date,
                ))
            # DR-001 Scenario 5: warn (log-only, not fatal) when period exceeds
            # the administratively-configured threshold (default 60 months).
            if schedule.period_count > threshold:
                _logger.warning(
                    "Deferred schedule %s spans %d months - exceeds configured "
                    "%d-month threshold (DR-001 Scenario 5).",
                    schedule.name or schedule.id,
                    schedule.period_count,
                    threshold,
                )

    @api.constrains('total_amount')
    def _check_amount(self):
        for schedule in self:
            if float_compare(
                schedule.total_amount,
                0.0,
                precision_rounding=(schedule.currency_id.rounding if schedule.currency_id else 0.01),
            ) <= 0:
                raise ValidationError(_(
                    "Total deferred amount must be strictly positive (got %(amount)s).",
                    amount=schedule.total_amount,
                ))

    @api.constrains('deferred_account_id', 'recognition_account_id')
    def _check_accounts_distinct(self):
        for schedule in self:
            if (
                schedule.deferred_account_id
                and schedule.recognition_account_id
                and schedule.deferred_account_id == schedule.recognition_account_id
            ):
                raise ValidationError(_(
                    "Deferred account and recognition account must be different "
                    "(both currently set to %(account)s).",
                    account=schedule.deferred_account_id.display_name,
                ))

    # ------------------------------------------------------------------
    # Onchange handler
    # ------------------------------------------------------------------
    @api.onchange('source_move_line_id')
    def _onchange_source_move_line(self):
        """Pre-fill schedule fields from a picked invoice line (DR-001 Scenario 1)."""
        if not self.source_move_line_id:
            return
        src = self.source_move_line_id
        # Inherit source's move / partner / amount / analytic distribution
        self.source_move_id = src.move_id
        self.partner_id = src.partner_id or src.move_id.partner_id
        self.total_amount = abs(src.balance) or abs(src.price_subtotal)
        self.currency_id = src.currency_id or src.company_currency_id
        self.analytic_distribution = src.analytic_distribution or False
        # Default deferred_account_id from the source line's account (user can override)
        if not self.deferred_account_id:
            # For invoices, source line posts to revenue/expense; user picks the deferred account
            pass  # leave blank - user must explicitly select
        # Propose start_date = invoice date; end_date = invoice_date + 12 months (user adjusts)
        if src.move_id.invoice_date:
            self.start_date = src.move_id.invoice_date
            if not self.end_date:
                self.end_date = src.move_id.invoice_date + relativedelta(months=12)

    # ------------------------------------------------------------------
    # State-transition action methods
    # ------------------------------------------------------------------
    def action_confirm(self):
        """Generate recognition lines and transition to ``confirmed`` (DR-001 -> DR-002 handoff).

        **DR-002 SUM INVARIANT (manual method safety)**: after line generation (or
        inspection of user-supplied lines for the manual method), the sum of
        ``recognition_amount`` across ``line_ids`` must equal ``total_amount`` using
        the schedule's currency rounding. Enforced here (rather than as an
        ``@api.constrains``) so that draft schedules may be edited freely without
        tripping validation mid-edit; the invariant only becomes mandatory at the
        moment the user requests confirmation.
        """
        for schedule in self:
            if schedule.state != 'draft':
                raise UserError(_(
                    "Only draft schedules can be confirmed; %(name)s is %(state)s.",
                    name=schedule.name,
                    state=schedule.state,
                ))
            if not schedule.line_ids:
                schedule._compute_recognition_schedule()
            # DR-002 SUM INVARIANT: verify line totals match the schedule total
            # before committing the draft -> confirmed transition. This is the
            # safety net for the `manual` recognition method (where the user
            # enters amounts by hand) and also validates auto-generated lines
            # against rounding drift.
            currency = schedule.currency_id or schedule.company_id.currency_id
            total_allocated = sum(schedule.line_ids.mapped('recognition_amount'))
            rounding = currency.rounding if currency else 0.01
            if not float_is_zero(
                schedule.total_amount - total_allocated,
                precision_rounding=rounding,
            ):
                raise UserError(_(
                    "Cannot confirm schedule %(name)s: recognition lines total "
                    "%(lines_total)s but schedule total is %(schedule_total)s. "
                    "Adjust the recognition lines so their sum equals the "
                    "schedule total before confirming (DR-002 sum invariant).",
                    name=schedule.name,
                    lines_total=(
                        currency.format(total_allocated)
                        if currency else total_allocated
                    ),
                    schedule_total=(
                        currency.format(schedule.total_amount)
                        if currency else schedule.total_amount
                    ),
                ))
            schedule.state = 'confirmed'
            schedule.message_post(
                body=_(
                    "Schedule confirmed. Generated %(count)s recognition lines totalling "
                    "%(amount)s.",
                    count=len(schedule.line_ids),
                    amount=schedule.currency_id.format(
                        sum(schedule.line_ids.mapped('recognition_amount')),
                    ),
                ),
            )
        return True

    def action_close(self):
        """Transition to ``closed``. Guards against unposted lines."""
        for schedule in self:
            if schedule.state != 'confirmed':
                raise UserError(_(
                    "Only confirmed schedules can be closed; %(name)s is %(state)s.",
                    name=schedule.name,
                    state=schedule.state,
                ))
            draft_lines = schedule.line_ids.filtered(lambda line: line.state == 'draft')
            if draft_lines:
                raise UserError(_(
                    "Cannot close schedule %(name)s: %(count)s recognition line(s) "
                    "are still pending. Post them via the cut-off wizard (DR-003) "
                    "or delete them first.",
                    name=schedule.name,
                    count=len(draft_lines),
                ))
            schedule.state = 'closed'
            schedule.message_post(body=_("Schedule closed."))
        return True

    def action_draft(self):
        """Revert ``confirmed`` -> ``draft``. Forbidden if any lines are posted."""
        for schedule in self:
            if schedule.state != 'confirmed':
                raise UserError(_(
                    "Only confirmed schedules can be reset to draft; %(name)s is %(state)s.",
                    name=schedule.name,
                    state=schedule.state,
                ))
            posted_lines = schedule.line_ids.filtered(lambda line: line.state == 'posted')
            if posted_lines:
                raise UserError(_(
                    "Cannot reset schedule %(name)s to draft: %(count)s recognition "
                    "line(s) have been posted. Reverse them first via the cut-off "
                    "wizard (DR-003 Scenario 5).",
                    name=schedule.name,
                    count=len(posted_lines),
                ))
            # Remove existing draft lines so user can reconfigure and regenerate
            schedule.line_ids.unlink()
            schedule.state = 'draft'
            schedule.message_post(body=_("Schedule reset to draft; recognition lines cleared."))
        return True

    # ------------------------------------------------------------------
    # Core allocation logic (DR-002)
    # ------------------------------------------------------------------
    def _compute_recognition_schedule(self):
        """Generate or recalculate recognition lines per ``recognition_method`` (DR-002).

        Behavior:
            * **straight_line**: equal ``total_amount / period_count`` per line; last line
              adjusted for rounding residual using company currency rounding.
            * **date_based**: prorated by calendar days in each month that falls within
              [start_date, end_date]. Handles partial periods at both ends.
            * **manual**: no-op - preserves existing user-entered lines.

        **Past-preserving recalculation (DR-002 Scenario 4)**: lines with ``state='posted'``
        are never touched; only FUTURE (``state='draft'``) lines are deleted and regenerated.

        Multi-currency (DR-002 Scenario 5): amounts are computed in ``currency_id``;
        ``amount_currency`` preservation happens when the cut-off wizard posts.

        Rounding: uses ``currency_id.round`` to ensure the sum of line amounts exactly
        equals ``total_amount`` (no accumulated rounding drift).
        """
        self.ensure_one()
        if self.recognition_method == 'manual':
            _logger.info(
                "Skipping auto-generation for manual schedule %s (user-defined lines preserved).",
                self.name,
            )
            return

        # DR-002 Scenario 4: preserve posted lines, regenerate only draft
        self.line_ids.filtered(lambda line: line.state == 'draft').unlink()
        posted_count = len(self.line_ids)
        remaining = self.total_amount - sum(self.line_ids.mapped('recognition_amount'))
        remaining_periods = self.period_count - posted_count
        if remaining_periods <= 0:
            _logger.info(
                "Schedule %s has no remaining periods to allocate (posted=%d, total=%d).",
                self.name, posted_count, self.period_count,
            )
            return

        currency = self.currency_id or self.company_id.currency_id

        new_line_vals = []
        if self.recognition_method == 'straight_line':
            per_period = currency.round(remaining / remaining_periods)
            running_total = 0.0
            for i in range(remaining_periods):
                # End-of-month recognition date for each period
                period_date = (
                    self.start_date
                    + relativedelta(months=posted_count + i + 1, days=-1)
                )
                # Last period: assign the rounding residual to avoid drift
                if i == remaining_periods - 1:
                    amount = currency.round(remaining - running_total)
                else:
                    amount = per_period
                    running_total += per_period
                new_line_vals.append({
                    'schedule_id': self.id,
                    'sequence': 10 * (posted_count + i + 1),
                    'recognition_date': period_date,
                    'recognition_amount': amount,
                })

        elif self.recognition_method == 'date_based':
            # Prorated by calendar days; each month's amount =
            # (days_in_month_within_range / total_days) * remaining.
            #
            # DR-002 Scenario 4 (past-preserving recalculation): when posted
            # lines already exist we MUST advance the cursor past months that
            # have posted lines, otherwise we would (a) create duplicate
            # ``recognition_date`` values colliding with posted records and
            # (b) under-allocate because ``remaining`` is the unposted amount
            # but ``total_days`` would otherwise span the full schedule range.
            # Re-anchor both the cursor and the denominator to the remaining
            # (unposted) window so numerator and denominator agree.
            #
            # IMPLEMENTATION NOTE: the loop's date-cursor variable is named
            # ``month_cursor`` rather than ``cursor`` to avoid a collision
            # with Odoo's ``odoo.tools.translate._get_cr(frame)`` helper,
            # which looks up ``frame.f_locals['cursor']`` as a fallback
            # mechanism to discover the active DB cursor when the
            # translation function ``_()`` needs to resolve the language.
            # Naming a ``datetime.date`` local ``cursor`` causes an
            # ``AssertionError`` (``isinstance(cr, BaseCursor)``) whenever
            # ``_()`` is invoked from this method (e.g. ``self.message_post(
            # body=_(...))`` at the bottom of this function) under a
            # test/empty-lang context that skips the ``self.env.lang``
            # early-return branch of ``_get_lang``. See translate.py line
            # ``if 'cursor' in frame.f_locals: return frame.f_locals['cursor']``.
            posted_lines = self.line_ids.filtered(
                lambda line: line.state == 'posted',
            )
            max_posted_date = max(
                posted_lines.mapped('recognition_date'),
                default=None,
            )
            if max_posted_date:
                # Advance to first day of the month AFTER the latest posted
                # recognition_date. relativedelta applies absolute terms
                # (``day=1``) before relative terms (``months=1``), so this
                # normalizes to 1st-of-next-month regardless of the posted
                # date's day-of-month.
                month_cursor = max_posted_date + relativedelta(day=1, months=1)
            else:
                # First-time generation: start at first of the schedule's
                # start-date month (existing behavior).
                month_cursor = self.start_date.replace(day=1)
            if month_cursor > self.end_date:
                # All recognition months are already posted; nothing to allocate.
                return
            # effective_start drives both the denominator and the first
            # month's proration. Using ``max(month_cursor, self.start_date)``
            # correctly handles: (a) posted-lines case — month_cursor is
            # later than start_date, so effective_start = month_cursor
            # (first of next unposted month); (b) initial generation with
            # mid-month start_date — month_cursor is first-of-month,
            # start_date is mid-month, so effective_start = start_date
            # (prorated first month).
            effective_start = max(month_cursor, self.start_date)
            total_days = (self.end_date - effective_start).days + 1
            if total_days <= 0:
                return
            sequence_counter = posted_count
            running_total = 0.0
            while month_cursor <= self.end_date:
                year, month = month_cursor.year, month_cursor.month
                # NOTE: use '_first_weekday' rather than '_' to avoid shadowing the
                # module-level translation function `_` via Python local-scope rules.
                _first_weekday, last_day = monthrange(year, month)
                month_start = month_cursor
                month_end = month_cursor.replace(day=last_day)
                period_start = max(month_start, effective_start)
                period_end = min(month_end, self.end_date)
                days_in_period = (period_end - period_start).days + 1
                amount = currency.round(remaining * days_in_period / total_days)
                # Advance month_cursor to first day of next month for next iteration
                next_month = month_cursor + relativedelta(months=1)
                is_last_iter = next_month > self.end_date
                if is_last_iter:
                    amount = currency.round(remaining - running_total)
                else:
                    running_total += amount
                sequence_counter += 1
                new_line_vals.append({
                    'schedule_id': self.id,
                    'sequence': 10 * sequence_counter,
                    'recognition_date': period_end,
                    'recognition_amount': amount,
                })
                month_cursor = next_month

        else:
            # Unknown recognition method - defensive guard
            raise UserError(_(
                "Unsupported recognition method %(method)s.",
                method=self.recognition_method,
            ))

        if new_line_vals:
            self.env['account.deferred.line'].create(new_line_vals)
            _logger.info(
                "Generated %d recognition lines for schedule %s (method=%s, remaining=%s).",
                len(new_line_vals), self.name, self.recognition_method, remaining,
            )
            self.message_post(body=_(
                "Generated %(count)s recognition lines (method: %(method)s).",
                count=len(new_line_vals),
                method=dict(self._fields['recognition_method'].selection)[self.recognition_method],
            ))

    # ------------------------------------------------------------------
    # Wizard entry point
    # ------------------------------------------------------------------
    def action_generate_cutoff(self):
        """Open the DR-003 cut-off wizard pre-filled with selected schedule(s).

        Called from the schedule form button "Generate Cut-off Entries". Opens the
        cut-off wizard (``account.deferred.cutoff.wizard`` - implemented in
        ``wizard/cutoff_wizard.py`` by the wizard-folder agent) with this schedule's
        ID(s) pre-selected. The wizard handles validation, preview, posting, and
        optional reversal (DR-003 Scenarios 1-6).
        """
        if not self:
            raise UserError(_("No schedules selected for cut-off generation."))
        if any(s.state != 'confirmed' for s in self):
            raise UserError(_(
                "Only confirmed schedules may be processed through the cut-off wizard.",
            ))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Generate Cut-off Entries'),
            'res_model': 'account.deferred.cutoff.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_schedule_ids': [(6, 0, self.ids)],
                'default_mode': 'single' if len(self) == 1 else 'batch',
            },
        }
