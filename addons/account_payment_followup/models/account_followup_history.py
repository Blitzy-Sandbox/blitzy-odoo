# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Account Follow-up History — PF-004 Immutable Audit Trail
========================================================

Immutable audit trail of every follow-up action taken against a
customer partner: email dispatches, phone calls, letters, meetings,
payment promises, status changes, manual notes, SMS. Each record is
a single historical event; once created, the record becomes
effectively immutable under PF-004 BR-003 — a small whitelist of
addendum-style fields (``notes``, ``outcome``, ``attachment_ids``,
``promised_date``, ``promised_amount``) may be updated post-facto,
but all identifying/corroborating fields (``partner_id``,
``action_type``, ``action_date``, ``user_id``, ``invoice_ids``,
``followup_level_id``, ``mail_message_id``, ``summary``,
``total_amount_communicated``, ``company_id``) are write-locked after
creation, and deletion is forbidden for ALL users regardless of
group.

Implements:
    - FEATURE-006 PF-004 BR-003: Immutability of audit trail
      records. ``unlink()`` raises ``UserError`` unconditionally;
      ``write()`` raises ``UserError`` for any field not in the
      whitelist.
    - FEATURE-006 PF-004 §4.5: 12+ authoritative fields for audit
      trail completeness.

Integration Notes:
    - Inherits ``mail.thread`` and ``mail.activity.mixin`` so each
      history record has its own chatter for addendum notes and
      activity scheduling.
    - Consumed at runtime by
      ``account.followup.level.process_followup_emails()`` (at line
      553 of ``account_followup_level.py``), which creates a history
      record for every email dispatched by the PF-002 cron.
    - ACL coverage in ``security/ir.model.access.csv`` (rows 6-7)
      grants read/write/create to the billing group and manager
      group, but ``perm_unlink=0`` on both — the Python override is
      defense-in-depth.
    - Multi-company isolation enforced by the ir.rule in
      ``security/followup_security.xml`` (lines 45-52).

Rules Compliance (AAP §0.7):
    - R-01: No cross-module imports.
    - R-02: No Enterprise references.
    - R-03: Uses ``_name`` for a net-new model.
    - R-07: No ``sudo()`` usage.
"""

import logging

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

#: Whitelist of fields that MAY be updated on a history record after
#: creation. Any other field in a ``write()`` call raises UserError.
#: Addendum fields are permitted so that accountants can, for example,
#: record the outcome of a phone call logged earlier, or update the
#: promised-payment details after a later conversation without losing
#: the original record's integrity.
_IMMUTABILITY_WHITELIST = frozenset({
    'notes',
    'outcome',
    'attachment_ids',
    'promised_date',
    'promised_amount',
    # Activity-mixin fields (required so that chatter and activities
    # can attach to the record without raising immutability errors).
    'activity_ids',
    'message_ids',
    'message_follower_ids',
    'message_main_attachment_id',
    'message_partner_ids',
    'message_is_follower',
    'message_needaction',
    'message_needaction_counter',
    'message_has_error',
    'message_has_error_counter',
    'message_attachment_count',
    'message_has_sms_error',
    'website_message_ids',
    'rating_ids',
    'my_activity_date_deadline',
    'activity_user_id',
    'activity_state',
    'activity_type_id',
    'activity_type_icon',
    'activity_date_deadline',
    'activity_summary',
    'activity_exception_decoration',
    'activity_exception_icon',
    'activity_calendar_event_id',
})


class AccountFollowupHistory(models.Model):
    """Immutable audit-trail record of a single follow-up action.

    Once created, identifying fields are locked; only the whitelisted
    addendum fields may be updated. Deletion is forbidden. The record
    itself has a chatter (``mail.thread`` inheritance) so accountants
    can post internal notes and attachments without ever modifying
    the original audit record.
    """

    _name = 'account.followup.history'
    _description = 'Follow-up Action History (Immutable Audit Trail)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'action_date desc, id desc'
    _rec_name = 'summary'

    # -------------------------------------------------------------------------
    # KEY FIELDS
    # -------------------------------------------------------------------------

    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Partner',
        required=True,
        index=True,
        ondelete='restrict',
        tracking=True,
        help=(
            'Customer partner this follow-up action was directed at. '
            'Deletion of the partner is blocked by ``ondelete=restrict`` '
            'because deleting the partner would orphan (and implicitly '
            'destroy) audit history.'
        ),
    )

    action_type = fields.Selection(
        selection=[
            ('email', 'Email'),
            ('phone', 'Phone Call'),
            ('letter', 'Letter'),
            ('meeting', 'Meeting'),
            ('promise', 'Payment Promise'),
            ('status', 'Status Change'),
            ('note', 'Manual Note'),
            ('sms', 'SMS'),
        ],
        string='Action Type',
        required=True,
        index=True,
        tracking=True,
        help=(
            'Type of follow-up action recorded. The eight action types '
            'are:\n'
            ' * Email: Automated dunning email dispatched by the PF-002 '
            'cron or manually sent by an accountant.\n'
            ' * Phone Call: Logged outbound or inbound collection call.\n'
            ' * Letter: Physical dunning letter mailed to the partner.\n'
            ' * Meeting: In-person or video meeting regarding overdue '
            'balances.\n'
            ' * Payment Promise: Customer commitment to pay by a '
            'specific date.\n'
            ' * Status Change: Internal status transition (e.g., '
            'manager override of follow-up level).\n'
            ' * Manual Note: Free-form accountant annotation.\n'
            ' * SMS: Text-message reminder.'
        ),
    )

    action_date = fields.Datetime(
        string='Action Date',
        required=True,
        default=fields.Datetime.now,
        index=True,
        tracking=True,
        help=(
            'Exact datetime at which the follow-up action occurred '
            '(for automated emails, the dispatch timestamp; for manual '
            'actions, the timestamp recorded by the accountant).'
        ),
    )

    user_id = fields.Many2one(
        comodel_name='res.users',
        string='Responsible',
        required=True,
        default=lambda self: self.env.user,
        index=True,
        tracking=True,
        help=(
            'User who initiated or logged this follow-up action. For '
            'automated emails dispatched by the PF-002 cron, this is '
            'the cron user (typically ``base.user_root``); for manual '
            'actions, the logged-in user at creation time.'
        ),
    )

    # -------------------------------------------------------------------------
    # RELATED RECORDS
    # -------------------------------------------------------------------------

    followup_level_id = fields.Many2one(
        comodel_name='account.followup.level',
        string='Follow-up Level',
        index=True,
        tracking=True,
        help=(
            'Follow-up level under which this action was performed. '
            'May be empty for manual actions not associated with any '
            'specific escalation step.'
        ),
    )

    invoice_ids = fields.Many2many(
        comodel_name='account.move',
        relation='followup_history_invoice_rel',
        column1='history_id',
        column2='invoice_id',
        string='Related Invoices',
        help=(
            'Invoices covered by this follow-up action. For automated '
            'email dispatches, this is the full set of overdue invoices '
            'communicated to the customer in that email. Explicit '
            'relation table name avoids collisions with other modules '
            'that might also M2M ``account.move``.'
        ),
    )

    mail_message_id = fields.Many2one(
        comodel_name='mail.message',
        string='Email Message',
        index=True,
        ondelete='set null',
        help=(
            'For email-type actions, a reference to the ``mail.message`` '
            'created by the outbound send so the original email body '
            'can be inspected via the chatter. Set-null on deletion '
            'to preserve the history record if the mail.message is '
            'archived.'
        ),
    )

    # -------------------------------------------------------------------------
    # NARRATIVE / OUTCOME
    # -------------------------------------------------------------------------

    summary = fields.Text(
        string='Summary',
        required=True,
        tracking=True,
        help=(
            'Brief one-line summary of the action for display in list '
            'views (e.g., "Email sent: 2 overdue invoices, $12,450.00 '
            'total"). Required and immutable.'
        ),
    )

    notes = fields.Html(
        string='Detailed Notes',
        help=(
            'Detailed free-form notes describing the action outcome, '
            'customer response, next steps, etc. This field is part of '
            'the immutability whitelist — accountants may add or update '
            'notes after creation (e.g., to record the outcome of a '
            'phone call initially logged without a note).'
        ),
    )

    outcome = fields.Selection(
        selection=[
            ('pending', 'Pending / In Progress'),
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
        help=(
            'Result of the follow-up action. Part of the immutability '
            'whitelist — updates are permitted so that, e.g., a call '
            'logged as "pending" can later be updated to '
            '"payment_promised" once the customer calls back.'
        ),
    )

    # -------------------------------------------------------------------------
    # PAYMENT PROMISE FIELDS
    # -------------------------------------------------------------------------

    promised_date = fields.Date(
        string='Promised Payment Date',
        help=(
            'Customer-committed payment date, captured during a phone '
            'call, meeting, or email response. Part of the immutability '
            'whitelist.'
        ),
    )

    promised_amount = fields.Monetary(
        string='Promised Amount',
        currency_field='currency_id',
        help=(
            'Customer-committed payment amount. Part of the '
            'immutability whitelist.'
        ),
    )

    # -------------------------------------------------------------------------
    # AGGREGATE / COMPANY / CURRENCY
    # -------------------------------------------------------------------------

    total_amount_communicated = fields.Monetary(
        string='Total Amount Communicated',
        currency_field='currency_id',
        help=(
            'Sum of overdue amounts communicated to the customer in '
            'this action (e.g., total overdue at the time of email '
            'send). Immutable — represents a point-in-time snapshot.'
        ),
    )

    attachment_ids = fields.Many2many(
        comodel_name='ir.attachment',
        relation='followup_history_attachment_rel',
        column1='history_id',
        column2='attachment_id',
        string='Attachments',
        help=(
            'Documents attached to this action (e.g., PDF copies of '
            'dunning letters, invoice attachments, signed promise '
            'letters). Part of the immutability whitelist so '
            'accountants can attach supplementary evidence after the '
            'fact.'
        ),
    )

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        index=True,
        tracking=True,
        help=(
            'Company scope for this history record. Enforces multi-'
            'company isolation via the ir.rule at '
            '``security/followup_security.xml`` lines 45-52.'
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
    # IMMUTABILITY ENFORCEMENT (PF-004 BR-003)
    # -------------------------------------------------------------------------

    def write(self, vals):
        """Enforce PF-004 BR-003 immutability on the audit trail.

        Raises ``UserError`` if the caller attempts to modify any field
        outside the whitelist defined in ``_IMMUTABILITY_WHITELIST``.
        Whitelisted fields (``notes``, ``outcome``, ``attachment_ids``,
        ``promised_date``, ``promised_amount``) are permitted because
        they represent post-facto addenda rather than alterations to
        the original audit event.

        Activity and messaging fields from ``mail.thread`` and
        ``mail.activity.mixin`` are also whitelisted so that the
        chatter can function normally (without whitelisting them, every
        message-post or activity-assignment would raise).

        :param vals: Dictionary of field-name -> new-value pairs.
        :raises UserError: If any key in ``vals`` is not in the
            immutability whitelist.
        :return: The standard ``write()`` return value (True).
        """
        disallowed = set(vals.keys()) - _IMMUTABILITY_WHITELIST
        if disallowed:
            _logger.warning(
                'Immutability violation: attempted write on '
                'account.followup.history ids=%s with disallowed '
                'fields=%s',
                self.ids,
                sorted(disallowed),
            )
            raise UserError(
                _(
                    'Follow-up history records are immutable per audit '
                    'policy (PF-004). The following fields cannot be '
                    'modified after creation: %(fields)s.\n\nOnly '
                    'addendum fields (notes, outcome, attachment_ids, '
                    'promised_date, promised_amount) may be updated.',
                ) % {'fields': ', '.join(sorted(disallowed))},
            )
        return super().write(vals)

    def unlink(self):
        """Forbid deletion of follow-up history records unconditionally.

        PF-004 BR-003 mandates that audit-trail records are preserved
        indefinitely. This override raises ``UserError`` for ALL
        users, including managers and administrators — group-based ACL
        ``perm_unlink=0`` already blocks non-managers, and this Python
        override closes the loophole for managers and any future
        group.

        :raises UserError: Unconditionally.
        """
        _logger.warning(
            'Immutability violation: attempted unlink on '
            'account.followup.history ids=%s',
            self.ids,
        )
        raise UserError(
            _(
                'Follow-up history records cannot be deleted — the audit '
                'trail is immutable per PF-004 policy. If a record was '
                'created in error, archive it or add a corrective note '
                'via the chatter instead.',
            ),
        )

    # -------------------------------------------------------------------------
    # CONVENIENCE ACTIONS
    # -------------------------------------------------------------------------

    def action_view_invoices(self):
        """Open the related invoices in a list view.

        Convenience action for list-view buttons and chatter links,
        letting accountants jump from a history record to the set of
        invoices it covers. Returns a plain action dict; the view
        wiring is added in subsequent checkpoint UI files.
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Related Invoices'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.invoice_ids.ids)],
            'context': {'create': False},
        }

    def action_view_partner(self):
        """Open the partner form.

        Convenience action for drilling from a history record back to
        the customer profile.
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Partner'),
            'res_model': 'res.partner',
            'res_id': self.partner_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # -------------------------------------------------------------------------
    # COPY / CLONE PROTECTION
    # -------------------------------------------------------------------------

    def copy(self, default=None):
        """Prevent duplication of audit records.

        Cloning an immutable audit record would create a second copy
        of the event with a different timestamp, which is semantically
        meaningless and risks confusing the audit trail. Raise
        UserError instead.

        :raises UserError: Always.
        """
        raise UserError(
            _(
                'Follow-up history records cannot be duplicated. Each '
                'record represents a unique audit event; create a new '
                'history entry instead of cloning an existing one.',
            ),
        )
