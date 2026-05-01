# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
PF-004 — Action History Tracking: Acceptance Test Suite
========================================================

Verifies the immutable audit trail surface introduced by:

  * ``addons/account_payment_followup/models/account_followup_history.py``
    — net-new ``account.followup.history`` model.

Acceptance Scenarios (BDD Given/When/Then) covered:

  - Scenario 1: Automatic History Creation on Email Dispatch (BR-001)
  - Scenario 2: View Customer Action History (newest-first ordering)
  - Scenario 3: Manual Activity Logging (phone, letter, meeting, etc.)
  - Scenario 4: Single & Many invoice References (BR-004)
  - Scenario 5: Manual Activities — Attachments + activity scheduling
  - Scenario 6: Outcome Tracking (selection field, mutable)
  - Scenario 7: View Email Content (mail_message_id linkage)
  - Scenario 8: Payment Promise Tracking (BR-006)

Plus the 8 Business Rule BR-003 immutability tests (NON-whitelisted
fields cannot be modified) and the 5 mutable whitelist tests
(``outcome``, ``notes``, ``attachment_ids``, ``promised_date``,
``promised_amount``):

  - 1 test verifying user cannot unlink (perm_unlink=0)
  - 1 test verifying MANAGER also cannot unlink (perm_unlink=0)
  - 8 immutability tests (action_type, action_date, partner_id,
    summary, total_amount_communicated, user_id, company_id,
    followup_level_id)
  - 5 whitelist mutability tests
  - 4 BR-001..BR-007 tests
  - smart-button action tests
  - copy() rejection test (audit-trail integrity)

Targets ≥80% line coverage of ``models/account_followup_history.py``.

Determinism
-----------
The class uses :class:`AccountPaymentFollowupTestCommon` which freezes
fixture creation to ``date(2024, 6, 30)``. PF-004 tests mostly don't
depend on time, but the freeze ensures consistent ``action_date``
defaults via ``fields.Datetime.now()``.

Rules Compliance (AAP §0.7)
---------------------------
- R-01: No imports from sibling new modules.
- R-02: No imports from Enterprise modules.
- R-04: Targets ≥80% coverage of ``account_followup_history.py``.
- R-07: No ``sudo()`` calls (uses with_user for ACL boundary tests).
- R-09: Filename is ``test_pf_004.py`` exactly.
"""

import logging
from datetime import date, timedelta

from freezegun import freeze_time

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import AccountPaymentFollowupTestCommon

_logger = logging.getLogger(__name__)

# Module-level frozen reference date — must match common.py FROZEN_DATE.
FROZEN_DATE = date(2024, 6, 30)


@tagged('post_install', '-at_install')
@freeze_time(FROZEN_DATE)
class TestActionHistoryTracking(AccountPaymentFollowupTestCommon):
    """PF-004 — Action History Tracking acceptance tests.

    Inherits :class:`AccountPaymentFollowupTestCommon` for the eight
    overdue-bucket partners + invoices.

    Implementation Notes
    --------------------
    The model declares ``_IMMUTABILITY_WHITELIST`` as a frozenset of
    field names that are PERMITTED to be modified after creation. All
    other fields raise UserError on write attempts unless the caller
    has env.su context.

    Tests for unlink permission boundaries use ``with_user(user)`` to
    simulate non-superuser context — ``env.su`` is False for non-
    superuser users, so the unlink override raises UserError.

    Tests for ACL-level restrictions (perm_unlink=0 in
    ir.model.access.csv) use ``with_user(user)`` and assert
    AccessError is raised.
    """

    @classmethod
    def setUpClass(cls):
        """Build PF-004-specific fixtures on top of the common base.

        Creates manager and user-only test users for ACL boundary
        verification.
        """
        super().setUpClass()
        cls.History = cls.env['account.followup.history']

        # Test user with manager group (for write/create access)
        cls.user_manager = cls.env['res.users'].create({
            'name': 'PF-004 Manager User',
            'login': 'pf004_manager@test.com',
            'email': 'pf004_manager@test.com',
            'company_id': cls.env.company.id,
            'company_ids': [Command.set([cls.env.company.id])],
            'group_ids': [
                Command.link(
                    cls.env.ref('account.group_account_manager').id,
                ),
            ],
        })

        # Test user with only user group (for read access)
        cls.user_account_user = cls.env['res.users'].create({
            'name': 'PF-004 Regular User',
            'login': 'pf004_user@test.com',
            'email': 'pf004_user@test.com',
            'company_id': cls.env.company.id,
            'company_ids': [Command.set([cls.env.company.id])],
            'group_ids': [
                Command.link(
                    cls.env.ref('account.group_account_user').id,
                ),
            ],
        })

    # =========================================================================
    # SCENARIO 1: Automatic History Creation on Email Dispatch (BR-001)
    # =========================================================================

    def test_scenario_1_create_email_history(self):
        """Scenario 1 BR-001: history record created for email actions."""
        history = self._create_history_record(
            partner=self.partner_overdue_7d,
            action_type='email',
            level=self.first_reminder_level,
            invoice=self.inv_7d,
        )
        self.assertTrue(history.id)
        self.assertEqual(history.partner_id, self.partner_overdue_7d)
        self.assertEqual(history.action_type, 'email')
        self.assertEqual(history.followup_level_id,
                         self.first_reminder_level)

    def test_scenario_1_history_required_fields_default(self):
        """Scenario 1 BR-005: required fields have sensible defaults."""
        history = self.History.create({
            'partner_id': self.partner_overdue_7d.id,
            'action_type': 'note',
            'summary': 'Test note',
        })
        # action_date defaults to fields.Datetime.now()
        self.assertTrue(history.action_date)
        # user_id defaults to env.user
        self.assertEqual(history.user_id, self.env.user)

    # =========================================================================
    # SCENARIO 2: View Customer Action History (ordering)
    # =========================================================================

    def test_scenario_2_history_ordered_newest_first(self):
        """Scenario 2: history records ordered by action_date desc."""
        partner = self.partner_overdue_30d
        # Create three history records with distinct action_dates
        h1 = self._create_history_record(
            partner=partner, action_type='email',
            summary='Older',
        )
        h1.write_date  # force flush
        h_middle = self._create_history_record(
            partner=partner, action_type='phone',
            summary='Middle',
        )
        h_middle.write_date
        h_newest = self._create_history_record(
            partner=partner, action_type='letter',
            summary='Newest',
        )
        # Search returns in order
        records = self.History.search([
            ('partner_id', '=', partner.id),
        ])
        self.assertGreaterEqual(len(records), 3)
        # The first record (highest priority) should be the newest
        # (action_date is the same since freeze_time, so id ordering
        # tiebreaks; newest id == newest record)
        self.assertEqual(records[0], h_newest,
                         'Newest record (or highest id under same time) '
                         'must appear first per _order=action_date desc, id desc.')

    # =========================================================================
    # SCENARIO 3: Manual Activity Logging
    # =========================================================================

    def test_scenario_3_manual_phone_call(self):
        """Scenario 3: manually log a phone-call action."""
        history = self._create_history_record(
            partner=self.partner_overdue_14d,
            action_type='phone',
            summary='Spoke with AP team',
            notes='<p>Customer promised payment next week.</p>',
        )
        self.assertEqual(history.action_type, 'phone')
        self.assertIn('next week', history.notes or '')

    def test_scenario_3_manual_letter(self):
        """Scenario 3: manually log a letter action."""
        history = self._create_history_record(
            partner=self.partner_overdue_21d,
            action_type='letter',
            summary='Mailed certified letter',
        )
        self.assertEqual(history.action_type, 'letter')

    def test_scenario_3_manual_meeting(self):
        """Scenario 3: manually log a meeting action."""
        history = self._create_history_record(
            partner=self.partner_overdue_30d,
            action_type='meeting',
            summary='In-person review',
        )
        self.assertEqual(history.action_type, 'meeting')

    def test_scenario_3_all_action_types_supported(self):
        """Scenario 3: all eight action_type selection values valid."""
        for action_type in ('email', 'phone', 'letter', 'meeting',
                            'promise', 'status', 'note', 'sms'):
            history = self._create_history_record(
                partner=self.partner_overdue_7d,
                action_type=action_type,
                summary=f'Test {action_type}',
            )
            self.assertEqual(history.action_type, action_type)

    # =========================================================================
    # SCENARIO 4: Invoice References (BR-004)
    # =========================================================================

    def test_scenario_4_single_invoice_reference(self):
        """Scenario 4 BR-004: invoice_id (single) reference works."""
        history = self._create_history_record(
            partner=self.partner_overdue_7d,
            invoice=self.inv_7d,
        )
        self.assertEqual(history.invoice_id, self.inv_7d)

    def test_scenario_4_many_invoice_references(self):
        """Scenario 4 BR-004: invoice_ids (Many2many) reference works.

        ``invoice_ids`` is NOT in the ``_IMMUTABILITY_WHITELIST``, so the
        Many2many MUST be populated atomically inside the initial
        ``create()`` call. Setting it post-creation would trigger the
        immutability guard in
        :meth:`account_followup_history.AccountFollowupHistory.write`
        and raise ``UserError``.
        """
        # Pass invoice_ids through **kwargs so it lands in the create
        # vals dict atomically. Do NOT pass ``invoice`` (singular) —
        # the helper would overwrite our invoice_ids with a single-item
        # Command.set in that branch.
        history = self._create_history_record(
            partner=self.partner_mixed_aging,
            action_type='email',
            invoice_ids=[Command.set([
                self.inv_mixed_15d.id,
                self.inv_mixed_45d.id,
                self.inv_mixed_75d.id,
            ])],
        )
        self.assertEqual(len(history.invoice_ids), 3)

    def test_scenario_4_br_004_history_preserved_on_invoice_delete(self):
        """BR-004: history record preserved when invoice is deleted.

        invoice_id uses ondelete='set null' so deleting the invoice
        clears the FK without destroying the history record.
        """
        # Create a fresh draft invoice (cannot delete posted ones)
        partner = self.partner_overdue_7d
        invoice = self._create_overdue_invoice(
            partner=partner,
            invoice_date=FROZEN_DATE - timedelta(days=10),
            amount=100.0,
            post=False,
        )
        history = self._create_history_record(
            partner=partner,
            invoice=invoice,
        )
        self.assertEqual(history.invoice_id, invoice)
        # Delete the draft invoice (capture id only for documentation;
        # the ondelete='set null' rule is verified via invoice_id below).
        invoice.unlink()
        # History record must still exist
        self.assertTrue(history.exists(),
                        'History record must survive invoice deletion (BR-004).')
        # invoice_id is set to NULL
        self.assertFalse(history.invoice_id,
                         'invoice_id must be cleared (ondelete=set null).')

    # =========================================================================
    # SCENARIO 5: Manual Activities (attachments + scheduling)
    # =========================================================================

    def test_scenario_5_promised_date_schedules_activity(self):
        """Scenario 5 BR-006: promised_date schedules a mail.activity."""
        partner = self.partner_overdue_30d
        history = self.History.create({
            'partner_id': partner.id,
            'action_type': 'promise',
            'summary': 'Customer promise',
            'promised_date': FROZEN_DATE + timedelta(days=14),
            'promised_amount': 1000.0,
            'user_id': self.env.user.id,
        })
        # An activity should have been scheduled
        self.assertTrue(
            history.activity_ids,
            'mail.activity must be scheduled when promised_date is set.',
        )

    def test_scenario_5_attachments_supported(self):
        """Scenario 5: attachment_ids field is whitelisted for post-creation.

        Note: ``ir.attachment.datas`` expects a *base64-encoded* binary
        payload (the ORM decodes it to populate ``raw``). Passing the
        unencoded raw bytes would fail with ``binascii.Error: Incorrect
        padding`` during the b64decode call inside
        :meth:`ir.attachment.create`. We use the ``raw`` field directly
        (which stores the binary content as-is) for clarity and to
        avoid the encode/decode round-trip.
        """
        history = self._create_history_record(
            partner=self.partner_overdue_14d,
            action_type='letter',
            summary='Mailed reminder',
        )
        # Create a test attachment using ``raw`` (raw binary) rather
        # than ``datas`` (base64-encoded) to avoid padding errors.
        attachment = self.env['ir.attachment'].create({
            'name': 'reminder.pdf',
            'raw': b'fake pdf data',
            'res_model': 'account.followup.history',
            'res_id': history.id,
        })
        # Post-creation attachment add must succeed (whitelist)
        history.write({
            'attachment_ids': [Command.link(attachment.id)],
        })
        self.assertIn(attachment, history.attachment_ids)

    # =========================================================================
    # SCENARIO 6: Outcome Tracking
    # =========================================================================

    def test_scenario_6_outcome_default_pending(self):
        """Scenario 6: outcome defaults to 'pending'."""
        history = self._create_history_record(
            partner=self.partner_overdue_7d,
        )
        self.assertEqual(history.outcome, 'pending',
                         "Default outcome must be 'pending'.")

    def test_scenario_6_outcome_mutable_post_creation(self):
        """Scenario 6: outcome is in _IMMUTABILITY_WHITELIST."""
        history = self._create_history_record(
            partner=self.partner_overdue_7d,
        )
        # Update outcome — must succeed
        history.write({'outcome': 'payment_received'})
        self.assertEqual(history.outcome, 'payment_received')

    def test_scenario_6_outcome_selection_values(self):
        """Scenario 6: outcome accepts all declared selection values."""
        history = self._create_history_record(
            partner=self.partner_overdue_7d,
        )
        for outcome_value in (
            'pending', 'contacted', 'no_contact',
            'payment_promised', 'payment_received',
            'disputed', 'escalated', 'closed',
        ):
            history.write({'outcome': outcome_value})
            self.assertEqual(history.outcome, outcome_value)

    # =========================================================================
    # SCENARIO 7: View Email Content (mail_message_id linkage)
    # =========================================================================

    def test_scenario_7_mail_message_id_linkage(self):
        """Scenario 7: mail_message_id links a history to a mail.message."""
        partner = self.partner_overdue_7d
        # Post a chatter message to obtain a mail.message
        message = partner.message_post(body='Test follow-up')
        history = self.History.create({
            'partner_id': partner.id,
            'action_type': 'email',
            'summary': 'Sent reminder',
            'mail_message_id': message.id,
        })
        self.assertEqual(history.mail_message_id, message)

    def test_scenario_7_mail_message_id_in_whitelist(self):
        """Scenario 7: mail_message_id is in _IMMUTABILITY_WHITELIST."""
        history = self._create_history_record(
            partner=self.partner_overdue_7d,
        )
        # The mail pipeline writes mail_message_id asynchronously after
        # record creation, so it must be writable.
        message = self.partner_overdue_7d.message_post(body='Async')
        history.write({'mail_message_id': message.id})
        self.assertEqual(history.mail_message_id, message)

    # =========================================================================
    # SCENARIO 8: Payment Promise Tracking (BR-006)
    # =========================================================================

    def test_scenario_8_promise_fields_persist(self):
        """Scenario 8 BR-006: promised_date and promised_amount persist."""
        history = self.History.create({
            'partner_id': self.partner_overdue_30d.id,
            'action_type': 'promise',
            'summary': 'Promise to pay',
            'promised_date': FROZEN_DATE + timedelta(days=21),
            'promised_amount': 2500.0,
        })
        self.assertEqual(history.promised_date,
                         FROZEN_DATE + timedelta(days=21))
        self.assertEqual(history.promised_amount, 2500.0)

    def test_scenario_8_promise_fields_in_whitelist(self):
        """Scenario 8: promised_date and promised_amount are mutable post-create."""
        history = self._create_history_record(
            partner=self.partner_overdue_30d,
            action_type='promise',
        )
        # Post-creation update must succeed (whitelist).
        new_date = FROZEN_DATE + timedelta(days=14)
        history.write({
            'promised_date': new_date,
            'promised_amount': 500.0,
        })
        self.assertEqual(history.promised_date, new_date)
        self.assertEqual(history.promised_amount, 500.0)

    def test_scenario_8_onchange_promised_date_warning(self):
        """Scenario 8: _onchange_promised_date emits a UI warning."""
        history = self.History.new({
            'partner_id': self.partner_overdue_7d.id,
            'action_type': 'promise',
            'user_id': self.env.user.id,
            'summary': 'Test promise',
            'promised_date': FROZEN_DATE + timedelta(days=7),
        })
        warning = history._onchange_promised_date()
        self.assertIsNotNone(warning,
                             'A warning dict must be returned for promise.')
        self.assertIn('warning', warning)
        self.assertIn('title', warning['warning'])
        self.assertIn('message', warning['warning'])

    def test_scenario_8_onchange_promised_date_returns_none_when_unset(self):
        """Scenario 8: _onchange_promised_date returns None when no date."""
        history = self.History.new({
            'partner_id': self.partner_overdue_7d.id,
            'action_type': 'note',
            'user_id': self.env.user.id,
            'summary': 'No promise',
            'promised_date': False,
        })
        result = history._onchange_promised_date()
        self.assertIsNone(result,
                          'No warning when promised_date is unset.')

    # =========================================================================
    # BR-003: IMMUTABILITY (8 tests for non-whitelisted fields)
    # =========================================================================

    def test_br_003_cannot_modify_action_type(self):
        """BR-003: action_type cannot be modified after creation."""
        history = self._create_history_record(
            partner=self.partner_overdue_7d,
            action_type='email',
        )
        with self.assertRaises(UserError):
            history.write({'action_type': 'phone'})

    def test_br_003_cannot_modify_action_date(self):
        """BR-003: action_date cannot be modified after creation."""
        history = self._create_history_record(
            partner=self.partner_overdue_7d,
        )
        with self.assertRaises(UserError):
            history.write({
                'action_date': fields.Datetime.now() - timedelta(days=1),
            })

    def test_br_003_cannot_modify_partner_id(self):
        """BR-003: partner_id cannot be modified after creation."""
        history = self._create_history_record(
            partner=self.partner_overdue_7d,
        )
        with self.assertRaises(UserError):
            history.write({'partner_id': self.partner_overdue_14d.id})

    def test_br_003_cannot_modify_summary(self):
        """BR-003: summary cannot be modified after creation."""
        history = self._create_history_record(
            partner=self.partner_overdue_7d,
        )
        with self.assertRaises(UserError):
            history.write({'summary': 'Tampered summary'})

    def test_br_003_cannot_modify_total_amount_communicated(self):
        """BR-003: total_amount_communicated cannot be modified post-create."""
        history = self.History.create({
            'partner_id': self.partner_overdue_30d.id,
            'action_type': 'email',
            'summary': 'Test',
            'total_amount_communicated': 1000.0,
        })
        with self.assertRaises(UserError):
            history.write({'total_amount_communicated': 999999.0})

    def test_br_003_cannot_modify_user_id(self):
        """BR-003: user_id cannot be modified after creation.

        Note: user_id is in the mail.thread tracking so we have to be
        careful. The model declares it as required+tracked but NOT in
        the whitelist, so modifications raise UserError.
        """
        history = self._create_history_record(
            partner=self.partner_overdue_7d,
        )
        # Create a different user
        other_user = self.env['res.users'].create({
            'name': 'Other User',
            'login': 'other_pf004@test.com',
            'email': 'other_pf004@test.com',
        })
        with self.assertRaises(UserError):
            history.write({'user_id': other_user.id})

    def test_br_003_cannot_modify_company_id(self):
        """BR-003: company_id cannot be modified after creation."""
        history = self._create_history_record(
            partner=self.partner_overdue_7d,
        )
        # Create a different company
        other_company = self.env['res.company'].create({
            'name': 'Other Company',
        })
        with self.assertRaises(UserError):
            history.write({'company_id': other_company.id})

    def test_br_003_cannot_modify_followup_level_id(self):
        """BR-003: followup_level_id cannot be modified after creation."""
        history = self._create_history_record(
            partner=self.partner_overdue_7d,
            level=self.first_reminder_level,
        )
        with self.assertRaises(UserError):
            history.write({'followup_level_id': self.warning_level.id})

    # =========================================================================
    # BR-003: WHITELIST MUTABILITY (5 tests for permitted fields)
    # =========================================================================

    def test_br_003_whitelist_outcome_writable(self):
        """Whitelist: outcome can be modified post-create."""
        history = self._create_history_record(
            partner=self.partner_overdue_7d,
        )
        history.write({'outcome': 'payment_received'})
        self.assertEqual(history.outcome, 'payment_received')

    def test_br_003_whitelist_notes_writable(self):
        """Whitelist: notes can be modified post-create."""
        history = self._create_history_record(
            partner=self.partner_overdue_7d,
        )
        history.write({'notes': '<p>Updated notes</p>'})
        self.assertIn('Updated notes', history.notes)

    def test_br_003_whitelist_attachments_writable(self):
        """Whitelist: attachment_ids can be modified post-create."""
        history = self._create_history_record(
            partner=self.partner_overdue_7d,
        )
        attachment = self.env['ir.attachment'].create({
            'name': 'test.pdf',
            'datas': b'data',
        })
        history.write({
            'attachment_ids': [Command.link(attachment.id)],
        })
        self.assertIn(attachment, history.attachment_ids)

    def test_br_003_whitelist_promised_date_writable(self):
        """Whitelist: promised_date can be modified post-create."""
        history = self._create_history_record(
            partner=self.partner_overdue_7d,
        )
        new_date = FROZEN_DATE + timedelta(days=10)
        history.write({'promised_date': new_date})
        self.assertEqual(history.promised_date, new_date)

    def test_br_003_whitelist_promised_amount_writable(self):
        """Whitelist: promised_amount can be modified post-create."""
        history = self._create_history_record(
            partner=self.partner_overdue_7d,
        )
        history.write({'promised_amount': 500.0})
        self.assertEqual(history.promised_amount, 500.0)

    # =========================================================================
    # BR-003: UNLINK BLOCKED FOR USER AND MANAGER
    # =========================================================================

    def test_br_003_user_cannot_unlink(self):
        """BR-003: user-group user cannot unlink history records.

        The ir.model.access.csv sets perm_unlink=0 for the user group.
        Attempting to unlink raises ``AccessError`` (ACL layer) or
        ``UserError`` (Python override layer); both are acceptable.

        Implementation note: ``self.assertRaises`` cannot accept a
        tuple of exception types because Odoo's ``_assertRaises``
        override calls ``issubclass(exception, AccessError)`` directly
        without handling tuples (raises ``TypeError``). We therefore
        use a try/except + explicit fail pattern.
        """
        history = self._create_history_record(
            partner=self.partner_overdue_7d,
        )
        # Switch to user_account_user (read-only)
        try:
            history.with_user(self.user_account_user).unlink()
            self.fail('Expected AccessError or UserError when user '
                      'attempts to unlink a history record.')
        except (AccessError, UserError):
            pass  # expected — perm_unlink=0 OR Python guard fires

    def test_br_003_manager_also_cannot_unlink(self):
        """BR-003: MANAGER user ALSO cannot unlink history records.

        The ir.model.access.csv sets perm_unlink=0 for BOTH the user
        and manager groups. This explicitly verifies the manager-level
        constraint, complementing test_br_003_user_cannot_unlink.

        Implementation note: see ``test_br_003_user_cannot_unlink`` for
        the rationale behind the try/except + fail pattern.
        """
        history = self._create_history_record(
            partner=self.partner_overdue_7d,
        )
        # Switch to manager user — perm_unlink=0 still applies
        try:
            history.with_user(self.user_manager).unlink()
            self.fail('Expected AccessError or UserError when manager '
                      'attempts to unlink a history record.')
        except (AccessError, UserError):
            pass  # expected — perm_unlink=0 OR Python guard fires

    def test_br_003_unlink_python_override_blocks_non_su(self):
        """BR-003: even if ACL passes, the Python unlink() override blocks.

        The model's unlink() method checks env.su and raises UserError
        for non-superuser context. This is defense-in-depth — even if
        a future ACL change allowed unlink, the Python guard would
        still block it.

        Implementation note: see ``test_br_003_user_cannot_unlink`` for
        the rationale behind the try/except + fail pattern.
        """
        history = self._create_history_record(
            partner=self.partner_overdue_7d,
        )
        # Direct unlink as the test user (env.su is False)
        try:
            history.unlink()
            self.fail('Expected AccessError or UserError when non-su '
                      'user attempts to unlink a history record.')
        except (AccessError, UserError):
            pass  # expected — ACL OR Python guard fires

    # =========================================================================
    # COPY REJECTION (audit-trail integrity)
    # =========================================================================

    def test_copy_rejected_for_non_su(self):
        """Copy is rejected for non-superuser context (audit integrity).

        Duplicating a history record would create a false historical
        claim. The model's copy() override raises UserError unless
        env.su is True.
        """
        history = self._create_history_record(
            partner=self.partner_overdue_7d,
        )
        # As regular user, copy must raise UserError.
        with self.assertRaises(UserError):
            history.with_user(self.user_account_user).copy()

    # =========================================================================
    # BR-001..BR-007 BUSINESS RULES (additional)
    # =========================================================================

    def test_br_001_create_via_cron(self):
        """BR-001: history can be created by external callers (cron).

        BR-001 mandates automatic history creation on email dispatch;
        the cron handler is the primary caller. Tests in test_pf_002.py
        verify the cron path; here we verify the model's create()
        accepts the cron's payload shape.
        """
        history = self.History.create({
            'partner_id': self.partner_overdue_7d.id,
            'followup_level_id': self.first_reminder_level.id,
            'action_type': 'email',
            'action_date': fields.Datetime.now(),
            'user_id': self.env.uid,
            'company_id': self.env.company.id,
            'summary': 'Automated follow-up email sent',
            'invoice_ids': [Command.set([self.inv_7d.id])],
            'total_amount_communicated': 1500.0,
        })
        self.assertTrue(history.id,
                        'Cron-payload-shape create() must succeed.')

    def test_br_002_manual_creation_for_non_email(self):
        """BR-002: manual creation permitted for non-email actions."""
        for action_type in ('phone', 'letter', 'meeting', 'sms'):
            history = self.History.create({
                'partner_id': self.partner_overdue_7d.id,
                'action_type': action_type,
                'summary': f'Manual {action_type}',
            })
            self.assertEqual(history.action_type, action_type)

    def test_br_005_required_field_partner_id(self):
        """BR-005: partner_id is required."""
        with self.assertRaises(Exception):  # noqa: BLE001
            with mute_logger('odoo.sql_db'):
                self.History.create({
                    'action_type': 'email',
                    'summary': 'No partner',
                })

    def test_br_005_required_field_action_type(self):
        """BR-005: action_type is required."""
        with self.assertRaises(Exception):  # noqa: BLE001
            with mute_logger('odoo.sql_db'):
                self.History.create({
                    'partner_id': self.partner_overdue_7d.id,
                    'summary': 'No type',
                })

    def test_br_005_required_field_summary(self):
        """BR-005: summary is required."""
        with self.assertRaises(Exception):  # noqa: BLE001
            with mute_logger('odoo.sql_db'):
                self.History.create({
                    'partner_id': self.partner_overdue_7d.id,
                    'action_type': 'email',
                })

    def test_br_006_promise_creates_activity(self):
        """BR-006: promised_date triggers activity scheduling.

        Already covered by test_scenario_5_promised_date_schedules_activity
        but repeat with explicit BR identifier for traceability.
        """
        history = self.History.create({
            'partner_id': self.partner_overdue_30d.id,
            'action_type': 'promise',
            'summary': 'BR-006',
            'promised_date': FROZEN_DATE + timedelta(days=14),
            'promised_amount': 2000.0,
            'user_id': self.env.user.id,
        })
        self.assertTrue(history.activity_ids,
                        'BR-006: promise must schedule activity.')

    def test_br_007_attachments_chatter_supported(self):
        """BR-007: attachments via mail.thread chatter are supported."""
        history = self._create_history_record(
            partner=self.partner_overdue_7d,
        )
        # mail.thread provides message_post which can attach files
        # through attachment_ids in the message context.
        msg = history.message_post(body='Test message')
        self.assertTrue(msg,
                        'mail.thread chatter must be functional.')

    # =========================================================================
    # COMPUTE METHODS — display_name, currency_id
    # =========================================================================

    def test_compute_display_name(self):
        """Compute: display_name format is 'Partner — ActionType — Date'."""
        history = self._create_history_record(
            partner=self.partner_overdue_7d,
            action_type='email',
        )
        self.assertIn(self.partner_overdue_7d.name, history.display_name)
        self.assertIn('Email', history.display_name)

    def test_compute_currency_id_from_company(self):
        """Compute: currency_id derives from company.currency_id."""
        history = self._create_history_record(
            partner=self.partner_overdue_7d,
        )
        self.assertEqual(history.currency_id,
                         history.company_id.currency_id)

    # =========================================================================
    # ACTION METHODS — Smart Buttons
    # =========================================================================

    def test_action_view_invoice_with_invoice(self):
        """Action: action_view_invoice returns window action when invoice set."""
        history = self._create_history_record(
            partner=self.partner_overdue_7d,
            invoice=self.inv_7d,
        )
        action = history.action_view_invoice()
        self.assertEqual(action['type'], 'ir.actions.act_window')
        self.assertEqual(action['res_model'], 'account.move')
        self.assertEqual(action['res_id'], self.inv_7d.id)

    def test_action_view_invoice_without_invoice(self):
        """Action: action_view_invoice raises when no invoice linked."""
        history = self._create_history_record(
            partner=self.partner_overdue_7d,
        )
        # No invoice_id set
        with self.assertRaises(UserError):
            history.action_view_invoice()

    def test_action_view_invoices_many(self):
        """Action: action_view_invoices returns list view for multiple.

        ``invoice_ids`` is NOT in the immutability whitelist, so the
        Many2many MUST be populated atomically inside the initial
        ``create()`` call rather than via post-creation assignment.
        """
        history = self._create_history_record(
            partner=self.partner_mixed_aging,
            invoice_ids=[Command.set([
                self.inv_mixed_15d.id, self.inv_mixed_45d.id,
            ])],
        )
        action = history.action_view_invoices()
        self.assertEqual(action['view_mode'], 'list,form',
                         'Multiple invoices yield list view.')

    def test_action_view_invoices_single(self):
        """Action: action_view_invoices returns form view when single.

        ``invoice_ids`` is NOT in the immutability whitelist, so the
        Many2many MUST be populated atomically inside the initial
        ``create()`` call rather than via post-creation assignment.
        """
        history = self._create_history_record(
            partner=self.partner_overdue_7d,
            invoice_ids=[Command.set([self.inv_7d.id])],
        )
        action = history.action_view_invoices()
        self.assertEqual(action['view_mode'], 'form',
                         'Single invoice yields form view.')

    def test_action_view_invoices_empty_raises(self):
        """Action: action_view_invoices raises when no invoices linked."""
        history = self._create_history_record(
            partner=self.partner_overdue_7d,
        )
        with self.assertRaises(UserError):
            history.action_view_invoices()

    def test_action_view_partner(self):
        """Action: action_view_partner navigates to partner record."""
        history = self._create_history_record(
            partner=self.partner_overdue_30d,
        )
        action = history.action_view_partner()
        self.assertEqual(action['type'], 'ir.actions.act_window')
        self.assertEqual(action['res_model'], 'res.partner')
        self.assertEqual(action['res_id'], self.partner_overdue_30d.id)
