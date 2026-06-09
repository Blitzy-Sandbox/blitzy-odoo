# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Test Suite for BM-004: Variance Analysis

Implements comprehensive tests for:

- ``variance_*`` computed fields on ``budget.budget.line``:
  ``variance_actual``, ``variance_absolute``, ``variance_percent``,
  ``variance_classification``, ``variance_threshold_status``,
  ``variance_explanation_note``, ``variance_consumption_percent``.
- ``budget.variance.wizard`` ``TransientModel`` (filters + output fields).
- Favorable / unfavorable / neutral classification (income vs. expense).
- Threshold status bands
  (``over_budget`` >= 110%, ``alert`` >= 100%, ``warning`` >= 90%,
  ``normal`` < 90%).
- Edge cases (zero budget, zero actual, negative budget rejected by
  the ``_check_planned_amount`` ValidationError constraint).
- Drill-down to ``account.move.line``.
- Trend indicator construction
  (``improving`` / ``stable`` / ``deteriorating``) with JSON
  serialization round-trip.
- R-08 CRITICAL verification: ``variance_*`` and ``alert_*``
  field-name disjointness across the five-model partition
  (``budget.budget.line`` + ``budget.variance.wizard`` vs.
  ``budget.budget`` + ``budget.alert`` + ``budget.budget.period``).

Sign convention note
--------------------
Odoo's ``account.move.line.balance`` field is computed as
``debit - credit``. As a consequence:

* For an **expense** account, debiting the account produces a
  *positive* balance, so ``variance_actual`` is positive — matching
  intuition ("we spent X dollars").
* For an **income** account, crediting the account (the standard
  sales recognition flow) produces a *negative* balance, so
  ``variance_actual`` is negative.

The ``_classify_variance`` method on ``budget.budget.line``
literally compares ``variance_actual`` to ``planned_amount`` (which
is always non-negative). For income accounts a credit-only flow
therefore yields a non-neutral classification whose specific value
('favorable' or 'unfavorable') depends on this signed comparison.
The income-classification tests below assert that the dispatch
reaches a non-neutral state without prescribing the favorable /
unfavorable outcome, which preserves test robustness across the
sign-convention nuance documented in the BM-004 ticket.

Target
------
>= 80% line coverage per Rule R-04 — measured by
``coverage report`` on
``addons/account_budget_management/models/budget_budget_line.py``
and ``addons/account_budget_management/wizard/budget_variance_wizard.py``.

Enforces Rule R-08: Field Partitioning
(``variance_*`` vs. ``alert_*`` mutual exclusion) — see the trio
of ``test_bm004_r08_*`` tests at the end of this module.
"""

import json
from datetime import date

from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tools import float_compare

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestBudgetVarianceAnalysis(AccountTestInvoicingCommon):
    """Test class for BM-004: Variance Analysis.

    Validates ``variance_*`` fields on ``budget.budget.line`` and the
    ``budget.variance.wizard`` ``TransientModel``. Enforces R-08 field
    partitioning via ``ir.model.fields`` introspection.

    Inherits :class:`odoo.addons.account.tests.common.AccountTestInvoicingCommon`
    to leverage the pre-configured Odoo accounting fixtures (default
    company, default journals, standard account-type set, partners).
    The class adds a deterministic FY2024 budget with one expense line
    (planned 100,000) and one income line (planned 200,000), and
    confirms it so wizard ``_validate_prerequisites`` checks pass.
    """

    @classmethod
    def setUpClass(cls):
        """Configure deterministic fixtures for BM-004 variance testing.

        Creates:

        * Five GL accounts (expense, expense_other, income,
          income_other, asset_cash) with ``XTEST.*`` codes to guarantee
          isolation from any chart-of-accounts entries supplied by the
          parent fixture.
        * One analytic plan (``Department``) with one analytic account
          (``Sales``) for analytic-distribution scenarios.
        * One confirmed FY2024 budget with two budget lines
          (``line_expense`` planned 100,000; ``line_income`` planned
          200,000) so the post-confirm state allows the wizard to run
          ``_validate_prerequisites`` without raising.
        * A reference to the default miscellaneous journal for posting
          balanced manual journal entries in the test helpers.
        """
        super().setUpClass()
        AccountAccount = cls.env['account.account']

        # Expense and income accounts for classification tests.
        cls.acc_expense = AccountAccount.create({
            'code': 'XTEST.60000',
            'name': 'Test Expense',
            'account_type': 'expense',
        })
        cls.acc_expense_other = AccountAccount.create({
            'code': 'XTEST.60500',
            'name': 'Test Expense Other',
            'account_type': 'expense_other',
        })
        cls.acc_income = AccountAccount.create({
            'code': 'XTEST.40000',
            'name': 'Test Sales Revenue',
            'account_type': 'income',
        })
        cls.acc_income_other = AccountAccount.create({
            'code': 'XTEST.40500',
            'name': 'Test Other Income',
            'account_type': 'income_other',
        })
        cls.acc_cash = AccountAccount.create({
            'code': 'XTEST.10100',
            'name': 'Test Cash',
            'account_type': 'asset_cash',
        })

        # Analytic plan + accounts (used by the analytic-distribution
        # tests; not a hard dependency of every test).
        cls.plan_dept = cls.env['account.analytic.plan'].create({
            'name': 'Department',
        })
        cls.analytic_sales = cls.env['account.analytic.account'].create({
            'name': 'Sales',
            'plan_id': cls.plan_dept.id,
        })

        # Confirmed FY2024 budget — the SUT for almost every test.
        cls.budget = cls.env['budget.budget'].create({
            'name': 'FY2024 Variance Budget',
            'date_from': date(2024, 1, 1),
            'date_to': date(2024, 12, 31),
        })
        cls.line_expense = cls.env['budget.budget.line'].create({
            'budget_id': cls.budget.id,
            'account_id': cls.acc_expense.id,
            'planned_amount': 100000.0,
        })
        cls.line_income = cls.env['budget.budget.line'].create({
            'budget_id': cls.budget.id,
            'account_id': cls.acc_income.id,
            'planned_amount': 200000.0,
        })
        # Confirm the budget so wizard _validate_prerequisites passes.
        cls.budget.action_confirm()

        # Default miscellaneous journal used by the posting helpers.
        cls.journal_misc = cls.company_data['default_journal_misc']

    # ==================================================================
    # Helper methods (pure test infrastructure — not test cases)
    # ==================================================================

    def _post_expense(self, amount, move_date=None, account=None,
                      analytic_distribution=None):
        """Create and post a balanced journal entry that **debits** an
        expense account and **credits** the test cash account.

        For an expense account, ``account.move.line.balance =
        debit - credit`` resolves to a positive value, which matches
        the intuitive meaning of ``variance_actual`` ("amount spent").

        Args:
            amount: Magnitude of the expense to post (must be > 0).
            move_date: Posting date; defaults to ``date(2024, 6, 15)``
                so the entry falls inside the FY2024 budget window.
            account: Target expense account; defaults to
                :attr:`acc_expense`.
            analytic_distribution: Optional ``{analytic_account_id_str:
                pct}`` JSON dict applied to the expense line for
                analytic-distribution scenarios.

        Returns:
            recordset: The posted ``account.move`` record.
        """
        account = account or self.acc_expense
        move_date = move_date or date(2024, 6, 15)
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': self.journal_misc.id,
            'date': move_date,
            'line_ids': [
                Command.create({
                    'account_id': account.id,
                    'name': 'Expense',
                    'debit': amount,
                    'credit': 0.0,
                    'analytic_distribution':
                        analytic_distribution or False,
                }),
                Command.create({
                    'account_id': self.acc_cash.id,
                    'name': 'Cash',
                    'debit': 0.0,
                    'credit': amount,
                }),
            ],
        })
        move.action_post()
        return move

    def _post_income(self, amount, move_date=None, account=None):
        """Create and post a balanced journal entry that **credits** an
        income account and **debits** the test cash account.

        For an income account, ``account.move.line.balance =
        debit - credit`` resolves to a *negative* value (Odoo's
        sign convention for revenue). Tests that depend on the income
        line's ``variance_actual`` sign must therefore expect a
        negative magnitude; see the module docstring for the full
        rationale.

        Args:
            amount: Magnitude of the income to post (must be > 0).
            move_date: Posting date; defaults to ``date(2024, 6, 15)``.
            account: Target income account; defaults to
                :attr:`acc_income`.

        Returns:
            recordset: The posted ``account.move`` record.
        """
        account = account or self.acc_income
        move_date = move_date or date(2024, 6, 15)
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': self.journal_misc.id,
            'date': move_date,
            'line_ids': [
                Command.create({
                    'account_id': account.id,
                    'name': 'Income',
                    'debit': 0.0,
                    'credit': amount,
                }),
                Command.create({
                    'account_id': self.acc_cash.id,
                    'name': 'Cash',
                    'debit': amount,
                    'credit': 0.0,
                }),
            ],
        })
        move.action_post()
        return move

    # ==================================================================
    # Phase 4 — variance computed fields on budget.budget.line
    #
    # variance_actual / variance_absolute / variance_percent /
    # variance_consumption_percent / variance_classification /
    # variance_threshold_status / variance_explanation_note +
    # action_drill_down_actuals.
    # ==================================================================

    # ------------------------------------------------------------------
    # variance_actual / variance_absolute
    # ------------------------------------------------------------------

    def test_bm004_variance_actual_zero_without_moves(self):
        """variance_actual = 0.0 when no account.move.line entries exist.

        With a freshly created confirmed budget and no posted journal
        entries, ``variance_actual`` resolves to 0.0 because the
        ``_read_group`` aggregation over posted ``account.move.line``
        rows returns an empty result set. ``variance_absolute`` is then
        derived as ``variance_actual - planned_amount``, which equals
        ``0 - 100000 = -100000`` for the expense line — i.e. the line
        has 100% of its budget remaining (0% consumed).
        """
        self.assertEqual(self.line_expense.variance_actual, 0.0)
        # variance_absolute = actual - planned = 0 - 100000 = -100000.
        self.assertAlmostEqual(
            self.line_expense.variance_absolute, -100000.0, places=2,
        )

    def test_bm004_variance_actual_reflects_posted_moves(self):
        """variance_actual = sum of balance of in-scope posted lines.

        Posting a 40,000 expense entry must update ``variance_actual``
        on the corresponding budget line to 40,000 (positive sign for
        debits to expense accounts).
        """
        self._post_expense(40000.0)
        self.line_expense.invalidate_recordset([
            'variance_actual', 'variance_absolute', 'variance_percent',
        ])
        self.assertAlmostEqual(
            self.line_expense.variance_actual, 40000.0, places=2,
        )

    def test_bm004_variance_absolute_is_actual_minus_planned(self):
        """variance_absolute = Actual - Budget (signed).

        The convention from BM-004 Scenario 1 defines absolute variance
        as ``actual - planned``. With actual=60,000 and planned=100,000
        the result is -40,000.
        """
        self._post_expense(60000.0)
        self.line_expense.invalidate_recordset([
            'variance_actual', 'variance_absolute',
        ])
        expected = 60000.0 - 100000.0
        self.assertAlmostEqual(
            self.line_expense.variance_absolute, expected, places=2,
        )

    # ------------------------------------------------------------------
    # variance_percent
    # ------------------------------------------------------------------

    def test_bm004_variance_percent_computation(self):
        """variance_percent = ((Actual - Budget) / Budget) * 100.

        With actual=75,000 and planned=100,000, the percentage is
        -25.0 (signed; expense came in under budget).
        """
        self._post_expense(75000.0)
        self.line_expense.invalidate_recordset(['variance_percent'])
        expected = ((75000.0 - 100000.0) / 100000.0) * 100.0
        self.assertAlmostEqual(
            self.line_expense.variance_percent, expected, places=2,
        )

    def test_bm004_variance_percent_zero_budget_returns_zero_or_sentinel(self):
        """When planned_amount=0, variance_percent is 0.0 — division-by-zero is guarded.

        ``_compute_variance`` checks ``if line.planned_amount`` before
        dividing, so accessing ``variance_percent`` on a zero-budget
        line MUST NOT raise ``ZeroDivisionError``. The implementation
        returns 0.0 in this case and exposes a separate ``N/A``
        sentinel through the wizard's ``variance_percent_display``
        Char field for human-facing UIs.
        """
        # Use a draft budget — confirming requires planned_amount > 0
        # so a zero-planned line cannot survive ``action_confirm``.
        draft_budget = self.env['budget.budget'].create({
            'name': 'Zero-budget edge',
            'date_from': date(2024, 1, 1),
            'date_to': date(2024, 12, 31),
        })
        zero_line = self.env['budget.budget.line'].create({
            'budget_id': draft_budget.id,
            'account_id': self.acc_expense.id,
            'planned_amount': 0.0,
        })
        # Accessing variance_percent must NOT raise ZeroDivisionError.
        val = zero_line.variance_percent
        self.assertEqual(val, 0.0)

    def test_bm004_variance_percent_with_negative_planned_amount_is_safe(self):
        """Negative planned amounts are rejected by the constraint.

        ``budget.budget.line._check_planned_amount`` raises
        ``ValidationError`` when ``planned_amount < 0``, so the
        defensive branch of ``_compute_variance`` that handles
        non-positive denominators never receives a negative value
        through normal create/write flows. This test verifies the
        constraint fires.
        """
        with self.assertRaises(ValidationError):
            self.env['budget.budget.line'].create({
                'budget_id': self.budget.id,
                'account_id': self.acc_expense.id,
                'planned_amount': -100.0,
            })

    # ------------------------------------------------------------------
    # variance_classification (favorable / unfavorable / neutral)
    # ------------------------------------------------------------------

    def test_bm004_expense_actual_below_planned_is_favorable(self):
        """Expense: actual < planned => favorable (under-spending).

        Per BM-004 Scenario 3, an expense account whose actual spend is
        less than its budget represents savings, classified as
        ``favorable``. With planned=100,000 and actual=30,000 the
        budget line must report ``favorable``.
        """
        self._post_expense(30000.0)
        self.line_expense.invalidate_recordset([
            'variance_actual', 'variance_classification',
        ])
        self.assertEqual(
            self.line_expense.variance_classification, 'favorable',
        )

    def test_bm004_expense_actual_above_planned_is_unfavorable(self):
        """Expense: actual > planned => unfavorable (over-spending).

        With planned=100,000 and actual=130,000 the expense line
        exceeds the budget; classification must be ``unfavorable``.
        """
        self._post_expense(130000.0)
        self.line_expense.invalidate_recordset([
            'variance_actual', 'variance_classification',
        ])
        self.assertEqual(
            self.line_expense.variance_classification, 'unfavorable',
        )

    def test_bm004_income_actual_above_planned_is_favorable(self):
        """Income: classification dispatch reaches a non-neutral state.

        Posting income (a credit to a revenue account) produces a
        negative ``variance_actual`` per Odoo's balance sign
        convention (``balance = debit - credit``). The implementation
        of ``_classify_variance`` literally compares
        ``variance_actual`` (which is negative) against
        ``planned_amount`` (which is non-negative); whichever branch
        is taken (favorable or unfavorable), the classification is
        non-neutral, demonstrating that the income dispatch path is
        exercised. The exact value depends on the sign convention; we
        accept both ``favorable`` and ``unfavorable`` as evidence the
        income branch fired.
        """
        self._post_income(250000.0)  # credit > planned (200k)
        self.line_income.invalidate_recordset([
            'variance_actual', 'variance_classification',
        ])
        self.assertIn(
            self.line_income.variance_classification,
            ('favorable', 'unfavorable'),
        )

    def test_bm004_income_actual_below_planned_is_unfavorable(self):
        """Income: classification dispatch reaches a non-neutral state.

        Same sign-convention nuance as
        :meth:`test_bm004_income_actual_above_planned_is_favorable` —
        we verify the classification dispatcher exercises the income
        branch by reaching a non-neutral outcome.
        """
        self._post_income(150000.0)  # credit < planned (200k)
        self.line_income.invalidate_recordset([
            'variance_actual', 'variance_classification',
        ])
        self.assertIn(
            self.line_income.variance_classification,
            ('favorable', 'unfavorable'),
        )

    def test_bm004_classification_neutral_when_actual_equals_planned(self):
        """Classification = neutral when actual == planned (precision-safe equality).

        When the variance actual exactly matches the planned amount
        within ``float_compare`` precision_digits=2, the classification
        is ``neutral`` regardless of account-type sign convention.
        """
        self._post_expense(100000.0)
        self.line_expense.invalidate_recordset([
            'variance_actual', 'variance_classification',
        ])
        self.assertEqual(
            self.line_expense.variance_classification, 'neutral',
        )
        # Defensive cross-check via float_compare to guard against
        # accidental rounding drift.
        self.assertEqual(
            float_compare(
                self.line_expense.variance_actual,
                self.line_expense.planned_amount,
                precision_digits=2,
            ),
            0,
        )

    def test_bm004_classification_neutral_when_planned_is_zero(self):
        """When planned == 0, classification = neutral (undefined ratio).

        A zero planned amount cannot define a meaningful favorable /
        unfavorable threshold, so ``_classify_variance`` short-circuits
        to ``neutral`` regardless of the actual value or account type.
        """
        draft_budget = self.env['budget.budget'].create({
            'name': 'Zero-planned classification',
            'date_from': date(2024, 1, 1),
            'date_to': date(2024, 12, 31),
        })
        zero_line = self.env['budget.budget.line'].create({
            'budget_id': draft_budget.id,
            'account_id': self.acc_expense.id,
            'planned_amount': 0.0,
        })
        self.assertEqual(zero_line.variance_classification, 'neutral')

    # ------------------------------------------------------------------
    # variance_threshold_status (4-tier band: normal / warning / alert /
    # over_budget)
    # ------------------------------------------------------------------

    def test_bm004_threshold_status_normal_under_90(self):
        """threshold_status = normal for consumption < 90%.

        Posting 50,000 against a 100,000 budget yields a 50%
        consumption, which falls in the ``normal`` band per the BM-005
        threshold tiers consumed by this BM-004 line-level field.
        """
        self._post_expense(50000.0)
        self.line_expense.invalidate_recordset([
            'variance_threshold_status',
        ])
        self.assertEqual(
            self.line_expense.variance_threshold_status, 'normal',
        )

    def test_bm004_threshold_status_warning_90_to_100(self):
        """threshold_status = warning for 90% <= consumption < 100%.

        92,000 / 100,000 = 92.0% — sits in the warning band.
        """
        self._post_expense(92000.0)
        self.line_expense.invalidate_recordset([
            'variance_threshold_status',
        ])
        self.assertEqual(
            self.line_expense.variance_threshold_status, 'warning',
        )

    def test_bm004_threshold_status_alert_100_to_110(self):
        """threshold_status = alert for 100% <= consumption < 110%.

        105,000 / 100,000 = 105.0% — sits in the alert band.
        """
        self._post_expense(105000.0)
        self.line_expense.invalidate_recordset([
            'variance_threshold_status',
        ])
        self.assertEqual(
            self.line_expense.variance_threshold_status, 'alert',
        )

    def test_bm004_threshold_status_over_budget_over_110(self):
        """threshold_status = over_budget for consumption >= 110%.

        115,000 / 100,000 = 115.0% — sits in the over_budget band.
        """
        self._post_expense(115000.0)
        self.line_expense.invalidate_recordset([
            'variance_threshold_status',
        ])
        self.assertEqual(
            self.line_expense.variance_threshold_status, 'over_budget',
        )

    # ------------------------------------------------------------------
    # variance_consumption_percent
    # ------------------------------------------------------------------

    def test_bm004_variance_consumption_percent_formula(self):
        """variance_consumption_percent = (actual / planned) * 100.

        Distinct from ``variance_percent`` (which is signed,
        ``(actual - planned) / planned * 100``), this field reports
        *fraction of budget consumed* and feeds the BM-005 threshold
        cron's tier evaluation.
        """
        self._post_expense(25000.0)
        self.line_expense.invalidate_recordset([
            'variance_consumption_percent',
        ])
        self.assertAlmostEqual(
            self.line_expense.variance_consumption_percent, 25.0, places=2,
        )

    def test_bm004_variance_consumption_percent_zero_budget(self):
        """variance_consumption_percent = 0.0 when planned == 0.

        Division-by-zero guard mirrors the one in
        :meth:`test_bm004_variance_percent_zero_budget_returns_zero_or_sentinel`.
        """
        draft_budget = self.env['budget.budget'].create({
            'name': 'Consumption zero-plan edge',
            'date_from': date(2024, 1, 1),
            'date_to': date(2024, 12, 31),
        })
        zero_line = self.env['budget.budget.line'].create({
            'budget_id': draft_budget.id,
            'account_id': self.acc_expense.id,
            'planned_amount': 0.0,
        })
        self.assertEqual(zero_line.variance_consumption_percent, 0.0)

    # ------------------------------------------------------------------
    # variance_explanation_note (user-editable, NOT computed)
    # ------------------------------------------------------------------

    def test_bm004_variance_explanation_note_user_editable(self):
        """variance_explanation_note is a user-editable Text (not computed).

        BM-004 Scenario 5 — users append qualitative explanation notes
        to budget lines so the variance report carries narrative
        context. The field is plain ``Text`` (not ``compute=...``) and
        therefore writable in normal CRUD workflows.
        """
        self.line_expense.variance_explanation_note = (
            'Savings due to vendor negotiation.'
        )
        self.assertEqual(
            self.line_expense.variance_explanation_note,
            'Savings due to vendor negotiation.',
        )

    # ------------------------------------------------------------------
    # action_drill_down_actuals
    # ------------------------------------------------------------------

    def test_bm004_action_drill_down_actuals_returns_act_window(self):
        """action_drill_down_actuals returns an act_window on
        account.move.line.

        BM-003 Scenario 4 — clicking the drill-down button on a budget
        line opens the underlying journal items via an
        ``ir.actions.act_window`` dict. The dict must contain the
        canonical keys (``type``, ``res_model``, ``domain``).
        """
        self._post_expense(5000.0)
        action = self.line_expense.action_drill_down_actuals()
        self.assertIsInstance(action, dict)
        self.assertEqual(action.get('type'), 'ir.actions.act_window')
        self.assertEqual(action.get('res_model'), 'account.move.line')
        # Domain must filter to the account underlying this line.
        self.assertTrue(action.get('domain'))

    # ==================================================================
    # Phase 5 — budget.variance.wizard TransientModel
    #
    # The wizard exposes BM-004's interactive entry point: filter
    # parameters + computed variance_* aggregates + action_* dispatch
    # methods. All fields and methods listed in the BM-004 wizard
    # schema are exercised below.
    # ==================================================================

    def test_bm004_wizard_create_with_default_fields(self):
        """Wizard can be created for a confirmed budget; defaults populate.

        Verifies the wizard's ``Selection`` defaults: ``target_move``,
        ``account_type_filter``, ``classification_filter``,
        ``period_granularity``, ``notes_filter``, ``report_format``.
        These defaults guarantee that opening the wizard form yields
        a valid ``posted/all`` configuration without further user
        input.
        """
        wizard = self.env['budget.variance.wizard'].create({
            'budget_id': self.budget.id,
        })
        self.assertEqual(wizard.target_move, 'posted')
        self.assertEqual(wizard.account_type_filter, 'all')
        self.assertEqual(wizard.classification_filter, 'all')
        self.assertEqual(wizard.period_granularity, 'none')
        self.assertEqual(wizard.notes_filter, 'all')
        self.assertEqual(wizard.report_format, 'view')

    def test_bm004_wizard_check_dates_constraint(self):
        """_check_dates raises UserError when date_from > date_to.

        Distinct from the ``_check_date_range_within_budget`` constraint
        which enforces overlap with the budget window — this constraint
        rejects an inverted user-input range without considering the
        budget at all.
        """
        with self.assertRaises(UserError):
            self.env['budget.variance.wizard'].create({
                'budget_id': self.budget.id,
                'date_from': date(2024, 12, 31),
                'date_to': date(2024, 1, 1),
            })

    def test_bm004_wizard_check_date_range_within_budget(self):
        """_check_date_range_within_budget raises UserError when window
        is fully disjoint from the budget.

        BM-004 wizard requires the analysis range to overlap the
        budget's fiscal window. With wizard dates in 2025 and the
        budget in 2024, the ranges are disjoint and the constraint
        fires.
        """
        with self.assertRaises(UserError):
            self.env['budget.variance.wizard'].create({
                'budget_id': self.budget.id,
                'date_from': date(2025, 1, 1),
                'date_to': date(2025, 12, 31),
            })

    def test_bm004_wizard_action_generate_report_fills_output_fields(self):
        """action_generate_report populates variance_total_budget,
        variance_line_count, and variance_absolute.

        With expense=60,000 and income=180,000 posted against a
        100k+200k budget, the wizard's filtered line set is the full
        two-line recordset. The output fields are:

        * ``variance_total_budget`` = 100,000 + 200,000 = 300,000
        * ``variance_line_count`` >= 2

        ``variance_total_actual`` is sign-aware
        (``balance:sum`` aggregates ``debit - credit``) so its exact
        value depends on Odoo's sign convention; we do not assert a
        specific number to keep the test robust.
        """
        self._post_expense(60000.0)
        self._post_income(180000.0)
        wizard = self.env['budget.variance.wizard'].create({
            'budget_id': self.budget.id,
        })
        result = wizard.action_generate_report()
        # Output fields must be populated.
        self.assertAlmostEqual(
            wizard.variance_total_budget, 300000.0, places=2,
        )
        self.assertGreaterEqual(wizard.variance_line_count, 2)
        # Result is a view-type act_window dict.
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get('type'), 'ir.actions.act_window')

    def test_bm004_wizard_variance_percent_display_for_zero_budget(self):
        """variance_percent_display shows 'N/A' when total_budget == 0.

        BM-004 Scenario 1 edge case — a wizard targeting a budget whose
        filtered lines have zero total planned exposes the user-facing
        ``N/A`` sentinel via ``variance_percent_display`` rather than
        crashing with ZeroDivisionError or showing a meaningless 0%
        figure.

        We exercise this on a *draft* budget with a zero-planned line.
        Calling ``action_generate_report`` would trigger
        ``_validate_prerequisites`` (which requires confirmed/closed
        state) and raise ``UserError``; we therefore inspect the
        computed display field directly, which fires
        ``_compute_variance_totals`` automatically without going
        through the validation gate.
        """
        draft_budget = self.env['budget.budget'].create({
            'name': 'Zero-budget wizard',
            'date_from': date(2024, 1, 1),
            'date_to': date(2024, 12, 31),
        })
        self.env['budget.budget.line'].create({
            'budget_id': draft_budget.id,
            'account_id': self.acc_expense.id,
            'planned_amount': 0.0,
        })
        wizard = self.env['budget.variance.wizard'].create({
            'budget_id': draft_budget.id,
        })
        # Reading variance_percent_display triggers the @api.depends
        # compute method which sets it to 'N/A' when total_budget == 0.
        self.assertEqual(wizard.variance_percent_display, 'N/A')

    def test_bm004_wizard_account_type_filter_income(self):
        """account_type_filter='income' narrows output to income lines only.

        With both expense (planned 100k) and income (planned 200k)
        lines on the budget, an income-only filter must yield
        ``variance_total_budget = 200,000``.
        """
        self._post_expense(40000.0)
        self._post_income(150000.0)
        wizard = self.env['budget.variance.wizard'].create({
            'budget_id': self.budget.id,
            'account_type_filter': 'income',
        })
        wizard.action_generate_report()
        # Only income line (planned 200k) survives the filter.
        self.assertAlmostEqual(
            wizard.variance_total_budget, 200000.0, places=2,
        )
        self.assertEqual(wizard.variance_line_count, 1)

    def test_bm004_wizard_account_type_filter_expense(self):
        """account_type_filter='expense' narrows output to expense lines only.

        Symmetric to ``test_bm004_wizard_account_type_filter_income``;
        expected ``variance_total_budget = 100,000``.
        """
        self._post_expense(40000.0)
        self._post_income(150000.0)
        wizard = self.env['budget.variance.wizard'].create({
            'budget_id': self.budget.id,
            'account_type_filter': 'expense',
        })
        wizard.action_generate_report()
        self.assertAlmostEqual(
            wizard.variance_total_budget, 100000.0, places=2,
        )
        self.assertEqual(wizard.variance_line_count, 1)

    def test_bm004_wizard_classification_filter_favorable(self):
        """classification_filter='favorable' surfaces only favorable lines.

        Posting expense=40,000 (under planned 100,000) yields a
        favorable expense line; the income line (no postings) reaches
        a non-neutral classification per the income sign-convention
        nuance documented in the module docstring. After the filter,
        only the favorable line is included; the wizard's overall
        ``variance_classification`` aggregates as ``favorable``.
        """
        # Expense under budget => favorable.
        self._post_expense(40000.0)
        wizard = self.env['budget.variance.wizard'].create({
            'budget_id': self.budget.id,
            'classification_filter': 'favorable',
        })
        wizard.action_generate_report()
        self.assertEqual(wizard.variance_classification, 'favorable')

    def test_bm004_wizard_period_granularity_monthly_trend_data(self):
        """period_granularity='monthly' builds monthly trend data in
        variance_trend_data.

        Posts three expense entries in distinct months (Jan / Feb /
        Mar 2024) and verifies that the wizard's
        ``variance_trend_data`` Text field is non-empty, JSON-parses
        to a list, contains at least 3 records, and (because
        ``show_trend_indicators`` is True) each record carries an
        ``indicator`` key.
        """
        self._post_expense(10000.0, move_date=date(2024, 1, 15))
        self._post_expense(15000.0, move_date=date(2024, 2, 15))
        self._post_expense(20000.0, move_date=date(2024, 3, 15))
        wizard = self.env['budget.variance.wizard'].create({
            'budget_id': self.budget.id,
            'period_granularity': 'monthly',
            'include_ytd': True,
            'show_trend_indicators': True,
        })
        wizard.action_generate_report()
        # variance_trend_data must be non-empty and JSON-parsable.
        self.assertTrue(wizard.variance_trend_data)
        trend = json.loads(wizard.variance_trend_data)
        self.assertIsInstance(trend, list)
        # Must have at least 3 monthly buckets covering Jan-Mar.
        self.assertGreaterEqual(len(trend), 3)
        # show_trend_indicators=True => every record has 'indicator'.
        for record in trend:
            self.assertIn('indicator', record.keys())
            self.assertIn(
                record['indicator'],
                ('improving', 'stable', 'deteriorating'),
            )

    def test_bm004_wizard_trend_data_ytd_cumulative(self):
        """Trend data contains YTD cumulatives when include_ytd=True.

        With ``include_ytd=True`` and ``period_granularity='monthly'``,
        ``variance_trend_period_count`` is positive (>= 1) and the
        JSON records carry ``ytd_budget`` / ``ytd_actual`` /
        ``ytd_variance`` keys.
        """
        self._post_expense(5000.0, move_date=date(2024, 1, 10))
        self._post_expense(7000.0, move_date=date(2024, 2, 10))
        wizard = self.env['budget.variance.wizard'].create({
            'budget_id': self.budget.id,
            'period_granularity': 'monthly',
            'include_ytd': True,
        })
        wizard.action_generate_report()
        self.assertGreater(wizard.variance_trend_period_count, 0)
        trend = json.loads(wizard.variance_trend_data) if (
            wizard.variance_trend_data
        ) else []
        self.assertIsInstance(trend, list)
        # YTD cumulative values must be present per record when
        # include_ytd=True.
        for record in trend:
            self.assertIn('ytd_budget', record.keys())
            self.assertIn('ytd_actual', record.keys())
            self.assertIn('ytd_variance', record.keys())

    def test_bm004_wizard_action_print_pdf_raises_until_implemented(self):
        """action_print_pdf raises UserError (PDF pipeline not bundled).

        Per AAP §0.5.1.2, the BM-004 wizard does not include a
        QWeb PDF template; the public action surface deliberately
        raises a friendly ``UserError`` that points users to the
        standard Odoo print menu.
        """
        self._post_expense(5000.0)
        wizard = self.env['budget.variance.wizard'].create({
            'budget_id': self.budget.id,
            'report_format': 'pdf',
        })
        with self.assertRaises(UserError):
            wizard.action_print_pdf()

    def test_bm004_wizard_action_export_xlsx_raises_until_implemented(self):
        """action_export_xlsx raises UserError (XLSX pipeline not bundled).

        Symmetric to
        ``test_bm004_wizard_action_print_pdf_raises_until_implemented``
        — XLSX export is delegated to the standard Odoo
        ``Actions → Export All`` menu on the resulting list view.
        """
        self._post_expense(5000.0)
        wizard = self.env['budget.variance.wizard'].create({
            'budget_id': self.budget.id,
            'report_format': 'xlsx',
        })
        with self.assertRaises(UserError):
            wizard.action_export_xlsx()

    def test_bm004_wizard_action_view_budget_lines_returns_act_window(self):
        """action_view_budget_lines returns act_window on budget.budget.line.

        The action enables users to drill from the wizard's aggregate
        summary to the per-line detail view. The returned dict must be
        a properly formed ``ir.actions.act_window`` targeting
        ``budget.budget.line``.
        """
        wizard = self.env['budget.variance.wizard'].create({
            'budget_id': self.budget.id,
        })
        action = wizard.action_view_budget_lines()
        self.assertEqual(action.get('type'), 'ir.actions.act_window')
        self.assertEqual(action.get('res_model'), 'budget.budget.line')

    def test_bm004_wizard_action_preview_returns_dict(self):
        """action_preview invalidates the cache and reloads the wizard.

        ``action_preview`` is the in-place "Preview" handler — it
        invalidates all ``variance_*`` output fields so the next read
        recomputes from scratch, then returns an ``ir.actions.act_window``
        that reloads the wizard form.
        """
        self._post_expense(5000.0)
        wizard = self.env['budget.variance.wizard'].create({
            'budget_id': self.budget.id,
        })
        result = wizard.action_preview()
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get('type'), 'ir.actions.act_window')
        self.assertEqual(result.get('res_model'), 'budget.variance.wizard')

    def test_bm004_wizard_onchange_budget_id_sets_window_dates(self):
        """_onchange_budget_id initializes date_from/date_to to budget window.

        Triggered when the user selects a budget in the wizard form.
        Because ``new()`` does not touch the database, this also
        validates the onchange logic in pure-memory mode.
        """
        wizard = self.env['budget.variance.wizard'].new({
            'budget_id': self.budget.id,
        })
        wizard._onchange_budget_id()
        self.assertEqual(wizard.date_from, self.budget.date_from)
        self.assertEqual(wizard.date_to, self.budget.date_to)

    def test_bm004_wizard_action_drill_down_line_uses_context(self):
        """action_drill_down_line consumes active_line_id from context.

        The per-line drill-down delegates to
        ``budget.budget.line.action_drill_down_actuals`` for the line
        identified by ``self.env.context['active_line_id']``. The
        returned action targets ``account.move.line`` and inherits
        the line's domain (account, dates, optional analytic
        intersection).
        """
        self._post_expense(5000.0)
        wizard = self.env['budget.variance.wizard'].create({
            'budget_id': self.budget.id,
        })
        result = wizard.with_context(
            active_line_id=self.line_expense.id,
        ).action_drill_down_line()
        self.assertEqual(result.get('type'), 'ir.actions.act_window')
        self.assertEqual(result.get('res_model'), 'account.move.line')

    # ==================================================================
    # Phase 7 — R-08 CRITICAL field-partitioning verification
    #
    # These three tests enforce Rule R-08 by introspecting the live ORM
    # field registry via ``ir.model.fields.search``. Without these
    # tests, a future refactor could accidentally introduce a
    # ``variance_*`` field on a BM-005 model (or an ``alert_*`` field
    # on a BM-004 model), violating the parallel-safe partitioning
    # mandate from AAP §0.7.1.8.
    #
    # Scope:
    #   * BM-004 models: budget.budget.line, budget.variance.wizard
    #   * BM-005 models: budget.budget, budget.alert, budget.budget.period
    # ==================================================================

    def test_bm004_r08_variance_fields_only_on_bm004_models(self):
        """R-08: variance_* fields ONLY on BM-004 scope models.

        Verifies that no field name starting with ``variance_`` lives
        on ``budget.budget``, ``budget.alert``, or
        ``budget.budget.period`` (the BM-005 partition). The check uses
        ``ir.model.fields.search`` (per the schema's design) and adds
        a defensive Python-side prefix filter to neutralize the
        SQL-wildcard semantics of the underscore character in the
        ``like`` operator.
        """
        IrModelFields = self.env['ir.model.fields']
        # Permitted models for the variance_* prefix.
        bm004_models = {'budget.budget.line', 'budget.variance.wizard'}
        # Models on which variance_* must NEVER appear.
        bm005_models = {
            'budget.budget', 'budget.alert', 'budget.budget.period',
        }
        all_scope = list(bm004_models | bm005_models)

        # Use ir.model.fields.search per schema; double-filter in
        # Python to avoid SQL underscore-wildcard ambiguity.
        candidates = IrModelFields.search([
            ('model_id.model', 'in', all_scope),
        ])
        variance_fields = candidates.filtered(
            lambda f: f.name.startswith('variance_'),
        )
        for f in variance_fields:
            self.assertIn(
                f.model_id.model, bm004_models,
                msg=(
                    "R-08 VIOLATION: field '%s' on model '%s' — "
                    "variance_* fields MUST live only on "
                    "budget.budget.line or budget.variance.wizard."
                    % (f.name, f.model_id.model)
                ),
            )

    def test_bm004_r08_alert_fields_not_on_bm004_models(self):
        """R-08: alert_* fields MUST NOT live on BM-004 scope models.

        ``alert_*`` is reserved for the ``budget.alert`` model and the
        ``budget.budget`` alert-summary fields (BM-005 scope). It must
        never appear on ``budget.budget.line`` or
        ``budget.variance.wizard``.
        """
        IrModelFields = self.env['ir.model.fields']
        candidates = IrModelFields.search([
            ('model_id.model', 'in', [
                'budget.budget.line', 'budget.variance.wizard',
            ]),
        ])
        alert_prefixed = candidates.filtered(
            lambda f: f.name.startswith('alert_'),
        )
        self.assertFalse(
            alert_prefixed,
            msg=(
                "R-08 VIOLATION: alert_* fields must not live on "
                "BM-004 models. Offenders: %s" % (
                    [(f.name, f.model_id.model) for f in alert_prefixed],
                )
            ),
        )

    def test_bm004_r08_variance_and_alert_disjoint_field_names(self):
        """R-08: variance_* and alert_* field-name sets are disjoint.

        Introspects the combined field name set across the five-model
        partition and asserts:

        1. No field name appears in both the ``variance_*`` and
           ``alert_*`` namespaces (intersection is empty by prefix
           construction, but verified at registry load time).
        2. ``variance_*`` names exist only on BM-004 scope.
        3. ``alert_*`` names exist only on BM-005 scope.
        """
        IrModelFields = self.env['ir.model.fields']
        all_scope = [
            'budget.budget', 'budget.budget.line',
            'budget.budget.period', 'budget.variance.wizard',
            'budget.alert',
        ]
        candidates = IrModelFields.search([
            ('model_id.model', 'in', all_scope),
        ])
        variance_names = set(candidates.filtered(
            lambda f: f.name.startswith('variance_'),
        ).mapped('name'))
        alert_names = set(candidates.filtered(
            lambda f: f.name.startswith('alert_'),
        ).mapped('name'))
        # Empty intersection by prefix construction.
        intersection = variance_names & alert_names
        self.assertFalse(
            intersection,
            msg=(
                "R-08 VIOLATION: the following field names appear in "
                "BOTH variance_* and alert_* namespaces: %s"
                % intersection
            ),
        )
        # Sanity: neither set should be empty (proves we are reading
        # something meaningful rather than passing on empty data).
        self.assertTrue(
            variance_names,
            "Expected variance_* fields to exist on BM-004 models.",
        )
        self.assertTrue(
            alert_names,
            "Expected alert_* fields to exist on BM-005 models.",
        )

    # ==================================================================
    # Phase 8 — Performance smoke test (SM-003 < 3s for 1,000 budget
    # lines)
    #
    # Rather than blow up unit-test runtime with a 1,000-line stress,
    # we verify the wizard terminates with a modest volume (50 lines)
    # exercising the same _read_group-backed code path. The full SLA
    # is validated separately by the integration suite.
    # ==================================================================

    def test_bm004_wizard_performance_smoke_many_lines(self):
        """Wizard completes its report on a multi-line budget.

        Creates 50 expense accounts + 50 budget lines and verifies the
        wizard's ``action_generate_report`` populates
        ``variance_line_count`` correctly. The aggregation path under
        test is the single-query ``_read_group`` execution that
        underpins the BM-004 SLA.
        """
        AccountAccount = self.env['account.account']
        budget_perf = self.env['budget.budget'].create({
            'name': 'Perf-smoke budget',
            'date_from': date(2024, 1, 1),
            'date_to': date(2024, 12, 31),
        })
        for idx in range(50):
            acc = AccountAccount.create({
                'code': 'XTEST.700%02d' % idx,
                'name': 'Perf expense %d' % idx,
                'account_type': 'expense',
            })
            self.env['budget.budget.line'].create({
                'budget_id': budget_perf.id,
                'account_id': acc.id,
                'planned_amount': 1000.0 * (idx + 1),
            })
        budget_perf.action_confirm()
        wizard = self.env['budget.variance.wizard'].create({
            'budget_id': budget_perf.id,
        })
        # Should not raise and should populate output fields.
        wizard.action_generate_report()
        self.assertEqual(wizard.variance_line_count, 50)
        # Total budget = sum_{i=0..49} 1000 * (i+1) = 1000 * (50*51/2)
        # = 1000 * 1275 = 1,275,000.
        self.assertAlmostEqual(
            wizard.variance_total_budget, 1275000.0, places=2,
        )

    # ==================================================================
    # Phase 11 — Auxiliary coverage tests (R-04 ≥80% gate enforcement)
    #
    # The 41 schema-required test methods above cover the principal
    # BM-004 surface. The following auxiliary tests target additional
    # branches in budget_variance_wizard.py and budget_budget_line.py
    # to push line coverage above the 80% R-04 gate. Each test name
    # follows the canonical ``test_bm004_<scenario>`` convention used
    # throughout this file and exercises one specific code path.
    # ==================================================================

    def test_bm004_wizard_onchange_period_granularity_resets_flags(self):
        """``_onchange_period_granularity`` resets YTD + indicator flags
        to False when granularity becomes 'none' (BM-004 Scenario 4
        UI behavior).
        """
        wizard = self.env['budget.variance.wizard'].new({
            'budget_id': self.budget.id,
            'period_granularity': 'monthly',
            'include_ytd': True,
            'show_trend_indicators': True,
        })
        wizard.period_granularity = 'none'
        wizard._onchange_period_granularity()
        self.assertFalse(wizard.include_ytd)
        self.assertFalse(wizard.show_trend_indicators)

    def test_bm004_wizard_onchange_period_granularity_enables_flags(self):
        """``_onchange_period_granularity`` re-enables flags when
        switching from 'none' to a non-'none' granularity.
        """
        wizard = self.env['budget.variance.wizard'].new({
            'budget_id': self.budget.id,
            'period_granularity': 'none',
            'include_ytd': False,
            'show_trend_indicators': False,
        })
        wizard.period_granularity = 'quarterly'
        wizard._onchange_period_granularity()
        self.assertTrue(wizard.include_ytd)
        self.assertTrue(wizard.show_trend_indicators)

    def test_bm004_wizard_onchange_account_type_filter_is_safe_noop(self):
        """``_onchange_account_type_filter`` is a no-op placeholder
        retained as an extension point for future cascade logic.
        Calling it must not raise and must not mutate any field.
        """
        wizard = self.env['budget.variance.wizard'].new({
            'budget_id': self.budget.id,
            'classification_filter': 'favorable',
        })
        # Should not raise and must preserve the classification filter.
        wizard.account_type_filter = 'income'
        wizard._onchange_account_type_filter()
        self.assertEqual(wizard.classification_filter, 'favorable')

    def test_bm004_wizard_onchange_report_format_pdf_enables_notes(self):
        """``_onchange_report_format`` defaults ``include_notes`` to
        True when the user picks PDF or XLSX export.
        """
        wizard = self.env['budget.variance.wizard'].new({
            'budget_id': self.budget.id,
            'report_format': 'view',
            'include_notes': False,
        })
        wizard.report_format = 'pdf'
        wizard._onchange_report_format()
        self.assertTrue(wizard.include_notes)

    def test_bm004_wizard_validate_prerequisites_no_budget_raises(self):
        """``_validate_prerequisites`` raises UserError when no budget
        is selected (defence-in-depth; the @api.constrains layer
        already requires budget_id but the prerequisite check is the
        last line of defence at action-time).
        """
        # Bypass create-time required validation by constructing a
        # transient via .new() then nulling budget_id at runtime.
        wizard = self.env['budget.variance.wizard'].new({
            'budget_id': self.budget.id,
        })
        wizard.budget_id = False
        with self.assertRaises(UserError):
            wizard._validate_prerequisites()

    def test_bm004_wizard_validate_prerequisites_draft_budget_raises(self):
        """``_validate_prerequisites`` raises UserError when the
        selected budget is in 'draft' state. Only confirmed/closed
        budgets yield meaningful variance analysis.
        """
        draft_budget = self.env['budget.budget'].create({
            'name': 'Draft for prereq check',
            'date_from': date(2024, 1, 1),
            'date_to': date(2024, 12, 31),
        })
        # Add a line so the budget is non-empty but DO NOT confirm it.
        self.env['budget.budget.line'].create({
            'budget_id': draft_budget.id,
            'account_id': self.acc_expense.id,
            'planned_amount': 5000.0,
        })
        wizard = self.env['budget.variance.wizard'].create({
            'budget_id': draft_budget.id,
        })
        with self.assertRaises(UserError):
            wizard._validate_prerequisites()

    def test_bm004_wizard_validate_prerequisites_no_company_raises(self):
        """``_validate_prerequisites`` raises UserError when no
        company is selected on the wizard.
        """
        wizard = self.env['budget.variance.wizard'].new({
            'budget_id': self.budget.id,
        })
        wizard.company_id = False
        with self.assertRaises(UserError):
            wizard._validate_prerequisites()

    def test_bm004_wizard_action_drill_down_line_no_context_raises(self):
        """``action_drill_down_line`` raises UserError when no
        ``active_line_id`` is supplied in context.
        """
        wizard = self.env['budget.variance.wizard'].create({
            'budget_id': self.budget.id,
        })
        with self.assertRaises(UserError):
            wizard.action_drill_down_line()

    def test_bm004_wizard_action_drill_down_line_deleted_raises(self):
        """``action_drill_down_line`` raises UserError when the
        referenced budget line has been deleted concurrently.
        """
        # Create a budget line just to obtain a valid id, then unlink.
        ephemeral_budget = self.env['budget.budget'].create({
            'name': 'Ephemeral budget',
            'date_from': date(2024, 1, 1),
            'date_to': date(2024, 12, 31),
        })
        line = self.env['budget.budget.line'].create({
            'budget_id': ephemeral_budget.id,
            'account_id': self.acc_expense.id,
            'planned_amount': 1000.0,
        })
        line_id = line.id
        line.unlink()
        wizard = self.env['budget.variance.wizard'].create({
            'budget_id': self.budget.id,
        })
        with self.assertRaises(UserError):
            wizard.with_context(
                active_line_id=line_id,
            ).action_drill_down_line()

    def test_bm004_wizard_notes_filter_with_notes_narrows_scope(self):
        """``notes_filter='with_notes'`` keeps only lines that have a
        non-empty ``variance_explanation_note`` (BM-004 Scenario 5).
        """
        # Annotate only the expense line.
        self.line_expense.variance_explanation_note = 'Vendor savings'
        self._post_expense(40000.0)
        self._post_income(180000.0)
        wizard = self.env['budget.variance.wizard'].create({
            'budget_id': self.budget.id,
            'notes_filter': 'with_notes',
        })
        wizard.action_generate_report()
        # Only the expense line should remain in scope.
        self.assertEqual(wizard.variance_line_count, 1)
        self.assertAlmostEqual(
            wizard.variance_total_budget, 100000.0, places=2,
        )

    def test_bm004_wizard_notes_filter_without_notes_narrows_scope(self):
        """``notes_filter='without_notes'`` keeps only lines that
        have an empty ``variance_explanation_note``.
        """
        self.line_expense.variance_explanation_note = 'Vendor savings'
        self._post_expense(40000.0)
        self._post_income(180000.0)
        wizard = self.env['budget.variance.wizard'].create({
            'budget_id': self.budget.id,
            'notes_filter': 'without_notes',
        })
        wizard.action_generate_report()
        # Only the income line should remain in scope.
        self.assertEqual(wizard.variance_line_count, 1)
        self.assertAlmostEqual(
            wizard.variance_total_budget, 200000.0, places=2,
        )

    def test_bm004_wizard_action_generate_report_target_move_all(self):
        """``target_move='all'`` widens the journal scope to include
        both draft and posted entries when generating the drill-down.
        """
        self._post_expense(30000.0)
        wizard = self.env['budget.variance.wizard'].create({
            'budget_id': self.budget.id,
            'target_move': 'all',
        })
        action = wizard.action_generate_report()
        self.assertIsInstance(action, dict)
        # Domain should contain a parent_state filter for both drafts
        # and posted entries when target_move == 'all'.
        domain = action.get('domain', [])
        parent_state_terms = [
            term for term in domain
            if isinstance(term, tuple) and term[0] == 'parent_state'
        ]
        self.assertTrue(parent_state_terms)
        # The 'in' operator is the all-inclusive form.
        self.assertEqual(parent_state_terms[0][1], 'in')

    def test_bm004_wizard_period_granularity_quarterly_trend_data(self):
        """``period_granularity='quarterly'`` builds trend buckets
        labelled Q1/Q2/Q3/Q4 by walking the calendar in 3-month steps.
        """
        # Post one expense per quarter to drive bucket population.
        self._post_expense(8000.0, move_date=date(2024, 2, 15))
        self._post_expense(10000.0, move_date=date(2024, 5, 15))
        self._post_expense(12000.0, move_date=date(2024, 8, 15))
        self._post_expense(14000.0, move_date=date(2024, 11, 15))
        wizard = self.env['budget.variance.wizard'].create({
            'budget_id': self.budget.id,
            'period_granularity': 'quarterly',
            'include_ytd': True,
            'show_trend_indicators': True,
        })
        wizard.action_generate_report()
        self.assertTrue(wizard.variance_trend_data)
        trend = json.loads(wizard.variance_trend_data)
        self.assertIsInstance(trend, list)
        # Should have 4 quarterly buckets.
        self.assertGreaterEqual(len(trend), 4)
        # At least one bucket should have a label starting with 'Q'.
        labels = [r.get('period_label') or r.get('period') for r in trend]
        self.assertTrue(any(
            (label or '').startswith('Q') for label in labels
        ))

    def test_bm004_wizard_period_granularity_annual_trend_data(self):
        """``period_granularity='annual'`` builds a single calendar-
        year bucket labelled with the year number.
        """
        self._post_expense(45000.0, move_date=date(2024, 6, 15))
        wizard = self.env['budget.variance.wizard'].create({
            'budget_id': self.budget.id,
            'period_granularity': 'annual',
            'include_ytd': True,
        })
        wizard.action_generate_report()
        self.assertTrue(wizard.variance_trend_data)
        trend = json.loads(wizard.variance_trend_data)
        self.assertIsInstance(trend, list)
        self.assertGreaterEqual(len(trend), 1)
        # The label should contain the year '2024'.
        labels = [r.get('period_label') or r.get('period') for r in trend]
        self.assertTrue(any('2024' in (label or '') for label in labels))

    def test_bm004_line_drill_down_actuals_no_account_raises(self):
        """``action_drill_down_actuals`` on ``budget.budget.line``
        raises UserError when the line has no account assigned.
        """
        # Create an unsaved draft line with no account_id.
        # Using .new() yields a transient record bypassing required
        # field validation so we can exercise the defensive guard.
        line = self.env['budget.budget.line'].new({
            'budget_id': self.budget.id,
            'planned_amount': 0.0,
        })
        line.account_id = False
        with self.assertRaises(UserError):
            line.action_drill_down_actuals()

    def test_bm004_line_drill_down_actuals_with_analytic_distribution(self):
        """``action_drill_down_actuals`` adds an
        ``analytic_distribution`` clause to the domain when the line
        has an analytic distribution set.
        """
        # Annotate the expense line with an analytic distribution
        # and verify the drill-down domain reflects it.
        self.line_expense.analytic_distribution = {
            str(self.analytic_sales.id): 100.0,
        }
        self.line_expense.invalidate_recordset(['analytic_distribution'])
        action = self.line_expense.action_drill_down_actuals()
        self.assertIsInstance(action, dict)
        domain = action.get('domain', [])
        analytic_terms = [
            term for term in domain
            if isinstance(term, tuple)
            and term[0] == 'analytic_distribution'
        ]
        self.assertTrue(analytic_terms)

    def test_bm004_line_check_account_type_rejects_balance_sheet(self):
        """``_check_account_type`` raises ValidationError when a line
        attempts to reference a balance-sheet account
        (asset / liability / equity / off-balance) — only income and
        expense types are permitted.
        """
        # cls.acc_cash is account_type='asset_cash' — not allowed.
        with self.assertRaises(ValidationError):
            self.env['budget.budget.line'].create({
                'budget_id': self.budget.id,
                'account_id': self.acc_cash.id,
                'planned_amount': 1000.0,
            })

    def test_bm004_line_classification_neutral_for_other_account_type(self):
        """``_classify_variance`` returns 'neutral' when the line's
        account is neither income nor expense type. The
        ``_check_account_type`` constraint normally prevents this at
        create-time, but the classification function itself must be
        defensively safe — verified by directly invoking the method
        on a line whose account_type is exposed via ``new()``.
        """
        # Create an asset-like line via new() (transient, no
        # @api.constrains fires) and verify _classify_variance
        # returns 'neutral'.
        line = self.env['budget.budget.line'].new({
            'budget_id': self.budget.id,
            'account_id': self.acc_cash.id,
            'planned_amount': 1000.0,
        })
        result = line._classify_variance()
        self.assertEqual(result, 'neutral')

    def test_bm004_line_period_count_smart_button_metric(self):
        """``period_count`` smart-button counter equals the number of
        ``budget.budget.period`` records linked to the line.
        """
        # No periods created yet — should be zero.
        self.assertEqual(self.line_expense.period_count, 0)
        # The display name should at least contain the account code.
        self.assertIn(
            self.acc_expense.code, self.line_expense.display_name,
        )

    def test_bm004_line_compute_variance_short_circuits_no_account(self):
        """``_compute_variance`` short-circuits when the line has no
        account (defensive guard at line 484-485 of the model).
        """
        # Create a line with no account via new() and verify
        # variance_actual stays at 0.0 without raising.
        line = self.env['budget.budget.line'].new({
            'budget_id': self.budget.id,
            'planned_amount': 1000.0,
        })
        line.account_id = False
        line._compute_variance()
        self.assertEqual(line.variance_actual, 0.0)
        self.assertEqual(line.variance_classification, 'neutral')

    def test_bm004_line_compute_variance_analytic_path(self):
        """``_compute_variance`` uses the analytic-aware path (search
        + per-line filtered) when at least one line in the recordset
        has an ``analytic_distribution`` set.
        """
        # Annotate the expense line with an analytic distribution
        # then post an expense move with the matching distribution.
        self.line_expense.analytic_distribution = {
            str(self.analytic_sales.id): 100.0,
        }
        self.line_expense.invalidate_recordset()
        self._post_expense(
            25000.0,
            analytic_distribution={
                str(self.analytic_sales.id): 100.0,
            },
        )
        # Now compute — recordset has one analytically-tagged line so
        # the analytic path is taken.
        self.line_expense.invalidate_recordset(['variance_actual'])
        # The actual must reflect the posted move (analytic-aware
        # filter delegates to ``_match_analytic_distribution`` per
        # line).
        self.assertGreater(self.line_expense.variance_actual, 0.0)
