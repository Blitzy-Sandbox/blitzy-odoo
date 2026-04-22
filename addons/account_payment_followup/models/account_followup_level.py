# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Account Follow-up Level — Configuration Model + Email Cron Handler

Defines the ``account.followup.level`` net-new model. A follow-up level
represents one step in a customer follow-up escalation ladder: "7 days past
due -> friendly reminder", "30 days past due -> formal warning", etc. Each
level defines:

    - When it triggers (``delay`` days after due date)
    - What action is taken (``action_type``: automatic email, manual, phone, etc.)
    - Which email template is used (``email_template_id``)
    - Whether to include PDF invoice attachments (``attach_invoices``)
    - Additional side-effect actions (block sales, flag for collection, etc.)

Implements:
    - FEATURE-006 PF-001: Follow-up Level Configuration (full story)
    - FEATURE-006 PF-002: Automated Email Generation (cron handler logic)
    - Supports FEATURE-006 PF-004: Action History Tracking (by creating history records)
    - Supports FEATURE-006 PF-005: Overdue Calculation (consumed by partner level assignment)

Integration Notes:
    - Pure ``_name`` model (no ``_inherit`` since this is a net-new config model)
    - Multi-company aware via ``company_id`` (per-company follow-up policies)
    - Scheduled action entry point: ``process_followup_emails()`` invoked by
      ``data/followup_cron.xml`` (R-06: XML-only scheduling)
    - Zero Enterprise module dependencies (R-02: no reference to Enterprise
      ``account_followup``)
    - AGPL-3.0 licensing

Rules Compliance (AAP §0.7):
    - R-01: No cross-module imports.
    - R-02: No Enterprise references; replacement for Enterprise ``account_followup``.
    - R-03: ``_name`` for net-new model; no ``_inherit``.
    - R-06: ``process_followup_emails()`` designed for XML ``ir.cron`` invocation;
      no Python-level scheduling primitives.
    - R-07: No ``sudo()`` calls. ``mail.template.send_mail(force_send=False)``
      uses Odoo's built-in mail queue which runs under its own cron privileges.
"""

import logging

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import (
    ValidationError,  # noqa: F401 - reserved for future BR-003 hard-constraint upgrades
)

_logger = logging.getLogger(__name__)


class AccountFollowupLevel(models.Model):
    """Payment follow-up escalation level configuration.

    Each record represents one rung of a company's follow-up escalation ladder.
    Records are per-company (via ``company_id``) so that different legal entities
    may maintain independent follow-up policies. Sequence + delay together
    define the ordering: a level with sequence=10, delay=7 fires 7 days after
    an invoice's due date and is evaluated before a level with sequence=20,
    delay=30.

    This is a pure configuration model — it holds settings used by the
    ``process_followup_emails()`` cron handler and by
    ``res.partner._compute_followup_level`` when assigning a current level to
    each overdue partner.
    """

    _name = 'account.followup.level'
    _description = 'Payment Follow-up Level'
    _order = 'sequence, delay, id'
    _check_company_domain = models.check_company_domain_parent_of
    _rec_name = 'name'

    # -------------------------------------------------------------------------
    # CORE CONFIGURATION FIELDS (PF-001 §4.4)
    # -------------------------------------------------------------------------

    name = fields.Char(
        string='Level Name',
        required=True,
        translate=True,
        help='Human-readable name for this follow-up level, e.g., '
             '"First Reminder", "Formal Warning", "Final Notice".',
    )

    sequence = fields.Integer(
        string='Sequence',
        required=True,
        default=10,
        help='Ordering key. Lower sequence = earlier escalation step. Must be '
             'unique per company (BR-001). By convention: 10 = first reminder, '
             '20 = second, 30 = warning, 40 = final notice.',
    )

    delay = fields.Integer(
        string='Delay (Days)',
        required=True,
        default=7,
        help='Number of days after the invoice due date before this level '
             'triggers. Must be non-negative (BR-002). By convention: 7 days '
             'for first reminder, 14 for second, 21 for warning, 30 for '
             'final notice.',
    )

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        default=lambda self: self.env.company,
        index=True,
        help='Company this follow-up level applies to. Per PF-001 §9.1 '
             'assumption, levels are company-specific; the default is set '
             'to the current company.',
    )

    email_template_id = fields.Many2one(
        comodel_name='mail.template',
        string='Email Template',
        domain="[('model', '=', 'res.partner')]",
        ondelete='restrict',
        help='Optional email template used when an automated follow-up fires '
             'at this level. Leave empty for call-only / letter-only / manual '
             'levels. Must target the res.partner model so that template '
             'rendering has partner context available.',
    )

    action_type = fields.Selection(
        selection=[
            ('automatic', 'Automatic'),
            ('manual', 'Manual Trigger'),
            ('email', 'Email Only'),
            ('letter', 'Letter Only'),
            ('phone', 'Phone Call'),
            ('lawyer', 'Legal Action'),
        ],
        string='Action Type',
        default='automatic',
        required=True,
        help='How this level is triggered. "Automatic" fires via the follow-up '
             'email cron; "Email Only" also fires via cron but only when an '
             'email template is configured; "Manual Trigger" / "Phone" / '
             '"Letter" / "Legal Action" require explicit user action.',
    )

    min_amount = fields.Monetary(
        string='Minimum Amount',
        default=0.0,
        currency_field='currency_id',
        help='Optional threshold. Customers whose total overdue amount is '
             'strictly less than this value are skipped when this level '
             'triggers. Set to 0 (default) to evaluate all overdue customers. '
             'Must be non-negative (BR-005).',
    )

    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency',
        compute='_compute_currency_id',
        help='Currency for the min_amount field, derived from the company.',
    )

    description = fields.Text(
        string='Description',
        translate=True,
        help='Internal notes about this level for accounting team reference. '
             'Not shown to customers.',
    )

    active = fields.Boolean(
        default=True,
        help='Set to False to archive this level without deleting it. '
             'Archived levels are skipped by ``process_followup_emails()``.',
    )

    # -------------------------------------------------------------------------
    # TRIGGER ACTIONS (PF-001 Scenario 5)
    # -------------------------------------------------------------------------

    trigger_block_sales = fields.Boolean(
        string='Block New Sales',
        default=False,
        help='When this level fires, sets the partner flag to prevent new '
             'sales orders from being confirmed. Applies per PF-001 Scenario 5 '
             '"Block New Sales" action.',
    )

    trigger_collection_list = fields.Boolean(
        string='Add to Collection List',
        default=False,
        help='When this level fires, flags the partner for inclusion in the '
             'collection report. Applies per PF-001 Scenario 5 '
             '"Add to Collection Report" action.',
    )

    trigger_notify_sales_rep = fields.Boolean(
        string='Notify Salesperson',
        default=False,
        help='When this level fires, sends a notification to the partner\'s '
             'assigned salesperson (user_id on res.partner). Applies per '
             'PF-001 Scenario 5 "Notify Salesperson" action.',
    )

    trigger_update_trust = fields.Selection(
        selection=[
            ('normal', 'Normal'),
            ('good', 'Good Debtor'),
            ('bad', 'Bad Debtor'),
        ],
        string='Update Trust Level',
        help='When this level fires, updates the partner\'s trust '
             'classification to the selected value. Leave empty for no '
             'change. Applies per PF-001 Scenario 5 "Update Trust Level" '
             'action.',
    )

    attach_invoices = fields.Boolean(
        string='Attach Invoice PDFs',
        default=False,
        help='When this level sends an automated email, includes PDF copies '
             'of the overdue invoices as attachments. Applies per PF-002 '
             'BR-004 "PDF invoice attachments OPTIONAL, configurable per '
             'follow-up level".',
    )

    # -------------------------------------------------------------------------
    # SQL CONSTRAINTS (PF-001 BR-001, BR-002, BR-005)
    # -------------------------------------------------------------------------

    _sql_constraints = [
        (
            'sequence_company_unique',
            'UNIQUE(sequence, company_id)',
            'Follow-up level sequence must be unique per company (PF-001 BR-001).',
        ),
        (
            'delay_non_negative',
            'CHECK(delay >= 0)',
            'Follow-up delay (days) cannot be negative (PF-001 BR-002).',
        ),
        (
            'min_amount_non_negative',
            'CHECK(min_amount >= 0)',
            'Minimum amount threshold cannot be negative (PF-001 BR-005).',
        ),
    ]

    # -------------------------------------------------------------------------
    # PYTHON CONSTRAINTS
    # -------------------------------------------------------------------------

    @api.constrains('sequence', 'delay', 'company_id')
    def _check_sequence_delay_ordering(self):
        """BR-003 SOFT validation: lower-sequence levels should have lower delays.

        Per PF-001 §2.3 BR-003: "Levels with lower sequence should have lower
        delay" — explicitly noted as a SOFT validation/warning, NOT a hard
        constraint. We log a warning but do NOT raise ``ValidationError``, so
        that unusual escalation patterns (e.g., a fast-track level with
        sequence=50 but delay=3 for VIP customers) remain possible.

        This method is kept here (rather than omitted) to document the intent
        and emit diagnostics for the accounting team to review via server logs.
        """
        for level in self:
            if not level.company_id:
                # No company scoping -> cannot meaningfully compare against
                # other levels; silently accept.
                continue
            earlier_levels = self.search(
                [
                    ('company_id', '=', level.company_id.id),
                    ('sequence', '<', level.sequence),
                    ('id', '!=', level.id),
                ],
                order='sequence desc',
                limit=1,
            )
            if earlier_levels and earlier_levels.delay > level.delay:
                _logger.warning(
                    "Follow-up level ordering warning: '%(current)s' "
                    "(sequence=%(seq)s, delay=%(delay)s) has a smaller delay "
                    "than the prior level '%(prev)s' (sequence=%(prev_seq)s, "
                    "delay=%(prev_delay)s). Per PF-001 BR-003 this is "
                    "permitted but may cause unexpected escalation behaviour.",
                    {
                        'current': level.name,
                        'seq': level.sequence,
                        'delay': level.delay,
                        'prev': earlier_levels.name,
                        'prev_seq': earlier_levels.sequence,
                        'prev_delay': earlier_levels.delay,
                    },
                )

    # -------------------------------------------------------------------------
    # COMPUTE METHODS
    # -------------------------------------------------------------------------

    @api.depends('company_id')
    @api.depends_context('company')
    def _compute_currency_id(self):
        """Derive currency from the level's company, falling back to env.company.

        Follows the ``account.payment.term`` canonical pattern:
        ``record.company_id.currency_id or self.env.company.currency_id``.

        The ``@api.depends_context('company')`` decorator ensures recompute
        when the user switches the active company via the company-selector
        widget (common in multi-company deployments).
        """
        for level in self:
            level.currency_id = (
                level.company_id.currency_id
                or self.env.company.currency_id
            )

    # -------------------------------------------------------------------------
    # HELPER METHODS
    # -------------------------------------------------------------------------

    def _get_applicable_partners(self, batch_size=500):
        """Return partners eligible for follow-up at ANY level in this recordset.

        Called by ``process_followup_emails()`` to identify which customers
        should receive follow-up action this cron run.

        Filtering:

            - Must have overdue invoices (``has_overdue_invoices=True``)
            - Must be assigned to a level in ``self`` (after
              ``res.partner._compute_followup_level`` evaluation)
            - Honors ``active_partner_ids`` context key for manual-trigger path
            - Limited to ``batch_size`` partners (PF-002 performance target)

        The ``min_amount`` threshold is enforced per-partner inside
        ``process_followup_emails()`` rather than in the domain here, because
        thresholds may differ across levels and the comparison must happen
        against the partner's currently-assigned level only.

        :param batch_size: maximum number of partners to return (default 500)
        :return: ``res.partner`` recordset
        """
        Partner = self.env['res.partner']
        # Base domain: customers with overdue receivables assigned to one of
        # our levels.
        domain = [
            ('has_overdue_invoices', '=', True),
            ('followup_level_id', 'in', self.ids),
        ]
        # Manual-trigger path (called from res.partner.action_send_followup_now
        # or wizard-driven flows): restrict to explicitly-selected partners.
        active_partner_ids = self.env.context.get('active_partner_ids')
        if active_partner_ids:
            domain.append(('id', 'in', active_partner_ids))
        return Partner.search(domain, limit=batch_size)

    def _apply_trigger_actions(self, partner):
        """Apply Scenario 5 side-effect actions on a single partner.

        Handles the unconditional writes (trust level update) and the chatter
        notification to the assigned salesperson. The ``trigger_block_sales``
        and ``trigger_collection_list`` flags are read elsewhere (by sales
        order validation and the collection report, respectively) and do not
        require an explicit write here — the flag presence on the current
        level is authoritative.

        :param partner: ``res.partner`` recordset (len=1)
        """
        self.ensure_one()
        vals = {}
        # Trust level update: only attempt write if the partner model exposes
        # the ``trust`` field (depends on which modules are installed).
        if self.trigger_update_trust:
            if 'trust' in partner._fields:
                vals['trust'] = self.trigger_update_trust
        if vals:
            partner.write(vals)
        # Notify the assigned salesperson (if any) via chatter.
        if self.trigger_notify_sales_rep and partner.user_id:
            body = _(
                "Follow-up level '%(level)s' triggered for this customer "
                "(%(days)s days overdue, %(amount)s outstanding). "
                "Sales team notification required.",
                level=self.name,
                days=partner.max_days_overdue,
                amount=partner.total_overdue,
            )
            partner.message_post(
                body=body,
                partner_ids=partner.user_id.partner_id.ids,
                message_type='notification',
                subtype_xmlid='mail.mt_note',
            )

    # -------------------------------------------------------------------------
    # CRON HANDLER — PF-002 INTEGRATION (R-06 compliance)
    # -------------------------------------------------------------------------

    @api.model
    def process_followup_emails(self, batch_size=500):
        """Entry point invoked by XML ``ir.cron`` record
        ``ir_cron_payment_followup`` (see ``data/followup_cron.xml``).

        Processes up to ``batch_size`` partners per invocation; for each:

            1. Verifies the partner has overdue invoices and a level assigned.
            2. Skips if partner's ``total_overdue < level.min_amount`` (BR-005).
            3. Skips if ``level.action_type`` not in automatic-eligible set.
            4. Queues email via
               ``level.email_template_id.send_mail(partner.id, force_send=False)``
               (PF-002 Scenarios 1-3).
            5. Optionally generates PDF invoice attachments
               (``attach_invoices``).
            6. Creates ``account.followup.history`` record with
               ``action_type='email'`` and linked invoices (PF-002 BR-007 /
               PF-004 BR-001).
            7. Applies trigger actions (block sales, update trust, etc. —
               Scenario 5).
            8. Updates ``partner.followup_next_action_date`` based on
               ``level.delay``.
            9. Logs success/failure per partner — failures do NOT halt the
               batch (PF-002 Scenario 7: "processing continues even if
               individual emails fail (errors logged)").

        Context keys honored:

            ``active_partner_ids``
                List of ``res.partner`` IDs to restrict processing to (used by
                ``res.partner.action_send_followup_now`` for manual
                single-partner trigger).

        :param batch_size: Maximum partners per cron run. Hard cap per AAP
            §0.7.3 performance target (<=500 partners per run within default
            cron timeout). Enforced via ``search(..., limit=batch_size)``.
        :return: dict with statistics for operational observability:
            ``{'partners_processed': N, 'emails_queued': M, 'errors': K}``
        """
        # BR-004 guard: at least one active follow-up level must exist.
        all_active_levels = self.search([('active', '=', True)])
        if not all_active_levels:
            _logger.info(
                "Payment follow-up cron: no active follow-up levels "
                "configured; skipping run (PF-001 BR-004).",
            )
            return {'partners_processed': 0, 'emails_queued': 0, 'errors': 0}

        # PF-002 BR-006: only levels with automatic/email action types are
        # eligible for cron-driven dispatch. Manual/phone/letter/lawyer
        # levels require an explicit user action.
        automatic_levels = all_active_levels.filtered(
            lambda lvl: lvl.action_type in ('automatic', 'email'),
        )
        if not automatic_levels:
            _logger.info(
                "Payment follow-up cron: no levels with automatic/email "
                "action_type; skipping run.",
            )
            return {'partners_processed': 0, 'emails_queued': 0, 'errors': 0}

        # Fetch eligible partners across all automatic levels (batched).
        partners = automatic_levels._get_applicable_partners(
            batch_size=batch_size,
        )
        stats = {'partners_processed': 0, 'emails_queued': 0, 'errors': 0}

        _logger.info(
            "Payment follow-up cron: processing %d partners across %d active "
            "automatic levels (batch_size=%d)",
            len(partners),
            len(automatic_levels),
            batch_size,
        )

        for partner in partners:
            try:
                level = partner.followup_level_id
                if not level:
                    # Defensive: partner's level may have been cleared
                    # between the search and this iteration.
                    continue

                # BR-005: min_amount threshold check. A level with
                # min_amount=0 evaluates every overdue partner.
                if level.min_amount and partner.total_overdue < level.min_amount:
                    _logger.debug(
                        "Skipping partner %s: overdue %.2f < level min %.2f",
                        partner.display_name,
                        partner.total_overdue,
                        level.min_amount,
                    )
                    continue

                # Handle automatic / email-only levels: queue the mail and
                # create the history record.
                if level.action_type in ('automatic', 'email'):
                    if not level.email_template_id:
                        _logger.debug(
                            "Skipping partner %s: level %s has no email "
                            "template configured",
                            partner.display_name,
                            level.name,
                        )
                        continue
                    if not partner.email:
                        # PF-002 BR-005: customers without an email address
                        # are skipped — manual action is required.
                        _logger.info(
                            "Partner %s has no email address; skipping "
                            "automated email for level %s (PF-002 BR-005)",
                            partner.display_name,
                            level.name,
                        )
                        continue

                    # Fetch the overdue invoices — used both for optional
                    # PDF attachments and for history linkage.
                    overdue_invoices = partner._get_overdue_invoices()

                    # Optionally generate PDF attachments (PF-002 BR-004).
                    attachment_ids = []
                    if level.attach_invoices and overdue_invoices:
                        attachment_ids = level._generate_invoice_attachments(
                            overdue_invoices,
                        )

                    # Queue the email via mail.mail (force_send=False -> async).
                    # The standard notification layout provides company
                    # branding, salutation, and signature structure.
                    mail_id = level.email_template_id.send_mail(
                        partner.id,
                        force_send=False,
                        email_layout_xmlid='mail.mail_notification_layout',
                    )

                    # Browse the queued mail record to capture its message
                    # for the history row and to attach the generated PDFs.
                    mail_message_id = False
                    if mail_id:
                        mail_record = self.env['mail.mail'].browse(mail_id)
                        if mail_record.exists():
                            mail_message_id = mail_record.mail_message_id.id
                            # Attach the generated PDFs to the outgoing mail.
                            if attachment_ids:
                                mail_record.write({
                                    'attachment_ids': [(6, 0, attachment_ids)],
                                })

                    # Create immutable audit-trail entry (PF-004 BR-001).
                    # The history model enforces immutability via write()
                    # and unlink() overrides that raise UserError.
                    self.env['account.followup.history'].create({
                        'partner_id': partner.id,
                        'followup_level_id': level.id,
                        'action_type': 'email',
                        'action_date': fields.Datetime.now(),
                        'user_id': self.env.uid,
                        'company_id': (
                            partner.company_id.id
                            or self.env.company.id
                        ),
                        'summary': _(
                            'Automated follow-up email sent (Level: %s)',
                        ) % level.name,
                        'invoice_ids': [(6, 0, overdue_invoices.ids)],
                        'total_amount_communicated': partner.total_overdue,
                        'mail_message_id': mail_message_id,
                    })

                    stats['emails_queued'] += 1

                # Apply Scenario 5 side-effect actions (trust update,
                # salesperson notification). Executed for every eligible
                # partner, regardless of email outcome.
                level._apply_trigger_actions(partner)

                # Advance the partner's next-action date by the level's
                # delay. This is the "cooldown" between successive follow-up
                # touches for the same customer.
                partner.write({
                    'followup_next_action_date': (
                        fields.Date.context_today(self)
                        + relativedelta(days=level.delay or 7)
                    ),
                })

                stats['partners_processed'] += 1

            except Exception:  # noqa: BLE001 — fault-tolerant batch
                # PF-002 Scenario 7: processing continues even if individual
                # emails fail; errors are logged with full stack traces for
                # operator diagnosis. _logger.exception() automatically
                # captures the current exception via sys.exc_info().
                _logger.exception(
                    "Follow-up processing failed for partner %s (id=%s)",
                    partner.display_name,
                    partner.id,
                )
                stats['errors'] += 1

        _logger.info(
            "Payment follow-up cron complete: processed=%d, queued=%d, "
            "errors=%d",
            stats['partners_processed'],
            stats['emails_queued'],
            stats['errors'],
        )
        return stats

    def _generate_invoice_attachments(self, invoices):
        """Render invoice PDFs and create ir.attachment records.

        Called by ``process_followup_emails()`` when ``level.attach_invoices``
        is True. Per-invoice try/except ensures one failed PDF does not
        prevent other PDFs in the same email from being attached.

        :param invoices: ``account.move`` recordset of overdue customer
            invoices
        :return: list of ``ir.attachment`` IDs to link to the outgoing
            ``mail.mail`` record
        """
        self.ensure_one()
        if not invoices:
            return []
        Attachment = self.env['ir.attachment']
        # Use Odoo's standard invoice report. If the reference is missing
        # (unusual but possible in stripped-down deployments), log a warning
        # and skip attachment generation rather than crashing the cron.
        report_action = self.env.ref(
            'account.account_invoices', raise_if_not_found=False,
        )
        if not report_action:
            _logger.warning(
                "Standard invoice report 'account.account_invoices' not "
                "found; skipping PDF attachment generation.",
            )
            return []
        attachment_ids = []
        for invoice in invoices:
            try:
                pdf_content, _pdf_type = report_action._render_qweb_pdf(
                    report_action.report_name, invoice.ids,
                )
                attachment = Attachment.create({
                    'name': 'Invoice_%s.pdf' % (invoice.name or invoice.id),
                    'type': 'binary',
                    'raw': pdf_content,
                    'mimetype': 'application/pdf',
                    'res_model': 'account.move',
                    'res_id': invoice.id,
                })
                attachment_ids.append(attachment.id)
            except Exception:  # noqa: BLE001 — per-invoice resilience
                # _logger.exception() automatically captures the current
                # exception via sys.exc_info().
                _logger.exception(
                    "Failed to render PDF for invoice %s",
                    invoice.display_name,
                )
        return attachment_ids

    # -------------------------------------------------------------------------
    # ACTION METHODS
    # -------------------------------------------------------------------------

    def action_view_email_template(self):
        """Smart-button handler: navigate to the associated email template.

        Returns an Odoo action dict that opens the configured
        ``mail.template`` in form view. Returns ``False`` when no template
        is assigned so that the UI can gracefully disable the button.
        """
        self.ensure_one()
        if not self.email_template_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': _('Email Template'),
            'res_model': 'mail.template',
            'res_id': self.email_template_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
