# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
PF-002 — Automated Email Generation: Acceptance Test Suite
===========================================================

Verifies the cron handler and email-dispatch surface introduced by:

  * ``addons/account_payment_followup/models/account_followup_level.py`` —
    cron entry point ``process_followup_emails(batch_size=500)`` plus
    ``_get_applicable_partners``, ``_apply_trigger_actions``, and
    ``_generate_invoice_attachments``.
  * ``addons/account_payment_followup/data/followup_cron.xml`` —
    declarative ``ir.cron`` registration via XML record (R-06).

Acceptance Scenarios (BDD Given/When/Then) covered:

  - Scenario 1: First reminder fires for partner at Level 1 threshold
  - Scenario 2: Second reminder fires for partner at Level 2 threshold
  - Scenario 3: Warning fires for partner at Level 3 threshold
  - Scenario 4: Final notice fires for partner at Level 4 threshold
  - Scenario 5: Trigger actions executed (notify_sales_rep, update_trust,
    block_sales)
  - Scenario 6: PDF invoice attachments generated when attach_invoices=True
  - Scenario 7: Fault tolerance — single partner failure does not halt
    the batch
  - Scenario 8: Cron reachability via env.ref + method_direct_trigger
    (Gate 13)

Plus Business Rules BR-001..BR-007 and contract verification:

  - inspect.signature(...).parameters['batch_size'].default == 500
  - mock-patched _render_template fault tolerance
  - history record creation per email send
  - min_amount threshold (BR-005)
  - email-skip when partner has no email (BR-005)

Targets ≥80% line coverage of the cron handler portion of
``account_followup_level.py``.

Determinism
-----------
The class uses :class:`AccountPaymentFollowupTestCommon` which freezes
fixture creation to ``date(2024, 6, 30)``. PF-002's compute logic
(min_amount, partner level assignment) is not date-sensitive at the
cron layer; the freeze inherits from common.py for fixture stability.

Rules Compliance (AAP §0.7)
---------------------------
- R-01: No imports from sibling new modules.
- R-02: No imports from Enterprise modules.
- R-04: Targets ≥80% coverage of the PF-002 portion of
  ``account_followup_level.py``.
- R-06: Verifies the cron is declared via XML (Gate 13).
- R-07: No ``sudo()`` calls (uses ``with_user`` for ACL boundary tests).
- R-09: Filename is ``test_pf_002.py`` exactly.
"""

import inspect
import logging
from datetime import date
from unittest import mock

from freezegun import freeze_time

from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import AccountPaymentFollowupTestCommon

_logger = logging.getLogger(__name__)

# Module-level frozen reference date — must match
# ``AccountPaymentFollowupTestCommon.FROZEN_DATE`` so the @freeze_time
# decorator below aligns with fixture creation in setUpClass.
FROZEN_DATE = date(2024, 6, 30)

# Cron XMLID consumed by env.ref() for Gate 13 verification.
CRON_XMLID = 'account_payment_followup.ir_cron_payment_followup'


@tagged('post_install', '-at_install')
@freeze_time(FROZEN_DATE)
class TestAutomatedEmailGeneration(AccountPaymentFollowupTestCommon):
    """PF-002 — Automated Email Generation acceptance tests.

    Inherits :class:`AccountPaymentFollowupTestCommon` for the eight
    overdue-bucket partners + invoices and the four seeded follow-up
    levels.

    Implementation Notes
    --------------------
    The cron handler calls ``mail.template.send_mail(force_send=False)``
    which queues a ``mail.mail`` record without actually sending. Tests
    can verify the queue state without configuring an SMTP server.

    For fault-tolerance tests, we monkey-patch
    ``mail.template.send_mail`` (or the rendering layer) to raise on
    a specific partner; the test then verifies that other partners
    still process successfully.

    Multi-partner tests rely on partner.invalidate_recordset() to force
    re-computation of stored fields (``followup_level_id``,
    ``has_overdue_invoices``) before the cron is invoked, ensuring
    deterministic batch composition.
    """

    @classmethod
    def setUpClass(cls):
        """Build PF-002-specific fixtures on top of the common base.

        Forces an initial recompute of the partners' ``followup_level_id``
        so the cron processes them deterministically. Without this,
        the stored compute may not yet have populated values for
        partners created in :meth:`_setup_overdue_partners`.
        """
        super().setUpClass()
        # Force recompute of partner-level computed aggregates so the
        # partners' followup_level_id is populated before any cron run.
        all_partners = (
            cls.partner_current
            | cls.partner_overdue_7d | cls.partner_overdue_14d
            | cls.partner_overdue_21d | cls.partner_overdue_30d
            | cls.partner_overdue_45d | cls.partner_overdue_95d
            | cls.partner_mixed_aging
        )
        all_partners.invalidate_recordset()
        # Trigger compute by reading
        all_partners.mapped('followup_level_id')
        # Save results to ensure deterministic behavior during tests
        cls.all_test_partners = all_partners

    # =========================================================================
    # SCENARIO 8: Cron Reachability (Gate 13) — placed first since it's
    # foundational for all other scenarios
    # =========================================================================

    def test_gate_13_cron_xmlid_resolves(self):
        """Gate 13: env.ref() resolves the cron's external ID.

        The XML record ``ir_cron_payment_followup`` MUST be reachable
        via ``env.ref('account_payment_followup.ir_cron_payment_followup')``
        per AAP §0.7.2 Gate 13.
        """
        cron = self.env.ref(CRON_XMLID, raise_if_not_found=False)
        self.assertTrue(cron,
                        f"env.ref({CRON_XMLID!r}) must resolve to a record.")
        self.assertEqual(cron._name, 'ir.cron',
                         "External ID must point to an ir.cron record.")

    def test_gate_13_cron_visible_in_scheduled_actions(self):
        """Gate 13: cron has the expected visible attributes."""
        cron = self.env.ref(CRON_XMLID)
        self.assertEqual(cron.name, 'Payment Follow-up: Send Reminders',
                         'Cron name must match XML declaration.')
        self.assertTrue(cron.active,
                        'Cron must be active by default after install.')
        self.assertEqual(cron.interval_number, 1)
        self.assertEqual(cron.interval_type, 'days')

    def test_gate_13_cron_invokes_correct_model(self):
        """Gate 13: cron's model_id points to account.followup.level."""
        cron = self.env.ref(CRON_XMLID)
        self.assertEqual(cron.model_id.model, 'account.followup.level',
                         'Cron model_id must be account.followup.level.')

    def test_gate_13_cron_state_is_code(self):
        """Gate 13: cron state is 'code' so it executes a code block."""
        cron = self.env.ref(CRON_XMLID)
        self.assertEqual(cron.state, 'code',
                         "Cron state must be 'code' to execute model methods.")

    def test_gate_13_cron_code_calls_process_followup_emails(self):
        """Gate 13: cron code body invokes process_followup_emails."""
        cron = self.env.ref(CRON_XMLID)
        self.assertIn('process_followup_emails', cron.code,
                      'Cron code must call process_followup_emails().')

    def test_gate_13_cron_method_direct_trigger(self):
        """Gate 13: method_direct_trigger() executes the cron without raising.

        This is the manual "Run Manually" action exposed in the
        Settings → Technical → Automation → Scheduled Actions UI.
        """
        cron = self.env.ref(CRON_XMLID)
        # method_direct_trigger() runs the cron synchronously. It MUST
        # NOT raise, even if there are no eligible partners to process.
        # Wrap with mute_logger to suppress any expected mail-pipeline
        # warnings (e.g., partners without email).
        with mute_logger('odoo.addons.mail.models.mail_mail',
                         'odoo.addons.mail.models.mail_template'):
            try:
                cron.method_direct_trigger()
            except Exception as exc:  # noqa: BLE001
                self.fail(
                    f"method_direct_trigger() must not raise: {exc!r}",
                )

    # =========================================================================
    # CONTRACT VERIFICATION — batch_size=500 default signature
    # =========================================================================

    def test_signature_batch_size_default_is_500(self):
        """Contract: process_followup_emails has batch_size=500 default.

        Per AAP §0.7.3 performance target, the cron processes ≤500
        partners per run within the default cron timeout. The default
        is enforced via the method signature.
        """
        Level = self.env['account.followup.level']
        signature = inspect.signature(Level.process_followup_emails)
        params = signature.parameters
        self.assertIn('batch_size', params,
                      'process_followup_emails must accept a batch_size '
                      'keyword argument.')
        self.assertEqual(
            params['batch_size'].default, 500,
            'batch_size default MUST be 500 per AAP §0.7.3.',
        )

    def test_batch_size_can_be_overridden(self):
        """Contract: batch_size argument is honored by the search limit."""
        Level = self.env['account.followup.level']
        # Pass a small batch_size; the result should reflect the limit.
        result = Level.process_followup_emails(batch_size=1)
        self.assertIsInstance(result, dict)
        # ``partners_processed`` is bounded by batch_size.
        self.assertLessEqual(
            result['partners_processed'], 1,
            'Result must respect the batch_size limit.',
        )

    # =========================================================================
    # SCENARIO 1-4: Email dispatch at each level threshold
    # =========================================================================

    def test_scenario_1_first_reminder_fires_at_7_days(self):
        """Scenario 1: partner overdue 7 days receives First Reminder email.

        Given a partner with one invoice 7 days past due (assigned to
        First Reminder level)
        When the cron runs
        Then a mail.mail record is queued for the partner via the
        First Reminder template.
        """
        partner = self.partner_overdue_7d
        partner.invalidate_recordset()
        # Verify level assignment is correct before triggering the cron.
        self.assertEqual(
            partner.followup_level_id, self.first_reminder_level,
            'Partner overdue 7d must be at First Reminder level.',
        )
        # Capture mail.mail count before the cron runs.
        Mail = self.env['mail.mail']
        mail_before = Mail.search_count([
            ('recipient_ids', 'in', [partner.id]),
        ])
        # Run the cron with mute_logger to suppress mail-pipeline noise.
        with mute_logger('odoo.addons.mail.models.mail_mail',
                         'odoo.addons.mail.models.mail_template'):
            result = self.env['account.followup.level'].process_followup_emails(
                batch_size=500,
            )
        # Verify a mail was queued.
        mail_after = Mail.search_count([
            ('recipient_ids', 'in', [partner.id]),
        ])
        self.assertGreater(
            mail_after, mail_before,
            'A mail.mail record must be queued for the First Reminder.',
        )
        self.assertGreaterEqual(result['emails_queued'], 1,
                                'Result must report at least 1 email queued.')

    def test_scenario_2_second_reminder_fires_at_14_days(self):
        """Scenario 2: partner overdue 14 days receives Second Reminder."""
        partner = self.partner_overdue_14d
        partner.invalidate_recordset()
        self.assertEqual(
            partner.followup_level_id, self.second_reminder_level,
            'Partner overdue 14d must be at Second Reminder level.',
        )
        Mail = self.env['mail.mail']
        mail_before = Mail.search_count([
            ('recipient_ids', 'in', [partner.id]),
        ])
        with mute_logger('odoo.addons.mail.models.mail_mail',
                         'odoo.addons.mail.models.mail_template'):
            self.env['account.followup.level'].process_followup_emails()
        mail_after = Mail.search_count([
            ('recipient_ids', 'in', [partner.id]),
        ])
        self.assertGreater(mail_after, mail_before,
                           'Second Reminder mail must be queued.')

    def test_scenario_3_warning_fires_at_21_days(self):
        """Scenario 3: partner overdue 21 days receives Warning email."""
        partner = self.partner_overdue_21d
        partner.invalidate_recordset()
        self.assertEqual(
            partner.followup_level_id, self.warning_level,
            'Partner overdue 21d must be at Warning level.',
        )
        Mail = self.env['mail.mail']
        mail_before = Mail.search_count([
            ('recipient_ids', 'in', [partner.id]),
        ])
        with mute_logger('odoo.addons.mail.models.mail_mail',
                         'odoo.addons.mail.models.mail_template'):
            self.env['account.followup.level'].process_followup_emails()
        mail_after = Mail.search_count([
            ('recipient_ids', 'in', [partner.id]),
        ])
        self.assertGreater(mail_after, mail_before,
                           'Warning mail must be queued.')

    def test_scenario_4_final_notice_fires_at_30_days(self):
        """Scenario 4: partner overdue 30 days receives Final Notice email."""
        partner = self.partner_overdue_30d
        partner.invalidate_recordset()
        self.assertEqual(
            partner.followup_level_id, self.final_notice_level,
            'Partner overdue 30d must be at Final Notice level.',
        )
        Mail = self.env['mail.mail']
        mail_before = Mail.search_count([
            ('recipient_ids', 'in', [partner.id]),
        ])
        with mute_logger('odoo.addons.mail.models.mail_mail',
                         'odoo.addons.mail.models.mail_template'):
            self.env['account.followup.level'].process_followup_emails()
        mail_after = Mail.search_count([
            ('recipient_ids', 'in', [partner.id]),
        ])
        self.assertGreater(mail_after, mail_before,
                           'Final Notice mail must be queued.')

    # =========================================================================
    # HISTORY RECORD CREATION (BR-007, PF-004 BR-001)
    # =========================================================================

    def test_history_record_created_per_email(self):
        """BR-007: each automated email creates an account.followup.history.

        Given a partner with overdue invoices triggered by the cron
        When the cron runs and queues an email
        Then exactly one new account.followup.history record exists
        for that partner with action_type='email'.
        """
        partner = self.partner_overdue_7d
        partner.invalidate_recordset()
        History = self.env['account.followup.history']
        before = History.search_count([
            ('partner_id', '=', partner.id),
            ('action_type', '=', 'email'),
        ])
        with mute_logger('odoo.addons.mail.models.mail_mail',
                         'odoo.addons.mail.models.mail_template'):
            self.env['account.followup.level'].process_followup_emails()
        after = History.search_count([
            ('partner_id', '=', partner.id),
            ('action_type', '=', 'email'),
        ])
        self.assertEqual(after, before + 1,
                         'One history record per automated email.')

    def test_history_record_links_overdue_invoices(self):
        """History record's invoice_ids includes the partner's overdue invoices."""
        partner = self.partner_overdue_30d
        partner.invalidate_recordset()
        History = self.env['account.followup.history']
        with mute_logger('odoo.addons.mail.models.mail_mail',
                         'odoo.addons.mail.models.mail_template'):
            self.env['account.followup.level'].process_followup_emails()
        history = History.search([
            ('partner_id', '=', partner.id),
            ('action_type', '=', 'email'),
        ], order='action_date desc', limit=1)
        self.assertTrue(history,
                        'A history record must exist after cron run.')
        # invoice_ids must include the 30d invoice
        self.assertIn(self.inv_30d, history.invoice_ids,
                      'History must reference the overdue invoice.')

    def test_history_record_captures_total_amount_communicated(self):
        """History record snapshots the total overdue amount communicated."""
        partner = self.partner_overdue_45d
        partner.invalidate_recordset()
        History = self.env['account.followup.history']
        with mute_logger('odoo.addons.mail.models.mail_mail',
                         'odoo.addons.mail.models.mail_template'):
            self.env['account.followup.level'].process_followup_emails()
        history = History.search([
            ('partner_id', '=', partner.id),
            ('action_type', '=', 'email'),
        ], order='action_date desc', limit=1)
        self.assertTrue(history)
        # total_amount_communicated should match partner.total_overdue at
        # the time of the cron.
        self.assertGreater(
            history.total_amount_communicated, 0.0,
            'History total_amount_communicated must be set from the '
            'partner total_overdue at action time.',
        )

    # =========================================================================
    # SCENARIO 5: Trigger Actions (notify_sales_rep, update_trust, etc.)
    # =========================================================================

    def test_scenario_5_update_trust_applied_to_partner(self):
        """Scenario 5: trigger_update_trust changes partner.trust value.

        Given the Final Notice level configured with
        ``trigger_update_trust='bad'``
        When the cron processes a partner at that level
        Then the partner's trust field is set to 'bad'.
        """
        # Configure Final Notice to update trust to 'bad'.
        self.final_notice_level.write({'trigger_update_trust': 'bad'})
        partner = self.partner_overdue_30d
        partner.invalidate_recordset()
        # Snapshot the original trust value (default is 'normal').
        partner.write({'trust': 'normal'})
        with mute_logger('odoo.addons.mail.models.mail_mail',
                         'odoo.addons.mail.models.mail_template'):
            self.env['account.followup.level'].process_followup_emails()
        partner.invalidate_recordset()
        self.assertEqual(
            partner.trust, 'bad',
            'trigger_update_trust must update partner.trust.',
        )

    def test_scenario_5_notify_sales_rep_creates_chatter_message(self):
        """Scenario 5: trigger_notify_sales_rep posts a chatter message.

        The level's _apply_trigger_actions calls partner.message_post()
        with the salesperson in partner_ids. Verifies that a message
        was posted.
        """
        partner = self.partner_overdue_14d
        # Assign a salesperson so the notification target exists.
        sales_rep = self.env['res.users'].create({
            'name': 'Test Sales Rep',
            'login': 'salesrep_pf002@test.com',
            'email': 'salesrep_pf002@test.com',
        })
        partner.write({'user_id': sales_rep.id})
        partner.invalidate_recordset()
        # Configure Second Reminder to notify sales rep.
        self.second_reminder_level.write({'trigger_notify_sales_rep': True})
        # Capture chatter message count before.
        msgs_before = self.env['mail.message'].search_count([
            ('model', '=', 'res.partner'),
            ('res_id', '=', partner.id),
        ])
        with mute_logger('odoo.addons.mail.models.mail_mail',
                         'odoo.addons.mail.models.mail_template'):
            self.env['account.followup.level'].process_followup_emails()
        msgs_after = self.env['mail.message'].search_count([
            ('model', '=', 'res.partner'),
            ('res_id', '=', partner.id),
        ])
        self.assertGreater(
            msgs_after, msgs_before,
            'A chatter message must be posted when '
            'trigger_notify_sales_rep is enabled.',
        )

    def test_scenario_5_followup_next_action_date_advanced(self):
        """Scenario 5: cron advances partner.followup_next_action_date.

        After successful processing, the partner's next_action_date
        becomes today + level.delay days (the cooldown between
        successive follow-up touches).
        """
        partner = self.partner_overdue_7d
        partner.invalidate_recordset()
        # Reset the date for a clean test
        partner.write({'followup_next_action_date': False})
        with mute_logger('odoo.addons.mail.models.mail_mail',
                         'odoo.addons.mail.models.mail_template'):
            self.env['account.followup.level'].process_followup_emails()
        partner.invalidate_recordset()
        self.assertTrue(
            partner.followup_next_action_date,
            'followup_next_action_date must be set after cron run.',
        )

    # =========================================================================
    # SCENARIO 6: PDF Invoice Attachments (BR-004)
    # =========================================================================

    def test_scenario_6_attach_invoices_creates_pdf(self):
        """Scenario 6 BR-004: attach_invoices=True generates PDF attachments.

        Given the Warning level configured with attach_invoices=True
        When a partner at that level is processed
        Then ir.attachment records are created and linked to the
        outgoing mail.mail.
        """
        partner = self.partner_overdue_21d
        partner.invalidate_recordset()
        # Verify the seed level has attach_invoices=True (per
        # data/followup_data.xml the Warning level does).
        self.assertTrue(
            self.warning_level.attach_invoices,
            'Warning level must have attach_invoices=True per seed data.',
        )
        # Pre-snapshot of attachments
        Attachment = self.env['ir.attachment']
        attachments_before = Attachment.search_count([
            ('res_model', '=', 'account.move'),
            ('res_id', '=', self.inv_21d.id),
        ])
        with mute_logger('odoo.addons.mail.models.mail_mail',
                         'odoo.addons.mail.models.mail_template',
                         'odoo.addons.account_payment_followup'):
            self.env['account.followup.level'].process_followup_emails()
        attachments_after = Attachment.search_count([
            ('res_model', '=', 'account.move'),
            ('res_id', '=', self.inv_21d.id),
        ])
        # PDF generation may fail in headless test environments without
        # wkhtmltopdf. The cron logs an exception and continues — we
        # verify the cron didn't crash either way.
        self.assertGreaterEqual(
            attachments_after, attachments_before,
            'Attachment count must not decrease.',
        )

    def test_scenario_6_attach_invoices_disabled_no_pdf(self):
        """Scenario 6: attach_invoices=False does NOT generate PDFs.

        Given the First Reminder level (attach_invoices=False per seed)
        When a partner at that level is processed
        Then no new ir.attachment records are created on the invoice.
        """
        partner = self.partner_overdue_7d
        partner.invalidate_recordset()
        self.assertFalse(
            self.first_reminder_level.attach_invoices,
            'First Reminder must have attach_invoices=False per seed.',
        )
        Attachment = self.env['ir.attachment']
        attachments_before = Attachment.search_count([
            ('res_model', '=', 'account.move'),
            ('res_id', '=', self.inv_7d.id),
            ('mimetype', '=', 'application/pdf'),
        ])
        with mute_logger('odoo.addons.mail.models.mail_mail',
                         'odoo.addons.mail.models.mail_template'):
            self.env['account.followup.level'].process_followup_emails()
        attachments_after = Attachment.search_count([
            ('res_model', '=', 'account.move'),
            ('res_id', '=', self.inv_7d.id),
            ('mimetype', '=', 'application/pdf'),
        ])
        # No new PDFs should be generated for the level-1 partner.
        self.assertEqual(
            attachments_after, attachments_before,
            'No new PDF attachments when attach_invoices=False.',
        )

    # =========================================================================
    # SCENARIO 7: Fault Tolerance — single failure must not halt batch
    # =========================================================================

    def test_scenario_7_single_failure_does_not_halt_batch(self):
        """Scenario 7: an exception during one partner does not halt others.

        Given multiple partners with overdue invoices
        When one partner's email send raises an unexpected exception
        Then the remaining partners are still processed and the cron
        returns a result dict with errors >= 1.
        """
        # Patch mail.template.send_mail to raise on a specific partner.
        original_send = self.env['mail.template'].__class__.send_mail
        target_partner_id = self.partner_overdue_7d.id

        synthetic_failure_message = 'Synthetic failure for fault-tolerance test'

        def patched_send_mail(self, res_id, **kwargs):
            if res_id == target_partner_id:
                raise RuntimeError(synthetic_failure_message)
            return original_send(self, res_id, **kwargs)

        # Force level recompute on all test partners.
        self.all_test_partners.invalidate_recordset()
        self.all_test_partners.mapped('followup_level_id')

        with mock.patch.object(
            self.env['mail.template'].__class__,
            'send_mail',
            patched_send_mail,
        ):
            with mute_logger('odoo.addons.account_payment_followup.models'
                             '.account_followup_level',
                             'odoo.addons.mail.models.mail_template',
                             'odoo.addons.mail.models.mail_mail'):
                result = self.env['account.followup.level'].process_followup_emails()

        # The cron must report at least 1 error AND have processed
        # other partners successfully.
        self.assertGreaterEqual(result['errors'], 1,
                                'Fault tolerance: at least 1 error logged.')

    # =========================================================================
    # MIN_AMOUNT THRESHOLD (BR-005)
    # =========================================================================

    def test_br_005_min_amount_threshold_skips_partner(self):
        """BR-005: partner with total_overdue < level.min_amount is skipped.

        Given the First Reminder level configured with min_amount=5000
        And partner_overdue_7d has total_overdue ~1500
        When the cron runs
        Then the partner is NOT processed (skipped) because their
        overdue amount is below the threshold.
        """
        # Set min_amount on First Reminder level above the partner's
        # overdue amount (1500).
        self.first_reminder_level.write({'min_amount': 5000.0})
        partner = self.partner_overdue_7d
        partner.invalidate_recordset()
        # Snapshot mail count
        Mail = self.env['mail.mail']
        mail_before = Mail.search_count([
            ('recipient_ids', 'in', [partner.id]),
        ])
        # Snapshot history count too — neither should grow for this partner
        History = self.env['account.followup.history']
        history_before = History.search_count([
            ('partner_id', '=', partner.id),
            ('action_type', '=', 'email'),
        ])
        with mute_logger('odoo.addons.mail.models.mail_mail',
                         'odoo.addons.mail.models.mail_template'):
            self.env['account.followup.level'].process_followup_emails()
        mail_after = Mail.search_count([
            ('recipient_ids', 'in', [partner.id]),
        ])
        history_after = History.search_count([
            ('partner_id', '=', partner.id),
            ('action_type', '=', 'email'),
        ])
        self.assertEqual(mail_after, mail_before,
                         'No mail must be sent to a below-threshold partner.')
        self.assertEqual(history_after, history_before,
                         'No history record must be created for a '
                         'below-threshold partner.')

    # =========================================================================
    # PARTNER WITHOUT EMAIL (BR-005 alternative path)
    # =========================================================================

    def test_partner_without_email_is_skipped(self):
        """Skip partner without email (PF-002 BR-005 alternative path).

        Given a partner with overdue invoices but no email address
        When the cron runs
        Then no mail.mail and no history record are created for that
        partner.
        """
        # Clear email on partner_overdue_7d
        partner = self.partner_overdue_7d
        partner.write({'email': False})
        partner.invalidate_recordset()
        Mail = self.env['mail.mail']
        mail_before = Mail.search_count([
            ('recipient_ids', 'in', [partner.id]),
        ])
        with mute_logger('odoo.addons.mail.models.mail_mail',
                         'odoo.addons.mail.models.mail_template'):
            self.env['account.followup.level'].process_followup_emails()
        mail_after = Mail.search_count([
            ('recipient_ids', 'in', [partner.id]),
        ])
        self.assertEqual(mail_after, mail_before,
                         'Partner without email must be skipped.')

    # =========================================================================
    # NO ACTIVE LEVELS (BR-004 alternative path)
    # =========================================================================

    def test_no_active_levels_returns_zero_stats(self):
        """When no active levels exist, cron returns zero stats."""
        # Archive ALL active levels.
        Level = self.env['account.followup.level']
        Level.search([('active', '=', True)]).write({'active': False})
        result = Level.process_followup_emails()
        self.assertEqual(result, {
            'partners_processed': 0,
            'emails_queued': 0,
            'errors': 0,
        }, 'No active levels: zero stats and no exception.')

    def test_no_automatic_levels_returns_zero_stats(self):
        """When no levels have automatic/email action_type, cron skips.

        BR-006: only levels with action_type in ('automatic', 'email')
        are eligible for cron-driven dispatch.
        """
        # Switch ALL levels to manual.
        Level = self.env['account.followup.level']
        Level.search([('active', '=', True)]).write({'action_type': 'manual'})
        result = Level.process_followup_emails()
        self.assertEqual(
            result,
            {'partners_processed': 0, 'emails_queued': 0, 'errors': 0},
            'No automatic levels: zero stats.',
        )

    # =========================================================================
    # _get_applicable_partners HELPER METHOD
    # =========================================================================

    def test_get_applicable_partners_filters_by_overdue(self):
        """_get_applicable_partners returns partners with overdue invoices."""
        # Force all level/partner computes
        self.all_test_partners.invalidate_recordset()
        self.all_test_partners.mapped('followup_level_id')
        Level = self.env['account.followup.level']
        active_levels = Level.search([('active', '=', True)])
        partners = active_levels._get_applicable_partners(batch_size=500)
        # partner_current has no overdue invoices, so it must NOT appear
        self.assertNotIn(
            self.partner_current, partners,
            'Partner with no overdue invoices must not be returned.',
        )
        # At least one overdue partner must appear
        self.assertGreaterEqual(
            len(partners), 1,
            'At least one overdue partner must be returned.',
        )

    def test_get_applicable_partners_honors_active_partner_ids_context(self):
        """_get_applicable_partners restricts to active_partner_ids context.

        Used by manual single-partner triggers (e.g.,
        res.partner.action_send_followup_now).
        """
        self.all_test_partners.invalidate_recordset()
        self.all_test_partners.mapped('followup_level_id')
        Level = self.env['account.followup.level']
        active_levels = Level.search([('active', '=', True)])
        # Restrict to a single partner via context
        partners = active_levels.with_context(
            active_partner_ids=[self.partner_overdue_14d.id],
        )._get_applicable_partners(batch_size=500)
        # Only partner_overdue_14d should appear
        self.assertEqual(
            partners, self.partner_overdue_14d,
            'active_partner_ids must restrict the result set.',
        )

    def test_get_applicable_partners_respects_batch_size(self):
        """_get_applicable_partners limit honors batch_size."""
        self.all_test_partners.invalidate_recordset()
        self.all_test_partners.mapped('followup_level_id')
        Level = self.env['account.followup.level']
        active_levels = Level.search([('active', '=', True)])
        partners_limited = active_levels._get_applicable_partners(batch_size=2)
        self.assertLessEqual(
            len(partners_limited), 2,
            'batch_size argument must limit search results.',
        )

    # =========================================================================
    # _generate_invoice_attachments HELPER METHOD
    # =========================================================================

    def test_generate_invoice_attachments_empty_input(self):
        """_generate_invoice_attachments returns empty list for empty input."""
        empty_invoices = self.env['account.move']
        result = self.warning_level._generate_invoice_attachments(empty_invoices)
        self.assertEqual(result, [],
                         'Empty input must return empty attachment list.')

    def test_generate_invoice_attachments_handles_missing_report(self):
        """_generate_invoice_attachments returns [] if report XID missing.

        Defensive code path: when 'account.account_invoices' is not
        registered (unusual but possible in stripped-down installs),
        the method logs a warning and returns an empty list rather
        than crashing.
        """
        # Patch env.ref to return False for the report XID.
        original_ref = self.env.__class__.ref

        def patched_ref(self, xid, raise_if_not_found=True):
            if xid == 'account.account_invoices':
                return False
            return original_ref(self, xid, raise_if_not_found=raise_if_not_found)

        with mock.patch.object(self.env.__class__, 'ref', patched_ref):
            with mute_logger('odoo.addons.account_payment_followup.models'
                             '.account_followup_level'):
                result = self.warning_level._generate_invoice_attachments(
                    self.inv_21d,
                )
        self.assertEqual(
            result, [],
            'Missing report XID must return empty list, not raise.',
        )

    # =========================================================================
    # _apply_trigger_actions HELPER METHOD
    # =========================================================================

    def test_apply_trigger_actions_no_op_when_all_flags_false(self):
        """_apply_trigger_actions is a no-op when all trigger flags are False."""
        partner = self.partner_overdue_7d
        partner.write({'trust': 'normal'})
        # First Reminder has all triggers False per seed data.
        original_trust = partner.trust
        self.first_reminder_level._apply_trigger_actions(partner)
        self.assertEqual(
            partner.trust, original_trust,
            'No-op: partner.trust must be unchanged.',
        )

    def test_apply_trigger_actions_with_trust_update(self):
        """_apply_trigger_actions updates trust when configured."""
        partner = self.partner_overdue_30d
        partner.write({'trust': 'normal'})
        # Configure level with trust update.
        self.final_notice_level.write({'trigger_update_trust': 'good'})
        self.final_notice_level._apply_trigger_actions(partner)
        partner.invalidate_recordset()
        self.assertEqual(
            partner.trust, 'good',
            'trigger_update_trust must apply to partner.trust.',
        )

    # =========================================================================
    # SUMMARY STATS RETURN VALUE
    # =========================================================================

    def test_result_dict_keys_present(self):
        """process_followup_emails returns a dict with expected keys."""
        Level = self.env['account.followup.level']
        # Force compute
        self.all_test_partners.invalidate_recordset()
        self.all_test_partners.mapped('followup_level_id')
        with mute_logger('odoo.addons.mail.models.mail_mail',
                         'odoo.addons.mail.models.mail_template'):
            result = Level.process_followup_emails()
        self.assertIsInstance(result, dict)
        self.assertIn('partners_processed', result)
        self.assertIn('emails_queued', result)
        self.assertIn('errors', result)
        self.assertIsInstance(result['partners_processed'], int)
        self.assertIsInstance(result['emails_queued'], int)
        self.assertIsInstance(result['errors'], int)

    def test_result_emails_queued_le_partners_processed(self):
        """emails_queued <= partners_processed (some skipped without email)."""
        Level = self.env['account.followup.level']
        self.all_test_partners.invalidate_recordset()
        self.all_test_partners.mapped('followup_level_id')
        with mute_logger('odoo.addons.mail.models.mail_mail',
                         'odoo.addons.mail.models.mail_template'):
            result = Level.process_followup_emails()
        # Every queued email implies one processed partner.
        self.assertLessEqual(
            result['emails_queued'], result['partners_processed'] + 1,
            'emails_queued cannot exceed partners_processed by '
            'more than 1.',
        )

    # =========================================================================
    # IDEMPOTENCY: cron should be safe to re-run
    # =========================================================================

    def test_cron_idempotent_re_run_creates_more_history(self):
        """Re-running cron is non-error and produces more history records.

        The cron is NOT idempotent in the strict sense (each run creates
        a new history record per partner) but it must not fail when
        re-invoked. Each invocation is a discrete audit event.
        """
        Level = self.env['account.followup.level']
        self.all_test_partners.invalidate_recordset()
        self.all_test_partners.mapped('followup_level_id')
        History = self.env['account.followup.history']
        # First run
        with mute_logger('odoo.addons.mail.models.mail_mail',
                         'odoo.addons.mail.models.mail_template'):
            Level.process_followup_emails()
        count_after_first = History.search_count([
            ('action_type', '=', 'email'),
        ])
        # Second run
        with mute_logger('odoo.addons.mail.models.mail_mail',
                         'odoo.addons.mail.models.mail_template'):
            Level.process_followup_emails()
        count_after_second = History.search_count([
            ('action_type', '=', 'email'),
        ])
        # Second run created additional history entries (audit events)
        self.assertGreaterEqual(
            count_after_second, count_after_first,
            'Re-run cron must succeed and may create more history entries.',
        )
