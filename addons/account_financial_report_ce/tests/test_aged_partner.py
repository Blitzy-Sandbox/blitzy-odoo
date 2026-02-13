# -*- coding: utf-8 -*-
# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Aged Partner Balance Report Tests — FR-006 Acceptance Criteria

Test module for FR-006: Aged Receivable/Payable Reports.
Maps each test method to specific acceptance scenarios defined in the
FR-006 user story:
  - Scenario 1: Generate Aged Receivables report
  - Scenario 2: Generate Aged Payables report
  - Scenario 3: Display aging buckets (Current, 1-30, 31-60, 61-90, 91-120, 120+)
  - Scenario 4: Show partner-level details with drill-down
  - Scenario 5: Sort by total amount or oldest bucket
  - Scenario 6: Configurable bucket boundaries and filtering

All tests use @freeze_time('2024-06-30') to ensure deterministic aging
calculations against invoices with known due dates, and extend the Odoo
AccountTestInvoicingCommon base class for realistic accounting fixtures.
"""

from datetime import date, timedelta

from freezegun import freeze_time

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestAgedPartner(AccountTestInvoicingCommon):
    """
    Test suite for the Aged Partner Balance Report (FR-006).

    Aging bucket layout with default configuration (as of 2024-06-30):
      - Not Due (Current): days_overdue <= 0
      - Bucket 1 (1-30 days): 1 <= days_overdue <= 30
      - Bucket 2 (31-60 days): 31 <= days_overdue <= 60
      - Bucket 3 (61-90 days): 61 <= days_overdue <= 90
      - Bucket 4 (91-120 days): 91 <= days_overdue <= 120
      - Bucket 5 (120+ days): days_overdue > 120

    Test data layout (all amounts are price_unit, no taxes):
      Partner A (AR):
        - inv_a_current: 1000, invoice_date 2024-06-30 → 0 days → Not Due
        - inv_a_15d:     2000, invoice_date 2024-06-15 → 15 days → Bucket 1
        - inv_a_45d:     3000, invoice_date 2024-05-16 → 45 days → Bucket 2
      Partner B (AR):
        - inv_b_75d:     4000, invoice_date 2024-04-16 → 75 days → Bucket 3
        - inv_b_100d:    5000, invoice_date 2024-03-22 → 100 days → Bucket 4
      Partner C (AR):
        - inv_c_150d:    6000, invoice_date 2024-02-01 → 150 days → Bucket 5
      Partner A (AP):
        - bill_a_45d:    1500, invoice_date 2024-05-16 → 45 days → Bucket 2
      Draft (not posted):
        - inv_draft:      500, invoice_date 2024-06-15 → 15 days → Bucket 1 (if included)
    """

    REPORT_MODEL = 'account.aged.partner.balance.report'
    FROZEN_DATE = date(2024, 6, 30)

    @classmethod
    def setUpClass(cls):
        """
        Create test partners, AR invoices, AP bills, and a draft invoice
        spanning all aging buckets for deterministic FR-006 scenario coverage.
        """
        super().setUpClass()

        # -- Partner C: additional partner for 120+ bucket isolation ----------
        cls.partner_c = cls.env['res.partner'].create({
            'name': 'partner_c',
            'invoice_sending_method': 'manual',
            'invoice_edi_format': False,
            'property_payment_term_id': cls.pay_terms_a.id,
            'property_supplier_payment_term_id': cls.pay_terms_a.id,
            'property_account_receivable_id': (
                cls.company_data['default_account_receivable'].id
            ),
            'property_account_payable_id': (
                cls.company_data['default_account_payable'].id
            ),
            'company_id': False,
        })

        # -- AR Invoices (out_invoice) ----------------------------------------
        # Partner A — Current / Not Due (0 days overdue)
        cls.inv_a_current = cls._create_aged_invoice(
            move_type='out_invoice',
            partner=cls.partner_a,
            invoice_date=date(2024, 6, 30),
            amount=1000.0,
        )
        # Partner A — 15 days overdue → Bucket 1 (1-30)
        cls.inv_a_15d = cls._create_aged_invoice(
            move_type='out_invoice',
            partner=cls.partner_a,
            invoice_date=date(2024, 6, 15),
            amount=2000.0,
        )
        # Partner A — 45 days overdue → Bucket 2 (31-60)
        cls.inv_a_45d = cls._create_aged_invoice(
            move_type='out_invoice',
            partner=cls.partner_a,
            invoice_date=date(2024, 5, 16),
            amount=3000.0,
        )
        # Partner B — 75 days overdue → Bucket 3 (61-90)
        cls.inv_b_75d = cls._create_aged_invoice(
            move_type='out_invoice',
            partner=cls.partner_b,
            invoice_date=date(2024, 4, 16),
            amount=4000.0,
        )
        # Partner B — 100 days overdue → Bucket 4 (91-120)
        cls.inv_b_100d = cls._create_aged_invoice(
            move_type='out_invoice',
            partner=cls.partner_b,
            invoice_date=date(2024, 3, 22),
            amount=5000.0,
        )
        # Partner C — 150 days overdue → Bucket 5 (120+)
        cls.inv_c_150d = cls._create_aged_invoice(
            move_type='out_invoice',
            partner=cls.partner_c,
            invoice_date=date(2024, 2, 1),
            amount=6000.0,
        )

        # -- AP Bills (in_invoice) for payable-mode tests --------------------
        # Partner A — 45 days overdue → Bucket 2 (31-60)
        cls.bill_a_45d = cls._create_aged_invoice(
            move_type='in_invoice',
            partner=cls.partner_a,
            invoice_date=date(2024, 5, 16),
            amount=1500.0,
        )

        # -- Draft invoice (for target_move filtering test) -------------------
        cls.inv_draft = cls._create_aged_invoice(
            move_type='out_invoice',
            partner=cls.partner_a,
            invoice_date=date(2024, 6, 15),
            amount=500.0,
            post=False,
        )

    # -------------------------------------------------------------------------
    # HELPER METHODS
    # -------------------------------------------------------------------------

    @classmethod
    def _create_aged_invoice(cls, move_type, partner, invoice_date, amount,
                             post=True):
        """
        Create a minimal invoice/bill with a single line (no taxes)
        and the *Immediate Payment* term so that ``date_maturity`` equals
        ``invoice_date``, giving deterministic aging bucket placement.

        Args:
            move_type: 'out_invoice' for AR or 'in_invoice' for AP.
            partner:   ``res.partner`` record.
            invoice_date: Date object for the invoice.
            amount:    Line price_unit (positive number).
            post:      Whether to validate (post) the move immediately.

        Returns:
            The created ``account.move`` record.
        """
        move = cls.env['account.move'].create({
            'move_type': move_type,
            'partner_id': partner.id,
            'invoice_date': invoice_date,
            'date': invoice_date,
            'invoice_payment_term_id': cls.pay_terms_a.id,
            'invoice_line_ids': [
                Command.create({
                    'name': 'Aged test line',
                    'price_unit': amount,
                    'quantity': 1.0,
                    'tax_ids': [Command.clear()],
                }),
            ],
        })
        if post:
            move.action_post()
        return move

    def _create_report(self, **kwargs):
        """
        Instantiate an Aged Partner Balance report with sensible defaults.

        Returns a *browseable* ``account.aged.partner.balance.report`` record
        whose computed fields (``partner_line_ids``, totals, etc.) are
        triggered on first access.

        Any keyword argument overrides the corresponding field value.
        """
        vals = {
            'date_to': self.FROZEN_DATE,
            'company_id': self.env.company.id,
            'target_move': 'posted',
            'report_type': 'receivable',
        }
        vals.update(kwargs)
        return self.env[self.REPORT_MODEL].create(vals)

    def _get_partner_line(self, report, partner):
        """Return the partner line record for *partner* in *report*, or False."""
        return report.partner_line_ids.filtered(
            lambda l: l.partner_id == partner
        )

    # -------------------------------------------------------------------------
    # FR-006 — REPORT CREATION TESTS
    # -------------------------------------------------------------------------

    @freeze_time('2024-06-30')
    def test_fr006_aged_receivable_creation(self):
        """FR-006 Scenario 1: Create an Aged Receivables report and verify
        it is properly created with report_type='receivable'."""
        report = self._create_report(report_type='receivable')
        self.assertTrue(report.exists())
        self.assertEqual(report.report_type, 'receivable')
        self.assertEqual(report.date_to, self.FROZEN_DATE)
        # Should have partner lines for partners with open AR items
        self.assertTrue(len(report.partner_line_ids) > 0,
                        "Receivable report must produce partner lines.")

        # Verify action_generate_report returns a valid window action
        action = report.action_generate_report()
        self.assertEqual(action['type'], 'ir.actions.act_window')
        self.assertEqual(action['res_model'], self.REPORT_MODEL)

        # Verify action_generate_report raises UserError when date_to missing
        report_no_date = self.env[self.REPORT_MODEL].new({
            'report_type': 'receivable',
            'company_id': self.env.company.id,
            'target_move': 'posted',
        })
        report_no_date.date_to = False
        with self.assertRaises(UserError):
            report_no_date.action_generate_report()

    @freeze_time('2024-06-30')
    def test_fr006_aged_payable_creation(self):
        """FR-006 Scenario 2: Create an Aged Payables report and verify
        it is properly created with report_type='payable'."""
        report = self._create_report(report_type='payable')
        self.assertTrue(report.exists())
        self.assertEqual(report.report_type, 'payable')
        # Partner A has an AP bill → at least one line expected
        self.assertTrue(len(report.partner_line_ids) > 0,
                        "Payable report must produce partner lines "
                        "when open AP items exist.")

    @freeze_time('2024-06-30')
    def test_fr006_aged_both_creation(self):
        """FR-006: Create a combined (both) report and verify it contains
        lines from both receivable and payable accounts."""
        report = self._create_report(report_type='both')
        self.assertTrue(report.exists())
        self.assertEqual(report.report_type, 'both')
        self.assertTrue(len(report.partner_line_ids) > 0)

    # -------------------------------------------------------------------------
    # FR-006 — AGING BUCKET ACCURACY TESTS
    # -------------------------------------------------------------------------

    @freeze_time('2024-06-30')
    def test_fr006_aging_bucket_current(self):
        """FR-006 Scenario 3a: Entries not yet due (days_overdue <= 0)
        are classified in the 'Not Due' / Current bucket.
        Partner A has inv_a_current dated 2024-06-30 → 0 days overdue."""
        report = self._create_report(report_type='receivable')
        line_a = self._get_partner_line(report, self.partner_a)
        self.assertTrue(line_a, "Partner A must appear in the report.")

        # Verify the invoice date equals the report as-of date (zero days)
        inv_due = self.inv_a_current.invoice_date
        self.assertEqual(
            (self.FROZEN_DATE - inv_due), timedelta(days=0),
            "Current invoice must have 0 days overdue.",
        )

        # The 1000 current invoice should land in not_due
        self.assertAlmostEqual(
            line_a.not_due, 1000.0, places=2,
            msg="Current (0-day) invoice must be in the Not Due bucket.",
        )

    @freeze_time('2024-06-30')
    def test_fr006_aging_bucket_30(self):
        """FR-006 Scenario 3b: Entries 1-30 days overdue land in Bucket 1.
        Partner A has inv_a_15d dated 2024-06-15 → 15 days overdue."""
        report = self._create_report(report_type='receivable')
        line_a = self._get_partner_line(report, self.partner_a)
        self.assertTrue(line_a)
        # 2000 should be in bucket_1 (1-30 days)
        self.assertAlmostEqual(
            line_a.bucket_1, 2000.0, places=2,
            msg="15-day-overdue invoice must be in the 1-30 day bucket.",
        )

    @freeze_time('2024-06-30')
    def test_fr006_aging_bucket_60(self):
        """FR-006 Scenario 3c: Entries 31-60 days overdue land in Bucket 2.
        Partner A has inv_a_45d dated 2024-05-16 → 45 days overdue."""
        report = self._create_report(report_type='receivable')
        line_a = self._get_partner_line(report, self.partner_a)
        self.assertTrue(line_a)
        # 3000 should be in bucket_2 (31-60 days)
        self.assertAlmostEqual(
            line_a.bucket_2, 3000.0, places=2,
            msg="45-day-overdue invoice must be in the 31-60 day bucket.",
        )

    @freeze_time('2024-06-30')
    def test_fr006_aging_bucket_90(self):
        """FR-006 Scenario 3d: Entries 61-90 days overdue land in Bucket 3.
        Partner B has inv_b_75d dated 2024-04-16 → 75 days overdue."""
        report = self._create_report(report_type='receivable')
        line_b = self._get_partner_line(report, self.partner_b)
        self.assertTrue(line_b, "Partner B must appear in the report.")
        # 4000 should be in bucket_3 (61-90 days)
        self.assertAlmostEqual(
            line_b.bucket_3, 4000.0, places=2,
            msg="75-day-overdue invoice must be in the 61-90 day bucket.",
        )

    @freeze_time('2024-06-30')
    def test_fr006_aging_bucket_120_plus(self):
        """FR-006 Scenario 3e: Entries 91+ days overdue.
        Partner B has inv_b_100d (100 days) → Bucket 4 (91-120).
        Partner C has inv_c_150d (150 days) → Bucket 5 (120+)."""
        report = self._create_report(report_type='receivable')

        # Bucket 4 (91-120): Partner B — 100 days overdue
        line_b = self._get_partner_line(report, self.partner_b)
        self.assertTrue(line_b)
        self.assertAlmostEqual(
            line_b.bucket_4, 5000.0, places=2,
            msg="100-day-overdue invoice must be in the 91-120 day bucket.",
        )

        # Bucket 5 (120+): Partner C — 150 days overdue
        line_c = self._get_partner_line(report, self.partner_c)
        self.assertTrue(line_c, "Partner C must appear in the report.")
        self.assertAlmostEqual(
            line_c.bucket_5, 6000.0, places=2,
            msg="150-day-overdue invoice must be in the 120+ day bucket.",
        )

    @freeze_time('2024-06-30')
    def test_fr006_bucket_sum_equals_total(self):
        """FR-006 Scenario 3f: For every partner line the sum of all
        aging buckets must equal the partner's total balance."""
        report = self._create_report(report_type='receivable')
        for pline in report.partner_line_ids:
            bucket_sum = (
                pline.not_due
                + pline.bucket_1
                + pline.bucket_2
                + pline.bucket_3
                + pline.bucket_4
                + pline.bucket_5
            )
            self.assertAlmostEqual(
                bucket_sum, pline.total, places=2,
                msg=(
                    f"Sum of buckets ({bucket_sum}) must equal total "
                    f"({pline.total}) for partner '{pline.name}'."
                ),
            )

        # Also verify report-level totals
        report_bucket_sum = (
            report.total_not_due
            + report.total_bucket_1
            + report.total_bucket_2
            + report.total_bucket_3
            + report.total_bucket_4
            + report.total_bucket_5
        )
        self.assertAlmostEqual(
            report_bucket_sum, report.total_balance, places=2,
            msg="Sum of report-level bucket totals must equal total_balance.",
        )

    # -------------------------------------------------------------------------
    # FR-006 — AR vs AP MODE TESTS
    # -------------------------------------------------------------------------

    @freeze_time('2024-06-30')
    def test_fr006_ar_mode_account_types(self):
        """FR-006 Scenario 1/3: In receivable mode, only move lines on
        accounts with account_type 'asset_receivable' are included."""
        report = self._create_report(report_type='receivable')

        # Collect all account types backing the reported data.
        # Partner A has both AR invoices and an AP bill; only AR should appear.
        # The report total should NOT include the AP bill_a_45d (1500).
        expected_ar_total = 1000.0 + 2000.0 + 3000.0 + 4000.0 + 5000.0 + 6000.0
        self.assertAlmostEqual(
            report.total_balance, expected_ar_total, places=2,
            msg="AR report total must include only receivable items.",
        )

    @freeze_time('2024-06-30')
    def test_fr006_ap_mode_account_types(self):
        """FR-006 Scenario 2: In payable mode, only move lines on accounts
        with account_type 'liability_payable' are included."""
        report = self._create_report(report_type='payable')

        # Only bill_a_45d (1500) should appear.
        # The AP model negates amount_residual for payable accounts,
        # so the reported value is the absolute open payable.
        self.assertAlmostEqual(
            report.total_balance, 1500.0, places=2,
            msg="AP report total must include only payable items.",
        )

    # -------------------------------------------------------------------------
    # FR-006 — PARTNER DRILL-DOWN
    # -------------------------------------------------------------------------

    @freeze_time('2024-06-30')
    def test_fr006_partner_drill_down(self):
        """FR-006 Scenario 4: Clicking a partner line triggers an
        ir.actions.act_window targeting the partner's open move lines."""
        report = self._create_report(report_type='receivable')
        line_a = self._get_partner_line(report, self.partner_a)
        self.assertTrue(line_a, "Partner A must appear for drill-down test.")

        action = line_a.action_drilldown()

        self.assertEqual(action['type'], 'ir.actions.act_window')
        self.assertEqual(action['res_model'], 'account.move.line')
        # Domain must filter to the specific partner
        domain = action.get('domain', [])
        partner_filter = [d for d in domain if d[0] == 'partner_id']
        self.assertTrue(
            partner_filter,
            "Drill-down domain must include a partner_id filter.",
        )
        self.assertEqual(
            partner_filter[0][2], self.partner_a.id,
            "Drill-down must target Partner A's move lines.",
        )

    # -------------------------------------------------------------------------
    # FR-006 — PARTNER FILTERING
    # -------------------------------------------------------------------------

    @freeze_time('2024-06-30')
    def test_fr006_partner_filtering(self):
        """FR-006: When partner_ids is set, only those partners appear
        in the report."""
        report = self._create_report(
            report_type='receivable',
            partner_ids=[Command.set([self.partner_b.id])],
        )
        partner_names = report.partner_line_ids.mapped('partner_id')
        self.assertEqual(
            partner_names, self.partner_b,
            "Only Partner B should appear when filtering by partner_ids.",
        )
        # Partner A and C must not be present
        line_a = self._get_partner_line(report, self.partner_a)
        line_c = self._get_partner_line(report, self.partner_c)
        self.assertFalse(line_a, "Partner A must be excluded by filter.")
        self.assertFalse(line_c, "Partner C must be excluded by filter.")

    # -------------------------------------------------------------------------
    # FR-006 — CONFIGURABLE BUCKET BOUNDARIES
    # -------------------------------------------------------------------------

    @freeze_time('2024-06-30')
    def test_fr006_custom_bucket_configuration(self):
        """FR-006 Scenario 6: Custom bucket boundaries change aging
        classification.

        Default buckets: 30/60/90/120.
        Custom buckets: bucket_1=15, bucket_2=45.
        With bucket_1=15 the 15-day overdue invoice (inv_a_15d) falls
        exactly at the boundary of Bucket 1 (<=15). The 45-day invoice
        (inv_a_45d) now falls in Bucket 2 (16-45), not Bucket 2 (31-60).
        """
        report = self._create_report(
            report_type='receivable',
            bucket_1_days=15,
            bucket_2_days=45,
            bucket_3_days=90,
            bucket_4_days=120,
        )
        line_a = self._get_partner_line(report, self.partner_a)
        self.assertTrue(line_a)

        # inv_a_15d (15 days overdue) should be at boundary of bucket_1 (<=15)
        self.assertAlmostEqual(
            line_a.bucket_1, 2000.0, places=2,
            msg="With bucket_1_days=15, 15-day invoice must remain in Bucket 1.",
        )
        # inv_a_45d (45 days overdue) should be at boundary of bucket_2 (<=45)
        self.assertAlmostEqual(
            line_a.bucket_2, 3000.0, places=2,
            msg="With bucket_2_days=45, 45-day invoice must fall in Bucket 2.",
        )

    # -------------------------------------------------------------------------
    # FR-006 — SORTING TESTS
    # -------------------------------------------------------------------------

    @freeze_time('2024-06-30')
    def test_fr006_sort_by_total(self):
        """FR-006 Scenario 5a: Sort by total amount (descending absolute)."""
        report = self._create_report(
            report_type='receivable',
            sort_by='total',
        )
        totals = [pline.total for pline in report.partner_line_ids]
        # Sorting is by -abs(total) so highest absolute totals come first.
        abs_totals = [abs(t) for t in totals]
        self.assertEqual(
            abs_totals, sorted(abs_totals, reverse=True),
            "Partner lines must be sorted by descending absolute total.",
        )

    @freeze_time('2024-06-30')
    def test_fr006_sort_by_oldest(self):
        """FR-006 Scenario 5b: Sort by oldest balance (bucket_5+bucket_4
        descending)."""
        report = self._create_report(
            report_type='receivable',
            sort_by='oldest',
        )
        oldest_sums = [
            pline.bucket_5 + pline.bucket_4
            for pline in report.partner_line_ids
        ]
        self.assertEqual(
            oldest_sums, sorted(oldest_sums, reverse=True),
            "Partner lines must be sorted by descending oldest bucket sums.",
        )

    # -------------------------------------------------------------------------
    # FR-006 — SHOW ONLY OVERDUE TOGGLE
    # -------------------------------------------------------------------------

    @freeze_time('2024-06-30')
    def test_fr006_show_only_overdue(self):
        """FR-006: With show_only_overdue=True, items that are not yet due
        (days_overdue <= 0) must be excluded from bucket totals.
        Partner A's inv_a_current (1000, 0 days) should be excluded."""
        report = self._create_report(
            report_type='receivable',
            show_only_overdue=True,
        )

        # The not-due amount across the entire report must be zero
        self.assertAlmostEqual(
            report.total_not_due, 0.0, places=2,
            msg="Not-due total must be 0 when show_only_overdue is enabled.",
        )

        # Partner A still appears (has overdue items), but not_due is 0
        line_a = self._get_partner_line(report, self.partner_a)
        if line_a:
            self.assertAlmostEqual(
                line_a.not_due, 0.0, places=2,
                msg="Partner A's not-due bucket must be 0.",
            )

        # Overall total should exclude the 1000 not-due amount
        # Expected: 2000 + 3000 + 4000 + 5000 + 6000 = 20000
        expected_overdue_total = 2000.0 + 3000.0 + 4000.0 + 5000.0 + 6000.0
        self.assertAlmostEqual(
            report.total_balance, expected_overdue_total, places=2,
            msg="Total must exclude current/not-due items when toggle is on.",
        )

    # -------------------------------------------------------------------------
    # FR-006 — MULTI-COMPANY ISOLATION
    # -------------------------------------------------------------------------

    @freeze_time('2024-06-30')
    def test_fr006_multi_company_isolation(self):
        """FR-006: Reports must respect company_id isolation.
        Invoices created in the default company must NOT appear in a report
        generated for a different company."""
        # Set up the second company's accounting data
        company_2_data = self.setup_other_company()
        company_2 = company_2_data['company']

        report = self._create_report(
            report_type='receivable',
            company_id=company_2.id,
        )
        # No AR invoices were created for company_2, so the report must be
        # empty (no partner lines, zero total).
        self.assertEqual(
            len(report.partner_line_ids), 0,
            "Report for a different company must show no partner lines.",
        )
        self.assertAlmostEqual(
            report.total_balance, 0.0, places=2,
            msg="Total balance must be 0 for a company with no AR data.",
        )

    # -------------------------------------------------------------------------
    # FR-006 — ZERO BALANCE PARTNER EXCLUSION
    # -------------------------------------------------------------------------

    @freeze_time('2024-06-30')
    def test_fr006_zero_balance_partner_excluded(self):
        """FR-006: A partner whose invoices are fully paid (zero residual)
        must not appear in the report."""
        # Create and fully pay an invoice for a fresh partner
        partner_paid = self.env['res.partner'].create({
            'name': 'partner_fully_paid',
            'invoice_sending_method': 'manual',
            'invoice_edi_format': False,
            'property_account_receivable_id': (
                self.company_data['default_account_receivable'].id
            ),
            'property_account_payable_id': (
                self.company_data['default_account_payable'].id
            ),
            'company_id': False,
        })
        invoice = self._create_aged_invoice(
            move_type='out_invoice',
            partner=partner_paid,
            invoice_date=date(2024, 6, 1),
            amount=750.0,
        )

        # Fully reconcile / pay the invoice
        receivable_line = invoice.line_ids.filtered(
            lambda l: l.account_id.account_type == 'asset_receivable'
        )
        payment = self.env['account.payment'].create({
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': partner_paid.id,
            'amount': 750.0,
            'journal_id': self.company_data['default_journal_bank'].id,
            'date': date(2024, 6, 2),
        })
        payment.action_post()

        # Reconcile payment line with invoice line
        payment_receivable = payment.line_ids.filtered(
            lambda l: l.account_id.account_type == 'asset_receivable'
        )
        (receivable_line + payment_receivable).reconcile()

        report = self._create_report(report_type='receivable')
        line_paid = self._get_partner_line(report, partner_paid)
        self.assertFalse(
            line_paid,
            "Fully paid partner must not appear in the aged report.",
        )

    # -------------------------------------------------------------------------
    # FR-006 — POSTED MOVES ONLY
    # -------------------------------------------------------------------------

    @freeze_time('2024-06-30')
    def test_fr006_posted_moves_only(self):
        """FR-006: With target_move='posted', draft invoices must be excluded.
        inv_draft (500, 15 days overdue, draft) must NOT contribute to totals.
        """
        report_posted = self._create_report(
            report_type='receivable',
            target_move='posted',
        )
        # Total should be 1000+2000+3000+4000+5000+6000 = 21000 (no draft 500)
        expected_posted = 21000.0
        self.assertAlmostEqual(
            report_posted.total_balance, expected_posted, places=2,
            msg="Posted-only report must exclude draft invoice amounts.",
        )

        # With target_move='all', draft invoice should be included
        report_all = self._create_report(
            report_type='receivable',
            target_move='all',
        )
        expected_all = expected_posted + 500.0
        self.assertAlmostEqual(
            report_all.total_balance, expected_all, places=2,
            msg="All-entries report must include draft invoice amounts.",
        )
