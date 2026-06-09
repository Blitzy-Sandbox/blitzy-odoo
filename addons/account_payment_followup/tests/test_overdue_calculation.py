# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
PF-005 — Overdue Calculation: Phase-Plan Acceptance Test Suite
==============================================================

Verifies the aging-bucket and follow-up-level-assignment logic introduced
by the PF-005 model extensions in ``account_payment_followup`` against
all six BDD scenarios and six business rules (BR-001 through BR-006)
defined in ``tickets/stories/payment-followups/PF-005-overdue-calculation.md``.

Targets ≥80% line coverage on the four PF-005-owned files:

  * ``addons/account_payment_followup/models/res_partner.py`` —
    ``_inherit='res.partner'`` extension contributing per-partner aging
    bucket fields, total-overdue, max-days-overdue, follow-up level,
    and helper actions.
  * ``addons/account_payment_followup/models/account_move.py`` —
    ``_inherit='account.move'`` extension contributing
    ``days_overdue``, ``is_overdue``, ``aging_bucket``, ``is_disputed``,
    and the ``followup_history_ids`` reverse relation.
  * ``addons/account_payment_followup/models/account_move_line.py`` —
    ``_inherit='account.move.line'`` extension contributing
    ``days_overdue`` and ``aging_bucket`` on receivable lines.
  * ``addons/account_payment_followup/models/account_followup_line.py``
    — net-new ``account.followup.line`` denormalized aging summary.

Determinism
-----------
The class is decorated with ``@freeze_time(FROZEN_DATE)`` so every
``today``-based computation (including the ``flush_all()`` triggered
by Odoo's ``TransactionCase.setUp()`` before introducing a savepoint
— see ``odoo/tests/common.py:1157``) resolves against
``date(2024, 6, 30)``. Class-level decoration is mandatory — wrapping
only the test body would let setUp's pre-savepoint flush run with the
real wall-clock date, persisting wrong stored-compute values and
breaking every aging-related assertion. Individual tests that need to
override the frozen date can still nest ``with freeze_time(other):``
inside the method body.

Phase Plan (matches agent_prompt §"Phase Plan & Checklist")
-----------------------------------------------------------
- Phase 1 — Scenario 1: ``days_overdue`` calculation (5 tests)
- Phase 2 — Scenario 2: Follow-up level assignment (8 tests)
- Phase 3 — Scenario 3: Aging buckets (12 tests)
- Phase 4 — Scenario 4: Disputed invoices framework (1 test)
- Phase 5 — Scenario 5: Partial payments (2 tests)
- Phase 6 — Scenario 6: Recalculation triggers (4 tests)
- Phase 7 — BR-006 credit notes (1 test)
- Phase 8 — Performance & integration (3 tests)

Total: 36 test methods (35 ``test_*`` + ``setUpClass``).

Rules Compliance (AAP §0.7)
---------------------------
- R-01: No imports from sibling new modules
  (``account_asset_management``, ``account_budget_management``,
  ``account_deferred_revenue``).
- R-02: No imports from Odoo Enterprise modules
  (``account_followup``, ``account_accountant``, ``account_reports``).
- R-04: Targets ≥80% coverage on the four PF-005 files listed above
  via 35 deterministic test methods.
- R-07: No ``sudo()`` calls.
- R-09: Filename matches the agent prompt verbatim
  (``test_overdue_calculation.py``).
"""

import time
from datetime import date, timedelta

from freezegun import freeze_time

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tools import float_compare

from .common import AccountPaymentFollowupTestCommon

# The class-level ``@freeze_time(FROZEN_DATE)`` decorator is required
# (not optional) because Odoo's ``TransactionCase.setUp()`` calls
# ``env.flush_all()`` BEFORE the test body runs, which triggers pending
# stored-compute recomputations from ``setUpClass``. If freeze_time were
# only active inside the test body (e.g., via a ``with freeze_time(...):``
# wrapper), those flushed recomputes would fire with the real wall-clock
# date and persist wrong values in the database, causing every assertion
# that reads ``partner.max_days_overdue`` / ``partner.followup_level_id``
# / ``partner.aging_bucket_*`` to fail. The class-level decorator wraps
# each ``test_*`` method execution including ``setUp()`` so the
# pre-savepoint ``flush_all()`` runs under the frozen reference date,
# matching the proven pattern used in ``test_pf_005.py`` (line 79).
FROZEN_DATE = AccountPaymentFollowupTestCommon.FROZEN_DATE


@tagged('post_install', '-at_install')
@freeze_time(FROZEN_DATE)
class TestOverdueCalculation(AccountPaymentFollowupTestCommon):
    """PF-005 — Overdue Calculation.

    Maps to acceptance scenarios:
      - Scenario 1: Calculate Days Overdue
      - Scenario 2: Assign Customer Follow-up Level
      - Scenario 3: Calculate Aging Buckets (Current/1-30/31-60/61-90/90+)
      - Scenario 4: Exclude Disputed Invoices (framework only — actual
        dispute tracking is future scope)
      - Scenario 5: Handle Partial Payments (amount_residual)
      - Scenario 6: Recalculate on Invoice and Payment Changes

    And business rules:
      - BR-001: Days overdue calculated from date_maturity
      - BR-002: Only posted (state='posted') invoices
      - BR-003: Customer follow-up level based on most-overdue invoice
      - BR-004: Aging uses amount_residual (not amount_total)
      - BR-005: Disputed invoices tracked separately (framework)
      - BR-006: Credit notes reduce total but preserve bucket distribution
    """

    # =========================================================================
    # PHASE 1 — SCENARIO 1: Days Overdue Calculation
    # =========================================================================
    # Per PF-005 Scenario 1:
    #   Given an invoice has a due date and the invoice is not fully paid
    #   When the overdue calculation runs
    #   Then the number of days overdue is calculated as
    #        (current date - due date) for invoices past due date
    #   And invoices with due dates in the future are not marked as overdue
    #   And the days overdue value is zero or positive (never negative)
    # =========================================================================

    def test_days_overdue_positive_for_past_due_invoices(self):
        """Scenario 1: posted invoices past due report exact days_overdue.

        Iterates the six pre-built ``partner_overdue_Nd`` fixtures from
        :class:`AccountPaymentFollowupTestCommon` and asserts each
        partner's invoice ``days_overdue`` matches the day-offset baked
        into its fixture name (7 / 14 / 21 / 30 / 45 / 95).

        Verifies:
          * ``account.move._compute_days_overdue`` produces the exact
            integer day count ``today - invoice_date_due``.
          * Each invoice's ``is_overdue`` flag is True.
          * Each invoice's ``aging_bucket`` is a non-default bucket
            (i.e., not ``'current'``).
          * ``self.FROZEN_DATE`` is a proper ``datetime.date`` instance
            and ``fields.Date.context_today`` resolves to it under
            ``freeze_time`` (sanity check guarding against accidental
            removal of the freezegun decorator in subclasses).
        """
        with freeze_time(self.FROZEN_DATE):
            # Frame invariant: FROZEN_DATE must be a date and equal the
            # ORM's idea of "today" inside the freeze block. Without
            # this invariant, every downstream day-offset assertion is
            # meaningless. Uses both ``date`` (from ``datetime``) and
            # ``fields.Date.context_today`` to confirm cross-stack
            # alignment between Python and the Odoo ORM.
            self.assertIsInstance(
                self.FROZEN_DATE, date,
                "FROZEN_DATE must be a datetime.date instance.",
            )
            self.assertEqual(
                fields.Date.context_today(self.env['res.partner']),
                self.FROZEN_DATE,
                "fields.Date.context_today must return FROZEN_DATE under "
                "the @freeze_time context manager.",
            )
            # Build a (partner_fixture, expected_days, expected_bucket) table
            # so downstream assertions are tabular and easy to extend.
            cases = [
                (self.partner_overdue_7d, 7, 'bucket_1_30'),
                (self.partner_overdue_14d, 14, 'bucket_1_30'),
                (self.partner_overdue_21d, 21, 'bucket_1_30'),
                (self.partner_overdue_30d, 30, 'bucket_1_30'),
                (self.partner_overdue_45d, 45, 'bucket_31_60'),
                (self.partner_overdue_95d, 95, 'bucket_90_plus'),
            ]
            for partner, expected_days, expected_bucket in cases:
                # Force fresh compute by invalidating the cache. The
                # @api.depends chain ensures the compute runs again.
                partner.invalidate_recordset()
                # Each partner_overdue_Nd fixture has exactly one invoice
                # built by ``_create_overdue_invoice``; filter to the
                # posted out_invoice (defensive against fixture edits).
                invoices = partner.invoice_ids.filtered(
                    lambda m: m.move_type == 'out_invoice'
                    and m.state == 'posted',
                )
                self.assertEqual(
                    len(invoices), 1,
                    f"{partner.name}: expected exactly one posted invoice.",
                )
                invoice = invoices
                invoice.invalidate_recordset()
                self.assertEqual(
                    invoice.days_overdue, expected_days,
                    f"{partner.name}: days_overdue must equal "
                    f"{expected_days} (got {invoice.days_overdue}).",
                )
                self.assertTrue(
                    invoice.is_overdue,
                    f"{partner.name}: is_overdue must be True for past-due.",
                )
                self.assertEqual(
                    invoice.aging_bucket, expected_bucket,
                    f"{partner.name}: aging_bucket must be "
                    f"{expected_bucket} (got {invoice.aging_bucket}).",
                )

    def test_days_overdue_zero_for_current_invoices(self):
        """Scenario 1: invoices not yet past due report days_overdue=0.

        ``self.partner_current`` has a single posted invoice with
        ``invoice_date_due == FROZEN_DATE`` (i.e., due exactly today
        per finance convention "the due date is the last timely day").
        Expected behaviour:
          * ``invoice.days_overdue == 0``
          * ``invoice.is_overdue == False``
          * ``invoice.aging_bucket == 'current'``
        """
        with freeze_time(self.FROZEN_DATE):
            self.partner_current.invalidate_recordset()
            # Filter to posted out_invoice for the same defensive reasons
            # noted in test_days_overdue_positive_for_past_due_invoices.
            invoices = self.partner_current.invoice_ids.filtered(
                lambda m: m.move_type == 'out_invoice'
                and m.state == 'posted',
            )
            self.assertTrue(
                invoices,
                "partner_current must have at least one posted invoice.",
            )
            for invoice in invoices:
                invoice.invalidate_recordset()
                self.assertEqual(
                    invoice.days_overdue, 0,
                    "Current invoice (due today) must have days_overdue=0.",
                )
                self.assertFalse(
                    invoice.is_overdue,
                    "Current invoice must have is_overdue=False.",
                )
                self.assertEqual(
                    invoice.aging_bucket, 'current',
                    "Current invoice must have aging_bucket='current'.",
                )

    def test_days_overdue_zero_for_unposted_invoices(self):
        """BR-002: draft (unposted) invoices yield days_overdue=0.

        Creates a draft (``state='draft'``) invoice with a past-due
        ``invoice_date_due`` and asserts the compute method returns the
        default values (``days_overdue=0``, ``is_overdue=False``,
        ``aging_bucket='current'``) because BR-002 limits aging to
        legally-binding posted moves.
        """
        with freeze_time(self.FROZEN_DATE):
            partner = self.env['res.partner'].create({
                'name': 'Test Partner — Draft Past-Due',
                'customer_rank': 1,
                'property_payment_term_id': self.pay_terms_a.id,
                'email': 'draft_pastdue@test.com',
                'company_id': False,
            })
            # Build a 30-day past-due invoice but DON'T post it.
            invoice = self._create_overdue_invoice(
                partner=partner,
                invoice_date=self.FROZEN_DATE - timedelta(days=30),
                amount=999.0,
                post=False,
            )
            invoice.invalidate_recordset()
            self.assertEqual(
                invoice.state, 'draft',
                "Test invariant: invoice must be in draft state.",
            )
            self.assertEqual(
                invoice.days_overdue, 0,
                "BR-002: draft invoice must have days_overdue=0 even "
                "with a past-due date.",
            )
            self.assertFalse(
                invoice.is_overdue,
                "BR-002: draft invoice must have is_overdue=False.",
            )
            self.assertEqual(
                invoice.aging_bucket, 'current',
                "BR-002: draft invoice must have aging_bucket='current'.",
            )

    def test_days_overdue_zero_for_fully_paid_invoices(self):
        """BR-002: fully paid invoices yield days_overdue=0 and is_overdue=False.

        Posts a 30-day past-due invoice for 1000.00, registers a full
        payment of 1000.00, and asserts the compute method resets
        ``days_overdue`` and ``is_overdue`` because ``payment_state``
        transitions to ``'paid'`` (or ``'in_payment'``) which is
        excluded by the BR-002 domain filter.
        """
        with freeze_time(self.FROZEN_DATE):
            partner = self.env['res.partner'].create({
                'name': 'Test Partner — Fully Paid',
                'customer_rank': 1,
                'property_payment_term_id': self.pay_terms_a.id,
                'email': 'fullypaid@test.com',
                'company_id': False,
            })
            invoice = self._create_overdue_invoice(
                partner=partner,
                invoice_date=self.FROZEN_DATE - timedelta(days=30),
                amount=1000.0,
            )
            # Pre-state assertion: invoice is past-due and overdue.
            invoice.invalidate_recordset()
            self.assertEqual(invoice.days_overdue, 30)
            self.assertTrue(invoice.is_overdue)

            # Register full payment.
            self._register_payment(invoice, 1000.0)
            invoice.invalidate_recordset()
            # ``payment_state`` may end at 'paid' or 'in_payment' depending
            # on bank-journal reconciliation; either way the residual
            # is zero and the move is no longer counted as overdue.
            self.assertEqual(
                float_compare(
                    invoice.amount_residual, 0.0, precision_digits=2,
                ),
                0,
                "Residual must be zero after full payment.",
            )
            self.assertEqual(
                invoice.days_overdue, 0,
                "BR-002: fully paid invoice must have days_overdue=0.",
            )
            self.assertFalse(
                invoice.is_overdue,
                "BR-002: fully paid invoice must have is_overdue=False.",
            )
            self.assertEqual(
                invoice.aging_bucket, 'current',
                "BR-002: fully paid invoice must have "
                "aging_bucket='current'.",
            )

    def test_days_overdue_never_negative(self):
        """Scenario 1: invoices with future due dates report days_overdue=0.

        Per Scenario 1's "zero or positive (never negative)" guarantee,
        an invoice with a due date 10 days in the future must have:

          * ``days_overdue == 0`` (not -10)
          * ``is_overdue == False``
          * ``aging_bucket == 'current'``
        """
        with freeze_time(self.FROZEN_DATE):
            partner = self.env['res.partner'].create({
                'name': 'Test Partner — Future Due',
                'customer_rank': 1,
                'property_payment_term_id': self.pay_terms_a.id,
                'email': 'future@test.com',
                'company_id': False,
            })
            invoice = self._create_overdue_invoice(
                partner=partner,
                invoice_date=self.FROZEN_DATE + timedelta(days=10),
                amount=2500.0,
            )
            invoice.invalidate_recordset()
            self.assertEqual(
                invoice.days_overdue, 0,
                "Scenario 1: future-due invoice must have days_overdue=0 "
                "(never negative).",
            )
            self.assertFalse(
                invoice.is_overdue,
                "Scenario 1: future-due invoice must have is_overdue=False.",
            )
            self.assertEqual(
                invoice.aging_bucket, 'current',
                "Scenario 1: future-due invoice must be in 'current' bucket.",
            )

    # =========================================================================
    # PHASE 2 — SCENARIO 2: Follow-up Level Assignment
    # =========================================================================
    # Per PF-005 Scenario 2 + BR-003:
    #   Given follow-up levels are configured with day thresholds
    #     (Level 1: 7d, Level 2: 14d, Level 3: 21d, Level 4: 30d)
    #   When a customer has overdue invoices
    #   Then the customer is assigned to the follow-up level matching
    #     their most overdue invoice's days overdue
    #   And the customer's follow-up level is the highest applicable
    #     level based on all their overdue invoices
    #   And a customer with no overdue invoices is not assigned to any
    #     follow-up level
    # =========================================================================

    def test_level_assignment_based_on_max_days_overdue(self):
        """Scenario 2: 7-day overdue partner resolves to First Reminder.

        ``self.partner_overdue_7d`` has exactly one invoice 7 days past
        due. Per the seed level config (delays = 7 / 14 / 21 / 30), the
        applicable level is the highest with ``delay <= 7``, namely
        First Reminder (delay=7).
        """
        with freeze_time(self.FROZEN_DATE):
            self.partner_overdue_7d.invalidate_recordset(
                ['followup_level_id', 'max_days_overdue'],
            )
            self.assertEqual(
                self.partner_overdue_7d.max_days_overdue, 7,
                "Pre-condition: max_days_overdue must be 7.",
            )
            self.assertEqual(
                self.partner_overdue_7d.followup_level_id,
                self.first_reminder_level,
                "7-day overdue partner must resolve to First Reminder "
                "(delay=7).",
            )
            self.assertEqual(
                self.partner_overdue_7d.followup_level_id.name,
                'First Reminder',
            )

    def test_level_assignment_14d_second_reminder(self):
        """Scenario 2: 14-day overdue partner resolves to Second Reminder."""
        with freeze_time(self.FROZEN_DATE):
            self.partner_overdue_14d.invalidate_recordset(
                ['followup_level_id', 'max_days_overdue'],
            )
            self.assertEqual(self.partner_overdue_14d.max_days_overdue, 14)
            self.assertEqual(
                self.partner_overdue_14d.followup_level_id,
                self.second_reminder_level,
                "14-day overdue partner must resolve to Second Reminder.",
            )
            self.assertEqual(
                self.partner_overdue_14d.followup_level_id.name,
                'Second Reminder',
            )

    def test_level_assignment_21d_warning(self):
        """Scenario 2: 21-day overdue partner resolves to Warning level."""
        with freeze_time(self.FROZEN_DATE):
            self.partner_overdue_21d.invalidate_recordset(
                ['followup_level_id', 'max_days_overdue'],
            )
            self.assertEqual(self.partner_overdue_21d.max_days_overdue, 21)
            self.assertEqual(
                self.partner_overdue_21d.followup_level_id,
                self.warning_level,
                "21-day overdue partner must resolve to Warning (delay=21).",
            )
            self.assertEqual(
                self.partner_overdue_21d.followup_level_id.name,
                'Warning',
            )

    def test_level_assignment_30d_final_notice(self):
        """Scenario 2: 30-day overdue partner resolves to Final Notice."""
        with freeze_time(self.FROZEN_DATE):
            self.partner_overdue_30d.invalidate_recordset(
                ['followup_level_id', 'max_days_overdue'],
            )
            self.assertEqual(self.partner_overdue_30d.max_days_overdue, 30)
            self.assertEqual(
                self.partner_overdue_30d.followup_level_id,
                self.final_notice_level,
                "30-day overdue partner must resolve to Final Notice "
                "(delay=30).",
            )
            self.assertEqual(
                self.partner_overdue_30d.followup_level_id.name,
                'Final Notice',
            )

    def test_level_assignment_45d_still_final_notice(self):
        """Scenario 2: 45-day overdue partner stays at Final Notice.

        Per BR-003 ("highest applicable level based on most overdue
        invoice"), a partner whose worst invoice is 45 days overdue
        still falls under Final Notice (the largest configured delay
        is 30).
        """
        with freeze_time(self.FROZEN_DATE):
            self.partner_overdue_45d.invalidate_recordset(
                ['followup_level_id', 'max_days_overdue'],
            )
            self.assertEqual(self.partner_overdue_45d.max_days_overdue, 45)
            self.assertEqual(
                self.partner_overdue_45d.followup_level_id,
                self.final_notice_level,
                "45-day overdue partner must stay at Final Notice "
                "(delay=30 is still <= 45).",
            )

    def test_level_assignment_95d_still_final_notice(self):
        """Scenario 2: 95-day overdue partner stays at Final Notice.

        No configured level has delay > 30, so Final Notice is the
        highest applicable level even at 95 days past due.
        """
        with freeze_time(self.FROZEN_DATE):
            self.partner_overdue_95d.invalidate_recordset(
                ['followup_level_id', 'max_days_overdue'],
            )
            self.assertEqual(self.partner_overdue_95d.max_days_overdue, 95)
            self.assertEqual(
                self.partner_overdue_95d.followup_level_id,
                self.final_notice_level,
                "95-day overdue partner must stay at Final Notice "
                "(no higher level configured).",
            )

    def test_level_assignment_none_for_current_partner(self):
        """Scenario 2: partner with no overdue invoices has no level.

        ``self.partner_current`` has only a current invoice
        (``invoice_date_due == today``); since there are zero past-due
        days, ``followup_level_id`` resolves to False (no level).
        """
        with freeze_time(self.FROZEN_DATE):
            self.partner_current.invalidate_recordset(
                ['followup_level_id', 'max_days_overdue'],
            )
            self.assertEqual(
                self.partner_current.max_days_overdue, 0,
                "partner_current must have max_days_overdue=0.",
            )
            self.assertFalse(
                self.partner_current.followup_level_id,
                "Scenario 2: partner with no overdue invoices must have "
                "no follow-up level (followup_level_id=False).",
            )

    def test_level_assignment_highest_applicable_when_multiple_invoices(self):
        """BR-003: partner with mixed-age invoices uses worst overdue.

        Creates a partner with two invoices: one 14 days past due, one
        30 days past due. The applicable level must be Final Notice
        (worst case at 30 days, not Second Reminder which would apply
        only if the worst case were 14 days).
        """
        with freeze_time(self.FROZEN_DATE):
            partner = self.env['res.partner'].create({
                'name': 'Test Partner — Multi-invoice level',
                'customer_rank': 1,
                'property_payment_term_id': self.pay_terms_a.id,
                'email': 'multi_level@test.com',
                'company_id': False,
            })
            # Invoice 1: 14 days overdue.
            self._create_overdue_invoice(
                partner=partner,
                invoice_date=self.FROZEN_DATE - timedelta(days=14),
                amount=500.0,
            )
            # Invoice 2: 30 days overdue (the "worst" one).
            self._create_overdue_invoice(
                partner=partner,
                invoice_date=self.FROZEN_DATE - timedelta(days=30),
                amount=750.0,
            )
            partner.invalidate_recordset()
            self.assertEqual(
                partner.max_days_overdue, 30,
                "BR-003: max_days_overdue must reflect the WORST invoice "
                "(30, not 14).",
            )
            self.assertEqual(
                partner.followup_level_id,
                self.final_notice_level,
                "BR-003: level must be Final Notice (matches worst case at "
                "30 days, not Second Reminder).",
            )

    # =========================================================================
    # PHASE 3 — SCENARIO 3: Aging Buckets
    # =========================================================================
    # Per PF-005 Scenario 3:
    #   Given a customer has multiple overdue invoices with varying due
    #     dates
    #   When I view the customer's aging information
    #   Then I see the total overdue amount distributed across aging
    #     buckets:
    #       - Current: due date >= today
    #       - 1-30 days: 1 to 30 days past due (inclusive)
    #       - 31-60 days: 31 to 60 days past due (inclusive)
    #       - 61-90 days: 61 to 90 days past due (inclusive)
    #       - 90+ days: > 90 days past due
    #   And each bucket shows the sum of remaining unpaid amounts for
    #     invoices in that aging range
    #   And the total of all buckets equals the customer's total
    #     receivable balance
    # =========================================================================

    # --- Bucket boundary helpers --------------------------------------------
    # Each ``_assert_bucket_boundary`` test creates a fresh partner +
    # invoice with a precise day-offset due date and asserts that the
    # invoice's ``aging_bucket`` resolves to the expected bucket. The
    # partner is freshly created per test to avoid cross-test fixture
    # contamination of aggregate computations.

    def _create_partner_and_invoice_at_offset(
        self, days_past_due, amount=100.0, label_suffix='boundary',
    ):
        """Helper: create a partner + posted invoice at exact day-offset.

        :param days_past_due: Integer day offset relative to FROZEN_DATE.
            Positive values = past due; negative values = future due.
        :param amount: Invoice price_unit (default 100.0).
        :param label_suffix: Suffix used in the partner name and email
            for log readability when boundary tests fail.
        :return: Tuple ``(partner, invoice)``.
        """
        partner = self.env['res.partner'].create({
            'name': f'Test Partner — {label_suffix} d{days_past_due}',
            'customer_rank': 1,
            'property_payment_term_id': self.pay_terms_a.id,
            'email': f'b{days_past_due}_{label_suffix}@test.com',
            'company_id': False,
        })
        invoice = self._create_overdue_invoice(
            partner=partner,
            invoice_date=self.FROZEN_DATE - timedelta(days=days_past_due),
            amount=amount,
        )
        return partner, invoice

    def test_aging_buckets_exact_boundary_day_1(self):
        """Boundary: exactly 1 day overdue → bucket_1_30 (lower inclusive)."""
        with freeze_time(self.FROZEN_DATE):
            _, invoice = self._create_partner_and_invoice_at_offset(1)
            invoice.invalidate_recordset()
            self.assertEqual(invoice.days_overdue, 1)
            self.assertEqual(
                invoice.aging_bucket, 'bucket_1_30',
                "Day 1 overdue must map to 1-30 bucket (inclusive lower).",
            )

    def test_aging_buckets_exact_boundary_day_30(self):
        """Boundary: exactly 30 days overdue → bucket_1_30 (upper inclusive)."""
        with freeze_time(self.FROZEN_DATE):
            _, invoice = self._create_partner_and_invoice_at_offset(30)
            invoice.invalidate_recordset()
            self.assertEqual(invoice.days_overdue, 30)
            self.assertEqual(
                invoice.aging_bucket, 'bucket_1_30',
                "Day 30 overdue must map to 1-30 bucket (inclusive upper).",
            )

    def test_aging_buckets_exact_boundary_day_31(self):
        """Boundary: exactly 31 days overdue → bucket_31_60 (lower inclusive)."""
        with freeze_time(self.FROZEN_DATE):
            _, invoice = self._create_partner_and_invoice_at_offset(31)
            invoice.invalidate_recordset()
            self.assertEqual(invoice.days_overdue, 31)
            self.assertEqual(
                invoice.aging_bucket, 'bucket_31_60',
                "Day 31 overdue must map to 31-60 bucket (lower inclusive).",
            )

    def test_aging_buckets_exact_boundary_day_60(self):
        """Boundary: exactly 60 days overdue → bucket_31_60 (upper inclusive)."""
        with freeze_time(self.FROZEN_DATE):
            _, invoice = self._create_partner_and_invoice_at_offset(60)
            invoice.invalidate_recordset()
            self.assertEqual(invoice.days_overdue, 60)
            self.assertEqual(
                invoice.aging_bucket, 'bucket_31_60',
                "Day 60 overdue must map to 31-60 bucket (upper inclusive).",
            )

    def test_aging_buckets_exact_boundary_day_61(self):
        """Boundary: exactly 61 days overdue → bucket_61_90 (lower inclusive)."""
        with freeze_time(self.FROZEN_DATE):
            _, invoice = self._create_partner_and_invoice_at_offset(61)
            invoice.invalidate_recordset()
            self.assertEqual(invoice.days_overdue, 61)
            self.assertEqual(
                invoice.aging_bucket, 'bucket_61_90',
                "Day 61 overdue must map to 61-90 bucket (lower inclusive).",
            )

    def test_aging_buckets_exact_boundary_day_90(self):
        """Boundary: exactly 90 days overdue → bucket_61_90 (upper inclusive)."""
        with freeze_time(self.FROZEN_DATE):
            _, invoice = self._create_partner_and_invoice_at_offset(90)
            invoice.invalidate_recordset()
            self.assertEqual(invoice.days_overdue, 90)
            self.assertEqual(
                invoice.aging_bucket, 'bucket_61_90',
                "Day 90 overdue must map to 61-90 bucket (upper inclusive).",
            )

    def test_aging_buckets_exact_boundary_day_91(self):
        """Boundary: exactly 91 days overdue → bucket_90_plus (lower inclusive)."""
        with freeze_time(self.FROZEN_DATE):
            _, invoice = self._create_partner_and_invoice_at_offset(91)
            invoice.invalidate_recordset()
            self.assertEqual(invoice.days_overdue, 91)
            self.assertEqual(
                invoice.aging_bucket, 'bucket_90_plus',
                "Day 91 overdue must map to 90+ bucket (lower inclusive).",
            )

    def test_aging_buckets_current_bucket(self):
        """Scenario 3 boundary: invoice due today or in future → 'current'.

        Two cases verified:
          1. ``invoice_date_due == today`` (delta=0) → 'current'.
          2. ``invoice_date_due > today`` (delta=-10) → 'current'.
        Both must produce ``aging_bucket='current'`` and
        ``days_overdue=0`` per Scenario 1's "zero or positive" guarantee.
        """
        with freeze_time(self.FROZEN_DATE):
            # Case 1: due exactly today (delta = 0).
            _, inv_today = self._create_partner_and_invoice_at_offset(
                0, label_suffix='today',
            )
            inv_today.invalidate_recordset()
            self.assertEqual(inv_today.days_overdue, 0)
            self.assertEqual(
                inv_today.aging_bucket, 'current',
                "Invoice due today must map to 'current' bucket.",
            )
            # Case 2: due 10 days in the future (delta = -10).
            _, inv_future = self._create_partner_and_invoice_at_offset(
                -10, label_suffix='future',
            )
            inv_future.invalidate_recordset()
            self.assertEqual(inv_future.days_overdue, 0)
            self.assertEqual(
                inv_future.aging_bucket, 'current',
                "Future-due invoice must map to 'current' bucket.",
            )

    def test_partner_bucket_amounts_sum_correctly(self):
        """Scenario 3: partner aging buckets sum correctly with mixed aging.

        Two invariants verified on ``self.partner_mixed_aging``:

          1. ``total_overdue == sum(aging_bucket_1_30, _31_60, _61_90,
             _90_plus)`` — the "total overdue" specifically EXCLUDES the
             ``current`` bucket per the agent_prompt's Key Implementation
             Insight #1 ("CRITICAL: total_overdue on res.partner EXCLUDES
             the current bucket").
          2. ``total_overdue + aging_bucket_current`` matches the sum of
             ``amount_residual`` across the partner's open receivable
             invoices, demonstrating internal consistency between the
             per-line aggregation and the partner-level computed fields.

        Fixture layout for ``partner_mixed_aging`` (from common.py):
          - inv_mixed_current  → +5d (current bucket), residual 100.00
          - inv_mixed_15d      → -15d (1-30), residual 200.00
          - inv_mixed_45d      → -45d (31-60), residual 300.00
          - inv_mixed_75d      → -75d (61-90), residual 400.00
          - inv_mixed_100d     → -100d (90+), residual 500.00
        """
        with freeze_time(self.FROZEN_DATE):
            partner = self.partner_mixed_aging
            partner.invalidate_recordset()

            # Sum the overdue buckets (excluding 'current') and assert
            # equality to total_overdue with monetary precision.
            overdue_sum = (
                partner.aging_bucket_1_30
                + partner.aging_bucket_31_60
                + partner.aging_bucket_61_90
                + partner.aging_bucket_90_plus
            )
            self.assertEqual(
                float_compare(
                    partner.total_overdue, overdue_sum, precision_digits=2,
                ),
                0,
                "total_overdue must equal sum of the four overdue buckets "
                "(EXCLUDING current).",
            )

            # The fixture totals: 200 + 300 + 400 + 500 = 1400 overdue,
            # plus 100 current = 1500 total receivable.
            self.assertEqual(
                float_compare(
                    partner.total_overdue, 1400.0, precision_digits=2,
                ),
                0,
                "Expected fixture-derived total_overdue == 1400.00.",
            )
            self.assertEqual(
                float_compare(
                    partner.aging_bucket_current, 100.0, precision_digits=2,
                ),
                0,
                "Expected fixture-derived aging_bucket_current == 100.00.",
            )

            # Also verify equality with sum of amount_residual on the
            # partner's open receivable invoices (cross-check between the
            # per-invoice totals and the partner-level aggregate).
            invoices = partner.invoice_ids.filtered(
                lambda m: m.move_type in ('out_invoice', 'out_refund')
                and m.state == 'posted'
                and m.payment_state in ('not_paid', 'partial', 'in_payment'),
            )
            invoice_residual_sum = sum(invoices.mapped('amount_residual'))
            full_bucket_sum = overdue_sum + partner.aging_bucket_current
            self.assertEqual(
                float_compare(
                    full_bucket_sum,
                    invoice_residual_sum,
                    precision_digits=2,
                ),
                0,
                "Sum of all 5 buckets must equal sum of invoice residuals "
                f"(buckets={full_bucket_sum}, residuals="
                f"{invoice_residual_sum}).",
            )

    def test_aging_buckets_only_classify_receivables(self):
        """Scenario 3 + BR-002: payable invoices (in_invoice) excluded.

        Builds two invoices on the same fresh partner:

          * One ``out_invoice`` (receivable) — 30 days past due,
            amount 1000.00.
          * One ``in_invoice`` (payable / vendor bill) — 30 days past
            due, amount 500.00.

        Verifies that:
          1. The receivable invoice contributes to the partner's
             aging_bucket_1_30 and total_overdue.
          2. The payable invoice does NOT contribute (move_type filter
             ``[('move_type', 'in', ('out_invoice', 'out_refund'))]``).
          3. The payable invoice's own ``aging_bucket`` defaults to
             ``'current'`` because it's not a customer move.
        """
        with freeze_time(self.FROZEN_DATE):
            partner = self.env['res.partner'].create({
                'name': 'Test Partner — AR/AP isolation',
                'customer_rank': 1,
                'supplier_rank': 1,
                'property_payment_term_id': self.pay_terms_a.id,
                'property_supplier_payment_term_id': self.pay_terms_a.id,
                'email': 'arap_isolation@test.com',
                'company_id': False,
            })
            # Customer invoice (receivable) — should be classified.
            ar_invoice = self._create_overdue_invoice(
                partner=partner,
                invoice_date=self.FROZEN_DATE - timedelta(days=30),
                amount=1000.0,
                move_type='out_invoice',
            )
            # Vendor bill (payable) — should be ignored.
            ap_invoice = self._create_overdue_invoice(
                partner=partner,
                invoice_date=self.FROZEN_DATE - timedelta(days=30),
                amount=500.0,
                move_type='in_invoice',
            )

            partner.invalidate_recordset()
            ar_invoice.invalidate_recordset()
            ap_invoice.invalidate_recordset()

            # Receivable invoice contributes to the partner's overdue.
            self.assertEqual(ar_invoice.aging_bucket, 'bucket_1_30')
            self.assertEqual(
                float_compare(
                    partner.aging_bucket_1_30, 1000.0, precision_digits=2,
                ),
                0,
                "Only the AR (out_invoice) must contribute (1000.00).",
            )
            # Payable invoice is NOT counted; its aging_bucket defaults
            # to 'current' since the compute method skips non-customer moves.
            self.assertEqual(
                ap_invoice.aging_bucket, 'current',
                "Vendor bill (in_invoice) must default to 'current' bucket.",
            )
            self.assertEqual(
                ap_invoice.days_overdue, 0,
                "Vendor bill must have days_overdue=0 (excluded by "
                "move_type filter).",
            )
            # Total overdue equals only the AR invoice (1000.00),
            # not 1500 (1000 AR + 500 AP).
            self.assertEqual(
                float_compare(
                    partner.total_overdue, 1000.0, precision_digits=2,
                ),
                0,
                "total_overdue must reflect ONLY the receivable invoice.",
            )

    def test_aging_buckets_only_posted_moves(self):
        """BR-002: draft customer invoices default to 'current' bucket.

        Verifies the draft (``state='draft'``) filter on the per-move
        compute: a customer invoice that is past-due in calendar terms
        but still in draft state must have ``aging_bucket='current'``
        (the default) and ``days_overdue=0``.
        """
        with freeze_time(self.FROZEN_DATE):
            partner = self.env['res.partner'].create({
                'name': 'Test Partner — Draft AR',
                'customer_rank': 1,
                'property_payment_term_id': self.pay_terms_a.id,
                'email': 'draft_ar@test.com',
                'company_id': False,
            })
            invoice = self._create_overdue_invoice(
                partner=partner,
                invoice_date=self.FROZEN_DATE - timedelta(days=45),
                amount=2200.0,
                post=False,
            )
            invoice.invalidate_recordset()
            self.assertEqual(invoice.state, 'draft')
            self.assertEqual(
                invoice.aging_bucket, 'current',
                "BR-002: draft AR must default to 'current' bucket.",
            )
            self.assertEqual(
                invoice.days_overdue, 0,
                "BR-002: draft AR must have days_overdue=0.",
            )
            # Partner aggregates also exclude draft moves.
            partner.invalidate_recordset()
            self.assertEqual(
                float_compare(
                    partner.total_overdue, 0.0, precision_digits=2,
                ),
                0,
                "BR-002: partner with only draft past-due AR must have "
                "total_overdue=0.",
            )

    # =========================================================================
    # PHASE 4 — SCENARIO 4: Disputed Invoices (Framework)
    # =========================================================================
    # Per PF-005 Scenario 4 + BR-005:
    #   The module DEFINES a mechanism for marking invoices as disputed
    #   (the ``is_disputed`` Boolean field on account.move) but the
    #   PF-005 partner aging compute does NOT exclude disputed invoices
    #   from the per-partner aging totals. Instead, disputed invoices
    #   appear in aging reports with a dispute indicator (a dispute-aware
    #   filter is layered on top by PF-002 cron and PF-003 reports).
    # =========================================================================

    def test_disputed_invoice_framework_exists(self):
        """Scenario 4: ``is_disputed`` field exists and behaves correctly.

        Asserts:
          1. The ``is_disputed`` field exists on ``account.move`` (added
             by ``account_payment_followup`` per BR-005).
          2. Field is Boolean and indexed (for fast PF-002/PF-003 filters).
          3. Default value is False.
          4. Setting ``is_disputed=True`` does not break aging compute.
          5. Per Scenario 4's "the disputed invoice still appears in
             aging reports with a dispute indicator", the disputed
             invoice continues to contribute to the partner's aging
             totals — only downstream report / cron logic filters it.

        If, in a future iteration, the ``is_disputed`` field is removed
        or its semantics change, this test highlights the regression.
        """
        with freeze_time(self.FROZEN_DATE):
            AccountMove = self.env['account.move']
            # Field existence check.
            self.assertIn(
                'is_disputed', AccountMove._fields,
                "PF-005 BR-005: ``is_disputed`` field must exist on "
                "account.move.",
            )
            field = AccountMove._fields['is_disputed']
            self.assertEqual(
                field.type, 'boolean',
                "is_disputed must be a Boolean field.",
            )
            self.assertTrue(
                getattr(field, 'index', None),
                "is_disputed must be indexed for fast filtering by "
                "downstream PF-002/PF-003 components.",
            )

            # Build a 30-day past-due invoice via direct ORM create
            # (bypassing the helper) so this test exercises the
            # ``Command.clear()`` ORM operator on ``invoice_line_ids``.
            # Demonstrates that PF-005 aging compute runs identically
            # regardless of how the invoice was authored — through the
            # standard helper or via raw ``Command.*`` operations.
            partner = self.env['res.partner'].create({
                'name': 'Test Partner — Disputed Framework',
                'customer_rank': 1,
                'property_payment_term_id': self.pay_terms_a.id,
                'email': 'disputed@test.com',
                'company_id': False,
            })
            invoice_date = self.FROZEN_DATE - timedelta(days=30)
            invoice = self.env['account.move'].create({
                'move_type': 'out_invoice',
                'partner_id': partner.id,
                'invoice_date': invoice_date,
                'date': invoice_date,
                'invoice_payment_term_id': self.pay_terms_a.id,
                'invoice_line_ids': [
                    Command.create({
                        'name': 'Disputed framework test line',
                        'price_unit': 777.0,
                        'quantity': 1.0,
                        # Command.clear() resets tax_ids so the invoice
                        # total equals the price_unit exactly. Mirrors
                        # the convention used by ``_create_overdue_invoice``
                        # but with explicit Command-operator usage.
                        'tax_ids': [Command.clear()],
                    }),
                ],
            })
            invoice.action_post()
            self.assertFalse(
                invoice.is_disputed,
                "is_disputed must default to False.",
            )
            # Setting True must not raise.
            invoice.is_disputed = True
            self.assertTrue(invoice.is_disputed)

            # The PF-005 aging compute does NOT filter on is_disputed
            # — Scenario 4 requires disputed invoices to still appear in
            # aging reports. Verify the partner aggregate still includes
            # the disputed amount.
            partner.invalidate_recordset()
            self.assertEqual(
                float_compare(
                    partner.aging_bucket_1_30, 777.0, precision_digits=2,
                ),
                0,
                "Disputed invoice must still appear in aging buckets per "
                "Scenario 4.",
            )

    # =========================================================================
    # PHASE 5 — SCENARIO 5: Partial Payments
    # =========================================================================
    # Per PF-005 Scenario 5 + BR-004:
    #   Given an invoice has partial payments applied
    #   When the overdue calculation runs
    #   Then only the remaining unpaid amount (amount_residual) is
    #     considered overdue
    #   And the original invoice total is not used for aging calculations
    #   And invoices that are fully paid (amount_residual = 0) are
    #     excluded from overdue calculations
    # =========================================================================

    def test_aging_uses_amount_residual_not_total(self):
        """BR-004: aging classification uses amount_residual, not amount_total.

        Builds a 1000.00 invoice 45 days past due (bucket 31-60).
        Registers a 400.00 partial payment, leaving residual = 600.00.
        Verifies:
          * ``invoice.amount_residual == 600.00``
          * Partner's ``aging_bucket_31_60`` reflects 600.00, not 1000.00.
          * Partner's ``total_overdue`` reflects 600.00.
        """
        with freeze_time(self.FROZEN_DATE):
            partner = self.env['res.partner'].create({
                'name': 'Test Partner — Partial Payment',
                'customer_rank': 1,
                'property_payment_term_id': self.pay_terms_a.id,
                'email': 'partial_payment@test.com',
                'company_id': False,
            })
            invoice = self._create_overdue_invoice(
                partner=partner,
                invoice_date=self.FROZEN_DATE - timedelta(days=45),
                amount=1000.0,
            )
            # Pre-payment: total_overdue == 1000.00.
            partner.invalidate_recordset()
            self.assertEqual(
                float_compare(
                    partner.total_overdue, 1000.0, precision_digits=2,
                ),
                0,
            )

            # Register 400.00 partial payment.
            self._register_payment(invoice, 400.0)
            invoice.invalidate_recordset()
            partner.invalidate_recordset()

            # Residual decreased to 600.00.
            self.assertEqual(
                float_compare(
                    invoice.amount_residual, 600.0, precision_digits=2,
                ),
                0,
                "BR-004: residual must reduce by partial payment amount.",
            )
            # Aging bucket 31-60 reflects 600 (residual), not 1000 (total).
            self.assertEqual(
                float_compare(
                    partner.aging_bucket_31_60, 600.0, precision_digits=2,
                ),
                0,
                "BR-004: aging_bucket_31_60 must reflect residual, not total.",
            )
            self.assertEqual(
                float_compare(
                    partner.total_overdue, 600.0, precision_digits=2,
                ),
                0,
                "BR-004: total_overdue must reflect residual (600), not "
                "original total (1000).",
            )

    def test_fully_paid_invoices_excluded_from_aging(self):
        """Scenario 5: fully paid invoices excluded from aging.

        Builds a 600.00 invoice 45 days past due, registers full
        payment, asserts:
          * ``invoice.payment_state in ('paid', 'in_payment')``
            (transition depends on bank journal reconciliation).
          * ``invoice.aging_bucket == 'current'`` (no longer overdue).
          * Partner's ``aging_bucket_31_60 == 0.0``.
          * Partner's ``total_overdue == 0.0``.
        """
        with freeze_time(self.FROZEN_DATE):
            partner = self.env['res.partner'].create({
                'name': 'Test Partner — Fully Paid Excluded',
                'customer_rank': 1,
                'property_payment_term_id': self.pay_terms_a.id,
                'email': 'paid_excluded@test.com',
                'company_id': False,
            })
            invoice = self._create_overdue_invoice(
                partner=partner,
                invoice_date=self.FROZEN_DATE - timedelta(days=45),
                amount=600.0,
            )
            partner.invalidate_recordset()
            self.assertEqual(
                float_compare(
                    partner.aging_bucket_31_60, 600.0, precision_digits=2,
                ),
                0,
                "Pre-payment: bucket 31-60 must be 600.00.",
            )

            # Full payment.
            self._register_payment(invoice, 600.0)
            invoice.invalidate_recordset()
            partner.invalidate_recordset()

            # Either 'paid' (cleared) or 'in_payment' (pending bank
            # reconciliation) is acceptable; both have residual==0.
            self.assertIn(
                invoice.payment_state, ('paid', 'in_payment'),
                "After full payment, payment_state must be 'paid' or "
                "'in_payment'.",
            )
            self.assertEqual(
                float_compare(
                    invoice.amount_residual, 0.0, precision_digits=2,
                ),
                0,
                "Fully paid invoice must have residual=0.",
            )
            self.assertEqual(
                invoice.aging_bucket, 'current',
                "Fully paid invoice must reset aging_bucket to 'current'.",
            )
            self.assertEqual(
                float_compare(
                    partner.aging_bucket_31_60, 0.0, precision_digits=2,
                ),
                0,
                "Bucket 31-60 must be empty after full payment.",
            )
            self.assertEqual(
                float_compare(
                    partner.total_overdue, 0.0, precision_digits=2,
                ),
                0,
                "total_overdue must be 0 after full payment.",
            )

    # =========================================================================
    # PHASE 6 — SCENARIO 6: Recalculation Triggers
    # =========================================================================
    # Per PF-005 Scenario 6:
    #   The partner's overdue status and follow-up level recalculate
    #   automatically when:
    #     - A payment is recorded
    #     - An invoice is modified (due date changed, amount adjusted,
    #       cancelled)
    #     - A new overdue invoice is posted
    # Triggered by the @api.depends declaration covering invoice_ids
    # transitions on payment_state, amount_residual, invoice_date_due,
    # state, and move_type.
    # =========================================================================

    def test_recalculation_on_payment(self):
        """Scenario 6: full payment removes the partner's follow-up level.

        Uses ``self.partner_overdue_14d`` (level Second Reminder).
        Registers full payment, asserts ``partner.followup_level_id``
        becomes False because no overdue invoices remain.
        """
        with freeze_time(self.FROZEN_DATE):
            partner = self.partner_overdue_14d
            partner.invalidate_recordset()
            # Pre-state: level is Second Reminder.
            self.assertEqual(
                partner.followup_level_id, self.second_reminder_level,
                "Pre-condition: partner must be at Second Reminder.",
            )
            # Find the partner's overdue invoice and register full payment.
            invoice = partner.invoice_ids.filtered(
                lambda m: m.move_type == 'out_invoice'
                and m.state == 'posted',
            )
            self.assertEqual(len(invoice), 1)
            self._register_payment(invoice, invoice.amount_residual)
            partner.invalidate_recordset()
            # Post-state: no level (no overdue invoices).
            self.assertFalse(
                partner.followup_level_id,
                "Scenario 6: payment must reset followup_level_id to False.",
            )

    def test_recalculation_on_invoice_posting(self):
        """Scenario 6: posting a new past-due invoice assigns a level.

        Uses ``self.partner_current`` (no overdue invoices, no level).
        Posts a new 20-day past-due invoice; asserts the partner now has
        a Second Reminder level (delay=14, since 14 <= 20 < 21=Warning).
        """
        with freeze_time(self.FROZEN_DATE):
            partner = self.partner_current
            partner.invalidate_recordset()
            self.assertFalse(
                partner.followup_level_id,
                "Pre-condition: partner_current must have no level.",
            )
            # Post a new past-due invoice (20 days overdue).
            self._create_overdue_invoice(
                partner=partner,
                invoice_date=self.FROZEN_DATE - timedelta(days=20),
                amount=2200.0,
            )
            partner.invalidate_recordset()
            # 20 days overdue: highest applicable level with delay <= 20
            # is Second Reminder (delay=14).
            self.assertEqual(
                partner.followup_level_id, self.second_reminder_level,
                "Scenario 6: new posted invoice (20d overdue) must "
                "advance level to Second Reminder.",
            )
            self.assertEqual(partner.max_days_overdue, 20)

    def test_recalculation_on_invoice_cancellation(self):
        """Scenario 6: cancelling the only invoice clears the level.

        Builds a partner with one 30-day past-due invoice. Verifies
        the level is Final Notice. Cancels the invoice
        (``button_cancel()``); asserts the level is cleared.
        """
        with freeze_time(self.FROZEN_DATE):
            partner = self.env['res.partner'].create({
                'name': 'Test Partner — Cancel Recalc',
                'customer_rank': 1,
                'property_payment_term_id': self.pay_terms_a.id,
                'email': 'cancel_recalc@test.com',
                'company_id': False,
            })
            invoice = self._create_overdue_invoice(
                partner=partner,
                invoice_date=self.FROZEN_DATE - timedelta(days=30),
                amount=4000.0,
            )
            partner.invalidate_recordset()
            self.assertEqual(
                partner.followup_level_id, self.final_notice_level,
                "Pre-condition: partner must be at Final Notice.",
            )
            # Cancel the invoice.
            invoice.button_cancel()
            partner.invalidate_recordset()
            self.assertEqual(invoice.state, 'cancel')
            self.assertFalse(
                partner.followup_level_id,
                "Scenario 6: cancellation must reset followup_level_id.",
            )

    def test_recalculation_on_due_date_change(self):
        """Scenario 6: pushing due date to future clears the level.

        Builds a partner with a 14-day past-due invoice. Verifies the
        level is Second Reminder. Resets the invoice to draft, pushes
        ``invoice_date`` (and therefore ``invoice_date_due`` via the
        Immediate payment term) 10 days into the future, posts again.
        Asserts ``partner.followup_level_id`` becomes False.

        Implementation note: the Odoo ``account.move._compute_invoice_date_due``
        method derives ``invoice_date_due`` from ``needed_terms`` (the
        payment-term date_maturity). With the Immediate Payment term
        (``pay_terms_a``), ``date_maturity == invoice_date`` so writing
        ``invoice_date_due`` directly would be overwritten on post. We
        therefore update ``invoice_date`` (and the line's
        ``date_maturity`` for safety), which causes the compute to
        produce the desired future ``invoice_date_due`` on re-post.
        """
        partner = self.env['res.partner'].create({
            'name': 'Test Partner — Due Date Recalc',
            'customer_rank': 1,
            'property_payment_term_id': self.pay_terms_a.id,
            'email': 'duedate_recalc@test.com',
            'company_id': False,
        })
        invoice = self._create_overdue_invoice(
            partner=partner,
            invoice_date=self.FROZEN_DATE - timedelta(days=14),
            amount=1800.0,
        )
        partner.invalidate_recordset()
        self.assertEqual(
            partner.followup_level_id, self.second_reminder_level,
            "Pre-condition: partner must be at Second Reminder.",
        )
        # Reset to draft, push the invoice date 10 days into the future
        # so the Immediate-payment-term-driven recompute of
        # ``invoice_date_due`` produces a future due date, then re-post.
        invoice.button_draft()
        future_date = self.FROZEN_DATE + timedelta(days=10)
        invoice.write({
            'invoice_date': future_date,
            'invoice_date_due': future_date,
        })
        invoice.action_post()
        partner.invalidate_recordset()
        invoice.invalidate_recordset()
        # Now the invoice is future-due, so partner has no overdue.
        self.assertEqual(
            invoice.invoice_date_due, future_date,
            "Sanity: invoice_date_due must be future-dated after re-post.",
        )
        self.assertEqual(invoice.days_overdue, 0)
        self.assertFalse(
            partner.followup_level_id,
            "Scenario 6: due-date push must reset followup_level_id.",
        )

    # =========================================================================
    # PHASE 7 — BR-006 CREDIT NOTES
    # =========================================================================
    # Per PF-005 BR-006:
    #   Credit notes (out_refund) reduce the partner's total receivable
    #   exposure but do not clear specific invoice aging buckets.
    #   The implementation aggregates ``amount_residual`` from the
    #   underlying receivable lines via _read_group; for an out_refund
    #   the residual on the receivable line is signed negatively so it
    #   nets the partner's bucket totals.
    # =========================================================================

    def test_credit_note_reduces_total_overdue(self):
        """BR-006: credit notes net the partner's total via signed residual.

        Scenario:
          * Build a partner with one 45-day past-due invoice for 2000.00
            (placing it in bucket 31-60).
          * Build a 45-day past-due credit note (``out_refund``) for
            500.00 on the same partner.

        Expected outcome (per BR-006 + the implementation's _read_group
        sum on amount_residual):
          * The partner's ``aging_bucket_31_60`` reflects the netted
            amount: 2000 - 500 = 1500.
          * The partner's ``total_overdue`` reflects the netted amount:
            1500.

        This documents the module's actual behaviour: credit notes
        contribute a NEGATIVE signed amount_residual to the same
        bucket as the original invoice (they "net" within the bucket
        rather than appearing in a separate negative bucket).
        """
        with freeze_time(self.FROZEN_DATE):
            partner = self.env['res.partner'].create({
                'name': 'Test Partner — Credit Note Net',
                'customer_rank': 1,
                'property_payment_term_id': self.pay_terms_a.id,
                'email': 'credit_note@test.com',
                'company_id': False,
            })
            # Posted invoice for 2000 (45 days overdue).
            invoice = self._create_overdue_invoice(
                partner=partner,
                invoice_date=self.FROZEN_DATE - timedelta(days=45),
                amount=2000.0,
            )
            partner.invalidate_recordset()
            # Pre-credit-note: bucket 31-60 == 2000.00.
            self.assertEqual(
                float_compare(
                    partner.aging_bucket_31_60, 2000.0, precision_digits=2,
                ),
                0,
                "Pre-credit-note: bucket 31-60 must be 2000.00.",
            )

            # Posted credit note for 500 (45 days overdue, same bucket).
            credit_note = self._create_overdue_credit_note(
                partner=partner,
                invoice_date=self.FROZEN_DATE - timedelta(days=45),
                amount=500.0,
            )
            self.assertEqual(
                credit_note.move_type, 'out_refund',
                "Helper must produce an out_refund credit note.",
            )
            partner.invalidate_recordset()
            invoice.invalidate_recordset()

            # The credit note's receivable line has signed residual
            # (-500) so the bucket nets to 1500.
            self.assertEqual(
                float_compare(
                    partner.aging_bucket_31_60, 1500.0, precision_digits=2,
                ),
                0,
                "BR-006: credit note must net within bucket 31-60 to "
                "1500.00 (2000 - 500).",
            )
            # total_overdue mirrors the netted bucket.
            self.assertEqual(
                float_compare(
                    partner.total_overdue, 1500.0, precision_digits=2,
                ),
                0,
                "BR-006: total_overdue must reflect netted exposure "
                "(1500 = 2000 - 500).",
            )

    # =========================================================================
    # PHASE 8 — PERFORMANCE & INTEGRATION
    # =========================================================================
    # Per PF-005 §4.3 + BR-004 performance constraint:
    #   - Aging compute MUST use a single _read_group aggregation, not
    #     N+1 per-invoice queries.
    #   - Performance target: <5s for 10,000 invoices (CI-friendly
    #     scaled-down: <1s for 100 invoices across 10 partners).
    #   - The denormalized ``account.followup.line`` aggregate table
    #     MUST stay consistent with the live partner-level computed
    #     fields after ``_cron_refresh_all`` runs.
    # =========================================================================

    def test_read_group_used_for_aging_computation(self):
        """Performance: aging compute uses single _read_group, not N+1.

        Builds a partner with 30 invoices spanning multiple buckets.
        Forces the ORM to flush all writes, then captures
        ``self.env.cr.sql_log_count`` before and after reading the
        partner's aging fields.

        Asserts the query-count delta is bounded (well under 50) —
        demonstrating that the implementation does NOT scale linearly
        with invoice count. An N+1 pattern with 30 invoices would emit
        at least 30 queries; the single-_read_group approach emits
        roughly one _read_group + a small constant for stored-field
        writes.
        """
        with freeze_time(self.FROZEN_DATE):
            partner = self.env['res.partner'].create({
                'name': 'Test Partner — _read_group Verification',
                'customer_rank': 1,
                'property_payment_term_id': self.pay_terms_a.id,
                'email': 'readgroup@test.com',
                'company_id': False,
            })
            # 30 invoices across the four overdue buckets and current.
            for i in range(30):
                self._create_overdue_invoice(
                    partner=partner,
                    invoice_date=self.FROZEN_DATE - timedelta(days=1 + i),
                    amount=10.0,
                )

            # Flush so query counter only captures the compute pass below.
            partner.invalidate_recordset()
            self.env.flush_all()
            self.env.cr.flush()

            count_before = self.env.cr.sql_log_count
            # Read all aging fields → triggers compute.
            _ = (
                partner.total_overdue,
                partner.aging_bucket_current,
                partner.aging_bucket_1_30,
                partner.aging_bucket_31_60,
                partner.aging_bucket_61_90,
                partner.aging_bucket_90_plus,
                partner.max_days_overdue,
                partner.has_overdue_invoices,
            )
            self.env.flush_all()
            count_after = self.env.cr.sql_log_count
            delta = count_after - count_before

            # 50 query ceiling: a true N+1 pattern with 30 invoices
            # would exceed this; the single _read_group implementation
            # stays well under (typically 5-15 queries).
            self.assertLess(
                delta, 50,
                f"Aging compute used {delta} queries for 30 invoices — "
                "looks like an N+1 pattern (expected single _read_group).",
            )

    def test_aging_performance_100_invoices(self):
        """Performance: 100 invoices across 10 partners < 1 second.

        Scaled-down version of PF-005's "<5s for 10,000 invoices"
        target. Creates 100 invoices distributed across 10 partners,
        invalidates the cache, then times reading the aging fields for
        all 10 partners using ``time.monotonic()``.

        ``time.monotonic()`` is preferred over ``time.time()`` because
        ``freezegun`` does NOT freeze the monotonic clock — meaning
        elapsed wall-clock time for the timed section is measured
        accurately even though the test body runs under
        ``with freeze_time(...)``.
        """
        with freeze_time(self.FROZEN_DATE):
            # Build 10 partners.
            partners = self.env['res.partner']
            for i in range(10):
                partners |= self.env['res.partner'].create({
                    'name': f'Test Partner — Perf {i}',
                    'customer_rank': 1,
                    'property_payment_term_id': self.pay_terms_a.id,
                    'email': f'perf{i}@test.com',
                    'company_id': False,
                })

            # 100 invoices distributed: 10 per partner, varying days.
            for i, partner in enumerate(partners):
                for j in range(10):
                    days = 1 + (i * 10) + j  # 1..100
                    self._create_overdue_invoice(
                        partner=partner,
                        invoice_date=(
                            self.FROZEN_DATE - timedelta(days=days)
                        ),
                        amount=50.0,
                    )

            # Flush and invalidate so the timer captures compute work.
            partners.invalidate_recordset()
            self.env.flush_all()
            self.env.cr.flush()

            # Time the aging read across all 10 partners.
            t0 = time.monotonic()
            _ = partners.mapped('total_overdue')
            _ = partners.mapped('aging_bucket_current')
            _ = partners.mapped('aging_bucket_1_30')
            _ = partners.mapped('aging_bucket_31_60')
            _ = partners.mapped('aging_bucket_61_90')
            _ = partners.mapped('aging_bucket_90_plus')
            _ = partners.mapped('max_days_overdue')
            self.env.flush_all()
            t1 = time.monotonic()
            elapsed = t1 - t0

            # CI-friendly bound: 1 second is generous for 100 invoices
            # on standard CI hardware. Real production targets <5s for
            # 10k invoices (per PF-005 Performance Constraint).
            self.assertLess(
                elapsed, 1.0,
                f"Aging compute for 100 invoices across 10 partners took "
                f"{elapsed:.3f}s — exceeds 1.0s scaled-down SLA.",
            )

    def test_account_followup_line_aggregates_match_partner(self):
        """Phase 8: denormalized ``account.followup.line`` matches partner.

        Calls ``self.env['account.followup.line']._cron_refresh_all()``
        to materialize the denormalized aggregate table from the live
        partner-level computed fields. Then queries the summary line
        for ``self.partner_overdue_45d`` and asserts each materialized
        field matches the corresponding partner field.

        This validates that the denormalization stays in sync — a
        property the cron handler must guarantee. Mismatch would
        indicate either:
          * The cron handler's ``_refresh_from_partner`` writes the
            wrong field mapping.
          * The partner's ``_compute_overdue_aging`` returns different
            values from one invocation to the next (non-determinism).
          * The ``account.followup.line._get_or_create_for_partner``
            picks the wrong existing record (UNIQUE constraint
            violation).

        Also confirms the API contract for ``_get_or_create_for_partner``
        on empty input: it must raise ``UserError`` rather than create
        a row with NULL ``partner_id`` (which would violate the
        required-field constraint on the model).
        """
        with freeze_time(self.FROZEN_DATE):
            FollowupLine = self.env['account.followup.line']

            # API guard: empty partner argument raises UserError before
            # any DB write attempt. Demonstrates that the upsert helper
            # validates inputs at the Python level rather than relying
            # on PostgreSQL's NOT NULL constraint to fail later.
            with self.assertRaises(UserError):
                FollowupLine._get_or_create_for_partner(
                    self.env['res.partner'].browse(),
                )

            # Run the cron handler with a small batch_size for the
            # test scenario. Fixture has eight customer_rank=1 partners,
            # batch_size=100 covers them all.
            result = FollowupLine._cron_refresh_all(batch_size=100)

            # Telemetry dict shape verification.
            self.assertIsInstance(result, dict)
            for key in (
                'partners_processed',
                'summaries_refreshed',
                'errors',
            ):
                self.assertIn(key, result)
            self.assertEqual(
                result['errors'], 0,
                "Clean fixture set must not produce cron errors.",
            )
            self.assertGreaterEqual(
                result['summaries_refreshed'], 1,
                "At least one summary must refresh "
                "(fixtures include overdue partners).",
            )

            # Look up the materialized summary for partner_overdue_45d.
            partner = self.partner_overdue_45d
            partner.invalidate_recordset()
            line = FollowupLine.search(
                [
                    ('partner_id', '=', partner.id),
                    ('company_id', '=', self.env.company.id),
                ],
                limit=1,
            )
            self.assertTrue(
                line,
                "Materialized summary line must exist for "
                "partner_overdue_45d.",
            )

            # Field-by-field consistency between summary and partner.
            self.assertEqual(
                float_compare(
                    line.total_overdue,
                    partner.total_overdue,
                    precision_digits=2,
                ),
                0,
                f"Summary total_overdue ({line.total_overdue}) must match "
                f"partner ({partner.total_overdue}).",
            )
            self.assertEqual(
                float_compare(
                    line.aging_bucket_current,
                    partner.aging_bucket_current,
                    precision_digits=2,
                ),
                0,
            )
            self.assertEqual(
                float_compare(
                    line.aging_bucket_1_30,
                    partner.aging_bucket_1_30,
                    precision_digits=2,
                ),
                0,
            )
            self.assertEqual(
                float_compare(
                    line.aging_bucket_31_60,
                    partner.aging_bucket_31_60,
                    precision_digits=2,
                ),
                0,
            )
            self.assertEqual(
                float_compare(
                    line.aging_bucket_61_90,
                    partner.aging_bucket_61_90,
                    precision_digits=2,
                ),
                0,
            )
            self.assertEqual(
                float_compare(
                    line.aging_bucket_90_plus,
                    partner.aging_bucket_90_plus,
                    precision_digits=2,
                ),
                0,
            )
            self.assertEqual(
                line.max_days_overdue, partner.max_days_overdue,
                "Summary max_days_overdue must match partner.",
            )
            self.assertEqual(
                line.followup_level_id, partner.followup_level_id,
                "Summary followup_level_id must match partner.",
            )
