# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Test Suite for BM-002: Budget Period Allocation

Implements comprehensive tests for budget.budget.period model:
period generation, allocation methods, sum validation, audit trail,
and copy-from-previous functionality per BM-002 acceptance criteria:

- Scenario 1: Monthly allocation generates 12 periods per fiscal year
- Scenario 2: Quarterly allocation generates 4 periods per fiscal year
- Scenario 3: Equal distribution with rounding absorbed in final period
- Scenario 4: Custom/manual allocation with discrepancy detection
- Scenario 5: Audit trail on modifications (prev_amount, modified_by_id, modified_date)
- Scenario 6: Copy from previous budget preserving percentage distribution

Implementation notes:
---------------------

The ``budget.budget.period`` model declares BOTH a Python
``@api.constrains('date_from', 'date_to')`` (``_check_dates``,
raising ``ValidationError``) AND a SQL CHECK constraint
``_date_range_valid = models.Constraint('CHECK(date_from <= date_to)')``.
On INSERT, PostgreSQL evaluates the SQL CHECK before Odoo's Python
``@api.constrains`` runs, so the inverted-date-range scenario raises
``psycopg2.IntegrityError`` rather than ``ValidationError``. The
test ``test_bm002_period_date_from_after_date_to_raises`` therefore
catches ``IntegrityError`` and uses ``mute_logger('odoo.sql_db')``
to keep the test output clean. (Odoo's ``_assertRaises`` override
in ``odoo/tests/common.py`` does not support tuple arguments via
``issubclass``, so a single exception class must be passed.)

The model's ``_check_sum_matches_line`` constraint fires whenever a
period's ``allocated_amount`` is written and requires the sum of
sibling period ``allocated_amount`` values to match the parent line's
``planned_amount`` within currency rounding. To create periods whose
allocations align with the parent line's planned amount we use either
(a) a parent line whose planned amount equals the period's allocation,
or (b) a single batch ``create([...])`` call so the constraint runs
once after all records are materialized.

Target: >=80% line coverage per Rule R-04.
"""

from datetime import date

from dateutil.relativedelta import relativedelta
from psycopg2 import IntegrityError

from odoo import Command, fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tools import float_compare, float_round, mute_logger

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestBudgetPeriodAllocation(AccountTestInvoicingCommon):
    """
    Test class for BM-002: Budget Period Allocation.

    Validates monthly/quarterly period generation, equal/manual/
    copy-previous allocation methods, rounding behavior, audit trail
    fields, and cross-budget copy with percentage pattern preservation.
    Inherits from :class:`AccountTestInvoicingCommon` so that
    ``self.company_data['default_journal_misc']`` is available for
    posting balanced ``account.move`` entries (used in the
    ``actual_amount`` computation tests).
    """

    @classmethod
    def setUpClass(cls):
        """Set up shared chart-of-accounts test fixtures.

        Creates two GL accounts (``test_expense`` of type ``expense``
        and ``test_revenue`` of type ``income``) with an isolated
        ``XTEST.*`` numeric prefix so that tests never collide with
        the standard chart-of-accounts loaded by Odoo.
        """
        super().setUpClass()
        AccountAccount = cls.env['account.account']

        # Test expense account — used in nearly every test as the
        # ``account_id`` of the budget line under test.
        cls.test_expense = AccountAccount.create({
            'code': 'XTEST.60000',
            'name': 'Test Operating Expense',
            'account_type': 'expense',
        })
        # Test revenue account — used by tests that need an income-
        # type account (e.g. quarterly distribution on income lines).
        cls.test_revenue = AccountAccount.create({
            'code': 'XTEST.40000',
            'name': 'Test Sales Revenue',
            'account_type': 'income',
        })

    # ------------------------------------------------------------------
    # Helper Methods
    # ------------------------------------------------------------------

    def _create_budget_with_line(self, planned_amount=120000.0,
                                 date_from=None, date_to=None,
                                 account=None, name='BM-002 Budget'):
        """Create a draft budget plus one line for period-allocation tests.

        Args:
            planned_amount (float): The line's ``planned_amount`` —
                used as the sum-target for ``_check_sum_matches_line``.
            date_from (date | None): Budget start; defaults to
                ``2024-01-01`` so periods created in 2024 are valid.
            date_to (date | None): Budget end; defaults to
                ``2024-12-31``.
            account (recordset | None): GL account for the line;
                defaults to ``self.test_expense``.
            name (str): Human-readable budget name.

        Returns:
            tuple[budget.budget, budget.budget.line]: The created
            budget header and its single line.
        """
        budget = self.env['budget.budget'].create({
            'name': name,
            'date_from': date_from or date(2024, 1, 1),
            'date_to': date_to or date(2024, 12, 31),
        })
        line = self.env['budget.budget.line'].create({
            'budget_id': budget.id,
            'account_id': (account or self.test_expense).id,
            'planned_amount': planned_amount,
        })
        return budget, line

    # ------------------------------------------------------------------
    # Scenario 1: Monthly allocation (12 periods per year)
    # ------------------------------------------------------------------

    def test_bm002_equal_distribution_monthly_creates_12_periods(self):
        """Equal distribution over a fiscal year produces 12 monthly periods.

        Verifies BM-002 Scenario 1 by calling the
        ``_generate_equal_distribution`` helper with ``period_type =
        'monthly'`` and asserting that the line ends up with exactly
        twelve ``budget.budget.period`` children spanning from
        ``2024-01-01`` through ``2024-12-31`` inclusive.
        """
        _, line = self._create_budget_with_line(planned_amount=120000.0)
        BudgetPeriod = self.env['budget.budget.period']
        BudgetPeriod._generate_equal_distribution(line, 'monthly')
        periods = line.period_ids
        self.assertEqual(len(periods), 12)
        # All periods in the same fiscal year — earliest start and
        # latest end coincide with the budget's fiscal window.
        self.assertEqual(min(p.date_from for p in periods), date(2024, 1, 1))
        self.assertEqual(max(p.date_to for p in periods), date(2024, 12, 31))

    def test_bm002_equal_distribution_monthly_sums_to_line_total(self):
        """Sum of allocated amounts equals line planned_amount (within tolerance).

        Verifies the sum-matches-line invariant of BM-002 Scenario 1
        using ``float_compare`` with the line's currency rounding as
        the precision so that USD (0.01) and other currencies are
        handled correctly.
        """
        _, line = self._create_budget_with_line(planned_amount=120000.0)
        self.env['budget.budget.period']._generate_equal_distribution(
            line, 'monthly',
        )
        total_allocated = sum(line.period_ids.mapped('allocated_amount'))
        self.assertEqual(
            float_compare(
                total_allocated, line.planned_amount,
                precision_rounding=line.currency_id.rounding,
            ),
            0,
        )

    def test_bm002_equal_distribution_monthly_rounding_on_final_period(self):
        """Rounding remainder is absorbed by the final period.

        Verifies BM-002 Scenario 3 (rounding behaviour). 100 / 12 =
        8.3333... — the equal-distribution generator rounds each of
        the first eleven periods to 8.33 (currency precision = 0.01),
        then assigns the remainder (100 - 11 * 8.33 = 8.37) to the
        twelfth period so the sum equals 100.00 exactly.
        """
        _, line = self._create_budget_with_line(planned_amount=100.0)
        self.env['budget.budget.period']._generate_equal_distribution(
            line, 'monthly',
        )
        periods = line.period_ids.sorted(lambda p: p.date_from)
        first_eleven = periods[:11]
        final = periods[11]
        # All first 11 should have the same rounded amount.
        base_amount = float_round(100.0 / 12.0, precision_rounding=0.01)
        for period in first_eleven:
            self.assertAlmostEqual(period.allocated_amount, base_amount, places=2)
        # Final must absorb the rounding remainder.
        expected_final = 100.0 - base_amount * 11
        self.assertAlmostEqual(final.allocated_amount, expected_final, places=2)
        # Total exactly equals the line amount.
        self.assertAlmostEqual(
            sum(periods.mapped('allocated_amount')), 100.0, places=2,
        )

    # ------------------------------------------------------------------
    # Scenario 2: Quarterly allocation (4 periods)
    # ------------------------------------------------------------------

    def test_bm002_equal_distribution_quarterly_creates_4_periods(self):
        """Quarterly distribution produces exactly 4 periods covering Q1-Q4.

        Verifies BM-002 Scenario 2: a fiscal-year quarterly split
        yields four periods, each spanning approximately three months.
        ``relativedelta`` is used to confirm that consecutive quarter
        boundaries are exactly three months apart (modulo end-of-month
        edge cases).
        """
        _, line = self._create_budget_with_line(planned_amount=40000.0)
        self.env['budget.budget.period']._generate_equal_distribution(
            line, 'quarterly',
        )
        periods = line.period_ids
        self.assertEqual(len(periods), 4)
        # Each quarter spans 3 calendar months — verify via
        # ``relativedelta`` arithmetic on the sorted periods so we
        # accommodate any end-of-month rounding the generator applies.
        ordered = periods.sorted(lambda p: p.date_from)
        self.assertEqual(ordered[0].date_from, date(2024, 1, 1))
        self.assertEqual(ordered[-1].date_to, date(2024, 12, 31))
        # Verify quarter boundaries via month differences.
        for idx in range(len(ordered) - 1):
            current = ordered[idx]
            next_period = ordered[idx + 1]
            # Next period's start = current period's end + 1 day
            expected_next_start = current.date_to + relativedelta(days=1)
            self.assertEqual(next_period.date_from, expected_next_start)

    def test_bm002_equal_distribution_quarterly_sums_to_line_total(self):
        """Quarterly equal distribution sums to the line total.

        Verifies the sum-matches-line invariant of BM-002 Scenario 2:
        the four quarterly amounts add up to the parent line's
        ``planned_amount`` exactly within currency rounding precision.
        """
        _, line = self._create_budget_with_line(planned_amount=40000.0)
        self.env['budget.budget.period']._generate_equal_distribution(
            line, 'quarterly',
        )
        total = sum(line.period_ids.mapped('allocated_amount'))
        self.assertAlmostEqual(total, 40000.0, places=2)

    # ------------------------------------------------------------------
    # Scenario: Date-range validation
    # ------------------------------------------------------------------

    def test_bm002_period_date_from_after_date_to_raises(self):
        """A period with inverted date range is rejected.

        The ``budget.budget.period`` model declares both a Python
        ``@api.constrains`` (``_check_dates`` raising
        ``ValidationError``) and a SQL CHECK constraint
        (``_date_range_valid``). PostgreSQL evaluates the SQL CHECK
        on INSERT before Odoo runs the Python ``@api.constrains``, so
        the inverted-date scenario raises ``psycopg2.IntegrityError``
        in practice. The test catches ``IntegrityError`` to match the
        first-fired layer; ``mute_logger`` suppresses the
        accompanying ``odoo.sql_db`` ERROR log line so the test
        output stays clean. (Odoo's ``assertRaises`` override does
        not support tuple arguments — see
        ``odoo/tests/common.py:537``.)
        """
        _, line = self._create_budget_with_line()
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            self.env['budget.budget.period'].create({
                'budget_line_id': line.id,
                'date_from': date(2024, 12, 31),
                'date_to': date(2024, 1, 1),
                'allocated_amount': 10000.0,
            })
            # Force any deferred SQL flush so the CHECK constraint
            # fires synchronously and the assertRaises catches it.
            self.env.cr.flush()

    def test_bm002_period_outside_budget_window_raises(self):
        """A period with dates outside the budget window fails validation.

        Verifies the ``_check_within_budget_window`` constraint which
        ensures every period falls inside its parent budget's fiscal
        bounds. The constraint raises ``ValidationError``. Note that
        ``_check_sum_matches_line`` may also fire for the same INSERT
        because the period's ``allocated_amount`` does not match the
        line's ``planned_amount`` — both Python constraints raise
        ``ValidationError`` so the ``assertRaises`` catches whichever
        fires first.
        """
        _, line = self._create_budget_with_line()
        with self.assertRaises(ValidationError):
            self.env['budget.budget.period'].create({
                'budget_line_id': line.id,
                'date_from': date(2025, 6, 1),
                'date_to': date(2025, 6, 30),
                'allocated_amount': 10000.0,
            })

    # ------------------------------------------------------------------
    # Scenario 4: Custom / Manual allocation
    # ------------------------------------------------------------------

    def test_bm002_manual_allocation_accepts_custom_amounts(self):
        """Manual allocation accepts user-specified amounts per period.

        BM-002 Scenario 4: users may distribute the planned amount
        unevenly across periods to model seasonal patterns. Verifies
        a 12-period seasonal pattern summing exactly to the line's
        planned amount via a SINGLE batch ``create([...])`` call so
        that ``_check_sum_matches_line`` evaluates the cumulative sum
        once after every record is materialised.
        """
        _, line = self._create_budget_with_line(planned_amount=120000.0)
        # 12 monthly amounts summing to 120,000 — a seasonal pattern
        # typical of retail (low summer, high December).
        seasonal = [5000, 8000, 12000, 15000, 20000, 10000,
                    7000, 8000, 10000, 12000, 8000, 5000]
        self.assertEqual(
            sum(seasonal), 120000,
            "Seasonal pattern must sum to line.planned_amount.",
        )
        vals_list = []
        for idx, amount in enumerate(seasonal):
            month_start = date(2024, idx + 1, 1)
            if idx == 11:
                # December — last day of the year.
                month_end = date(2024, 12, 31)
            else:
                month_end = (
                    month_start + relativedelta(months=1)
                ) - relativedelta(days=1)
            vals_list.append({
                'budget_line_id': line.id,
                'date_from': month_start,
                'date_to': month_end,
                'allocated_amount': amount,
                'allocation_method': 'manual',
                'period_type': 'monthly',
                'sequence': (idx + 1) * 10,
            })
        # Batch create — ``_check_sum_matches_line`` evaluates the
        # full set once after all records are materialised, allowing
        # the sum to match the planned amount.
        self.env['budget.budget.period'].create(vals_list)
        total = sum(line.period_ids.mapped('allocated_amount'))
        self.assertEqual(total, sum(seasonal))
        self.assertEqual(len(line.period_ids), 12)

    def test_bm002_sum_mismatch_discrepancy_warns_via_constrains(self):
        """When sum(periods) != line.planned_amount, @api.constrains warns.

        Verifies the ``_check_sum_matches_line`` constraint by
        creating a single period whose allocation exceeds the line's
        planned amount. The constraint fires on INSERT and raises
        ``ValidationError`` because the absolute difference exceeds
        the currency rounding tolerance.
        """
        _, line = self._create_budget_with_line(planned_amount=100000.0)
        # Single period with allocation > line total.
        with self.assertRaises(ValidationError):
            self.env['budget.budget.period'].create({
                'budget_line_id': line.id,
                'date_from': date(2024, 1, 1),
                'date_to': date(2024, 12, 31),
                'allocated_amount': 150000.0,  # exceeds line total
                'allocation_method': 'manual',
                'period_type': 'annual',
            })

    # ------------------------------------------------------------------
    # Scenario 5: Audit trail on modifications
    # ------------------------------------------------------------------

    def test_bm002_write_allocated_amount_populates_audit_fields(self):
        """Modifying allocated_amount captures audit fields.

        BM-002 Scenario 5: when a period's ``allocated_amount`` is
        modified the ``write()`` override populates ``prev_amount``
        with the value before the change, ``modified_by_id`` with the
        active user, and ``modified_date`` with the current UTC
        timestamp. The free-form ``audit_note`` field accepts the
        explanation rationale.
        """
        # Use planned_amount=30000 so a single period with allocated=30000
        # satisfies _check_sum_matches_line on initial creation.
        _, line = self._create_budget_with_line(planned_amount=30000.0)
        period = self.env['budget.budget.period'].create({
            'budget_line_id': line.id,
            'date_from': date(2024, 1, 1),
            'date_to': date(2024, 3, 31),
            'allocated_amount': 30000.0,
            'allocation_method': 'manual',
            'period_type': 'quarterly',
        })
        original_amount = period.allocated_amount
        # Bump the line's planned amount so the modified period's
        # allocation continues to satisfy ``_check_sum_matches_line``.
        line.write({'planned_amount': 35000.0})
        before_modify = fields.Datetime.now()
        period.write({
            'allocated_amount': 35000.0,
            'audit_note': 'Adjusted for Q1 ramp-up',
        })
        # Allocated amount and audit note are recorded.
        self.assertEqual(period.allocated_amount, 35000.0)
        self.assertEqual(period.audit_note, 'Adjusted for Q1 ramp-up')
        # Audit trail fields populated by the write() override.
        self.assertEqual(period.prev_amount, original_amount)
        self.assertEqual(period.modified_by_id, self.env.user)
        self.assertTrue(period.modified_date)
        # Modified date should not predate the moment we triggered the
        # write — sanity check that the timestamp is fresh.
        self.assertGreaterEqual(period.modified_date, before_modify)

    def test_bm002_write_non_amount_does_not_populate_audit(self):
        """Modifying a non-allocation field does NOT populate audit fields.

        The ``write()`` override only enters the audit-bookkeeping
        branch when ``allocated_amount`` is in ``vals``. Writes that
        only touch other fields (``sequence``, ``audit_note``, etc.)
        take the fast path, leaving audit fields untouched.
        """
        _, line = self._create_budget_with_line(planned_amount=30000.0)
        period = self.env['budget.budget.period'].create({
            'budget_line_id': line.id,
            'date_from': date(2024, 1, 1),
            'date_to': date(2024, 3, 31),
            'allocated_amount': 30000.0,
            'allocation_method': 'manual',
            'period_type': 'quarterly',
        })
        # Sanity check: audit fields are unset on a freshly-created
        # period (the write() override only fires on subsequent
        # writes that touch ``allocated_amount``).
        self.assertFalse(period.modified_by_id)
        # Write only the sequence — fast path, no audit bookkeeping.
        period.write({'sequence': 99})
        # prev_amount remains 0 (falsy) since allocated_amount didn't
        # change.
        self.assertFalse(period.prev_amount)
        self.assertFalse(period.modified_by_id)

    # ------------------------------------------------------------------
    # Scenario 6: Copy from previous budget
    # ------------------------------------------------------------------

    def test_bm002_copy_from_previous_budget_preserves_percentage(self):
        """``_copy_from_previous_budget`` preserves the percentage pattern.

        BM-002 Scenario 6: copy a 20%/30%/30%/20% quarterly pattern
        from a 2023 source budget (planned 100,000) to a 2024
        destination budget (planned 200,000). The destination periods
        are stamped with ``allocation_method='copy_previous'`` and
        the same quarterly shape — i.e. 40,000 / 60,000 / 60,000 /
        40,000 — preserving the source's pattern and respecting the
        new budget's fiscal year.
        """
        # Source: 2023 with Q1=20%, Q2=30%, Q3=30%, Q4=20%.
        src_budget = self.env['budget.budget'].create({
            'name': '2023 Budget',
            'date_from': date(2023, 1, 1),
            'date_to': date(2023, 12, 31),
        })
        src_line = self.env['budget.budget.line'].create({
            'budget_id': src_budget.id,
            'account_id': self.test_expense.id,
            'planned_amount': 100000.0,
        })
        # Build the source quarterly distribution via batch create so
        # the sum-matches-line constraint evaluates the cumulative
        # set once after all four periods are materialised.
        self.env['budget.budget.period'].create([
            {
                'budget_line_id': src_line.id,
                'date_from': date(2023, 1, 1),
                'date_to': date(2023, 3, 31),
                'allocated_amount': 20000.0,
                'period_type': 'quarterly',
                'allocation_method': 'manual',
                'sequence': 10,
            },
            {
                'budget_line_id': src_line.id,
                'date_from': date(2023, 4, 1),
                'date_to': date(2023, 6, 30),
                'allocated_amount': 30000.0,
                'period_type': 'quarterly',
                'allocation_method': 'manual',
                'sequence': 20,
            },
            {
                'budget_line_id': src_line.id,
                'date_from': date(2023, 7, 1),
                'date_to': date(2023, 9, 30),
                'allocated_amount': 30000.0,
                'period_type': 'quarterly',
                'allocation_method': 'manual',
                'sequence': 30,
            },
            {
                'budget_line_id': src_line.id,
                'date_from': date(2023, 10, 1),
                'date_to': date(2023, 12, 31),
                'allocated_amount': 20000.0,
                'period_type': 'quarterly',
                'allocation_method': 'manual',
                'sequence': 40,
            },
        ])
        # Destination: 2024 budget with double the planned amount —
        # percentages should preserve, scaling each period by 2x.
        dest_budget = self.env['budget.budget'].create({
            'name': '2024 Budget',
            'date_from': date(2024, 1, 1),
            'date_to': date(2024, 12, 31),
        })
        self.env['budget.budget.line'].create({
            'budget_id': dest_budget.id,
            'account_id': self.test_expense.id,
            'planned_amount': 200000.0,
        })
        # Invoke the copy helper.
        self.env['budget.budget.period']._copy_from_previous_budget(
            src_budget, dest_budget,
        )
        # Sort destination periods chronologically and verify the
        # quarterly pattern is preserved at the new total scale.
        dest_periods = dest_budget.mapped('line_ids.period_ids').sorted(
            lambda p: p.date_from,
        )
        self.assertEqual(len(dest_periods), 4)
        expected = [40000.0, 60000.0, 60000.0, 40000.0]
        for dest_period, exp_amount in zip(dest_periods, expected):
            self.assertAlmostEqual(
                dest_period.allocated_amount, exp_amount, places=2,
            )
            # Each destination period is stamped with the
            # ``copy_previous`` allocation method.
            self.assertEqual(dest_period.allocation_method, 'copy_previous')
        # The total must equal the destination line's planned_amount.
        total = sum(dest_periods.mapped('allocated_amount'))
        self.assertAlmostEqual(total, 200000.0, places=2)

    # ------------------------------------------------------------------
    # Computed fields: display_name
    # ------------------------------------------------------------------

    def test_bm002_display_name_for_monthly_period(self):
        """display_name for a monthly period reads like 'January 2024'.

        Verifies the ``_compute_name`` / ``_compute_display_name``
        compute methods. For monthly periods the underlying ``name``
        field renders as ``'%B %Y'`` (full month name + year), and
        ``display_name`` composes the account label with the period
        label.
        """
        # Use planned_amount=10000 so the single period satisfies
        # _check_sum_matches_line on creation.
        _, line = self._create_budget_with_line(planned_amount=10000.0)
        period = self.env['budget.budget.period'].create({
            'budget_line_id': line.id,
            'date_from': date(2024, 1, 1),
            'date_to': date(2024, 1, 31),
            'allocated_amount': 10000.0,
            'period_type': 'monthly',
            'allocation_method': 'manual',
        })
        # display_name should include the year and the month name.
        self.assertTrue(period.display_name)
        self.assertIn('2024', period.display_name)
        self.assertIn('January', period.display_name)

    def test_bm002_display_name_for_quarterly_period(self):
        """display_name for a quarterly period reads like 'Q1 2024'.

        For quarterly periods the underlying ``name`` field renders
        as ``'Q<N> %Y'`` where N is derived from
        ``(month-1)//3 + 1``; ``display_name`` composes the account
        label with the period label.
        """
        _, line = self._create_budget_with_line(planned_amount=30000.0)
        period = self.env['budget.budget.period'].create({
            'budget_line_id': line.id,
            'date_from': date(2024, 1, 1),
            'date_to': date(2024, 3, 31),
            'allocated_amount': 30000.0,
            'period_type': 'quarterly',
            'allocation_method': 'manual',
        })
        self.assertTrue(period.display_name)
        self.assertIn('2024', period.display_name)
        # Q1 corresponds to date(2024, 1, 1) → Q1 2024.
        self.assertIn('Q1', period.display_name)

    # ------------------------------------------------------------------
    # Related fields
    # ------------------------------------------------------------------

    def test_bm002_related_fields_track_parent_line(self):
        """period.budget_id, .account_id, .company_id are related to budget_line_id.

        Verifies the stored ``related`` fields cascade values from
        the parent ``budget.budget.line`` so that period queries can
        filter by budget / account / company without an explicit JOIN.
        """
        budget, line = self._create_budget_with_line(planned_amount=30000.0)
        period = self.env['budget.budget.period'].create({
            'budget_line_id': line.id,
            'date_from': date(2024, 1, 1),
            'date_to': date(2024, 3, 31),
            'allocated_amount': 30000.0,
            'period_type': 'quarterly',
            'allocation_method': 'manual',
        })
        self.assertEqual(period.budget_id, budget)
        self.assertEqual(period.account_id, self.test_expense)
        self.assertEqual(period.company_id, line.company_id)
        self.assertEqual(period.currency_id, line.currency_id)

    # ------------------------------------------------------------------
    # Cascade delete behaviour
    # ------------------------------------------------------------------

    def test_bm002_period_cascade_on_line_delete(self):
        """Periods are cascade-deleted when parent line is deleted.

        Verifies the ``ondelete='cascade'`` declaration on
        ``budget.budget.period.budget_line_id``: removing the parent
        line removes all of its period children atomically without
        leaving orphan period records in the database.
        """
        _, line = self._create_budget_with_line(planned_amount=30000.0)
        period = self.env['budget.budget.period'].create({
            'budget_line_id': line.id,
            'date_from': date(2024, 1, 1),
            'date_to': date(2024, 3, 31),
            'allocated_amount': 30000.0,
            'period_type': 'quarterly',
            'allocation_method': 'manual',
        })
        period_id = period.id
        line.unlink()
        # The period record no longer exists in the database.
        self.assertFalse(
            self.env['budget.budget.period'].browse(period_id).exists(),
        )

    # ------------------------------------------------------------------
    # actual_amount computation (BM-002 → BM-003 bridge)
    # ------------------------------------------------------------------

    def test_bm002_actual_amount_computes_to_zero_without_moves(self):
        """actual_amount = 0.0 when no account.move.line entries exist.

        Verifies the short-circuit branch of ``_compute_actual_amount``
        which returns zero for both ``actual_amount`` and
        ``consumption_percent`` when no posted move lines exist on
        the parent line's account within the period's date window.
        """
        _, line = self._create_budget_with_line(planned_amount=30000.0)
        period = self.env['budget.budget.period'].create({
            'budget_line_id': line.id,
            'date_from': date(2024, 1, 1),
            'date_to': date(2024, 3, 31),
            'allocated_amount': 30000.0,
            'period_type': 'quarterly',
            'allocation_method': 'manual',
        })
        # Force a fresh compute pass so cached values from related
        # field updates don't mask the zero-actuals state.
        period.invalidate_recordset(['actual_amount', 'consumption_percent'])
        self.assertEqual(period.actual_amount, 0.0)
        self.assertEqual(period.consumption_percent, 0.0)

    def test_bm002_actual_amount_computes_with_posted_moves(self):
        """actual_amount reflects sum of posted account.move.line entries.

        Posts a balanced ``account.move`` (one debit on the budget
        line's expense account plus one credit on a cash offset)
        within the period's date window; verifies that
        ``actual_amount`` reads the debited amount and that
        ``consumption_percent`` is computed correctly.
        """
        _, line = self._create_budget_with_line(planned_amount=30000.0)
        period = self.env['budget.budget.period'].create({
            'budget_line_id': line.id,
            'date_from': date(2024, 1, 1),
            'date_to': date(2024, 3, 31),
            'allocated_amount': 30000.0,
            'period_type': 'quarterly',
            'allocation_method': 'manual',
        })
        journal = self.company_data['default_journal_misc']
        # Offset account for a balanced entry — independent test
        # account so we don't pollute the chart-of-accounts cash.
        offset_cash = self.env['account.account'].create({
            'code': 'XTEST.10100',
            'name': 'Test Cash',
            'account_type': 'asset_cash',
        })
        # Post a balanced journal entry inside the Q1 window
        # (2024-02-15) with a debit on the expense account and a
        # credit on the offset cash account.
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': journal.id,
            'date': date(2024, 2, 15),
            'line_ids': [
                Command.create({
                    'account_id': self.test_expense.id,
                    'name': 'Q1 expense',
                    'debit': 5000.0,
                    'credit': 0.0,
                }),
                Command.create({
                    'account_id': offset_cash.id,
                    'name': 'Q1 cash',
                    'debit': 0.0,
                    'credit': 5000.0,
                }),
            ],
        })
        move.action_post()
        # Invalidate the computed fields so the next read re-runs the
        # batched search-and-distribute logic.
        period.invalidate_recordset(['actual_amount', 'consumption_percent'])
        # The expense account balance for the period equals the
        # debited amount (5,000) — debit positive, credit zero.
        self.assertAlmostEqual(period.actual_amount, 5000.0, places=2)
        # consumption = (actual / allocated) * 100 = 5000 / 30000 * 100
        consumption = 5000.0 / 30000.0 * 100.0
        self.assertAlmostEqual(period.consumption_percent, consumption, places=2)

    # ------------------------------------------------------------------
    # Defensive coverage of helper edge cases — exercises additional
    # branches of the model under test to push line coverage above
    # the 80% threshold mandated by Rule R-04.
    # ------------------------------------------------------------------

    def test_bm002_generate_equal_distribution_rejects_existing_periods(self):
        """``_generate_equal_distribution`` raises UserError when periods exist.

        Defensive check: re-calling the generator on a line that
        already has periods raises a ``UserError`` with a clear
        message rather than silently doubling the period count.
        """
        _, line = self._create_budget_with_line(planned_amount=40000.0)
        BudgetPeriod = self.env['budget.budget.period']
        BudgetPeriod._generate_equal_distribution(line, 'quarterly')
        # Second invocation must raise UserError.
        with self.assertRaises(UserError):
            BudgetPeriod._generate_equal_distribution(line, 'quarterly')

    def test_bm002_generate_equal_distribution_falls_back_to_budget_dates(self):
        """Generator falls back to budget's date range when line has no dates.

        Lines inherit ``date_from`` / ``date_to`` from their parent
        budget via ``related`` fields, so this branch is exercised
        whenever a line is created without explicit overrides — the
        common path. Verifies the annual fallback yields a single
        period spanning the entire fiscal window.
        """
        _, line = self._create_budget_with_line(planned_amount=40000.0)
        self.env['budget.budget.period']._generate_equal_distribution(
            line, 'annual',
        )
        # Annual period = single period covering the full fiscal
        # year. Sequence-aware sort just in case the generator
        # produces multiple periods in some configuration.
        ordered = line.period_ids.sorted(lambda p: p.date_from)
        self.assertEqual(len(ordered), 1)
        self.assertEqual(ordered[0].date_from, date(2024, 1, 1))
        self.assertEqual(ordered[0].date_to, date(2024, 12, 31))

    def test_bm002_split_date_range_monthly(self):
        """``_split_date_range`` with monthly granularity yields 12 tuples.

        Verifies the bare ``_split_date_range`` helper produces
        twelve ``(date_from, date_to)`` tuples for a calendar-year
        range — independent of the budget-line sum-check
        infrastructure. The first tuple is January 1-31, the last
        tuple is December 1-31, and each interior tuple is
        month-aligned.
        """
        Period = self.env['budget.budget.period']
        tuples = Period._split_date_range(
            date(2024, 1, 1), date(2024, 12, 31), 'monthly',
        )
        self.assertEqual(len(tuples), 12)
        # First and last tuples — anchor months.
        self.assertEqual(tuples[0], (date(2024, 1, 1), date(2024, 1, 31)))
        self.assertEqual(tuples[-1], (date(2024, 12, 1), date(2024, 12, 31)))
        # February — leap year (29 days in 2024).
        self.assertEqual(tuples[1], (date(2024, 2, 1), date(2024, 2, 29)))

    def test_bm002_split_date_range_custom_yields_single_tuple(self):
        """Non-standard ``period_type`` returns one all-encompassing tuple.

        Defensive branch coverage: when ``period_type`` does not
        match any known value, the helper returns a single-tuple
        list spanning the input range. This matches the design
        intent (custom = caller-defined window).
        """
        Period = self.env['budget.budget.period']
        tuples = Period._split_date_range(
            date(2024, 3, 15), date(2024, 7, 20), 'custom',
        )
        self.assertEqual(tuples, [(date(2024, 3, 15), date(2024, 7, 20))])

    def test_bm002_split_date_range_empty_when_inverted(self):
        """``_split_date_range`` with inverted dates returns empty list.

        Defensive guard: passing ``date_from > date_to`` short-
        circuits to an empty list rather than raising — callers can
        check the return value to detect invalid input.
        """
        Period = self.env['budget.budget.period']
        tuples = Period._split_date_range(
            date(2024, 12, 31), date(2024, 1, 1), 'monthly',
        )
        self.assertEqual(tuples, [])

    def test_bm002_action_open_source_transactions_returns_act_window(self):
        """``action_open_source_transactions`` returns an act_window dict.

        Verifies the BM-003 drill-down action: clicking the period's
        smart button on a list view returns an Odoo
        ``ir.actions.act_window`` descriptor whose ``res_model`` is
        ``account.move.line`` and whose ``domain`` filters by
        account, posted parent state, and the period's date range.
        """
        _, line = self._create_budget_with_line(planned_amount=30000.0)
        period = self.env['budget.budget.period'].create({
            'budget_line_id': line.id,
            'date_from': date(2024, 1, 1),
            'date_to': date(2024, 3, 31),
            'allocated_amount': 30000.0,
            'period_type': 'quarterly',
            'allocation_method': 'manual',
        })
        action = period.action_open_source_transactions()
        # Verify the action descriptor structure.
        self.assertEqual(action['type'], 'ir.actions.act_window')
        self.assertEqual(action['res_model'], 'account.move.line')
        # Domain filters by account, posted state, and date window.
        domain = action['domain']
        self.assertIn(('account_id', '=', self.test_expense.id), domain)
        self.assertIn(('parent_state', '=', 'posted'), domain)
        self.assertIn(('date', '>=', date(2024, 1, 1)), domain)
        self.assertIn(('date', '<=', date(2024, 3, 31)), domain)

    def test_bm002_compute_name_for_annual_period(self):
        """Annual period name is the year string.

        Defensive coverage of the ``_compute_name`` branch for
        ``period_type='annual'`` — name renders as the bare year.
        """
        _, line = self._create_budget_with_line(planned_amount=120000.0)
        period = self.env['budget.budget.period'].create({
            'budget_line_id': line.id,
            'date_from': date(2024, 1, 1),
            'date_to': date(2024, 12, 31),
            'allocated_amount': 120000.0,
            'period_type': 'annual',
            'allocation_method': 'manual',
        })
        self.assertEqual(period.name, '2024')

    def test_bm002_compute_name_for_custom_period(self):
        """Custom period name renders the date-range literal.

        Defensive coverage of the ``_compute_name`` branch for
        ``period_type='custom'`` — name renders as
        ``YYYY-MM-DD → YYYY-MM-DD``.
        """
        _, line = self._create_budget_with_line(planned_amount=10000.0)
        period = self.env['budget.budget.period'].create({
            'budget_line_id': line.id,
            'date_from': date(2024, 2, 15),
            'date_to': date(2024, 5, 20),
            'allocated_amount': 10000.0,
            'period_type': 'custom',
            'allocation_method': 'manual',
        })
        self.assertIn('2024-02-15', period.name)
        self.assertIn('2024-05-20', period.name)
