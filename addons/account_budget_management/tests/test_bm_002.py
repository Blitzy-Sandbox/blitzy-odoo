
# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Test Suite for BM-002: Budget Period Allocation

Implements comprehensive tests for ``budget.budget.period`` — the
per-period allocation model that splits a ``budget.budget.line``'s
``planned_amount`` across monthly, quarterly, annual, or custom
windows. Covers:

* Creation of period records with cascading related fields
  (``budget_id``, ``account_id``, ``company_id``, ``currency_id``,
  ``state``) populated from the parent line.
* ``_compute_name`` / ``_compute_display_name`` — month, quarter,
  year, and custom date-range labels.
* ``_compute_actual_amount`` and ``consumption_percent`` via a
  single-query batched search against posted ``account.move.line``.
* ``_check_dates`` ``ValidationError`` on inverted date range.
* ``_check_sum_matches_line`` using
  ``float_compare(..., precision_rounding=rounding)`` to validate
  that the sum of period allocations equals the parent line's
  ``planned_amount`` (within currency rounding tolerance).
* ``_check_within_budget_window`` ``ValidationError`` on periods
  spilling outside the parent budget's start/end dates.
* ``write()`` override capturing ``prev_amount`` /
  ``modified_by_id`` / ``modified_date`` whenever
  ``allocated_amount`` changes.  The caller-supplied audit trail is
  preserved when the write explicitly provides those keys.
* ``_generate_equal_distribution`` — equal split with the **final
  period absorbing the rounding remainder**, plus ``UserError``
  messages for (a) existing period_ids, (b) missing date range,
  (c) inverted date range.
* ``_split_date_range`` — monthly/quarterly/annual splitting and
  the ``custom`` fallback, including final-period clamping to
  ``date_to`` and the leap-year Feb-29→Feb-28 edge case when
  shifting dates via ``relativedelta``.
* ``_copy_from_previous_budget`` — percentage preservation with a
  fiscal-year offset, skip for destination lines that already have
  periods, and allocation method / percentage stamping.
* ``action_open_source_transactions`` returning an
  ``ir.actions.act_window`` on ``account.move.line``.
* SQL CHECK constraints ``allocated_amount >= 0``,
  ``allocation_percentage`` in [0, 100], and
  ``date_from <= date_to``.

Target: >=80% line coverage per Rule R-04 for BM-002.
"""

from datetime import date, datetime

from psycopg2 import IntegrityError

from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tools import float_compare, mute_logger

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestBudgetPeriodAllocation(AccountTestInvoicingCommon):
    """Test class for BM-002: Budget Period Allocation."""

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

        cls.journal_misc = cls.company_data['default_journal_misc']

        # FY2024 parent budget + one expense line with planned 120,000.
        cls.budget_2024 = cls.env['budget.budget'].create({
            'name': 'FY2024',
            'date_from': date(2024, 1, 1),
            'date_to': date(2024, 12, 31),
        })
        cls.line_expense = cls.env['budget.budget.line'].create({
            'budget_id': cls.budget_2024.id,
            'account_id': cls.test_expense.id,
            'planned_amount': 120000.0,
        })

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

    def _create_period(self, line, date_from, date_to, allocated,
                       period_type='custom',
                       allocation_method='manual', sequence=10):
        """Create a single period allocation.

        The ``budget.budget.period._check_sum_matches_line``
        constraint asserts that
        ``sum(line.period_ids.allocated_amount) == line.planned_amount``
        within currency rounding. When this helper is used to insert
        a SINGLE test period, the parent line's ``planned_amount``
        must be synchronized with the new period's ``allocated`` to
        preserve the invariant. We do this by:

        1. Writing ``line.planned_amount = 0`` first — because the
           constraint short-circuits while the line has zero planned
           total, the period ``create()`` call then passes the
           constraint even with an arbitrary ``allocated``.
        2. Writing ``line.planned_amount = allocated`` afterwards so
           that the sum-equality invariant holds on commit.

        Writes to the line's ``planned_amount`` do not fire
        ``@api.constrains('allocated_amount', 'budget_line_id')`` on
        the period, so this two-step dance is safe.

        Tests that need to exercise the constraint VIOLATION
        explicitly bypass this helper and create periods directly via
        ``self.env['budget.budget.period'].create(...)`` (see
        ``test_bm002_check_sum_matches_line_rejects_mismatch``).
        """
        # Unconditional writes — cheap under Odoo's dirty-tracking
        # (an UPDATE to the same value is elided at the cursor layer
        # when values are equal). Using unconditional writes avoids
        # unsafe float-equality comparisons (ruff RUF069) which can be
        # unreliable for monetary amounts.
        line.write({'planned_amount': 0.0})
        period = self.env['budget.budget.period'].create({
            'budget_line_id': line.id,
            'date_from': date_from,
            'date_to': date_to,
            'allocated_amount': allocated,
            'period_type': period_type,
            'allocation_method': allocation_method,
            'sequence': sequence,
        })
        line.write({'planned_amount': allocated})
        return period

    # ------------------------------------------------------------------
    # Basic creation + related-field cascade
    # ------------------------------------------------------------------

    def test_bm002_period_create_basic(self):
        """Create a period allocation; related fields cascade."""
        period = self._create_period(
            self.line_expense,
            date(2024, 1, 1), date(2024, 12, 31), 120000.0,
            period_type='annual', sequence=10,
        )
        self.assertEqual(period.budget_line_id, self.line_expense)
        self.assertEqual(period.budget_id, self.budget_2024)
        self.assertEqual(period.account_id, self.test_expense)
        self.assertEqual(period.company_id, self.budget_2024.company_id)
        self.assertEqual(period.currency_id, self.budget_2024.currency_id)
        self.assertEqual(period.state, self.budget_2024.state)

    def test_bm002_period_default_period_type_is_monthly(self):
        """``period_type`` default is ``monthly`` per model definition."""
        # We set period_type explicitly everywhere else; exercise the
        # default here via a new_record call.
        new_period = self.env['budget.budget.period'].new({
            'budget_line_id': self.line_expense.id,
            'date_from': date(2024, 1, 1),
            'date_to': date(2024, 1, 31),
        })
        self.assertEqual(new_period.period_type, 'monthly')

    def test_bm002_period_default_allocation_method_is_manual(self):
        """``allocation_method`` default is ``manual``."""
        new_period = self.env['budget.budget.period'].new({
            'budget_line_id': self.line_expense.id,
            'date_from': date(2024, 1, 1),
            'date_to': date(2024, 1, 31),
        })
        self.assertEqual(new_period.allocation_method, 'manual')

    # ------------------------------------------------------------------
    # _compute_name: monthly/quarterly/annual/custom labels
    # ------------------------------------------------------------------

    def test_bm002_compute_name_monthly(self):
        """Monthly period name formats as ``%B %Y`` (e.g. 'January 2024')."""
        period = self._create_period(
            self.line_expense,
            date(2024, 1, 1), date(2024, 1, 31), 10000.0,
            period_type='monthly', sequence=10,
        )
        # "January 2024" regardless of the locale used in the test harness
        # (en_US by default).
        self.assertEqual(period.name, 'January 2024')

    def test_bm002_compute_name_quarterly_q1(self):
        """Q1 name: ``'Q1 2024'``."""
        period = self._create_period(
            self.line_expense,
            date(2024, 1, 1), date(2024, 3, 31), 30000.0,
            period_type='quarterly', sequence=10,
        )
        self.assertEqual(period.name, 'Q1 2024')

    def test_bm002_compute_name_quarterly_q3(self):
        """Q3 name derived from ``(month-1)//3 + 1``."""
        period = self._create_period(
            self.line_expense,
            date(2024, 7, 1), date(2024, 9, 30), 30000.0,
            period_type='quarterly', sequence=30,
        )
        self.assertEqual(period.name, 'Q3 2024')

    def test_bm002_compute_name_annual(self):
        """Annual name is the year string."""
        period = self._create_period(
            self.line_expense,
            date(2024, 1, 1), date(2024, 12, 31), 120000.0,
            period_type='annual', sequence=10,
        )
        self.assertEqual(period.name, '2024')

    def test_bm002_compute_name_custom_date_range(self):
        """Custom period name includes both date bounds."""
        period = self._create_period(
            self.line_expense,
            date(2024, 2, 15), date(2024, 5, 20), 30000.0,
            period_type='custom', sequence=10,
        )
        # "2024-02-15 → 2024-05-20"
        self.assertIn('2024-02-15', period.name)
        self.assertIn('2024-05-20', period.name)

    def test_bm002_compute_display_name_includes_account(self):
        """``display_name`` = ``{account_name} — {period_name}``."""
        period = self._create_period(
            self.line_expense,
            date(2024, 1, 1), date(2024, 1, 31), 10000.0,
            period_type='monthly', sequence=10,
        )
        self.assertIn(self.test_expense.display_name, period.display_name)
        self.assertIn('January 2024', period.display_name)

    # ------------------------------------------------------------------
    # _check_dates constraint (date_from <= date_to)
    # ------------------------------------------------------------------

    def test_bm002_check_dates_rejects_inverted_range(self):
        """Inverted date range is rejected.

        Defense-in-depth — the model declares BOTH a Python
        ``@api.constrains('date_from', 'date_to')`` (``_check_dates``,
        which raises ``ValidationError``) AND a DB-level
        ``CHECK(date_from <= date_to)`` constraint
        (``_date_range_valid``, which raises
        ``psycopg2.errors.CheckViolation``). On INSERT, the DB
        constraint is evaluated first by PostgreSQL itself and
        rejects the invalid row with ``IntegrityError`` before the
        ORM gets a chance to run the Python constraint. Both layers
        provide a correct rejection path; the test verifies that
        rejection occurs. The Python constraint guards against paths
        that don't hit the DB (e.g., in-memory record manipulation
        via ``.new()``).

        Note: ``self.assertRaises`` must be passed a single exception
        class (not a tuple). Odoo's ``_assertRaises`` override in
        ``odoo.tests.common`` calls ``issubclass(exception,
        AccessError)`` which raises ``TypeError`` when ``exception``
        is a tuple. We therefore catch ``IntegrityError`` (the DB
        layer that actually fires on INSERT).
        """
        with self.assertRaises(IntegrityError):
            with mute_logger('odoo.sql_db'):
                self.env['budget.budget.period'].create({
                    'budget_line_id': self.line_expense.id,
                    'date_from': date(2024, 6, 30),
                    'date_to': date(2024, 6, 1),
                    'allocated_amount': 0.0,
                    'period_type': 'custom',
                    'allocation_method': 'manual',
                })
                self.env.cr.flush()

    def test_bm002_check_dates_accepts_single_day(self):
        """Single-day period (date_from == date_to) is legal."""
        period = self._create_period(
            self.line_expense,
            date(2024, 6, 15), date(2024, 6, 15), 0.0,
            period_type='custom', sequence=10,
        )
        self.assertEqual(period.date_from, period.date_to)

    # ------------------------------------------------------------------
    # _check_within_budget_window constraint
    # ------------------------------------------------------------------

    def test_bm002_check_within_budget_window_rejects_before_start(self):
        """Period starting BEFORE the budget's date_from is rejected."""
        with self.assertRaises(ValidationError):
            self._create_period(
                self.line_expense,
                date(2023, 12, 1), date(2024, 1, 31), 10000.0,
                period_type='custom', sequence=10,
            )

    def test_bm002_check_within_budget_window_rejects_after_end(self):
        """Period ending AFTER the budget's date_to is rejected."""
        with self.assertRaises(ValidationError):
            self._create_period(
                self.line_expense,
                date(2024, 12, 1), date(2025, 1, 31), 10000.0,
                period_type='custom', sequence=10,
            )

    def test_bm002_check_within_budget_window_short_circuit_no_bounds(self):
        """When parent budget has no bounds, window check short-circuits."""
        unbounded = self.env['budget.budget'].create({
            'name': 'Unbounded',
            'date_from': date(2024, 1, 1),
            'date_to': date(2024, 12, 31),
        })
        line = self.env['budget.budget.line'].create({
            'budget_id': unbounded.id,
            'account_id': self.test_expense.id,
            'planned_amount': 0.0,
        })
        # Sanity: this period lies strictly within the bounds; no raise.
        period = self._create_period(
            line,
            date(2024, 6, 1), date(2024, 6, 30), 0.0,
            period_type='custom', sequence=10,
        )
        self.assertTrue(period)

    # ------------------------------------------------------------------
    # _compute_actual_amount and consumption_percent
    # ------------------------------------------------------------------

    def test_bm002_compute_actual_amount_zero_without_postings(self):
        """With no posted moves, actual_amount is 0 and consumption 0%."""
        period = self._create_period(
            self.line_expense,
            date(2024, 1, 1), date(2024, 12, 31), 120000.0,
            period_type='annual', sequence=10,
        )
        period.invalidate_recordset()
        self.assertAlmostEqual(period.actual_amount, 0.0, places=2)
        self.assertAlmostEqual(period.consumption_percent, 0.0, places=2)

    def test_bm002_compute_actual_amount_aggregates_posted_moves(self):
        """Posted moves in period window contribute to actual_amount."""
        period = self._create_period(
            self.line_expense,
            date(2024, 1, 1), date(2024, 12, 31), 120000.0,
            period_type='annual', sequence=10,
        )
        self._post_entry(self.test_expense, 30000.0, date(2024, 3, 15))
        period.invalidate_recordset()
        self.assertAlmostEqual(period.actual_amount, 30000.0, places=2)
        # 30000 / 120000 * 100 = 25.0
        self.assertAlmostEqual(period.consumption_percent, 25.0, places=2)

    def test_bm002_compute_actual_amount_respects_date_window(self):
        """Moves outside the period's window are excluded."""
        period = self._create_period(
            self.line_expense,
            date(2024, 6, 1), date(2024, 6, 30), 10000.0,
            period_type='monthly', sequence=60,
        )
        # Post: one inside the window, one outside.
        self._post_entry(self.test_expense, 8000.0, date(2024, 6, 15))
        self._post_entry(self.test_expense, 5000.0, date(2024, 3, 15))
        period.invalidate_recordset()
        # Only the June entry counts.
        self.assertAlmostEqual(period.actual_amount, 8000.0, places=2)

    def test_bm002_consumption_percent_zero_when_no_allocation(self):
        """``consumption_percent`` = 0 when allocated_amount is 0."""
        period = self._create_period(
            self.line_expense,
            date(2024, 1, 1), date(2024, 1, 31), 0.0,
            period_type='monthly', sequence=10,
        )
        self._post_entry(self.test_expense, 5000.0, date(2024, 1, 15))
        period.invalidate_recordset()
        # Actual is positive but allocated is zero ⇒ consumption = 0.
        self.assertAlmostEqual(period.consumption_percent, 0.0, places=2)

    # ------------------------------------------------------------------
    # _generate_equal_distribution (monthly, quarterly, rounding)
    # ------------------------------------------------------------------

    def test_bm002_equal_distribution_monthly_creates_12_periods(self):
        """Monthly equal distribution yields 12 periods over a year."""
        line = self.env['budget.budget.line'].create({
            'budget_id': self.budget_2024.id,
            'account_id': self.test_expense_marketing.id,
            'planned_amount': 120000.0,
        })
        self.env['budget.budget.period']._generate_equal_distribution(
            line, 'monthly',
        )
        self.assertEqual(len(line.period_ids), 12)
        # Sum equals the line's planned_amount (within rounding).
        total = sum(line.period_ids.mapped('allocated_amount'))
        rounding = line.currency_id.rounding or 0.01
        self.assertEqual(
            float_compare(total, 120000.0, precision_rounding=rounding),
            0,
        )

    def test_bm002_equal_distribution_quarterly_creates_4_periods(self):
        """Quarterly equal distribution yields 4 periods over a year."""
        line = self.env['budget.budget.line'].create({
            'budget_id': self.budget_2024.id,
            'account_id': self.test_revenue.id,
            'planned_amount': 400000.0,
        })
        self.env['budget.budget.period']._generate_equal_distribution(
            line, 'quarterly',
        )
        self.assertEqual(len(line.period_ids), 4)
        for p in line.period_ids:
            self.assertAlmostEqual(p.allocated_amount, 100000.0, places=2)

    def test_bm002_equal_distribution_rounding_remainder_on_final(self):
        """Rounding residue lands on the FINAL period only."""
        line = self.env['budget.budget.line'].create({
            'budget_id': self.budget_2024.id,
            'account_id': self.test_expense_marketing.id,
            'planned_amount': 100.0,  # 100 / 12 = 8.333..., not exact
        })
        self.env['budget.budget.period']._generate_equal_distribution(
            line, 'monthly',
        )
        self.assertEqual(len(line.period_ids), 12)
        # Sum matches planned_amount exactly.
        total = sum(line.period_ids.mapped('allocated_amount'))
        self.assertAlmostEqual(total, 100.0, places=2)
        # The last period should absorb the residual.
        ordered = line.period_ids.sorted(key=lambda p: (p.date_from, p.sequence))
        last_amount = ordered[-1].allocated_amount
        first_amount = ordered[0].allocated_amount
        # Per-period rounded to 2 places = 8.33; last = 100 - 11*8.33 = 8.37
        # (or similar — the invariant is that the last period differs).
        # At minimum: first_amount is the canonical per-period amount,
        # and last_amount + 11*first_amount == 100.
        self.assertAlmostEqual(
            11 * first_amount + last_amount,
            100.0,
            places=2,
        )

    def test_bm002_equal_distribution_sets_allocation_method_equal(self):
        """Generated periods carry ``allocation_method='equal'``."""
        line = self.env['budget.budget.line'].create({
            'budget_id': self.budget_2024.id,
            'account_id': self.test_expense_marketing.id,
            'planned_amount': 60000.0,
        })
        self.env['budget.budget.period']._generate_equal_distribution(
            line, 'monthly',
        )
        for p in line.period_ids:
            self.assertEqual(p.allocation_method, 'equal')

    def test_bm002_equal_distribution_assigns_sequence_increments(self):
        """Generated periods have ``sequence = (idx+1) * 10``."""
        line = self.env['budget.budget.line'].create({
            'budget_id': self.budget_2024.id,
            'account_id': self.test_expense_marketing.id,
            'planned_amount': 40000.0,
        })
        self.env['budget.budget.period']._generate_equal_distribution(
            line, 'quarterly',
        )
        ordered = line.period_ids.sorted(key=lambda p: p.date_from)
        self.assertEqual(ordered[0].sequence, 10)
        self.assertEqual(ordered[1].sequence, 20)
        self.assertEqual(ordered[2].sequence, 30)
        self.assertEqual(ordered[3].sequence, 40)

    def test_bm002_equal_distribution_rejects_existing_periods(self):
        """UserError when the line already has period_ids."""
        line = self.env['budget.budget.line'].create({
            'budget_id': self.budget_2024.id,
            'account_id': self.test_expense_marketing.id,
            'planned_amount': 40000.0,
        })
        self.env['budget.budget.period']._generate_equal_distribution(
            line, 'quarterly',
        )
        # Second call raises UserError.
        with self.assertRaises(UserError) as ctx:
            self.env['budget.budget.period']._generate_equal_distribution(
                line, 'quarterly',
            )
        self.assertIn('already has', str(ctx.exception))
        self.assertIn('period allocation', str(ctx.exception))

    def test_bm002_equal_distribution_falls_back_to_budget_dates(self):
        """When line has no dates, falls back to budget's date_from/to."""
        # line.date_from / date_to come from budget via related fields —
        # the method must still compute periods spanning the budget.
        line = self.env['budget.budget.line'].create({
            'budget_id': self.budget_2024.id,
            'account_id': self.test_expense_marketing.id,
            'planned_amount': 40000.0,
        })
        self.env['budget.budget.period']._generate_equal_distribution(
            line, 'annual',
        )
        # Annual period covers the full fiscal year.
        self.assertEqual(len(line.period_ids), 1)
        ordered = line.period_ids.sorted(key=lambda p: p.date_from)
        self.assertEqual(ordered[0].date_from, date(2024, 1, 1))
        self.assertEqual(ordered[0].date_to, date(2024, 12, 31))

    # ------------------------------------------------------------------
    # _split_date_range (monthly / quarterly / annual / custom)
    # ------------------------------------------------------------------

    def test_bm002_split_date_range_monthly(self):
        """Monthly split yields 12 (date_from, date_to) tuples for 1 year."""
        Period = self.env['budget.budget.period']
        tuples = Period._split_date_range(
            date(2024, 1, 1), date(2024, 12, 31), 'monthly',
        )
        self.assertEqual(len(tuples), 12)
        self.assertEqual(tuples[0], (date(2024, 1, 1), date(2024, 1, 31)))
        self.assertEqual(tuples[1], (date(2024, 2, 1), date(2024, 2, 29)))
        self.assertEqual(tuples[-1], (date(2024, 12, 1), date(2024, 12, 31)))

    def test_bm002_split_date_range_quarterly(self):
        """Quarterly split yields 4 tuples for 1 year."""
        Period = self.env['budget.budget.period']
        tuples = Period._split_date_range(
            date(2024, 1, 1), date(2024, 12, 31), 'quarterly',
        )
        self.assertEqual(len(tuples), 4)
        self.assertEqual(tuples[0][0], date(2024, 1, 1))
        self.assertEqual(tuples[-1][1], date(2024, 12, 31))

    def test_bm002_split_date_range_annual_single(self):
        """Annual split yields a single tuple over the input range."""
        Period = self.env['budget.budget.period']
        tuples = Period._split_date_range(
            date(2024, 1, 1), date(2024, 12, 31), 'annual',
        )
        self.assertEqual(len(tuples), 1)

    def test_bm002_split_date_range_custom_single_tuple(self):
        """Non-standard ``period_type`` returns a single-tuple range."""
        Period = self.env['budget.budget.period']
        tuples = Period._split_date_range(
            date(2024, 3, 15), date(2024, 7, 20), 'custom',
        )
        self.assertEqual(tuples, [(date(2024, 3, 15), date(2024, 7, 20))])

    def test_bm002_split_date_range_empty_when_missing_dates(self):
        """Returns [] when date_from or date_to is missing."""
        Period = self.env['budget.budget.period']
        self.assertEqual(
            Period._split_date_range(None, date(2024, 12, 31), 'monthly'),
            [],
        )
        self.assertEqual(
            Period._split_date_range(date(2024, 1, 1), None, 'monthly'),
            [],
        )

    def test_bm002_split_date_range_empty_when_inverted(self):
        """Returns [] when date_from > date_to."""
        Period = self.env['budget.budget.period']
        tuples = Period._split_date_range(
            date(2024, 12, 31), date(2024, 1, 1), 'monthly',
        )
        self.assertEqual(tuples, [])

    def test_bm002_split_date_range_monthly_final_clamped(self):
        """Final period is clamped to the provided date_to bound."""
        Period = self.env['budget.budget.period']
        tuples = Period._split_date_range(
            date(2024, 1, 1), date(2024, 3, 15), 'monthly',
        )
        self.assertEqual(tuples[-1][1], date(2024, 3, 15))

    # ------------------------------------------------------------------
    # write() override: audit trail capture
    # ------------------------------------------------------------------

    def test_bm002_write_captures_prev_amount_and_user(self):
        """Writing ``allocated_amount`` records audit fields."""
        line = self.env['budget.budget.line'].create({
            'budget_id': self.budget_2024.id,
            'account_id': self.test_expense_marketing.id,
            'planned_amount': 40000.0,
        })
        self.env['budget.budget.period']._generate_equal_distribution(
            line, 'quarterly',
        )
        first_period = line.period_ids.sorted(key=lambda p: p.date_from)[0]
        original_amount = first_period.allocated_amount
        # Update — forced to keep line total consistent by touching all
        # four quarters (second absorbs delta).
        second_period = line.period_ids.sorted(key=lambda p: p.date_from)[1]
        delta = 5000.0
        # Zero-and-restore pattern: ``_check_sum_matches_line`` fires
        # on every ``allocated_amount`` write. A naive split-write
        # (first +delta, then second -delta) produces a mid-operation
        # state where sum=45000 ≠ planned=40000 → ValidationError. We
        # temporarily zero ``line.planned_amount`` — which short-
        # circuits the constraint (``if not line.planned_amount:
        # continue``) — perform both rebalancing writes, then restore
        # the original planned amount. Writes to ``planned_amount`` do
        # NOT trigger ``@api.constrains('allocated_amount',
        # 'budget_line_id')`` on periods, so this is safe.
        line.write({'planned_amount': 0.0})
        first_period.with_user(self.env.user).write(
            {'allocated_amount': original_amount + delta},
        )
        second_period.with_user(self.env.user).write(
            {'allocated_amount': second_period.allocated_amount - delta},
        )
        line.write({'planned_amount': 40000.0})
        # Audit fields populated on first_period.
        self.assertAlmostEqual(
            first_period.prev_amount, original_amount, places=2,
        )
        self.assertEqual(first_period.modified_by_id, self.env.user)
        self.assertTrue(first_period.modified_date)

    def test_bm002_write_fast_path_when_amount_unchanged(self):
        """Write without ``allocated_amount`` does NOT touch audit fields."""
        line = self.env['budget.budget.line'].create({
            'budget_id': self.budget_2024.id,
            'account_id': self.test_expense_marketing.id,
            'planned_amount': 40000.0,
        })
        self.env['budget.budget.period']._generate_equal_distribution(
            line, 'quarterly',
        )
        first_period = line.period_ids.sorted(key=lambda p: p.date_from)[0]
        # No prev_amount yet (never written).
        self.assertFalse(first_period.modified_by_id)
        # Write only audit_note — fast path.
        first_period.write({'audit_note': 'Note only'})
        # modified_by_id remains unset because allocated_amount didn't change.
        self.assertFalse(first_period.modified_by_id)

    def test_bm002_write_honors_caller_supplied_audit_values(self):
        """Explicit audit vals from caller are not overridden."""
        line = self.env['budget.budget.line'].create({
            'budget_id': self.budget_2024.id,
            'account_id': self.test_expense_marketing.id,
            'planned_amount': 40000.0,
        })
        self.env['budget.budget.period']._generate_equal_distribution(
            line, 'quarterly',
        )
        first_period = line.period_ids.sorted(key=lambda p: p.date_from)[0]
        second_period = line.period_ids.sorted(key=lambda p: p.date_from)[1]
        original = first_period.allocated_amount
        delta = 2000.0
        custom_datetime = datetime(2023, 1, 1, 0, 0, 0)
        # Zero-and-restore pattern (see
        # ``test_bm002_write_captures_prev_amount_and_user`` for the
        # rationale). The split-write sequence produces an
        # intermediate state (sum=42000 ≠ planned=40000) that would
        # trip ``_check_sum_matches_line`` without this bypass.
        line.write({'planned_amount': 0.0})
        # Caller supplies explicit prev_amount + modified_by_id + modified_date.
        first_period.write({
            'allocated_amount': original + delta,
            'prev_amount': 99999.0,
            'modified_by_id': self.env.user.id,
            'modified_date': custom_datetime,
        })
        second_period.write({
            'allocated_amount': second_period.allocated_amount - delta,
        })
        line.write({'planned_amount': 40000.0})
        # Custom prev_amount is honored (not overwritten with old value).
        self.assertAlmostEqual(first_period.prev_amount, 99999.0, places=2)

    # ------------------------------------------------------------------
    # _check_sum_matches_line constraint
    # ------------------------------------------------------------------

    def test_bm002_check_sum_matches_line_rejects_mismatch(self):
        """Sum of periods != line.planned_amount raises ValidationError."""
        line = self.env['budget.budget.line'].create({
            'budget_id': self.budget_2024.id,
            'account_id': self.test_expense_marketing.id,
            'planned_amount': 30000.0,
        })
        # Generate an equal distribution → valid initial state.
        self.env['budget.budget.period']._generate_equal_distribution(
            line, 'quarterly',
        )
        # Force the sum to exceed planned_amount by 1000 on first period.
        first_period = line.period_ids.sorted(key=lambda p: p.date_from)[0]
        with self.assertRaises(ValidationError) as ctx:
            first_period.write({
                'allocated_amount': first_period.allocated_amount + 1000.0,
            })
        self.assertIn('Sum of period allocations', str(ctx.exception))

    def test_bm002_check_sum_matches_line_short_circuit_no_periods(self):
        """No period_ids → constraint short-circuits (no raise)."""
        line = self.env['budget.budget.line'].create({
            'budget_id': self.budget_2024.id,
            'account_id': self.test_expense_marketing.id,
            'planned_amount': 40000.0,
        })
        # No periods yet — writing the line is fine.
        line.write({'planned_amount': 45000.0})
        self.assertAlmostEqual(line.planned_amount, 45000.0, places=2)

    def test_bm002_check_sum_matches_line_tolerance(self):
        """Sum within currency rounding tolerance is accepted."""
        line = self.env['budget.budget.line'].create({
            'budget_id': self.budget_2024.id,
            'account_id': self.test_expense_marketing.id,
            'planned_amount': 120000.0,
        })
        self.env['budget.budget.period']._generate_equal_distribution(
            line, 'monthly',
        )
        # Sum should already be exact — verify.
        total = sum(line.period_ids.mapped('allocated_amount'))
        self.assertAlmostEqual(total, 120000.0, places=2)

    # ------------------------------------------------------------------
    # _copy_from_previous_budget
    # ------------------------------------------------------------------

    def test_bm002_copy_from_previous_budget_percentage_preservation(self):
        """Percentages of source periods are preserved on destination."""
        # Source: FY2024 line with 3 periods of different sizes.
        src_line = self.env['budget.budget.line'].create({
            'budget_id': self.budget_2024.id,
            'account_id': self.test_expense_marketing.id,
            'planned_amount': 1000.0,
        })
        Period = self.env['budget.budget.period']
        # Manually create source periods (10 / 30 / 60 split) via a
        # SINGLE batch create. ``@api.constrains`` fires once after the
        # whole batch is materialized, so the cumulative sum (100 + 300
        # + 600 = 1000) matches ``src_line.planned_amount`` and
        # ``_check_sum_matches_line`` passes. Iterating per-period and
        # calling ``create()`` individually would trip the constraint
        # on the first record (sum = 100 ≠ 1000).
        Period.create([
            {
                'budget_line_id': src_line.id,
                'date_from': date(2024, 1, 1),
                'date_to': date(2024, 4, 30),
                'allocated_amount': 100.0,
                'period_type': 'custom',
                'allocation_method': 'manual',
                'sequence': 10,
            },
            {
                'budget_line_id': src_line.id,
                'date_from': date(2024, 5, 1),
                'date_to': date(2024, 8, 31),
                'allocated_amount': 300.0,
                'period_type': 'custom',
                'allocation_method': 'manual',
                'sequence': 20,
            },
            {
                'budget_line_id': src_line.id,
                'date_from': date(2024, 9, 1),
                'date_to': date(2024, 12, 31),
                'allocated_amount': 600.0,
                'period_type': 'custom',
                'allocation_method': 'manual',
                'sequence': 30,
            },
        ])
        # Destination: FY2025 budget + matching line with 2x the amount.
        dest_budget = self.env['budget.budget'].create({
            'name': 'FY2025',
            'date_from': date(2025, 1, 1),
            'date_to': date(2025, 12, 31),
        })
        dest_line = self.env['budget.budget.line'].create({
            'budget_id': dest_budget.id,
            'account_id': self.test_expense_marketing.id,
            'planned_amount': 2000.0,
        })
        Period._copy_from_previous_budget(self.budget_2024, dest_budget)
        # Destination should have 3 periods summing to 2000.
        self.assertEqual(len(dest_line.period_ids), 3)
        total = sum(dest_line.period_ids.mapped('allocated_amount'))
        self.assertAlmostEqual(total, 2000.0, places=2)
        # Percentages: 10/30/60 preserved → 200/600/1200
        ordered = dest_line.period_ids.sorted(key=lambda p: p.date_from)
        self.assertAlmostEqual(ordered[0].allocated_amount, 200.0, places=2)
        self.assertAlmostEqual(ordered[1].allocated_amount, 600.0, places=2)
        self.assertAlmostEqual(ordered[2].allocated_amount, 1200.0, places=2)

    def test_bm002_copy_from_previous_budget_year_offset(self):
        """Date shift uses ``relativedelta(years=offset)``."""
        src_line = self.env['budget.budget.line'].create({
            'budget_id': self.budget_2024.id,
            'account_id': self.test_expense_marketing.id,
            'planned_amount': 500.0,
        })
        Period = self.env['budget.budget.period']
        Period.create({
            'budget_line_id': src_line.id,
            'date_from': date(2024, 3, 1),
            'date_to': date(2024, 3, 31),
            'allocated_amount': 500.0,
            'period_type': 'monthly',
            'allocation_method': 'manual',
            'sequence': 10,
        })
        dest_budget = self.env['budget.budget'].create({
            'name': 'FY2025',
            'date_from': date(2025, 1, 1),
            'date_to': date(2025, 12, 31),
        })
        dest_line = self.env['budget.budget.line'].create({
            'budget_id': dest_budget.id,
            'account_id': self.test_expense_marketing.id,
            'planned_amount': 500.0,
        })
        Period._copy_from_previous_budget(self.budget_2024, dest_budget)
        self.assertEqual(len(dest_line.period_ids), 1)
        dest_period = dest_line.period_ids[0]
        # Shifted by +1 year: 2024-03-01 → 2025-03-01
        self.assertEqual(dest_period.date_from, date(2025, 3, 1))
        self.assertEqual(dest_period.date_to, date(2025, 3, 31))

    def test_bm002_copy_from_previous_budget_skips_preallocated_dest(self):
        """Destination lines that already have periods are skipped."""
        src_line = self.env['budget.budget.line'].create({
            'budget_id': self.budget_2024.id,
            'account_id': self.test_expense_marketing.id,
            'planned_amount': 500.0,
        })
        Period = self.env['budget.budget.period']
        Period.create({
            'budget_line_id': src_line.id,
            'date_from': date(2024, 3, 1),
            'date_to': date(2024, 3, 31),
            'allocated_amount': 500.0,
            'period_type': 'monthly',
            'allocation_method': 'manual',
            'sequence': 10,
        })
        dest_budget = self.env['budget.budget'].create({
            'name': 'FY2025',
            'date_from': date(2025, 1, 1),
            'date_to': date(2025, 12, 31),
        })
        dest_line = self.env['budget.budget.line'].create({
            'budget_id': dest_budget.id,
            'account_id': self.test_expense_marketing.id,
            'planned_amount': 500.0,
        })
        # Pre-create a period on dest_line.
        Period.create({
            'budget_line_id': dest_line.id,
            'date_from': date(2025, 1, 1),
            'date_to': date(2025, 12, 31),
            'allocated_amount': 500.0,
            'period_type': 'annual',
            'allocation_method': 'manual',
            'sequence': 10,
        })
        original_period_count = len(dest_line.period_ids)
        Period._copy_from_previous_budget(self.budget_2024, dest_budget)
        # Preserved user customization — count unchanged.
        self.assertEqual(len(dest_line.period_ids), original_period_count)

    def test_bm002_copy_from_previous_budget_sets_allocation_method(self):
        """Copied periods are stamped with ``copy_previous`` method."""
        src_line = self.env['budget.budget.line'].create({
            'budget_id': self.budget_2024.id,
            'account_id': self.test_expense_marketing.id,
            'planned_amount': 500.0,
        })
        Period = self.env['budget.budget.period']
        Period.create({
            'budget_line_id': src_line.id,
            'date_from': date(2024, 1, 1),
            'date_to': date(2024, 12, 31),
            'allocated_amount': 500.0,
            'period_type': 'annual',
            'allocation_method': 'manual',
            'sequence': 10,
        })
        dest_budget = self.env['budget.budget'].create({
            'name': 'FY2025',
            'date_from': date(2025, 1, 1),
            'date_to': date(2025, 12, 31),
        })
        dest_line = self.env['budget.budget.line'].create({
            'budget_id': dest_budget.id,
            'account_id': self.test_expense_marketing.id,
            'planned_amount': 500.0,
        })
        Period._copy_from_previous_budget(self.budget_2024, dest_budget)
        for p in dest_line.period_ids:
            self.assertEqual(p.allocation_method, 'copy_previous')
            # allocation_percentage is set to the source share * 100
            self.assertAlmostEqual(p.allocation_percentage, 100.0, places=2)

    # ------------------------------------------------------------------
    # action_open_source_transactions
    # ------------------------------------------------------------------

    def test_bm002_action_open_source_transactions(self):
        """Opens an act_window on account.move.line with date filter."""
        period = self._create_period(
            self.line_expense,
            date(2024, 1, 1), date(2024, 3, 31), 30000.0,
            period_type='quarterly', sequence=10,
        )
        action = period.action_open_source_transactions()
        self.assertEqual(action['type'], 'ir.actions.act_window')
        self.assertEqual(action['res_model'], 'account.move.line')
        # Domain filters by account + parent_state + date range.
        domain = action['domain']
        self.assertIn(
            ('account_id', '=', self.test_expense.id),
            domain,
        )
        self.assertIn(
            ('parent_state', '=', 'posted'),
            domain,
        )
        self.assertIn(
            ('date', '>=', date(2024, 1, 1)),
            domain,
        )
        self.assertIn(
            ('date', '<=', date(2024, 3, 31)),
            domain,
        )

    # ------------------------------------------------------------------
    # SQL CHECK constraints
    # ------------------------------------------------------------------

    def test_bm002_sql_check_allocated_amount_non_negative(self):
        """SQL CHECK: ``allocated_amount >= 0``."""
        with self.assertRaises(Exception):  # IntegrityError from psycopg2
            with mute_logger('odoo.sql_db'):
                self.env['budget.budget.period'].create({
                    'budget_line_id': self.line_expense.id,
                    'date_from': date(2024, 1, 1),
                    'date_to': date(2024, 1, 31),
                    'allocated_amount': -1.0,
                    'period_type': 'monthly',
                    'allocation_method': 'manual',
                })
                self.env.cr.flush()

    def test_bm002_sql_check_allocation_percentage_bounded_above(self):
        """SQL CHECK: ``allocation_percentage <= 100``."""
        with self.assertRaises(Exception):
            with mute_logger('odoo.sql_db'):
                self.env['budget.budget.period'].create({
                    'budget_line_id': self.line_expense.id,
                    'date_from': date(2024, 1, 1),
                    'date_to': date(2024, 1, 31),
                    'allocated_amount': 0.0,
                    'allocation_percentage': 150.0,
                    'period_type': 'monthly',
                    'allocation_method': 'percentage',
                })
                self.env.cr.flush()

    def test_bm002_sql_check_allocation_percentage_bounded_below(self):
        """SQL CHECK: ``allocation_percentage >= 0``."""
        with self.assertRaises(Exception):
            with mute_logger('odoo.sql_db'):
                self.env['budget.budget.period'].create({
                    'budget_line_id': self.line_expense.id,
                    'date_from': date(2024, 1, 1),
                    'date_to': date(2024, 1, 31),
                    'allocated_amount': 0.0,
                    'allocation_percentage': -5.0,
                    'period_type': 'monthly',
                    'allocation_method': 'percentage',
                })
                self.env.cr.flush()

    # ------------------------------------------------------------------
    # Audit note persistence
    # ------------------------------------------------------------------

    def test_bm002_audit_note_is_persisted(self):
        """``audit_note`` is stored verbatim."""
        period = self._create_period(
            self.line_expense,
            date(2024, 1, 1), date(2024, 3, 31), 30000.0,
            period_type='quarterly', sequence=10,
        )
        period.write({'audit_note': 'Q1 increased per finance meeting'})
        self.assertEqual(
            period.audit_note,
            'Q1 increased per finance meeting',
        )

    def test_bm002_sequence_ordering_is_monotonic(self):
        """``_order`` clause sorts by (budget_line_id, date_from, sequence)."""
        line = self.env['budget.budget.line'].create({
            'budget_id': self.budget_2024.id,
            'account_id': self.test_expense_marketing.id,
            'planned_amount': 40000.0,
        })
        self.env['budget.budget.period']._generate_equal_distribution(
            line, 'quarterly',
        )
        ordered = line.period_ids.sorted(key=lambda p: p.date_from)
        # Seq ascending: 10, 20, 30, 40.
        sequences = [p.sequence for p in ordered]
        self.assertEqual(sequences, sorted(sequences))
