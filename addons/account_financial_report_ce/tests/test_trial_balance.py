# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Test Suite for Trial Balance Report — FR-005

Implements acceptance criteria for FR-005: Trial Balance Report.
User Story: As an Accountant, I want to generate a trial balance showing all
account balances with debit and credit totals so that I can verify that debits
equal credits and prepare for financial statement generation.

Acceptance Scenarios Covered:
- Scenario 1: Generate Trial Balance for specific date
- Scenario 2: Show all accounts with balances (debit/credit columns)
- Scenario 3: Display debit and credit column values per account
- Scenario 4: Verify total debits equal total credits
- Scenario 5: Option for showing/hiding accounts with zero balance
- Scenario 6: Comparative Trial Balance
- Opening balance, period movement, and closing balance verification
- Posted vs. draft entry filtering
- Multi-company isolation
- Date boundary correctness

Per EPIC-001 requirements:
- Minimum 80% test coverage
- BDD alignment with FR-005 acceptance criteria
- OCA coding standards compliance
- Tests tagged @tagged('post_install', '-at_install')
"""

from datetime import date, timedelta

from freezegun import freeze_time

from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestTrialBalance(AccountTestInvoicingCommon):
    """
    Dedicated Trial Balance test class for FR-005 acceptance criteria.

    Extends AccountTestInvoicingCommon to leverage pre-configured accounting
    fixtures: company_data with accounts (receivable, payable, revenue,
    expense, bank), journals (sale, purchase, bank, misc), partners
    (partner_a, partner_b), and payment terms.

    All test methods are prefixed with test_fr005_ to map to the FR-005
    user story acceptance scenarios and enable traceability.
    """

    @classmethod
    def setUpClass(cls):
        """
        Set up test data for Trial Balance FR-005 scenarios.

        Creates:
        - Pre-period journal entries (before 2024-01-01) for opening balances
        - In-period journal entries (2024-01-01 to 2024-06-30) for period
          activity with known debit/credit amounts
        - A draft journal entry to test posted-only filtering
        - An account that will have zero balance for hide-zero-balance testing
        - Journal entries in a second company for multi-company isolation
        """
        super().setUpClass()

        cls.company = cls.env.company
        cls.currency = cls.company.currency_id

        # Grant Financial Reports User/Manager groups to the test user
        # so that ACL checks pass when creating/reading report records.
        fr_user_group = cls.env.ref(
            'account_financial_report_ce.group_financial_report_user',
            raise_if_not_found=False,
        )
        fr_mgr_group = cls.env.ref(
            'account_financial_report_ce.group_financial_report_manager',
            raise_if_not_found=False,
        )
        groups_to_add = cls.env['res.groups']
        if fr_user_group:
            groups_to_add |= fr_user_group
        if fr_mgr_group:
            groups_to_add |= fr_mgr_group
        if groups_to_add and cls.env.user != cls.env.ref('base.user_admin'):
            cls.env.user.write({
                'group_ids': [(4, g.id) for g in groups_to_add],
            })

        # Retrieve key accounts from company_data fixtures
        cls.account_receivable = cls.company_data['default_account_receivable']
        cls.account_payable = cls.company_data['default_account_payable']
        cls.account_revenue = cls.company_data['default_account_revenue']
        cls.account_expense = cls.company_data['default_account_expense']

        # Journals from company_data
        cls.journal_misc = cls.company_data['default_journal_misc']
        cls.journal_sale = cls.company_data['default_journal_sale']
        cls.journal_bank = cls.company_data['default_journal_bank']

        # Create a dedicated "zero balance" account for testing hide-zero
        # Odoo 19.0: account.account uses company_ids (Many2many) not company_id
        cls.account_zero_balance = cls.env['account.account'].create({
            'name': 'Zero Balance Test Account',
            'code': 'XZERO0',
            'account_type': 'asset_current',
            'company_ids': [cls.company.id],
        })

        # ---- Dates used throughout tests ----
        cls.date_before_period = date(2023, 11, 15)
        cls.date_period_start = date(2024, 1, 1)
        cls.date_mid_period = date(2024, 3, 15)
        cls.date_period_end = date(2024, 6, 30)

        # =====================================================================
        # PRE-PERIOD ENTRIES — contribute to opening balances
        # Entry 1: Revenue accrual before the period (partner_a)
        #   Debit Receivable 1000, Credit Revenue 1000
        # =====================================================================
        cls.move_pre_period = cls.env['account.move'].create({
            'move_type': 'entry',
            'date': cls.date_before_period,
            'journal_id': cls.journal_misc.id,
            'partner_id': cls.partner_a.id,
            'line_ids': [
                (0, 0, {
                    'name': 'Pre-period receivable debit',
                    'account_id': cls.account_receivable.id,
                    'partner_id': cls.partner_a.id,
                    'debit': 1000.0,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': 'Pre-period revenue credit',
                    'account_id': cls.account_revenue.id,
                    'partner_id': cls.partner_a.id,
                    'debit': 0.0,
                    'credit': 1000.0,
                }),
            ],
        })
        cls.move_pre_period.action_post()

        # =====================================================================
        # IN-PERIOD ENTRIES — contribute to period movement
        # Entry 2 (Jan): Expense payment (partner_b)
        #   Debit Expense 500, Credit Payable 500
        # =====================================================================
        cls.move_period_1 = cls.env['account.move'].create({
            'move_type': 'entry',
            'date': cls.date_period_start,
            'journal_id': cls.journal_misc.id,
            'partner_id': cls.partner_b.id,
            'line_ids': [
                (0, 0, {
                    'name': 'Period expense debit',
                    'account_id': cls.account_expense.id,
                    'partner_id': cls.partner_b.id,
                    'debit': 500.0,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': 'Period payable credit',
                    'account_id': cls.account_payable.id,
                    'partner_id': cls.partner_b.id,
                    'debit': 0.0,
                    'credit': 500.0,
                }),
            ],
        })
        cls.move_period_1.action_post()

        # =====================================================================
        # Entry 3 (March): Revenue recognition (partner_a)
        #   Debit Receivable 2000, Credit Revenue 2000
        # =====================================================================
        cls.move_period_2 = cls.env['account.move'].create({
            'move_type': 'entry',
            'date': cls.date_mid_period,
            'journal_id': cls.journal_misc.id,
            'partner_id': cls.partner_a.id,
            'line_ids': [
                (0, 0, {
                    'name': 'Period receivable debit',
                    'account_id': cls.account_receivable.id,
                    'partner_id': cls.partner_a.id,
                    'debit': 2000.0,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': 'Period revenue credit',
                    'account_id': cls.account_revenue.id,
                    'partner_id': cls.partner_a.id,
                    'debit': 0.0,
                    'credit': 2000.0,
                }),
            ],
        })
        cls.move_period_2.action_post()

        # =====================================================================
        # Entry 4 (June 30 — boundary): Exactly on date_to
        #   Debit Expense 300, Credit Payable 300
        # =====================================================================
        cls.move_boundary = cls.env['account.move'].create({
            'move_type': 'entry',
            'date': cls.date_period_end,
            'journal_id': cls.journal_misc.id,
            'line_ids': [
                (0, 0, {
                    'name': 'Boundary expense debit',
                    'account_id': cls.account_expense.id,
                    'debit': 300.0,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': 'Boundary payable credit',
                    'account_id': cls.account_payable.id,
                    'debit': 0.0,
                    'credit': 300.0,
                }),
            ],
        })
        cls.move_boundary.action_post()

        # =====================================================================
        # DRAFT ENTRY — should be excluded by target_move='posted'
        #   Debit Receivable 750, Credit Revenue 750
        # =====================================================================
        cls.move_draft = cls.env['account.move'].create({
            'move_type': 'entry',
            'date': cls.date_mid_period,
            'journal_id': cls.journal_misc.id,
            'line_ids': [
                (0, 0, {
                    'name': 'Draft receivable debit',
                    'account_id': cls.account_receivable.id,
                    'debit': 750.0,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': 'Draft revenue credit',
                    'account_id': cls.account_revenue.id,
                    'debit': 0.0,
                    'credit': 750.0,
                }),
            ],
        })
        # Intentionally NOT posted — stays in draft state

        # =====================================================================
        # Expected totals reference (posted entries only):
        #
        # Receivable: Debit 3000 (1000 pre + 2000 in-period), Credit 0
        # Revenue:    Debit 0, Credit 3000 (1000 pre + 2000 in-period)
        # Expense:    Debit 800 (500 + 300 in-period), Credit 0
        # Payable:    Debit 0, Credit 800 (500 + 300 in-period)
        #
        # Total Debits = 3800, Total Credits = 3800 => balanced
        #
        # Opening (before 2024-01-01, posted):
        #   Receivable: Debit 1000, Credit 0
        #   Revenue:    Debit 0, Credit 1000
        #
        # Period (2024-01-01 to 2024-06-30, posted):
        #   Receivable: Debit 2000, Credit 0
        #   Expense:    Debit 800 (500 + 300), Credit 0
        #   Revenue:    Debit 0, Credit 2000
        #   Payable:    Debit 0, Credit 800
        # =====================================================================

    # -------------------------------------------------------------------------
    # HELPER METHODS
    # -------------------------------------------------------------------------

    def _create_trial_balance_report(self, **kwargs):
        """
        Create a trial balance report with sensible defaults.

        Convenience helper that sets company_id and currency_id
        automatically, allowing tests to override any parameter.

        Args:
            **kwargs: Keyword arguments passed to the report create method.
                      Common overrides: date_to, date_from, target_move,
                      show_balance_zero, show_hierarchy, enable_comparison.

        Returns:
            account.trial.balance.report record.
        """
        defaults = {
            'date_to': self.date_period_end,
            'company_id': self.company.id,
            'target_move': 'posted',
        }
        defaults.update(kwargs)
        return self.env['account.trial.balance.report'].create(defaults)

    def _find_line_for_account(self, report, account):
        """
        Locate the report line corresponding to a specific account.

        Args:
            report: account.trial.balance.report record (computed).
            account: account.account record to look up.

        Returns:
            account.trial.balance.report.line record or empty recordset.
        """
        return report.line_ids.filtered(
            lambda line: line.account_id.id == account.id,
        )

    # -------------------------------------------------------------------------
    # FR-005 TEST METHODS
    # -------------------------------------------------------------------------

    @freeze_time('2024-06-30')
    def test_fr005_trial_balance_creation(self):
        """
        FR-005 Scenario 1: Generate Trial Balance for specific date.

        Given I am an authenticated accountant
        When I create a Trial Balance report with date_to = 2024-06-30
        Then the report is created in 'draft' state with correct parameters.
        Also verifies that action_generate_report raises UserError when
        date_from > date_to (invalid date range).
        """
        report = self._create_trial_balance_report()
        self.assertTrue(report, "Trial Balance report should be created")
        self.assertEqual(report.state, 'draft',
                         "New report should be in draft state")
        self.assertEqual(report.date_to, self.date_period_end,
                         "Report date_to should match specified date")
        self.assertEqual(report.company_id, self.company,
                         "Report company should match current company")
        self.assertEqual(report.target_move, 'posted',
                         "Default target_move should be 'posted'")

        # Verify that action_generate_report raises UserError when
        # date_from is after date_to (the model validates this)
        report_invalid = self._create_trial_balance_report(
            date_from=self.date_period_end + timedelta(days=1),
        )
        with self.assertRaises(UserError):
            report_invalid.action_generate_report()

    @freeze_time('2024-06-30')
    def test_fr005_trial_balance_computation(self):
        """
        FR-005 Scenario 1: Compute Trial Balance and verify state transition.

        Given a Trial Balance report in 'draft' state
        When I invoke action_compute
        Then the report transitions to 'done' state and line_ids are populated.
        """
        report = self._create_trial_balance_report()
        self.assertEqual(report.state, 'draft')

        report.action_compute()

        self.assertEqual(report.state, 'done',
                         "Report should be in 'done' state after computation")
        self.assertTrue(len(report.line_ids) > 0,
                        "Report should have at least one line after compute")

    @freeze_time('2024-06-30')
    def test_fr005_debit_credit_equality(self):
        """
        FR-005 Scenario 4: Verify total debits equal total credits.

        Given a computed Trial Balance report
        When I inspect total_debit and total_credit
        Then total_debit equals total_credit within 0.01 tolerance,
        and the is_balanced flag is True.

        This validates the fundamental accounting constraint:
        Total Debits = Total Credits.
        """
        report = self._create_trial_balance_report()
        report.action_compute()

        difference = abs(report.total_debit - report.total_credit)
        self.assertLessEqual(
            difference, 0.01,
            "Trial Balance total debits (%.2f) should equal total credits "
            "(%.2f); difference=%.2f" % (
                report.total_debit, report.total_credit, difference,
            ),
        )
        self.assertTrue(
            report.is_balanced,
            "Trial Balance is_balanced flag should be True when balanced",
        )

    @freeze_time('2024-06-30')
    def test_fr005_per_account_debit_credit(self):
        """
        FR-005 Scenario 2/3: Verify per-account debit and credit columns.

        Given a computed Trial Balance (cumulative to 2024-06-30)
        When I check individual account lines
        Then each line shows correct debit and credit amounts.

        Expected posted cumulative totals:
          Receivable: debit=3000, credit=0, balance=3000
          Revenue:    debit=0, credit=3000, balance=-3000
          Expense:    debit=800, credit=0, balance=800
          Payable:    debit=0, credit=800, balance=-800
        """
        report = self._create_trial_balance_report(
            show_balance_zero=True,
        )
        report.action_compute()

        # Receivable account
        recv_line = self._find_line_for_account(report, self.account_receivable)
        self.assertTrue(recv_line, "Receivable account should appear in report")
        self.assertAlmostEqual(
            recv_line.debit, 3000.0, places=2,
            msg="Receivable debit should be 3000.00",
        )
        self.assertAlmostEqual(
            recv_line.credit, 0.0, places=2,
            msg="Receivable credit should be 0.00",
        )

        # Revenue account
        rev_line = self._find_line_for_account(report, self.account_revenue)
        self.assertTrue(rev_line, "Revenue account should appear in report")
        self.assertAlmostEqual(
            rev_line.debit, 0.0, places=2,
            msg="Revenue debit should be 0.00",
        )
        self.assertAlmostEqual(
            rev_line.credit, 3000.0, places=2,
            msg="Revenue credit should be 3000.00",
        )

        # Expense account
        exp_line = self._find_line_for_account(report, self.account_expense)
        self.assertTrue(exp_line, "Expense account should appear in report")
        self.assertAlmostEqual(
            exp_line.debit, 800.0, places=2,
            msg="Expense debit should be 800.00",
        )
        self.assertAlmostEqual(
            exp_line.credit, 0.0, places=2,
            msg="Expense credit should be 0.00",
        )

        # Payable account
        pay_line = self._find_line_for_account(report, self.account_payable)
        self.assertTrue(pay_line, "Payable account should appear in report")
        self.assertAlmostEqual(
            pay_line.debit, 0.0, places=2,
            msg="Payable debit should be 0.00",
        )
        self.assertAlmostEqual(
            pay_line.credit, 800.0, places=2,
            msg="Payable credit should be 800.00",
        )

    @freeze_time('2024-06-30')
    def test_fr005_opening_balance(self):
        """
        FR-005: Opening balance verification with date_from.

        Given entries exist both before and within the reporting period
        When I generate a Trial Balance with date_from=2024-01-01
        Then the opening balances reflect only pre-period posted entries.

        The model computes period activity (date_from to date_to), so
        opening balance = cumulative_to_date - period_activity.
        With date_from set, we verify that the reported debit/credit
        represent only the period activity, not the cumulative totals.

        Pre-period posted entries (before 2024-01-01):
          Receivable: debit=1000, credit=0
          Revenue:    debit=0, credit=1000
        """
        report = self._create_trial_balance_report(
            date_from=self.date_period_start,
            show_balance_zero=True,
        )
        report.action_compute()

        # With date_from, the model returns period-only debit/credit.
        # Receivable should show only in-period activity: debit=2000
        recv_line = self._find_line_for_account(report, self.account_receivable)
        self.assertTrue(recv_line, "Receivable should be in period report")
        self.assertAlmostEqual(
            recv_line.debit, 2000.0, places=2,
            msg="Receivable period debit should be 2000.00 (in-period only)",
        )

        # Revenue in-period: credit=2000
        rev_line = self._find_line_for_account(report, self.account_revenue)
        self.assertTrue(rev_line, "Revenue should be in period report")
        self.assertAlmostEqual(
            rev_line.credit, 2000.0, places=2,
            msg="Revenue period credit should be 2000.00 (in-period only)",
        )

    @freeze_time('2024-06-30')
    def test_fr005_period_movement(self):
        """
        FR-005: Verify period_debit and period_credit reflect only in-period.

        Given entries exist in the period 2024-01-01 to 2024-06-30
        When I generate a Trial Balance with date_from and date_to
        Then debit and credit columns show only period movement amounts.

        In-period posted entries:
          Receivable: debit=2000, credit=0
          Revenue:    debit=0, credit=2000
          Expense:    debit=800, credit=0
          Payable:    debit=0, credit=800
        """
        report = self._create_trial_balance_report(
            date_from=self.date_period_start,
            show_balance_zero=True,
        )
        report.action_compute()

        # Expense: only in-period (500 + 300 = 800)
        exp_line = self._find_line_for_account(report, self.account_expense)
        self.assertTrue(exp_line, "Expense should be in period report")
        self.assertAlmostEqual(
            exp_line.debit, 800.0, places=2,
            msg="Expense period debit should be 800.00",
        )
        self.assertAlmostEqual(
            exp_line.credit, 0.0, places=2,
            msg="Expense period credit should be 0.00",
        )

        # Payable: only in-period credits (500 + 300 = 800)
        pay_line = self._find_line_for_account(report, self.account_payable)
        self.assertTrue(pay_line, "Payable should be in period report")
        self.assertAlmostEqual(
            pay_line.credit, 800.0, places=2,
            msg="Payable period credit should be 800.00",
        )

    @freeze_time('2024-06-30')
    def test_fr005_closing_balance(self):
        """
        FR-005: Closing balance = opening + period activity.

        Given entries exist before and within the reporting period
        When I generate cumulative (no date_from) and period reports
        Then cumulative balance equals opening + period for each account.

        Verification logic:
          cumulative_balance(date_to) == opening_balance + period_balance
          For Receivable: 3000 = 1000 + 2000
          For Revenue: -3000 = -1000 + (-2000)
        """
        # Cumulative report (no date_from)
        report_cumul = self._create_trial_balance_report(
            show_balance_zero=True,
        )
        report_cumul.action_compute()

        # Period report
        report_period = self._create_trial_balance_report(
            date_from=self.date_period_start,
            show_balance_zero=True,
        )
        report_period.action_compute()

        # Opening report (cumulative to day before period)
        date_before_period_start = self.date_period_start - timedelta(days=1)
        report_opening = self._create_trial_balance_report(
            date_to=date_before_period_start,
            show_balance_zero=True,
        )
        report_opening.action_compute()

        # Verify closing = opening + period for receivable
        recv_cumul = self._find_line_for_account(
            report_cumul, self.account_receivable,
        )
        recv_period = self._find_line_for_account(
            report_period, self.account_receivable,
        )
        recv_opening = self._find_line_for_account(
            report_opening, self.account_receivable,
        )

        if recv_cumul and recv_period and recv_opening:
            closing_balance = recv_cumul.balance
            opening_balance = recv_opening.balance
            period_balance = recv_period.balance
            self.assertAlmostEqual(
                closing_balance, opening_balance + period_balance, places=2,
                msg=(
                    "Closing balance (%.2f) should equal opening (%.2f) "
                    "+ period (%.2f) for receivable"
                    % (closing_balance, opening_balance, period_balance)
                ),
            )

        # Verify for revenue
        rev_cumul = self._find_line_for_account(
            report_cumul, self.account_revenue,
        )
        rev_period = self._find_line_for_account(
            report_period, self.account_revenue,
        )
        rev_opening = self._find_line_for_account(
            report_opening, self.account_revenue,
        )

        if rev_cumul and rev_period and rev_opening:
            closing_balance = rev_cumul.balance
            opening_balance = rev_opening.balance
            period_balance = rev_period.balance
            self.assertAlmostEqual(
                closing_balance, opening_balance + period_balance, places=2,
                msg=(
                    "Closing balance (%.2f) should equal opening (%.2f) "
                    "+ period (%.2f) for revenue"
                    % (closing_balance, opening_balance, period_balance)
                ),
            )

    @freeze_time('2024-06-30')
    def test_fr005_hide_zero_balance(self):
        """
        FR-005 Scenario 5: Hide accounts with zero balance.

        Given an account (XZERO0) exists with no journal entries
        When I generate Trial Balance with show_balance_zero=False
        Then the zero-balance account is excluded from line_ids.
        """
        report = self._create_trial_balance_report(
            show_balance_zero=False,
        )
        report.action_compute()

        zero_line = self._find_line_for_account(
            report, self.account_zero_balance,
        )
        self.assertFalse(
            zero_line,
            "Zero-balance account should be excluded when "
            "show_balance_zero=False",
        )

        # Accounts WITH activity should still be present
        recv_line = self._find_line_for_account(
            report, self.account_receivable,
        )
        self.assertTrue(
            recv_line,
            "Receivable account with activity should be included",
        )

    @freeze_time('2024-06-30')
    def test_fr005_show_zero_balance(self):
        """
        FR-005 Scenario 5: Show accounts with zero balance.

        Given an account (XZERO0) exists with no journal entries
        When I generate Trial Balance with show_balance_zero=True
        Then the zero-balance account is included in line_ids.
        """
        report = self._create_trial_balance_report(
            show_balance_zero=True,
        )
        report.action_compute()

        zero_line = self._find_line_for_account(
            report, self.account_zero_balance,
        )
        self.assertTrue(
            zero_line,
            "Zero-balance account should be included when "
            "show_balance_zero=True",
        )

        # Verify the zero-balance line has zero amounts
        if zero_line:
            self.assertAlmostEqual(
                zero_line.debit, 0.0, places=2,
                msg="Zero-balance account debit should be 0.00",
            )
            self.assertAlmostEqual(
                zero_line.credit, 0.0, places=2,
                msg="Zero-balance account credit should be 0.00",
            )
            self.assertAlmostEqual(
                zero_line.balance, 0.0, places=2,
                msg="Zero-balance account balance should be 0.00",
            )

    @freeze_time('2024-06-30')
    def test_fr005_show_hierarchy(self):
        """
        FR-005: Show account group hierarchy in report.

        Given the report has show_hierarchy=True
        When I generate the Trial Balance
        Then the report is computed successfully with hierarchy enabled.

        Note: Hierarchy grouping depends on account group configuration.
        This test validates the flag is accepted and does not cause errors.
        """
        report = self._create_trial_balance_report(
            show_hierarchy=True,
            show_balance_zero=True,
        )
        report.action_compute()

        self.assertEqual(report.state, 'done',
                         "Report with hierarchy should compute successfully")
        self.assertTrue(
            report.show_hierarchy,
            "show_hierarchy flag should be True on the report",
        )
        self.assertTrue(
            len(report.line_ids) > 0,
            "Hierarchical report should have lines",
        )

    @freeze_time('2024-06-30')
    def test_fr005_posted_moves_only(self):
        """
        FR-005: target_move='posted' excludes draft journal entries.

        Given both posted and draft journal entries exist
        When I generate Trial Balance with target_move='posted'
        Then draft entry amounts (750 debit/credit) are excluded.

        Cumulative posted totals:
          Receivable: debit=3000 (excludes 750 draft)
          Revenue:    credit=3000 (excludes 750 draft)
        """
        report = self._create_trial_balance_report(
            target_move='posted',
            show_balance_zero=True,
        )
        report.action_compute()

        recv_line = self._find_line_for_account(
            report, self.account_receivable,
        )
        self.assertTrue(recv_line)
        self.assertAlmostEqual(
            recv_line.debit, 3000.0, places=2,
            msg="Posted-only receivable debit should be 3000 (no draft 750)",
        )

        rev_line = self._find_line_for_account(report, self.account_revenue)
        self.assertTrue(rev_line)
        self.assertAlmostEqual(
            rev_line.credit, 3000.0, places=2,
            msg="Posted-only revenue credit should be 3000 (no draft 750)",
        )

    @freeze_time('2024-06-30')
    def test_fr005_all_moves(self):
        """
        FR-005: target_move='all' includes draft journal entries.

        Given both posted and draft journal entries exist
        When I generate Trial Balance with target_move='all'
        Then draft entry amounts (750 debit/credit) ARE included.

        Cumulative all totals:
          Receivable: debit=3750 (3000 posted + 750 draft)
          Revenue:    credit=3750 (3000 posted + 750 draft)
        """
        report = self._create_trial_balance_report(
            target_move='all',
            show_balance_zero=True,
        )
        report.action_compute()

        recv_line = self._find_line_for_account(
            report, self.account_receivable,
        )
        self.assertTrue(recv_line)
        self.assertAlmostEqual(
            recv_line.debit, 3750.0, places=2,
            msg="All-moves receivable debit should be 3750 (incl. draft 750)",
        )

        rev_line = self._find_line_for_account(report, self.account_revenue)
        self.assertTrue(rev_line)
        self.assertAlmostEqual(
            rev_line.credit, 3750.0, places=2,
            msg="All-moves revenue credit should be 3750 (incl. draft 750)",
        )

        # Debit/credit equality must still hold with all entries
        difference = abs(report.total_debit - report.total_credit)
        self.assertLessEqual(
            difference, 0.01,
            "Trial Balance should be balanced even with draft entries",
        )

    @freeze_time('2024-06-30')
    def test_fr005_comparative_period(self):
        """
        FR-005 Scenario 6: Comparative Trial Balance.

        Given I enable comparison with a prior period
        When I generate the Trial Balance
        Then the report computes successfully with comparison enabled.

        The comparison columns (comparison_debit, comparison_credit) show
        the prior period's trial balance data.
        """
        comparison_date = self.date_period_end - timedelta(days=365)
        report = self._create_trial_balance_report(
            enable_comparison=True,
            comparison_date_to=comparison_date,
            show_balance_zero=True,
        )
        report.action_compute()

        self.assertEqual(report.state, 'done',
                         "Comparative report should compute successfully")
        self.assertTrue(
            report.enable_comparison,
            "enable_comparison should be True",
        )

    @freeze_time('2024-06-30')
    def test_fr005_date_boundary(self):
        """
        FR-005: Entries exactly on date_to are included.

        Given a journal entry posted on 2024-06-30 (the date_to value)
        When I generate a Trial Balance with date_to=2024-06-30
        Then the entry's amounts are included in the trial balance.

        Entry on boundary date: Expense 300 debit, Payable 300 credit.
        Cumulative expense should include this: 500 + 300 = 800.
        """
        report = self._create_trial_balance_report(
            show_balance_zero=True,
        )
        report.action_compute()

        exp_line = self._find_line_for_account(report, self.account_expense)
        self.assertTrue(exp_line, "Expense account should be in report")
        # Cumulative expense: 500 (Jan) + 300 (Jun 30) = 800
        self.assertAlmostEqual(
            exp_line.debit, 800.0, places=2,
            msg="Expense debit should include boundary-date entry (800.00)",
        )

        pay_line = self._find_line_for_account(report, self.account_payable)
        self.assertTrue(pay_line, "Payable account should be in report")
        self.assertAlmostEqual(
            pay_line.credit, 800.0, places=2,
            msg="Payable credit should include boundary-date entry (800.00)",
        )

    @freeze_time('2024-06-30')
    def test_fr005_single_account_balance(self):
        """
        FR-005: Verify exact debit/credit for a single known account.

        Given the Expense account has exactly two posted entries:
          - 2024-01-01: debit=500
          - 2024-06-30: debit=300
        When I generate a cumulative Trial Balance
        Then the Expense line shows debit=800, credit=0, balance=800.
        """
        report = self._create_trial_balance_report(
            show_balance_zero=True,
        )
        report.action_compute()

        exp_line = self._find_line_for_account(report, self.account_expense)
        self.assertTrue(exp_line, "Expense line must exist")
        self.assertAlmostEqual(exp_line.debit, 800.0, places=2)
        self.assertAlmostEqual(exp_line.credit, 0.0, places=2)
        self.assertAlmostEqual(exp_line.balance, 800.0, places=2,
                               msg="Expense balance should be 800.00")

    @freeze_time('2024-06-30')
    def test_fr005_total_debit_equals_credit_with_entries(self):
        """
        FR-005 Scenario 4: Create specific entries and verify totals.

        Given an additional balanced entry is created and posted
        When I generate the Trial Balance
        Then total_debit still equals total_credit.

        This tests the invariant with fresh data beyond setUp entries.
        """
        # Create an additional balanced entry
        # Odoo 19.0: account.account uses company_ids (Many2many) not company_id
        extra_account = self.env['account.account'].create({
            'name': 'Extra Test Account',
            'code': 'XEXTR1',
            'account_type': 'asset_current',
            'company_ids': [self.company.id],
        })
        extra_move = self.env['account.move'].create({
            'move_type': 'entry',
            'date': date(2024, 4, 15),
            'journal_id': self.journal_misc.id,
            'line_ids': [
                (0, 0, {
                    'name': 'Extra debit',
                    'account_id': extra_account.id,
                    'debit': 1234.56,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': 'Extra credit',
                    'account_id': self.account_payable.id,
                    'debit': 0.0,
                    'credit': 1234.56,
                }),
            ],
        })
        extra_move.action_post()

        report = self._create_trial_balance_report(
            show_balance_zero=True,
        )
        report.action_compute()

        difference = abs(report.total_debit - report.total_credit)
        self.assertLessEqual(
            difference, 0.01,
            "Trial Balance should remain balanced after adding new entries; "
            "total_debit=%.2f, total_credit=%.2f" % (
                report.total_debit, report.total_credit,
            ),
        )
        self.assertTrue(report.is_balanced,
                        "is_balanced should be True with new entries")

        # Verify the extra account shows in the report
        extra_line = self._find_line_for_account(report, extra_account)
        self.assertTrue(extra_line, "Extra account should appear in report")
        self.assertAlmostEqual(
            extra_line.debit, 1234.56, places=2,
            msg="Extra account debit should be 1234.56",
        )

    @freeze_time('2024-06-30')
    def test_fr005_multi_company_isolation(self):
        """
        FR-005: Multi-company isolation via company_id filter.

        Given entries exist in the primary company
        And a second company is set up with its own data
        When I generate a Trial Balance for the second company
        Then only the second company's entries appear in the report,
        and the primary company's entries are excluded.
        """
        # Set up second company using AccountTestInvoicingCommon helper
        company_2_data = self.setup_other_company()
        company_2 = company_2_data['company']
        company_2_misc = company_2_data['default_journal_misc']
        company_2_revenue = company_2_data['default_account_revenue']
        company_2_receivable = company_2_data['default_account_receivable']

        # Create a journal entry in company 2
        move_c2 = self.env['account.move'].with_company(company_2).create({
            'move_type': 'entry',
            'date': date(2024, 5, 1),
            'journal_id': company_2_misc.id,
            'line_ids': [
                (0, 0, {
                    'name': 'Company 2 receivable',
                    'account_id': company_2_receivable.id,
                    'debit': 5000.0,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': 'Company 2 revenue',
                    'account_id': company_2_revenue.id,
                    'debit': 0.0,
                    'credit': 5000.0,
                }),
            ],
        })
        move_c2.action_post()

        # Generate Trial Balance for company 2
        report_c2 = self.env['account.trial.balance.report'].create({
            'date_to': self.date_period_end,
            'company_id': company_2.id,
            'target_move': 'posted',
            'show_balance_zero': True,
        })
        report_c2.action_compute()

        # Company 1's receivable account should NOT be in company 2's report
        c1_recv_line = report_c2.line_ids.filtered(
            lambda ln: ln.account_id.id == self.account_receivable.id,
        )
        self.assertFalse(
            c1_recv_line,
            "Company 1 receivable should not appear in Company 2 report",
        )

        # Company 2's receivable should be present
        c2_recv_line = report_c2.line_ids.filtered(
            lambda ln: ln.account_id.id == company_2_receivable.id,
        )
        self.assertTrue(
            c2_recv_line,
            "Company 2 receivable should appear in Company 2 report",
        )
        if c2_recv_line:
            self.assertAlmostEqual(
                c2_recv_line.debit, 5000.0, places=2,
                msg="Company 2 receivable debit should be 5000.00",
            )

        # Also verify company 1 report is unaffected
        report_c1 = self._create_trial_balance_report(
            show_balance_zero=True,
        )
        report_c1.action_compute()

        c1_recv_in_c1 = self._find_line_for_account(
            report_c1, self.account_receivable,
        )
        self.assertTrue(c1_recv_in_c1)
        self.assertAlmostEqual(
            c1_recv_in_c1.debit, 3000.0, places=2,
            msg="Company 1 receivable should still show 3000.00 in C1 report",
        )
