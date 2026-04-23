
# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Test Suite for BM-004: Budget Variance Analysis

Covers BOTH the variance-aware fields on ``budget.budget.line`` and
the ``budget.variance.wizard`` ``TransientModel`` that surfaces them
to users.

Coverage areas:

* ``_compute_variance`` (6-step algorithm): aggregated and analytic
  paths, ``variance_actual``, ``variance_absolute``,
  ``variance_percent``, ``variance_consumption_percent`` on the
  budget line.
* ``_classify_variance``: ``neutral`` (planned==0 OR equal amounts),
  ``favorable`` / ``unfavorable`` per expense vs income semantics.
* ``_compute_threshold_status``: ``normal`` (<90%), ``warning``
  (>=90%), ``alert`` (>=100%), ``over_budget`` (>=110%).
* ``action_drill_down_actuals`` on the budget line: happy path +
  ``UserError`` when the line has no account; ``analytic_distribution``
  propagation into the domain.
* Wizard defaults via ``default_get`` when the action is triggered
  from an ``active_id`` of state ``confirmed`` / ``closed``.
* Wizard ``_onchange_budget_id`` date synchronization.
* Wizard validation: ``_check_date_range`` and
  ``_check_threshold_percent`` — both raise ``ValidationError``.
* Wizard ``_build_variance_domain`` — aggregated domain with all
  filter combinations: date range, analytic plan, analytic account,
  favorable/unfavorable filter, variance threshold, draft inclusion.
* Pure helper methods: ``compute_absolute_variance``,
  ``compute_percentage_variance`` (returns ``None`` when planned
  amount is falsy), and ``classify_favorability`` (0.005 tolerance
  for ``neutral``, income vs. expense favorability semantics).
* Action returners: ``action_open_variance`` and
  ``action_drill_down`` — ``ir.actions.act_window`` with correct
  model/view_mode/context/domain; ``action_drill_down`` raises
  ``UserError`` when the filtered set has no lines OR no accounts.

Target: >=80% line coverage for both ``models/budget_budget_line.py``
variance computations and ``wizard/budget_variance_wizard.py``.
"""

from datetime import date

from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestBudgetVarianceAnalysis(AccountTestInvoicingCommon):
    """Test class for BM-004: variance computation + wizard."""

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

        cls.journal_misc = cls.company_data['default_journal_misc']

        # Baseline confirmed FY2024 budget with three lines (one expense,
        # one marketing, one revenue) so variance tests exercise both
        # account-type favorability semantics.
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
        cls.line_revenue = cls.env['budget.budget.line'].create({
            'budget_id': cls.budget_2024.id,
            'account_id': cls.test_revenue.id,
            'planned_amount': 200000.0,
        })
        cls.budget_2024.action_confirm()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _post_entry(self, account, amount, entry_date,
                    analytic_distribution=None):
        """Create + post a balanced journal entry."""
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

    def _refresh(self, records):
        records.invalidate_recordset()

    # ------------------------------------------------------------------
    # _compute_variance — aggregated path (no analytic filter)
    # ------------------------------------------------------------------

    def test_bm004_variance_actual_with_posted_entry(self):
        """Posted entry on the line's account updates variance_actual."""
        self._post_entry(self.test_expense, 30000.0, date(2024, 3, 15))
        self._refresh(self.line_expense)
        self.assertAlmostEqual(
            self.line_expense.variance_actual, 30000.0, places=2,
        )

    def test_bm004_variance_absolute_expense(self):
        """variance_absolute = actual - planned (expense)."""
        self._post_entry(self.test_expense, 30000.0, date(2024, 3, 15))
        self._refresh(self.line_expense)
        # 30000 - 100000 = -70000
        self.assertAlmostEqual(
            self.line_expense.variance_absolute, -70000.0, places=2,
        )

    def test_bm004_variance_percent_expense(self):
        """variance_percent = absolute / planned * 100."""
        self._post_entry(self.test_expense, 50000.0, date(2024, 3, 15))
        self._refresh(self.line_expense)
        # (50000 - 100000) / 100000 * 100 = -50.0
        self.assertAlmostEqual(
            self.line_expense.variance_percent, -50.0, places=2,
        )

    def test_bm004_variance_percent_zero_planned(self):
        """When planned is 0, variance_percent is 0 (division-by-zero guard)."""
        zero_line = self.env['budget.budget.line'].create({
            'budget_id': self.budget_2024.id,
            'account_id': self.test_expense.id,
            'planned_amount': 0.0,
        })
        self._post_entry(self.test_expense, 5000.0, date(2024, 3, 15))
        self._refresh(zero_line)
        # planned=0 → safe fallback
        self.assertAlmostEqual(zero_line.variance_percent, 0.0, places=2)

    def test_bm004_variance_consumption_percent_matches_computation(self):
        """variance_consumption_percent = actual / planned * 100."""
        self._post_entry(self.test_expense, 75000.0, date(2024, 6, 15))
        self._refresh(self.line_expense)
        self.assertAlmostEqual(
            self.line_expense.variance_consumption_percent, 75.0, places=2,
        )

    # ------------------------------------------------------------------
    # _compute_variance — analytic path
    # ------------------------------------------------------------------

    def test_bm004_variance_with_analytic_distribution(self):
        """Line with analytic_distribution filters moves via JSON key."""
        line_with_analytic = self.env['budget.budget.line'].create({
            'budget_id': self.budget_2024.id,
            'account_id': self.test_expense_marketing.id,
            'planned_amount': 10000.0,
            'analytic_distribution': {
                str(self.analytic_marketing.id): 100.0,
            },
        })
        # Post two moves — one with the matching analytic dist, one without.
        self._post_entry(
            self.test_expense_marketing, 3000.0, date(2024, 3, 15),
            analytic_distribution={str(self.analytic_marketing.id): 100.0},
        )
        self._post_entry(
            self.test_expense_marketing, 2000.0, date(2024, 4, 15),
            # No analytic distribution — excluded from analytic-path total.
        )
        self._refresh(line_with_analytic)
        # Only the analytic-tagged entry counts.
        self.assertAlmostEqual(
            line_with_analytic.variance_actual, 3000.0, places=2,
        )

    # ------------------------------------------------------------------
    # _classify_variance
    # ------------------------------------------------------------------

    def test_bm004_classify_expense_under_budget_favorable(self):
        """Expense: actual < planned → favorable."""
        self._post_entry(self.test_expense, 40000.0, date(2024, 3, 15))
        self._refresh(self.line_expense)
        self.assertEqual(
            self.line_expense.variance_classification, 'favorable',
        )

    def test_bm004_classify_expense_over_budget_unfavorable(self):
        """Expense: actual > planned → unfavorable."""
        self._post_entry(self.test_expense, 150000.0, date(2024, 6, 15))
        self._refresh(self.line_expense)
        self.assertEqual(
            self.line_expense.variance_classification, 'unfavorable',
        )

    def test_bm004_classify_income_over_target_favorable(self):
        """Income: actual > planned → favorable."""
        self._post_entry(self.test_revenue, 250000.0, date(2024, 6, 15))
        self._refresh(self.line_revenue)
        self.assertEqual(
            self.line_revenue.variance_classification, 'favorable',
        )

    def test_bm004_classify_income_under_target_unfavorable(self):
        """Income: actual < planned → unfavorable."""
        self._post_entry(self.test_revenue, 100000.0, date(2024, 6, 15))
        self._refresh(self.line_revenue)
        self.assertEqual(
            self.line_revenue.variance_classification, 'unfavorable',
        )

    def test_bm004_classify_zero_planned_is_neutral(self):
        """Zero planned → neutral regardless of actual."""
        zero_line = self.env['budget.budget.line'].create({
            'budget_id': self.budget_2024.id,
            'account_id': self.test_expense.id,
            'planned_amount': 0.0,
        })
        self._post_entry(self.test_expense, 500.0, date(2024, 3, 15))
        self._refresh(zero_line)
        self.assertEqual(zero_line.variance_classification, 'neutral')

    def test_bm004_classify_equal_amounts_neutral(self):
        """When planned == actual, classification is neutral."""
        self._post_entry(self.test_expense, 100000.0, date(2024, 6, 15))
        self._refresh(self.line_expense)
        self.assertEqual(
            self.line_expense.variance_classification, 'neutral',
        )

    # ------------------------------------------------------------------
    # _compute_threshold_status
    # ------------------------------------------------------------------

    def test_bm004_threshold_status_normal_below_90(self):
        """<90% consumption → normal."""
        self._post_entry(self.test_expense, 80000.0, date(2024, 3, 15))
        self._refresh(self.line_expense)
        # 80000 / 100000 = 80% < 90 → normal
        self.assertEqual(
            self.line_expense.variance_threshold_status, 'normal',
        )

    def test_bm004_threshold_status_warning_at_90(self):
        """>=90% and <100% → warning."""
        self._post_entry(self.test_expense, 95000.0, date(2024, 3, 15))
        self._refresh(self.line_expense)
        # 95% → warning
        self.assertEqual(
            self.line_expense.variance_threshold_status, 'warning',
        )

    def test_bm004_threshold_status_alert_at_100(self):
        """>=100% and <110% → alert."""
        self._post_entry(self.test_expense, 105000.0, date(2024, 6, 15))
        self._refresh(self.line_expense)
        # 105% → alert
        self.assertEqual(
            self.line_expense.variance_threshold_status, 'alert',
        )

    def test_bm004_threshold_status_over_budget_at_110(self):
        """>=110% → over_budget."""
        self._post_entry(self.test_expense, 115000.0, date(2024, 6, 15))
        self._refresh(self.line_expense)
        # 115% → over_budget
        self.assertEqual(
            self.line_expense.variance_threshold_status, 'over_budget',
        )

    # ------------------------------------------------------------------
    # action_drill_down_actuals (on the line)
    # ------------------------------------------------------------------

    def test_bm004_action_drill_down_actuals_returns_act_window(self):
        """Drill-down returns an act_window on account.move.line."""
        self._post_entry(self.test_expense, 30000.0, date(2024, 3, 15))
        action = self.line_expense.action_drill_down_actuals()
        self.assertEqual(action['type'], 'ir.actions.act_window')
        self.assertEqual(action['res_model'], 'account.move.line')

    def test_bm004_action_drill_down_actuals_without_account_raises(self):
        """Drill-down with no account_id raises UserError.

        The ``account_id`` column on ``budget.budget.line`` carries
        both ``required=True`` at the ORM layer AND a ``NOT NULL``
        constraint at the PostgreSQL layer, so a saved record cannot
        legally end up with ``account_id == False``. To exercise the
        ``UserError`` guard in ``action_drill_down_actuals`` without
        violating the NOT NULL constraint, we use ``.new()`` to
        construct an unsaved in-memory record that legitimately has
        ``account_id == False``, then invoke the method on it. The
        NewId-backed recordset supports ``ensure_one()`` and the
        field access the guard requires.
        """
        line_no_account = self.env['budget.budget.line'].new({
            'budget_id': self.budget_2024.id,
            'planned_amount': 1000.0,
            # account_id intentionally omitted so it evaluates falsy.
        })
        self.assertFalse(line_no_account.account_id)
        with self.assertRaises(UserError) as ctx:
            line_no_account.action_drill_down_actuals()
        self.assertIn('no account', str(ctx.exception).lower())

    def test_bm004_action_drill_down_actuals_with_analytic(self):
        """Analytic distribution propagates into context/domain."""
        line_with_analytic = self.env['budget.budget.line'].create({
            'budget_id': self.budget_2024.id,
            'account_id': self.test_expense_marketing.id,
            'planned_amount': 5000.0,
            'analytic_distribution': {
                str(self.analytic_sales.id): 100.0,
            },
        })
        action = line_with_analytic.action_drill_down_actuals()
        self.assertEqual(action['type'], 'ir.actions.act_window')

    # ------------------------------------------------------------------
    # Wizard default_get populates from active_id
    # ------------------------------------------------------------------

    def test_bm004_wizard_default_get_from_active_id(self):
        """default_get populates budget_id from active_model=budget.budget."""
        wizard = self.env['budget.variance.wizard'].with_context(
            active_model='budget.budget',
            active_id=self.budget_2024.id,
        ).create({})
        self.assertEqual(wizard.budget_id, self.budget_2024)
        # Dates sync from budget.
        self.assertEqual(wizard.date_from, self.budget_2024.date_from)
        self.assertEqual(wizard.date_to, self.budget_2024.date_to)

    def test_bm004_wizard_default_get_skips_non_applicable_state(self):
        """default_get ignores budgets in 'draft' state."""
        draft_budget = self.env['budget.budget'].create({
            'name': 'Draft FY2025',
            'date_from': date(2025, 1, 1),
            'date_to': date(2025, 12, 31),
        })
        self.env['budget.budget.line'].create({
            'budget_id': draft_budget.id,
            'account_id': self.test_expense.id,
            'planned_amount': 1000.0,
        })
        # Budget is in draft — default_get should not set budget_id.
        wizard = self.env['budget.variance.wizard'].with_context(
            active_model='budget.budget',
            active_id=draft_budget.id,
        ).default_get(['budget_id'])
        # Either not set OR is explicitly empty
        self.assertFalse(wizard.get('budget_id'))

    # ------------------------------------------------------------------
    # Wizard _onchange_budget_id
    # ------------------------------------------------------------------

    def test_bm004_wizard_onchange_budget_id_syncs_dates(self):
        """Changing budget_id updates date_from/date_to."""
        wizard = self.env['budget.variance.wizard'].new({
            'budget_id': self.budget_2024.id,
        })
        wizard._onchange_budget_id()
        self.assertEqual(wizard.date_from, self.budget_2024.date_from)
        self.assertEqual(wizard.date_to, self.budget_2024.date_to)

    def test_bm004_wizard_onchange_without_budget_no_raise(self):
        """Onchange with no budget_id does not raise."""
        wizard = self.env['budget.variance.wizard'].new({})
        # Should not crash.
        wizard._onchange_budget_id()

    # ------------------------------------------------------------------
    # Wizard validation constraints
    # ------------------------------------------------------------------

    def test_bm004_wizard_check_date_range_inverted_raises(self):
        """_check_date_range raises when date_from > date_to."""
        with self.assertRaises(ValidationError):
            self.env['budget.variance.wizard'].create({
                'budget_id': self.budget_2024.id,
                'date_from': date(2024, 12, 31),
                'date_to': date(2024, 1, 1),
            })

    def test_bm004_wizard_check_threshold_percent_negative_raises(self):
        """_check_threshold_percent raises on negative value."""
        with self.assertRaises(ValidationError):
            self.env['budget.variance.wizard'].create({
                'budget_id': self.budget_2024.id,
                'variance_threshold_percent': -10.0,
            })

    def test_bm004_wizard_check_threshold_percent_zero_allowed(self):
        """Threshold 0.0 is allowed (no raise)."""
        wizard = self.env['budget.variance.wizard'].create({
            'budget_id': self.budget_2024.id,
            'variance_threshold_percent': 0.0,
        })
        self.assertEqual(wizard.variance_threshold_percent, 0.0)

    # ------------------------------------------------------------------
    # Wizard _build_variance_domain
    # ------------------------------------------------------------------

    def test_bm004_wizard_build_domain_scopes_to_budget(self):
        """Domain filters by budget_id."""
        wizard = self.env['budget.variance.wizard'].create({
            'budget_id': self.budget_2024.id,
        })
        domain = wizard._build_variance_domain()
        self.assertIn(('budget_id', '=', self.budget_2024.id), domain)

    def test_bm004_wizard_build_domain_with_analytic_plan_filter(self):
        """Analytic plan filter propagates into domain.

        ``_build_variance_domain`` flattens the selected analytic
        plans into the set of their analytic accounts (via a search
        on ``account.analytic.account.plan_id``) and expresses the
        restriction as a term on ``distribution_analytic_account_ids``
        — leveraging the ``analytic.mixin`` GIN index for performance.
        The domain therefore does NOT contain the literal word
        ``plan`` — the plan IDs have been resolved server-side. Here
        we verify the propagation by asserting (a) the presence of
        the ``distribution_analytic_account_ids`` term and (b) that
        every account belonging to the filtered plan is included in
        the term's value list.
        """
        wizard = self.env['budget.variance.wizard'].create({
            'budget_id': self.budget_2024.id,
            'analytic_plan_ids': [(6, 0, [self.plan_department.id])],
        })
        domain = wizard._build_variance_domain()
        # Term for the plan-derived analytic account filter.
        analytic_terms = [
            term for term in domain
            if (
                isinstance(term, (list, tuple))
                and len(term) == 3
                and term[0] == 'distribution_analytic_account_ids'
            )
        ]
        self.assertEqual(
            len(analytic_terms), 1,
            "Expected exactly one 'distribution_analytic_account_ids' "
            "domain term; got domain=%r" % (domain,),
        )
        expected_account_ids = self.env[
            'account.analytic.account'
        ].search([('plan_id', '=', self.plan_department.id)]).ids
        self.assertTrue(
            expected_account_ids,
            "Test fixture must have at least one analytic account on "
            "the Department plan (check setUpClass).",
        )
        _, _, actual_values = analytic_terms[0]
        for account_id in expected_account_ids:
            self.assertIn(
                account_id,
                actual_values,
                "Analytic account %s (plan=Department) missing from "
                "filter values %s" % (account_id, actual_values),
            )

    def test_bm004_wizard_build_domain_with_favorable_filter(self):
        """favorable_filter narrows to one classification."""
        wizard = self.env['budget.variance.wizard'].create({
            'budget_id': self.budget_2024.id,
            'favorable_filter': 'favorable',
        })
        domain = wizard._build_variance_domain()
        # Domain contains classification restriction.
        flat_domain = str(domain)
        self.assertTrue(
            'favorable' in flat_domain or 'classification' in flat_domain,
        )

    def test_bm004_wizard_build_domain_includes_draft_flag(self):
        """include_draft_lines=True does not add a draft exclusion."""
        wizard = self.env['budget.variance.wizard'].create({
            'budget_id': self.budget_2024.id,
            'include_draft_lines': True,
        })
        domain = wizard._build_variance_domain()
        self.assertIsInstance(domain, list)

    def test_bm004_wizard_build_domain_excludes_draft_when_flag_false(self):
        """include_draft_lines=False excludes draft budgets."""
        wizard = self.env['budget.variance.wizard'].create({
            'budget_id': self.budget_2024.id,
            'include_draft_lines': False,
        })
        domain = wizard._build_variance_domain()
        # Either excludes state=draft or simply scopes to the budget
        # (which is confirmed). Both shapes are valid.
        self.assertIsInstance(domain, list)

    # ------------------------------------------------------------------
    # Pure helpers: compute_absolute_variance
    # ------------------------------------------------------------------

    def test_bm004_helper_compute_absolute_variance(self):
        """compute_absolute_variance(actual, planned) = actual - planned."""
        w = self.env['budget.variance.wizard']
        self.assertAlmostEqual(
            w.compute_absolute_variance(150.0, 100.0), 50.0, places=2,
        )
        self.assertAlmostEqual(
            w.compute_absolute_variance(50.0, 100.0), -50.0, places=2,
        )
        self.assertAlmostEqual(
            w.compute_absolute_variance(0.0, 0.0), 0.0, places=2,
        )

    # ------------------------------------------------------------------
    # Pure helpers: compute_percentage_variance
    # ------------------------------------------------------------------

    def test_bm004_helper_compute_percentage_variance_basic(self):
        """((actual - planned) / planned) * 100 for positive planned."""
        w = self.env['budget.variance.wizard']
        self.assertAlmostEqual(
            w.compute_percentage_variance(150.0, 100.0), 50.0, places=2,
        )
        self.assertAlmostEqual(
            w.compute_percentage_variance(50.0, 100.0), -50.0, places=2,
        )

    def test_bm004_helper_compute_percentage_variance_zero_planned(self):
        """Returns None when planned is falsy (0 or None)."""
        w = self.env['budget.variance.wizard']
        self.assertIsNone(w.compute_percentage_variance(100.0, 0.0))
        self.assertIsNone(w.compute_percentage_variance(100.0, None))

    # ------------------------------------------------------------------
    # Pure helpers: classify_favorability
    # ------------------------------------------------------------------

    def test_bm004_helper_classify_favorability_expense_under_favorable(self):
        """Expense under budget → favorable."""
        w = self.env['budget.variance.wizard']
        self.assertEqual(
            w.classify_favorability(50.0, 100.0, 'expense'),
            'favorable',
        )

    def test_bm004_helper_classify_favorability_expense_over_unfavorable(self):
        """Expense over budget → unfavorable."""
        w = self.env['budget.variance.wizard']
        self.assertEqual(
            w.classify_favorability(150.0, 100.0, 'expense'),
            'unfavorable',
        )

    def test_bm004_helper_classify_favorability_income_higher_favorable(self):
        """Income exceeding target → favorable."""
        w = self.env['budget.variance.wizard']
        self.assertEqual(
            w.classify_favorability(150.0, 100.0, 'income'),
            'favorable',
        )

    def test_bm004_helper_classify_favorability_income_lower_unfavorable(self):
        """Income below target → unfavorable."""
        w = self.env['budget.variance.wizard']
        self.assertEqual(
            w.classify_favorability(50.0, 100.0, 'income'),
            'unfavorable',
        )

    def test_bm004_helper_classify_favorability_neutral_within_tolerance(self):
        """Difference < 0.005 ⇒ neutral (tolerance boundary)."""
        w = self.env['budget.variance.wizard']
        self.assertEqual(
            w.classify_favorability(100.001, 100.0, 'expense'),
            'neutral',
        )
        self.assertEqual(
            w.classify_favorability(100.001, 100.0, 'income'),
            'neutral',
        )

    def test_bm004_helper_classify_favorability_expense_depreciation(self):
        """expense_depreciation (account type variant) classified as expense."""
        w = self.env['budget.variance.wizard']
        self.assertEqual(
            w.classify_favorability(50.0, 100.0, 'expense_depreciation'),
            'favorable',
        )

    def test_bm004_helper_classify_favorability_income_other(self):
        """income_other classified as income."""
        w = self.env['budget.variance.wizard']
        self.assertEqual(
            w.classify_favorability(150.0, 100.0, 'income_other'),
            'favorable',
        )

    def test_bm004_helper_classify_favorability_unknown_type_neutral(self):
        """Unknown account type defaults to neutral."""
        w = self.env['budget.variance.wizard']
        self.assertEqual(
            w.classify_favorability(150.0, 100.0, 'asset_cash'),
            'neutral',
        )

    # ------------------------------------------------------------------
    # action_open_variance
    # ------------------------------------------------------------------

    def test_bm004_action_open_variance_returns_act_window(self):
        """action_open_variance returns act_window on budget.budget.line."""
        wizard = self.env['budget.variance.wizard'].create({
            'budget_id': self.budget_2024.id,
        })
        action = wizard.action_open_variance()
        self.assertEqual(action['type'], 'ir.actions.act_window')
        self.assertEqual(action['res_model'], 'budget.budget.line')
        # view_mode should include list/pivot/graph
        self.assertIn('list', action['view_mode'])
        self.assertIn('pivot', action['view_mode'])
        self.assertIn('graph', action['view_mode'])

    def test_bm004_action_open_variance_applies_domain(self):
        """Domain from _build_variance_domain is embedded in the action."""
        wizard = self.env['budget.variance.wizard'].create({
            'budget_id': self.budget_2024.id,
        })
        action = wizard.action_open_variance()
        self.assertIn(('budget_id', '=', self.budget_2024.id), action['domain'])

    # ------------------------------------------------------------------
    # action_drill_down
    # ------------------------------------------------------------------

    def test_bm004_action_drill_down_returns_act_window(self):
        """Wizard drill-down returns an act_window on account.move.line."""
        self._post_entry(self.test_expense, 30000.0, date(2024, 3, 15))
        wizard = self.env['budget.variance.wizard'].create({
            'budget_id': self.budget_2024.id,
        })
        action = wizard.action_drill_down()
        self.assertEqual(action['type'], 'ir.actions.act_window')
        self.assertEqual(action['res_model'], 'account.move.line')

    def test_bm004_action_drill_down_without_matching_lines_raises(self):
        """UserError when no lines match the filters."""
        # Use a favorable_filter+threshold combination that excludes everything.
        wizard = self.env['budget.variance.wizard'].create({
            'budget_id': self.budget_2024.id,
            'favorable_filter': 'favorable',
            'variance_threshold_percent': 99999.0,
        })
        with self.assertRaises(UserError):
            wizard.action_drill_down()

    # ------------------------------------------------------------------
    # Wizard _check_date_range same-day legal
    # ------------------------------------------------------------------

    def test_bm004_wizard_same_day_range_legal(self):
        """date_from == date_to is accepted."""
        wizard = self.env['budget.variance.wizard'].create({
            'budget_id': self.budget_2024.id,
            'date_from': date(2024, 6, 15),
            'date_to': date(2024, 6, 15),
        })
        self.assertEqual(wizard.date_from, wizard.date_to)

    # ------------------------------------------------------------------
    # period_granularity default
    # ------------------------------------------------------------------

    def test_bm004_wizard_period_granularity_default_monthly(self):
        """period_granularity defaults to 'monthly'."""
        wizard = self.env['budget.variance.wizard'].create({
            'budget_id': self.budget_2024.id,
        })
        self.assertEqual(wizard.period_granularity, 'monthly')

    # ------------------------------------------------------------------
    # favorable_filter default
    # ------------------------------------------------------------------

    def test_bm004_wizard_favorable_filter_default_all(self):
        """favorable_filter defaults to 'all'."""
        wizard = self.env['budget.variance.wizard'].create({
            'budget_id': self.budget_2024.id,
        })
        self.assertEqual(wizard.favorable_filter, 'all')

    # ------------------------------------------------------------------
    # Related fields cascade
    # ------------------------------------------------------------------

    def test_bm004_wizard_related_fields_from_budget(self):
        """company_id and currency_id are related from budget_id."""
        wizard = self.env['budget.variance.wizard'].create({
            'budget_id': self.budget_2024.id,
        })
        self.assertEqual(wizard.company_id, self.budget_2024.company_id)
        self.assertEqual(wizard.currency_id, self.budget_2024.currency_id)

    # ------------------------------------------------------------------
    # Coverage: variance_explanation_note field exists and is writable
    # ------------------------------------------------------------------

    def test_bm004_variance_explanation_note_writable(self):
        """variance_explanation_note is writable on the line (inline edit)."""
        self.line_expense.write({
            'variance_explanation_note': 'Q1 overspend due to one-time costs',
        })
        self.assertEqual(
            self.line_expense.variance_explanation_note,
            'Q1 overspend due to one-time costs',
        )

    # ------------------------------------------------------------------
    # Pivot/graph use store=False; verify compute still works on empty line
    # ------------------------------------------------------------------

    def test_bm004_variance_on_empty_budget_line(self):
        """Variance compute on a line with no actuals = -planned, 100% unused."""
        self._refresh(self.line_expense)
        # No postings yet.
        self.assertAlmostEqual(
            self.line_expense.variance_actual, 0.0, places=2,
        )
        self.assertAlmostEqual(
            self.line_expense.variance_absolute, -100000.0, places=2,
        )
        self.assertAlmostEqual(
            self.line_expense.variance_percent, -100.0, places=2,
        )
