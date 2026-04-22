# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Res Partner Extensions — Payment Follow-ups
===========================================

Extends Odoo's core ``res.partner`` with per-partner aggregation of
overdue invoices, aging-bucket totals, and a Many2one link to the
currently-applicable ``account.followup.level``. These fields are the
runtime backbone of the PF-002 follow-up cron (which searches partners
with ``has_overdue_invoices=True``) and the four default mail templates
in ``data/mail_template_data.xml`` (which render ``object.total_overdue``
and iterate ``object._get_overdue_invoices()``).

Implements:
    - FEATURE-006 PF-001: Follow-up level configuration (partner-side
      linkage to ``account.followup.level``).
    - FEATURE-006 PF-005: Per-partner overdue aggregation
      (``total_overdue``, ``max_days_overdue``, aging buckets, auto
      level assignment).

Integration Notes:
    - Extends ``res.partner`` via ``_inherit`` (no core modifications).
    - Zero Enterprise module dependencies.
    - AGPL-3.0 licensing.
    - Uses the existing core ``invoice_ids`` One2many (defined in
      ``addons/account/models/partner.py`` line 562) to enumerate
      customer invoices without adding a new relation.
    - Uses the core ``currency_id`` (from ``_get_company_currency``) for
      Monetary-field precision.

Business Rules (PF-005):
    - Only POSTED customer invoices/refunds (``move_type in
      ('out_invoice', 'out_refund')``, ``state == 'posted'``) with
      ``payment_state in ('not_paid', 'partial')`` and a set
      ``invoice_date_due`` in the past contribute to overdue aggregates.
    - Supplier bills (``in_invoice``, ``in_refund``) are ALWAYS excluded
      from overdue aggregates (PF-005 BR-003).
    - Credit notes (``out_refund``) reduce ``total_overdue`` but do NOT
      populate aging buckets directly (the absolute ``amount_residual``
      on refunds offsets invoice amounts at the partner level).
    - Disputed invoices (``is_disputed=True``) are excluded from both
      ``total_overdue`` and aging buckets (PF-005 BR-005) so that
      customers are not dunned for amounts under review.

Rules Compliance (AAP §0.7):
    - R-01: No cross-module imports (imports only from ``odoo``).
    - R-02: No Enterprise references.
    - R-03: Uses ``_inherit`` only, no ``_name`` redefinition.
    - R-05 (tangential — R-05 targets account.move/account.move.line):
      All new fields are either computed (``has_overdue_invoices``,
      ``total_overdue``, aging buckets, ``max_days_overdue``,
      ``followup_level_id``, ``followup_next_action_date``,
      ``followup_status``) or simple additive relational fields
      (``followup_history_ids`` One2many reverse relation for PF-004
      chatter). No existing core field on ``res.partner`` is
      redefined.
    - R-07: No ``sudo()`` usage.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ResPartner(models.Model):
    """Customer partner extensions for payment follow-up workflows.

    Adds computed per-partner overdue aggregation fields
    (``has_overdue_invoices``, ``total_overdue``, aging buckets,
    ``max_days_overdue``), a computed ``followup_level_id`` that
    auto-selects the applicable escalation level based on
    ``max_days_overdue`` and each level's ``delay`` threshold, a
    computed ``followup_next_action_date`` that schedules the next
    dunning event, a ``followup_status`` selection reflecting the
    partner's follow-up state, and a ``followup_history_ids`` One2many
    reverse relation for PF-004 audit-trail navigation.

    The ``_get_overdue_invoices()`` method is the authoritative helper
    used by both the PF-002 cron (``account.followup.level.
    process_followup_emails``) and the four mail templates in
    ``data/mail_template_data.xml`` to enumerate the partner's
    open overdue customer invoices.
    """

    _inherit = 'res.partner'

    # -------------------------------------------------------------------------
    # PF-001 LEVEL ASSIGNMENT
    # -------------------------------------------------------------------------

    followup_level_id = fields.Many2one(
        comodel_name='account.followup.level',
        string='Current Follow-up Level',
        compute='_compute_followup_level',
        store=True,
        index=True,
        help=(
            'Applicable follow-up level for this partner, computed from the '
            'maximum days-overdue across all the partner\'s open customer '
            'invoices. Recomputed whenever an invoice is posted, paid, or '
            'modified. See PF-001 for level thresholds (7/14/21/30 days) '
            'and PF-005 for the BR-002 recalculation triggers.'
        ),
    )

    followup_next_action_date = fields.Date(
        string='Next Follow-up Date',
        compute='_compute_followup_next_action',
        store=True,
        index=True,
        help=(
            'Next scheduled follow-up action date. Typically computed as '
            'the earliest invoice due date plus the current level\'s delay '
            'threshold, representing the soonest date the PF-002 cron will '
            'include this partner in a batch. Overridden by the cron itself '
            'after each dunning touch.'
        ),
    )

    followup_status = fields.Selection(
        selection=[
            ('no_action_needed', 'No Action Needed'),
            ('in_followup', 'In Follow-up'),
            ('no_response', 'No Response'),
            ('done', 'Done'),
            ('need_review', 'Needs Review'),
        ],
        string='Follow-up Status',
        compute='_compute_followup_status',
        store=True,
        default='no_action_needed',
        help=(
            'Follow-up state summarising the partner\'s current position in '
            'the dunning ladder:\n'
            ' * No Action Needed: No overdue invoices or all disputed.\n'
            ' * In Follow-up: Has overdue invoices with an assigned level.\n'
            ' * No Response: In follow-up for more than 60 days overdue.\n'
            ' * Done: All overdue invoices resolved.\n'
            ' * Needs Review: Requires manual intervention (disputed, '
            'over-90-day aging, or missing level).'
        ),
    )

    # -------------------------------------------------------------------------
    # PF-005 OVERDUE AGGREGATION
    # -------------------------------------------------------------------------

    has_overdue_invoices = fields.Boolean(
        string='Has Overdue Invoices',
        compute='_compute_overdue_aggregates',
        store=True,
        index=True,
        help=(
            'True when the partner has at least one open overdue customer '
            'invoice (posted, unpaid or partial, past due, non-disputed). '
            'Indexed to support the fast domain search performed by the '
            'PF-002 cron (process_followup_emails) against thousands of '
            'partner records.'
        ),
    )

    total_overdue = fields.Monetary(
        string='Total Overdue',
        compute='_compute_overdue_aggregates',
        store=True,
        currency_field='currency_id',
        help=(
            'Sum of open residual amounts across all the partner\'s overdue '
            'customer invoices, net of any open customer refunds '
            '(out_refund). Disputed invoices (is_disputed=True) are '
            'excluded per PF-005 BR-005. Used by mail-template summary '
            'sections (object.total_overdue).'
        ),
    )

    max_days_overdue = fields.Integer(
        string='Max Days Overdue',
        compute='_compute_overdue_aggregates',
        store=True,
        help=(
            'Maximum days-overdue across all open customer invoices for '
            'this partner. Drives the automatic follow-up level selection '
            '(followup_level_id) by comparing against each level\'s delay '
            'threshold.'
        ),
    )

    aging_bucket_current = fields.Monetary(
        string='Current (Not Due)',
        compute='_compute_overdue_aggregates',
        store=True,
        currency_field='currency_id',
        help=(
            'Open customer invoice residual amounts that are NOT yet '
            'overdue (due today or in the future). Useful for aging '
            'reports that present both current and overdue buckets '
            'side-by-side.'
        ),
    )

    aging_bucket_1_30 = fields.Monetary(
        string='1-30 Days Overdue',
        compute='_compute_overdue_aggregates',
        store=True,
        currency_field='currency_id',
        help=(
            'Sum of residual amounts on customer invoices that are 1-30 '
            'days past due. Disputed invoices are excluded. Used by '
            'partner-card aging summary and PF-003 follow-up reports.'
        ),
    )

    aging_bucket_31_60 = fields.Monetary(
        string='31-60 Days Overdue',
        compute='_compute_overdue_aggregates',
        store=True,
        currency_field='currency_id',
        help=(
            'Sum of residual amounts on customer invoices that are 31-60 '
            'days past due. Disputed invoices are excluded.'
        ),
    )

    aging_bucket_61_90 = fields.Monetary(
        string='61-90 Days Overdue',
        compute='_compute_overdue_aggregates',
        store=True,
        currency_field='currency_id',
        help=(
            'Sum of residual amounts on customer invoices that are 61-90 '
            'days past due. Disputed invoices are excluded.'
        ),
    )

    aging_bucket_90_plus = fields.Monetary(
        string='90+ Days Overdue',
        compute='_compute_overdue_aggregates',
        store=True,
        currency_field='currency_id',
        help=(
            'Sum of residual amounts on customer invoices that are more '
            'than 90 days past due. Disputed invoices are excluded. '
            'High values in this bucket indicate bad-debt risk.'
        ),
    )

    # -------------------------------------------------------------------------
    # PF-004 HISTORY BACK-REFERENCE
    # -------------------------------------------------------------------------

    followup_history_ids = fields.One2many(
        comodel_name='account.followup.history',
        inverse_name='partner_id',
        string='Follow-up History',
        help=(
            'Immutable audit trail of every follow-up action taken against '
            'this partner (emails sent, phone calls logged, letters issued, '
            'meeting notes, payment promises). PF-004 BR-003 enforces that '
            'records are never modified or deleted after creation.'
        ),
    )

    followup_history_count = fields.Integer(
        string='Follow-up History Count',
        compute='_compute_followup_history_count',
        help=(
            'Number of follow-up history records logged against this '
            'partner. Displayed as a smart-button badge on the partner '
            'form when views are added in subsequent checkpoints.'
        ),
    )

    # -------------------------------------------------------------------------
    # COMPUTE METHODS — OVERDUE AGGREGATION
    # -------------------------------------------------------------------------

    @api.depends(
        'invoice_ids',
        'invoice_ids.state',
        'invoice_ids.move_type',
        'invoice_ids.payment_state',
        'invoice_ids.invoice_date_due',
        'invoice_ids.amount_residual',
        'invoice_ids.is_disputed',
        'invoice_ids.days_overdue',
    )
    def _compute_overdue_aggregates(self):
        """Aggregate open overdue customer invoices per partner.

        Business Rules (PF-005):
            - Customer invoices and refunds only (``move_type`` in
              ``('out_invoice', 'out_refund')``).
            - Posted moves only (``state == 'posted'``).
            - Unpaid or partially paid only (``payment_state`` in
              ``('not_paid', 'partial')``).
            - Disputed moves (``is_disputed=True``) are excluded from
              overdue totals and aging buckets but still appear in
              ``aging_bucket_current`` calculations (they remain open
              receivables; they just don't contribute to dunning).

        For refunds (``out_refund``), ``amount_residual`` is negative-
        effective (it reduces the partner's receivable balance); we
        subtract it from ``total_overdue`` by including it with its
        natural signed value. Aging buckets aggregate only positive
        residual amounts so refunds do not create negative bucket
        balances; the net effect is applied at the ``total_overdue``
        level only.
        """
        today = fields.Date.context_today(self)
        for partner in self:
            total_overdue = 0.0
            max_days = 0
            bucket_current = 0.0
            bucket_1_30 = 0.0
            bucket_31_60 = 0.0
            bucket_61_90 = 0.0
            bucket_90_plus = 0.0
            has_overdue = False

            for inv in partner.invoice_ids:
                # Only customer side (refunds included for net-total).
                if inv.move_type not in ('out_invoice', 'out_refund'):
                    continue
                # Posted only.
                if inv.state != 'posted':
                    continue
                # Unpaid / partial only.
                if inv.payment_state not in ('not_paid', 'partial'):
                    continue

                residual = inv.amount_residual or 0.0

                # Residual sign convention:
                #   out_invoice -> positive residual (customer owes us)
                #   out_refund -> usually positive residual on the refund
                #                 record, but REDUCES the partner's
                #                 receivable balance at the partner level
                # Apply a sign flip for refunds when aggregating totals.
                signed_residual = (
                    -residual if inv.move_type == 'out_refund' else residual
                )

                # Not-yet-due invoices populate aging_bucket_current
                # regardless of dispute status (they are open receivables).
                if not inv.invoice_date_due:
                    bucket_current += residual
                    continue

                delta = (today - inv.invoice_date_due).days
                if delta <= 0:
                    # Due today or in the future.
                    bucket_current += residual
                    continue

                # Overdue beyond grace (delta >= 1). Disputed invoices
                # are excluded from overdue totals per PF-005 BR-005.
                if inv.is_disputed:
                    continue

                # Non-disputed overdue invoice/refund — include in totals.
                total_overdue += signed_residual
                has_overdue = True

                if delta > max_days:
                    max_days = delta

                # Aging buckets: only positive residual amounts (i.e.,
                # invoices) populate aging buckets; refunds net against
                # total_overdue only.
                if inv.move_type == 'out_invoice':
                    if delta <= 30:
                        bucket_1_30 += residual
                    elif delta <= 60:
                        bucket_31_60 += residual
                    elif delta <= 90:
                        bucket_61_90 += residual
                    else:
                        bucket_90_plus += residual

            # Commit computed values.
            partner.has_overdue_invoices = has_overdue
            partner.total_overdue = total_overdue
            partner.max_days_overdue = max_days
            partner.aging_bucket_current = bucket_current
            partner.aging_bucket_1_30 = bucket_1_30
            partner.aging_bucket_31_60 = bucket_31_60
            partner.aging_bucket_61_90 = bucket_61_90
            partner.aging_bucket_90_plus = bucket_90_plus

    # -------------------------------------------------------------------------
    # COMPUTE METHODS — LEVEL / STATUS
    # -------------------------------------------------------------------------

    @api.depends('max_days_overdue', 'company_id')
    def _compute_followup_level(self):
        """Select the highest-``delay`` active level whose threshold is met.

        Iterates the active ``account.followup.level`` records in the
        partner's company, ordered by ``delay`` ascending, and picks the
        highest level whose ``delay`` is <= the partner's
        ``max_days_overdue``. A partner with zero days overdue gets no
        level (``followup_level_id = False``).

        Multi-company handling:
            - Levels with ``company_id = False`` (global templates) apply
              to all companies per the ir.rule in
              ``security/followup_security.xml``.
            - Levels with a specific ``company_id`` apply only to partners
              in the same company context.
        """
        # Fetch all active levels for partners' companies in one pass.
        Level = self.env['account.followup.level']
        for partner in self:
            if not partner.max_days_overdue or partner.max_days_overdue <= 0:
                partner.followup_level_id = False
                continue

            # Company-scoped level lookup, allowing global templates.
            # ORM's automatic company domain enforces multi-company isolation.
            company = partner.company_id or self.env.company
            domain = [
                ('active', '=', True),
                '|',
                ('company_id', '=', False),
                ('company_id', '=', company.id),
                ('delay', '<=', partner.max_days_overdue),
            ]
            applicable = Level.search(domain, order='delay desc', limit=1)
            partner.followup_level_id = applicable.id if applicable else False

    @api.depends('followup_level_id', 'followup_level_id.delay', 'max_days_overdue')
    def _compute_followup_next_action(self):
        """Compute the next scheduled follow-up action date.

        Semantics:
            - If no level applies (no overdue or before first level's
              threshold): next action is in the future when the earliest
              overdue invoice would cross the first level's delay. For
              simplicity at this checkpoint we use today + level.delay
              when there is NO current level but there ARE overdue
              invoices; False otherwise.
            - If a level applies, next action date is today (the cron
              should pick this partner up on its next run).

        The cron (``process_followup_emails``) overrides this field
        after each dunning touch to project the next contact date
        forward (``today + level.delay``).
        """
        today = fields.Date.context_today(self)
        for partner in self:
            if partner.followup_level_id:
                partner.followup_next_action_date = today
            elif partner.max_days_overdue and partner.max_days_overdue > 0:
                # Has overdue but below first level threshold.
                partner.followup_next_action_date = today
            else:
                partner.followup_next_action_date = False

    @api.depends(
        'has_overdue_invoices',
        'followup_level_id',
        'max_days_overdue',
        'aging_bucket_90_plus',
    )
    def _compute_followup_status(self):
        """Classify partner's overall follow-up state into a Selection.

        Mapping:
            - ``no_action_needed``: No overdue invoices.
            - ``in_followup``: Has overdue invoices with an assigned level.
            - ``no_response``: Overdue > 60 days (indicates non-response
              to earlier communications).
            - ``done``: Previously overdue but now cleared (currently
              indistinguishable from ``no_action_needed`` without
              history; retained as selection for future enhancement).
            - ``need_review``: Has overdue > 90 days or has overdue but
              no matching level (e.g., below first threshold or all
              levels inactive).
        """
        for partner in self:
            if not partner.has_overdue_invoices:
                partner.followup_status = 'no_action_needed'
                continue

            # Partner has overdue invoices.
            if partner.aging_bucket_90_plus and partner.aging_bucket_90_plus > 0:
                partner.followup_status = 'need_review'
            elif (
                partner.max_days_overdue and partner.max_days_overdue > 60
                and not partner.followup_level_id
            ):
                partner.followup_status = 'no_response'
            elif partner.followup_level_id:
                partner.followup_status = 'in_followup'
            else:
                # Has overdue but no level matched (below first threshold).
                partner.followup_status = 'need_review'

    # -------------------------------------------------------------------------
    # COMPUTE METHODS — CHATTER COUNT
    # -------------------------------------------------------------------------

    def _compute_followup_history_count(self):
        """Count of follow-up history records per partner (non-stored).

        Used by partner-form smart buttons in subsequent-checkpoint views
        to render a badge with the number of historical touches.
        """
        History = self.env['account.followup.history']
        for partner in self:
            partner.followup_history_count = History.search_count(
                [('partner_id', '=', partner.id)],
            )

    # -------------------------------------------------------------------------
    # HELPERS CONSUMED BY CRON + MAIL TEMPLATES
    # -------------------------------------------------------------------------

    def _get_overdue_invoices(self):
        """Return open overdue customer invoice recordset for this partner.

        This is the **authoritative** helper consumed by:
            - ``account.followup.level.process_followup_emails()`` at
              ``models/account_followup_level.py`` line 519, which
              iterates each partner's overdue invoices to populate
              history records and optional PDF attachments.
            - All four default mail templates in
              ``data/mail_template_data.xml``, which use QWeb
              ``t-foreach`` over ``object._get_overdue_invoices()`` to
              render the overdue-invoice table in each dunning email.

        Filter criteria (PF-005):
            - ``move_type in ('out_invoice', 'out_refund')`` — customer
              side only; supplier bills are NEVER included per BR-003.
            - ``state == 'posted'`` — draft/cancelled moves are not
              dunning candidates.
            - ``payment_state in ('not_paid', 'partial')`` — fully-paid
              moves do not need dunning.
            - ``invoice_date_due`` set AND strictly less than today —
              excludes future-due and exactly-today-due moves.
            - ``is_disputed == False`` — disputed moves are excluded
              from dunning correspondence per BR-005 even though they
              remain in the open-receivable aging view.

        Ordering: by ``invoice_date_due`` ascending, then ``name``
        ascending, so the oldest overdue invoice appears first in
        email tables — consistent with collection best practice.

        :return: ``account.move`` recordset (may be empty) filtered to
            the current partner's open overdue customer invoices.
        """
        self.ensure_one()
        today = fields.Date.context_today(self)
        return self.invoice_ids.filtered(
            lambda m: (
                m.move_type in ('out_invoice', 'out_refund')
                and m.state == 'posted'
                and m.payment_state in ('not_paid', 'partial')
                and m.invoice_date_due
                and m.invoice_date_due < today
                and not m.is_disputed
            ),
        ).sorted(key=lambda m: (m.invoice_date_due, m.name or ''))

    # -------------------------------------------------------------------------
    # ACTION METHODS
    # -------------------------------------------------------------------------

    def action_view_followup_history(self):
        """Smart-button handler: open this partner's follow-up history.

        Returns an Odoo action dict that opens the partner's history
        records in a list view, filtered by ``partner_id``. Views and
        menu wiring are added in a subsequent checkpoint; this action
        is future-proofed so it returns the correct structure even
        before those views exist (Odoo gracefully falls back to the
        default view types).
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Follow-up History'),
            'res_model': 'account.followup.history',
            'view_mode': 'list,form',
            'domain': [('partner_id', '=', self.id)],
            'context': {
                'default_partner_id': self.id,
                'default_company_id': (
                    self.company_id.id or self.env.company.id
                ),
            },
        }

    def action_send_followup_now(self):
        """Trigger an immediate follow-up email send for this partner.

        Manual-trigger handler bound to the "Send Follow-up Now" button on
        the partner form (PF-001/PF-002). Validates that the partner has a
        current follow-up level and overdue invoices, then delegates to
        :meth:`account.followup.level.process_followup_emails` with the
        ``active_partner_ids`` context populated so the level's partner
        resolver (``_get_applicable_partners``) restricts processing to
        this single partner only.

        The downstream ``process_followup_emails`` method handles all
        business-rule enforcement (BR-004 active-level guard, minimum
        amount threshold, email-template presence, attachment rendering,
        history record creation, and trigger-action side-effects). This
        wrapper only performs the minimal pre-flight checks necessary for
        a clean user-facing error message and returns a UI notification
        summarising the outcome.

        Returns:
            dict: ``ir.actions.client`` notification confirming dispatch
            (or surfacing the user-visible error via ``UserError``).

        Raises:
            UserError: If the partner has no current follow-up level or
                no overdue invoices to communicate.
        """
        self.ensure_one()
        if not self.followup_level_id:
            raise UserError(_(
                "Partner %(partner)s has no current follow-up level; "
                "nothing to send.",
                partner=self.display_name,
            ))
        if not self.has_overdue_invoices:
            raise UserError(_(
                "Partner %(partner)s has no overdue invoices; "
                "follow-up is not applicable.",
                partner=self.display_name,
            ))
        # Delegate to the level's batch pipeline scoped to this partner
        # via the documented ``active_partner_ids`` context key
        # (see account.followup.level._get_applicable_partners).
        self.followup_level_id.with_context(
            active_partner_ids=[self.id],
        ).process_followup_emails()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Follow-up Sent"),
                'message': _(
                    "Follow-up email for level '%(level)s' has been "
                    "queued for %(partner)s.",
                    level=self.followup_level_id.name,
                    partner=self.display_name,
                ),
                'type': 'success',
                'sticky': False,
            },
        }
