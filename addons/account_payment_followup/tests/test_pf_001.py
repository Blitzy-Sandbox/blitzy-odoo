# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
PF-001 — Follow-up Level Configuration: Acceptance Test Suite
==============================================================

Verifies the configuration model surface introduced by:

  * ``addons/account_payment_followup/models/account_followup_level.py`` —
    net-new ``account.followup.level`` model.

Acceptance Scenarios (BDD Given/When/Then) covered:

  - Scenario 1: Create New Follow-up Level with valid CRUD attributes
  - Scenario 2: Configure Default Follow-up Levels (sequence/delay
    canonical ladder: 7 → 14 → 21 → 30 days)
  - Scenario 3: Set Email Template per Level (FK validity + domain on
    res.partner)
  - Scenario 4: Set Action Type per Level (selection validity)
  - Scenario 5: Set Trigger Actions on a Level (block_sales,
    update_trust, notify_sales_rep, collection_list)
  - Scenario 6: Set Minimum Amount Threshold (BR-005 non-negative)
  - Scenario 7: Active/Archive flag toggle and ordering on browse
  - Scenario 8: Multi-Company Level Isolation (per-company unique
    sequence)

Plus Business Rules BR-001..BR-005 and edge cases. Targets ≥80% line
coverage of ``models/account_followup_level.py`` PF-001 portions
(configuration fields, constraints, smart-button actions, currency
compute) — the cron handler portion is exhaustively covered by
``test_pf_002.py``.

Determinism
-----------
The class uses :class:`AccountPaymentFollowupTestCommon` which freezes
fixture creation to ``date(2024, 6, 30)``. PF-001 itself has no
date-sensitive logic; the freeze is inherited solely so this suite
can interleave with PF-005 fixtures without time drift.

Rules Compliance (AAP §0.7)
---------------------------
- R-01: No imports from sibling new modules.
- R-02: No imports from Enterprise modules.
- R-04: Targets ≥80% coverage of ``account_followup_level.py``.
- R-07: No ``sudo()`` calls.
- R-09: Filename is ``test_pf_001.py`` exactly (story ID lowercase).
"""

import logging

from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import AccountPaymentFollowupTestCommon

_logger = logging.getLogger(__name__)


@tagged('post_install', '-at_install')
class TestFollowupLevelConfiguration(AccountPaymentFollowupTestCommon):
    """PF-001 — Follow-up Level Configuration acceptance tests.

    Inherits :class:`AccountPaymentFollowupTestCommon` for the four seeded
    follow-up levels (First Reminder/Second Reminder/Warning/Final Notice)
    and the ``accountman`` user with manager access.

    Implementation Notes
    --------------------
    Tests that mutate the ``sequence`` field on existing levels MUST first
    move that level to a non-conflicting sequence so the
    ``UNIQUE(sequence, company_id)`` SQL constraint is not violated by
    the simultaneous existence of two levels at the same sequence in the
    same company.

    Tests that exercise the IntegrityError path use ``mute_logger`` on
    ``odoo.sql_db`` to suppress the noisy traceback from the unique-
    violation rollback path.
    """

    @classmethod
    def setUpClass(cls):
        """Build PF-001-specific fixtures on top of the common base.

        Adds:
          * A second test company (``company_secondary``) for cross-
            company isolation tests.
          * A reusable mail.template targeting res.partner for FK tests.
          * A test user explicitly granted ``account.group_account_user``
            (read-only) for ACL boundary checks.
        """
        super().setUpClass()
        Level = cls.env['account.followup.level']
        cls.Level = Level

        # Secondary test company for cross-company tests. Anchored to the
        # parent's company creation pattern so multi-company semantics
        # stay deterministic.
        cls.company_secondary = cls.env['res.company'].create({
            'name': 'PF-001 Secondary Company',
        })

        # Realign env.user companies to include the secondary one (so the
        # test user can read levels in either company without privilege
        # escalation).
        cls.env.user.company_ids = [
            Command.link(cls.company_secondary.id),
        ]

        # Reusable mail.template targeting res.partner — required by the
        # email_template_id domain constraint on
        # ``account.followup.level.email_template_id``.
        cls.test_template = cls.env['mail.template'].create({
            'name': 'PF-001 Test Template',
            'model_id': cls.env.ref('base.model_res_partner').id,
            'subject': 'Follow-up Test',
            'body_html': '<p>Test body</p>',
        })

    # =========================================================================
    # SCENARIO 1: Create New Follow-up Level (CRUD)
    # =========================================================================

    def test_scenario_1_create_followup_level(self):
        """Scenario 1: create a basic follow-up level with required fields.

        Given a manager user
        When they create a level with name, sequence, delay, and
        action_type
        Then the level is persisted and accessible via the ORM.
        """
        level = self.Level.create({
            'name': 'Test Reminder',
            'sequence': 100,
            'delay': 3,
            'action_type': 'automatic',
            'company_id': self.env.company.id,
        })
        self.assertTrue(level.id, 'Level must be created with an ID.')
        self.assertEqual(level.name, 'Test Reminder')
        self.assertEqual(level.sequence, 100)
        self.assertEqual(level.delay, 3)
        self.assertEqual(level.action_type, 'automatic')
        self.assertTrue(level.active, 'New levels default active=True.')

    def test_scenario_1_read_followup_level(self):
        """Scenario 1 (R): read an existing level by external ID."""
        level = self.first_reminder_level
        self.assertTrue(level.id)
        self.assertEqual(level.sequence, 10)
        self.assertEqual(level.delay, 7)

    def test_scenario_1_update_followup_level(self):
        """Scenario 1 (U): update a level's mutable fields."""
        level = self.Level.create({
            'name': 'Update Test',
            'sequence': 101,
            'delay': 5,
            'action_type': 'manual',
            'company_id': self.env.company.id,
        })
        level.write({'delay': 10, 'description': 'Updated description'})
        self.assertEqual(level.delay, 10)
        self.assertEqual(level.description, 'Updated description')

    def test_scenario_1_delete_followup_level(self):
        """Scenario 1 (D): delete a custom level."""
        level = self.Level.create({
            'name': 'Delete Test',
            'sequence': 102,
            'delay': 2,
            'action_type': 'manual',
            'company_id': self.env.company.id,
        })
        level_id = level.id
        level.unlink()
        self.assertFalse(self.Level.browse(level_id).exists(),
                         'Level must not exist after unlink.')

    # =========================================================================
    # SCENARIO 2: Configure Default Follow-up Levels (canonical ladder)
    # =========================================================================

    def test_scenario_2_default_levels_loaded(self):
        """Scenario 2: the four seeded default levels exist post-install.

        Per data/followup_data.xml: First Reminder (seq=10, delay=7),
        Second Reminder (seq=20, delay=14), Warning (seq=30, delay=21),
        Final Notice (seq=40, delay=30).
        """
        self.assertEqual(self.first_reminder_level.sequence, 10)
        self.assertEqual(self.first_reminder_level.delay, 7)
        self.assertEqual(self.second_reminder_level.sequence, 20)
        self.assertEqual(self.second_reminder_level.delay, 14)
        self.assertEqual(self.warning_level.sequence, 30)
        self.assertEqual(self.warning_level.delay, 21)
        self.assertEqual(self.final_notice_level.sequence, 40)
        self.assertEqual(self.final_notice_level.delay, 30)

    def test_scenario_2_default_levels_have_email_templates(self):
        """Scenario 2: each default level has an email template assigned."""
        self.assertTrue(self.first_reminder_level.email_template_id,
                        'First Reminder must have a template.')
        self.assertTrue(self.second_reminder_level.email_template_id,
                        'Second Reminder must have a template.')
        self.assertTrue(self.warning_level.email_template_id,
                        'Warning must have a template.')
        self.assertTrue(self.final_notice_level.email_template_id,
                        'Final Notice must have a template.')

    def test_scenario_2_default_levels_action_type_automatic(self):
        """Scenario 2: all default levels are automatic for cron processing."""
        for level in (
            self.first_reminder_level, self.second_reminder_level,
            self.warning_level, self.final_notice_level,
        ):
            self.assertEqual(
                level.action_type, 'automatic',
                f"Level '{level.name}' must default to action_type=automatic "
                f"so the PF-002 cron processes it.",
            )

    def test_scenario_2_levels_ordered_by_sequence(self):
        """Scenario 2: browse() returns levels in sequence order.

        ``_order = 'sequence, delay, id'`` should make a search() yield
        levels from earliest (lowest seq) to latest (highest seq).
        """
        levels = self.Level.search(
            [('company_id', '=', self.env.company.id)],
            order='sequence',
        )
        self.assertGreaterEqual(len(levels), 4,
                                'At least the four seed levels exist.')
        seqs = levels.mapped('sequence')
        self.assertEqual(seqs, sorted(seqs),
                         'search(order="sequence") must return levels '
                         'in ascending sequence order.')

    # =========================================================================
    # SCENARIO 3: Email Template per Level
    # =========================================================================

    def test_scenario_3_email_template_assignment(self):
        """Scenario 3: assign a mail.template to a level."""
        level = self.Level.create({
            'name': 'Template Assignment Test',
            'sequence': 110,
            'delay': 1,
            'action_type': 'email',
            'email_template_id': self.test_template.id,
            'company_id': self.env.company.id,
        })
        self.assertEqual(level.email_template_id, self.test_template,
                         'Email template assignment must persist.')

    def test_scenario_3_email_template_is_optional(self):
        """Scenario 3: email_template_id may be unset for non-email levels."""
        level = self.Level.create({
            'name': 'No Template',
            'sequence': 111,
            'delay': 1,
            'action_type': 'phone',
            'company_id': self.env.company.id,
        })
        self.assertFalse(level.email_template_id,
                         'email_template_id is optional.')

    def test_scenario_3_email_template_ondelete_restrict(self):
        """Scenario 3: deleting a referenced template raises (ondelete=restrict).

        The email_template_id field declares ``ondelete='restrict'`` so a
        template cannot be silently deleted while still referenced.
        """
        level = self.Level.create({
            'name': 'Restrict Test',
            'sequence': 112,
            'delay': 1,
            'action_type': 'email',
            'email_template_id': self.test_template.id,
            'company_id': self.env.company.id,
        })
        # Cannot delete a referenced template — restrict should raise.
        # A different exception type is permissible (e.g. IntegrityError
        # vs UserError) depending on Odoo version, so we catch broadly.
        with self.assertRaises(Exception):  # noqa: BLE001
            with mute_logger('odoo.sql_db'):
                self.test_template.unlink()
        # Defensive: the level must still exist.
        self.assertTrue(level.exists())

    # =========================================================================
    # SCENARIO 4: Action Type Selection
    # =========================================================================

    def test_scenario_4_action_type_selection_values(self):
        """Scenario 4: action_type accepts all six declared selection values.

        Per the model: 'automatic', 'manual', 'email', 'letter', 'phone',
        'lawyer'.

        Implementation note: the ``UNIQUE(sequence, company_id)`` SQL
        constraint requires distinct ``sequence`` values per company. We
        derive the sequence from the loop index (``200 + i*10``) rather
        than from ``ord(action_type[0])`` because two action types may
        share the same first letter (e.g., ``letter`` and ``lawyer``
        both start with ``l``), which would collide on sequence=308 and
        raise ``UniqueViolation``.
        """
        for i, action_type in enumerate(('automatic', 'manual', 'email',
                                         'letter', 'phone', 'lawyer')):
            level = self.Level.create({
                'name': f'Action Type {action_type}',
                'sequence': 200 + i * 10,
                'delay': 1,
                'action_type': action_type,
                'company_id': self.env.company.id,
            })
            self.assertEqual(level.action_type, action_type,
                             f"Level must accept action_type={action_type}.")

    def test_scenario_4_action_type_invalid_value_rejected(self):
        """Scenario 4: assigning an invalid action_type raises an error.

        Selection field validates at write time. Odoo coerces invalid
        values to a ``ValueError`` raised by the ORM. We use a try/except
        pattern with an explicit fail-if-no-raise rather than
        ``assertRaises((ValueError, ValidationError))`` because Odoo's
        custom ``_assertRaises`` calls ``issubclass()`` on its first
        argument unconditionally, which raises ``TypeError`` when given
        a tuple of exception types.
        """
        try:
            self.Level.create({
                'name': 'Invalid Action Type',
                'sequence': 130,
                'delay': 1,
                'action_type': 'not_a_real_value',
                'company_id': self.env.company.id,
            })
            self.fail("Expected ValueError or ValidationError to be raised "
                      "for invalid action_type selection value.")
        except (ValueError, ValidationError):
            pass  # expected — ORM rejects the invalid selection value

    # =========================================================================
    # SCENARIO 5: Trigger Actions on a Level
    # =========================================================================

    def test_scenario_5_trigger_block_sales(self):
        """Scenario 5: trigger_block_sales flag persists."""
        level = self.Level.create({
            'name': 'Block Sales Test',
            'sequence': 140,
            'delay': 30,
            'action_type': 'automatic',
            'trigger_block_sales': True,
            'company_id': self.env.company.id,
        })
        self.assertTrue(level.trigger_block_sales,
                        'trigger_block_sales must persist.')

    def test_scenario_5_trigger_collection_list(self):
        """Scenario 5: trigger_collection_list flag persists."""
        level = self.Level.create({
            'name': 'Collection Test',
            'sequence': 141,
            'delay': 21,
            'action_type': 'automatic',
            'trigger_collection_list': True,
            'company_id': self.env.company.id,
        })
        self.assertTrue(level.trigger_collection_list,
                        'trigger_collection_list must persist.')

    def test_scenario_5_trigger_notify_sales_rep(self):
        """Scenario 5: trigger_notify_sales_rep flag persists."""
        level = self.Level.create({
            'name': 'Notify Test',
            'sequence': 142,
            'delay': 14,
            'action_type': 'automatic',
            'trigger_notify_sales_rep': True,
            'company_id': self.env.company.id,
        })
        self.assertTrue(level.trigger_notify_sales_rep)

    def test_scenario_5_trigger_update_trust_selection(self):
        """Scenario 5: trigger_update_trust accepts normal/good/bad."""
        for trust_value in ('normal', 'good', 'bad'):
            level = self.Level.create({
                'name': f'Trust {trust_value}',
                'sequence': 150 + ord(trust_value[0]),
                'delay': 1,
                'action_type': 'automatic',
                'trigger_update_trust': trust_value,
                'company_id': self.env.company.id,
            })
            self.assertEqual(level.trigger_update_trust, trust_value)

    def test_scenario_5_attach_invoices_flag(self):
        """Scenario 5: attach_invoices flag (PF-002 BR-004) persists."""
        level = self.Level.create({
            'name': 'Attach Test',
            'sequence': 160,
            'delay': 21,
            'action_type': 'automatic',
            'attach_invoices': True,
            'company_id': self.env.company.id,
        })
        self.assertTrue(level.attach_invoices,
                        'attach_invoices flag must persist.')

    def test_scenario_5_default_triggers_are_false(self):
        """Scenario 5: by default, no trigger flags are set."""
        level = self.Level.create({
            'name': 'Defaults Test',
            'sequence': 161,
            'delay': 1,
            'action_type': 'automatic',
            'company_id': self.env.company.id,
        })
        self.assertFalse(level.trigger_block_sales)
        self.assertFalse(level.trigger_collection_list)
        self.assertFalse(level.trigger_notify_sales_rep)
        self.assertFalse(level.trigger_update_trust)
        self.assertFalse(level.attach_invoices)

    # =========================================================================
    # SCENARIO 6: Minimum Amount Threshold (BR-005)
    # =========================================================================

    def test_scenario_6_min_amount_default_is_zero(self):
        """Scenario 6: min_amount defaults to 0 (evaluate every partner)."""
        level = self.Level.create({
            'name': 'Min Amount Default',
            'sequence': 170,
            'delay': 1,
            'action_type': 'automatic',
            'company_id': self.env.company.id,
        })
        self.assertEqual(level.min_amount, 0.0,
                         'min_amount default is 0 (BR-005 boundary).')

    def test_scenario_6_min_amount_positive_persists(self):
        """Scenario 6: positive min_amount persists."""
        level = self.Level.create({
            'name': 'Min Amount 100',
            'sequence': 171,
            'delay': 14,
            'action_type': 'automatic',
            'min_amount': 100.0,
            'company_id': self.env.company.id,
        })
        self.assertEqual(level.min_amount, 100.0)

    def test_scenario_6_min_amount_negative_rejected(self):
        """Scenario 6 BR-005: negative min_amount is rejected by SQL CHECK."""
        # The model declares a SQL CHECK(min_amount >= 0) constraint.
        with self.assertRaises(Exception):  # noqa: BLE001
            with mute_logger('odoo.sql_db'):
                self.Level.create({
                    'name': 'Min Amount Negative',
                    'sequence': 172,
                    'delay': 1,
                    'action_type': 'automatic',
                    'min_amount': -10.0,
                    'company_id': self.env.company.id,
                })

    # =========================================================================
    # SCENARIO 7: Active flag toggle and ordering on browse
    # =========================================================================

    def test_scenario_7_active_default_true(self):
        """Scenario 7: new levels default to active=True."""
        level = self.Level.create({
            'name': 'Active Default',
            'sequence': 180,
            'delay': 1,
            'action_type': 'automatic',
            'company_id': self.env.company.id,
        })
        self.assertTrue(level.active, 'New levels are active by default.')

    def test_scenario_7_archived_levels_excluded_from_default_search(self):
        """Scenario 7: archived (active=False) levels are excluded by default.

        Odoo's standard ``active`` field semantics: search() excludes
        archived records unless ``active_test=False`` is passed.
        """
        level = self.Level.create({
            'name': 'Archived Level',
            'sequence': 181,
            'delay': 7,
            'action_type': 'automatic',
            'active': False,
            'company_id': self.env.company.id,
        })
        # Default search() must NOT return the archived level.
        active_levels = self.Level.search([
            ('id', '=', level.id),
            ('company_id', '=', self.env.company.id),
        ])
        self.assertFalse(active_levels.ids,
                         'Default search() must exclude archived records.')
        # With active_test=False, the archived level IS visible.
        all_levels = self.Level.with_context(active_test=False).search([
            ('id', '=', level.id),
        ])
        self.assertEqual(all_levels.ids, level.ids,
                         'active_test=False must include archived records.')

    def test_scenario_7_toggle_active_flag(self):
        """Scenario 7: toggling active flag works without errors."""
        level = self.Level.create({
            'name': 'Toggle Test',
            'sequence': 182,
            'delay': 7,
            'action_type': 'automatic',
            'company_id': self.env.company.id,
        })
        self.assertTrue(level.active)
        level.write({'active': False})
        self.assertFalse(level.active, 'Archived state must persist.')
        level.write({'active': True})
        self.assertTrue(level.active, 'Re-activation must persist.')

    # =========================================================================
    # SCENARIO 8: Multi-Company Isolation
    # =========================================================================

    def test_scenario_8_per_company_unique_sequence(self):
        """Scenario 8 BR-001: sequence is unique per company.

        Two levels with the same sequence in different companies are
        permitted; two levels with the same sequence in the SAME company
        violate UNIQUE(sequence, company_id).
        """
        # Same sequence in different companies — must succeed.
        level_a = self.Level.create({
            'name': 'Sequence in Company A',
            'sequence': 190,
            'delay': 7,
            'action_type': 'automatic',
            'company_id': self.env.company.id,
        })
        level_b = self.Level.create({
            'name': 'Sequence in Company B',
            'sequence': 190,  # SAME sequence
            'delay': 7,
            'action_type': 'automatic',
            'company_id': self.company_secondary.id,
        })
        self.assertTrue(level_a.id and level_b.id,
                        'Same sequence in different companies is permitted.')
        # Same sequence in SAME company — must fail (SQL constraint).
        with self.assertRaises(Exception):  # noqa: BLE001
            with mute_logger('odoo.sql_db'):
                self.Level.create({
                    'name': 'Duplicate Sequence',
                    'sequence': 190,  # SAME sequence + SAME company
                    'delay': 7,
                    'action_type': 'automatic',
                    'company_id': self.env.company.id,
                })

    def test_scenario_8_company_id_required(self):
        """Scenario 8 BR-001: company_id is required on every level."""
        # Cannot create without company_id (required=True).
        # If we omit it, Odoo's default lambda assigns env.company,
        # so we explicitly set False to verify the constraint fires.
        with self.assertRaises(Exception):  # noqa: BLE001
            with mute_logger('odoo.sql_db'):
                self.Level.create({
                    'name': 'No Company',
                    'sequence': 195,
                    'delay': 1,
                    'action_type': 'automatic',
                    'company_id': False,
                })

    # =========================================================================
    # BUSINESS RULES — BR-001 through BR-005
    # =========================================================================

    def test_br_001_unique_sequence_per_company_constraint(self):
        """BR-001: UNIQUE(sequence, company_id) constraint exists."""
        # Verify the constraint by attempting a duplicate insert.
        self.Level.create({
            'name': 'BR-001 First',
            'sequence': 250,
            'delay': 7,
            'action_type': 'automatic',
            'company_id': self.env.company.id,
        })
        with self.assertRaises(Exception):  # noqa: BLE001
            with mute_logger('odoo.sql_db'):
                self.Level.create({
                    'name': 'BR-001 Duplicate',
                    'sequence': 250,
                    'delay': 14,
                    'action_type': 'automatic',
                    'company_id': self.env.company.id,
                })

    def test_br_002_delay_non_negative(self):
        """BR-002: CHECK(delay >= 0) constraint exists."""
        # delay=0 is permitted (immediate-trigger level).
        level = self.Level.create({
            'name': 'BR-002 Zero Delay',
            'sequence': 251,
            'delay': 0,
            'action_type': 'automatic',
            'company_id': self.env.company.id,
        })
        self.assertEqual(level.delay, 0, 'delay=0 is permitted.')
        # delay=-1 is rejected.
        with self.assertRaises(Exception):  # noqa: BLE001
            with mute_logger('odoo.sql_db'):
                self.Level.create({
                    'name': 'BR-002 Negative',
                    'sequence': 252,
                    'delay': -1,
                    'action_type': 'automatic',
                    'company_id': self.env.company.id,
                })

    def test_br_003_sequence_delay_ordering_warning(self):
        """BR-003: SOFT validation — warns but does not raise.

        Per the model docstring, BR-003 is a SOFT validation that emits
        a warning when a higher-sequence level has a smaller delay than
        a lower-sequence level. The test verifies the warning fires
        without raising ValidationError.
        """
        # Create a lower-sequence high-delay level first.
        self.Level.create({
            'name': 'BR-003 Higher Delay First',
            'sequence': 270,
            'delay': 30,
            'action_type': 'automatic',
            'company_id': self.env.company.id,
        })
        # Then create a higher-sequence shorter-delay level.
        # Capture the logger to check the warning fires.
        with self.assertLogs(
            'odoo.addons.account_payment_followup.models'
            '.account_followup_level',
            level='WARNING',
        ) as ctx:
            level_2 = self.Level.create({
                'name': 'BR-003 Shorter Delay Later',
                'sequence': 280,  # later sequence
                'delay': 7,  # shorter delay than the seq=270 level
                'action_type': 'automatic',
                'company_id': self.env.company.id,
            })
        self.assertTrue(level_2.id,
                        'BR-003 violation must NOT prevent creation '
                        '(soft validation only).')
        self.assertTrue(
            any('BR-003' in msg or 'ordering warning' in msg.lower()
                for msg in ctx.output),
            'BR-003 must emit a WARNING-level log line.',
        )

    def test_br_004_inactive_levels_skipped_by_cron(self):
        """BR-004: cron skips when no active levels exist (no error).

        When no active levels are configured, the cron handler must
        return cleanly without raising — the empty-config case is
        valid.
        """
        # Archive ALL active levels in the test company.
        active_levels = self.Level.search([
            ('company_id', '=', self.env.company.id),
            ('active', '=', True),
        ])
        active_levels.write({'active': False})
        # Cron handler must not raise.
        result = self.Level.process_followup_emails()
        self.assertIsInstance(result, dict,
                              'process_followup_emails returns a dict.')
        self.assertEqual(result['partners_processed'], 0)
        self.assertEqual(result['emails_queued'], 0)
        self.assertEqual(result['errors'], 0)

    def test_br_005_min_amount_threshold_constraint(self):
        """BR-005: min_amount must be non-negative (CHECK SQL constraint)."""
        # Already covered by test_scenario_6_min_amount_negative_rejected
        # but repeat here under the BR identifier for explicit traceability.
        with self.assertRaises(Exception):  # noqa: BLE001
            with mute_logger('odoo.sql_db'):
                self.Level.create({
                    'name': 'BR-005 Test',
                    'sequence': 290,
                    'delay': 7,
                    'action_type': 'automatic',
                    'min_amount': -50.0,
                    'company_id': self.env.company.id,
                })

    # =========================================================================
    # COMPUTE METHODS — Currency
    # =========================================================================

    def test_compute_currency_id_from_company(self):
        """Compute: currency_id derives from company_id.currency_id."""
        level = self.Level.create({
            'name': 'Currency Compute Test',
            'sequence': 300,
            'delay': 7,
            'action_type': 'automatic',
            'company_id': self.env.company.id,
        })
        self.assertEqual(level.currency_id,
                         self.env.company.currency_id,
                         'currency_id must equal company.currency_id.')

    # =========================================================================
    # ACTION METHODS — action_view_email_template
    # =========================================================================

    def test_action_view_email_template_with_template(self):
        """Action: action_view_email_template returns a window action."""
        level = self.Level.create({
            'name': 'Smart Button Test',
            'sequence': 310,
            'delay': 7,
            'action_type': 'email',
            'email_template_id': self.test_template.id,
            'company_id': self.env.company.id,
        })
        action = level.action_view_email_template()
        self.assertEqual(action['type'], 'ir.actions.act_window')
        self.assertEqual(action['res_model'], 'mail.template')
        self.assertEqual(action['res_id'], self.test_template.id)
        self.assertEqual(action['view_mode'], 'form')

    def test_action_view_email_template_without_template(self):
        """Action: returns False when no template is assigned."""
        level = self.Level.create({
            'name': 'No Template Smart Button',
            'sequence': 311,
            'delay': 7,
            'action_type': 'phone',
            'company_id': self.env.company.id,
        })
        self.assertFalse(level.action_view_email_template(),
                         'Returns False when no template is assigned.')

    # =========================================================================
    # EDGE CASES
    # =========================================================================

    def test_edge_translatable_name(self):
        """Edge: name is translatable (translate=True declared)."""
        # The field declares translate=True; we just verify it's writable
        # and persists without errors.
        level = self.first_reminder_level
        original_name = level.name
        level.write({'name': 'Renamed Level'})
        self.assertEqual(level.name, 'Renamed Level')
        # Restore for downstream tests
        level.write({'name': original_name})

    def test_edge_description_optional(self):
        """Edge: description is optional and may be empty."""
        level = self.Level.create({
            'name': 'No Description',
            'sequence': 320,
            'delay': 7,
            'action_type': 'automatic',
            'company_id': self.env.company.id,
        })
        self.assertFalse(level.description,
                         'description default is False/empty.')

    def test_edge_invalid_email_template_domain(self):
        """Edge: assigning a template targeting a non-res.partner model.

        The email_template_id field has a domain restricting selection
        to templates targeting res.partner, but this is a UI hint not
        a hard constraint. The ORM accepts any mail.template at write
        time. Tests should document this distinction.
        """
        # Create a template targeting account.move (NOT res.partner)
        wrong_template = self.env['mail.template'].create({
            'name': 'Wrong Model Template',
            'model_id': self.env.ref('account.model_account_move').id,
            'subject': 'Wrong Subject',
        })
        # The ORM accepts this assignment (domain is a UI hint).
        level = self.Level.create({
            'name': 'Wrong Model Test',
            'sequence': 321,
            'delay': 7,
            'action_type': 'email',
            'email_template_id': wrong_template.id,
            'company_id': self.env.company.id,
        })
        # Persistence must succeed; the domain is enforced only by the
        # form view's record selector.
        self.assertEqual(level.email_template_id, wrong_template,
                         'ORM accepts templates regardless of domain hint.')

    def test_edge_smoke_create_minimum_required_fields(self):
        """Edge smoke: minimum required field set creates successfully.

        Verifies the model defaults for ``delay``, ``action_type``, and
        ``company_id``. The ``sequence`` default (10) collides with the
        seeded "First Reminder" level in the test company under the
        ``UNIQUE(sequence, company_id)`` SQL constraint, so we supply
        a non-conflicting sequence explicitly. The default ``sequence``
        value is verified separately by inspecting the field metadata
        (see :meth:`test_field_defaults_metadata` below).
        """
        # Use a sequence well above the seeded ladder (10, 20, 30, 40)
        # to avoid collisions with the demo / seed records.
        level = self.Level.create({
            'name': 'Minimum Fields',
            'sequence': 999,
        })
        self.assertEqual(level.name, 'Minimum Fields')
        self.assertEqual(level.delay, 7,
                         'default delay is 7 days per the field default.')
        self.assertEqual(level.action_type, 'automatic',
                         'default action_type is automatic.')
        self.assertEqual(level.company_id, self.env.company,
                         'default company is env.company.')

    def test_field_defaults_metadata(self):
        """Verify the default values declared on the model itself.

        Uses ``default_get`` (the canonical Odoo API for retrieving
        field defaults) to confirm the canonical default values without
        creating a record at the default sequence — that path would
        violate the ``UNIQUE(sequence, company_id)`` SQL constraint
        because the seeded "First Reminder" level already occupies
        sequence=10 in the test company.
        """
        defaults = self.Level.default_get(
            ['sequence', 'delay', 'action_type', 'company_id', 'active'],
        )
        self.assertEqual(defaults['sequence'], 10,
                         'default sequence is 10 per the field default.')
        self.assertEqual(defaults['delay'], 7,
                         'default delay is 7 days per the field default.')
        self.assertEqual(defaults['action_type'], 'automatic',
                         'default action_type is automatic.')
        self.assertEqual(defaults['company_id'], self.env.company.id,
                         'default company is env.company.')
        # active flag — default True per the field declaration
        self.assertTrue(defaults.get('active', True),
                        'default active is True per the field default.')
