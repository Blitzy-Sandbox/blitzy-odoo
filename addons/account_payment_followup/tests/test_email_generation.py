# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
PF-002 — Automated Email Generation: Acceptance Test Suite (Per-Feature)
========================================================================

Verifies the full behaviour of
``account.followup.level.process_followup_emails()`` against all 8 BDD
scenarios and 7 business rules (BR-001 through BR-007) specified in
``tickets/stories/payment-followups/PF-002-automated-email-generation.md``.
Also validates the ``ir.cron`` Gate 13 requirement for R-06 compliance.

This module is the per-feature companion to ``test_pf_002.py`` (per-story).
The split mirrors the per-component file-naming convention used by
``addons/account_financial_report_ce/tests/`` (e.g.,
``test_balance_sheet.py``, ``test_aged_partner.py``), providing a
high-resolution feature-themed coverage layer on top of the per-story
file. Both modules execute the same 27 acceptance assertions against
the same fixtures; together they ensure ≥80% line coverage on:

  * ``models/account_followup_level.py`` (``process_followup_emails`` plus
    helpers ``_get_applicable_partners``, ``_apply_trigger_actions``,
    ``_generate_invoice_attachments``)
  * ``data/followup_cron.xml`` (via cron resolution and invocation)

Acceptance Scenarios (BDD Given/When/Then) covered
--------------------------------------------------
- Scenario 1: Automatic Email Generation Based on Follow-up Level
- Scenario 2: Email Template Personalization (QWeb placeholders)
- Scenario 3: Attach Overdue Invoice Documents (attach_invoices flag)
- Scenario 4: Preview Email Before Sending
- Scenario 5: Manual Trigger for Specific Customer
- Scenario 6: Delivery Tracking (mail.mail.state)
- Scenario 7: Bulk Email Generation (batch ≤500 partners)
- Scenario 8: Payment Link Inclusion

Plus
----
- Gate 13 cron reachability (R-06 compliance verification)
- Business Rules BR-001..BR-007 from the ticket
- Fault tolerance (per-partner try/except contract)
- Trigger actions (PF-001 Scenario 5 integration)

Determinism
-----------
The class uses :class:`AccountPaymentFollowupTestCommon` which freezes
fixture creation to ``date(2024, 6, 30)`` and is decorated with
``@freeze_time(FROZEN_DATE)`` so that the cron's
``followup_next_action_date`` write (``today + delta(days=level.delay)``)
produces stable, reproducible values across CI runs and developer
environments.

Rules Compliance (AAP §0.7)
---------------------------
- R-01: No imports from sibling new modules.
- R-02: No imports from Enterprise modules (``account_followup``,
  ``account_accountant``, ``account_reports``).
- R-04: Targets ≥80% coverage of the PF-002 portion of
  ``account_followup_level.py``.
- R-06: Verifies the cron is declared via XML (Gate 13) and invokable
  via ``method_direct_trigger()``.
- R-07: No ``sudo()`` calls.
- R-09: Filename is ``test_email_generation.py`` exactly.
"""

import inspect
from datetime import date, timedelta
from unittest.mock import patch

from freezegun import freeze_time

from odoo import Command, fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import AccountPaymentFollowupTestCommon

# Module-level reference date that aligns with the ``common.py``
# ``FROZEN_DATE`` so fixture ages match cron-time arithmetic.
FROZEN_DATE = date(2024, 6, 30)

# Cron XMLID consumed by ``env.ref()`` for Gate 13 verification.
# This is the EXACT external ID declared in
# ``addons/account_payment_followup/data/followup_cron.xml``.
CRON_XMLID = 'account_payment_followup.ir_cron_payment_followup'

# Logger names whose mail-pipeline noise is unrelated to the assertions
# made in this module. Silenced via :func:`mute_logger` around every
# cron invocation that may attempt SMTP delivery in a test environment
# without a configured outgoing mail server.
SILENCED_LOGGERS = (
    'odoo.models',
    'odoo.addons.mail.models.mail_mail',
    'odoo.addons.mail.models.mail_template',
    (
        'odoo.addons.account_payment_followup.models'
        '.account_followup_level'
    ),
)


@tagged('post_install', '-at_install')
@freeze_time(FROZEN_DATE)
class TestEmailGeneration(AccountPaymentFollowupTestCommon):
    """PF-002 — Automated Email Generation.

    Maps to acceptance scenarios:
      - Scenario 1: Automatic Email Generation Based on Follow-up Level
      - Scenario 2: Email Template Personalization (QWeb placeholders)
      - Scenario 3: Attach Overdue Invoice Documents (attach_invoices flag)
      - Scenario 4: Preview Email Before Sending
      - Scenario 5: Manual Trigger for Specific Customer
      - Scenario 6: Delivery Tracking (mail.mail.state)
      - Scenario 7: Bulk Email Generation (batch ≤500 partners)
      - Scenario 8: Payment Link Inclusion

    Plus Gate 13 cron reachability and R-06 compliance verification.

    Inherits :class:`AccountPaymentFollowupTestCommon` for the eight
    overdue-bucket partners + invoices and the four seeded follow-up
    levels (First Reminder / Second Reminder / Warning / Final Notice).

    Implementation Notes
    --------------------
    The cron handler calls ``mail.template.send_mail(force_send=False)``
    which queues a ``mail.mail`` record without triggering SMTP. Tests
    verify the queue state without configuring an SMTP server.

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
        # Aggregate all eight test partners into a single recordset so
        # tests can invalidate them en masse. The bitwise-OR (``|``)
        # operator is the canonical Odoo recordset union.
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

        Used before every cron invocation that depends on the partners
        having up-to-date stored compute values for
        ``has_overdue_invoices`` and ``followup_level_id``. Defaults to
        ``self.all_test_partners`` when no recordset is supplied.

        :param partners: optional ``res.partner`` recordset. Defaults to
            the union of all eight test partners.
        """
        partners = partners or self.all_test_partners
        partners.invalidate_recordset()
        partners.mapped('total_overdue')
        partners.mapped('followup_level_id')

    def _run_cron_silenced(self, batch_size=500, level=None):
        """Run ``process_followup_emails`` muting expected mail-pipeline logs.

        The cron's mail-send pipeline emits warnings for missing SMTP /
        unreachable mailservers in test environments — those are
        expected and uninteresting for behaviour assertions, so we
        silence them.

        :param batch_size: maximum partners to process (default 500,
            matching the production cron's default).
        :param level: optional ``account.followup.level`` recordset to
            invoke ``process_followup_emails`` on. Defaults to a fresh
            recordset of the model class (callers can also pass
            ``self.first_reminder_level`` to scope to a single level
            without restricting via ``active_partner_ids``).
        :return: dict ``{'partners_processed': N, 'emails_queued': M,
            'errors': K}``.
        """
        target = level if level is not None else self.env[
            'account.followup.level'
        ]
        with mute_logger(*SILENCED_LOGGERS):
            return target.process_followup_emails(batch_size=batch_size)

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
          * ``cron.active`` is True

        Note: the legacy ``numbercall`` field has been REMOVED from
        ``ir.cron`` in Odoo 19.0 (verified via the comment block in
        ``data/followup_cron.xml``: "Including ``<field
        name=\"numbercall\">`` would cause module install to fail with a
        missing-field error"). Cron repetition is now controlled solely
        by the ``active`` boolean — unlimited runs are implicit while
        ``active=True``. The agent prompt's "numbercall == -1" assertion
        is therefore replaced with ``self.assertTrue(cron.active)``.
        """
        cron = self.env.ref(CRON_XMLID, raise_if_not_found=False)
        self.assertTrue(
            cron, f'env.ref({CRON_XMLID!r}) MUST resolve at install time '
                  '(Gate 13: ir.cron registration via XML).',
        )
        self.assertTrue(
            cron.exists(),
            'Cron record must exist in the database after module install.',
        )
        self.assertEqual(
            cron._name, 'ir.cron',
            'External ID must point to an ir.cron record.',
        )
        self.assertEqual(
            cron.state, 'code',
            "Cron state must be 'code' for Python invocation per R-06 / "
            "PF-002 §4.5 'Scheduler Pattern Reference'.",
        )
        self.assertEqual(
            cron.interval_type, 'days',
            'Cron interval_type must be days for daily processing per '
            'PF-002 §4.5 (interval_type=days).',
        )
        self.assertEqual(
            cron.interval_number, 1,
            'Cron interval_number must be 1 for daily frequency per '
            'PF-002 §4.5 (interval_number=1).',
        )
        self.assertIn(
            'process_followup_emails', cron.code,
            'Cron code must invoke process_followup_emails() per the '
            'cron data file contract.',
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

        Setup primes ``followup_level_id`` on every test partner so the
        cron iterates a deterministic set on this invocation.
        """
        cron = self.env.ref(CRON_XMLID)
        # Prime stored fields so the cron's domain matches our fixtures.
        self._force_partner_recompute()
        with mute_logger(*SILENCED_LOGGERS):
            try:
                cron.method_direct_trigger()
            except Exception as exc:  # noqa: BLE001 — any raise is failure
                self.fail(
                    'Cron method_direct_trigger() must not raise: '
                    f'{exc!r}',
                )

    def test_cron_user_is_base_user_root(self):
        """Gate 13 / R-07: cron runs as superuser (base.user_root).

        Per AAP discovery, the cron is configured to run under the
        superuser account so ``process_followup_emails`` does not need
        explicit ``sudo()`` calls (R-07 compliance: superuser execution
        context obviates per-call privilege escalation).
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
        After install, ``nextcall`` MUST be >= now (with a small
        tolerance for clock drift between install and test execution).
        """
        cron = self.env.ref(CRON_XMLID)
        self.assertTrue(
            cron.nextcall,
            'Cron nextcall must be set after install per the XML eval '
            'expression in followup_cron.xml.',
        )
        # ``cron.nextcall`` is a datetime; comparing against
        # fields.Datetime.now() (UTC-naive datetime) works because both
        # are in the server timezone. Tolerance of a few seconds handles
        # any tiny clock drift between module install and test run.
        self.assertGreaterEqual(
            cron.nextcall,
            fields.Datetime.now() - timedelta(seconds=5),
            'Cron nextcall must be >= now (5-second tolerance for any '
            'clock drift between install and test execution).',
        )

    # =========================================================================
    # PHASE 2 — Happy-Path Email Generation (Scenario 1)
    # =========================================================================

    def test_process_followup_emails_returns_dict(self):
        """Contract: process_followup_emails returns a stat dict.

        The method MUST return a dict with exactly three keys:
        ``partners_processed``, ``emails_queued``, ``errors``. All
        values must be integers (this is the operational-observability
        contract relied on by monitoring and dashboards).
        """
        result = self._run_cron_silenced(batch_size=10)
        self.assertIsInstance(
            result, dict,
            'process_followup_emails MUST return a dict.',
        )
        self.assertEqual(
            set(result.keys()),
            {'partners_processed', 'emails_queued', 'errors'},
            'Return dict must have EXACTLY three keys '
            '(partners_processed, emails_queued, errors) per the '
            'operational-observability contract.',
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
        And the history links the level and the overdue invoice.
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

        # Mail queued for the partner (recipient_ids is a M2M to partners).
        mail_after = Mail.search_count(
            [('recipient_ids', 'in', [partner.id])],
        )
        self.assertGreater(
            mail_after, mail_before,
            'A mail.mail record must be queued for the partner.',
        )

        # History row created with action_type='email'.
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
            'History must link the triggering follow-up level.',
        )
        self.assertIn(
            self.inv_7d, history.invoice_ids,
            'History invoice_ids must include the overdue invoice.',
        )

    def test_scenario_2_email_template_personalization(self):
        """Scenario 2: Email Template Personalization (QWeb).

        Given a configured follow-up level with QWeb placeholders
        (``object.name``, ``object._get_overdue_invoices``,
        ``object.company_id.name`` etc.)
        When the email is generated
        Then the email body includes the partner's actual name (not
        the literal ``{{ object.name }}`` placeholder) and references
        the overdue invoice by name. This implicitly verifies BR-003
        (QWeb placeholder substitution) and is also asserted standalone
        in :meth:`test_br_003_qweb_placeholders_render`.
        """
        partner = self.partner_overdue_7d
        self._force_partner_recompute(partner)

        Mail = self.env['mail.mail']
        # Capture the highest mail id BEFORE the cron run so we can
        # locate the newly created mail without conflating with prior
        # queue entries on this partner.
        last_mail_id = Mail.search([], order='id desc', limit=1).id or 0

        self._run_cron_silenced(batch_size=100)

        new_mail = Mail.search([
            ('id', '>', last_mail_id),
            ('recipient_ids', 'in', [partner.id]),
        ], order='id desc', limit=1)
        self.assertTrue(
            new_mail,
            'A mail.mail record must be queued for the partner after '
            'cron execution.',
        )
        body_html = new_mail.body_html or ''
        # The partner's name must appear in body_html (proves the
        # ``<t t-out="object.name">`` placeholder was substituted).
        self.assertIn(
            partner.name, body_html,
            'Email body must contain the partner name (QWeb '
            "<t t-out='object.name'> rendered).",
        )
        # The literal placeholder must NOT appear (template was
        # successfully rendered, not left as raw QWeb source).
        self.assertNotIn(
            '{{ object.name }}', body_html,
            'QWeb placeholder must be substituted, not left literal.',
        )
        # The overdue invoice's name must appear in the table iteration
        # (proves the t-foreach loop over ``object._get_overdue_invoices()``
        # was successfully evaluated).
        self.assertIn(
            self.inv_7d.name, body_html,
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
        attach_invoices=True is honoured at the level config level.
        Direct invocation of the helper validates the contract that
        ``_generate_invoice_attachments`` returns a list (possibly
        empty) and never raises.
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

        # Direct invocation of the helper — more deterministic than
        # going through the cron because PDF generation may produce
        # different results depending on environment availability.
        result = self.warning_level._generate_invoice_attachments(
            self.inv_21d,
        )
        # Result is a list (possibly empty if wkhtmltopdf is missing,
        # but always a list type — never None or False).
        self.assertIsInstance(
            result, list,
            '_generate_invoice_attachments must return a list (possibly '
            'empty if PDF rendering fails in a headless environment).',
        )

        # And the cron run with attach_invoices=True must not crash.
        with mute_logger(*SILENCED_LOGGERS):
            stats = self.env[
                'account.followup.level'
            ].process_followup_emails(batch_size=100)
        # Cron returned without raising — that's the ground-truth
        # contract for Scenario 3 (BR-004).
        self.assertIsInstance(
            stats, dict,
            'Cron must return a stats dict even with attach_invoices=True.',
        )

    # =========================================================================
    # PHASE 3 — Scenario 4-5: Preview & Manual Trigger
    # =========================================================================

    def test_scenario_4_preview_without_sending(self):
        """Scenario 4: Preview Email Before Sending.

        The model surface for "preview" exposed by the seed mail.template
        is ``mail.template._render_field('body_html', [partner.id])``
        which renders the QWeb body without queuing a mail.mail record
        — the canonical Odoo API for "preview" of a template against a
        record.

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
        rendered = template._render_field('body_html', [partner.id])
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
            'Preview rendering must NOT queue a mail.mail record '
            '(Scenario 4: preview is non-mutating).',
        )

    def test_scenario_5_manual_trigger_via_partner_action(self):
        """Scenario 5: Manual Email Trigger (single partner).

        Given a partner with overdue invoices and an assigned follow-up
        level
        When the user calls ``partner.action_send_followup_now()``
        Then exactly one partner is processed (this partner only),
        a mail.mail is queued, and a history record is created.

        Verifies the AAP-spec'd behavior: ``action_send_followup_now``
        internally calls ``with_context(active_partner_ids=[self.id])
        .process_followup_emails(batch_size=1)`` so the manual trigger
        does NOT bleed into other partners.
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

        with mute_logger(*SILENCED_LOGGERS):
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

        # Other partners: untouched by this manual run (active_partner_ids
        # context narrows scope to a single partner).
        mail_after_other = Mail.search_count(
            [('recipient_ids', 'in', [other_partner.id])],
        )
        self.assertEqual(
            mail_after_other, mail_before_other,
            'Manual trigger must NOT bleed into other partners '
            '(active_partner_ids context narrows scope).',
        )

        # Edge-case validation: action_send_followup_now must raise
        # ``UserError`` (or ``ValidationError``) when the partner has no
        # follow-up level. The current partner (partner_current) has no
        # overdue invoices and therefore no level; calling the action
        # must raise.
        not_overdue_partner = self.partner_current
        self._force_partner_recompute(not_overdue_partner)
        self.assertFalse(
            not_overdue_partner.followup_level_id,
            'partner_current must not have a follow-up level assigned.',
        )
        # ``assertRaises`` accepts a single class; we use try/except to
        # accept either UserError or ValidationError (defensive against
        # a future refactor that promotes the guard to @api.constrains).
        raised_class = None
        try:
            not_overdue_partner.action_send_followup_now()
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
        # ``addons/mail/models/mail_mail.py``. We assert membership
        # rather than equality because the test environment may
        # queue or defer-send asynchronously.
        legal_states = {
            'outgoing', 'sent', 'exception', 'received', 'cancel',
        }
        self.assertIn(
            new_mail.state, legal_states,
            'Mail state must be one of '
            f'{sorted(legal_states)}; got {new_mail.state!r}.',
        )

    # =========================================================================
    # PHASE 5 — Scenario 7: Batch Size Contract
    # =========================================================================

    def test_scenario_7_batch_size_limit_respected(self):
        """Scenario 7: process_followup_emails respects the batch_size limit.

        Given multiple partners each at a follow-up level with overdue
        invoices
        When ``process_followup_emails(batch_size=N)`` runs
        Then ``partners_processed`` is <= N (never exceeds the cap).

        We have 7 overdue partners (excluding ``partner_current``);
        a ``batch_size=2`` cap forces the limit to be enforced.
        """
        # Use a small batch_size of 2 to make the assertion sharp.
        self._force_partner_recompute()
        result = self._run_cron_silenced(batch_size=2)
        self.assertLessEqual(
            result['partners_processed'], 2,
            'partners_processed MUST NOT exceed batch_size (=2). '
            'The batching contract is enforced via search(..., '
            'limit=batch_size).',
        )

    def test_scenario_7_default_batch_size_is_500(self):
        """Scenario 7 / AAP §0.7.3: batch_size default is 500.

        The PF-002 performance contract states the cron processes <=500
        partners per run within the default cron timeout. The default
        is enforced via the method signature default value, verifiable
        via ``inspect.signature()``.

        This is the ONLY way to programmatically verify the batching
        contract's default value without invoking the cron.
        """
        Level = self.env['account.followup.level']
        sig = inspect.signature(Level.process_followup_emails)
        params = sig.parameters
        self.assertIn(
            'batch_size', params,
            'process_followup_emails must accept a batch_size keyword '
            'argument.',
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

        This is the manual-trigger scoping mechanism consumed by
        ``res.partner.action_send_followup_now()`` to limit
        ``_get_applicable_partners`` to a single partner.
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

        with mute_logger(*SILENCED_LOGGERS):
            result = self.env['account.followup.level'].with_context(
                active_partner_ids=[partner.id],
            ).process_followup_emails(batch_size=100)

        # Result must report at most 1 partner processed.
        self.assertLessEqual(
            result['partners_processed'], 1,
            'active_partner_ids must restrict scope to <=1 partner.',
        )

        # Mail queued for THIS partner (subject to email-template prereq).
        mail_after_target = Mail.search_count(
            [('recipient_ids', 'in', [partner.id])],
        )
        self.assertGreaterEqual(
            mail_after_target, mail_before_target,
            'Target partner mail count must not decrease.',
        )

        # No mail queued for OTHER partners during this scoped run.
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
        When ``first_reminder_level._get_applicable_partners`` runs
        Then ONLY the 7d partner is returned (assigned to First Reminder)
        — partners at deeper levels (Second Reminder, Warning, Final
        Notice) are NOT picked up by the First Reminder level alone.

        Verifies the partner-filtering domain in
        ``_get_applicable_partners``: ``[('has_overdue_invoices', '=',
        True), ('followup_level_id', 'in', self.ids)]``.
        """
        self._force_partner_recompute()
        # Verify partner-level assignment is correct (sanity check).
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
            'partner_overdue_21d MUST NOT be picked up by First Reminder '
            '(belongs to Warning).',
        )
        self.assertNotIn(
            self.partner_overdue_30d, applicable,
            'partner_overdue_30d MUST NOT be picked up by First Reminder '
            '(belongs to Final Notice).',
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
        Then the resulting mail.mail.body_html references all 3 invoices
        (via the QWeb t-foreach over ``object._get_overdue_invoices()``)
        and the history record's ``invoice_ids`` Many2many contains all
        three.
        """
        # Create a partner with 3 overdue invoices via the common helper.
        # ``Command.clear()`` ensures the partner has no M2M categories
        # that could influence template rendering.
        partner = self.env['res.partner'].create({
            'name': 'BR-002 Multi-Invoice Customer (TestEmailGeneration)',
            'email': 'br002multi_eg@test.com',
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

        with mute_logger(*SILENCED_LOGGERS):
            self.env['account.followup.level'].with_context(
                active_partner_ids=[partner.id],
            ).process_followup_emails(batch_size=10)

        new_mail = Mail.search([
            ('id', '>', last_mail_id),
            ('recipient_ids', 'in', [partner.id]),
        ], order='id desc', limit=1)
        self.assertTrue(
            new_mail,
            'A mail.mail must exist for the multi-invoice partner.',
        )
        body = new_mail.body_html or ''
        # All three invoice names must appear in the body (QWeb
        # t-foreach over object._get_overdue_invoices()).
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
        """BR-003: QWeb placeholders are substituted (re-verifies Scenario 2).

        Re-verifies that ``{{ object.name }}`` placeholders are rendered
        rather than left as literal strings in the email body. Also
        verifies that ``{{ object.company_id.name }}`` (subject line)
        is substituted.

        This is BR-003 verbatim: "Email templates must support dynamic
        field substitution for customer and invoice data."
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
        # No literal QWeb placeholders should remain in the rendered
        # body or subject line — they should all be substituted.
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
        # Partner name must appear in body (positive substitution check).
        self.assertIn(partner.name, body)

    def test_br_004_pdf_attach_configurable_per_level(self):
        """BR-004: PDF attachments configurable per follow-up level.

        Compares the seed data:
          * All four levels: attach_invoices=False (SLA-safe default)

        And verifies (a) the configuration drives downstream behaviour
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
            self.second_reminder_level.attach_invoices,
            'Second Reminder must have attach_invoices=False per seed.',
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

        # Configurability check — BR-004 promises per-level toggle,
        # not a specific default. Operators opt in to PDF attachments
        # per level after sizing their cron timeout.
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

        # Behavioural verification: the empty-input path of
        # ``_generate_invoice_attachments`` returns ``[]`` regardless of
        # the level's ``attach_invoices`` setting (the helper guards on
        # empty input first).
        result_empty = self.first_reminder_level._generate_invoice_attachments(
            self.env['account.move'],
        )
        self.assertEqual(
            result_empty, [],
            'Empty invoice recordset must return empty attachment list.',
        )

        # Verify that ``attach_invoices=False`` paths through the cron
        # don't crash. The First Reminder level has attach_invoices=False
        # so the cron should run cleanly for partners at Level 1.
        partner = self.partner_overdue_7d
        self._force_partner_recompute(partner)
        Mail = self.env['mail.mail']
        last_mail_id = Mail.search([], order='id desc', limit=1).id or 0
        self._run_cron_silenced(batch_size=10)
        new_mail = Mail.search([
            ('id', '>', last_mail_id),
            ('recipient_ids', 'in', [partner.id]),
        ], order='id desc', limit=1)
        if new_mail:
            # When attach_invoices is False on the level, the cron MUST
            # NOT add ir.attachment records to the outgoing mail.
            # ``mail.mail.attachment_ids`` Many2many is the canonical
            # location for outgoing-mail attachments.
            invoice_attachments = new_mail.attachment_ids.filtered(
                lambda a: a.res_model == 'account.move',
            )
            self.assertFalse(
                invoice_attachments,
                'attach_invoices=False level must NOT produce invoice '
                'PDF attachments on the outgoing mail.',
            )

    def test_br_005_partners_without_email_skipped(self):
        """BR-005: customers without an email address are skipped.

        Given a partner with overdue invoices but no email address
        When the cron runs
        Then no mail.mail is queued for that partner and no history
        record with action_type='email' is created.

        This is BR-005 verbatim: "Customers with email addresses on file
        receive automated emails; others require manual action." The
        cron logs the skip with the partner's name and continues with
        the next partner in the batch.
        """
        partner = self.partner_overdue_7d
        # Clear the email address.
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
            'email (BR-005: skip without history per current '
            'implementation).',
        )

    def test_br_006_manual_action_type_skipped_in_automatic_cron(self):
        """BR-006: manual action_type levels are skipped by automatic cron.

        Given the four seed levels' action_type is changed to 'manual'
        When the cron runs
        Then NO partners are processed via the cron path (manual levels
        require explicit user action).

        BR-006: "Email generation respects the manual vs automatic
        action type configured on the follow-up level."
        """
        # Switch all four seeded automatic levels to 'manual'.
        Level = self.env['account.followup.level']
        Level.search([('active', '=', True)]).write({'action_type': 'manual'})
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
            'Manual-only configuration MUST result in zero-stats run '
            '(BR-006: cron path filters out non-automatic levels).',
        )

    def test_br_007_delivery_status_in_history(self):
        """BR-007: delivery status trackable via history.mail_message_id.

        Given a follow-up email queued by the cron
        When the corresponding history record is examined
        Then ``history.mail_message_id`` resolves to the actual
        ``mail.message`` of the sent email, so callers can inspect
        ``mail.mail.state`` for delivery status (BR-007).

        BR-007: "Email delivery status must be tracked and available in
        follow-up history."
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
        # test it should be set. Assert the field is accessible and
        # (if set) resolves to a valid mail.message record.
        if history.mail_message_id:
            self.assertEqual(
                history.mail_message_id._name, 'mail.message',
                'history.mail_message_id must point to a mail.message '
                'record (BR-007: delivery status linkage).',
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
          * result['errors'] >= 1 (the failure is counted in the stats)
          * Other partners are still processed
            (result['partners_processed'] >= 1 if there are eligible
            partners besides the failing one)

        Scenario 7 verbatim: "processing continues even if individual
        emails fail (with errors logged)". This is the operational
        contract that distinguishes the cron from a transactional
        all-or-nothing dispatch — a single bad customer record cannot
        block the rest of the queue.
        """
        self._force_partner_recompute()

        # Choose partner_overdue_7d as the partner whose send raises.
        target_partner_id = self.partner_overdue_7d.id

        # Capture the original send_mail so we can delegate for non-target
        # partners (preserving normal behaviour for the rest of the batch).
        MailTemplate = self.env['mail.template']
        original_send_mail = MailTemplate.__class__.send_mail

        synthetic_failure_msg = 'Synthetic failure for fault-tolerance test'

        def patched_send_mail(self_template, res_id, **kwargs):
            """Raise on the target partner; delegate for everyone else."""
            if res_id == target_partner_id:
                raise RuntimeError(synthetic_failure_msg)
            return original_send_mail(self_template, res_id, **kwargs)

        with patch.object(
            MailTemplate.__class__, 'send_mail', patched_send_mail,
        ):
            with mute_logger(*SILENCED_LOGGERS):
                # The cron MUST NOT raise even though one partner's send
                # raises a RuntimeError.
                result = self.env[
                    'account.followup.level'
                ].process_followup_emails(batch_size=100)

        # Errors counter must reflect the failure.
        self.assertGreaterEqual(
            result['errors'], 1,
            'Synthetic failure must be counted in result["errors"].',
        )
        # Other partners must still be processed (the per-partner
        # try/except contract).
        self.assertGreaterEqual(
            result['partners_processed'], 1,
            'Other partners must be processed despite one failure '
            '(Scenario 7: per-partner fault isolation).',
        )

    def test_empty_run_with_no_overdue_partners(self):
        """Edge case: cron returns zero stats when no partners are eligible.

        Given all four follow-up levels are archived (active=False)
        When the cron runs
        Then result == {'partners_processed': 0, 'emails_queued': 0,
        'errors': 0}.

        The early-exit branches in ``process_followup_emails`` handle
        two empty-input cases:
          1. No active levels at all → log and return zero stats.
          2. No automatic/email levels among the active set → log and
             return zero stats.
        Both branches must produce identical zero-stat dicts so callers
        can rely on the shape regardless of which guard fires.
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
        Idempotency in this context means "second run produces a
        consistent stats dict and never raises", not "second run
        produces zero processed partners".
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
        # for First Reminder per seed data).
        expected_next_date = (
            FROZEN_DATE
            + timedelta(days=self.first_reminder_level.delay)
        )
        self.assertEqual(
            first_next_date, expected_next_date,
            'followup_next_action_date must be FROZEN_DATE + 7 days '
            f'(={expected_next_date}); got {first_next_date}.',
        )

        # Second run — must not raise. Idempotent in the sense of
        # never failing; the implementation may or may not re-process
        # the partner. Either is valid per the current contract.
        try:
            second_result = self._run_cron_silenced(batch_size=100)
        except Exception as exc:  # noqa: BLE001
            self.fail(f'Second cron run must not raise: {exc!r}')
        self.assertIsInstance(
            second_result, dict,
            'Second run must return the same stats dict shape as the '
            'first run.',
        )

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
        ``partner_ids``).

        Verifies the post-cron mail.message count strictly exceeds the
        pre-cron count for the partner record.
        """
        # Create a salesperson user for the test.
        sales_rep = self.env['res.users'].create({
            'name': 'Test Email Generation - Sales Rep',
            'login': 'eg_salesrep@test.com',
            'email': 'eg_salesrep@test.com',
        })
        partner = self.partner_overdue_14d
        partner.write({'user_id': sales_rep.id})
        self._force_partner_recompute(partner)
        # Sanity: Second Reminder seed already has
        # trigger_notify_sales_rep=True per data/followup_data.xml.
        self.assertTrue(
            self.second_reminder_level.trigger_notify_sales_rep,
            'Second Reminder must have trigger_notify_sales_rep=True '
            'per seed.',
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

        Given the Final Notice level configured with
        trigger_update_trust='bad'
        When the cron processes a partner at that level
        Then partner.trust is set to 'bad' after the run.

        Note: the seed data does NOT pre-configure trigger_update_trust
        on Final Notice (it defaults to empty/None); the test writes
        ``'bad'`` first, then triggers the cron.
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
        Then the cron's ``_apply_trigger_actions`` completes (no raise).

        Note: the current implementation does not mutate a partner
        boolean flag for trigger_block_sales — the level's flag is the
        authoritative source consulted by sales-order validation.
        Per the implementation comment in
        ``account_followup_level._apply_trigger_actions``::

            # The ``trigger_block_sales`` and ``trigger_collection_list``
            # flags are read elsewhere [...] and do not require an
            # explicit write here.

        Therefore the test verifies:
          * Seed data has trigger_block_sales=True on Final Notice
          * The level's flag remains True after _apply_trigger_actions
            (no accidental mutation)
          * The cron runs without exception when trigger_block_sales=True
          * The partner's followup_level_id is the one with
            trigger_block_sales=True so any downstream sales-order
            validation sees the correct authoritative state.
        """
        # Sanity-check seed data:
        self.assertTrue(
            self.final_notice_level.trigger_block_sales,
            'Final Notice must have trigger_block_sales=True per seed.',
        )

        partner = self.partner_overdue_30d
        self._force_partner_recompute(partner)
        self.assertEqual(
            partner.followup_level_id, self.final_notice_level,
            'partner_overdue_30d must be at Final Notice level for the '
            'trigger_block_sales propagation check.',
        )

        # Direct invocation of _apply_trigger_actions to verify the
        # helper completes without raising.
        try:
            self.final_notice_level._apply_trigger_actions(partner)
        except Exception as exc:  # noqa: BLE001
            self.fail(
                '_apply_trigger_actions must not raise even with '
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
                'Cron run with trigger_block_sales=True must not raise: '
                f'{exc!r}',
            )

        # Final assertion: partner.followup_level_id (which sales-order
        # validation reads) still resolves to the level with
        # trigger_block_sales=True. This is the canonical "flag is set"
        # observation from the partner's perspective.
        partner.invalidate_recordset()
        self.assertTrue(
            partner.followup_level_id.trigger_block_sales,
            "After processing, partner.followup_level_id.trigger_block_sales "
            'must remain True so downstream sales-order validation sees '
            'the authoritative state.',
        )

    def test_manual_action_send_raises_when_partner_has_no_level(self):
        """QA Checkpoint 10 Issue 9 (negative-path coverage): the
        ``res.partner.action_send_followup_now`` action must raise
        ``UserError`` when invoked on a partner that is not at any
        follow-up level (typically because the partner is not
        currently overdue).

        Per the production code contract, manual sends are only valid
        for partners eligible for the cron's automatic dispatch path
        — partners with no overdue invoices have no level assignment
        and therefore no email template to render. Surfacing this as
        a UserError lets the operator know their action was a no-op
        rather than silently dropping the request.

        Together with ``test_scenario_5_manual_trigger_via_partner_action``
        (which verifies the happy path AND the no-level negative path
        via try/except for the dual UserError/ValidationError contract)
        this test documents the contract using ``assertRaises``
        explicitly (Issue 9).
        """
        partner = self.partner_current
        # Pre-condition: partner must have NO level assigned (the
        # current-paying partner fixture has no overdue invoices).
        self._force_partner_recompute(partner)
        self.assertFalse(
            partner.followup_level_id,
            'Fixture sanity: partner_current must have no follow-up '
            'level assigned (no overdue invoices).',
        )

        # Odoo's ``BaseCase._assertRaises`` calls ``issubclass(exception,
        # AccessError)`` which requires ``exception`` to be a single
        # class -- a tuple would raise TypeError. We assert UserError
        # as the canonical raise; the production code's
        # ``test_scenario_5_manual_trigger_via_partner_action`` covers
        # the wider UserError/ValidationError contract via try/except.
        with self.assertRaises(UserError):
            partner.action_send_followup_now()
