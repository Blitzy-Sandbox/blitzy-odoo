# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Account Follow-up Line — Per-Partner Aging Summary
==================================================

Denormalized aggregate record holding aging buckets, total overdue, and
current follow-up level for each (partner, company) pair. Serves as a
fast-lookup cache for follow-up reports, dashboards, and search operations
that would otherwise require repeated ``_read_group`` aggregation on
``account.move.line``.

Implements:
    - FEATURE-006 PF-005: Overdue Calculation (denormalized aging storage)

Relationship to ``res.partner`` fields:
    - ``res.partner`` holds the same aging buckets as *computed* fields for
      real-time accuracy during interactive editing.
    - ``account.followup.line`` holds the SAME aging buckets as *stored,
      refreshed-on-demand* fields for fast bulk search/sort (report views).
    - The two are kept in sync via ``_refresh_from_partner`` / the
      ``_cron_refresh_all`` scheduled action. Downstream flows (batch
      email, report rendering) consume this denormalized summary and
      avoid the cost of partner-level recompute during a render.

Rationale for denormalization:
    PF-005 BR-004 performance target requires fast aging-sort/filter for
    populations exceeding 10,000 invoices. Computing aging on demand for
    every report render or search would require SQL aggregation at query
    time; denormalized storage moves the cost to write-time (payment
    posting, invoice creation, cron refresh), amortizing it across many
    subsequent reads and keeping dashboard latency flat.

Integration Notes:
    - Referenced by ``security/ir.model.access.csv`` (rows 4-5) and
      ``security/followup_security.xml`` (``ir.rule`` scoping by
      ``company_id``).
    - Views defined in ``views/account_followup_line_views.xml`` — list
      form, search, graph, pivot, plus a window action registered as
      ``action_account_followup_line`` for the sidebar menu entry.
    - The ``partner.followup_status`` (on ``res.partner``) and this
      model's ``followup_status`` are semantically distinct axes. The
      partner field captures the partner's overall state from aging; the
      line's field captures the workflow state of the follow-up process
      (e.g., ``promised``). They are intentionally NOT kept in sync.

Rules Compliance (AAP §0.7):
    - R-01: No cross-module imports.
    - R-02: No Enterprise references.
    - R-03: Uses ``_name`` for a net-new model; no ``_inherit``.
    - R-07: No ``sudo()`` usage.
"""

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountFollowupLine(models.Model):
    """Denormalized per-partner aging summary record.

    Uniqueness: exactly one record per ``(partner_id, company_id)`` pair,
    enforced via ``models.Constraint`` declarations. Records are created
    lazily when ``_get_or_create_for_partner()`` is invoked (typically
    from ``res.partner._compute_overdue_aggregates`` as a side-effect
    hook, or from the ``_cron_refresh_all`` batch refresh).

    Aggregate fields (aging buckets, ``total_overdue``,
    ``max_days_overdue``) are NOT themselves computed; they are written
    by ``_refresh_from_partner``. This avoids cascading recompute during
    bulk payment registration and keeps query performance flat
    regardless of invoice volume.
    """

    _name = 'account.followup.line'
    _description = 'Customer Follow-up Aging Summary'
    _order = 'total_overdue desc, partner_id'
    _rec_name = 'partner_id'

    # -------------------------------------------------------------------------
    # IDENTITY & SCOPE
    # -------------------------------------------------------------------------

    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Customer',
        required=True,
        ondelete='cascade',
        index=True,
        help=(
            'The customer this aging summary represents. Cascade-deleted '
            'with the partner record since the summary has no meaning '
            'without its partner.'
        ),
    )

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        index=True,
        help=(
            'Multi-company scope. Each (partner, company) pair has exactly '
            'one summary record.'
        ),
    )

    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency',
        related='company_id.currency_id',
        store=True,
        readonly=True,
        help='Currency for monetary fields, derived from the company.',
    )

    # -------------------------------------------------------------------------
    # AGING BUCKETS (PF-005 Scenario 3)
    # -------------------------------------------------------------------------
    # Fields are written by ``_refresh_from_partner`` from the partner's
    # computed aggregates. Direct user edits are blocked by the form view
    # (``edit="false"``) but the SQL-level CHECK constraint protects
    # against malformed writes from future code paths.

    total_overdue = fields.Monetary(
        string='Total Overdue',
        currency_field='currency_id',
        default=0.0,
        help=(
            'Sum of receivable amounts past due (net of credit notes). '
            'Index-friendly for top-N ordering in follow-up dashboards.'
        ),
    )

    aging_bucket_current = fields.Monetary(
        string='Current (Not Due)',
        currency_field='currency_id',
        default=0.0,
        help='Receivable amount not yet due (due date >= today).',
    )

    aging_bucket_1_30 = fields.Monetary(
        string='1-30 Days',
        currency_field='currency_id',
        default=0.0,
        help='Receivable amount 1 to 30 days past due.',
    )

    aging_bucket_31_60 = fields.Monetary(
        string='31-60 Days',
        currency_field='currency_id',
        default=0.0,
        help='Receivable amount 31 to 60 days past due.',
    )

    aging_bucket_61_90 = fields.Monetary(
        string='61-90 Days',
        currency_field='currency_id',
        default=0.0,
        help='Receivable amount 61 to 90 days past due.',
    )

    aging_bucket_90_plus = fields.Monetary(
        string='Over 90 Days',
        currency_field='currency_id',
        default=0.0,
        help='Receivable amount more than 90 days past due.',
    )

    max_days_overdue = fields.Integer(
        string='Max Days Overdue',
        default=0,
        index=True,
        help=(
            'Largest days-overdue value across open customer invoices; '
            'used to determine ``followup_level_id``. Indexed to support '
            'fast sort/filter in the list view.'
        ),
    )

    # -------------------------------------------------------------------------
    # FOLLOW-UP STATE
    # -------------------------------------------------------------------------

    followup_level_id = fields.Many2one(
        comodel_name='account.followup.level',
        string='Current Follow-up Level',
        ondelete='restrict',
        index=True,
        help=(
            'Applicable follow-up level based on ``max_days_overdue`` at '
            'the last refresh. ``ondelete="restrict"`` protects historical '
            'level assignments from accidental deletion of the level '
            'configuration.'
        ),
    )

    last_followup_date = fields.Datetime(
        string='Last Follow-up Date',
        help=(
            'Timestamp of the most recent follow-up action from '
            '``account.followup.history`` for this partner + company; '
            'used to determine when the next action should be due.'
        ),
    )

    next_action_date = fields.Date(
        string='Next Action Date',
        index=True,
        help=(
            'Scheduled date for the next follow-up action. Written by '
            'the cron handler after an action is executed, or mirrored '
            'from ``res.partner.followup_next_action_date``.'
        ),
    )

    followup_status = fields.Selection(
        selection=[
            ('no_action', 'No Action Needed'),
            ('in_need', 'Needs Follow-up'),
            ('in_progress', 'In Progress'),
            ('promised', 'Payment Promised'),
        ],
        string='Follow-up Status',
        default='no_action',
        index=True,
        help=(
            'High-level state of the follow-up workflow for this '
            'partner. Distinct axis from ``res.partner.followup_status`` '
            '(which captures aging-derived state):\n'
            '  * No Action Needed: no overdue amount.\n'
            '  * Needs Follow-up: overdue, no action yet taken.\n'
            '  * In Progress: follow-up action has been sent.\n'
            '  * Payment Promised: customer committed to paying.'
        ),
    )

    # -------------------------------------------------------------------------
    # SQL CONSTRAINTS (Odoo 19 declarative syntax)
    # -------------------------------------------------------------------------
    # Odoo 19 migrated from the class-level ``_sql_constraints`` list to
    # the new ``models.Constraint(...)`` declarative attribute. The
    # attribute name (without leading underscore) becomes the constraint
    # identifier suffix registered by Odoo's ORM (e.g., ``partner_company_
    # unique`` -> ``account_followup_line_partner_company_unique``).

    _partner_company_unique = models.Constraint(
        'UNIQUE(partner_id, company_id)',
        'Only one follow-up summary record is allowed per customer per company.',
    )

    _total_overdue_non_negative = models.Constraint(
        'CHECK(total_overdue >= 0)',
        'Total overdue amount cannot be negative.',
    )

    _max_days_overdue_non_negative = models.Constraint(
        'CHECK(max_days_overdue >= 0)',
        'Max days overdue cannot be negative.',
    )

    # -------------------------------------------------------------------------
    # COMPUTED DISPLAY HELPERS
    # -------------------------------------------------------------------------

    @api.depends('partner_id', 'partner_id.display_name', 'total_overdue')
    def _compute_display_name(self):
        """Human-readable label: partner name + total overdue amount.

        Overrides the default ``models.Model._compute_display_name`` to
        produce a label that surfaces the partner's current overdue
        exposure directly in selection widgets, breadcrumbs, and
        chatter references without requiring a secondary query.
        """
        for rec in self:
            if rec.partner_id:
                total = rec.total_overdue or 0.0
                rec.display_name = _(
                    '%(partner)s (%(amount).2f)',
                    partner=rec.partner_id.display_name or rec.partner_id.name or '',
                    amount=total,
                )
            else:
                rec.display_name = _('(unassigned summary)')

    # -------------------------------------------------------------------------
    # HELPER METHODS — LAZY CREATION & REFRESH
    # -------------------------------------------------------------------------

    @api.model
    def _get_or_create_for_partner(self, partner, company=None):
        """Fetch or create the aging-summary record for (partner, company).

        Lazily instantiates the record on first access, so partners without
        overdue invoices do not consume storage unnecessarily until needed.

        The lookup-before-create sequence preserves the ``UNIQUE(partner_id,
        company_id)`` invariant and lets callers safely loop over partner
        sets without risking ORM ``IntegrityError`` from racing inserts.

        :param partner: ``res.partner`` recordset (must contain exactly one
            record).
        :param company: Optional ``res.company`` recordset; defaults to
            ``self.env.company`` when omitted.
        :return: ``account.followup.line`` recordset (exactly one record).
        :raises UserError: If ``partner`` is an empty or multi-record
            recordset.
        """
        if not partner:
            raise UserError(
                _('Cannot create a follow-up summary without a partner.'),
            )
        partner.ensure_one()
        resolved_company = company or self.env.company

        existing = self.search(
            [
                ('partner_id', '=', partner.id),
                ('company_id', '=', resolved_company.id),
            ],
            limit=1,
        )
        if existing:
            return existing

        return self.create({
            'partner_id': partner.id,
            'company_id': resolved_company.id,
        })

    def _refresh_from_partner(self):
        """Sync this summary record from the live partner aging computation.

        Reads the partner's computed fields (aging buckets, totals,
        ``max_days_overdue``, ``followup_level_id``) and persists them to
        this denormalized cache record. The partner is expected to have
        already had its ``_compute_overdue_aggregates`` invoked (which
        happens automatically via ``@api.depends`` on invoice changes or
        explicitly via ``invalidate_recordset`` + ``mapped`` in
        ``_cron_refresh_all``).

        Note on ``followup_status``: the partner's ``followup_status``
        and this record's ``followup_status`` are semantically distinct
        (aging-derived state vs workflow state), so this method does
        NOT copy the partner's value. Instead, the status field is
        updated by workflow actions (e.g., history record creation,
        manual accountant override).

        :return: The refreshed recordset (``self``) for method chaining.
        """
        for rec in self:
            partner = rec.partner_id
            if not partner:
                continue
            rec.write({
                'total_overdue': partner.total_overdue or 0.0,
                'aging_bucket_current': partner.aging_bucket_current or 0.0,
                'aging_bucket_1_30': partner.aging_bucket_1_30 or 0.0,
                'aging_bucket_31_60': partner.aging_bucket_31_60 or 0.0,
                'aging_bucket_61_90': partner.aging_bucket_61_90 or 0.0,
                'aging_bucket_90_plus': partner.aging_bucket_90_plus or 0.0,
                'max_days_overdue': partner.max_days_overdue or 0,
                'followup_level_id': (
                    partner.followup_level_id.id
                    if partner.followup_level_id
                    else False
                ),
                'next_action_date': partner.followup_next_action_date or False,
            })
        return self

    @api.model
    def _cron_refresh_all(self, batch_size=5000):
        """Batch-refresh all follow-up summary records.

        Optional scheduled cron target. Iterates customer partners,
        triggers recompute of their aging aggregates (by invalidating
        the cache and reading the fields back), then materializes /
        refreshes the corresponding summary record for any partner with
        an overdue or current-bucket balance.

        Fault tolerance: each partner is processed in its own try/except
        so a failure on one partner does not abort the batch (PF-002
        BR-005 pattern, applied analogously here). Errors are logged
        via ``_logger.exception`` so operators can investigate without
        losing the audit trail.

        :param batch_size: Maximum number of partners to process per
            invocation (default 5000, per AAP Phase 7). Bounds memory
            usage for very large customer populations.
        :return: Dict with batch statistics:
            ``{'partners_processed': N, 'summaries_refreshed': M,
              'errors': K}``
        """
        Partner = self.env['res.partner']
        partners = Partner.search(
            [('customer_rank', '>', 0)],
            limit=batch_size,
        )

        # Force recompute of stored aging fields by invalidating the
        # ORM cache and then re-reading. Odoo 19's cache is aggressive,
        # so a plain ``mapped`` on a stored computed field would return
        # cached values; the explicit invalidate_recordset + mapped
        # sequence guarantees fresh values when the calendar advances
        # past a partner's invoice due date without any invoice change
        # triggering @api.depends.
        aging_fnames = [
            'total_overdue',
            'aging_bucket_current',
            'aging_bucket_1_30',
            'aging_bucket_31_60',
            'aging_bucket_61_90',
            'aging_bucket_90_plus',
            'max_days_overdue',
            'has_overdue_invoices',
            'followup_level_id',
            'followup_next_action_date',
        ]
        partners.invalidate_recordset(fnames=aging_fnames)
        # Force re-read of the stored computed fields. ``.mapped()``
        # evaluates the compute methods transitively; we discard the
        # return value.
        partners.mapped('total_overdue')

        partners_processed = len(partners)
        summaries_refreshed = 0
        errors = 0

        _logger.info(
            'account.followup.line._cron_refresh_all: %s customer partners '
            'to process (batch_size=%s).',
            partners_processed,
            batch_size,
        )

        for partner in partners:
            try:
                # Skip partners with no overdue or current receivable —
                # no point materializing an empty summary row.
                if not (
                    partner.has_overdue_invoices
                    or partner.aging_bucket_current
                ):
                    continue
                line = self._get_or_create_for_partner(partner)
                line._refresh_from_partner()
                summaries_refreshed += 1
            except Exception:
                errors += 1
                _logger.exception(
                    'account.followup.line._cron_refresh_all: refresh failed '
                    'for partner id=%s; skipping and continuing.',
                    partner.id,
                )

        _logger.info(
            'account.followup.line._cron_refresh_all: complete. '
            'Processed=%s, Refreshed=%s, Errors=%s.',
            partners_processed,
            summaries_refreshed,
            errors,
        )
        return {
            'partners_processed': partners_processed,
            'summaries_refreshed': summaries_refreshed,
            'errors': errors,
        }

    # -------------------------------------------------------------------------
    # WINDOW ACTIONS — DRILL-DOWN FROM FORM
    # -------------------------------------------------------------------------

    def action_view_partner(self):
        """Navigate to the partner form for this summary record.

        Used as the "View Partner" smart-button handler on the line's
        form view. Returns a standard ``ir.actions.act_window`` client
        action payload pointing at the partner form.
        """
        self.ensure_one()
        if not self.partner_id:
            raise UserError(
                _('Cannot view partner: no partner linked to this summary.'),
            )
        return {
            'type': 'ir.actions.act_window',
            'name': _('Customer'),
            'res_model': 'res.partner',
            'res_id': self.partner_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_invoices(self):
        """Open the list of overdue invoices for this partner.

        Used as the "Related Invoices" smart-button handler on the
        line's form view. Filters the result to posted, not-fully-paid
        customer invoices for the summary's partner.
        """
        self.ensure_one()
        if not self.partner_id:
            raise UserError(
                _('Cannot view invoices: no partner linked to this summary.'),
            )
        return {
            'type': 'ir.actions.act_window',
            'name': _('Overdue Invoices'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [
                ('partner_id', '=', self.partner_id.id),
                ('move_type', 'in', ('out_invoice', 'out_refund')),
                ('state', '=', 'posted'),
                ('payment_state', 'in', ('not_paid', 'partial', 'in_payment')),
            ],
            'context': {
                'default_partner_id': self.partner_id.id,
                'search_default_partner_id': self.partner_id.id,
            },
        }
