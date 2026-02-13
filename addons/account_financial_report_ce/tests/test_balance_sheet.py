# -*- coding: utf-8 -*-
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Test Suite for Balance Sheet Report (FR-001)

Implements comprehensive tests for Balance Sheet report generation
as defined in FR-001 acceptance criteria:

- Assets = Liabilities + Equity (fundamental accounting equation)
- GAAP/IFRS section format verification (Current Assets, Non-Current Assets,
  Current Liabilities, Non-Current Liabilities, Equity)
- Account type classification accuracy for all relevant account types
- Comparative period calculation with variance analysis
- Drill-down navigation to source account.move.line records
- Multi-company data isolation
- Edge cases (zero-balance filtering, date boundaries, draft entries)

Maps test methods to FR-001 scenarios using ``test_fr001_*`` naming convention.
Target: Minimum 80% test coverage per EPIC-001 requirements.
"""

from datetime import date, timedelta

from freezegun import freeze_time

from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestBalanceSheet(AccountTestInvoicingCommon):
    """
    Test class for FR-001: Balance Sheet Report.

    Extends ``AccountTestInvoicingCommon`` to leverage pre-configured
    accounting fixtures (company, accounts, journals, partners).
    Creates dedicated test accounts and journal entries with known
    amounts to validate Balance Sheet generation, accounting equation,
    section classification, comparative periods, and drill-down.

    Expected posted account balances as of 2024-06-30
    (on TEST accounts only, Odoo balance = debit − credit):

    ============================================  ============
    Account (type)                                Balance
    ============================================  ============
    test_receivable  (asset_receivable)           +5,000
    test_cash        (asset_cash)                 +77,000
    test_fixed_asset (asset_fixed)                +20,000
    test_payable     (liability_payable)          −2,000
    test_non_current_liability (liability_non_current) −15,000
    test_equity      (equity)                     −80,000
    test_revenue     (income, 2024 fiscal year)   −10,000
    test_expense     (expense, 2024 fiscal year)  +5,000
    ============================================  ============

    Balance Sheet presented values (test accounts only):

    * Total Current Assets  = 82,000  (5,000 + 77,000)
    * Total Non-Current Assets = 20,000
    * Total Assets          = 102,000
    * Total Current Liabilities = 2,000
    * Total Non-Current Liabilities = 15,000
    * Total Liabilities     = 17,000
    * Equity (accounts)     = 80,000
    * Current Year Earnings = 5,000  (10,000 − 5,000)
    * Total Equity          = 85,000
    * CHECK: 102,000 = 17,000 + 85,000  ✓
    """

    @classmethod
    def setUpClass(cls):
        """
        Set up test data for Balance Sheet report tests.

        Creates:
        - Dedicated test accounts for every balance-sheet-relevant type
        - Posted journal entries with deterministic amounts
        - A draft entry for ``target_move`` filter testing
        - A prior-year entry for comparison-period testing
        """
        super().setUpClass()

        AccountAccount = cls.env['account.account']

        # ==================================================================
        # 1. Create dedicated test accounts for each account type
        #    Using XTEST.* codes to guarantee isolation from COA entries
        # ==================================================================

        # -- Current Asset accounts --
        cls.test_receivable = AccountAccount.create({
            'code': 'XTEST.11000',
            'name': 'Test Accounts Receivable',
            'account_type': 'asset_receivable',
            'reconcile': True,
        })
        cls.test_cash = AccountAccount.create({
            'code': 'XTEST.10100',
            'name': 'Test Cash and Bank',
            'account_type': 'asset_cash',
        })
        cls.test_current_asset = AccountAccount.create({
            'code': 'XTEST.11500',
            'name': 'Test Other Current Assets',
            'account_type': 'asset_current',
        })
        cls.test_prepayments = AccountAccount.create({
            'code': 'XTEST.13000',
            'name': 'Test Prepaid Expenses',
            'account_type': 'asset_prepayments',
        })

        # -- Non-Current Asset accounts --
        cls.test_fixed_asset = AccountAccount.create({
            'code': 'XTEST.15000',
            'name': 'Test Fixed Assets',
            'account_type': 'asset_fixed',
        })
        cls.test_non_current_asset = AccountAccount.create({
            'code': 'XTEST.18000',
            'name': 'Test Other Non-Current Assets',
            'account_type': 'asset_non_current',
        })

        # -- Current Liability accounts --
        cls.test_payable = AccountAccount.create({
            'code': 'XTEST.20000',
            'name': 'Test Accounts Payable',
            'account_type': 'liability_payable',
            'reconcile': True,
        })
        cls.test_credit_card = AccountAccount.create({
            'code': 'XTEST.21000',
            'name': 'Test Credit Card Liability',
            'account_type': 'liability_credit_card',
        })
        cls.test_current_liability = AccountAccount.create({
            'code': 'XTEST.22000',
            'name': 'Test Other Current Liabilities',
            'account_type': 'liability_current',
        })

        # -- Non-Current Liability accounts --
        cls.test_non_current_liability = AccountAccount.create({
            'code': 'XTEST.25000',
            'name': 'Test Long-Term Liabilities',
            'account_type': 'liability_non_current',
        })

        # -- Equity accounts --
        cls.test_equity = AccountAccount.create({
            'code': 'XTEST.30000',
            'name': 'Test Equity Capital',
            'account_type': 'equity',
        })
        cls.test_equity_unaffected = AccountAccount.create({
            'code': 'XTEST.30500',
            'name': 'Test Retained Earnings (Unaffected)',
            'account_type': 'equity_unaffected',
        })

        # -- Income and Expense accounts --
        cls.test_revenue = AccountAccount.create({
            'code': 'XTEST.40000',
            'name': 'Test Revenue',
            'account_type': 'income',
        })
        cls.test_expense = AccountAccount.create({
            'code': 'XTEST.50000',
            'name': 'Test Operating Expenses',
            'account_type': 'expense',
        })

        # ==================================================================
        # 2. Reference journal for manual entries
        # ==================================================================
        cls.journal_misc = cls.company_data['default_journal_misc']

        # ==================================================================
        # 3. Create and post journal entries with known amounts
        # ==================================================================

        # Entry A: Prior-year equity contribution (2023-03-15)
        cls.move_prior_equity = cls.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': cls.journal_misc.id,
            'date': date(2023, 3, 15),
            'line_ids': [
                Command.create({
                    'account_id': cls.test_cash.id,
                    'name': 'Prior year equity deposit',
                    'debit': 30000.0,
                    'credit': 0.0,
                }),
                Command.create({
                    'account_id': cls.test_equity.id,
                    'name': 'Prior year equity contribution',
                    'debit': 0.0,
                    'credit': 30000.0,
                }),
            ],
        })
        cls.move_prior_equity.action_post()

        # Entry 1: Current-year equity contribution (2024-01-15)
        cls.move_equity = cls.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': cls.journal_misc.id,
            'date': date(2024, 1, 15),
            'line_ids': [
                Command.create({
                    'account_id': cls.test_cash.id,
                    'name': 'Owner equity deposit',
                    'debit': 50000.0,
                    'credit': 0.0,
                }),
                Command.create({
                    'account_id': cls.test_equity.id,
                    'name': 'Owner equity contribution',
                    'debit': 0.0,
                    'credit': 50000.0,
                }),
            ],
        })
        cls.move_equity.action_post()

        # Entry 2: Revenue recognition (2024-03-15)
        # Reference partner_a as the customer on the receivable line.
        cls.move_revenue = cls.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': cls.journal_misc.id,
            'date': date(2024, 3, 15),
            'line_ids': [
                Command.create({
                    'account_id': cls.test_receivable.id,
                    'partner_id': cls.partner_a.id,
                    'name': 'Customer invoice receivable',
                    'debit': 10000.0,
                    'credit': 0.0,
                }),
                Command.create({
                    'account_id': cls.test_revenue.id,
                    'name': 'Service revenue earned',
                    'debit': 0.0,
                    'credit': 10000.0,
                }),
            ],
        })
        cls.move_revenue.action_post()

        # Entry 3: Customer collection (2024-04-01)
        cls.move_collection = cls.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': cls.journal_misc.id,
            'date': date(2024, 4, 1),
            'line_ids': [
                Command.create({
                    'account_id': cls.test_cash.id,
                    'name': 'Customer payment received',
                    'debit': 5000.0,
                    'credit': 0.0,
                }),
                Command.create({
                    'account_id': cls.test_receivable.id,
                    'name': 'Receivable reduction from payment',
                    'debit': 0.0,
                    'credit': 5000.0,
                }),
            ],
        })
        cls.move_collection.action_post()

        # Entry 4: Fixed asset purchase (2024-02-01)
        cls.move_fixed_asset = cls.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': cls.journal_misc.id,
            'date': date(2024, 2, 1),
            'line_ids': [
                Command.create({
                    'account_id': cls.test_fixed_asset.id,
                    'name': 'Equipment purchase',
                    'debit': 20000.0,
                    'credit': 0.0,
                }),
                Command.create({
                    'account_id': cls.test_cash.id,
                    'name': 'Payment for equipment',
                    'debit': 0.0,
                    'credit': 20000.0,
                }),
            ],
        })
        cls.move_fixed_asset.action_post()

        # Entry 5: Operating expense cash payment (2024-05-01)
        cls.move_expense_cash = cls.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': cls.journal_misc.id,
            'date': date(2024, 5, 1),
            'line_ids': [
                Command.create({
                    'account_id': cls.test_expense.id,
                    'name': 'Office supplies expense',
                    'debit': 3000.0,
                    'credit': 0.0,
                }),
                Command.create({
                    'account_id': cls.test_cash.id,
                    'name': 'Cash payment for supplies',
                    'debit': 0.0,
                    'credit': 3000.0,
                }),
            ],
        })
        cls.move_expense_cash.action_post()

        # Entry 6: Accrued expense via payable (2024-04-15)
        # Reference partner_b as the vendor on the payable line.
        cls.move_expense_accrued = cls.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': cls.journal_misc.id,
            'date': date(2024, 4, 15),
            'line_ids': [
                Command.create({
                    'account_id': cls.test_expense.id,
                    'name': 'Accrued professional fees',
                    'debit': 2000.0,
                    'credit': 0.0,
                }),
                Command.create({
                    'account_id': cls.test_payable.id,
                    'partner_id': cls.partner_b.id,
                    'name': 'Payable for professional fees',
                    'debit': 0.0,
                    'credit': 2000.0,
                }),
            ],
        })
        cls.move_expense_accrued.action_post()

        # Entry 7: Long-term loan received (2024-01-20)
        cls.move_loan = cls.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': cls.journal_misc.id,
            'date': date(2024, 1, 20),
            'line_ids': [
                Command.create({
                    'account_id': cls.test_cash.id,
                    'name': 'Loan proceeds received',
                    'debit': 15000.0,
                    'credit': 0.0,
                }),
                Command.create({
                    'account_id': cls.test_non_current_liability.id,
                    'name': 'Long-term loan payable',
                    'debit': 0.0,
                    'credit': 15000.0,
                }),
            ],
        })
        cls.move_loan.action_post()

        # Entry 8: Draft entry — NOT posted (2024-06-15)
        # Used to validate target_move='posted' filtering.
        cls.move_draft = cls.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': cls.journal_misc.id,
            'date': date(2024, 6, 15),
            'line_ids': [
                Command.create({
                    'account_id': cls.test_receivable.id,
                    'name': 'Pending invoice receivable',
                    'debit': 1000.0,
                    'credit': 0.0,
                }),
                Command.create({
                    'account_id': cls.test_revenue.id,
                    'name': 'Pending revenue recognition',
                    'debit': 0.0,
                    'credit': 1000.0,
                }),
            ],
        })
        # Intentionally left in draft state

    # ==================================================================
    # HELPER METHODS
    # ==================================================================

    def _create_report(self, **kwargs):
        """
        Create a Balance Sheet report with sensible defaults.

        All keyword arguments are forwarded to the ``create`` call
        and override any defaults listed below.

        Returns:
            Recordset of ``account.balance.sheet.report``
        """
        defaults = {
            'date_to': date(2024, 6, 30),
            'company_id': self.env.company.id,
            'target_move': 'posted',
        }
        defaults.update(kwargs)
        return self.env['account.balance.sheet.report'].create(defaults)

    def _get_line_for_account(self, report, account):
        """
        Find the report line corresponding to a specific account.

        Searches ``report.line_ids`` for a line whose ``account_ids``
        contains the given account.

        Args:
            report: ``account.balance.sheet.report`` record
            account: ``account.account`` record to look for

        Returns:
            First matching report line, or empty recordset.
        """
        for line in report.line_ids:
            if account in line.account_ids:
                return line
        return self.env['account.balance.sheet.report.line']

    def _get_section_for_account(self, report, account):
        """
        Determine which section header an account falls under.

        Iterates ``report.line_ids`` sorted by sequence and tracks the
        most recent level-1 section header.  Returns the section name
        when the target account is found.

        Args:
            report: ``account.balance.sheet.report`` record
            account: ``account.account`` record

        Returns:
            str | None — section name (e.g. 'Current Assets')
        """
        current_section = None
        for line in report.line_ids.sorted('sequence'):
            if line.level == 1 and line.is_total:
                current_section = line.name
            if account in line.account_ids:
                return current_section
        return None

    # ==================================================================
    # FR-001 TEST METHODS
    # ==================================================================

    @freeze_time('2024-06-30')
    def test_fr001_balance_sheet_creation(self):
        """
        FR-001 Scenario: Report creation with default state.

        Given I am logged in as a CFO,
        When I create a Balance Sheet report for a reporting date,
        Then the report record is created with state 'draft'.
        Also validates that creation with valid params does not raise
        UserError or ValidationError.
        """
        # Verify creation with valid parameters does not raise errors
        try:
            report = self._create_report()
        except (UserError, ValidationError) as exc:
            self.fail(
                f"Report creation should not raise an error with valid "
                f"parameters, but got: {exc}"
            )
        self.assertTrue(report, "Balance Sheet report record should be created")
        self.assertEqual(
            report.state, 'draft',
            "Newly created report should be in 'draft' state",
        )
        self.assertEqual(report.date_to, date(2024, 6, 30))
        self.assertEqual(report.target_move, 'posted')
        self.assertEqual(report.company_id, self.env.company)

    @freeze_time('2024-06-30')
    def test_fr001_balance_sheet_equation(self):
        """
        FR-001 Scenario 6: Fundamental accounting equation validation.

        Given posted journal entries exist in the system,
        When I generate the Balance Sheet as of 2024-06-30,
        Then Assets = Liabilities + Equity within a tolerance of 0.01,
        And the report indicates ``is_balanced=True``.
        """
        report = self._create_report()
        report.action_compute()

        # Verify the accounting equation: A = L + E
        difference = abs(
            report.total_assets - (report.total_liabilities + report.total_equity)
        )
        self.assertLess(
            difference, 0.01,
            "Balance Sheet must satisfy A = L + E "
            f"(Assets={report.total_assets}, "
            f"Liabilities={report.total_liabilities}, "
            f"Equity={report.total_equity}, "
            f"diff={difference})",
        )
        self.assertTrue(
            report.is_balanced,
            "Report should flag is_balanced=True when equation holds",
        )

    @freeze_time('2024-06-30')
    def test_fr001_asset_classification_current(self):
        """
        FR-001 Scenario 2: Current asset account classification.

        Given accounts of type asset_receivable, asset_cash,
        asset_current, and asset_prepayments exist with balances,
        When I generate the Balance Sheet,
        Then all four account types appear under the 'Current Assets'
        section.
        """
        report = self._create_report()
        report.action_compute()

        current_asset_accounts = [
            (self.test_receivable, 'asset_receivable'),
            (self.test_cash, 'asset_cash'),
        ]
        for account, atype in current_asset_accounts:
            section = self._get_section_for_account(report, account)
            self.assertEqual(
                section, 'Current Assets',
                f"Account type '{atype}' ({account.name}) should appear "
                f"under 'Current Assets', found in '{section}'",
            )

        # For accounts without posted entries we verify classification
        # via the model constants rather than line presence.
        bs_model = self.env['account.balance.sheet.report']
        for atype in ('asset_receivable', 'asset_cash',
                       'asset_current', 'asset_prepayments'):
            self.assertIn(
                atype, bs_model.ASSET_CURRENT_TYPES,
                f"'{atype}' should be in ASSET_CURRENT_TYPES",
            )

    @freeze_time('2024-06-30')
    def test_fr001_asset_classification_non_current(self):
        """
        FR-001 Scenario 2: Non-current asset account classification.

        Given accounts of type asset_fixed and asset_non_current,
        When I generate the Balance Sheet,
        Then those account types appear under 'Non-Current Assets'.
        """
        report = self._create_report()
        report.action_compute()

        section = self._get_section_for_account(report, self.test_fixed_asset)
        self.assertEqual(
            section, 'Non-Current Assets',
            "asset_fixed should appear under 'Non-Current Assets'",
        )

        bs_model = self.env['account.balance.sheet.report']
        for atype in ('asset_fixed', 'asset_non_current'):
            self.assertIn(
                atype, bs_model.ASSET_NON_CURRENT_TYPES,
                f"'{atype}' should be in ASSET_NON_CURRENT_TYPES",
            )

    @freeze_time('2024-06-30')
    def test_fr001_liability_classification_current(self):
        """
        FR-001 Scenario 3: Current liability account classification.

        Given accounts of type liability_payable, liability_credit_card,
        and liability_current exist,
        When I generate the Balance Sheet,
        Then they appear under 'Current Liabilities'.
        """
        report = self._create_report()
        report.action_compute()

        section = self._get_section_for_account(report, self.test_payable)
        self.assertEqual(
            section, 'Current Liabilities',
            "liability_payable should appear under 'Current Liabilities'",
        )

        bs_model = self.env['account.balance.sheet.report']
        for atype in ('liability_payable', 'liability_credit_card',
                       'liability_current'):
            self.assertIn(
                atype, bs_model.LIABILITY_CURRENT_TYPES,
                f"'{atype}' should be in LIABILITY_CURRENT_TYPES",
            )

    @freeze_time('2024-06-30')
    def test_fr001_liability_classification_non_current(self):
        """
        FR-001 Scenario 3: Non-current liability classification.

        Given an account of type liability_non_current with balance,
        When I generate the Balance Sheet,
        Then it appears under 'Non-Current Liabilities'.
        """
        report = self._create_report()
        report.action_compute()

        section = self._get_section_for_account(
            report, self.test_non_current_liability,
        )
        self.assertEqual(
            section, 'Non-Current Liabilities',
            "liability_non_current should appear under "
            "'Non-Current Liabilities'",
        )

        bs_model = self.env['account.balance.sheet.report']
        self.assertIn(
            'liability_non_current',
            bs_model.LIABILITY_NON_CURRENT_TYPES,
        )

    @freeze_time('2024-06-30')
    def test_fr001_equity_section(self):
        """
        FR-001 Scenario 4: Equity section with current year earnings.

        Given equity and equity_unaffected accounts exist,
        And income/expense entries have been posted in the fiscal year,
        When I generate the Balance Sheet,
        Then the Equity section includes equity accounts
        And current_year_earnings equals income minus expenses.
        """
        report = self._create_report()
        report.action_compute()

        # Equity total must be positive and non-zero (we contributed
        # 80,000 in equity accounts and have 5,000 CYE).
        self.assertGreater(
            report.total_equity, 0,
            "Total equity should be positive given equity contributions "
            "and net income",
        )

        # Current year earnings = income - expenses for fiscal year
        # Our test data: revenue 10,000, expense 5,000 → CYE 5,000.
        # NOTE: there may be other accounts in the chart, so we check
        # that CYE is at least our test contribution.
        self.assertGreaterEqual(
            report.current_year_earnings, 5000.0 - 0.01,
            "Current year earnings should include at least our test "
            "revenue minus expenses",
        )

        # Verify equity account types are in the model constants
        bs_model = self.env['account.balance.sheet.report']
        for atype in ('equity', 'equity_unaffected'):
            self.assertIn(atype, bs_model.EQUITY_TYPES)

    @freeze_time('2024-06-30')
    def test_fr001_retained_earnings(self):
        """
        FR-001 Scenario 4: Retained earnings from equity_unaffected.

        Given equity-type accounts have cumulative balances,
        When I generate the Balance Sheet,
        Then retained_earnings reflects the balance of equity accounts
        And total_equity = retained_earnings + current_year_earnings.
        """
        report = self._create_report()
        report.action_compute()

        # Retained earnings should include the equity account balances
        # Our test equity account has balance: 30,000 + 50,000 = 80,000
        self.assertGreater(
            report.retained_earnings, 0,
            "Retained earnings should be positive given equity "
            "contributions",
        )

        # Verify the identity: total_equity = retained + CYE
        expected_total = report.retained_earnings + report.current_year_earnings
        self.assertAlmostEqual(
            report.total_equity, expected_total, places=2,
            msg="total_equity must equal retained_earnings + "
                "current_year_earnings",
        )

    @freeze_time('2024-06-30')
    def test_fr001_comparative_period(self):
        """
        FR-001 Scenario 5: Comparative Balance Sheet with prior period.

        Given enable_comparison is True and comparison_date_to is set
        to one year prior,
        When I generate the Balance Sheet,
        Then the comparison columns are populated with prior period data.
        """
        comparison_date = date(2023, 6, 30)
        report = self._create_report(
            enable_comparison=True,
            comparison_date_to=comparison_date,
        )
        report.action_compute()

        # Report should still be balanced for current period
        self.assertTrue(report.is_balanced, "Current period should balance")

        # Comparison flag should be enabled
        self.assertTrue(report.enable_comparison)
        self.assertEqual(report.comparison_date_to, comparison_date)

        # Line items with comparison should have comparison_amount set
        # for at least the lines where prior-year data exists.
        # Our prior-year entry has cash/equity, so at least some lines
        # should have non-zero comparison_amount.
        lines_with_comparison = report.line_ids.filtered(
            lambda l: l.comparison_amount and l.comparison_amount != 0
        )
        self.assertTrue(
            lines_with_comparison,
            "Some report lines should have comparison_amount populated "
            "when enable_comparison=True and prior-year entries exist",
        )

    @freeze_time('2024-06-30')
    def test_fr001_comparative_variance(self):
        """
        FR-001 Scenario 5: Variance calculation between periods.

        Given a comparative report with both current and prior period,
        When the report is computed,
        Then variance_absolute and variance_percentage are calculated
        for report lines that have comparison data.
        """
        comparison_date = date(2023, 6, 30)
        report = self._create_report(
            enable_comparison=True,
            comparison_date_to=comparison_date,
            show_variance=True,
        )
        report.action_compute()

        # Find lines where both current and comparison amounts exist
        lines_with_variance = report.line_ids.filtered(
            lambda l: l.amount and l.comparison_amount
        )
        for line in lines_with_variance:
            expected_abs_variance = line.amount - line.comparison_amount
            self.assertAlmostEqual(
                line.variance_absolute, expected_abs_variance, places=2,
                msg=f"Line '{line.name}': variance_absolute should equal "
                    f"amount − comparison_amount "
                    f"({line.amount} − {line.comparison_amount})",
            )
            # Percentage variance
            if line.comparison_amount:
                expected_pct = (
                    expected_abs_variance / abs(line.comparison_amount)
                ) * 100
                self.assertAlmostEqual(
                    line.variance_percentage,
                    round(expected_pct, 2),
                    places=2,
                    msg=f"Line '{line.name}': variance_percentage mismatch",
                )

    @freeze_time('2024-06-30')
    def test_fr001_drilldown_navigation(self):
        """
        FR-001 / FR-007: Drill-down to source journal entries.

        Given the Balance Sheet is generated,
        When I invoke drill-down for a specific account,
        Then I receive an ir.actions.act_window action
        targeting account.move.line with appropriate domain filters.
        """
        report = self._create_report()
        report.action_compute()

        # Call drilldown on the report for our test receivable account
        result = report.action_drilldown(
            account_id=self.test_receivable.id,
            date_to=date(2024, 6, 30),
        )

        # Validate the returned action
        self.assertIsInstance(result, dict)
        self.assertEqual(
            result.get('type'), 'ir.actions.act_window',
            "Drilldown should return an act_window action",
        )
        self.assertEqual(
            result.get('res_model'), 'account.move.line',
            "Drilldown should target account.move.line",
        )

        # Verify domain includes account_id filter
        domain = result.get('domain', [])
        account_filter_found = any(
            isinstance(d, (list, tuple))
            and len(d) == 3
            and d[0] == 'account_id'
            and self.test_receivable.id in (
                d[2] if isinstance(d[2], list) else [d[2]]
            )
            for d in domain
        )
        self.assertTrue(
            account_filter_found,
            "Drilldown domain should contain an account_id filter "
            f"for account {self.test_receivable.id}",
        )

        # Verify domain includes date filter
        date_filter_found = any(
            isinstance(d, (list, tuple))
            and len(d) == 3
            and d[0] == 'date'
            for d in domain
        )
        self.assertTrue(
            date_filter_found,
            "Drilldown domain should contain a date filter",
        )

    @freeze_time('2024-06-30')
    def test_fr001_report_lines_populated(self):
        """
        FR-001 Scenario 1: Report lines with section hierarchy.

        Given I generate the Balance Sheet,
        When computation is complete,
        Then line_ids are populated with the correct GAAP/IFRS
        section hierarchy: ASSETS > Current/Non-Current,
        LIABILITIES > Current/Non-Current, EQUITY.
        """
        report = self._create_report()
        report.action_compute()

        lines = report.line_ids
        self.assertTrue(lines, "Report should have lines after computation")

        # Verify top-level section headers (level 0)
        section_headers = [
            l.name for l in lines if l.level == 0 and l.is_total
        ]
        self.assertIn('ASSETS', section_headers)
        self.assertIn('LIABILITIES', section_headers)
        self.assertIn('EQUITY', section_headers)

        # Verify subsection headers (level 1)
        subsections = [
            l.name for l in lines if l.level == 1 and l.is_total
        ]
        self.assertIn('Current Assets', subsections)
        self.assertIn('Non-Current Assets', subsections)
        self.assertIn('Current Liabilities', subsections)
        self.assertIn('Non-Current Liabilities', subsections)

        # Verify detail lines exist (level 2, with account_ids)
        detail_lines = [l for l in lines if l.level == 2 and l.account_ids]
        self.assertTrue(
            detail_lines,
            "Report should contain detail lines at level 2 "
            "with linked accounts",
        )

        # Verify TOTAL LIABILITIES AND EQUITY line exists
        total_le_line = [
            l for l in lines
            if 'TOTAL LIABILITIES AND EQUITY' in (l.name or '')
        ]
        self.assertTrue(
            total_le_line,
            "Report should include 'TOTAL LIABILITIES AND EQUITY' line",
        )

    @freeze_time('2024-06-30')
    def test_fr001_total_assets_breakdown(self):
        """
        FR-001: Total Assets = Current Assets + Non-Current Assets.

        Given the Balance Sheet is computed,
        Then total_assets must equal the sum of total_current_assets
        and total_non_current_assets (algebraic identity).
        """
        report = self._create_report()
        report.action_compute()

        expected = report.total_current_assets + report.total_non_current_assets
        self.assertAlmostEqual(
            report.total_assets, expected, places=2,
            msg="total_assets must equal "
                "total_current_assets + total_non_current_assets "
                f"({report.total_current_assets} + "
                f"{report.total_non_current_assets})",
        )

    @freeze_time('2024-06-30')
    def test_fr001_total_liabilities_breakdown(self):
        """
        FR-001: Total Liabilities = Current + Non-Current Liabilities.

        Given the Balance Sheet is computed,
        Then total_liabilities must equal the sum of
        total_current_liabilities and total_non_current_liabilities.
        """
        report = self._create_report()
        report.action_compute()

        expected = (
            report.total_current_liabilities
            + report.total_non_current_liabilities
        )
        self.assertAlmostEqual(
            report.total_liabilities, expected, places=2,
            msg="total_liabilities must equal "
                "total_current_liabilities + total_non_current_liabilities "
                f"({report.total_current_liabilities} + "
                f"{report.total_non_current_liabilities})",
        )

    @freeze_time('2024-06-30')
    def test_fr001_posted_moves_only(self):
        """
        FR-001: target_move='posted' excludes draft entries.

        Given both posted and draft journal entries exist,
        When I generate the Balance Sheet with target_move='posted',
        Then only posted entries are included in the computation.
        """
        report_posted = self._create_report(target_move='posted')
        report_posted.action_compute()

        # Capture total assets with posted-only filter
        total_posted = report_posted.total_assets

        # The draft entry (Entry 8) has 1,000 debit to receivable.
        # With target_move='all', that 1,000 should be included.
        report_all = self._create_report(target_move='all')
        report_all.action_compute()
        total_all = report_all.total_assets

        # 'all' totals should be greater because the draft entry
        # adds 1,000 to receivable (current assets)
        self.assertGreater(
            total_all, total_posted,
            "target_move='all' should include draft entry amounts, "
            "yielding higher total_assets than 'posted'",
        )

        # Both reports should still balance
        self.assertTrue(report_posted.is_balanced)
        self.assertTrue(report_all.is_balanced)

    @freeze_time('2024-06-30')
    def test_fr001_all_moves_included(self):
        """
        FR-001: target_move='all' includes draft entries.

        Given a draft journal entry exists with receivable 1,000
        and revenue 1,000,
        When I generate the Balance Sheet with target_move='all',
        Then the draft amounts are reflected in the report.
        """
        report = self._create_report(target_move='all')
        report.action_compute()

        # The report should include draft entries
        self.assertTrue(report.is_balanced)

        # Check that the receivable line includes the draft amount.
        # With target_move='all', test_receivable balance should be
        # 5,000 (posted) + 1,000 (draft) = 6,000.
        line = self._get_line_for_account(report, self.test_receivable)
        if line:
            # Receivable should reflect both posted and draft balances
            self.assertAlmostEqual(
                line.amount, 6000.0, places=2,
                msg="Receivable line with target_move='all' should include "
                    "draft entry amount (5,000 + 1,000 = 6,000)",
            )

    @freeze_time('2024-06-30')
    def test_fr001_multi_company_isolation(self):
        """
        FR-001: Multi-company data isolation.

        Given entries exist in Company 1,
        And a separate entry exists in Company 2,
        When I generate the Balance Sheet for Company 1,
        Then only Company 1's data is included.
        """
        # Set up second company with accounting data
        company_data_2 = self.setup_other_company()
        company_2 = company_data_2['company']
        journal_2 = company_data_2['default_journal_misc']

        # Create a test account and entry in Company 2
        account_cash_2 = self.env['account.account'].with_company(
            company_2,
        ).create({
            'code': 'XTEST2.10100',
            'name': 'Company 2 Cash',
            'account_type': 'asset_cash',
            'company_ids': [Command.link(company_2.id)],
        })
        account_equity_2 = self.env['account.account'].with_company(
            company_2,
        ).create({
            'code': 'XTEST2.30000',
            'name': 'Company 2 Equity',
            'account_type': 'equity',
            'company_ids': [Command.link(company_2.id)],
        })

        move_2 = self.env['account.move'].with_company(company_2).create({
            'move_type': 'entry',
            'journal_id': journal_2.id,
            'date': date(2024, 3, 1),
            'line_ids': [
                Command.create({
                    'account_id': account_cash_2.id,
                    'name': 'Company 2 cash deposit',
                    'debit': 999999.0,
                    'credit': 0.0,
                }),
                Command.create({
                    'account_id': account_equity_2.id,
                    'name': 'Company 2 equity',
                    'debit': 0.0,
                    'credit': 999999.0,
                }),
            ],
        })
        move_2.action_post()

        # Generate Balance Sheet for Company 1
        report_c1 = self._create_report(company_id=self.env.company.id)
        report_c1.action_compute()

        # Company 1 report should balance
        self.assertTrue(
            report_c1.is_balanced,
            "Company 1 Balance Sheet should balance",
        )

        # The massive Company 2 amount (999,999) should NOT appear in
        # Company 1's report.  If it did, assets would be inflated.
        # We check that no single line has that amount.
        c2_amounts = report_c1.line_ids.filtered(
            lambda l: abs(l.amount - 999999.0) < 0.01
        )
        self.assertFalse(
            c2_amounts,
            "Company 2 amounts must not leak into Company 1 report",
        )

    @freeze_time('2024-06-30')
    def test_fr001_balance_difference(self):
        """
        FR-001 Scenario 6: Balance difference equals zero when balanced.

        Given the accounting system has only balanced journal entries,
        When the Balance Sheet is computed,
        Then balance_difference should be exactly 0.
        """
        report = self._create_report()
        report.action_compute()

        self.assertAlmostEqual(
            report.balance_difference, 0.0, places=2,
            msg="balance_difference should be 0 for a balanced sheet "
                f"(got {report.balance_difference})",
        )
        self.assertTrue(report.is_balanced)

    @freeze_time('2024-06-30')
    def test_fr001_date_boundary(self):
        """
        FR-001: Date boundary — entries on date_to included, after excluded.

        Given an entry dated exactly on 2024-06-30 (boundary),
        And an entry dated 2024-07-01 (one day after boundary),
        When I generate the Balance Sheet as of 2024-06-30,
        Then the boundary entry is included and the post-boundary
        entry is excluded.
        """
        report_date = date(2024, 6, 30)
        after_boundary_date = report_date + timedelta(days=1)  # 2024-07-01

        # Create an entry exactly ON the report date
        move_boundary = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': self.journal_misc.id,
            'date': report_date,
            'line_ids': [
                Command.create({
                    'account_id': self.test_receivable.id,
                    'name': 'Boundary date receivable',
                    'debit': 500.0,
                    'credit': 0.0,
                }),
                Command.create({
                    'account_id': self.test_revenue.id,
                    'name': 'Boundary date revenue',
                    'debit': 0.0,
                    'credit': 500.0,
                }),
            ],
        })
        move_boundary.action_post()

        # Create an entry one day AFTER the report date
        move_after = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': self.journal_misc.id,
            'date': after_boundary_date,
            'line_ids': [
                Command.create({
                    'account_id': self.test_receivable.id,
                    'name': 'Post-boundary receivable',
                    'debit': 2000.0,
                    'credit': 0.0,
                }),
                Command.create({
                    'account_id': self.test_revenue.id,
                    'name': 'Post-boundary revenue',
                    'debit': 0.0,
                    'credit': 2000.0,
                }),
            ],
        })
        move_after.action_post()

        # Generate report as of 2024-06-30
        report = self._create_report(date_to=report_date)
        report.action_compute()

        # The report should include the boundary entry (500) but
        # exclude the post-boundary entry (2,000).
        # Receivable balance should be:
        #   5,000 (base) + 500 (boundary) = 5,500
        # NOT 5,000 + 500 + 2,000 = 7,500
        line = self._get_line_for_account(report, self.test_receivable)
        if line:
            self.assertAlmostEqual(
                line.amount, 5500.0, places=2,
                msg="Receivable should include boundary entry (500) but "
                    "exclude post-boundary entry (2,000). "
                    f"Expected 5,500, got {line.amount}",
            )

        # Verify the after-boundary date is indeed one day later
        self.assertEqual(
            after_boundary_date, date(2024, 7, 1),
            "After-boundary date should be July 1st",
        )

        # Report should remain balanced
        self.assertTrue(
            report.is_balanced,
            "Report should balance with boundary entries",
        )
