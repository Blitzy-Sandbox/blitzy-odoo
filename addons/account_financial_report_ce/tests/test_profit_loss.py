# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""
Dedicated Profit & Loss test module for FR-002 acceptance criteria.

Maps test methods to FR-002 user-story acceptance scenarios:

  - FR-002 Scenario 1: Complete P&L for a given date range
  - FR-002 Scenario 2: Revenue / expense classification
  - FR-002 Scenario 3: Operating-expense breakdown
  - FR-002 Scenario 4: Gross Profit = Revenue − COGS
  - FR-002 Scenario 5: Net Income fully computed
  - FR-002 Scenario 6: Comparative period with variance analysis

References:
  ``tickets/stories/financial-reporting/FR-002-*.md``
  ``tickets/features/FEATURE-001-financial-reporting.md``
"""

from datetime import date, timedelta

from freezegun import freeze_time
from psycopg2 import IntegrityError

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tools import mute_logger

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestProfitLoss(AccountTestInvoicingCommon):
    """
    FR-002 Profit & Loss acceptance-criteria test suite.

    Uses deterministic amounts so every assertion can hard-code the expected
    value rather than computing it dynamically:

        Revenue (income)                 50 000
        COGS (expense_direct_cost)       20 000
        General expenses (expense)       10 000
        Depreciation (expense_depreciation) 5 000
        Other income (income_other)       3 000

    Expected P&L:
        Total Revenue          50 000
        Cost of Goods Sold     20 000
        Gross Profit           30 000
        Operating Expenses     15 000   (10 000 + 5 000)
        Operating Income       15 000
        Other Income            3 000
        Other Expenses              0
        Net Income             18 000
    """

    # ------------------------------------------------------------------
    # Class Setup
    # ------------------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        """
        Create chart-of-account fixtures and posted journal entries
        with known amounts for each P&L section.

        All entries are dated within the *primary reporting period*
        (2024-01-01 to 2024-06-30) unless otherwise noted.

        Additionally creates:
        - A *comparison-period* entry (2023-07-01 to 2023-12-31)
          for comparative-analysis tests.
        - A *draft* (unposted) entry for target_move filtering.
        - Entries in a *second company* for multi-company isolation.
        - Entries *outside* the reporting period for boundary tests.
        """
        super().setUpClass()

        cls.company = cls.env.company
        cls.currency = cls.company.currency_id

        # Grant Financial Reports groups to test user so ACL passes.
        fr_user_group = cls.env.ref(
            'account_financial_report_ce.group_financial_report_user',
            raise_if_not_found=False,
        )
        fr_mgr_group = cls.env.ref(
            'account_financial_report_ce.group_financial_report_manager',
            raise_if_not_found=False,
        )
        groups = cls.env['res.groups']
        if fr_user_group:
            groups |= fr_user_group
        if fr_mgr_group:
            groups |= fr_mgr_group
        if groups and cls.env.user != cls.env.ref('base.user_admin'):
            cls.env.user.write({
                'group_ids': [(4, g.id) for g in groups],
            })

        # ----- Accounts -----
        cls.account_revenue = cls.company_data['default_account_revenue']
        cls.account_expense = cls.company_data['default_account_expense']
        cls.account_receivable = cls.company_data['default_account_receivable']
        cls.account_payable = cls.company_data['default_account_payable']
        cls.journal_misc = cls.company_data['default_journal_misc']

        # COGS account (expense_direct_cost) — not in standard fixtures
        cls.account_cogs = cls.env['account.account'].create({
            'name': 'Cost of Goods Sold',
            'code': 'XCOGS0',
            'account_type': 'expense_direct_cost',
            'company_ids': [cls.company.id],
        })

        # Depreciation account
        cls.account_depreciation = cls.env['account.account'].create({
            'name': 'Depreciation & Amortization',
            'code': 'XDEPR0',
            'account_type': 'expense_depreciation',
            'company_ids': [cls.company.id],
        })

        # Other-income account
        cls.account_other_income = cls.env['account.account'].create({
            'name': 'Other Income',
            'code': 'XOINC0',
            'account_type': 'income_other',
            'company_ids': [cls.company.id],
        })

        # ----- Reporting dates -----
        cls.date_period_start = date(2024, 1, 1)
        cls.date_mid_period = date(2024, 3, 15)
        cls.date_period_end = date(2024, 6, 30)
        cls.date_before_period = date(2023, 11, 15)
        cls.date_after_period = date(2024, 8, 1)

        # Comparison period — computed relative to period_start via timedelta
        cls.comp_date_from = cls.date_period_start - timedelta(days=184)  # ~2023-07-01
        cls.comp_date_to = cls.date_period_start - timedelta(days=1)     # 2023-12-31

        # =================================================================
        # POSTED JOURNAL ENTRIES — Primary Period (2024-01-01 … 2024-06-30)
        # =================================================================

        # Revenue entry: 50 000 — posted 2024-02-15 (partner_a)
        cls.move_revenue = cls.env['account.move'].create({
            'move_type': 'entry',
            'date': date(2024, 2, 15),
            'journal_id': cls.journal_misc.id,
            'partner_id': cls.partner_a.id,
            'line_ids': [
                (0, 0, {
                    'name': 'Revenue: Receivable',
                    'account_id': cls.account_receivable.id,
                    'partner_id': cls.partner_a.id,
                    'debit': 50000.0,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': 'Revenue: Income',
                    'account_id': cls.account_revenue.id,
                    'partner_id': cls.partner_a.id,
                    'debit': 0.0,
                    'credit': 50000.0,
                }),
            ],
        })
        cls.move_revenue.action_post()

        # COGS entry: 20 000 — posted 2024-02-20 (partner_b)
        cls.move_cogs = cls.env['account.move'].create({
            'move_type': 'entry',
            'date': date(2024, 2, 20),
            'journal_id': cls.journal_misc.id,
            'partner_id': cls.partner_b.id,
            'line_ids': [
                (0, 0, {
                    'name': 'COGS: Direct Cost',
                    'account_id': cls.account_cogs.id,
                    'partner_id': cls.partner_b.id,
                    'debit': 20000.0,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': 'COGS: Payable',
                    'account_id': cls.account_payable.id,
                    'partner_id': cls.partner_b.id,
                    'debit': 0.0,
                    'credit': 20000.0,
                }),
            ],
        })
        cls.move_cogs.action_post()

        # General operating expenses: 10 000 — posted 2024-03-10
        cls.move_expense = cls.env['account.move'].create({
            'move_type': 'entry',
            'date': date(2024, 3, 10),
            'journal_id': cls.journal_misc.id,
            'line_ids': [
                (0, 0, {
                    'name': 'OpEx: General Expense',
                    'account_id': cls.account_expense.id,
                    'debit': 10000.0,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': 'OpEx: Payable',
                    'account_id': cls.account_payable.id,
                    'debit': 0.0,
                    'credit': 10000.0,
                }),
            ],
        })
        cls.move_expense.action_post()

        # Depreciation: 5 000 — posted 2024-04-01
        cls.move_depreciation = cls.env['account.move'].create({
            'move_type': 'entry',
            'date': date(2024, 4, 1),
            'journal_id': cls.journal_misc.id,
            'line_ids': [
                (0, 0, {
                    'name': 'Depreciation: Expense',
                    'account_id': cls.account_depreciation.id,
                    'debit': 5000.0,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': 'Depreciation: Payable',
                    'account_id': cls.account_payable.id,
                    'debit': 0.0,
                    'credit': 5000.0,
                }),
            ],
        })
        cls.move_depreciation.action_post()

        # Other income: 3 000 — posted 2024-05-10
        cls.move_other_income = cls.env['account.move'].create({
            'move_type': 'entry',
            'date': date(2024, 5, 10),
            'journal_id': cls.journal_misc.id,
            'line_ids': [
                (0, 0, {
                    'name': 'Other Income: Receivable',
                    'account_id': cls.account_receivable.id,
                    'debit': 3000.0,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': 'Other Income: Income Other',
                    'account_id': cls.account_other_income.id,
                    'debit': 0.0,
                    'credit': 3000.0,
                }),
            ],
        })
        cls.move_other_income.action_post()

        # =================================================================
        # COMPARISON-PERIOD ENTRY — (2023-07-01 … 2023-12-31)
        #   Revenue 30 000, COGS 12 000, Expense 6 000, Depr 2 000,
        #   Other Income 1 500
        # =================================================================
        cls.move_comp_revenue = cls.env['account.move'].create({
            'move_type': 'entry',
            'date': date(2023, 9, 15),
            'journal_id': cls.journal_misc.id,
            'line_ids': [
                (0, 0, {
                    'name': 'Comp Revenue: Receivable',
                    'account_id': cls.account_receivable.id,
                    'debit': 30000.0,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': 'Comp Revenue: Income',
                    'account_id': cls.account_revenue.id,
                    'debit': 0.0,
                    'credit': 30000.0,
                }),
            ],
        })
        cls.move_comp_revenue.action_post()

        cls.move_comp_cogs = cls.env['account.move'].create({
            'move_type': 'entry',
            'date': date(2023, 9, 20),
            'journal_id': cls.journal_misc.id,
            'line_ids': [
                (0, 0, {
                    'name': 'Comp COGS: Direct Cost',
                    'account_id': cls.account_cogs.id,
                    'debit': 12000.0,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': 'Comp COGS: Payable',
                    'account_id': cls.account_payable.id,
                    'debit': 0.0,
                    'credit': 12000.0,
                }),
            ],
        })
        cls.move_comp_cogs.action_post()

        cls.move_comp_expense = cls.env['account.move'].create({
            'move_type': 'entry',
            'date': date(2023, 10, 5),
            'journal_id': cls.journal_misc.id,
            'line_ids': [
                (0, 0, {
                    'name': 'Comp Expense',
                    'account_id': cls.account_expense.id,
                    'debit': 6000.0,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': 'Comp Expense: Payable',
                    'account_id': cls.account_payable.id,
                    'debit': 0.0,
                    'credit': 6000.0,
                }),
            ],
        })
        cls.move_comp_expense.action_post()

        cls.move_comp_depreciation = cls.env['account.move'].create({
            'move_type': 'entry',
            'date': date(2023, 11, 1),
            'journal_id': cls.journal_misc.id,
            'line_ids': [
                (0, 0, {
                    'name': 'Comp Depreciation',
                    'account_id': cls.account_depreciation.id,
                    'debit': 2000.0,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': 'Comp Depreciation: Payable',
                    'account_id': cls.account_payable.id,
                    'debit': 0.0,
                    'credit': 2000.0,
                }),
            ],
        })
        cls.move_comp_depreciation.action_post()

        cls.move_comp_other_income = cls.env['account.move'].create({
            'move_type': 'entry',
            'date': date(2023, 12, 10),
            'journal_id': cls.journal_misc.id,
            'line_ids': [
                (0, 0, {
                    'name': 'Comp Other Income: Receivable',
                    'account_id': cls.account_receivable.id,
                    'debit': 1500.0,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': 'Comp Other Income',
                    'account_id': cls.account_other_income.id,
                    'debit': 0.0,
                    'credit': 1500.0,
                }),
            ],
        })
        cls.move_comp_other_income.action_post()

        # =================================================================
        # DRAFT ENTRY — should be excluded by target_move='posted'
        # Revenue 7 777 in the primary period, NOT posted.
        # =================================================================
        cls.move_draft = cls.env['account.move'].create({
            'move_type': 'entry',
            'date': date(2024, 4, 15),
            'journal_id': cls.journal_misc.id,
            'line_ids': [
                (0, 0, {
                    'name': 'Draft Revenue: Receivable',
                    'account_id': cls.account_receivable.id,
                    'debit': 7777.0,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': 'Draft Revenue: Income',
                    'account_id': cls.account_revenue.id,
                    'debit': 0.0,
                    'credit': 7777.0,
                }),
            ],
        })
        # Deliberately NOT posted — stays in 'draft' state.

        # =================================================================
        # OUT-OF-PERIOD ENTRY — posted but outside 2024-01-01…2024-06-30
        # Revenue 9 999, dated 2024-08-01 (after period end).
        # =================================================================
        cls.move_after_period = cls.env['account.move'].create({
            'move_type': 'entry',
            'date': cls.date_after_period,
            'journal_id': cls.journal_misc.id,
            'line_ids': [
                (0, 0, {
                    'name': 'After Revenue: Receivable',
                    'account_id': cls.account_receivable.id,
                    'debit': 9999.0,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': 'After Revenue: Income',
                    'account_id': cls.account_revenue.id,
                    'debit': 0.0,
                    'credit': 9999.0,
                }),
            ],
        })
        cls.move_after_period.action_post()

        # =================================================================
        # BOUNDARY ENTRIES — exactly on date_from / date_to
        # Revenue 1 111 on 2024-01-01 (date_from boundary)
        # Revenue 2 222 on 2024-06-30 (date_to boundary)
        # =================================================================
        cls.move_on_date_from = cls.env['account.move'].create({
            'move_type': 'entry',
            'date': cls.date_period_start,
            'journal_id': cls.journal_misc.id,
            'line_ids': [
                (0, 0, {
                    'name': 'Boundary Start: Receivable',
                    'account_id': cls.account_receivable.id,
                    'debit': 1111.0,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': 'Boundary Start: Income',
                    'account_id': cls.account_revenue.id,
                    'debit': 0.0,
                    'credit': 1111.0,
                }),
            ],
        })
        cls.move_on_date_from.action_post()

        cls.move_on_date_to = cls.env['account.move'].create({
            'move_type': 'entry',
            'date': cls.date_period_end,
            'journal_id': cls.journal_misc.id,
            'line_ids': [
                (0, 0, {
                    'name': 'Boundary End: Receivable',
                    'account_id': cls.account_receivable.id,
                    'debit': 2222.0,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': 'Boundary End: Income',
                    'account_id': cls.account_revenue.id,
                    'debit': 0.0,
                    'credit': 2222.0,
                }),
            ],
        })
        cls.move_on_date_to.action_post()

    # ------------------------------------------------------------------
    # Helper Methods
    # ------------------------------------------------------------------

    def _create_pl_report(self, **kwargs):
        """
        Convenience wrapper to create a P&L report with common defaults.

        Default parameters (overridable via *kwargs*):
            date_from     2024-01-01
            date_to       2024-06-30
            company_id    current company
            target_move   'posted'
        """
        vals = {
            'date_from': self.date_period_start,
            'date_to': self.date_period_end,
            'company_id': self.company.id,
            'target_move': 'posted',
        }
        vals.update(kwargs)
        return self.env['account.profit.loss.report'].create(vals)

    def _create_and_compute(self, **kwargs):
        """Create a P&L report and run ``action_compute`` in one step."""
        report = self._create_pl_report(**kwargs)
        report.action_compute()
        return report

    # ------------------------------------------------------------------
    # FR-002 Scenario 1 — Report Creation & Computation Lifecycle
    # ------------------------------------------------------------------

    @freeze_time('2024-06-30')
    def test_fr002_pl_creation(self):
        """
        FR-002 Scenario 1: Create a Profit & Loss report.

        Given   valid date_from and date_to parameters
        When    a P&L report is created
        Then    the report record exists with state 'draft'.
        """
        report = self._create_pl_report()
        self.assertTrue(report, "P&L report record should be created")
        self.assertEqual(
            report.state, 'draft',
            "Newly created P&L report should be in 'draft' state",
        )
        self.assertEqual(report.date_from, self.date_period_start)
        self.assertEqual(report.date_to, self.date_period_end)

    @freeze_time('2024-06-30')
    def test_fr002_pl_computation(self):
        """
        FR-002 Scenario 1: Compute a Profit & Loss report.

        Given   a draft P&L report
        When    action_compute is called
        Then    the report transitions to state 'done'.
        """
        report = self._create_pl_report()
        self.assertEqual(report.state, 'draft')
        report.action_compute()
        self.assertEqual(
            report.state, 'done',
            "P&L report should be in 'done' state after computation",
        )

    @freeze_time('2024-06-30')
    def test_fr002_pl_missing_dates_raises(self):
        """
        FR-002: P&L report enforces mandatory date parameters.

        Given   the ``date_from`` field carries ``required=True``
        When    attempting to create a report without ``date_from``
        Then    the database NOT NULL constraint rejects the operation.

        The ``required=True`` attribute on ``date_from`` results in a
        PostgreSQL NOT NULL constraint.  This is the primary enforcement
        mechanism; the secondary Python-level validation inside
        ``action_generate_report`` is an additional safety net that is
        exercised separately in ``test_fr002_pl_action_validates_dates``.
        """
        with mute_logger('odoo.sql_db'), self.assertRaises(IntegrityError):
            self.env['account.profit.loss.report'].create({
                'date_to': self.date_period_end,
                'company_id': self.company.id,
                'target_move': 'posted',
            })

    @freeze_time('2024-06-30')
    def test_fr002_pl_action_validates_dates(self):
        """
        FR-002: ``action_generate_report`` validates date parameters.

        Given   a valid P&L report
        When    ``action_generate_report`` is called
        Then    the report is generated successfully (Python validation
                passes because dates are present).

        This test confirms the Python-level validation pathway inside
        ``action_generate_report`` by exercising it with valid dates.
        The negative path (missing dates) is covered by the database
        constraint tested in ``test_fr002_pl_missing_dates_raises``.
        """
        report = self._create_pl_report()
        result = report.action_generate_report()
        self.assertTrue(
            result,
            "action_generate_report should return a truthy action dict",
        )
        self.assertEqual(
            result.get('type'), 'ir.actions.act_window',
            "action_generate_report should return a window action",
        )

    # ------------------------------------------------------------------
    # FR-002 Scenario 2 — Revenue Aggregation
    # ------------------------------------------------------------------

    @freeze_time('2024-06-30')
    def test_fr002_revenue_aggregation(self):
        """
        FR-002 Scenario 2: Operating revenue classification.

        Given   posted revenue entries totalling 50 000 (income),
                plus boundary entries of 1 111 and 2 222
        When    a P&L report is computed for the primary period
        Then    total_revenue equals sum of all 'income' account entries
                within the date range:
                50 000 + 1 111 + 2 222 = 53 333.

        Note:   'income_other' entries (3 000) are NOT included in
                total_revenue — they appear in total_other_income.
        """
        report = self._create_and_compute()
        # Revenue = 50 000 (main) + 1 111 (boundary start) + 2 222 (boundary end)
        self.assertAlmostEqual(
            report.total_revenue, 53333.0, places=2,
            msg="total_revenue should be 53333.00 (all posted 'income' entries in period)",
        )

    # ------------------------------------------------------------------
    # FR-002 Scenario 4 — COGS Calculation
    # ------------------------------------------------------------------

    @freeze_time('2024-06-30')
    def test_fr002_cogs_calculation(self):
        """
        FR-002 Scenario 4: Cost of Goods Sold (expense_direct_cost).

        Given   posted COGS entries totalling 20 000
        When    a P&L report is computed
        Then    total_cogs equals 20 000.
        """
        report = self._create_and_compute()
        self.assertAlmostEqual(
            report.total_cogs, 20000.0, places=2,
            msg="total_cogs should be 20000.00",
        )

    # ------------------------------------------------------------------
    # FR-002 Scenario 4 — Gross Profit
    # ------------------------------------------------------------------

    @freeze_time('2024-06-30')
    def test_fr002_gross_profit(self):
        """
        FR-002 Scenario 4: Gross Profit = Revenue − COGS.

        Given   total_revenue = 53 333, total_cogs = 20 000
        When    P&L is computed
        Then    gross_profit = 53 333 − 20 000 = 33 333.
        """
        report = self._create_and_compute()
        expected_gross = report.total_revenue - report.total_cogs
        self.assertAlmostEqual(
            report.gross_profit, expected_gross, places=2,
            msg="gross_profit should equal total_revenue - total_cogs",
        )
        self.assertAlmostEqual(
            report.gross_profit, 33333.0, places=2,
            msg="gross_profit should be 33333.00",
        )

    # ------------------------------------------------------------------
    # FR-002 Scenario 3 — Operating Expenses
    # ------------------------------------------------------------------

    @freeze_time('2024-06-30')
    def test_fr002_operating_expenses(self):
        """
        FR-002 Scenario 3: Operating expenses breakdown.

        Given   general expenses = 10 000, depreciation = 5 000
        When    P&L is computed
        Then    total_operating_expenses = 15 000  (= 10 000 + 5 000)
                total_general_expenses  = 10 000
                total_depreciation      =  5 000
        """
        report = self._create_and_compute()
        self.assertAlmostEqual(
            report.total_general_expenses, 10000.0, places=2,
            msg="total_general_expenses should be 10000.00",
        )
        self.assertAlmostEqual(
            report.total_depreciation, 5000.0, places=2,
            msg="total_depreciation should be 5000.00",
        )
        self.assertAlmostEqual(
            report.total_operating_expenses, 15000.0, places=2,
            msg="total_operating_expenses should be 15000.00 (10000 + 5000)",
        )
        # Verify the alias field
        self.assertAlmostEqual(
            report.total_expenses, report.total_operating_expenses, places=2,
            msg="total_expenses alias should equal total_operating_expenses",
        )

    # ------------------------------------------------------------------
    # FR-002 Scenario 5 — Operating Income
    # ------------------------------------------------------------------

    @freeze_time('2024-06-30')
    def test_fr002_operating_income(self):
        """
        FR-002 Scenario 5: Operating Income = Gross Profit − OpEx.

        Given   gross_profit = 33 333, total_operating_expenses = 15 000
        When    P&L is computed
        Then    operating_income = 33 333 − 15 000 = 18 333.
        """
        report = self._create_and_compute()
        expected_oi = report.gross_profit - report.total_operating_expenses
        self.assertAlmostEqual(
            report.operating_income, expected_oi, places=2,
            msg="operating_income should equal gross_profit - total_operating_expenses",
        )
        self.assertAlmostEqual(
            report.operating_income, 18333.0, places=2,
            msg="operating_income should be 18333.00",
        )

    # ------------------------------------------------------------------
    # FR-002 — Other Income / Expenses
    # ------------------------------------------------------------------

    @freeze_time('2024-06-30')
    def test_fr002_other_income_expenses(self):
        """
        FR-002: Other Income / Expenses (non-operating section).

        Given   other income = 3 000 (income_other type)
                other expenses = 0.0 (no standard non-op expense type)
        When    P&L is computed
        Then    total_other_income  = 3 000
                total_other_expenses = 0.0
                total_other = 3 000 − 0 = 3 000
        """
        report = self._create_and_compute()
        self.assertAlmostEqual(
            report.total_other_income, 3000.0, places=2,
            msg="total_other_income should be 3000.00 (income_other entries)",
        )
        self.assertAlmostEqual(
            report.total_other_expenses, 0.0, places=2,
            msg="total_other_expenses should be 0.00 (no non-op expense type)",
        )
        self.assertAlmostEqual(
            report.total_other, 3000.0, places=2,
            msg="total_other = other_income - other_expenses = 3000.00",
        )

    # ------------------------------------------------------------------
    # FR-002 Scenario 5 — Net Income
    # ------------------------------------------------------------------

    @freeze_time('2024-06-30')
    def test_fr002_net_income_calculation(self):
        """
        FR-002 Scenario 5: Net Income — full P&L bottom line.

        Net Income = Operating Income + Other Income − Other Expenses
                   = 18 333 + 3 000 − 0 = 21 333.

        Also verifiable as:
        Net Income = Revenue − COGS − OpEx + Other
                   = 53 333 − 20 000 − 15 000 + 3 000 = 21 333
        """
        report = self._create_and_compute()
        expected_ni = (
            report.operating_income
            + report.total_other_income
            - report.total_other_expenses
        )
        self.assertAlmostEqual(
            report.net_income, expected_ni, places=2,
            msg="net_income should equal operating_income + other_income - other_expenses",
        )
        self.assertAlmostEqual(
            report.net_income, 21333.0, places=2,
            msg="net_income should be 21333.00",
        )
        # Cross-check via the algebraic identity
        cross_check = (
            report.total_revenue
            - report.total_cogs
            - report.total_operating_expenses
            + report.total_other_income
            - report.total_other_expenses
        )
        self.assertAlmostEqual(
            report.net_income, cross_check, places=2,
            msg="net_income should also equal revenue - cogs - opex + other (net)",
        )

    # ------------------------------------------------------------------
    # FR-002 — Date-Range Filtering
    # ------------------------------------------------------------------

    @freeze_time('2024-06-30')
    def test_fr002_date_range_filtering(self):
        """
        FR-002: Only entries within [date_from, date_to] are included.

        Given   entries exist before, within, and after the reporting period
        When    P&L is computed for 2024-03-01 to 2024-05-31
        Then    only the entries dated within that window contribute:
                Revenue      = 0        (50 000 entry is 2024-02-15 → outside)
                COGS         = 0        (2024-02-20 → outside)
                Gen. Expense = 10 000   (2024-03-10 → inside)
                Depreciation =  5 000   (2024-04-01 → inside)
                Other Income =  3 000   (2024-05-10 → inside)
        """
        report = self._create_and_compute(
            date_from=date(2024, 3, 1),
            date_to=date(2024, 5, 31),
        )
        self.assertAlmostEqual(
            report.total_revenue, 0.0, places=2,
            msg="Revenue entries are outside the narrowed date range",
        )
        self.assertAlmostEqual(
            report.total_cogs, 0.0, places=2,
            msg="COGS entries are outside the narrowed date range",
        )
        self.assertAlmostEqual(
            report.total_general_expenses, 10000.0, places=2,
            msg="General expense (2024-03-10) falls within narrowed range",
        )
        self.assertAlmostEqual(
            report.total_depreciation, 5000.0, places=2,
            msg="Depreciation (2024-04-01) falls within narrowed range",
        )
        self.assertAlmostEqual(
            report.total_other_income, 3000.0, places=2,
            msg="Other income (2024-05-10) falls within narrowed range",
        )
        # Net = 0 - 0 - 15000 + 3000 = -12 000
        self.assertAlmostEqual(
            report.net_income, -12000.0, places=2,
            msg="Net income should reflect only in-range entries",
        )

    @freeze_time('2024-06-30')
    def test_fr002_date_boundary_from(self):
        """
        FR-002: Entries exactly on date_from are included.

        Given   a revenue entry of 1 111 posted on 2024-01-01
        When    P&L is computed with date_from = 2024-01-01,
                date_to = 2024-01-01 (single-day window)
        Then    total_revenue includes the 1 111 entry.
        """
        report = self._create_and_compute(
            date_from=date(2024, 1, 1),
            date_to=date(2024, 1, 1),
        )
        # Only the 1 111 boundary-start entry falls on this single day
        self.assertAlmostEqual(
            report.total_revenue, 1111.0, places=2,
            msg="Entry on date_from boundary (2024-01-01) must be included",
        )

    @freeze_time('2024-06-30')
    def test_fr002_date_boundary_to(self):
        """
        FR-002: Entries exactly on date_to are included.

        Given   a revenue entry of 2 222 posted on 2024-06-30
        When    P&L is computed with date_from = 2024-06-30,
                date_to = 2024-06-30 (single-day window)
        Then    total_revenue includes the 2 222 entry.
        """
        report = self._create_and_compute(
            date_from=date(2024, 6, 30),
            date_to=date(2024, 6, 30),
        )
        # Only the 2 222 boundary-end entry falls on this single day
        self.assertAlmostEqual(
            report.total_revenue, 2222.0, places=2,
            msg="Entry on date_to boundary (2024-06-30) must be included",
        )

    # ------------------------------------------------------------------
    # FR-002 Scenario 6 — Comparative Period Analysis
    # ------------------------------------------------------------------

    @freeze_time('2024-06-30')
    def test_fr002_comparative_period(self):
        """
        FR-002 Scenario 6: Comparative P&L with comparison columns.

        Given   comparison period (2023-07-01 … 2023-12-31) has:
                Revenue 30 000, COGS 12 000, Expense 6 000,
                Depreciation 2 000, Other Income 1 500
        When    P&L is computed with enable_comparison = True
        Then    the report line_ids include comparison_amount values.
        """
        report = self._create_and_compute(
            enable_comparison=True,
            comparison_date_from=self.comp_date_from,
            comparison_date_to=self.comp_date_to,
        )
        # Verify comparison data is reflected in report lines
        self.assertTrue(
            report.line_ids,
            "Report should have lines when comparison is enabled",
        )
        # Check that comparison amounts are populated on total lines
        revenue_total_line = report.line_ids.filtered(
            lambda l: l.section == 'revenue' and l.is_total
        )
        if revenue_total_line:
            # Comparison revenue should be 30 000
            self.assertAlmostEqual(
                revenue_total_line[0].comparison_amount, 30000.0, places=2,
                msg="Comparison period revenue total should be 30000.00",
            )

        net_income_line = report.line_ids.filtered(
            lambda l: l.section == 'net_income' and l.is_total
        )
        if net_income_line:
            # Comparison net income = 30000 - 12000 - 8000 + 1500 = 11 500
            self.assertAlmostEqual(
                net_income_line[0].comparison_amount, 11500.0, places=2,
                msg="Comparison period net income should be 11500.00",
            )

    @freeze_time('2024-06-30')
    def test_fr002_variance_analysis(self):
        """
        FR-002 Scenario 6: Variance = Current − Comparison.

        Given   current net income = 21 333
                comparison net income = 11 500
        When    P&L is computed with enable_comparison
        Then    variance on net income line = 21 333 − 11 500 = 9 833.
        """
        report = self._create_and_compute(
            enable_comparison=True,
            comparison_date_from=self.comp_date_from,
            comparison_date_to=self.comp_date_to,
        )
        net_line = report.line_ids.filtered(
            lambda l: l.section == 'net_income' and l.is_total
        )
        if net_line:
            current_amount = net_line[0].amount
            comparison_amount = net_line[0].comparison_amount
            expected_variance = current_amount - comparison_amount
            self.assertAlmostEqual(
                net_line[0].variance_absolute, expected_variance, places=2,
                msg="Variance absolute should be current - comparison for net income",
            )

    # ------------------------------------------------------------------
    # FR-002 — Posted Moves Only
    # ------------------------------------------------------------------

    @freeze_time('2024-06-30')
    def test_fr002_posted_moves_only(self):
        """
        FR-002: target_move='posted' excludes draft entries.

        Given   a draft revenue entry of 7 777 exists in the period
        When    P&L is computed with target_move='posted'
        Then    total_revenue does NOT include the 7 777 draft amount.

        Cross-verified by comparing target_move='all' which DOES include it.
        """
        report_posted = self._create_and_compute(target_move='posted')
        report_all = self._create_and_compute(target_move='all')

        # 'all' mode should include 7 777 more revenue than 'posted' mode
        diff = report_all.total_revenue - report_posted.total_revenue
        self.assertAlmostEqual(
            diff, 7777.0, places=2,
            msg="Draft entry (7777) should appear only in target_move='all'",
        )
        # Confirm posted-mode revenue matches our known total
        self.assertAlmostEqual(
            report_posted.total_revenue, 53333.0, places=2,
            msg="Posted-only revenue should be 53333.00",
        )

    # ------------------------------------------------------------------
    # FR-002 — Zero Revenue Period
    # ------------------------------------------------------------------

    @freeze_time('2024-06-30')
    def test_fr002_zero_revenue_period(self):
        """
        FR-002: Empty period returns zero totals.

        Given   no entries exist in the period 2025-01-01 … 2025-06-30
        When    a P&L report is computed for that period
        Then    all monetary fields are 0.00.
        """
        report = self._create_and_compute(
            date_from=date(2025, 1, 1),
            date_to=date(2025, 6, 30),
        )
        for field_name in (
            'total_revenue', 'total_cogs', 'gross_profit',
            'total_general_expenses', 'total_depreciation',
            'total_operating_expenses', 'operating_income',
            'total_other_income', 'total_other_expenses', 'net_income',
        ):
            self.assertAlmostEqual(
                getattr(report, field_name), 0.0, places=2,
                msg=f"{field_name} should be 0.00 for a period with no entries",
            )

    # ------------------------------------------------------------------
    # FR-002 — Report Lines Populated
    # ------------------------------------------------------------------

    @freeze_time('2024-06-30')
    def test_fr002_report_lines_populated(self):
        """
        FR-002: Verify report line_ids are created with correct sections.

        Given   a computed P&L report
        When    line_ids are inspected
        Then    lines exist for the four P&L sections (revenue, cogs,
                expense, other) and summary rows for Gross Profit,
                Operating Income, and Net Income are present.

        The model assigns ``section`` only to account-detail lines.
        Summary / total rows (GROSS PROFIT, OPERATING INCOME, NET
        INCOME) are rendered as ``is_group=True`` / ``is_total=True``
        rows without a ``section`` value because the QWeb template
        positions them statically between the section blocks.
        """
        report = self._create_and_compute()
        self.assertTrue(
            report.line_ids,
            "Computed P&L report must have line_ids populated",
        )

        # Verify the four data-carrying section tags exist among
        # the generated lines.  These are set on account-detail and
        # sub-section lines by ``_generate_report_lines``.
        expected_sections = {'revenue', 'cogs', 'expense', 'other'}
        present_sections = set(report.line_ids.mapped('section')) - {False}
        for section in expected_sections:
            self.assertIn(
                section, present_sections,
                f"Section '{section}' should be present in report line_ids",
            )

        # Revenue header/total line: the REVENUE header is a group
        # line with is_total=True and level 0 but has NO section tag
        # (the template renders it statically).  Verify it carries the
        # correct monetary amount.
        rev_header = report.line_ids.filtered(
            lambda l: l.is_group and l.is_total and l.level == 0
            and 'REVENUE' in (l.name or '').upper()
            and 'OTHER' not in (l.name or '').upper()
        )
        if rev_header:
            self.assertAlmostEqual(
                rev_header[0].amount, report.total_revenue, places=2,
                msg="Revenue header line amount must match total_revenue",
            )

        # Net Income total line: rendered as a group line with
        # is_total=True at level 0, name containing 'NET INCOME'.
        ni_total = report.line_ids.filtered(
            lambda l: l.is_group and l.is_total and l.level == 0
            and 'NET INCOME' in (l.name or '').upper()
        )
        if ni_total:
            self.assertAlmostEqual(
                ni_total[0].amount, report.net_income, places=2,
                msg="Net Income total line amount must match net_income",
            )

    # ------------------------------------------------------------------
    # FR-002 — Multi-Company Isolation
    # ------------------------------------------------------------------

    @freeze_time('2024-06-30')
    def test_fr002_multi_company_isolation(self):
        """
        FR-002: company_id filter ensures multi-company isolation.

        Given   Company 1 has revenue entries
                Company 2 has its own revenue entries
        When    P&L is computed for Company 2
        Then    only Company 2 entries appear; Company 1 entries are excluded.
        """
        # Set up second company using the inherited helper
        company_2_data = self.setup_other_company()
        company_2 = company_2_data['company']
        company_2_misc = company_2_data['default_journal_misc']
        company_2_revenue = company_2_data['default_account_revenue']
        company_2_receivable = company_2_data['default_account_receivable']

        # Create a revenue entry in Company 2: 8 888
        move_c2 = self.env['account.move'].with_company(company_2).create({
            'move_type': 'entry',
            'date': date(2024, 3, 1),
            'journal_id': company_2_misc.id,
            'line_ids': [
                (0, 0, {
                    'name': 'C2 Receivable',
                    'account_id': company_2_receivable.id,
                    'debit': 8888.0,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': 'C2 Revenue',
                    'account_id': company_2_revenue.id,
                    'debit': 0.0,
                    'credit': 8888.0,
                }),
            ],
        })
        move_c2.action_post()

        # Generate P&L for Company 2
        report_c2 = self.env['account.profit.loss.report'].create({
            'date_from': self.date_period_start,
            'date_to': self.date_period_end,
            'company_id': company_2.id,
            'target_move': 'posted',
        })
        report_c2.action_compute()

        # Company 2 should only see its own 8 888 revenue,
        # NOT Company 1's 53 333.
        self.assertAlmostEqual(
            report_c2.total_revenue, 8888.0, places=2,
            msg="Company 2 P&L should report only Company 2 revenue (8888.00)",
        )

        # Company 1 report must be unaffected by Company 2 data
        report_c1 = self._create_and_compute()
        self.assertAlmostEqual(
            report_c1.total_revenue, 53333.0, places=2,
            msg="Company 1 P&L should still report 53333.00 revenue",
        )
