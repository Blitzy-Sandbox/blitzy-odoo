# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Account Follow-up History — Immutable Audit Trail
==================================================

Defines the ``account.followup.history`` model, an append-only ledger of every
follow-up action (email, letter, phone call, meeting, payment promise, status
change, note, SMS) taken against a customer's overdue receivables.

Implements
----------
- FEATURE-006 PF-004: Action History Tracking (complete story)

Business Rules Enforced
-----------------------
- **BR-001**: Automatic history creation on email dispatch (enforced by
  the caller ``account.followup.level.process_followup_emails()`` in
  ``account_followup_level.py``; this model provides the create() entry
  point and the required persistence surface).
- **BR-002**: Manual creation is permitted for non-email actions (phone,
  letter, meeting, etc.) via the standard Odoo form view.
- **BR-003**: **Immutability** — ``write()`` and ``unlink()`` are blocked
  for non-superuser contexts; only chatter/activity-mixin fields and a
  tightly-controlled whitelist of audit-safe fields may be updated
  post-creation. Superuser (``env.su``) bypass is preserved for GDPR
  data-erasure compliance scripts.
- **BR-004**: Invoice references preserved when the referenced invoice
  is cancelled or deleted. The singular ``invoice_id`` uses
  ``ondelete='set null'`` so the history record itself is never lost.
  The Many2many ``invoice_ids`` relies on Odoo's default behavior where
  deleting an invoice only removes the intersection row, preserving
  this record.
- **BR-005**: Required fields — ``partner_id``, ``action_type``,
  ``action_date``, ``user_id`` — are enforced as ``required=True`` at
  the model level, supplemented by defaults for ``action_date`` (now)
  and ``user_id`` (current user).
- **BR-006**: Payment promise dates are captured via ``promised_date``
  and ``promised_amount``. When ``promised_date`` is populated, the
  ``create()`` override schedules a ``mail.activity`` (To-Do) on the
  promise date so the assigned user is reminded to verify payment.
- **BR-007**: Attachments are supported through ``mail.thread``
  chatter-based attachments (``message_main_attachment_id``) plus a
  convenience ``attachment_ids`` Many2many for direct attachment
  management in the form view (PF-004 Scenario 5 - Manual Activities).

Design Decisions
----------------
- **Mixin composition**: ``_name = 'account.followup.history'`` creates
  a net-new model, and ``_inherit = ['mail.thread',
  'mail.activity.mixin']`` — a LIST, not a string — composes the two
  mixin classes onto it. This is the canonical Odoo pattern for
  "new model WITH chatter + activities" and does NOT violate R-03
  (which forbids redefinition of an existing concrete model via
  ``_name``).
- **Single primary invoice (``invoice_id``) + multi-invoice
  (``invoice_ids``) coexist** to handle both "email about one invoice"
  (Scenario 4) and "bulk email listing several overdue invoices" (the
  PF-002 cron caller contract) use cases.
- **``_order = 'action_date desc, id desc'``** ensures newest-first
  display (PF-004 Scenario 2 - View Customer Action History).
- **``_rec_name = 'display_name'``** exposes a computed, human-readable
  identifier ("Customer — Type — Date") as the record's name in Many2one
  dropdowns and breadcrumbs.
- **Outcome tracking** via a dedicated ``outcome`` Selection field
  supports PF-004 dashboard filters and effectiveness reporting
  (downstream PF-003 consumers).

Rules Compliance (AAP §0.7)
---------------------------
- **R-01**: No cross-module imports. Only depends on
  ``account_followup_level`` (same module, via ORM comodel lookup).
- **R-02**: No Enterprise references. Pure Community/AGPL-3 stack.
- **R-03**: ``_name`` used correctly for a net-new model; ``_inherit``
  is a LIST composing only mixin abstractions (``mail.thread``,
  ``mail.activity.mixin``).
- **R-07**: No ``sudo()`` calls. The ``env.su`` reads in ``write()``
  and ``unlink()`` are context attribute **reads** (not privilege
  escalation), which is an allowed pattern.
"""

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountFollowupHistory(models.Model):
    """Immutable audit trail of payment follow-up actions.

    Each record represents a single follow-up action (email, phone call,
    letter, meeting, promise, status change, note, SMS) taken against a
    customer. Once created, the record cannot be modified or deleted by
    end users; only an auditor-grade superuser context (``env.su``) may
    bypass immutability for GDPR compliance or data-correction scripts.

    The model inherits ``mail.thread`` for chatter-based attachments and
    ``mail.activity.mixin`` for scheduling follow-up-on-follow-up
    activities (e.g., "remind me to verify this payment promise on
    2024-03-15").
    """

    _name = 'account.followup.history'
    _description = 'Payment Follow-up Action History'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'action_date desc, id desc'
    _rec_name = 'display_name'

    # -------------------------------------------------------------------------
    # CORE REQUIRED FIELDS (PF-004 BR-005)
    # -------------------------------------------------------------------------
    # These four fields (partner_id, action_type, action_date, user_id)
    # constitute the mandatory identification surface of every history
    # record. ``followup_level_id`` and ``company_id`` complete the
    # contextualisation: the former may be NULL for ad-hoc manual actions
    # that occur outside the escalation ladder; the latter is required
    # for multi-company record rule isolation.
    # -------------------------------------------------------------------------

    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Customer',
        required=True,
        ondelete='restrict',
        index=True,
        tracking=True,
        help='The customer this follow-up action was directed at. Uses '
             "``ondelete='restrict'`` so a customer with recorded follow-up "
             'history cannot be silently deleted without review — audit '
             'integrity takes precedence over partner deletability.',
    )

    action_type = fields.Selection(
        selection=[
            ('email', 'Email Sent'),
            ('phone', 'Phone Call'),
            ('letter', 'Letter Sent'),
            ('meeting', 'Meeting'),
            ('promise', 'Payment Promise'),
            ('status', 'Status Change'),
            ('note', 'Internal Note'),
            ('sms', 'SMS Sent'),
        ],
        string='Action Type',
        required=True,
        index=True,
        tracking=True,
        help='The category of the follow-up action taken. Matches PF-004 '
             'action-type taxonomy exactly (8 values).',
    )

    action_date = fields.Datetime(
        string='Action Date',
        required=True,
        default=fields.Datetime.now,
        tracking=True,
        index=True,
        help='Timestamp at which the follow-up action occurred. Defaults '
             'to creation time for automated cron-generated entries; '
             'manual entries may use any past-or-present datetime to '
             'back-date actions that were taken offline.',
    )

    user_id = fields.Many2one(
        comodel_name='res.users',
        string='Action User',
        required=True,
        default=lambda self: self.env.user,
        tracking=True,
        index=True,
        help='The user who triggered or logged this follow-up action. '
             'For cron-generated email entries, this is typically the '
             'system user (uid of the cron owner). For manual entries, '
             'defaults to the current user. The label "Action User" '
             'disambiguates this field from the ``activity_user_id`` '
             'inherited from ``mail.activity.mixin`` (whose label is '
             '"Responsible User"), avoiding the install-time warning '
             'about duplicate labels.',
    )

    followup_level_id = fields.Many2one(
        comodel_name='account.followup.level',
        string='Follow-up Level',
        ondelete='restrict',
        index=True,
        tracking=True,
        help='The follow-up level (e.g., "First Reminder", "Formal '
             'Warning", "Final Notice") that was in effect when this '
             'action was taken. Not required because manual entries '
             '(e.g., an ad-hoc phone call) may occur outside the '
             'escalation ladder. Uses ``ondelete=\'restrict\'`` to '
             'prevent silent deletion of a level with historical '
             'references (audit-integrity protection per BR-003/BR-004).',
    )

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        index=True,
        tracking=True,
        help='Multi-company scope for this history record. Combined with '
             "the ``account_followup_history_company_rule`` ``ir.rule`` in "
             'security/followup_security.xml, enforces per-company record '
             'isolation.',
    )

    # -------------------------------------------------------------------------
    # INVOICE REFERENCES (PF-004 Scenario 4, BR-004)
    # -------------------------------------------------------------------------
    # Two complementary fields:
    #   - ``invoice_id`` (Many2one): primary invoice for single-invoice
    #     contexts (e.g., a phone call about one specific overdue bill).
    #   - ``invoice_ids`` (Many2many): set of invoices for bulk actions
    #     (e.g., the PF-002 email cron lists all overdue invoices for a
    #     customer in one email).
    # Both use preservation semantics so BR-004 is upheld regardless of
    # which field the caller populates.
    # -------------------------------------------------------------------------

    invoice_id = fields.Many2one(
        comodel_name='account.move',
        string='Primary Invoice',
        ondelete='set null',
        domain="[('move_type', 'in', ('out_invoice', 'out_refund'))]",
        index=True,
        help='Primary invoice referenced by this action. Use for single-'
             'invoice contexts (e.g., a phone call about one specific '
             'overdue bill). Uses ``ondelete=\'set null\'`` so the '
             'reference is silently cleared if the invoice is later '
             'deleted, preserving the history record per BR-004.',
    )

    invoice_ids = fields.Many2many(
        comodel_name='account.move',
        relation='followup_history_invoice_rel',
        column1='history_id',
        column2='invoice_id',
        string='Related Invoices',
        domain="[('move_type', 'in', ('out_invoice', 'out_refund'))]",
        help='Set of invoices referenced in this action (typical for '
             'bulk follow-up emails listing multiple overdue bills for '
             'one customer). Populated automatically by '
             '``account.followup.level.process_followup_emails()`` from '
             'the partner\'s overdue-invoice domain. The M2M default '
             'behaviour on invoice deletion is to remove only the '
             'intersection row, preserving the history record per BR-004.',
    )

    total_amount_communicated = fields.Monetary(
        string='Total Amount Communicated',
        currency_field='currency_id',
        help='Aggregate overdue amount that was communicated to the '
             'customer in this follow-up action (snapshot of the sum of '
             'invoice ``amount_residual`` at the time of the action). '
             'Snapshot value — does not auto-update as invoices are paid '
             'or amended, preserving the historical record of what the '
             'customer was actually told at the time.',
    )

    # -------------------------------------------------------------------------
    # CONTENT & COMMUNICATION (PF-004 BR-005, Scenario 7 - View Email Content)
    # -------------------------------------------------------------------------

    summary = fields.Char(
        string='Summary',
        required=True,
        tracking=True,
        help='One-line description of the action (displayed prominently '
             'in list/kanban views). For automated cron-generated emails, '
             'typically "Automated follow-up email sent (Level: <name>)". '
             'For manual entries, user-provided short description.',
    )

    notes = fields.Html(
        string='Detailed Notes',
        sanitize=True,
        sanitize_attributes=True,
        sanitize_style=True,
        help='Rich-text detail of the action. For automated emails, may '
             'contain the rendered email body for Scenario 7 audit '
             'review. For manual entries, free-form narrative of what '
             'was discussed or communicated. HTML is sanitized on save '
             '(including attributes and inline styles) to prevent '
             'stored-XSS attacks per Odoo 17+ hardening.',
    )

    mail_message_id = fields.Many2one(
        comodel_name='mail.message',
        string='Related Message',
        readonly=True,
        ondelete='set null',
        index=True,
        help='Link to the underlying ``mail.message`` record created '
             'when the email was sent through Odoo\'s mail pipeline '
             '(PF-002 automated email generation). Used by PF-004 '
             'Scenario 7 (View Email Content) to retrieve the sent '
             'body, recipients, and attachments. Uses '
             "``ondelete='set null'`` so a message garbage-collection "
             'does not destroy the history record itself.',
    )

    # ``outcome`` is a post-action status tag that supports PF-004
    # dashboard filters (e.g., "show all promised payments still
    # outstanding") and downstream effectiveness reporting in PF-003.
    # It is one of the few fields that is legitimately updated AFTER
    # record creation (e.g., when the promised payment arrives, the
    # accountant updates ``outcome`` to 'payment_received'). This
    # field is therefore included in ``_IMMUTABILITY_WHITELIST``.
    outcome = fields.Selection(
        selection=[
            ('pending', 'Pending'),
            ('contacted', 'Customer Contacted'),
            ('no_contact', 'No Contact Made'),
            ('payment_promised', 'Payment Promised'),
            ('payment_received', 'Payment Received'),
            ('disputed', 'Disputed'),
            ('escalated', 'Escalated'),
            ('closed', 'Closed'),
        ],
        string='Outcome',
        default='pending',
        index=True,
        tracking=True,
        help='Post-action outcome tag used by dashboard filters and '
             'effectiveness reporting. Legitimately mutable post-'
             'creation (e.g., update to ``payment_received`` when the '
             'promised payment arrives) — see '
             '``_IMMUTABILITY_WHITELIST``.',
    )

    # -------------------------------------------------------------------------
    # PAYMENT PROMISE TRACKING (PF-004 Scenario 8, BR-006)
    # -------------------------------------------------------------------------

    promised_date = fields.Date(
        string='Promised Payment Date',
        tracking=True,
        index=True,
        help='Date on which the customer committed to pay. When '
             'populated, the ``create()`` override schedules a '
             '``mail.activity`` (To-Do) on the promise date, assigned '
             'to the record\'s ``user_id``, so the accountant is '
             'reminded to verify payment arrival.',
    )

    promised_amount = fields.Monetary(
        string='Promised Amount',
        currency_field='currency_id',
        tracking=True,
        help='Amount the customer committed to pay by '
             '``promised_date``. May be less than the total overdue '
             'amount (partial promise) — the difference is left to the '
             'accountant to follow up on separately.',
    )

    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency',
        compute='_compute_currency_id',
        store=True,
        readonly=False,
        help='Currency of the monetary fields on this record. Computed '
             'by default from the company currency but ``readonly=False`` '
             'and ``store=True`` together permit explicit user override '
             'for multi-currency scenarios (e.g., an invoice denominated '
             'in USD while the company currency is EUR).',
    )

    # -------------------------------------------------------------------------
    # ATTACHMENTS (PF-004 BR-007, Scenario 5 - Manual Activities)
    # -------------------------------------------------------------------------
    # Although attachments are primarily managed via ``mail.thread``'s
    # chatter mechanism (``message_main_attachment_id``, attached via
    # ``message_post(attachment_ids=...)``), a dedicated ``attachment_ids``
    # Many2many is exposed in the form view for convenience. The field
    # stores direct references to scanned letters, photos of signed
    # promise letters, etc.
    # -------------------------------------------------------------------------

    attachment_ids = fields.Many2many(
        comodel_name='ir.attachment',
        relation='followup_history_attachment_rel',
        column1='history_id',
        column2='attachment_id',
        string='Attachments',
        help='Direct attachments on this history record (scanned '
             'letters, photos of signed promise letters, screenshots '
             'of chat transcripts, etc.). Complementary to the '
             '``mail.thread`` chatter attachments. This field is '
             'whitelisted for post-creation updates so attachments can '
             'be added after the fact (e.g., a scanned receipt that '
             'arrives days after the phone call).',
    )

    # -------------------------------------------------------------------------
    # DISPLAY
    # -------------------------------------------------------------------------

    display_name = fields.Char(
        string='Display Name',
        compute='_compute_display_name',
        store=True,
        help='Human-readable identifier: "Customer — Action Type — '
             'Date". Used as ``_rec_name`` so Many2one dropdowns, '
             'breadcrumbs, and search results show this friendly form.',
    )

    # -------------------------------------------------------------------------
    # IMMUTABILITY WHITELIST (PF-004 BR-003)
    # -------------------------------------------------------------------------
    # Fields that are PERMITTED to be modified AFTER record creation.
    # All other fields raise ``UserError`` on write attempts unless the
    # caller has explicit superuser context (``env.su``), which is the
    # GDPR data-erasure / data-correction escape hatch.
    #
    # Categories:
    #   1. Chatter (from mail.thread) — message_ids and friends MUST be
    #      writable because chatter posts happen after creation and the
    #      ORM writes reverse-O2M internally.
    #   2. Activities (from mail.activity.mixin) — activity_ids and
    #      friends MUST be writable so users can mark activities done.
    #   3. Attachments — message_main_attachment_id (mail.thread) and the
    #      dedicated ``attachment_ids`` M2M allow post-hoc attachment
    #      addition (PF-004 Scenario 5).
    #   4. Outcome — legitimately mutable (update to ``payment_received``
    #      when payment arrives, etc.).
    #   5. Notes — permitted to be augmented with clarifying detail after
    #      the fact (BR-003's intent is to prevent *substantive* field
    #      tampering, not to freeze annotation content).
    #   6. Promise date/amount — may need correction if the customer
    #      amends their commitment.
    #   7. mail_message_id — set by the mail pipeline asynchronously
    #      after record creation.
    #
    # This attribute is defined at CLASS level (not module level) so
    # subclasses may extend it via ``_IMMUTABILITY_WHITELIST = super()
    # ._IMMUTABILITY_WHITELIST | frozenset({...})`` if needed.
    # -------------------------------------------------------------------------

    _IMMUTABILITY_WHITELIST = frozenset({
        # Record-level audit/correction fields
        'outcome',
        'notes',
        'attachment_ids',
        'promised_date',
        'promised_amount',
        'mail_message_id',
        # mail.thread chatter fields
        'message_ids',
        'message_main_attachment_id',
        'message_follower_ids',
        'message_partner_ids',
        'message_is_follower',
        'message_has_error',
        'message_has_error_counter',
        'message_needaction',
        'message_needaction_counter',
        'message_has_sms_error',
        'message_attachment_count',
        'website_message_ids',
        # mail.activity.mixin fields
        'activity_ids',
        'activity_state',
        'activity_user_id',
        'activity_type_id',
        'activity_type_icon',
        'activity_date_deadline',
        'activity_date_deadline_formatted',
        'activity_summary',
        'activity_exception_decoration',
        'activity_exception_icon',
        'activity_calendar_event_id',
    })

    # -------------------------------------------------------------------------
    # COMPUTE METHODS
    # -------------------------------------------------------------------------

    @api.depends('company_id')
    def _compute_currency_id(self):
        """Default currency to the record's company currency.

        Computed-and-stored with ``readonly=False`` so the initial
        compute populates the field from ``company_id.currency_id`` but
        users may subsequently override for multi-currency scenarios.
        Idempotent: only assigns when ``currency_id`` is unset to
        respect prior explicit overrides.
        """
        for rec in self:
            if not rec.currency_id:
                rec.currency_id = (
                    rec.company_id.currency_id
                    if rec.company_id
                    else self.env.company.currency_id
                )

    @api.depends('partner_id.name', 'action_type', 'action_date')
    def _compute_display_name(self):
        """Build a human-readable display name for list/search views.

        Format: ``"<Customer Name> — <Action Type Label> — <YYYY-MM-DD>"``

        Example: ``"Acme Corp — Email Sent — 2024-03-15"``

        Gracefully degrades if fields are missing during record
        creation (partial assignments produced by onchange before
        persistence).
        """
        type_labels = dict(self._fields['action_type'].selection)
        for rec in self:
            partner_name = rec.partner_id.name or _('Unknown Customer')
            type_label = type_labels.get(
                rec.action_type, rec.action_type or _('Action'),
            )
            date_str = (
                rec.action_date.strftime('%Y-%m-%d')
                if rec.action_date
                else ''
            )
            if date_str:
                rec.display_name = f'{partner_name} — {type_label} — {date_str}'
            else:
                rec.display_name = f'{partner_name} — {type_label}'

    # -------------------------------------------------------------------------
    # ONCHANGE HANDLERS
    # -------------------------------------------------------------------------

    @api.onchange('promised_date')
    def _onchange_promised_date(self):
        """Warn the user when a payment promise is recorded.

        Shows a non-blocking warning that an activity will be scheduled
        on the promise date (the actual activity scheduling happens in
        ``create()``; this is a UI hint for manual-entry users). Fires
        on every ``promised_date`` change in the form view before save.
        """
        if self.promised_date and self.user_id:
            return {
                'warning': {
                    'title': _('Payment Promise Recorded'),
                    'message': _(
                        'An activity will be scheduled for %(user)s on '
                        '%(date)s to verify the payment arrival.',
                        user=self.user_id.name,
                        date=self.promised_date.strftime('%Y-%m-%d'),
                    ),
                },
            }
        return None

    # -------------------------------------------------------------------------
    # CRUD OVERRIDES
    # -------------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        """Create history records and schedule payment-promise activities.

        For each record with ``promised_date`` set, automatically
        schedule a ``mail.activity`` of type "To-Do" on the promise
        date, assigned to the record's ``user_id``. This implements
        PF-004 BR-006 / Scenario 5 (schedule activities for manual
        follow-up).

        The ``mail.mail_activity_data_todo`` External ID is the
        standard "To Do" activity type shipped by the ``mail`` module
        (see ``addons/mail/data/mail_data.xml``). Using the XML ID
        rather than a hardcoded integer makes the scheduling portable
        across databases.

        Errors in activity scheduling are caught and logged so that a
        broken activity type reference does not prevent the history
        record itself from being created — audit trail creation takes
        precedence over the convenience-reminder activity.
        """
        records = super().create(vals_list)
        for rec in records:
            if rec.promised_date and rec.user_id:
                try:
                    rec.activity_schedule(
                        act_type_xmlid='mail.mail_activity_data_todo',
                        date_deadline=rec.promised_date,
                        summary=_(
                            'Verify payment promise: %(amount)s by '
                            '%(date)s',
                            amount=rec.promised_amount or 0.0,
                            date=rec.promised_date.strftime('%Y-%m-%d'),
                        ),
                        user_id=rec.user_id.id,
                    )
                except Exception as exc:  # noqa: BLE001 - defensive
                    _logger.warning(
                        'Failed to schedule payment-promise activity for '
                        'history record %s: %s',
                        rec.id,
                        exc,
                    )
        return records

    def write(self, vals):
        """Enforce BR-003 immutability on substantive field updates.

        Permits updates only to fields in ``_IMMUTABILITY_WHITELIST``
        (chatter, activities, attachments, outcome, notes, promise
        details, and the mail_message_id backfill). Any other field
        modification raises ``UserError`` unless the caller has
        superuser privileges (``self.env.su``), which preserves an
        escape hatch for GDPR data-erasure and data-correction scripts.

        ``env.su`` is True exclusively in Python superuser context
        (e.g., when a script uses ``recordset.sudo()`` or
        ``with_user(SUPERUSER_ID)``) — this is stricter than any admin
        group check and matches BR-003 "immutable once created" with
        auditor-grade rigour while preserving GDPR compliance.
        """
        blocked = set(vals.keys()) - self._IMMUTABILITY_WHITELIST
        if blocked and not self.env.su:
            blocked_list = ', '.join(sorted(blocked))
            _logger.warning(
                'Rejected write on immutable fields (%s) for history '
                'records %s by user %s',
                blocked_list,
                self.ids,
                self.env.uid,
            )
            raise UserError(_(
                'Follow-up history records are immutable (PF-004 '
                'BR-003). The following fields cannot be modified '
                'after creation: %(fields)s\n\n'
                'If you need to make a correction, please contact a '
                'system administrator who can apply the change via a '
                'privileged data-correction script.',
                fields=blocked_list,
            ))
        return super().write(vals)

    def unlink(self):
        """Enforce BR-003 deletion immutability.

        Reject deletion unless the caller has explicit superuser
        privileges (``self.env.su``). The ``ir.model.access.csv`` also
        sets ``perm_unlink=0`` for all user-facing groups (defense-in-
        depth at the declarative layer), but this override provides an
        additional programmatic guard and a clearer, translatable
        error message.

        Superuser contexts (``env.su``) may still delete for GDPR
        data-erasure compliance — this is a deliberate escape hatch
        for privileged Python scripts, not a route accessible from the
        web UI (the ACL blocks web-UI deletes independently).
        """
        if not self.env.su:
            _logger.warning(
                'Rejected unlink on immutable history records %s by '
                'user %s',
                self.ids,
                self.env.uid,
            )
            raise UserError(_(
                'Follow-up history records cannot be deleted — they '
                'form a permanent audit trail (PF-004 BR-003 / '
                'Scenario 6 audit compliance).\n\n'
                'For GDPR-compliant data erasure, use a privileged '
                'system-level script that executes with superuser '
                'context.',
            ))
        return super().unlink()

    def copy(self, default=None):
        """Prevent duplication of history records.

        Audit-trail records must represent real actions that actually
        occurred; duplicating a record would create a false historical
        claim. This override rejects all copy attempts with a
        ``UserError`` unless running in ``env.su`` context (which
        exists only for internal Odoo subsystems that legitimately
        need to replicate records, e.g., test fixtures).
        """
        if not self.env.su:
            raise UserError(_(
                'Follow-up history records cannot be duplicated — '
                'each record represents a unique audit event (PF-004 '
                'BR-003). To log a similar new action, create a fresh '
                'history record.',
            ))
        return super().copy(default=default)

    # -------------------------------------------------------------------------
    # ACTION METHODS (navigation — smart buttons)
    # -------------------------------------------------------------------------

    def action_view_invoice(self):
        """Smart-button: navigate to the primary referenced invoice.

        Opens the ``invoice_id`` Many2one target (single primary
        invoice) in a form view. Raises ``UserError`` if no primary
        invoice is linked — callers should conditionally show/hide the
        button based on ``invoice_id`` presence.
        """
        self.ensure_one()
        if not self.invoice_id:
            raise UserError(_(
                'No primary invoice is linked to this history record. '
                'Use "View Invoices" to see related invoices (Many2many).',
            ))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Invoice'),
            'res_model': 'account.move',
            'res_id': self.invoice_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_invoices(self):
        """Smart-button: navigate to the related invoices (M2M).

        Opens the ``invoice_ids`` Many2many set in a list view (or in
        a form view if exactly one invoice is linked). Used by the PF-
        002 bulk-email scenario where a single history record
        references multiple overdue bills.
        """
        self.ensure_one()
        invoices = self.invoice_ids
        if not invoices:
            raise UserError(_(
                'No invoices are linked to this history record.',
            ))
        action = {
            'type': 'ir.actions.act_window',
            'name': _('Related Invoices'),
            'res_model': 'account.move',
            'domain': [('id', 'in', invoices.ids)],
            'context': {'create': False},
            'target': 'current',
        }
        if len(invoices) == 1:
            action.update({
                'view_mode': 'form',
                'res_id': invoices.id,
            })
        else:
            action['view_mode'] = 'list,form'
        return action

    def action_view_partner(self):
        """Smart-button: navigate to the partner record.

        Opens the ``partner_id`` in a form view. Always valid because
        ``partner_id`` is ``required=True``.
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Customer'),
            'res_model': 'res.partner',
            'res_id': self.partner_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
