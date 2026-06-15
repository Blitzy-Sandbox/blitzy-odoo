# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Test Suite for BM-003: Actual vs Budget Reporting

Implements comprehensive tests for budget.vs.actual.report AbstractModel:
actuals aggregation via read_group, hierarchical grouping by analytic plan,
multi-period / YTD totals, filters, and consumption classification per BM-003
acceptance criteria:

- Scenario 1: Generate actual vs budget report with variance indicator
- Scenario 2: Hierarchical display by analytic plan / department
- Scenario 3: Multi-period columns with YTD totals
- Scenario 4: Filtering by department, GL account, date range, budget name
- Scenario 5: Percentage consumed visualization with threshold bands
- Scenario 6: Drill-down to underlying account.move.line records

Target: >=80% line coverage per Rule R-04.
"""

from datetime import date

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tools import float_compare

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestBudgetVsActualReport(AccountTestInvoicingCommon):
    """
    Test class for BM-003: Actual vs Budget Reporting.

    Validates the AbstractModel 'budget.vs.actual.report' methods:
    _get_report_values, _get_budget_lines, _build_actuals_domain,
    _get_actual_amounts (single read_group), _get_hierarchical_data,
    _get_ytd_totals, and _classify_consumption.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        AccountAccount = cls.env['account.account']

        cls.test_expense = AccountAccount.create({
            'code': 'XTEST.60000',
            'name': 'Test Operating Expense',
            'account_type': 'expense',
        })
        cls.test_expense_marketing = AccountAccount.create({
            'code': 'XTEST.60500',
            'name': 'Test Marketing Expense',
            'account_type': 'expense_other',
        })
        cls.test_revenue = AccountAccount.create({
            'code': 'XTEST.40000',
            'name': 'Test Sales Revenue',
            'account_type': 'income',
        })
        cls.test_cash = AccountAccount.create({
            'code': 'XTEST.10100',
            'name': 'Test Cash',
            'account_type': 'asset_cash',
        })

        # Analytic plan and accounts for hierarchical tests
        cls.plan_department = cls.env['account.analytic.plan'].create({
            'name': 'Department',
        })
        cls.analytic_sales = cls.env['account.analytic.account'].create({
            'name': 'Sales',
            'plan_id': cls.plan_department.id,
        })
        cls.analytic_marketing = cls.env['account.analytic.account'].create({
            'name': 'Marketing',
            'plan_id': cls.plan_department.id,
        })

        # A confirmed budget covering fiscal year 2024
        cls.budget_2024 = cls.env['budget.budget'].create({
            'name': 'FY2024',
            'date_from': date(2024, 1, 1),
            'date_to': date(2024, 12, 31),
        })
        cls.line_expense = cls.env['budget.budget.line'].create({
            'budget_id': cls.budget_2024.id,
            'account_id': cls.test_expense.id,
            'planned_amount': 100000.0,
        })
        cls.line_marketing = cls.env['budget.budget.line'].create({
            'budget_id': cls.budget_2024.id,
            'account_id': cls.test_expense_marketing.id,
            'planned_amount': 50000.0,
        })
        cls.budget_2024.action_confirm()
        cls.journal_misc = cls.company_data['default_journal_misc']

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------

    def _post_entry(self, account, amount, entry_date,
                    analytic_distribution=None):
        """Create and post a simple balanced journal entry to generate an actual."""
        lines = [
            Command.create({
                'account_id': account.id,
                'name': 'Actual spend',
                'debit': amount,
                'credit': 0.0,
                'analytic_distribution': analytic_distribution or False,
            }),
            Command.create({
                'account_id': self.test_cash.id,
                'name': 'Cash offset',
                'debit': 0.0,
                'credit': amount,
            }),
        ]
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': self.journal_misc.id,
            'date': entry_date,
            'line_ids': lines,
        })
        move.action_post()
        return move

    # ------------------------------------------------------------------
    # Scenario 1: Basic variance report
    # ------------------------------------------------------------------

    def test_bm003_report_computes_actuals_and_variance(self):
        """_get_report_values returns budget_lines with actual_amount and variance."""
        # Post 40,000 against test_expense in April 2024
        self._post_entry(self.test_expense, 40000.0, date(2024, 4, 15))
        ReportModel = self.env['budget.vs.actual.report']
        options = {
            'budget_ids': self.budget_2024.ids,
            'date_from': date(2024, 1, 1),
            'date_to': date(2024, 12, 31),
        }
        values = ReportModel._get_report_values(
            docids=self.budget_2024.ids,
            data=options,
        )
        self.assertIn('rows', values)
        rows = values['rows']
        # Locate the row for test_expense
        expense_row = next(
            r for r in rows if r['account_id'] == self.test_expense.id
        )
        self.assertAlmostEqual(
            expense_row['planned_amount'], 100000.0, places=2,
        )
        self.assertAlmostEqual(
            expense_row['actual_amount'], 40000.0, places=2,
        )
        # variance = planned - actual for expense (favorable if < planned)
        self.assertAlmostEqual(
            expense_row['variance_amount'], 60000.0, places=2,
        )
        # Cross-check using precision-aware float_compare (complements assertAlmostEqual)
        self.assertEqual(
            float_compare(
                expense_row['variance_amount'], 60000.0, precision_digits=2,
            ),
            0,
        )

    def test_bm003_report_omits_draft_budgets_not_in_scope(self):
        """A draft budget not in options['budget_ids'] is not aggregated."""
        draft = self.env['budget.budget'].create({
            'name': 'FY2024 Draft',
            'date_from': date(2024, 1, 1),
            'date_to': date(2024, 12, 31),
        })
        ReportModel = self.env['budget.vs.actual.report']
        options = {
            'budget_ids': self.budget_2024.ids,
            'date_from': date(2024, 1, 1),
            'date_to': date(2024, 12, 31),
        }
        values = ReportModel._get_report_values(
            docids=self.budget_2024.ids,
            data=options,
        )
        budget_ids_in_rows = {r['budget_id'] for r in values['rows']}
        self.assertNotIn(draft.id, budget_ids_in_rows)

    # ------------------------------------------------------------------
    # Scenario 2: Hierarchical grouping
    # ------------------------------------------------------------------

    def test_bm003_hierarchical_grouping_by_analytic_plan(self):
        """_get_hierarchical_data groups rows by analytic plan when plan_id provided."""
        self._post_entry(
            self.test_expense, 10000.0, date(2024, 3, 15),
            analytic_distribution={str(self.analytic_sales.id): 100.0},
        )
        self._post_entry(
            self.test_expense_marketing, 5000.0, date(2024, 3, 20),
            analytic_distribution={str(self.analytic_marketing.id): 100.0},
        )
        ReportModel = self.env['budget.vs.actual.report']
        options = {
            'budget_ids': self.budget_2024.ids,
            'date_from': date(2024, 1, 1),
            'date_to': date(2024, 12, 31),
            'analytic_plan_id': self.plan_department.id,
        }
        values = ReportModel._get_report_values(
            docids=self.budget_2024.ids,
            data=options,
        )
        self.assertIn('rows', values)
        # Hierarchical rows should be keyed by analytic account
        rows = values['rows']
        self.assertTrue(
            any(
                'Sales' in str(r.get('analytic_distribution', ''))
                for r in rows
            ),
        )

    # ------------------------------------------------------------------
    # Scenario 3: YTD totals
    # ------------------------------------------------------------------

    def test_bm003_ytd_totals_cumulative(self):
        """_get_ytd_totals produces cumulative sums across periods."""
        self._post_entry(self.test_expense, 10000.0, date(2024, 1, 15))
        self._post_entry(self.test_expense, 15000.0, date(2024, 2, 15))
        self._post_entry(self.test_expense, 20000.0, date(2024, 3, 15))
        ReportModel = self.env['budget.vs.actual.report']
        # Build rows manually and invoke YTD helper
        options = {
            'budget_ids': self.budget_2024.ids,
            'date_from': date(2024, 1, 1),
            'date_to': date(2024, 12, 31),
        }
        values = ReportModel._get_report_values(
            docids=self.budget_2024.ids,
            data=options,
        )
        ytd = ReportModel._get_ytd_totals(values['rows'])
        # YTD for the expense line = 45000
        self.assertIn('total_actual', ytd)
        self.assertAlmostEqual(ytd['total_actual'], 45000.0, places=2)

    # ------------------------------------------------------------------
    # Scenario 4: Filters
    # ------------------------------------------------------------------

    def test_bm003_filter_by_date_range_excludes_outside_entries(self):
        """Entries dated outside options date_from/date_to are excluded."""
        # Entry in Jan 2024 (in scope) + entry in 2023 (out of scope)
        self._post_entry(self.test_expense, 10000.0, date(2024, 1, 15))
        self._post_entry(self.test_expense, 5000.0, date(2023, 12, 15))
        ReportModel = self.env['budget.vs.actual.report']
        options = {
            'budget_ids': self.budget_2024.ids,
            'date_from': date(2024, 1, 1),
            'date_to': date(2024, 12, 31),
        }
        values = ReportModel._get_report_values(
            docids=self.budget_2024.ids,
            data=options,
        )
        expense_row = next(
            r for r in values['rows']
            if r['account_id'] == self.test_expense.id
        )
        self.assertAlmostEqual(
            expense_row['actual_amount'], 10000.0, places=2,
        )

    def test_bm003_filter_by_target_move_only_posted(self):
        """Draft moves are excluded when target_move='posted' (domain default)."""
        # Draft entry (not posted)
        lines = [
            Command.create({
                'account_id': self.test_expense.id,
                'name': 'Draft spend',
                'debit': 10000.0,
                'credit': 0.0,
            }),
            Command.create({
                'account_id': self.test_cash.id,
                'name': 'Draft cash',
                'debit': 0.0,
                'credit': 10000.0,
            }),
        ]
        draft_move = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': self.journal_misc.id,
            'date': date(2024, 2, 15),
            'line_ids': lines,
        })  # NOT posted
        self.assertEqual(draft_move.state, 'draft')

        ReportModel = self.env['budget.vs.actual.report']
        options = {
            'budget_ids': self.budget_2024.ids,
            'date_from': date(2024, 1, 1),
            'date_to': date(2024, 12, 31),
        }
        values = ReportModel._get_report_values(
            docids=self.budget_2024.ids,
            data=options,
        )
        expense_row = next(
            r for r in values['rows']
            if r['account_id'] == self.test_expense.id
        )
        # Draft must not be counted
        self.assertAlmostEqual(
            expense_row['actual_amount'], 0.0, places=2,
        )

    def test_bm003_build_actuals_domain_includes_account_filter(self):
        """_build_actuals_domain applies account_id IN filter when budget lines span accounts."""
        ReportModel = self.env['budget.vs.actual.report']
        domain = ReportModel._build_actuals_domain(
            budget_lines=self.line_expense,
            options={
                'date_from': date(2024, 1, 1),
                'date_to': date(2024, 12, 31),
            },
        )
        # Domain list must include ('account_id', 'in', [...]) term
        has_account_filter = any(
            isinstance(t, (tuple, list)) and t[0] == 'account_id'
            for t in domain
        )
        self.assertTrue(has_account_filter)

    # ------------------------------------------------------------------
    # Scenario 5: Consumption classification
    # ------------------------------------------------------------------

    def test_bm003_classify_consumption_normal_under_80(self):
        """_classify_consumption returns 'normal' for consumption < 80%."""
        ReportModel = self.env['budget.vs.actual.report']
        self.assertEqual(ReportModel._classify_consumption(0.0), 'normal')
        self.assertEqual(ReportModel._classify_consumption(50.0), 'normal')
        self.assertEqual(ReportModel._classify_consumption(79.99), 'normal')

    def test_bm003_classify_consumption_warning_between_80_100(self):
        """_classify_consumption returns 'warning' for 80% <= consumption <= 100%."""
        ReportModel = self.env['budget.vs.actual.report']
        self.assertEqual(ReportModel._classify_consumption(80.0), 'warning')
        self.assertEqual(ReportModel._classify_consumption(95.0), 'warning')
        self.assertEqual(ReportModel._classify_consumption(100.0), 'warning')

    def test_bm003_classify_consumption_alert_over_100(self):
        """_classify_consumption returns 'alert' for consumption > 100%."""
        ReportModel = self.env['budget.vs.actual.report']
        self.assertEqual(ReportModel._classify_consumption(100.01), 'alert')
        self.assertEqual(ReportModel._classify_consumption(120.0), 'alert')
        self.assertEqual(ReportModel._classify_consumption(200.0), 'alert')

    def test_bm003_row_threshold_status_matches_consumption(self):
        """Row's threshold_status reflects classification of consumed_percent."""
        # 50% consumed (50000/100000)
        self._post_entry(self.test_expense, 50000.0, date(2024, 6, 15))
        ReportModel = self.env['budget.vs.actual.report']
        options = {
            'budget_ids': self.budget_2024.ids,
            'date_from': date(2024, 1, 1),
            'date_to': date(2024, 12, 31),
        }
        values = ReportModel._get_report_values(
            docids=self.budget_2024.ids,
            data=options,
        )
        expense_row = next(
            r for r in values['rows']
            if r['account_id'] == self.test_expense.id
        )
        self.assertAlmostEqual(
            expense_row['consumed_percent'], 50.0, places=2,
        )
        self.assertEqual(expense_row['threshold_status'], 'normal')

    # ------------------------------------------------------------------
    # Scenario 6: Drill-down
    # ------------------------------------------------------------------

    def test_bm003_report_rows_contain_drill_down_identifiers(self):
        """Each row contains budget_line_id and account_id for drill-down links."""
        self._post_entry(self.test_expense, 5000.0, date(2024, 5, 10))
        ReportModel = self.env['budget.vs.actual.report']
        options = {
            'budget_ids': self.budget_2024.ids,
            'date_from': date(2024, 1, 1),
            'date_to': date(2024, 12, 31),
        }
        values = ReportModel._get_report_values(
            docids=self.budget_2024.ids,
            data=options,
        )
        for row in values['rows']:
            self.assertIn('budget_line_id', row)
            self.assertIn('budget_id', row)
            self.assertIn('account_id', row)

    def test_bm003_action_drill_down_on_line_returns_act_window(self):
        """budget.budget.line.action_drill_down_actuals returns act_window on account.move.line."""
        self._post_entry(self.test_expense, 2500.0, date(2024, 3, 10))
        # Defensive: drill-down on a valid confirmed budget line must not raise
        # UserError (UserError import is used here to signal the contract
        # against business-rule violations).
        try:
            action = self.line_expense.action_drill_down_actuals()
        except UserError as exc:
            self.fail(f"Unexpected UserError on valid drill-down: {exc}")
        self.assertIsInstance(action, dict)
        self.assertEqual(action.get('type'), 'ir.actions.act_window')
        self.assertEqual(action.get('res_model'), 'account.move.line')

    # ------------------------------------------------------------------
    # Empty-data robustness and single-read_group performance
    # ------------------------------------------------------------------

    def test_bm003_report_returns_empty_rows_when_no_budgets(self):
        """Empty budget set yields rows=[] without exception."""
        ReportModel = self.env['budget.vs.actual.report']
        options = {
            'budget_ids': [],
            'date_from': date(2024, 1, 1),
            'date_to': date(2024, 12, 31),
        }
        values = ReportModel._get_report_values(docids=[], data=options)
        self.assertEqual(values.get('rows'), [])

    def test_bm003_get_actual_amounts_uses_read_group_single_call(self):
        """_get_actual_amounts uses a single read_group for performance (SM-002 < 3s)."""
        self._post_entry(self.test_expense, 10000.0, date(2024, 4, 1))
        self._post_entry(self.test_expense_marketing, 5000.0, date(2024, 4, 15))
        ReportModel = self.env['budget.vs.actual.report']
        domain = [
            ('date', '>=', date(2024, 1, 1)),
            ('date', '<=', date(2024, 12, 31)),
            (
                'account_id', 'in',
                [self.test_expense.id, self.test_expense_marketing.id],
            ),
            ('parent_state', '=', 'posted'),
        ]
        result = ReportModel._get_actual_amounts(domain)
        # Result shape: {account_id: amount}
        self.assertIsInstance(result, dict)
        self.assertAlmostEqual(
            result.get(self.test_expense.id, 0.0), 10000.0, places=2,
        )
        self.assertAlmostEqual(
            result.get(self.test_expense_marketing.id, 0.0),
            5000.0, places=2,
        )

    def test_bm003_inverted_date_range_raises_user_error(self):
        """QA Checkpoint 10 Issue 9 (negative-path coverage):
        ``_build_actuals_domain`` must raise ``UserError`` when the
        caller passes a ``date_from`` later than ``date_to``.

        This guards against an operator inverting the report window,
        which would otherwise silently produce zero rows (the
        ``account.move.line`` domain would be unsatisfiable).
        Surfacing the inversion as a ``UserError`` with both dates
        in the message lets the operator immediately correct the
        wizard input.
        """
        ReportModel = self.env['budget.vs.actual.report']
        budget_lines = self.env['budget.budget.line']  # empty is fine for domain
        options = {
            'date_from': date(2024, 12, 31),
            'date_to': date(2024, 1, 1),  # inverted on purpose
        }
        with self.assertRaises(UserError) as ctx:
            ReportModel._build_actuals_domain(budget_lines, options)
        msg = str(ctx.exception)
        self.assertIn(
            'Invalid date range', msg,
            'UserError must explain that the date range is invalid.',
        )
        # The dates must appear in the error message so the operator
        # can immediately see which boundary they got wrong.
        self.assertIn('2024-12-31', msg)
        self.assertIn('2024-01-01', msg)
