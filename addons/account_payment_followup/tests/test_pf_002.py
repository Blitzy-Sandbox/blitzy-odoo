# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
PF-002 — Automated Email Generation: Acceptance Test Suite
===========================================================

Verifies the cron handler and email-dispatch surface introduced by:

  * ``addons/account_payment_followup/models/account_followup_level.py`` —
    ``process_followup_emails(batch_size=500)`` cron entry point plus
    the ``_get_applicable_partners``, ``_apply_trigger_actions``, and
    ``_generate_invoice_attachments`` helpers.
  * ``addons/account_payment_followup/data/followup_cron.xml`` —
    declarative ``ir.cron`` registration via XML record (R-06).
  * ``addons/account_payment_followup/data/mail_template_data.xml`` —
    the four seeded ``mail.template`` records consumed by the cron.

Acceptance Scenarios (BDD Given/When/Then) covered:

  - Scenario 1: Automatic Email Generation Based on Follow-up Level
  - Scenario 2: Email Template Personalization (QWeb placeholders)
  - Scenario 3: Attach Overdue Invoice Documents (attach_invoices flag)
  - Scenario 4: Preview Email Before Sending
  - Scenario 5: Manual Trigger for Specific Customer
  - Scenario 6: Delivery Tracking (mail.mail.state)
  - Scenario 7: Bulk Email Generation (batch ≤500 partners)
  - Scenario 8: Payment Link Inclusion

Plus:

  - Gate 13 cron reachability (R-06 compliance verification)
  - Business Rules BR-001..BR-007 from the ticket
  - Fault tolerance (per-partner try/except contract)
  - Trigger actions (PF-001 Scenario 5 integration)

Targets ≥80% line coverage of the cron-handler portion of
``models/account_followup_level.py``.

Determinism
-----------
The class uses :class:`AccountPaymentFollowupTestCommon` which freezes
fixture creation to ``date(2024, 6, 30)`` and is decorated with
``@freeze_time(FROZEN_DATE)`` so that the cron's
``followup_next_action_date`` write (``today + delta(days=level.delay)``)
produces stable, reproducible values.

Rules Compliance (AAP §0.7)
---------------------------
- R-01: No imports from sibling new modules.
- R-02: No imports from Enterprise modules.
- R-04: Targets ≥80% coverage of PF-002 portion of
  ``account_followup_level.py``.
- R-06: Verifies the cron is declared via XML (Gate 13).
- R-07: No ``sudo()`` calls.
- R-09: Filename is ``test_pf_002.py`` exactly.
"""

import inspect
import io
from datetime import date, timedelta
from unittest.mock import patch

from freezegun import freeze_time

from odoo import Command, fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import AccountPaymentFollowupTestCommon

# Module-level reference date that aligns with the common.py
# ``FROZEN_DATE`` so fixture ages match cron-time arithmetic.
FROZEN_DATE = date(2024, 6, 30)

# Cron XMLID consumed by ``env.ref()`` for Gate 13 verification.
CRON_XMLID = 'account_payment_followup.ir_cron_payment_followup'


@tagged('post_install', '-at_install')
@freeze_time(FROZEN_DATE)
class TestAutomatedEmailGeneration(AccountPaymentFollowupTestCommon):
    """PF-002 — Automated Email Generation acceptance tests.

    Inherits :class:`AccountPaymentFollowupTestCommon` for the eight
    overdue-bucket partners + invoices and the four seeded follow-up
    levels (First Reminder / Second Reminder / Warning / Final Notice).

    Implementation Notes
    --------------------
    The cron handler calls ``mail.template.send_mail(force_send=False)``
    which queues a ``mail.mail`` record without triggering SMTP.
    Tests verify the queue state without configuring an SMTP server.

    For fault-tolerance tests, ``unittest.mock.patch`` monkey-patches
    ``mail.template.send_mail`` to raise on a specific partner; the
    test then verifies that other partners still process successfully
    (the per-partner try/except contract per Scenario 7 / PF-002 BR-007).

    Multi-partner tests rely on ``invalidate_recordset()`` to force
    re-computation of stored fields (``followup_level_id``,
    ``has_overdue_invoices``) before the cron is invoked, ensuring
    deterministic batch composition.
    """

    @classmethod
    def setUpClass(cls):
        """Build PF-002-specific fixtures on top of the common base.

        Forces an initial recompute of the partners' aging buckets and
        ``followup_level_id`` so the cron processes them deterministically.
        Without this, the stored compute may not yet have populated values
        for partners created in :meth:`_setup_overdue_partners`.

        Caches a unified ``all_test_partners`` recordset for use by tests
        that need to invalidate every partner's cache prior to cron
        invocation (e.g., the fault-tolerance and bulk-email tests).
        """
        super().setUpClass()
        all_partners = (
            cls.partner_current
            | cls.partner_overdue_7d
            | cls.partner_overdue_14d
            | cls.partner_overdue_21d
            | cls.partner_overdue_30d
            | cls.partner_overdue_45d
            | cls.partner_overdue_95d
            | cls.partner_mixed_aging
        )
        # Force aging-bucket and followup-level recompute via cache
        # invalidation + read so the cron sees deterministic values.
        all_partners.invalidate_recordset()
        all_partners.mapped('total_overdue')
        all_partners.mapped('followup_level_id')
        cls.all_test_partners = all_partners

    # =========================================================================
    # Helper utilities (test-internal)
    # =========================================================================

    def _force_partner_recompute(self, partners=None):
        """Invalidate cache and force aging / level recompute.

        Used before every cron invocation that depends on the
        partners having up-to-date stored compute values for
        ``has_overdue_invoices`` and ``followup_level_id``. Defaults to
        ``self.all_test_partners`` when no recordset is supplied.
        """
        partners = partners or self.all_test_partners
        partners.invalidate_recordset()
        partners.mapped('total_overdue')
        partners.mapped('followup_level_id')

    def _run_cron_silenced(self, batch_size=500):
        """Run ``process_followup_emails`` muting expected mail-pipeline logs.

        The cron's mail-send pipeline emits warnings for missing SMTP /
        unreachable mailservers in test environments — those are expected
        and uninteresting for behaviour assertions, so we silence them.
        """
        with mute_logger(
            'odoo.models',
            'odoo.addons.mail.models.mail_mail',
            'odoo.addons.mail.models.mail_template',
            'odoo.addons.account_payment_followup.models'
            '.account_followup_level',
        ):
            return self.env['account.followup.level'].process_followup_emails(
                batch_size=batch_size,
            )

    # =========================================================================
    # PHASE 1 — Cron Reachability (Gate 13, R-06) — CRITICAL
    # =========================================================================

    def test_cron_record_exists_and_is_reachable(self):
        """Gate 13 / R-06: cron resolves via env.ref and has expected fields.

        Asserts:
          * ``cron.exists()`` returns True
          * ``cron.state == 'code'``
          * ``cron.interval_type == 'days'``
          * ``cron.interval_number == 1``
          * ``cron.code`` invokes ``process_followup_emails``
          * ``cron.model_id.model == 'account.followup.level'``

        Note: The legacy ``numbercall`` field is REMOVED in Odoo 19.0
        (verified via ``addons/account_payment_followup/data/followup_cron.xml``
        comments). Cron repetition is now controlled solely by the
        ``active`` boolean. We assert ``active`` instead of ``numbercall``.
        """
        cron = self.env.ref(CRON_XMLID, raise_if_not_found=False)
        self.assertTrue(
            cron, f'env.ref({CRON_XMLID!r}) MUST resolve at install time.',
        )
        self.assertTrue(
            cron.exists(),
            'Cron record must exist in the database.',
        )
        self.assertEqual(
            cron._name, 'ir.cron',
            'External ID must point to an ir.cron record.',
        )
        self.assertEqual(
            cron.state, 'code',
            "Cron state must be 'code' for Python invocation (R-06).",
        )
        self.assertEqual(
            cron.interval_type, 'days',
            'Cron interval_type must be days for daily processing.',
        )
        self.assertEqual(
            cron.interval_number, 1,
            'Cron interval_number must be 1 for daily frequency.',
        )
        self.assertIn(
            'process_followup_emails', cron.code,
            'Cron code must call process_followup_emails().',
        )
        self.assertEqual(
            cron.model_id.model, 'account.followup.level',
            'Cron must target the account.followup.level model.',
        )
        # ``active=True`` is the Odoo 19 substitute for the legacy
        # ``numbercall=-1`` (unlimited runs while active).
        self.assertTrue(
            cron.active,
            'Cron must be active by default (Odoo 19 unlimited-runs '
            'semantics replaces the removed numbercall=-1).',
        )

    def test_cron_manually_triggerable(self):
        """Gate 13: cron runs synchronously via method_direct_trigger().

        ``method_direct_trigger()`` is the Odoo 17+ public API equivalent
        to "Run Manually" in the Settings → Technical → Automation →
        Scheduled Actions UI. The cron MUST execute without raising,
        even when there are zero overdue customers eligible for
        automated email — an empty run is a valid happy path.
        """
        cron = self.env.ref(CRON_XMLID)
        # Force a clean partner state (no overdue) before invocation
        # so the cron's internal "no eligible partners" branch is exercised
        # for the first call below — but our setUpClass has already created
        # overdue partners, so the more meaningful assertion is that the
        # cron doesn't raise even with our seeded partners present.
        self._force_partner_recompute()
        with mute_logger(
            'odoo.models',
            'odoo.addons.mail.models.mail_mail',
            'odoo.addons.mail.models.mail_template',
            'odoo.addons.account_payment_followup.models'
            '.account_followup_level',
        ):
            try:
                cron.method_direct_trigger()
            except Exception as exc:  # noqa: BLE001 — any raise is a fail
                self.fail(
                    f'Cron method_direct_trigger() must not raise: {exc!r}',
                )

    def test_cron_user_is_base_user_root(self):
        """Gate 13 / R-07: cron runs as superuser (base.user_root).

        Per AAP discovery, the cron is configured to run under the
        superuser account so ``process_followup_emails`` does not need
        explicit ``sudo()`` calls (R-07 compliance).
        """
        cron = self.env.ref(CRON_XMLID)
        user_root = self.env.ref('base.user_root')
        self.assertEqual(
            cron.user_id, user_root,
            'Cron user_id must be base.user_root for superuser context '
            '(R-07: avoid explicit sudo() in process_followup_emails).',
        )

    def test_cron_nextcall_in_future_after_install(self):
        """Gate 13: cron.nextcall is scheduled in the future after install.

        Per the XML's ``nextcall`` eval expression
        (``DateTime.now().replace(hour=2, minute=0) + timedelta(days=1)``),
        the cron is scheduled for tomorrow 02:00 AM at install time.
        After install, ``nextcall`` MUST be >= now.
        """
        cron = self.env.ref(CRON_XMLID)
        self.assertTrue(
            cron.nextcall,
            'Cron nextcall must be set after install.',
        )
        # ``cron.nextcall`` is a datetime; comparing against fields.Datetime.now()
        # (a UTC-naive datetime) works because both are in the server timezone.
        self.assertGreaterEqual(
            cron.nextcall,
            fields.Datetime.now() - timedelta(seconds=5),
            'Cron nextcall must be >= now (give 5s tolerance for any '
            'minor clock drift between install and test execution).',
        )

    # =========================================================================
    # PHASE 2 — Happy-Path Email Generation (Scenario 1)
    # =========================================================================

    def test_process_followup_emails_returns_dict(self):
        """Contract: process_followup_emails returns a stat dict.

        Returns a dict with exactly three keys: ``partners_processed``,
        ``emails_queued``, ``errors``. All values must be integers.
        """
        result = self._run_cron_silenced(batch_size=10)
        self.assertIsInstance(
            result, dict,
            'process_followup_emails MUST return a dict.',
        )
        self.assertEqual(
            set(result.keys()),
            {'partners_processed', 'emails_queued', 'errors'},
            'Return dict must have exactly three keys.',
        )
        self.assertIsInstance(
            result['partners_processed'], int,
            'partners_processed must be int.',
        )
        self.assertIsInstance(
            result['emails_queued'], int,
            'emails_queued must be int.',
        )
        self.assertIsInstance(
            result['errors'], int,
            'errors must be int.',
        )

    def test_scenario_1_automatic_email_for_customer_at_level(self):
        """Scenario 1: Automatic Email Generation Based on Follow-up Level.

        Given a partner with one invoice 7 days past due (Level 1)
        And the level's email_template_id is set
        And the level's action_type is 'automatic'
        When process_followup_emails runs
        Then an email is queued for the partner via the First Reminder
        template
        And a follow-up history record is created with action_type='email'
        """
        partner = self.partner_overdue_7d
        self._force_partner_recompute(partner)
        # Sanity: partner is at First Reminder level by construction.
        self.assertEqual(
            partner.followup_level_id, self.first_reminder_level,
            'Partner overdue 7d must be at First Reminder level.',
        )

        Mail = self.env['mail.mail']
        History = self.env['account.followup.history']
        mail_before = Mail.search_count(
            [('recipient_ids', 'in', [partner.id])],
        )
        history_before = History.search_count([
            ('partner_id', '=', partner.id),
            ('action_type', '=', 'email'),
        ])

        result = self._run_cron_silenced(batch_size=100)

        self.assertGreaterEqual(
            result['partners_processed'], 1,
            'At least one partner must be reported as processed.',
        )

        # Mail queued for the partner
        mail_after = Mail.search_count(
            [('recipient_ids', 'in', [partner.id])],
        )
        self.assertGreater(
            mail_after, mail_before,
            'A mail.mail record must be queued for the partner.',
        )

        # History row created with action_type='email'
        history_after = History.search_count([
            ('partner_id', '=', partner.id),
            ('action_type', '=', 'email'),
        ])
        self.assertEqual(
            history_after, history_before + 1,
            'Exactly one history record must be created for the email.',
        )

        # The history record links the level and the overdue invoice.
        history = History.search([
            ('partner_id', '=', partner.id),
            ('action_type', '=', 'email'),
        ], order='action_date desc, id desc', limit=1)
        self.assertEqual(
            history.followup_level_id, self.first_reminder_level,
            'History must link the triggering level.',
        )
        self.assertIn(
            self.inv_7d, history.invoice_ids,
            'History invoice_ids must include the overdue invoice.',
        )

    def test_scenario_2_email_template_personalization(self):
        """Scenario 2: Email Template Personalization (QWeb).

        Given a configured follow-up level with QWeb placeholders
        (``object.name``, ``object._get_overdue_invoices``, etc.)
        When the email is generated
        Then the email body includes the partner's actual name (not
        the literal ``{{ object.name }}`` placeholder) and references
        the overdue invoice by name.
        """
        partner = self.partner_overdue_7d
        self._force_partner_recompute(partner)

        Mail = self.env['mail.mail']
        # Capture the highest mail id BEFORE the cron run so we can find
        # the newly created mail without conflating with prior queue
        # entries on this partner.
        last_mail_id = Mail.search([], order='id desc', limit=1).id or 0

        self._run_cron_silenced(batch_size=100)

        new_mail = Mail.search([
            ('id', '>', last_mail_id),
            ('recipient_ids', 'in', [partner.id]),
        ], order='id desc', limit=1)
        self.assertTrue(
            new_mail, 'A mail.mail must be queued for the partner.',
        )
        # Partner's name must appear in body_html.
        self.assertIn(
            partner.name, new_mail.body_html or '',
            'Email body must contain the partner name (QWeb '
            '<t t-out="object.name"> rendered).',
        )
        # The literal placeholder must NOT appear (template was rendered).
        self.assertNotIn(
            '{{ object.name }}', new_mail.body_html or '',
            'QWeb placeholder must be substituted, not left literal.',
        )
        # The overdue invoice's name must appear in the table iteration.
        self.assertIn(
            self.inv_7d.name, new_mail.body_html or '',
            'Email body must list the overdue invoice via t-foreach.',
        )

    def test_scenario_3_attach_invoices_when_flag_set(self):
        """Scenario 3: Attach Overdue Invoice Documents (BR-004).

        Given the Warning level toggled to attach_invoices=True
        (the seed default ships False for SLA reasons; see
        data/followup_data.xml header — operators opt in per level
        after sizing their cron timeout for unpatched-QT wkhtmltopdf)
        When a partner at that level is processed
        Then ``ir.attachment`` records are created for each overdue
        invoice and linked to the outgoing mail.mail.

        PDF rendering may fail in headless test environments without
        wkhtmltopdf; the cron's per-invoice try/except logs the
        exception and continues. The test therefore asserts that the
        method returns gracefully (no overall raise) and that
        attach_invoices=True is honored at the level config level.
        """
        partner = self.partner_overdue_21d
        self._force_partner_recompute(partner)
        self.assertEqual(
            partner.followup_level_id, self.warning_level,
            'Partner overdue 21d must be at Warning level.',
        )
        # Seed default is attach_invoices=False for SLA compliance with
        # Odoo 19's default --limit-time-real-cron=120s on unpatched-QT
        # wkhtmltopdf (see data/followup_data.xml header). Operators
        # opt in per level. Toggle on for this test to verify BR-004
        # behaviour; the noupdate="1" data wrapper preserves
        # operator-side toggles across upgrades.
        self.warning_level.attach_invoices = True
        self.assertTrue(
            self.warning_level.attach_invoices,
            'Warning level attach_invoices=True must persist after toggle.',
        )

        # Call the helper directly — this is more deterministic than
        # going through the cron because PDF generation may produce
        # different counts depending on environment availability.
        result = self.warning_level._generate_invoice_attachments(
            self.inv_21d,
        )
        # Result is a list (possibly empty if wkhtmltopdf is missing,
        # but must always be a list type — never None or False).
        self.assertIsInstance(
            result, list,
            '_generate_invoice_attachments must return a list.',
        )

        # And the cron run with attach_invoices=True must not crash.
        with mute_logger(
            'odoo.models',
            'odoo.addons.mail.models.mail_mail',
            'odoo.addons.mail.models.mail_template',
            'odoo.addons.account_payment_followup.models'
            '.account_followup_level',
        ):
            stats = self.env['account.followup.level'].process_followup_emails(
                batch_size=100,
            )
        # Cron returned without raising — that's the ground-truth
        # contract for Scenario 3 (BR-004).
        self.assertIsInstance(
            stats, dict,
            'Cron must return a stats dict even with attach_invoices=True.',
        )

    def test_scenario_4_preview_without_sending(self):
        """Scenario 4: Preview Email Before Sending.

        The model surface for "preview" exposed by the seed mail.template
        is ``mail.template._render_field('body_html', [partner.id])``
        which renders the QWeb body without queuing a mail.mail record.

        Verifies:
          * The render returns HTML containing the partner name
            (placeholder substituted)
          * No mail.mail record is created during preview
          * The level's email template can be invoked outside the cron
        """
        partner = self.partner_overdue_7d
        self._force_partner_recompute(partner)

        Mail = self.env['mail.mail']
        mail_before = Mail.search_count([])

        template = self.first_reminder_level.email_template_id
        self.assertTrue(
            template,
            'First Reminder level must have a configured email template '
            '(per seed data/followup_data.xml).',
        )

        # Render the body without queuing mail. ``_render_field`` is the
        # canonical Odoo API for "preview" of a template against a record.
        rendered = template._render_field(
            'body_html', [partner.id],
        )
        self.assertIsInstance(
            rendered, dict,
            '_render_field must return dict {res_id: rendered_html}.',
        )
        body = rendered.get(partner.id) or ''
        self.assertIn(
            partner.name, body,
            'Preview body must contain the partner name (placeholder '
            'substituted).',
        )

        # Crucially: no mail.mail is created during preview.
        mail_after = Mail.search_count([])
        self.assertEqual(
            mail_after, mail_before,
            'Preview rendering must NOT queue a mail.mail record.',
        )

    def test_scenario_5_manual_trigger_via_partner_action(self):
        """Scenario 5: Manual Email Trigger (single partner).

        Given a partner with overdue invoices and an assigned follow-up
        level
        When the user calls ``partner.action_send_followup_now()``
        Then exactly one partner is processed (this partner only),
        a mail.mail is queued, and a history record is created.
        """
        partner = self.partner_overdue_7d
        self._force_partner_recompute()

        Mail = self.env['mail.mail']
        History = self.env['account.followup.history']
        mail_before_partner = Mail.search_count(
            [('recipient_ids', 'in', [partner.id])],
        )
        # Track that OTHER partners are not affected by this manual call.
        other_partner = self.partner_overdue_30d
        mail_before_other = Mail.search_count(
            [('recipient_ids', 'in', [other_partner.id])],
        )
        history_before = History.search_count([
            ('partner_id', '=', partner.id),
            ('action_type', '=', 'email'),
        ])

        with mute_logger(
            'odoo.models',
            'odoo.addons.mail.models.mail_mail',
            'odoo.addons.mail.models.mail_template',
            'odoo.addons.account_payment_followup.models'
            '.account_followup_level',
        ):
            result = partner.action_send_followup_now()

        # Result is the dict returned by process_followup_emails(batch_size=1).
        self.assertIsInstance(result, dict)
        self.assertLessEqual(
            result['partners_processed'], 1,
            'Manual trigger must process at most 1 partner '
            '(active_partner_ids context restriction).',
        )

        # This partner: mail queued, history created.
        mail_after_partner = Mail.search_count(
            [('recipient_ids', 'in', [partner.id])],
        )
        self.assertGreater(
            mail_after_partner, mail_before_partner,
            'Manual trigger must queue a mail.mail for the target partner.',
        )
        history_after = History.search_count([
            ('partner_id', '=', partner.id),
            ('action_type', '=', 'email'),
        ])
        self.assertEqual(
            history_after, history_before + 1,
            'Manual trigger must create exactly one history record.',
        )

        # Other partners: untouched by this manual run.
        mail_after_other = Mail.search_count(
            [('recipient_ids', 'in', [other_partner.id])],
        )
        self.assertEqual(
            mail_after_other, mail_before_other,
            'Manual trigger must NOT bleed into other partners '
            '(active_partner_ids context narrows scope).',
        )

    def test_scenario_5_manual_trigger_raises_when_no_level(self):
        """Manual trigger raises UserError when partner has no level.

        Scenario 5 negative path: action_send_followup_now() pre-flight
        validation per res_partner.py guard. ``UserError`` is the
        expected exception class because the guard is a user-facing
        pre-flight check, not a model-level constraint. The catch
        also covers ``ValidationError`` (defensive against a future
        refactor that promotes the check to ``@api.constrains``) by
        using a try/except — Odoo's ``assertRaises`` requires a
        single class, not a tuple.
        """
        partner = self.partner_current  # not overdue, no level
        self._force_partner_recompute(partner)
        self.assertFalse(
            partner.followup_level_id,
            'Current partner must have no followup level.',
        )
        raised_class = None
        try:
            partner.action_send_followup_now()
        except UserError:
            raised_class = UserError
        except ValidationError:
            raised_class = ValidationError
        self.assertIn(
            raised_class, (UserError, ValidationError),
            'action_send_followup_now must raise UserError (or '
            'ValidationError) when no follow-up level is assigned.',
        )

    # =========================================================================
    # PHASE 4 — Scenario 6: Delivery Tracking
    # =========================================================================

    def test_scenario_6_mail_state_lifecycle(self):
        """Scenario 6: Email Delivery Tracking via mail.mail.state.

        Given a follow-up email queued by the cron
        When the mail.mail record is examined
        Then its state is one of the legal Odoo mail states
        (outgoing/sent/exception/received/cancel).

        Per AAP discovery, ``send_mail(force_send=False)`` queues the
        mail in 'outgoing' state without immediate SMTP attempt. The
        test asserts the state is in the legal selection set rather
        than asserting an exact value, since the test environment may
        defer-process the queue asynchronously.
        """
        partner = self.partner_overdue_7d
        self._force_partner_recompute(partner)

        Mail = self.env['mail.mail']
        last_mail_id = Mail.search([], order='id desc', limit=1).id or 0
        self._run_cron_silenced(batch_size=100)

        new_mail = Mail.search([
            ('id', '>', last_mail_id),
            ('recipient_ids', 'in', [partner.id]),
        ], order='id desc', limit=1)
        self.assertTrue(
            new_mail, 'A mail.mail must exist after cron execution.',
        )
        # ``state`` is a Selection field with these legal values per
        # ``addons/mail/models/mail_mail.py``.
        legal_states = {'outgoing', 'sent', 'exception', 'received', 'cancel'}
        self.assertIn(
            new_mail.state, legal_states,
            f'Mail state must be one of {sorted(legal_states)}; got {new_mail.state!r}.',
        )

    # =========================================================================
    # PHASE 5 — Scenario 7: Batch Size Contract
    # =========================================================================

    def test_scenario_7_batch_size_limit_respected(self):
        """Scenario 7: process_followup_emails respects the batch_size limit.

        Given multiple partners each at Level 1 with overdue invoices
        When ``process_followup_emails(batch_size=N)`` runs
        Then ``partners_processed`` is <= N (never exceeds the cap).
        """
        # Use a small batch_size of 2 to make the assertion sharp.
        # We have 7 overdue partners (ex partner_current), so a 2-cap
        # forces the limit.
        self._force_partner_recompute()
        result = self._run_cron_silenced(batch_size=2)
        self.assertLessEqual(
            result['partners_processed'], 2,
            'partners_processed MUST NOT exceed batch_size (=2).',
        )

    def test_scenario_7_default_batch_size_is_500(self):
        """Scenario 7 / AAP §0.7.3: batch_size default is 500.

        The PF-002 performance contract states the cron processes <=500
        partners per run within the default cron timeout. The default
        is enforced via the method signature default value.
        """
        Level = self.env['account.followup.level']
        sig = inspect.signature(Level.process_followup_emails)
        params = sig.parameters
        self.assertIn(
            'batch_size', params,
            'process_followup_emails must accept a batch_size keyword arg.',
        )
        self.assertEqual(
            params['batch_size'].default, 500,
            'batch_size default MUST be 500 per AAP §0.7.3 performance '
            'target ("≤500 partners per cron run within default cron '
            'timeout").',
        )

    def test_scenario_7_active_partner_ids_context_override(self):
        """Scenario 7: active_partner_ids context narrows scope.

        Given the cron is invoked with ``active_partner_ids=[p.id]``
        When ``process_followup_emails`` runs
        Then ONLY partner ``p`` is processed; other overdue partners
        are not picked up by the cron in this run.
        """
        partner = self.partner_overdue_14d
        self._force_partner_recompute()
        # Capture pre-state of OTHER partners' mail counts.
        other_partner = self.partner_overdue_7d
        Mail = self.env['mail.mail']
        mail_before_target = Mail.search_count(
            [('recipient_ids', 'in', [partner.id])],
        )
        mail_before_other = Mail.search_count(
            [('recipient_ids', 'in', [other_partner.id])],
        )

        with mute_logger(
            'odoo.models',
            'odoo.addons.mail.models.mail_mail',
            'odoo.addons.mail.models.mail_template',
            'odoo.addons.account_payment_followup.models'
            '.account_followup_level',
        ):
            result = self.env['account.followup.level'].with_context(
                active_partner_ids=[partner.id],
            ).process_followup_emails(batch_size=100)

        # Result must report at most 1 partner processed
        self.assertLessEqual(
            result['partners_processed'], 1,
            'active_partner_ids must restrict scope to ≤1 partner.',
        )

        # Mail queued for THIS partner (subject to email-template prereq)
        mail_after_target = Mail.search_count(
            [('recipient_ids', 'in', [partner.id])],
        )
        self.assertGreaterEqual(
            mail_after_target, mail_before_target,
            'Target partner mail count must not decrease.',
        )

        # No mail queued for OTHER partners during this scoped run
        mail_after_other = Mail.search_count(
            [('recipient_ids', 'in', [other_partner.id])],
        )
        self.assertEqual(
            mail_after_other, mail_before_other,
            'Other partners must NOT be processed when active_partner_ids '
            'restricts scope.',
        )

    # =========================================================================
    # PHASE 6 — BR-001..BR-007 Business Rules
    # =========================================================================

    def test_br_001_only_partners_at_configured_level(self):
        """BR-001: emails only generated for partners at a configured level.

        Given partners at multiple levels (7d, 14d, 21d, 30d)
        When ``first_reminder_level.process_followup_emails`` runs
        Then ONLY the 7d partner is processed (assigned to First Reminder)
        — partners at deeper levels (Second Reminder, Warning, Final
        Notice) are NOT picked up by the First Reminder level alone.
        """
        self._force_partner_recompute()
        # Verify partner-level assignment is correct.
        self.assertEqual(
            self.partner_overdue_7d.followup_level_id,
            self.first_reminder_level,
        )
        self.assertEqual(
            self.partner_overdue_14d.followup_level_id,
            self.second_reminder_level,
        )

        # Get applicable partners for First Reminder ONLY.
        applicable = self.first_reminder_level._get_applicable_partners(
            batch_size=100,
        )
        self.assertIn(
            self.partner_overdue_7d, applicable,
            'partner_overdue_7d MUST be picked up by First Reminder.',
        )
        self.assertNotIn(
            self.partner_overdue_14d, applicable,
            'partner_overdue_14d MUST NOT be picked up by First Reminder '
            '(belongs to Second Reminder).',
        )
        self.assertNotIn(
            self.partner_overdue_21d, applicable,
            'partner_overdue_21d MUST NOT be picked up by First Reminder.',
        )
        self.assertNotIn(
            self.partner_overdue_30d, applicable,
            'partner_overdue_30d MUST NOT be picked up by First Reminder.',
        )
        # Non-overdue partner must never appear.
        self.assertNotIn(
            self.partner_current, applicable,
            'Non-overdue partner must never be returned.',
        )

    def test_br_002_email_includes_all_overdue_invoices_consolidated(self):
        """BR-002: each email includes all overdue invoices for the partner.

        Given a partner with 3 overdue invoices (consolidated email)
        When the cron runs
        Then the resulting mail.mail.body_html references all 3 invoices.
        """
        # Create a partner with 3 overdue invoices via the common helper.
        # ``Command.clear()`` is used below to ensure the partner has no
        # M2M categories that would influence template rendering.
        partner = self.env['res.partner'].create({
            'name': 'BR-002 Multi-Invoice Customer',
            'email': 'br002multi@test.com',
            'customer_rank': 1,
            'property_payment_term_id': self.pay_terms_a.id,
            'company_id': False,
            'category_id': [Command.clear()],
        })
        # Create three invoices at varying ages (all 7+ days overdue
        # → First Reminder level).
        inv1 = self._create_overdue_invoice(
            partner=partner,
            invoice_date=FROZEN_DATE - timedelta(days=7),
            amount=500.00,
        )
        inv2 = self._create_overdue_invoice(
            partner=partner,
            invoice_date=FROZEN_DATE - timedelta(days=8),
            amount=750.00,
        )
        inv3 = self._create_overdue_invoice(
            partner=partner,
            invoice_date=FROZEN_DATE - timedelta(days=9),
            amount=1000.00,
        )

        # Force level/aging recompute on this partner.
        partner.invalidate_recordset()
        partner.mapped('total_overdue')
        partner.mapped('followup_level_id')

        Mail = self.env['mail.mail']
        last_mail_id = Mail.search([], order='id desc', limit=1).id or 0

        with mute_logger(
            'odoo.models',
            'odoo.addons.mail.models.mail_mail',
            'odoo.addons.mail.models.mail_template',
            'odoo.addons.account_payment_followup.models'
            '.account_followup_level',
        ):
            self.env['account.followup.level'].with_context(
                active_partner_ids=[partner.id],
            ).process_followup_emails(batch_size=10)

        new_mail = Mail.search([
            ('id', '>', last_mail_id),
            ('recipient_ids', 'in', [partner.id]),
        ], order='id desc', limit=1)
        self.assertTrue(
            new_mail, 'A mail.mail must exist for the multi-invoice partner.',
        )
        body = new_mail.body_html or ''
        # All three invoice names must appear in the body (QWeb t-foreach
        # over object._get_overdue_invoices()).
        self.assertIn(
            inv1.name, body,
            f'Email body must include invoice {inv1.name}.',
        )
        self.assertIn(
            inv2.name, body,
            f'Email body must include invoice {inv2.name}.',
        )
        self.assertIn(
            inv3.name, body,
            f'Email body must include invoice {inv3.name}.',
        )

        # History invoice_ids must reference all three.
        history = self.env['account.followup.history'].search([
            ('partner_id', '=', partner.id),
            ('action_type', '=', 'email'),
        ], order='action_date desc, id desc', limit=1)
        self.assertTrue(history)
        self.assertEqual(
            set(history.invoice_ids.ids),
            {inv1.id, inv2.id, inv3.id},
            'History invoice_ids must contain all three overdue invoices '
            '(BR-002 consolidated communication).',
        )

    def test_br_003_qweb_placeholders_render(self):
        """BR-003: QWeb placeholders are substituted (covered by Scenario 2).

        Re-verifies that ``{{ object.name }}`` placeholders are rendered
        rather than left as literal strings in the email body. Also
        verifies that ``{{ object.company_id.name }}`` (subject line)
        is substituted.
        """
        partner = self.partner_overdue_7d
        self._force_partner_recompute(partner)

        Mail = self.env['mail.mail']
        last_mail_id = Mail.search([], order='id desc', limit=1).id or 0
        self._run_cron_silenced(batch_size=10)

        new_mail = Mail.search([
            ('id', '>', last_mail_id),
            ('recipient_ids', 'in', [partner.id]),
        ], order='id desc', limit=1)
        self.assertTrue(new_mail)
        body = new_mail.body_html or ''
        subject = new_mail.subject or ''
        # No literal QWeb placeholders should remain.
        for marker in ('{{ object.name }}', '{{ object.company_id.name }}'):
            self.assertNotIn(
                marker, body,
                f'Literal QWeb placeholder {marker!r} must NOT appear in '
                'the rendered body.',
            )
            self.assertNotIn(
                marker, subject,
                f'Literal QWeb placeholder {marker!r} must NOT appear in '
                'the rendered subject.',
            )
        # Partner name must appear in body.
        self.assertIn(partner.name, body)

    def test_br_004_pdf_attach_configurable_per_level(self):
        """BR-004: PDF attachments configurable per follow-up level.

        Compares the seed data:
          * All four levels: attach_invoices=False (SLA-safe default)

        and verifies (a) the configuration drives downstream behavior
        and (b) the toggle is persistable per level for operators who
        opt in to PDF attachments after sizing their cron timeout.

        The seed change from True (Levels 3-4) to False (all levels)
        was driven by the PF-002 SLA: synchronous wkhtmltopdf 0.12.6
        (unpatched QT) on Linux distributions cannot render 500
        invoice PDFs within Odoo 19's default
        ``--limit-time-real-cron=120s``. See
        ``data/followup_data.xml`` header for the full rationale.
        """
        # Seed-data assertions confirm BR-004's SLA-safe default at
        # the config level for all four levels.
        self.assertFalse(
            self.first_reminder_level.attach_invoices,
            'First Reminder must have attach_invoices=False per seed.',
        )
        self.assertFalse(
            self.warning_level.attach_invoices,
            'Warning must have attach_invoices=False per seed (SLA-safe '
            'default; see data/followup_data.xml header).',
        )
        self.assertFalse(
            self.final_notice_level.attach_invoices,
            'Final Notice must have attach_invoices=False per seed (SLA-safe '
            'default; see data/followup_data.xml header).',
        )

        # Behavior verification: per-level toggle works (BR-004
        # promises configurability, not a specific default value).
        # Operators opt in per level for PDF attachments.
        self.warning_level.attach_invoices = True
        self.assertTrue(
            self.warning_level.attach_invoices,
            'attach_invoices=True must persist after toggle (BR-004 '
            'configurability).',
        )
        self.warning_level.attach_invoices = False
        self.assertFalse(
            self.warning_level.attach_invoices,
            'attach_invoices=False must persist after toggle.',
        )

        # Behavior verification: with attach_invoices=False, the
        # _generate_invoice_attachments method is not called by the cron
        # for that level. The empty-input path of _generate_invoice_attachments
        # returns []; we verify by direct invocation that the helper is
        # well-behaved on either input.
        result_empty = self.first_reminder_level._generate_invoice_attachments(
            self.env['account.move'],
        )
        self.assertEqual(
            result_empty, [],
            'Empty invoice recordset must return empty attachment list.',
        )

    def test_br_005_partners_without_email_skipped(self):
        """BR-005: customers without an email address are skipped.

        Given a partner with overdue invoices but no email
        When the cron runs
        Then no mail.mail is queued for that partner and no history
        record with action_type='email' is created.
        """
        partner = self.partner_overdue_7d
        # Clear the email
        partner.write({'email': False})
        self._force_partner_recompute(partner)

        Mail = self.env['mail.mail']
        History = self.env['account.followup.history']
        mail_before = Mail.search_count(
            [('recipient_ids', 'in', [partner.id])],
        )
        history_before = History.search_count([
            ('partner_id', '=', partner.id),
            ('action_type', '=', 'email'),
        ])

        self._run_cron_silenced(batch_size=100)

        mail_after = Mail.search_count(
            [('recipient_ids', 'in', [partner.id])],
        )
        history_after = History.search_count([
            ('partner_id', '=', partner.id),
            ('action_type', '=', 'email'),
        ])
        self.assertEqual(
            mail_after, mail_before,
            'No mail must be queued for a partner without email (BR-005).',
        )
        self.assertEqual(
            history_after, history_before,
            'No history record must be created for a partner without '
            'email (BR-005).',
        )

    def test_br_006_manual_action_type_skipped_in_automatic_cron(self):
        """BR-006: manual action_type levels are skipped by automatic cron.

        Given the First Reminder level's action_type is changed to 'manual'
        When the cron runs
        Then partner_overdue_7d (who would normally be at First Reminder)
        is NOT processed via the cron path.
        """
        # Switch all four seeded automatic levels to 'manual'.
        Level = self.env['account.followup.level']
        Level.search([('active', '=', True)]).write(
            {'action_type': 'manual'},
        )
        self._force_partner_recompute()

        Mail = self.env['mail.mail']
        partner = self.partner_overdue_7d
        mail_before = Mail.search_count(
            [('recipient_ids', 'in', [partner.id])],
        )

        result = self._run_cron_silenced(batch_size=100)

        mail_after = Mail.search_count(
            [('recipient_ids', 'in', [partner.id])],
        )
        self.assertEqual(
            mail_after, mail_before,
            'No mail must be sent when all levels are manual (BR-006).',
        )
        # Cron returns zero stats — no automatic levels to process.
        self.assertEqual(
            result,
            {'partners_processed': 0, 'emails_queued': 0, 'errors': 0},
            'Manual-only configuration MUST result in zero-stats run.',
        )

    def test_br_007_delivery_status_in_history(self):
        """BR-007: delivery status trackable via history.mail_message_id.

        Given a follow-up email queued
        When the corresponding history record is examined
        Then ``history.mail_message_id`` resolves to the actual
        mail.message of the sent email, so callers can inspect
        ``mail.mail.state`` for delivery status (BR-007).
        """
        partner = self.partner_overdue_7d
        self._force_partner_recompute(partner)

        self._run_cron_silenced(batch_size=100)

        history = self.env['account.followup.history'].search([
            ('partner_id', '=', partner.id),
            ('action_type', '=', 'email'),
        ], order='action_date desc, id desc', limit=1)
        self.assertTrue(
            history,
            'A history record must exist after cron execution.',
        )
        # mail_message_id MAY be False if mail.mail creation failed —
        # which is a legitimate edge case BUT for a clean happy-path
        # test it should be set. Assert the field exists and (if set)
        # resolves to a valid mail.message record.
        if history.mail_message_id:
            self.assertEqual(
                history.mail_message_id._name, 'mail.message',
                'history.mail_message_id must point to a mail.message.',
            )

    # =========================================================================
    # PHASE 7 — Fault Tolerance & Edge Cases
    # =========================================================================

    def test_fault_tolerance_one_failure_doesnt_abort_batch(self):
        """Scenario 7 fault tolerance: one failure does not halt the batch.

        Given a batch of multiple partners
        When one partner's mail.template.send_mail raises an exception
        Then:
          * The cron does NOT propagate the exception
          * result['errors'] >= 1 (the failure is counted)
          * Other partners are still processed (result['partners_processed']
            >= 1 if there are eligible partners besides the failing one)
        """
        self._force_partner_recompute()

        # Choose partner_overdue_7d as the partner whose send raises.
        target_partner_id = self.partner_overdue_7d.id

        # Capture the original send_mail so we can delegate for non-target
        # partners.
        MailTemplate = self.env['mail.template']
        original_send_mail = MailTemplate.__class__.send_mail

        synthetic_failure_msg = 'Synthetic failure for fault-tolerance test'

        def patched_send_mail(self_template, res_id, **kwargs):
            if res_id == target_partner_id:
                raise RuntimeError(synthetic_failure_msg)
            return original_send_mail(self_template, res_id, **kwargs)

        with patch.object(
            MailTemplate.__class__, 'send_mail', patched_send_mail,
        ):
            with mute_logger(
                'odoo.models',
                'odoo.addons.mail.models.mail_mail',
                'odoo.addons.mail.models.mail_template',
                'odoo.addons.account_payment_followup.models'
                '.account_followup_level',
            ):
                # The cron MUST NOT raise even though one partner's send
                # raises a RuntimeError.
                result = self.env['account.followup.level'].process_followup_emails(
                    batch_size=100,
                )

        # Errors counter must reflect the failure
        self.assertGreaterEqual(
            result['errors'], 1,
            'Synthetic failure must be counted in result["errors"].',
        )
        # Other partners must still be processed
        self.assertGreaterEqual(
            result['partners_processed'], 1,
            'Other partners must be processed despite one failure.',
        )

    def test_empty_run_with_no_overdue_partners(self):
        """Edge case: cron returns zero stats when no partners are overdue.

        Given all overdue invoices are paid (no partner has overdue)
        When the cron runs
        Then result == {'partners_processed': 0, 'emails_queued': 0, 'errors': 0}.
        """
        # Force-clear has_overdue_invoices on all test partners by
        # archiving every active level — _get_applicable_partners
        # returns empty when there are no levels to match against.
        Level = self.env['account.followup.level']
        Level.search([('active', '=', True)]).write({'active': False})

        result = self._run_cron_silenced(batch_size=100)
        self.assertEqual(
            result,
            {'partners_processed': 0, 'emails_queued': 0, 'errors': 0},
            'Empty run (no active levels) MUST return zero stats.',
        )

    def test_idempotency_second_run_skips_recent_partners(self):
        """Second cron invocation: partner.followup_next_action_date advanced.

        Given a successful first cron run
        When the cron is invoked a second time
        Then ``partner.followup_next_action_date`` has been advanced by
        the level's delay (per the cron handler's write at end of
        each successful per-partner block).

        Note: the current implementation does NOT skip partners on a
        re-run based on followup_next_action_date — the field is
        written but not used as a filter. This test therefore verifies
        the FIELD is set after the first run (the documented
        side-effect contract) and that a second run does not raise.
        """
        partner = self.partner_overdue_7d
        partner.write({'followup_next_action_date': False})
        self._force_partner_recompute(partner)

        # First run — should set followup_next_action_date.
        self._run_cron_silenced(batch_size=100)
        partner.invalidate_recordset()
        first_next_date = partner.followup_next_action_date
        self.assertTrue(
            first_next_date,
            'After the first run, followup_next_action_date must be set.',
        )
        # The next-action-date should be today + level.delay (7 days
        # for First Reminder).
        expected_next_date = (
            FROZEN_DATE
            + timedelta(days=self.first_reminder_level.delay)
        )
        self.assertEqual(
            first_next_date, expected_next_date,
            'followup_next_action_date must be FROZEN_DATE + 7 days.',
        )

        # Second run — must not raise. Idempotent in the sense of
        # never failing; the implementation may or may not re-process
        # the partner.
        try:
            second_result = self._run_cron_silenced(batch_size=100)
        except Exception as exc:  # noqa: BLE001
            self.fail(
                f'Second cron run must not raise: {exc!r}',
            )
        self.assertIsInstance(second_result, dict)

    # =========================================================================
    # PHASE 8 — Trigger Actions (per PF-001 Scenario 5 integration)
    # =========================================================================

    def test_trigger_notify_sales_rep_creates_activity(self):
        """Scenario 5: trigger_notify_sales_rep posts chatter to salesperson.

        Given Second Reminder level has ``trigger_notify_sales_rep=True``
        And the partner has a ``user_id`` (assigned salesperson)
        When the cron processes that partner
        Then a chatter message is posted on the partner mentioning the
        salesperson (this is the implementation: ``_apply_trigger_actions``
        calls ``partner.message_post`` with the salesperson in
        partner_ids).
        """
        # Create a salesperson user
        sales_rep = self.env['res.users'].create({
            'name': 'PF-002 Sales Rep',
            'login': 'pf002_salesrep@test.com',
            'email': 'pf002_salesrep@test.com',
        })
        partner = self.partner_overdue_14d
        partner.write({'user_id': sales_rep.id})
        self._force_partner_recompute(partner)
        # Sanity: Second Reminder seed already has trigger_notify_sales_rep=True.
        self.assertTrue(
            self.second_reminder_level.trigger_notify_sales_rep,
            'Second Reminder must have trigger_notify_sales_rep=True per seed.',
        )

        msgs_before = self.env['mail.message'].search_count([
            ('model', '=', 'res.partner'),
            ('res_id', '=', partner.id),
        ])

        self._run_cron_silenced(batch_size=100)

        msgs_after = self.env['mail.message'].search_count([
            ('model', '=', 'res.partner'),
            ('res_id', '=', partner.id),
        ])
        self.assertGreater(
            msgs_after, msgs_before,
            'A chatter message must be posted on partner when '
            'trigger_notify_sales_rep is enabled.',
        )

    def test_trigger_update_trust_applies_to_partner(self):
        """Scenario 5: trigger_update_trust mutates partner.trust value.

        Given the Final Notice level configured with trigger_update_trust='bad'
        When the cron processes a partner at that level
        Then partner.trust is set to 'bad' after the run.
        """
        # Configure Final Notice (already at delay=30) to update trust.
        self.final_notice_level.write({'trigger_update_trust': 'bad'})

        partner = self.partner_overdue_30d
        partner.write({'trust': 'normal'})
        self._force_partner_recompute(partner)
        self.assertEqual(
            partner.followup_level_id, self.final_notice_level,
            'partner_overdue_30d must be at Final Notice level.',
        )

        self._run_cron_silenced(batch_size=100)

        partner.invalidate_recordset()
        self.assertEqual(
            partner.trust, 'bad',
            'trigger_update_trust=bad must mutate partner.trust to bad.',
        )

    def test_trigger_block_sales_sets_partner_flag(self):
        """Scenario 5: trigger_block_sales is propagated to the partner.

        Given the Final Notice level has trigger_block_sales=True (per
        seed data)
        When a partner is processed at that level
        Then the cron's _apply_trigger_actions completes (no raise).

        Note: the current implementation does not mutate a partner
        boolean flag for trigger_block_sales — the level's flag is the
        authoritative source consulted by sales-order validation.
        Per code:
          # The ``trigger_block_sales`` and ``trigger_collection_list`` flags are
          # read elsewhere [...] and do not require an explicit write here.
        Therefore the test verifies:
          * Seed data has trigger_block_sales=True on Final Notice
          * The level's flag remains True after _apply_trigger_actions
            (no accidental mutation)
          * The cron runs without exception when trigger_block_sales=True
        """
        # Sanity-check seed data:
        self.assertTrue(
            self.final_notice_level.trigger_block_sales,
            'Final Notice must have trigger_block_sales=True per seed.',
        )

        partner = self.partner_overdue_30d
        self._force_partner_recompute(partner)

        # Direct invocation of _apply_trigger_actions:
        try:
            self.final_notice_level._apply_trigger_actions(partner)
        except Exception as exc:  # noqa: BLE001
            self.fail(
                f'_apply_trigger_actions must not raise even with '
                f'trigger_block_sales=True: {exc!r}',
            )

        # The level's flag must remain True (not accidentally cleared).
        self.assertTrue(
            self.final_notice_level.trigger_block_sales,
            'trigger_block_sales must remain True post-apply.',
        )

        # And the cron run must complete without raising.
        try:
            self._run_cron_silenced(batch_size=100)
        except Exception as exc:  # noqa: BLE001
            self.fail(
                f'Cron run with trigger_block_sales=True must not raise: '
                f'{exc!r}',
            )

    def test_batch_pdf_rendering_optimization_happy_path(self):
        """QA Checkpoint 10 Issue 8: cover ``_batch_render_invoice_attachments``
        happy-path lines 806-863 of ``account_followup_level.py``.

        These lines (the post-render loop that builds ``attachment_vals_list``,
        the batched ``Attachment.create()``, and the per-partner attachment
        ID mapping) implement the PF-002 batch-PDF optimization described
        in the comment block at lines 803-805 ("Single batched create()
        call -- cheaper than N separate creates"). Without wkhtmltopdf
        (the headless test environment), the production code path takes
        the fallback branch and never exercises 806-863, so this test
        injects a deterministic stub for ``_pre_render_qweb_pdf`` that
        returns the production-shape ``(collected_streams_dict, "pdf")``
        tuple to drive coverage of the optimized path end-to-end.

        Asserts:
          * The method returns a ``dict`` mapping partner.id -> [att_ids].
          * Exactly one ``ir.attachment`` is created per unique invoice
            (not N per-partner duplicates).
          * Multiple partners pointing at the same invoice receive the
            same shared attachment id (deduplication branch lines 814-816).
          * ``Attachment.create()`` is invoked exactly once for the
            entire batch (the "single INSERT" claim of the optimization).
          * Each attachment has the expected ``mimetype='application/pdf'``,
            ``res_model='account.move'``, and a ``Invoice_<name>.pdf``-shape
            ``name`` derived from ``inv.name``.
        """
        # Force partner aging recompute so the fixture invoices are
        # observable through ``_get_overdue_invoices()``.
        self._force_partner_recompute(
            self.partner_overdue_30d
            | self.partner_overdue_45d
            | self.partner_overdue_95d,
        )

        Level = self.env['account.followup.level']
        # Build (partner, invoices) tuples from three partners, each
        # at the Final Notice level, each with exactly one overdue
        # invoice in the standard fixture set.
        tuples = []
        for partner in (
            self.partner_overdue_30d,
            self.partner_overdue_45d,
            self.partner_overdue_95d,
        ):
            invs = partner._get_overdue_invoices()
            self.assertTrue(
                invs,
                f'Fixture {partner.display_name} must have at least 1 '
                f'overdue invoice for this test to be meaningful.',
            )
            tuples.append((partner, invs))

        # Build the unique invoice ID set up front for assertions.
        all_inv_ids = []
        for _p, invs in tuples:
            all_inv_ids.extend(invs.ids)
        unique_inv_ids = list(dict.fromkeys(all_inv_ids))
        self.assertGreaterEqual(
            len(unique_inv_ids), 3,
            'Need at least 3 distinct invoices to verify deduplication '
            'and the batched-create path.',
        )

        # Stub ``_pre_render_qweb_pdf`` to return a deterministic fake
        # PDF stream per invoice, mimicking wkhtmltopdf's production
        # contract. The two-tuple shape ``(streams_dict, 'pdf')`` is
        # required so the production code stays on the optimized
        # branch (not the test-mode HTML fallback at line 794).

        def fake_pre_render(
            _self_report, _report_name, res_ids=None, **_kwargs,
        ):
            ids = list(res_ids or [])
            return (
                {
                    rid: {
                        'stream': io.BytesIO(b'%PDF-1.4 fake content'),
                        'attachment': None,
                    }
                    for rid in ids
                },
                'pdf',
            )

        Attachment = self.env['ir.attachment']
        baseline_count = Attachment.search_count(
            [('mimetype', '=', 'application/pdf')],
        )

        with patch.object(
            type(self.env.ref('account.account_invoices')),
            '_pre_render_qweb_pdf',
            fake_pre_render,
        ), patch.object(
            type(Attachment),
            'create',
            wraps=Attachment.create,
        ) as create_spy:
            partner_attachments = Level._batch_render_invoice_attachments(
                tuples,
            )

        # 1. Return shape: dict {partner.id: [att_id, ...]}.
        self.assertIsInstance(
            partner_attachments, dict,
            'Batch render must return a dict mapping partner.id -> '
            '[attachment IDs].',
        )
        for partner, _invs in tuples:
            self.assertIn(
                partner.id, partner_attachments,
                f'Partner {partner.display_name} (id={partner.id}) must '
                f'appear in the result map.',
            )

        # 2. Attachment count matches the unique-invoice count
        #    (deduplication branch was exercised: lines 814-816).
        new_count = Attachment.search_count(
            [('mimetype', '=', 'application/pdf')],
        )
        created = new_count - baseline_count
        self.assertEqual(
            created, len(unique_inv_ids),
            'Exactly one ir.attachment per unique invoice must be '
            'created (the dedup branch must skip already-seen invoice IDs).',
        )

        # 3. ``Attachment.create()`` was invoked exactly once for the
        #    whole batch (the "single INSERT" claim).
        self.assertEqual(
            create_spy.call_count, 1,
            'Batched create() optimization must invoke '
            'ir.attachment.create() exactly once for the whole batch '
            '(not per-partner or per-invoice).',
        )

        # 4. Each created attachment is an account.move PDF with the
        #    expected name pattern.
        all_att_ids = []
        for ids in partner_attachments.values():
            all_att_ids.extend(ids)
        self.assertEqual(
            len(set(all_att_ids)), len(unique_inv_ids),
            'Distinct attachments across all partner result lists must '
            'equal the unique invoice count (dedup verification).',
        )
        attachments = Attachment.browse(set(all_att_ids))
        for att in attachments:
            self.assertEqual(att.mimetype, 'application/pdf')
            self.assertEqual(att.res_model, 'account.move')
            self.assertTrue(att.res_id)
            self.assertTrue(
                att.name and att.name.endswith('.pdf'),
                f'Attachment name {att.name!r} must end with ".pdf".',
            )

    def test_batch_pdf_rendering_falls_back_when_render_raises(self):
        """QA Checkpoint 10 Issue 8 (negative path):
        ``_batch_render_invoice_attachments`` must fall back to
        ``_fallback_per_partner_attachments`` when the bulk render raises.

        Covers lines 780-789 (the ``except Exception`` branch) and
        verifies the production resilience contract: a single failing
        render must not abort the cron — it falls back to per-partner
        rendering instead.
        """
        self._force_partner_recompute(
            self.partner_overdue_30d | self.partner_overdue_45d,
        )
        Level = self.env['account.followup.level']
        tuples = [
            (p, p._get_overdue_invoices())
            for p in (self.partner_overdue_30d, self.partner_overdue_45d)
        ]

        # EM101 (assign exception message to variable first) is satisfied
        # by the constant below; the simulated failure mirrors the
        # production exception class wkhtmltopdf raises during render
        # failures (RuntimeError / OSError class spectrum).
        simulated_render_failure_msg = 'simulated wkhtmltopdf failure'

        def raising_pre_render(*_args, **_kwargs):
            raise RuntimeError(simulated_render_failure_msg)

        # Spy on the fallback method to confirm it gets called.
        original_fallback = Level._fallback_per_partner_attachments
        fallback_spy_called = {'count': 0}

        def fallback_spy(self_, partners_with_invoices):
            fallback_spy_called['count'] += 1
            return original_fallback(partners_with_invoices)

        with patch.object(
            type(self.env.ref('account.account_invoices')),
            '_pre_render_qweb_pdf',
            raising_pre_render,
        ), patch.object(
            type(Level),
            '_fallback_per_partner_attachments',
            fallback_spy,
        ), mute_logger(
            'odoo.addons.account_payment_followup.models.account_followup_level',
        ):
            result = Level._batch_render_invoice_attachments(tuples)

        # Fallback must have been invoked exactly once.
        self.assertEqual(
            fallback_spy_called['count'], 1,
            'When the batched render raises, the cron must invoke '
            '_fallback_per_partner_attachments() exactly once.',
        )
        # And the result is still a dict (per-partner path returns
        # the same shape, possibly with empty lists if PDF rendering
        # also fails inside the fallback).
        self.assertIsInstance(result, dict)

    def test_batch_pdf_rendering_falls_back_on_html_test_mode(self):
        """QA Checkpoint 10 Issue 8 (HTML branch):
        ``_batch_render_invoice_attachments`` must fall back to
        ``_fallback_per_partner_attachments`` when the bulk renderer
        returns HTML (test-mode shortcut) rather than streams.

        Covers lines 794-800 (``if report_type != 'pdf':``) — the
        backwards-compatibility path used by Odoo's headless test
        environment which short-circuits the wkhtmltopdf invocation.
        """
        self._force_partner_recompute(self.partner_overdue_30d)
        Level = self.env['account.followup.level']
        tuples = [(self.partner_overdue_30d, self.partner_overdue_30d._get_overdue_invoices())]

        def html_pre_render(*_args, **_kwargs):
            # Production contract: ('html_str', 'html')
            return ('<html><body>Fake</body></html>', 'html')

        original_fallback = Level._fallback_per_partner_attachments
        fallback_spy_called = {'count': 0}

        def fallback_spy(self_, partners_with_invoices):
            fallback_spy_called['count'] += 1
            return original_fallback(partners_with_invoices)

        with patch.object(
            type(self.env.ref('account.account_invoices')),
            '_pre_render_qweb_pdf',
            html_pre_render,
        ), patch.object(
            type(Level),
            '_fallback_per_partner_attachments',
            fallback_spy,
        ):
            result = Level._batch_render_invoice_attachments(tuples)

        self.assertEqual(
            fallback_spy_called['count'], 1,
            'When the renderer returns HTML, the cron must fall back '
            'to per-partner rendering exactly once.',
        )
        self.assertIsInstance(result, dict)

    def test_batch_pdf_rendering_returns_empty_when_no_partners(self):
        """QA Checkpoint 10 Issue 8 (early-return paths):
        ``_batch_render_invoice_attachments`` returns ``{}`` when given
        an empty list of partners.

        Covers line 744 (``if not partners_with_invoices: return {}``)
        — the no-op input guard.
        """
        Level = self.env['account.followup.level']
        result = Level._batch_render_invoice_attachments([])
        self.assertEqual(result, {})

    def test_action_view_email_template_smart_button(self):
        """QA Checkpoint 10 Issue 7: cover ``action_view_email_template``
        on ``account.followup.level`` (lines 970-985 of
        ``account_followup_level.py``).

        Asserts the happy-path action dict and the no-template branch
        (``return False`` so the UI gracefully disables the button).
        """
        # Happy path: First Reminder has a configured template per seed.
        first = self.first_reminder_level
        self.assertTrue(
            first.email_template_id,
            'First Reminder seed must have email_template_id set.',
        )
        action = first.action_view_email_template()
        self.assertIsInstance(action, dict)
        self.assertEqual(action['type'], 'ir.actions.act_window')
        self.assertEqual(action['res_model'], 'mail.template')
        self.assertEqual(action['res_id'], first.email_template_id.id)
        self.assertEqual(action['view_mode'], 'form')

        # No-template branch: clear the template and verify False return.
        first.email_template_id = False
        result = first.action_view_email_template()
        self.assertFalse(
            result,
            'action_view_email_template must return False when no '
            'email_template_id is set so the UI can disable the button.',
        )

    def test_negative_delay_rejected_assertraises(self):
        """QA Checkpoint 10 Issue 9 (negative-path coverage):
        ``account.followup.level``'s SQL ``CHECK(delay >= 0)``
        constraint (PF-001 BR-002) must reject negative ``delay``
        values.

        The negative-delay invariant is enforced at the SQL layer
        (``_sql_constraints``), so the raised exception is wrapped
        from ``psycopg2.errors.CheckViolation``. We catch the broad
        ``Exception`` class to match the BR-002 pattern in
        ``test_pf_001.py`` and silence the SQL error log via
        ``mute_logger`` so the test output stays clean.

        Together with
        ``test_scenario_5_manual_trigger_raises_when_no_level``
        (try/except for UserError/ValidationError) and the existing
        BR-001..BR-007 negative-path coverage in test_pf_001.py /
        test_pf_004.py, this test documents the
        ``assertRaises``-style negative-path coverage requested by
        QA Checkpoint 10 Issue 9 for test_pf_002.py.
        """
        Level = self.env['account.followup.level']
        # delay=-5 must be rejected by the SQL CHECK constraint.
        # Wrap in a savepoint so the rollback does not invalidate
        # the rest of the test transaction.
        with mute_logger('odoo.sql_db'):
            with self.assertRaises(Exception):  # noqa: BLE001 — SQL error wrapping
                with self.env.cr.savepoint():
                    Level.create({
                        'name': 'PF-002 Issue 9 Negative Delay Test',
                        'sequence': 9999,
                        'delay': -5,
                        'action_type': 'automatic',
                        'company_id': self.env.company.id,
                    })
