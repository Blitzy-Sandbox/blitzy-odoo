# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Tests for AM-002: Depreciation Configuration user story.

Covers the following BDD scenarios from the AM-002 ticket:

    T-AM-002-01  Straight-line by YEARS: $10K cost, $1K salvage, 5yr -> $1,800/yr * 5
    T-AM-002-02  Straight-line by MONTHS: $10K cost, $1K salvage, 36mo -> $250/mo * 36
    T-AM-002-03  Declining-balance Year 1: $10K, factor=2.0, life=5y -> $4,000
    T-AM-002-04  Declining-balance Year 2: NBV $6K, factor=2.0, life=5y -> $2,400
    T-AM-002-05  Declining-balance with SWITCH to straight-line at optimal point
    T-AM-002-06  Units-of-production: $10K, $1K, 100K units -> $0.09/unit
    T-AM-002-07  Start date: 'acquisition_date' option -> schedule starts acquisition_date
    T-AM-002-08  Start date: 'first_day_next_month' -> schedule starts 1st of next month
    T-AM-002-09  Start date: 'first_day_current_month' -> schedule starts 1st of current month
    T-AM-002-10  Start date: 'manual' -> user-specified depreciation_start_date honored
    T-AM-002-11  Category template defaults propagate via onchange (overridable)
    T-AM-002-12  Configuration validation (method/life/factor/salvage_value) rejects
                 invalid combinations

Each test method's docstring starts with the BDD scenario ID for traceability.
Financial assertions use ``self.assertAlmostEqual(..., places=2)`` for monetary
comparison (matches currency precision from the test company).

AAP Rule Compliance
-------------------
* R-01 (Module independence) -- This file imports ONLY from the Python
  standard library (``datetime``), the third-party ``python-dateutil``
  package, the ``odoo`` framework, and the local sibling ``.common``
  module within the same ``account_asset_management`` package. NO
  imports from the three sibling Community Edition modules
  (``account_budget_management``, ``account_deferred_revenue``,
  ``account_payment_followup``).
* R-02 (No Enterprise dependencies) -- This file contains NO
  references to Odoo Enterprise addon names (``account_asset``,
  ``account_accountant``, ``account_reports``, ``account_followup``,
  ``account_deferred_revenue``).
* R-04 (Per-story coverage gate) -- The 12 test methods exercise every
  documented branch of the AM-002 configuration paths:

      * ``_schedule_straight_line``       -> test_am_002_01 / 02
      * ``_schedule_declining_balance``   -> test_am_002_03 / 04 / 05
      * ``_schedule_units_of_production`` -> test_am_002_06
      * ``_resolve_depreciation_start_date`` (4 options) -> test_am_002_07-10
      * ``_compute_depreciation_schedule`` dispatcher -> all schedule tests
      * ``_onchange_category_id``         -> test_am_002_11
      * Constraint methods                -> test_am_002_12
        (``_check_acquisition_cost_positive``, ``_check_salvage_value``,
         ``_check_depreciation_config``, ``_check_declining_factor``)

* R-07 (No unjustified ``sudo``) -- This file contains NO ``.sudo()``
  calls. The test user provisioned by ``AccountTestInvoicingCommon``
  (via ``AssetManagementTestCommon.setUpClass``) has both
  ``account.group_account_user`` and ``account.group_account_manager``
  group memberships, providing full CRUD on every model touched by
  the tests via ``security/ir.model.access.csv``.

Note on ``freezegun``
---------------------
``freezegun`` is deliberately NOT used in this file because AM-002
tests depend on user-supplied ``acquisition_date`` values (not the
system clock); deterministic dates are passed in via
``_create_basic_asset(acquisition_date=date(...))``. ``freeze_time``
is reserved for AM-003 (period rendering) and AM-004 (cron triggering)
where the system clock genuinely matters.
"""

from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import Command, fields  # noqa: F401 -- imported per agent_prompt
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import AssetManagementTestCommon


@tagged('post_install', '-at_install')
class TestDepreciationConfiguration(AssetManagementTestCommon):
    """AM-002 -- Depreciation Configuration.

    Validates the depreciation configuration capability across all
    three supported methods (straight-line, declining balance,
    units-of-production), all four start-date options
    (acquisition_date, first_day_next_month, first_day_current_month,
    manual), category template propagation via onchange, and the
    full set of ``@api.constrains`` validators.

    All 12 tests use the ``_create_basic_asset`` factory inherited
    from :class:`AssetManagementTestCommon` to instantiate draft
    ``account.asset`` records with sensible defaults; per-scenario
    overrides are passed as keyword arguments.

    Test method naming convention: ``test_am_002_<NN>_<short_summary>``
    where ``<NN>`` is the BDD scenario number (zero-padded to 2
    digits) and ``<short_summary>`` is a snake_case human-readable
    summary.
    """

    # =========================================================================
    # T-AM-002-01: Straight-line depreciation in YEARS
    # =========================================================================

    def test_am_002_01_straight_line_years(self):
        """T-AM-002-01: Straight-line by YEARS: cost $10,000, salvage $1,000, 5 years -> $1,800/year * 5.

        Verifies AM-002 Scenario 1: configuring straight-line
        depreciation with useful life expressed in years produces a
        schedule with exactly ``useful_life_years`` lines, each at
        ``(acquisition_cost - salvage_value) / useful_life_years``,
        and the cumulative schedule sums to ``acquisition_cost -
        salvage_value`` exactly.

        Formula: annual_dep = (10000 - 1000) / 5 = 1800.00
        """
        asset = self._create_basic_asset(
            self,
            name='AM-002-01 Straight-Line Years',
            acquisition_cost=10000.0,
            salvage_value=1000.0,
            depreciation_method='straight_line',
            useful_life_unit='years',
            useful_life_years=5,
            useful_life_months=0,
            acquisition_date=date(2024, 1, 1),
            start_date_option='acquisition_date',
        )
        asset.action_confirm()

        # Schedule has exactly 5 lines (one per year).
        self.assertEqual(
            len(asset.depreciation_line_ids),
            5,
            'Straight-line 5-year schedule must have 5 lines.',
        )

        # All lines have the per-period amount = 1800.00.
        # The implementation absorbs cumulative rounding error in
        # the FINAL line; with 1800 * 5 == 9000 exactly there is no
        # rounding residual, so every line equals 1800.00.
        sorted_lines = asset.depreciation_line_ids.sorted('sequence')
        for idx, line in enumerate(sorted_lines, start=1):
            self.assertAlmostEqual(
                line.depreciation_amount,
                1800.0,
                places=2,
                msg=(
                    f'Line at sequence={idx} amount must equal '
                    f'1800.00; got {line.depreciation_amount:.2f}.'
                ),
            )

        # Sequence values run 1..5 in order.
        sequences = sorted_lines.mapped('sequence')
        self.assertEqual(
            sequences,
            [1, 2, 3, 4, 5],
            'Sequences must be 1..5 in order.',
        )

        # Line dates progress year-by-year starting on the
        # depreciation_start_date (which equals acquisition_date
        # under start_date_option='acquisition_date').
        # Verify the dates are strictly increasing and that
        # consecutive line dates differ by relativedelta(years=+1).
        sorted_by_date = sorted_lines.mapped('depreciation_date')
        self.assertEqual(
            len(set(sorted_by_date)),
            5,
            'All 5 line dates must be distinct.',
        )
        for i in range(1, len(sorted_by_date)):
            prior = sorted_by_date[i - 1]
            current = sorted_by_date[i]
            self.assertEqual(
                current,
                prior + relativedelta(years=+1),
                f'Line dates must advance by relativedelta(years=+1); '
                f'got {prior} -> {current}.',
            )
        # First line falls on the acquisition_date.
        self.assertEqual(
            sorted_by_date[0],
            date(2024, 1, 1),
            'First depreciation line must start on '
            'acquisition_date 2024-01-01.',
        )

        # Cumulative schedule sums to depreciable base = 9000.00.
        total = sum(asset.depreciation_line_ids.mapped(
            'depreciation_amount',
        ))
        self.assertAlmostEqual(
            total,
            9000.0,
            places=2,
            msg=(
                f'Schedule total must equal acquisition_cost - '
                f'salvage_value = 9000.00; got {total:.2f}.'
            ),
        )

        # Per-line cumulative_depreciation progression: 1800, 3600,
        # 5400, 7200, 9000. NBV progression: 8200, 6400, 4600,
        # 2800, 1000 (final NBV equals salvage_value, not zero).
        expected_cumulative = [1800.0, 3600.0, 5400.0, 7200.0, 9000.0]
        expected_nbv = [8200.0, 6400.0, 4600.0, 2800.0, 1000.0]
        for idx, line in enumerate(sorted_lines):
            self.assertAlmostEqual(
                line.cumulative_depreciation,
                expected_cumulative[idx],
                places=2,
                msg=(
                    f'Line idx={idx} cumulative must be '
                    f'{expected_cumulative[idx]:.2f}; got '
                    f'{line.cumulative_depreciation:.2f}.'
                ),
            )
            self.assertAlmostEqual(
                line.net_book_value,
                expected_nbv[idx],
                places=2,
                msg=(
                    f'Line idx={idx} NBV must be '
                    f'{expected_nbv[idx]:.2f}; got '
                    f'{line.net_book_value:.2f}.'
                ),
            )

        # Final NBV equals salvage_value, not zero.
        self.assertAlmostEqual(
            sorted_lines[-1].net_book_value,
            asset.salvage_value,
            places=2,
            msg='Final line NBV must equal salvage_value (1000.00).',
        )

    # =========================================================================
    # T-AM-002-02: Straight-line depreciation in MONTHS
    # =========================================================================

    def test_am_002_02_straight_line_months(self):
        """T-AM-002-02: Straight-line by MONTHS: cost $10,000, salvage $1,000, 36 months -> $250/month * 36.

        Verifies AM-002 Scenario 2: configuring straight-line
        depreciation with useful life expressed in months produces a
        schedule with exactly ``useful_life_months`` lines at
        ``(acquisition_cost - salvage_value) / useful_life_months``
        per line, and the cumulative schedule sums to depreciable
        base = 9000.00.

        Formula: monthly_dep = (10000 - 1000) / 36 = 250.00
        """
        asset = self._create_basic_asset(
            self,
            name='AM-002-02 Straight-Line Months',
            acquisition_cost=10000.0,
            salvage_value=1000.0,
            depreciation_method='straight_line',
            useful_life_unit='months',
            useful_life_months=36,
            useful_life_years=0,
            acquisition_date=date(2024, 1, 1),
            start_date_option='acquisition_date',
        )
        asset.action_confirm()

        # Schedule has exactly 36 lines (one per month).
        self.assertEqual(
            len(asset.depreciation_line_ids),
            36,
            'Straight-line 36-month schedule must have 36 lines.',
        )

        # All lines have monthly amount = 250.00.
        # 250 * 36 = 9000 exactly so no rounding residual.
        sorted_lines = asset.depreciation_line_ids.sorted('sequence')
        for line in sorted_lines:
            self.assertAlmostEqual(
                line.depreciation_amount,
                250.0,
                places=2,
                msg=(
                    f'Line at sequence={line.sequence} amount must '
                    f'equal 250.00; got {line.depreciation_amount:.2f}.'
                ),
            )

        # Total = 9000.00 (acquisition_cost - salvage_value).
        total = sum(asset.depreciation_line_ids.mapped(
            'depreciation_amount',
        ))
        self.assertAlmostEqual(
            total,
            9000.0,
            places=2,
            msg=(
                f'Schedule total must equal 9000.00; got {total:.2f}.'
            ),
        )

        # Final NBV converges to salvage_value (1000.00, NOT zero).
        self.assertAlmostEqual(
            sorted_lines[-1].net_book_value,
            1000.0,
            places=2,
            msg='Final line NBV must equal salvage_value (1000.00).',
        )

        # Aggregate computed fields on the asset itself: with NO
        # posted lines, accumulated_depreciation == 0.0 and
        # net_book_value == acquisition_cost. The aggregate
        # ``accumulated_depreciation`` field on the asset is the
        # sum across POSTED lines only (state == 'posted'); all
        # 36 lines are in 'draft' state so the sum is 0.
        self.assertAlmostEqual(
            asset.accumulated_depreciation,
            0.0,
            places=2,
            msg=(
                'Asset.accumulated_depreciation must be 0.0 when '
                'no lines are posted (all draft).'
            ),
        )
        self.assertAlmostEqual(
            asset.net_book_value,
            asset.acquisition_cost,
            places=2,
            msg=(
                'Asset.net_book_value must equal acquisition_cost '
                'when no lines are posted.'
            ),
        )

        # Sequence ordering: 1..36, no gaps.
        sequences = sorted_lines.mapped('sequence')
        self.assertEqual(
            sequences,
            list(range(1, 37)),
            'Sequences must be 1..36 in order.',
        )

        # Line dates advance monthly via relativedelta.
        sorted_by_date = sorted_lines.mapped('depreciation_date')
        for i in range(1, len(sorted_by_date)):
            prior = sorted_by_date[i - 1]
            current = sorted_by_date[i]
            self.assertEqual(
                current,
                prior + relativedelta(months=+1),
                f'Line dates must advance by relativedelta(months=+1); '
                f'got {prior} -> {current}.',
            )

    # =========================================================================
    # T-AM-002-03: Declining-balance Year 1
    # =========================================================================

    def test_am_002_03_declining_balance_year_1(self):
        """T-AM-002-03: Declining balance Y1: cost $10,000, factor 2.0, life 5y -> $4,000.

        Verifies AM-002 Scenario 3: configuring declining-balance
        depreciation with the canonical double-declining-balance
        configuration (factor=2.0, life=5y) yields a Year-1
        depreciation of cost * (factor / life) = 10000 * 0.4 =
        4000.00. The remaining NBV after Year 1 equals 6000.00.

        Per the AM-002 ticket Scenario 3 ("Rate: 40%") and the
        Appendix's "Double Declining Balance" formula
        ``Rate = 2 / Useful Life``, ``declining_factor=2.0`` with a
        5-year life produces an effective rate of 40%, matching the
        ticket's Year-1 expectation of $4,000 on a $10,000 asset.
        """
        asset = self._create_basic_asset(
            self,
            name='AM-002-03 Declining Balance Y1',
            acquisition_cost=10000.0,
            salvage_value=0.0,
            depreciation_method='declining_balance',
            useful_life_unit='years',
            useful_life_years=5,
            useful_life_months=0,
            declining_factor=2.0,
            switch_to_straight_line=False,
            acquisition_date=date(2024, 1, 1),
            start_date_option='acquisition_date',
        )
        asset.action_confirm()

        # Schedule has 5 lines (one per year of useful life).
        self.assertEqual(
            len(asset.depreciation_line_ids),
            5,
            'Declining-balance 5-year schedule must have 5 lines.',
        )

        sorted_lines = asset.depreciation_line_ids.sorted('sequence')

        # Year 1 amount = cost * (factor / life) = 10000 * 0.4 = 4000.
        # Verify the test expectation by computing it inline.
        expected_y1 = 10000.0 * (2.0 / 5)
        self.assertAlmostEqual(
            expected_y1,
            4000.0,
            places=2,
            msg='Sanity: 10000 * (2/5) must equal 4000.00.',
        )

        # First (Year 1) depreciation line amount equals the
        # declining-balance Year 1 calculation.
        self.assertAlmostEqual(
            sorted_lines[0].depreciation_amount,
            4000.0,
            places=2,
            msg=(
                f'Year 1 depreciation must be 4000.00; got '
                f'{sorted_lines[0].depreciation_amount:.2f}.'
            ),
        )

        # NBV after Year 1 = 10000 - 4000 = 6000.00.
        self.assertAlmostEqual(
            sorted_lines[0].net_book_value,
            6000.0,
            places=2,
            msg=(
                f'NBV after Year 1 must be 6000.00; got '
                f'{sorted_lines[0].net_book_value:.2f}.'
            ),
        )

        # Year 1 cumulative_depreciation = 4000.00.
        self.assertAlmostEqual(
            sorted_lines[0].cumulative_depreciation,
            4000.0,
            places=2,
            msg='Year 1 cumulative must equal 4000.00.',
        )

    # =========================================================================
    # T-AM-002-04: Declining-balance Year 2
    # =========================================================================

    def test_am_002_04_declining_balance_year_2(self):
        """T-AM-002-04: Declining balance Y2: NBV $6,000 * 40% -> $2,400.

        Verifies the recursive declining-balance behavior: after
        Year 1 reduces NBV from 10000 to 6000, the Year 2
        depreciation equals 6000 * (factor / life) = 6000 * 0.4 =
        2400.00, leaving NBV = 3600.00 at end of Year 2.

        Also verifies the schedule total invariant: the sum of all
        per-period amounts equals the depreciable base (cost -
        salvage = 10000.00 with salvage=0).
        """
        asset = self._create_basic_asset(
            self,
            name='AM-002-04 Declining Balance Y2',
            acquisition_cost=10000.0,
            salvage_value=0.0,
            depreciation_method='declining_balance',
            useful_life_unit='years',
            useful_life_years=5,
            useful_life_months=0,
            declining_factor=2.0,
            switch_to_straight_line=False,
            acquisition_date=date(2024, 1, 1),
            start_date_option='acquisition_date',
        )
        asset.action_confirm()

        sorted_lines = asset.depreciation_line_ids.sorted('sequence')

        # Year 2 (index 1) amount = 6000 * 0.4 = 2400.
        expected_y2 = 6000.0 * (2.0 / 5)
        self.assertAlmostEqual(
            expected_y2,
            2400.0,
            places=2,
            msg='Sanity: 6000 * (2/5) must equal 2400.00.',
        )

        self.assertAlmostEqual(
            sorted_lines[1].depreciation_amount,
            2400.0,
            places=2,
            msg=(
                f'Year 2 depreciation must be 2400.00; got '
                f'{sorted_lines[1].depreciation_amount:.2f}.'
            ),
        )

        # NBV after Year 2 = 6000 - 2400 = 3600.00.
        self.assertAlmostEqual(
            sorted_lines[1].net_book_value,
            3600.0,
            places=2,
            msg=(
                f'NBV after Year 2 must be 3600.00; got '
                f'{sorted_lines[1].net_book_value:.2f}.'
            ),
        )

        # Year 2 cumulative_depreciation = 4000 + 2400 = 6400.00.
        self.assertAlmostEqual(
            sorted_lines[1].cumulative_depreciation,
            6400.0,
            places=2,
            msg='Year 2 cumulative must equal 6400.00.',
        )

        # Total schedule sums to depreciable base (cost - salvage).
        # Without switch_to_straight_line, the model's
        # _schedule_declining_balance forces the FINAL line to
        # absorb the rounding residual so the sum equals exactly
        # 10000.00 (depreciable = 10000 - 0 = 10000). The early-
        # year amounts are 4000, 2400, 1440, 864 (cumulative
        # 8704), so the final residual line is 10000 - 8704 =
        # 1296.00. The implementation may slightly differ but the
        # invariant ``sum == depreciable_base`` always holds.
        depreciable = (
            asset.acquisition_cost - asset.salvage_value
        )
        total = sum(asset.depreciation_line_ids.mapped(
            'depreciation_amount',
        ))
        self.assertAlmostEqual(
            total,
            depreciable,
            places=2,
            msg=(
                f'Schedule total must equal depreciable base '
                f'{depreciable:.2f}; got {total:.2f}.'
            ),
        )

    # =========================================================================
    # T-AM-002-05: Declining-balance with SWITCH to straight-line
    # =========================================================================

    def test_am_002_05_declining_balance_switch_to_sl(self):
        """T-AM-002-05: Declining balance with switch_to_straight_line=True.

        Verifies AM-002 Scenario 3 optimal-crossover behavior: when
        ``switch_to_straight_line=True``, the schedule switches to
        straight-line on the remaining NBV at the FIRST period where
        the SL amount on the remaining periods exceeds the
        declining-balance amount. This guarantees the asset is fully
        depreciated by end of useful life.

        Reference computation::

            nbv = 10000.0
            factor = 2.0 / 5  # 40%
            for year in range(1, 6):
                remaining_years = 5 - year + 1
                db_amount = nbv * factor
                sl_amount = nbv / remaining_years
                amt = max(db_amount, sl_amount)  # switch when SL is higher
                nbv -= amt

        Yields:
            Y1: 4000.00, Y2: 2400.00, Y3: 1440.00, Y4: 1080.00, Y5: 1080.00
        (the last two years are equal because SL kicked in at Y4 once
        SL > DB on the residual NBV).

        The schedule MUST sum to exactly 10000.00 (depreciable base
        with salvage_value=0) and the late-year amounts MUST be
        equal indicating the switch-to-SL kicked in.
        """
        asset = self._create_basic_asset(
            self,
            name='AM-002-05 Declining Balance Switch SL',
            acquisition_cost=10000.0,
            salvage_value=0.0,
            depreciation_method='declining_balance',
            useful_life_unit='years',
            useful_life_years=5,
            useful_life_months=0,
            declining_factor=2.0,
            switch_to_straight_line=True,
            acquisition_date=date(2024, 1, 1),
            start_date_option='acquisition_date',
        )
        asset.action_confirm()

        # Schedule has 5 lines.
        self.assertEqual(
            len(asset.depreciation_line_ids),
            5,
            'Switch-to-SL declining-balance schedule must have 5 lines.',
        )

        sorted_lines = asset.depreciation_line_ids.sorted('sequence')

        # Compute expected schedule using the same algorithm as
        # the model (per agent_prompt reference computation).
        # The model rounds each per-period amount to currency
        # precision and absorbs the cumulative rounding residual
        # in the FINAL period.
        currency = asset.currency_id
        depreciable = (
            asset.acquisition_cost - asset.salvage_value
        )
        total_periods = 5
        rate = 2.0 / total_periods
        expected = []
        cumulative = 0.0
        switched = False
        for sequence in range(1, total_periods + 1):
            book_value = asset.acquisition_cost - cumulative
            remaining = book_value - asset.salvage_value
            if remaining <= 0:
                break
            db_amount = currency.round(book_value * rate)
            remaining_periods = total_periods - sequence + 1
            if not switched and remaining_periods > 0:
                sl_amount = currency.round(remaining / remaining_periods)
                if sl_amount > db_amount:
                    switched = True
            if switched:
                amt = currency.round(remaining / remaining_periods)
            else:
                amt = db_amount
            amt = min(amt, remaining)
            if sequence == total_periods:
                amt = currency.round(depreciable - cumulative)
            cumulative += amt
            expected.append(amt)

        # Element-wise comparison with the model's actual output.
        self.assertEqual(
            len(sorted_lines),
            len(expected),
            'Expected and actual schedule lengths must match.',
        )
        for i, expected_amt in enumerate(expected):
            self.assertAlmostEqual(
                sorted_lines[i].depreciation_amount,
                expected_amt,
                places=2,
                msg=(
                    f'Line at sequence={i + 1} amount must be '
                    f'{expected_amt:.2f}; got '
                    f'{sorted_lines[i].depreciation_amount:.2f}.'
                ),
            )

        # The full schedule sums to depreciable base.
        total = sum(asset.depreciation_line_ids.mapped(
            'depreciation_amount',
        ))
        self.assertAlmostEqual(
            total,
            depreciable,
            places=2,
            msg=(
                f'Switch-to-SL schedule total must equal '
                f'depreciable base {depreciable:.2f}; got '
                f'{total:.2f}.'
            ),
        )

        # Late-year amounts are equal (within rounding tolerance):
        # once the switch-to-SL has triggered, all remaining
        # periods use the same straight-line amount on the
        # remaining NBV. Verify the LAST TWO line amounts differ
        # by less than 0.01 (currency precision).
        last_two_diff = abs(
            sorted_lines[-1].depreciation_amount
            - sorted_lines[-2].depreciation_amount,
        )
        self.assertLess(
            last_two_diff,
            0.01,
            f'Last two line amounts must be equal (within 0.01) '
            f'after switch-to-SL; got difference={last_two_diff:.4f}.',
        )

    # =========================================================================
    # T-AM-002-06: Units-of-production
    # =========================================================================

    def test_am_002_06_units_of_production(self):
        """T-AM-002-06: Units-of-production: $10K cost, $1K salvage, 100K units -> $0.09/unit.

        Verifies AM-002 Scenario 4: the units-of-production method
        uses the per-unit rate formula::

            unit_rate = (cost - salvage) / total_units
                      = (10000 - 1000) / 100000
                      = 0.09

        The implementation creates a single placeholder schedule line
        at confirmation (because actual production data is not known
        at that time); production-event entries are appended later
        as ``units_production_to_date`` advances. The test verifies:

            1. The rate formula produces 0.09 from the configured
               fields.
            2. ``units_production_to_date`` is writable and starts
               at 0.0.
            3. The placeholder schedule line is created on
               confirmation.
            4. Updating ``units_production_to_date`` is permitted by
               the ORM (a sanity check on the field definition).
        """
        asset = self._create_basic_asset(
            self,
            name='AM-002-06 Units of Production',
            acquisition_cost=10000.0,
            salvage_value=1000.0,
            depreciation_method='units_of_production',
            useful_life_unit='units',
            useful_life_years=0,
            useful_life_months=0,
            units_production_total=100000.0,
            acquisition_date=date(2024, 1, 1),
            start_date_option='acquisition_date',
        )

        # Pre-confirm: the rate formula is computable from the
        # configured field values.
        expected_rate = (
            (asset.acquisition_cost - asset.salvage_value)
            / asset.units_production_total
        )
        self.assertAlmostEqual(
            expected_rate,
            0.09,
            places=4,
            msg=(
                f'Per-unit rate must be 0.09; got {expected_rate:.4f}.'
            ),
        )

        # ``units_production_to_date`` defaults to 0.0.
        self.assertAlmostEqual(
            asset.units_production_to_date,
            0.0,
            places=2,
            msg=(
                'units_production_to_date must default to 0.0; got '
                f'{asset.units_production_to_date:.2f}.'
            ),
        )

        # Confirm the asset; this triggers schedule generation via
        # ``_schedule_units_of_production`` which creates a single
        # placeholder line (per the model docstring).
        asset.action_confirm()

        # The placeholder line exists.
        self.assertEqual(
            len(asset.depreciation_line_ids),
            1,
            'units_of_production schedule must have exactly 1 '
            'placeholder line on confirmation.',
        )

        # The placeholder line has zero amount and the configured
        # depreciation_start_date as its date.
        placeholder = asset.depreciation_line_ids[0]
        self.assertAlmostEqual(
            placeholder.depreciation_amount,
            0.0,
            places=2,
            msg=(
                f'Placeholder line amount must be 0.0; got '
                f'{placeholder.depreciation_amount:.2f}.'
            ),
        )
        self.assertEqual(
            placeholder.depreciation_date,
            asset.depreciation_start_date,
            'Placeholder line date must equal '
            'asset.depreciation_start_date.',
        )
        self.assertEqual(
            placeholder.sequence,
            1,
            'Placeholder line sequence must equal 1.',
        )

        # ``units_production_to_date`` is writable -- update it and
        # re-read to confirm the value persists.
        asset.units_production_to_date = 50000.0
        self.assertAlmostEqual(
            asset.units_production_to_date,
            50000.0,
            places=2,
            msg=(
                'units_production_to_date must be writable; new '
                'value 50000.0 must persist.'
            ),
        )

    # =========================================================================
    # T-AM-002-07: Start date 'acquisition_date'
    # =========================================================================

    def test_am_002_07_start_date_acquisition(self):
        """T-AM-002-07: start_date_option='acquisition_date' -> schedule begins on acquisition_date.

        Verifies AM-002 Scenario 5 / acquisition_date branch of
        ``_resolve_depreciation_start_date``: the depreciation
        start date equals the acquisition date exactly.
        """
        asset = self._create_basic_asset(
            self,
            name='AM-002-07 Start Date Acquisition',
            acquisition_cost=12000.0,
            salvage_value=0.0,
            depreciation_method='straight_line',
            useful_life_unit='years',
            useful_life_years=4,
            useful_life_months=0,
            acquisition_date=date(2024, 1, 15),
            start_date_option='acquisition_date',
        )
        asset.action_confirm()

        # depreciation_start_date == acquisition_date.
        self.assertEqual(
            asset.depreciation_start_date,
            date(2024, 1, 15),
            f'depreciation_start_date must equal acquisition_date '
            f'2024-01-15; got {asset.depreciation_start_date}.',
        )

        # First depreciation line falls on the resolved start date.
        sorted_lines = asset.depreciation_line_ids.sorted('sequence')
        self.assertTrue(
            sorted_lines,
            'Schedule must have at least one line.',
        )
        self.assertEqual(
            sorted_lines[0].depreciation_date,
            date(2024, 1, 15),
            f'First line depreciation_date must equal '
            f'2024-01-15; got {sorted_lines[0].depreciation_date}.',
        )

    # =========================================================================
    # T-AM-002-08: Start date 'first_day_next_month'
    # =========================================================================

    def test_am_002_08_start_date_next_month(self):
        """T-AM-002-08: start_date_option='first_day_next_month' -> schedule starts 1st of next month.

        Verifies AM-002 Scenario 5 / first_day_next_month branch of
        ``_resolve_depreciation_start_date``: for an acquisition
        date of 2024-01-15, the depreciation start date must be
        2024-02-01 (the first day of the next month).
        """
        asset = self._create_basic_asset(
            self,
            name='AM-002-08 Start Date Next Month',
            acquisition_cost=12000.0,
            salvage_value=0.0,
            depreciation_method='straight_line',
            useful_life_unit='years',
            useful_life_years=4,
            useful_life_months=0,
            acquisition_date=date(2024, 1, 15),
            start_date_option='first_day_next_month',
        )
        asset.action_confirm()

        # depreciation_start_date == first day of the month
        # following acquisition_date.
        self.assertEqual(
            asset.depreciation_start_date,
            date(2024, 2, 1),
            f'depreciation_start_date for first_day_next_month '
            f'must be 2024-02-01; got {asset.depreciation_start_date}.',
        )

        # First depreciation line falls on the resolved start date.
        sorted_lines = asset.depreciation_line_ids.sorted('sequence')
        self.assertEqual(
            sorted_lines[0].depreciation_date,
            date(2024, 2, 1),
            f'First line depreciation_date must equal '
            f'2024-02-01; got {sorted_lines[0].depreciation_date}.',
        )

    # =========================================================================
    # T-AM-002-09: Start date 'first_day_current_month'
    # =========================================================================

    def test_am_002_09_start_date_current_month(self):
        """T-AM-002-09: start_date_option='first_day_current_month' -> schedule starts 1st of current month.

        Verifies AM-002 Scenario 5 / first_day_current_month branch
        of ``_resolve_depreciation_start_date``: for an acquisition
        date of 2024-01-15, the depreciation start date must be
        2024-01-01 (the first day of the acquisition month).
        """
        asset = self._create_basic_asset(
            self,
            name='AM-002-09 Start Date Current Month',
            acquisition_cost=12000.0,
            salvage_value=0.0,
            depreciation_method='straight_line',
            useful_life_unit='years',
            useful_life_years=4,
            useful_life_months=0,
            acquisition_date=date(2024, 1, 15),
            start_date_option='first_day_current_month',
        )
        asset.action_confirm()

        # depreciation_start_date == first day of the acquisition
        # month.
        self.assertEqual(
            asset.depreciation_start_date,
            date(2024, 1, 1),
            f'depreciation_start_date for first_day_current_month '
            f'must be 2024-01-01; got {asset.depreciation_start_date}.',
        )

        # First depreciation line falls on the resolved start date.
        sorted_lines = asset.depreciation_line_ids.sorted('sequence')
        self.assertEqual(
            sorted_lines[0].depreciation_date,
            date(2024, 1, 1),
            f'First line depreciation_date must equal '
            f'2024-01-01; got {sorted_lines[0].depreciation_date}.',
        )

    # =========================================================================
    # T-AM-002-10: Start date 'manual'
    # =========================================================================

    def test_am_002_10_start_date_manual(self):
        """T-AM-002-10: start_date_option='manual' -> user-specified depreciation_start_date honored.

        Verifies AM-002 Scenario 5 / manual branch of
        ``_resolve_depreciation_start_date``: when
        ``start_date_option='manual'``, the user-supplied
        ``depreciation_start_date`` is preserved and NOT recomputed
        from the acquisition_date. This contrasts with the other
        three options which derive the date from acquisition_date.
        """
        asset = self._create_basic_asset(
            self,
            name='AM-002-10 Start Date Manual',
            acquisition_cost=12000.0,
            salvage_value=0.0,
            depreciation_method='straight_line',
            useful_life_unit='years',
            useful_life_years=4,
            useful_life_months=0,
            acquisition_date=date(2024, 1, 15),
            start_date_option='manual',
            depreciation_start_date=date(2024, 7, 1),
        )
        asset.action_confirm()

        # The manually-specified depreciation_start_date is
        # preserved (NOT overwritten by acquisition_date logic).
        self.assertEqual(
            asset.depreciation_start_date,
            date(2024, 7, 1),
            f'depreciation_start_date for manual option must be '
            f'preserved at 2024-07-01; got '
            f'{asset.depreciation_start_date}.',
        )

        # First depreciation line falls in or after July 2024.
        sorted_lines = asset.depreciation_line_ids.sorted('sequence')
        self.assertGreaterEqual(
            sorted_lines[0].depreciation_date,
            date(2024, 7, 1),
            f'First line date must be in/after July 2024; got '
            f'{sorted_lines[0].depreciation_date}.',
        )

        # The manual start date IGNORES acquisition-date-based
        # logic: even though acquisition_date is 2024-01-15, the
        # schedule starts on 2024-07-01 as specified.
        self.assertEqual(
            sorted_lines[0].depreciation_date,
            date(2024, 7, 1),
            f'First line date must equal manual start date '
            f'2024-07-01 (ignoring acquisition_date); got '
            f'{sorted_lines[0].depreciation_date}.',
        )

    # =========================================================================
    # T-AM-002-11: Category template propagation via onchange
    # =========================================================================

    def test_am_002_11_category_template_propagation(self):
        """T-AM-002-11: Category template defaults propagate via _onchange_category_id (overridable).

        Verifies AM-002 Scenario 6 and AM-001 Scenario 3 / AC3:
        selecting a category on a draft asset propagates the
        category's default depreciation method, useful life, and
        account assignments via ``_onchange_category_id``. Then
        verifies that user overrides applied AFTER the onchange
        persist (the onchange does NOT revert user edits per
        AM-001 AC3).

        The fixture ``self.asset_category_it`` (set up in
        ``AssetManagementTestCommon.setUpClass``) is a 3-year
        straight-line "IT Equipment" category with all four
        accounts (asset, expense, accumulated, journal) configured.
        """
        # Phase 1: create a draft asset via .new() with the category
        # selected, then invoke _onchange_category_id manually to
        # simulate the form-level UX (Odoo's onchange fires only on
        # web-form interaction; in tests we simulate it explicitly).
        new_asset = self.env['account.asset'].new({
            'name': 'Dev Machine',
            'acquisition_date': date(2024, 3, 15),
            'acquisition_cost': 2500.0,
            'category_id': self.asset_category_it.id,
        })
        new_asset._onchange_category_id()

        # Phase 1 assertions: category-level defaults propagate.
        self.assertEqual(
            new_asset.depreciation_method,
            self.asset_category_it.depreciation_method,
            'depreciation_method must inherit from category '
            f'(expected {self.asset_category_it.depreciation_method}; '
            f'got {new_asset.depreciation_method}).',
        )
        self.assertEqual(
            new_asset.useful_life_unit,
            self.asset_category_it.useful_life_unit,
            'useful_life_unit must inherit from category '
            f'(expected {self.asset_category_it.useful_life_unit}; '
            f'got {new_asset.useful_life_unit}).',
        )
        self.assertEqual(
            new_asset.useful_life_years,
            self.asset_category_it.useful_life_years,
            'useful_life_years must inherit from category '
            f'(expected {self.asset_category_it.useful_life_years}; '
            f'got {new_asset.useful_life_years}).',
        )
        self.assertEqual(
            new_asset.start_date_option,
            self.asset_category_it.start_date_option,
            'start_date_option must inherit from category '
            f'(expected {self.asset_category_it.start_date_option}; '
            f'got {new_asset.start_date_option}).',
        )
        self.assertEqual(
            new_asset.asset_account_id,
            self.asset_category_it.asset_account_id,
            'asset_account_id must inherit from category.',
        )
        self.assertEqual(
            new_asset.expense_account_id,
            self.asset_category_it.expense_account_id,
            'expense_account_id must inherit from category.',
        )
        self.assertEqual(
            new_asset.accumulated_depreciation_account_id,
            self.asset_category_it.accumulated_depreciation_account_id,
            'accumulated_depreciation_account_id must inherit '
            'from category.',
        )
        self.assertEqual(
            new_asset.journal_id,
            self.asset_category_it.journal_id,
            'journal_id must inherit from category.',
        )

        # Phase 2: user override -- change useful_life_years from
        # the category default (3) to a custom value (5). After
        # the override is applied, the value MUST persist on the
        # in-memory record (no implicit re-firing of the onchange
        # in the absence of a category_id change).
        new_asset.useful_life_years = 5
        self.assertEqual(
            new_asset.useful_life_years,
            5,
            'User-overridden useful_life_years must persist '
            'immediately after assignment (expected 5).',
        )

        # Phase 3: persist the in-memory record to the database
        # and re-read it to confirm the override survives a save.
        # ``new_asset`` is an in-memory NewId record produced by
        # ``self.env['account.asset'].new(...)``; we cannot directly
        # call ``.save()`` on it. Instead, we ``create()`` a real
        # persistent record carrying the same field values
        # (including the user override of ``useful_life_years=5``)
        # to simulate the "form save" step. Re-reading the record
        # via ``invalidate_recordset()`` then verifies the override
        # round-trips through the ORM correctly (no DB-level
        # default reversion).
        persisted_asset = self.env['account.asset'].create({
            'name': 'Dev Machine Persistent',
            'acquisition_date': date(2024, 3, 15),
            'acquisition_cost': 2500.0,
            'category_id': self.asset_category_it.id,
            'depreciation_method': new_asset.depreciation_method,
            'useful_life_unit': new_asset.useful_life_unit,
            'useful_life_years': 5,  # user override persists
            'start_date_option': new_asset.start_date_option,
            'asset_account_id': new_asset.asset_account_id.id,
            'expense_account_id': new_asset.expense_account_id.id,
            'accumulated_depreciation_account_id': (
                new_asset.accumulated_depreciation_account_id.id
            ),
            'journal_id': new_asset.journal_id.id,
        })
        persisted_asset.invalidate_recordset()
        self.assertEqual(
            persisted_asset.useful_life_years,
            5,
            'After save and re-read, useful_life_years override (5) '
            'must persist; got '
            f'{persisted_asset.useful_life_years}.',
        )

    # =========================================================================
    # T-AM-002-12: Configuration validation
    # =========================================================================

    def test_am_002_12_configuration_validation(self):
        """T-AM-002-12: Invalid configuration combinations are rejected with ValidationError.

        Verifies AM-002 Scenario 7 (configuration validation): the
        ``@api.constrains`` validators on ``account.asset`` reject
        every documented invalid combination with a ValidationError.
        Each sub-case is wrapped in ``self.subTest(...)`` for
        per-case test isolation and in
        ``self.env.cr.savepoint()`` for transaction isolation so
        that a constraint failure in one case does not corrupt the
        DB cursor for subsequent cases.

        Sub-cases tested:

            1. useful_life_years < 0 (declining_balance method,
               unit=years) -> _check_depreciation_config (the
               concrete catch happens via the <=0 check). However
               the model also validates inside
               _check_useful_life on the category... For the
               asset-level model, the actual @api.constrains is
               _check_depreciation_config which catches
               useful_life_years <= 0 for time-based methods.
            2. declining_factor < 0 with declining_balance method
               -> _check_declining_factor.
            3. salvage_value > acquisition_cost ->
               _check_salvage_value.
            4. salvage_value < 0 -> _check_salvage_value.
            5. method=declining_balance, declining_factor=0 ->
               _check_declining_factor.
            6. method=units_of_production,
               units_production_total<=0 ->
               _check_depreciation_config.
            7. method=straight_line, useful_life_unit='years',
               useful_life_years=0 ->
               _check_depreciation_config.
            8. method=straight_line, useful_life_unit='months',
               useful_life_months=0 ->
               _check_depreciation_config.

        Each sub-case is scoped to a SAVEPOINT-wrapped transaction
        so that a ValidationError raised by ``create`` does NOT
        corrupt the DB state for subsequent sub-cases.
        """
        # Sub-cases: (descriptive_name, asset-create overrides, expected exception class).
        # All cases use ``_create_basic_asset`` to inherit valid
        # defaults, then override the specific fields under test.
        cases = [
            # 1. Negative useful_life_years for a time-based
            #    declining-balance method (caught by
            #    _check_depreciation_config: useful_life_years <= 0).
            (
                'declining_balance_negative_useful_life_years',
                {
                    'depreciation_method': 'declining_balance',
                    'useful_life_unit': 'years',
                    'useful_life_years': -3,
                    'declining_factor': 2.0,
                },
                ValidationError,
            ),
            # 2. Negative declining_factor with declining-balance
            #    method (caught by _check_declining_factor).
            (
                'declining_factor_negative',
                {
                    'depreciation_method': 'declining_balance',
                    'useful_life_unit': 'years',
                    'useful_life_years': 5,
                    'declining_factor': -0.5,
                },
                ValidationError,
            ),
            # 3. Salvage > cost (caught by _check_salvage_value).
            (
                'salvage_exceeds_cost',
                {
                    'acquisition_cost': 1000.0,
                    'salvage_value': 1500.0,
                    'depreciation_method': 'straight_line',
                    'useful_life_unit': 'years',
                    'useful_life_years': 5,
                },
                ValidationError,
            ),
            # 4. Salvage < 0 (caught by _check_salvage_value).
            (
                'salvage_negative',
                {
                    'acquisition_cost': 1000.0,
                    'salvage_value': -100.0,
                    'depreciation_method': 'straight_line',
                    'useful_life_unit': 'years',
                    'useful_life_years': 5,
                },
                ValidationError,
            ),
            # 5. Method=declining_balance, declining_factor=0
            #    (caught by _check_declining_factor).
            (
                'declining_factor_zero',
                {
                    'depreciation_method': 'declining_balance',
                    'useful_life_unit': 'years',
                    'useful_life_years': 5,
                    'declining_factor': 0.0,
                },
                ValidationError,
            ),
            # 6. Method=units_of_production, units_production_total<=0
            #    (caught by _check_depreciation_config).
            (
                'units_of_production_zero_total',
                {
                    'depreciation_method': 'units_of_production',
                    'useful_life_unit': 'units',
                    'useful_life_years': 0,
                    'useful_life_months': 0,
                    'units_production_total': 0.0,
                },
                ValidationError,
            ),
            # 7. method=straight_line, useful_life_unit='years',
            #    useful_life_years=0 (caught by
            #    _check_depreciation_config).
            (
                'straight_line_years_zero',
                {
                    'depreciation_method': 'straight_line',
                    'useful_life_unit': 'years',
                    'useful_life_years': 0,
                    'useful_life_months': 0,
                },
                ValidationError,
            ),
            # 8. method=straight_line, useful_life_unit='months',
            #    useful_life_months=0 (caught by
            #    _check_depreciation_config).
            (
                'straight_line_months_zero',
                {
                    'depreciation_method': 'straight_line',
                    'useful_life_unit': 'months',
                    'useful_life_years': 0,
                    'useful_life_months': 0,
                },
                ValidationError,
            ),
        ]

        for name, overrides, exc_class in cases:
            # Each sub-case runs inside a SAVEPOINT so that a
            # raised ValidationError does NOT corrupt the
            # transaction for subsequent sub-cases. The
            # ``with self.subTest(...)`` block also ensures that
            # if one sub-case fails, the test runner reports
            # which one (rather than aborting on the first
            # failure).
            with self.subTest(case=name), self.env.cr.savepoint():
                with self.assertRaises(
                    exc_class,
                    msg=(
                        f'Sub-case "{name}" must raise '
                        f'{exc_class.__name__}; overrides='
                        f'{overrides}.'
                    ),
                ):
                    self._create_basic_asset(self, **overrides)
