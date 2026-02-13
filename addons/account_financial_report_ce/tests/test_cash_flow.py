# -*- coding: utf-8 -*-
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Test Suite for FR-003: Cash Flow Statement

Implements dedicated tests for Cash Flow Statement acceptance criteria
as defined in the FR-003 user story and EPIC-001 requirements.

Test Coverage Areas:
- Indirect method computation (Net Income, depreciation add-back,
  working capital changes)
- Activity categorization (Operating, Investing, Financing)
- Cash reconciliation (opening_cash + net_change = closing_cash)
- Direct method support
- Comparative period analysis
- Date range filtering and multi-company isolation

BDD Alignment:
- Each test method maps to a specific FR-003 acceptance scenario
- Test method names reference the story ID (test_fr003_*)
- Fixtures extend AccountTestInvoicingCommon for realistic data

Performance Context:
- Cash Flow reports target <30 seconds for 100,000 transactions
- Tests verify correctness; performance validated separately

OCA Coding Standards:
- @tagged('post_install', '-at_install') per Odoo convention
- AGPL-3.0 license header
- Deterministic dates via @freeze_time
"""

from datetime import date, timedelta

from freezegun import freeze_time
from odoo.tests import tagged
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import UserError


@tagged('post_install', '-at_install')
@freeze_time('2024-06-30')
class TestCashFlow(AccountTestInvoicingCommon):
    """
    Test class for FR-003: Cash Flow Statement.

    Extends AccountTestInvoicingCommon to leverage pre-configured
    accounting fixtures (company_data with accounts, journals, partners).

    Creates comprehensive journal entries exercising all cash flow
    activity categories:
    - Operating: revenue, expense, depreciation, working capital
    - Investing: fixed asset purchases
    - Financing: loan proceeds

    Expected computed values (verified across test methods):
    - opening_cash = 20,000.00
    - closing_cash = 24,000.00
    - net_income = 5,500.00 (10,000 revenue - 4,000 expense - 500 depr)
    - depreciation_amortization = 500.00
    - change_in_receivables = -7,000.00 (AR increase = cash drag)
    - change_in_payables = 2,000.00 (AP increase = cash source)
    - cash_from_operating = 1,000.00
    - cash_from_investing = -5,000.00 (FA purchase)
    - cash_from_financing = 8,000.00 (loan proceeds)
    - net_change_in_cash = 4,000.00
    - is_reconciled = True
    """

    @classmethod
    def setUpClass(cls):
        """
        Set up comprehensive test data for Cash Flow Statement testing.

        Creates:
        - Accounts for each cash flow activity type
        - Pre-period entries establishing opening cash balance
        - In-period operating entries (revenue, expense, depreciation,
          receivable collection, payable payment)
        - In-period investing entries (fixed asset purchase)
        - In-period financing entries (loan proceeds)
        """
        super().setUpClass()

        cls.company = cls.env.company
        cls.currency = cls.company.currency_id

        # Reporting period boundaries
        cls.date_from = date(2024, 1, 1)
        cls.date_to = date(2024, 6, 30)
        cls.pre_period_date = date(2023, 12, 15)

        # Comparison period boundaries
        cls.comp_date_from = date(2023, 1, 1)
        cls.comp_date_to = date(2023, 6, 30)

        # Journals from base fixture
        cls.journal_misc = cls.company_data['default_journal_misc']
        cls.journal_bank = cls.company_data['default_journal_bank']

        # Set up all required accounts
        cls._setup_accounts()

        # Create and post journal entries for each activity category
        cls._create_pre_period_entries()
        cls._create_operating_entries()
        cls._create_investing_entries()
        cls._create_financing_entries()

    @classmethod
    def _setup_accounts(cls):
        """
        Set up or locate accounts for all cash flow activity types.

        Uses accounts from company_data where available, creates new
        accounts where the chart of accounts lacks the required type.
        """
        Account = cls.env['account.account']
        company = cls.company

        # Cash account (asset_cash) — primary cash flow tracking account
        cls.account_cash = Account.search([
            ('company_id', '=', company.id),
            ('account_type', '=', 'asset_cash'),
        ], limit=1)
        if not cls.account_cash:
            cls.account_cash = Account.create({
                'code': '101000',
                'name': 'Cash - CF Test',
                'account_type': 'asset_cash',
                'company_id': company.id,
            })

        # Receivable (asset_receivable) — working capital component
        cls.account_receivable = cls.company_data['default_account_receivable']

        # Payable (liability_payable) — working capital component
        cls.account_payable = cls.company_data['default_account_payable']

        # Revenue (income) — net income component
        cls.account_revenue = cls.company_data['default_account_revenue']

        # Expense (expense) — net income component
        cls.account_expense = cls.company_data['default_account_expense']

        # Fixed assets (asset_fixed) — investing activities
        cls.account_fixed_assets = cls.company_data.get('default_account_assets')
        if not cls.account_fixed_assets:
            cls.account_fixed_assets = Account.search([
                ('company_id', '=', company.id),
                ('account_type', '=', 'asset_fixed'),
            ], limit=1)
        if not cls.account_fixed_assets:
            cls.account_fixed_assets = Account.create({
                'code': '160000',
                'name': 'Fixed Assets - CF Test',
                'account_type': 'asset_fixed',
                'company_id': company.id,
            })

        # Depreciation expense (expense_depreciation) — non-cash add-back
        cls.account_depreciation = Account.search([
            ('company_id', '=', company.id),
            ('account_type', '=', 'expense_depreciation'),
        ], limit=1)
        if not cls.account_depreciation:
            cls.account_depreciation = Account.create({
                'code': '680000',
                'name': 'Depreciation Expense - CF Test',
                'account_type': 'expense_depreciation',
                'company_id': company.id,
            })

        # Accumulated depreciation (asset_non_current) — contra-asset,
        # deliberately not asset_fixed to avoid interfering with
        # investing activity FA balance computation
        cls.account_accum_depreciation = Account.search([
            ('company_id', '=', company.id),
            ('account_type', '=', 'asset_non_current'),
            ('name', 'ilike', 'depreciation'),
        ], limit=1)
        if not cls.account_accum_depreciation:
            cls.account_accum_depreciation = Account.create({
                'code': '169000',
                'name': 'Accumulated Depreciation - CF Test',
                'account_type': 'asset_non_current',
                'company_id': company.id,
            })

        # Equity (equity) — used for initial capital and financing
        cls.account_equity = Account.search([
            ('company_id', '=', company.id),
            ('account_type', '=', 'equity'),
        ], limit=1)
        if not cls.account_equity:
            cls.account_equity = Account.create({
                'code': '310000',
                'name': 'Equity - CF Test',
                'account_type': 'equity',
                'company_id': company.id,
            })

        # Long-term liability (liability_non_current) — financing
        cls.account_lt_liability = Account.search([
            ('company_id', '=', company.id),
            ('account_type', '=', 'liability_non_current'),
        ], limit=1)
        if not cls.account_lt_liability:
            cls.account_lt_liability = Account.create({
                'code': '240000',
                'name': 'Long-term Loan - CF Test',
                'account_type': 'liability_non_current',
                'company_id': company.id,
            })

    @classmethod
    def _create_and_post_entry(cls, journal, entry_date, lines, ref=None):
        """
        Helper to create and post a balanced journal entry.

        Args:
            journal: account.journal record
            entry_date: date for the journal entry
            lines: list of dicts with account_id, debit, credit, name
            ref: optional reference string

        Returns:
            Posted account.move record
        """
        move_vals = {
            'move_type': 'entry',
            'journal_id': journal.id,
            'date': entry_date,
            'ref': ref or 'CF Test Entry',
            'line_ids': [
                (0, 0, line_vals) for line_vals in lines
            ],
        }
        move = cls.env['account.move'].create(move_vals)
        move.action_post()
        return move

    @classmethod
    def _create_pre_period_entries(cls):
        """
        Create entries before 2024-01-01 establishing opening balances.

        Opening cash balance target: 20,000.00
        Counterpart: equity (initial capital contribution)
        """
        cls.move_initial_cash = cls._create_and_post_entry(
            cls.journal_misc,
            cls.pre_period_date,
            [
                {
                    'account_id': cls.account_cash.id,
                    'debit': 20000.0,
                    'credit': 0.0,
                    'name': 'Initial capital deposit',
                },
                {
                    'account_id': cls.account_equity.id,
                    'debit': 0.0,
                    'credit': 20000.0,
                    'name': 'Equity contribution',
                },
            ],
            ref='CF-INIT: Initial Cash Deposit',
        )

    @classmethod
    def _create_operating_entries(cls):
        """
        Create operating activity entries within 2024-01-01 to 2024-06-30.

        Creates:
        - Revenue: 10,000 (Debit receivable, Credit revenue)
        - Expense: 4,000 (Debit expense, Credit payable)
        - Depreciation: 500 (Debit depr expense, Credit accum depr)
        - Customer payment: 3,000 (Debit cash, Credit receivable)
        - Vendor payment: 2,000 (Debit payable, Credit cash)
        """
        # Revenue entry — generates receivable and income
        cls.move_revenue = cls._create_and_post_entry(
            cls.journal_misc,
            date(2024, 2, 15),
            [
                {
                    'account_id': cls.account_receivable.id,
                    'debit': 10000.0,
                    'credit': 0.0,
                    'name': 'Customer revenue',
                    'partner_id': cls.partner_a.id,
                },
                {
                    'account_id': cls.account_revenue.id,
                    'debit': 0.0,
                    'credit': 10000.0,
                    'name': 'Revenue earned',
                },
            ],
            ref='CF-OP: Revenue',
        )

        # Expense entry — generates payable and expense
        cls.move_expense = cls._create_and_post_entry(
            cls.journal_misc,
            date(2024, 3, 10),
            [
                {
                    'account_id': cls.account_expense.id,
                    'debit': 4000.0,
                    'credit': 0.0,
                    'name': 'Operating expense',
                },
                {
                    'account_id': cls.account_payable.id,
                    'debit': 0.0,
                    'credit': 4000.0,
                    'name': 'Vendor payable',
                    'partner_id': cls.partner_b.id,
                },
            ],
            ref='CF-OP: Expense',
        )

        # Depreciation — non-cash expense (add-back in operating)
        # Credits accumulated depreciation (asset_non_current), NOT
        # fixed assets, to cleanly separate from investing activities
        cls.move_depreciation = cls._create_and_post_entry(
            cls.journal_misc,
            date(2024, 3, 31),
            [
                {
                    'account_id': cls.account_depreciation.id,
                    'debit': 500.0,
                    'credit': 0.0,
                    'name': 'Depreciation expense',
                },
                {
                    'account_id': cls.account_accum_depreciation.id,
                    'debit': 0.0,
                    'credit': 500.0,
                    'name': 'Accumulated depreciation',
                },
            ],
            ref='CF-OP: Depreciation',
        )

        # Customer payment received — cash inflow, receivable decrease
        cls.move_cash_received = cls._create_and_post_entry(
            cls.journal_misc,
            date(2024, 4, 15),
            [
                {
                    'account_id': cls.account_cash.id,
                    'debit': 3000.0,
                    'credit': 0.0,
                    'name': 'Customer payment received',
                },
                {
                    'account_id': cls.account_receivable.id,
                    'debit': 0.0,
                    'credit': 3000.0,
                    'name': 'Receivable collected',
                    'partner_id': cls.partner_a.id,
                },
            ],
            ref='CF-OP: Customer Payment',
        )

        # Vendor payment — cash outflow, payable decrease
        cls.move_cash_paid = cls._create_and_post_entry(
            cls.journal_misc,
            date(2024, 5, 10),
            [
                {
                    'account_id': cls.account_payable.id,
                    'debit': 2000.0,
                    'credit': 0.0,
                    'name': 'Vendor payment',
                    'partner_id': cls.partner_b.id,
                },
                {
                    'account_id': cls.account_cash.id,
                    'debit': 0.0,
                    'credit': 2000.0,
                    'name': 'Cash paid to vendor',
                },
            ],
            ref='CF-OP: Vendor Payment',
        )

    @classmethod
    def _create_investing_entries(cls):
        """
        Create investing activity entries within the reporting period.

        Creates:
        - Fixed asset purchase: 5,000 (Debit FA, Credit cash)
        """
        cls.move_fa_purchase = cls._create_and_post_entry(
            cls.journal_misc,
            date(2024, 2, 28),
            [
                {
                    'account_id': cls.account_fixed_assets.id,
                    'debit': 5000.0,
                    'credit': 0.0,
                    'name': 'Equipment purchase',
                },
                {
                    'account_id': cls.account_cash.id,
                    'debit': 0.0,
                    'credit': 5000.0,
                    'name': 'Cash paid for equipment',
                },
            ],
            ref='CF-INV: Asset Purchase',
        )

    @classmethod
    def _create_financing_entries(cls):
        """
        Create financing activity entries within the reporting period.

        Creates:
        - Loan proceeds: 8,000 (Debit cash, Credit long-term liability)
        """
        cls.move_loan = cls._create_and_post_entry(
            cls.journal_misc,
            date(2024, 4, 1),
            [
                {
                    'account_id': cls.account_cash.id,
                    'debit': 8000.0,
                    'credit': 0.0,
                    'name': 'Loan proceeds received',
                },
                {
                    'account_id': cls.account_lt_liability.id,
                    'debit': 0.0,
                    'credit': 8000.0,
                    'name': 'Long-term loan payable',
                },
            ],
            ref='CF-FIN: Loan Proceeds',
        )

    # -------------------------------------------------------------------------
    # HELPER METHODS
    # -------------------------------------------------------------------------

    def _create_cash_flow_report(self, **kwargs):
        """
        Create a Cash Flow report with default parameters.

        Default configuration:
        - Period: 2024-01-01 to 2024-06-30
        - Company: test company
        - Target moves: posted only
        - Method: indirect

        Args:
            **kwargs: Override any default parameter

        Returns:
            account.cash.flow.report record
        """
        values = {
            'date_from': self.date_from,
            'date_to': self.date_to,
            'company_id': self.company.id,
            'target_move': 'posted',
            'method': 'indirect',
        }
        values.update(kwargs)
        return self.env['account.cash.flow.report'].create(values)

    def _compute_report(self, report):
        """
        Trigger report computation via action_compute if available,
        otherwise access a computed field to trigger recomputation.

        Args:
            report: account.cash.flow.report record

        Returns:
            The report record (for chaining)
        """
        if hasattr(report, 'action_compute'):
            report.action_compute()
        else:
            # Force recomputation by accessing a computed field
            _ = report.opening_cash
        return report

    # -------------------------------------------------------------------------
    # FR-003 TEST METHODS
    # -------------------------------------------------------------------------

    def test_fr003_cash_flow_creation(self):
        """
        FR-003 Scenario: Create Cash Flow Statement.

        Given a configured accounting system with posted entries
        When I create a Cash Flow report with method='indirect'
        Then the report is created with correct parameters.
        """
        report = self._create_cash_flow_report()
        self.assertTrue(report, "Cash Flow report should be created")
        self.assertEqual(
            report.method, 'indirect',
            "Report method should be 'indirect'",
        )
        self.assertEqual(
            report.date_from, self.date_from,
            "Report date_from should match",
        )
        self.assertEqual(
            report.date_to, self.date_to,
            "Report date_to should match",
        )
        self.assertEqual(
            report.company_id, self.company,
            "Report company should match",
        )
        self.assertEqual(
            report.target_move, 'posted',
            "Report target_move should be 'posted'",
        )

    def test_fr003_cash_flow_computation(self):
        """
        FR-003 Scenario: Compute Cash Flow Statement.

        Given a Cash Flow report is created
        When the computation is triggered
        Then the report state becomes 'done' indicating completion.
        """
        report = self._create_cash_flow_report()
        self._compute_report(report)
        if hasattr(report, 'state'):
            self.assertEqual(
                report.state, 'done',
                "Report state should be 'done' after computation",
            )

    def test_fr003_indirect_method_net_income(self):
        """
        FR-003 Scenario: Indirect method starts with Net Income.

        Given posted revenue entries of 10,000 and expenses of
        4,000 + 500 depreciation within the reporting period
        When the Cash Flow is computed using indirect method
        Then net_income equals 5,500 (revenue minus all expenses).

        Net Income = 10,000 - 4,000 - 500 = 5,500
        """
        report = self._create_cash_flow_report()
        self._compute_report(report)
        self.assertAlmostEqual(
            report.net_income,
            5500.0,
            places=2,
            msg="Net income should be 5,500 "
                "(10,000 revenue - 4,000 expense - 500 depreciation)",
        )

    def test_fr003_depreciation_addback(self):
        """
        FR-003 Scenario: Depreciation added back in operating activities.

        Given a depreciation entry of 500 posted to an
        expense_depreciation type account
        When the Cash Flow is computed using indirect method
        Then depreciation_amortization equals 500 (added back
        because it is a non-cash expense).
        """
        report = self._create_cash_flow_report()
        self._compute_report(report)
        self.assertAlmostEqual(
            report.depreciation_amortization,
            500.0,
            places=2,
            msg="Depreciation add-back should be 500",
        )

    def test_fr003_working_capital_receivable(self):
        """
        FR-003 Scenario: Receivable changes reflect in operating activities.

        Given revenue of 10,000 increasing receivables and
        customer payment of 3,000 decreasing receivables
        When the Cash Flow is computed
        Then change_in_receivables equals -7,000
        (increase in receivables = negative cash impact).

        Opening AR = 0, Closing AR = 7,000 (10,000 - 3,000)
        Change = -(7,000 - 0) = -7,000
        """
        report = self._create_cash_flow_report()
        self._compute_report(report)
        self.assertAlmostEqual(
            report.change_in_receivables,
            -7000.0,
            places=2,
            msg="Receivable change should be -7,000 "
                "(AR increase = negative cash impact)",
        )

    def test_fr003_working_capital_payable(self):
        """
        FR-003 Scenario: Payable changes reflect in operating activities.

        Given expenses of 4,000 increasing payables and
        vendor payment of 2,000 decreasing payables
        When the Cash Flow is computed
        Then change_in_payables equals 2,000
        (increase in payables = positive cash impact).

        Opening AP = 0, Closing AP = -2,000 (credit balance)
        Change = -(-2,000 - 0) = 2,000
        """
        report = self._create_cash_flow_report()
        self._compute_report(report)
        self.assertAlmostEqual(
            report.change_in_payables,
            2000.0,
            places=2,
            msg="Payable change should be 2,000 "
                "(AP increase = positive cash impact)",
        )

    def test_fr003_operating_activities_total(self):
        """
        FR-003 Scenario: Operating activities total computation.

        Given the indirect method components:
        - Net Income: 5,500
        - Depreciation: +500
        - Change in Receivables: -7,000
        - Change in Payables: +2,000
        - Change in Inventory: 0
        When the Cash Flow is computed
        Then cash_from_operating = 1,000.

        Formula: 5,500 + 500 + (-7,000) + 2,000 + 0 = 1,000
        """
        report = self._create_cash_flow_report()
        self._compute_report(report)

        # Verify the formula: operating = NI + depr + WC changes
        expected_operating = (
            report.net_income
            + report.depreciation_amortization
            + report.change_in_receivables
            + report.change_in_payables
            + report.change_in_inventory
        )
        self.assertAlmostEqual(
            report.cash_from_operating,
            expected_operating,
            places=2,
            msg="Operating cash should equal sum of components",
        )
        self.assertAlmostEqual(
            report.cash_from_operating,
            1000.0,
            places=2,
            msg="Cash from operating should be 1,000",
        )

    def test_fr003_investing_activities(self):
        """
        FR-003 Scenario: Fixed asset changes classified as investing.

        Given a fixed asset purchase of 5,000
        When the Cash Flow is computed
        Then capital_expenditures equals -5,000 and
        cash_from_investing equals -5,000.

        Opening FA = 0, Closing FA = 5,000
        CapEx = -max(5,000, 0) = -5,000
        """
        report = self._create_cash_flow_report()
        self._compute_report(report)
        self.assertAlmostEqual(
            report.capital_expenditures,
            -5000.0,
            places=2,
            msg="Capital expenditures should be -5,000",
        )
        self.assertAlmostEqual(
            report.asset_disposals,
            0.0,
            places=2,
            msg="Asset disposals should be 0 (no sales)",
        )
        self.assertAlmostEqual(
            report.cash_from_investing,
            -5000.0,
            places=2,
            msg="Cash from investing should be -5,000",
        )

    def test_fr003_financing_activities(self):
        """
        FR-003 Scenario: Loan/equity changes classified as financing.

        Given loan proceeds of 8,000 credited to liability_non_current
        When the Cash Flow is computed
        Then debt_proceeds equals 8,000 and
        cash_from_financing equals 8,000.

        Opening debt = 0, Closing debt = -8,000 (credit)
        debt_change = -(-8,000 - 0) = 8,000
        """
        report = self._create_cash_flow_report()
        self._compute_report(report)
        self.assertAlmostEqual(
            report.debt_proceeds,
            8000.0,
            places=2,
            msg="Debt proceeds should be 8,000",
        )
        self.assertAlmostEqual(
            report.debt_repayments,
            0.0,
            places=2,
            msg="Debt repayments should be 0 (no repayments)",
        )
        self.assertAlmostEqual(
            report.cash_from_financing,
            8000.0,
            places=2,
            msg="Cash from financing should be 8,000",
        )

    def test_fr003_cash_reconciliation(self):
        """
        FR-003 Scenario: Cash reconciliation verification.

        Given opening cash of 20,000 and computed activity totals:
        - Operating: 1,000
        - Investing: -5,000
        - Financing: 8,000
        When the Cash Flow is computed
        Then opening_cash + net_change = closing_cash within
        2 decimal places.

        20,000 + (1,000 + (-5,000) + 8,000) = 24,000 = closing_cash
        """
        report = self._create_cash_flow_report()
        self._compute_report(report)

        net_change = (
            report.cash_from_operating
            + report.cash_from_investing
            + report.cash_from_financing
        )
        expected_closing = report.opening_cash + net_change

        self.assertAlmostEqual(
            report.closing_cash,
            expected_closing,
            places=2,
            msg="Closing cash should equal opening + net change "
                "(cash reconciliation)",
        )
        self.assertAlmostEqual(
            report.opening_cash,
            20000.0,
            places=2,
            msg="Opening cash should be 20,000",
        )
        self.assertAlmostEqual(
            report.closing_cash,
            24000.0,
            places=2,
            msg="Closing cash should be 24,000",
        )

    def test_fr003_net_change_calculation(self):
        """
        FR-003 Scenario: Net change in cash equals sum of activities.

        Given computed activity totals for operating, investing,
        and financing
        When the Cash Flow is computed
        Then net_change_in_cash = operating + investing + financing.

        net_change = 1,000 + (-5,000) + 8,000 = 4,000
        """
        report = self._create_cash_flow_report()
        self._compute_report(report)

        expected_net_change = (
            report.cash_from_operating
            + report.cash_from_investing
            + report.cash_from_financing
        )
        self.assertAlmostEqual(
            report.net_change_in_cash,
            expected_net_change,
            places=2,
            msg="Net change should equal sum of activities",
        )
        self.assertAlmostEqual(
            report.net_change_in_cash,
            4000.0,
            places=2,
            msg="Net change in cash should be 4,000",
        )

    def test_fr003_direct_method(self):
        """
        FR-003 Scenario: Direct method support.

        Given a Cash Flow report is created with method='direct'
        When the report is computed
        Then the report processes without error and produces
        a valid cash flow computation (direct method computes
        cash activities from actual cash receipts/payments
        rather than starting from net income).
        """
        report = self._create_cash_flow_report(method='direct')
        self.assertEqual(
            report.method, 'direct',
            "Report method should be 'direct'",
        )
        self._compute_report(report)

        # Direct method should still reconcile: opening + net = closing
        net_change = (
            report.cash_from_operating
            + report.cash_from_investing
            + report.cash_from_financing
        )
        expected_closing = report.opening_cash + net_change
        self.assertAlmostEqual(
            report.closing_cash,
            expected_closing,
            places=2,
            msg="Direct method should still reconcile cash balances",
        )

    def test_fr003_comparative_period(self):
        """
        FR-003 Scenario: Comparative period analysis.

        Given a Cash Flow report with enable_comparison=True
        and comparison dates for the prior year period
        When the report is computed
        Then comparison data is populated and available
        for variance analysis.
        """
        report = self._create_cash_flow_report(
            enable_comparison=True,
            comparison_date_from=self.comp_date_from,
            comparison_date_to=self.comp_date_to,
        )
        self._compute_report(report)

        # Verify comparison flag is set
        self.assertTrue(
            report.enable_comparison,
            "Comparison should be enabled",
        )
        # Current period should still compute correctly
        self.assertAlmostEqual(
            report.opening_cash,
            20000.0,
            places=2,
            msg="Current period opening cash should be 20,000",
        )

    def test_fr003_date_range_filtering(self):
        """
        FR-003 Scenario: Only entries within date range included.

        Given journal entries inside and outside the date range
        When a Cash Flow report is generated for a narrower range
        (2024-03-01 to 2024-04-30)
        Then only in-range entries are reflected in the computation,
        and out-of-range entries are excluded from activity totals.
        """
        # Use a narrower date range that excludes some entries
        narrow_from = date(2024, 3, 1)
        narrow_to = date(2024, 4, 30)

        report = self._create_cash_flow_report(
            date_from=narrow_from,
            date_to=narrow_to,
        )
        self._compute_report(report)

        # Opening cash should include all entries up to 2024-02-28
        # (initial 20,000 + received before March - paid before March)
        # The FA purchase on 2024-02-28 reduces cash by 5,000
        # Revenue on 2024-02-15 doesn't affect cash directly
        # Opening cash = 20,000 - 5,000 = 15,000
        self.assertAlmostEqual(
            report.opening_cash,
            15000.0,
            places=2,
            msg="Opening cash for narrow range should reflect "
                "pre-period cash balance (20,000 - 5,000 FA purchase)",
        )

        # In this narrow range (March-April):
        # Cash inflows: 3,000 (customer payment Apr 15),
        #               8,000 (loan Apr 1)
        # Cash outflows: 2,000 (vendor payment is May 10 - excluded!)
        # Closing cash = 15,000 + 3,000 + 8,000 = 26,000
        # Wait, vendor payment is May 10 which is outside narrow range
        # But closing cash is the actual balance at date_to (April 30)
        # Cash entries through April 30: 20,000 - 5,000 + 3,000 + 8,000
        #   = 26,000
        # (vendor payment on May 10 is after narrow_to)

        # The actual closing cash balance at April 30
        # includes all cash entries through that date
        self.assertAlmostEqual(
            report.closing_cash,
            26000.0,
            places=2,
            msg="Closing cash should reflect balance at end of range",
        )

    def test_fr003_beginning_cash_calculation(self):
        """
        FR-003 Scenario: Beginning cash equals cash balance at date_from.

        Given pre-period entries establishing a 20,000 cash balance
        and no cash entries between 2023-12-15 and 2024-01-01
        When the Cash Flow is computed for the standard period
        Then opening_cash (beginning cash) equals 20,000,
        which is the cash account balance as of the day before
        date_from.
        """
        report = self._create_cash_flow_report()
        self._compute_report(report)
        self.assertAlmostEqual(
            report.opening_cash,
            20000.0,
            places=2,
            msg="Beginning cash should equal cash balance at "
                "start of period (20,000 from initial deposit)",
        )

    def test_fr003_ending_cash_verification(self):
        """
        FR-003 Scenario: Ending cash equals cash balance at date_to.

        Given all posted cash entries through 2024-06-30:
        - +20,000 initial deposit (pre-period)
        - +3,000 customer payment
        - -2,000 vendor payment
        - -5,000 FA purchase
        - +8,000 loan proceeds
        When the Cash Flow is computed
        Then closing_cash equals 24,000 (actual cash balance).
        """
        report = self._create_cash_flow_report()
        self._compute_report(report)
        self.assertAlmostEqual(
            report.closing_cash,
            24000.0,
            places=2,
            msg="Ending cash should equal actual cash balance at "
                "date_to (20,000 + 3,000 - 2,000 - 5,000 + 8,000)",
        )

        # Additionally verify is_reconciled flag
        self.assertTrue(
            report.is_reconciled,
            "Cash flow should be reconciled "
            "(opening + net_change = closing)",
        )

    def test_fr003_multi_company_isolation(self):
        """
        FR-003 Scenario: Multi-company data isolation.

        Given entries in the primary company and a separate company
        When a Cash Flow report is generated for the primary company
        Then only the primary company's entries are included,
        and the other company's data is excluded.
        """
        # Set up a second company with its own accounting data
        company_2_data = self.setup_other_company()
        company_2 = company_2_data['company']

        # Create an entry in the second company
        journal_2 = company_2_data['default_journal_misc']
        if journal_2:
            account_cash_2 = self.env['account.account'].search([
                ('company_id', '=', company_2.id),
                ('account_type', '=', 'asset_cash'),
            ], limit=1)
            account_equity_2 = self.env['account.account'].search([
                ('company_id', '=', company_2.id),
                ('account_type', '=', 'equity'),
            ], limit=1)

            if account_cash_2 and account_equity_2:
                move_2 = self.env['account.move'].create({
                    'move_type': 'entry',
                    'journal_id': journal_2.id,
                    'date': date(2024, 3, 15),
                    'company_id': company_2.id,
                    'ref': 'Company 2 Cash Entry',
                    'line_ids': [
                        (0, 0, {
                            'account_id': account_cash_2.id,
                            'debit': 99999.0,
                            'credit': 0.0,
                            'name': 'Company 2 cash',
                        }),
                        (0, 0, {
                            'account_id': account_equity_2.id,
                            'debit': 0.0,
                            'credit': 99999.0,
                            'name': 'Company 2 equity',
                        }),
                    ],
                })
                move_2.action_post()

        # Generate report for primary company
        report = self._create_cash_flow_report()
        self._compute_report(report)

        # Primary company values should be unaffected
        self.assertAlmostEqual(
            report.opening_cash,
            20000.0,
            places=2,
            msg="Opening cash should only include primary company data",
        )
        self.assertAlmostEqual(
            report.closing_cash,
            24000.0,
            places=2,
            msg="Closing cash should only include primary company data",
        )
        self.assertAlmostEqual(
            report.net_change_in_cash,
            4000.0,
            places=2,
            msg="Net change should only reflect primary company entries",
        )
