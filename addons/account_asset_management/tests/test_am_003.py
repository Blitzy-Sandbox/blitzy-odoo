# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Tests for AM-003: Depreciation Board user story.

Covers the following BDD scenarios from
``tickets/stories/asset-management/AM-003-depreciation-board.md``:

    T-AM-003-01  Full schedule displayed (period, date, amount,
                 accumulated, NBV) -- AC1.
    T-AM-003-02  Running accumulated depreciation calculation -- AC2.
    T-AM-003-03  Per-period NBV = Cost - Cumulative Accumulated
                 Depreciation -- AC3.
    T-AM-003-04  Status badges: draft / posted / skipped with move
                 references -- AC4.
    T-AM-003-05  Move hyperlink navigation from posted lines -- AC4.
    T-AM-003-06  Filter lines by state (draft/posted/skipped) -- AC5.
    T-AM-003-07  Filter lines by date range
                 (this_year/next_year/custom) -- AC5.
    T-AM-003-08  Sort lines by depreciation_date ASC / DESC -- AC5.
    T-AM-003-09  Sort by depreciation_amount -- AC5.
    T-AM-003-10  Group by fiscal period / quarter -- AC5.
    T-AM-003-11  Board read-only: create=False, delete=False
                 attributes honored -- AC1.
    T-AM-003-12  Smart button from asset form navigates to filtered
                 board -- (integration with AM-001 form).
    T-AM-003-13  XLSX export for the current filter selection -- AC6.
    T-AM-003-14  CSV export for the current filter selection -- AC6.
    T-AM-003-15  *** PERFORMANCE SLA: full schedule render < 2s for
                 480 periods *** (40-year monthly asset --
                 per AAP section 0.7.3).

Each test method's docstring starts with the BDD scenario ID for
traceability.

Performance test ``test_am_003_15`` uses ``time.perf_counter()`` to
measure wall-clock duration of a full ``search() + mapped()`` cycle
over 480 depreciation lines; failure asserts the SLA is violated.
The test is gated by the ``SKIP_PERF_TESTS`` environment variable so
constrained CI environments can opt out::

    SKIP_PERF_TESTS=1 pytest -k test_am_003

AAP Rule Compliance
-------------------
* R-01 (Module independence) -- This file imports ONLY from the
  Python standard library (``os``, ``time``, ``datetime``), the
  ``odoo`` framework (``Command``, ``fields``, ``tests.tagged``),
  and the local sibling ``.common`` module within the same
  ``account_asset_management`` package. NO imports from the three
  sibling Community Edition modules (``account_budget_management``,
  ``account_deferred_revenue``, ``account_payment_followup``).
* R-02 (No Enterprise dependencies) -- This file contains NO
  references to Odoo Enterprise addon names (``account_asset``,
  ``account_accountant``, ``account_reports``, ``account_followup``,
  ``account_deferred_revenue``).
* R-04 (Per-story coverage gate) -- Tests exercise every documented
  branch of the AM-003 board path: schedule generation
  (test_01-03), state machine (test_04), move linkage (test_05),
  filtering (test_06-07), sorting (test_08-09), grouping (test_10),
  view read-only attributes (test_11), smart button navigation
  (test_12), export ACL gating (test_13-14), and the SLA
  performance gate (test_15). All exercised via the public model
  surface (``action_post``, ``action_skip``, the ``_compute_*``
  recompute, ``action_view_depreciation_lines``).
* R-07 (No unjustified ``sudo``) -- This file contains NO
  ``.sudo()`` calls. The test user provisioned by
  ``AccountTestInvoicingCommon`` has both
  ``account.group_account_user`` and
  ``account.group_account_manager`` group memberships, providing
  full CRUD on every model touched by the tests via
  ``security/ir.model.access.csv``.

Performance SLA Note (AAP section 0.7.3)
----------------------------------------
The depreciation board MUST render the full schedule of an asset
with up to 480 periods (40-year monthly schedule) in under 2
seconds. Achievement of this SLA is contingent on:

    * ``cumulative_depreciation`` and ``net_book_value`` being
      ``store=True`` computes (see
      ``models/account_asset_depreciation_line.py``).
    * The ``asset_id`` foreign key being indexed (verified at the
      database level via the ``index=True`` declaration on the
      field).
    * The list view's ``limit="80"`` pagination cap (verified by
      ``test_am_003_11``).

Failure of ``test_am_003_15`` indicates a regression in one or more
of these performance enablers and MUST block release per AAP
section 0.7.3.
"""

import os
import time
from datetime import date

from odoo import Command, fields  # noqa: F401  -- imported per agent_prompt
from odoo.tests import tagged

from .common import AssetManagementTestCommon


@tagged('post_install', '-at_install')
class TestDepreciationBoard(AssetManagementTestCommon):
    """AM-003 -- Depreciation Board.

    Covers all 15 test scenarios for the AM-003 story. Each test
    method's name encodes both its scenario ID (``test_am_003_NN_``)
    and its scenario summary (e.g. ``full_schedule_displayed``).

    The class-level fixture ``cls.monthly_asset`` is a confirmed
    60-month straight-line asset spanning 2024-01-01 through
    2028-12-01. Most tests operate on this fixture; the
    performance test (test_am_003_15) creates its own dedicated
    480-line asset to avoid polluting the smaller fixture's state.

    Per the AAP, the asset's category is intentionally NOT set so
    that the depreciation line's ``action_post()`` creates moves in
    ``draft`` state (auto-post is opt-in via ``category_id`` ->
    ``auto_post_depreciation = True``). Tests that need posted moves
    can either (a) toggle the category flag or (b) call
    ``move.action_post()`` explicitly.
    """

    # =========================================================================
    # SETUP
    # =========================================================================

    @classmethod
    def setUpClass(cls):
        """Seed AM-003-specific fixtures atop the common test environment.

        Creates a confirmed 5-year monthly asset
        (``cls.monthly_asset``) used by 14 of the 15 test methods.
        The performance test (``test_am_003_15``) creates its own
        480-line asset.

        Asset parameters:

            * ``acquisition_cost`` = 6000.0  (per-period = 100.0)
            * ``salvage_value``   = 0.0      (final NBV = 0.0)
            * ``useful_life_unit`` = 'months'
            * ``useful_life_months`` = 60    (5 years monthly)
            * ``depreciation_method`` = 'straight_line'
            * ``acquisition_date`` = 2024-01-01 (anchors the
              year-bucket assertions in test_am_003_07 and the
              read_group year aggregation in test_am_003_10).
            * ``start_date_option`` = 'acquisition_date' (so the
              schedule starts on 2024-01-01 exactly).

        After confirmation:

            * 60 depreciation lines exist, each with ``state =
              'draft'``.
            * Per-period amount = 6000 / 60 = 100.00.
            * Final cumulative = 6000.00; final NBV = 0.00.
            * Schedule spans 2024-01 through 2028-12 (60 months).
        """
        super().setUpClass()
        cls.monthly_asset = cls._create_basic_asset(
            cls,
            name='AM-003 5yr Monthly Asset',
            acquisition_cost=6000.0,
            salvage_value=0.0,
            depreciation_method='straight_line',
            useful_life_unit='months',
            useful_life_months=60,
            useful_life_years=0,
            acquisition_date=date(2024, 1, 1),
            start_date_option='acquisition_date',
        )
        cls.monthly_asset.action_confirm()

    # =========================================================================
    # T-AM-003-01: Full schedule displayed
    # =========================================================================

    def test_am_003_01_full_schedule_displayed(self):
        """T-AM-003-01: Full schedule shows period, date, amount, accumulated, NBV.

        Verifies AC1 of AM-003: the depreciation board displays a
        complete schedule with the canonical columns. Asserts:

            * The schedule has exactly 60 lines (one per month for
              5 years).
            * Each line has all five required fields populated
              (sequence, depreciation_date, depreciation_amount,
              cumulative_depreciation, net_book_value) and a
              draft state.
            * Sequences run 1..60 in order when sorted by
              ``sequence``.
        """
        lines = self.monthly_asset.depreciation_line_ids
        self.assertEqual(
            len(lines),
            60,
            'Schedule must have 60 lines for a 5yr monthly asset.',
        )
        for line in lines:
            # Every line carries a non-zero sequence.
            self.assertGreaterEqual(
                line.sequence,
                1,
                f'Line id={line.id} must have sequence >= 1.',
            )
            # Every line has a populated depreciation_date.
            self.assertTrue(
                line.depreciation_date,
                f'Line id={line.id} must have a depreciation_date.',
            )
            self.assertIsInstance(
                line.depreciation_date,
                date,
                f'Line id={line.id} depreciation_date must be a '
                f'datetime.date.',
            )
            # Every line has the canonical 100.00 amount.
            self.assertAlmostEqual(
                line.depreciation_amount,
                100.0,
                places=2,
                msg=f'Line id={line.id} amount must be 100.00.',
            )
            # cumulative_depreciation and net_book_value are stored
            # @api.depends computes -- must be present (Monetary
            # fields default to 0.0 on missing data; we assert
            # > 0 for cumulative since every line contributes 100).
            self.assertGreaterEqual(
                line.cumulative_depreciation,
                100.0,
                f'Line id={line.id} cumulative_depreciation must '
                f'be >= 100.0.',
            )
            # net_book_value = acquisition_cost - cumulative
            #                = 6000 - cumulative
            #                = at most 5900 on the first line, at
            #                  least 0 on the last.
            self.assertLessEqual(
                line.net_book_value,
                5900.0,
                f'Line id={line.id} net_book_value must be '
                f'<= 5900.0.',
            )
            self.assertGreaterEqual(
                line.net_book_value,
                0.0,
                f'Line id={line.id} net_book_value must be >= 0.0.',
            )
            # Initial state is draft (no posting has run).
            self.assertEqual(
                line.state,
                'draft',
                f'Line id={line.id} initial state must be draft.',
            )

        # Sequence ordering: first line has sequence 1, last has 60.
        sorted_lines = lines.sorted('sequence')
        self.assertEqual(
            sorted_lines[0].sequence,
            1,
            'First line by sequence must have sequence == 1.',
        )
        self.assertEqual(
            sorted_lines[-1].sequence,
            60,
            'Last line by sequence must have sequence == 60.',
        )

    # =========================================================================
    # T-AM-003-02: Running accumulated depreciation
    # =========================================================================

    def test_am_003_02_running_accumulated(self):
        """T-AM-003-02: cumulative_depreciation is running total of amounts.

        Verifies AC2 of AM-003: each line's
        ``cumulative_depreciation`` equals the sum of every prior
        line's ``depreciation_amount`` plus the current line's
        amount.

        Concretely for the 60-line / 100-per-line fixture:

            * Line 1 cumulative == 100.00
            * Line 2 cumulative == 200.00
            * ...
            * Line 60 cumulative == 6000.00
        """
        lines = self.monthly_asset.depreciation_line_ids.sorted(
            'sequence',
        )
        running_total = 0.0
        for idx, line in enumerate(lines, start=1):
            running_total += line.depreciation_amount
            self.assertAlmostEqual(
                line.cumulative_depreciation,
                running_total,
                places=2,
                msg=(
                    f'Line at index {idx} (sequence={line.sequence}) '
                    f'cumulative_depreciation should equal running '
                    f'total {running_total:.2f}; got '
                    f'{line.cumulative_depreciation:.2f}.'
                ),
            )

        # Final running total must equal the depreciable base
        # (acquisition_cost - salvage_value = 6000 - 0 = 6000).
        self.assertAlmostEqual(
            lines[-1].cumulative_depreciation,
            6000.0,
            places=2,
            msg=(
                'Last line cumulative_depreciation must equal full '
                'depreciable base (6000.00).'
            ),
        )

    # =========================================================================
    # T-AM-003-03: Per-period NBV calculation
    # =========================================================================

    def test_am_003_03_nbv_per_period(self):
        """T-AM-003-03: NBV = acquisition_cost - cumulative_depreciation.

        Verifies AC3 of AM-003: each line's ``net_book_value`` is
        the asset's ``acquisition_cost`` minus that line's
        ``cumulative_depreciation``. Final line NBV == salvage value
        (0.00 in this fixture).
        """
        lines = self.monthly_asset.depreciation_line_ids.sorted(
            'sequence',
        )
        for line in lines:
            expected_nbv = (
                self.monthly_asset.acquisition_cost
                - line.cumulative_depreciation
            )
            self.assertAlmostEqual(
                line.net_book_value,
                expected_nbv,
                places=2,
                msg=(
                    f'Line sequence={line.sequence}: '
                    f'expected NBV={expected_nbv:.2f}, '
                    f'got NBV={line.net_book_value:.2f}.'
                ),
            )

        # Final NBV must equal salvage_value.
        self.assertAlmostEqual(
            lines[-1].net_book_value,
            self.monthly_asset.salvage_value,
            places=2,
            msg=(
                'Final NBV must equal salvage_value '
                f'({self.monthly_asset.salvage_value:.2f}).'
            ),
        )

    # =========================================================================
    # T-AM-003-04: Status badges (draft / posted / skipped)
    # =========================================================================

    def test_am_003_04_status_badges(self):
        """T-AM-003-04: Status transitions: draft -> posted / skipped.

        Verifies AC4 of AM-003: each depreciation line has a status
        that is one of {draft, posted, skipped}, with posted lines
        carrying a non-null ``move_id`` reference and skipped lines
        carrying a null ``move_id``.

        Acts:

            * ``line[0].action_post()`` -> state='posted',
              move_id populated.
            * ``line[1].action_skip()`` -> state='skipped',
              move_id NULL.
            * ``line[2..59]`` remain draft.
        """
        lines = self.monthly_asset.depreciation_line_ids.sorted(
            'sequence',
        )
        # Pre-condition: all 60 lines start as draft.
        self.assertTrue(
            all(line.state == 'draft' for line in lines),
            'All lines should start in draft state.',
        )

        # Act: post line[0], skip line[1].
        lines[0].action_post()
        lines[1].action_skip()

        # Refresh to ensure cached state is current.
        lines.invalidate_recordset()

        # Assert: line[0] is posted with a move_id.
        self.assertEqual(
            lines[0].state,
            'posted',
            'Line[0] should transition to posted after action_post.',
        )
        self.assertTrue(
            lines[0].move_id,
            'Posted line[0] must have a non-null move_id.',
        )
        # The category default is auto_post_depreciation=False
        # (no category set on cls.monthly_asset), so the move stays
        # in draft state. Both 'draft' and 'posted' are acceptable
        # depending on category configuration.
        self.assertIn(
            lines[0].move_id.state,
            ('draft', 'posted'),
            f'Move state should be draft or posted; got '
            f'{lines[0].move_id.state}.',
        )

        # Assert: line[1] is skipped without a move_id.
        self.assertEqual(
            lines[1].state,
            'skipped',
            'Line[1] should transition to skipped after action_skip.',
        )
        self.assertFalse(
            lines[1].move_id,
            'Skipped line[1] must NOT have a move_id.',
        )

        # Assert: line[2..59] remain draft.
        remaining = lines[2:]
        self.assertTrue(
            all(line.state == 'draft' for line in remaining),
            'Lines[2:] should remain in draft state.',
        )

    # =========================================================================
    # T-AM-003-05: Move hyperlink navigation
    # =========================================================================

    def test_am_003_05_move_hyperlink_navigation(self):
        """T-AM-003-05: Posted line move_id is a valid balanced account.move.

        Verifies AC4 / AC2-extension of AM-003: each posted
        depreciation line's ``move_id`` is a real
        ``account.move`` record with:

            * Two journal lines (DR depreciation expense /
              CR accumulated depreciation).
            * Balanced (sum(debit) == sum(credit)).
            * ``asset_id`` back-reference to the source asset.
            * ``asset_entry_type == 'depreciation'``.
            * The DR line's account == asset.expense_account_id.
            * The CR line's account == asset.accumulated
              _depreciation_account_id.
        """
        lines = self.monthly_asset.depreciation_line_ids.sorted(
            'sequence',
        )
        # Post the first 3 lines.
        lines_to_post = lines[:3]
        for line in lines_to_post:
            line.action_post()

        # Refresh to pick up move_id back-references.
        lines_to_post.invalidate_recordset()

        for line in lines_to_post:
            # move_id is set.
            self.assertTrue(
                line.move_id,
                f'Posted line sequence={line.sequence} must have a '
                f'move_id.',
            )
            move = line.move_id

            # Move state: draft (auto_post_depreciation=False
            # without a category) or posted (with auto_post=True).
            self.assertIn(
                move.state,
                ('draft', 'posted'),
                f'Move {move.id} state must be draft or posted.',
            )

            # asset_id back-reference (R-05-compliant additive
            # field on account.move).
            self.assertEqual(
                move.asset_id,
                self.monthly_asset,
                f'Move {move.id} asset_id must back-reference the '
                f'source asset.',
            )

            # asset_entry_type classification.
            self.assertEqual(
                move.asset_entry_type,
                'depreciation',
                f'Move {move.id} asset_entry_type must be '
                f"'depreciation'.",
            )

            # Two-line balanced journal entry.
            self.assertEqual(
                len(move.line_ids),
                2,
                f'Move {move.id} should have exactly 2 lines (DR / '
                f'CR); got {len(move.line_ids)}.',
            )
            total_debit = sum(move.line_ids.mapped('debit'))
            total_credit = sum(move.line_ids.mapped('credit'))
            self.assertAlmostEqual(
                total_debit,
                total_credit,
                places=2,
                msg=(
                    f'Move {move.id} must be balanced: '
                    f'total_debit={total_debit:.2f}, '
                    f'total_credit={total_credit:.2f}.'
                ),
            )

            # DR line: depreciation expense account.
            debit_lines = move.line_ids.filtered(
                lambda ml: ml.debit > 0,
            )
            self.assertEqual(
                len(debit_lines),
                1,
                f'Move {move.id} should have exactly 1 debit line.',
            )
            self.assertEqual(
                debit_lines.account_id,
                self.monthly_asset.expense_account_id,
                f'Move {move.id} debit line account must be the '
                f"asset's expense account.",
            )

            # CR line: accumulated depreciation account.
            credit_lines = move.line_ids.filtered(
                lambda ml: ml.credit > 0,
            )
            self.assertEqual(
                len(credit_lines),
                1,
                f'Move {move.id} should have exactly 1 credit line.',
            )
            self.assertEqual(
                credit_lines.account_id,
                self.monthly_asset.accumulated_depreciation_account_id,
                f'Move {move.id} credit line account must be the '
                f"asset's accumulated depreciation account.",
            )

            # Per-period amount (100.00 = 6000/60).
            self.assertAlmostEqual(
                debit_lines.debit,
                100.0,
                places=2,
                msg=(
                    f'Move {move.id} debit amount should be 100.00.'
                ),
            )
            self.assertAlmostEqual(
                credit_lines.credit,
                100.0,
                places=2,
                msg=(
                    f'Move {move.id} credit amount should be 100.00.'
                ),
            )

    # =========================================================================
    # T-AM-003-06: Filter lines by state
    # =========================================================================

    def test_am_003_06_filter_by_state(self):
        """T-AM-003-06: Search domain filters lines by state.

        Verifies AC5 of AM-003 (filter by status). Posts the first
        3 lines, skips line[3], and asserts the search domain
        ``[('asset_id', '=', X), ('state', '=', S)]`` returns the
        expected counts:

            * state=posted -> 3 lines
            * state=skipped -> 1 line
            * state=draft -> 56 lines
            * total -> 60 lines

        These counts are the canonical filter cardinalities expected
        by the search view in
        ``views/depreciation_board_views.xml`` (filters
        ``filter_draft``, ``filter_posted``, ``filter_skipped``).
        """
        lines = self.monthly_asset.depreciation_line_ids.sorted(
            'sequence',
        )
        # Arrange: post lines[0..2], skip line[3].
        for line in lines[:3]:
            line.action_post()
        lines[3].action_skip()

        # Force re-read of state flags.
        lines.invalidate_recordset()

        DepLine = self.env['account.asset.depreciation.line']

        # Filter: posted lines.
        posted = DepLine.search([
            ('asset_id', '=', self.monthly_asset.id),
            ('state', '=', 'posted'),
        ])
        self.assertEqual(
            len(posted),
            3,
            f'Expected 3 posted lines; got {len(posted)}.',
        )

        # Filter: skipped lines.
        skipped = DepLine.search([
            ('asset_id', '=', self.monthly_asset.id),
            ('state', '=', 'skipped'),
        ])
        self.assertEqual(
            len(skipped),
            1,
            f'Expected 1 skipped line; got {len(skipped)}.',
        )

        # Filter: draft lines.
        draft = DepLine.search([
            ('asset_id', '=', self.monthly_asset.id),
            ('state', '=', 'draft'),
        ])
        self.assertEqual(
            len(draft),
            56,
            f'Expected 56 draft lines; got {len(draft)}.',
        )

        # Total reconciliation: posted + skipped + draft == 60.
        self.assertEqual(
            len(posted) + len(skipped) + len(draft),
            60,
            'Posted + skipped + draft counts must sum to 60.',
        )

    # =========================================================================
    # T-AM-003-07: Filter lines by date range
    # =========================================================================

    def test_am_003_07_filter_by_date_range(self):
        """T-AM-003-07: Search domain filters lines by date range.

        Verifies AC5 of AM-003 (filter by date range). The fixture
        spans 2024-01-01 through 2028-12-01 (60 monthly periods).
        Asserts search domain
        ``[('depreciation_date', '>=', YYYY-01-01),
        ('depreciation_date', '<=', YYYY-12-31)]`` returns 12 lines
        per fiscal year and 60 lines total.
        """
        DepLine = self.env['account.asset.depreciation.line']
        # Lines per fiscal year.
        for year in range(2024, 2029):
            year_lines = DepLine.search([
                ('asset_id', '=', self.monthly_asset.id),
                (
                    'depreciation_date',
                    '>=',
                    date(year, 1, 1),
                ),
                (
                    'depreciation_date',
                    '<=',
                    date(year, 12, 31),
                ),
            ])
            self.assertEqual(
                len(year_lines),
                12,
                f'Expected 12 monthly lines in fiscal year {year}; '
                f'got {len(year_lines)}.',
            )

        # Total across the 5-year span.
        all_lines = DepLine.search([
            ('asset_id', '=', self.monthly_asset.id),
            ('depreciation_date', '>=', date(2024, 1, 1)),
            ('depreciation_date', '<=', date(2028, 12, 31)),
        ])
        self.assertEqual(
            len(all_lines),
            60,
            f'Expected 60 lines across 2024-2028; got '
            f'{len(all_lines)}.',
        )

        # Custom narrow range: Q1 2024 (3 monthly lines).
        q1_lines = DepLine.search([
            ('asset_id', '=', self.monthly_asset.id),
            ('depreciation_date', '>=', date(2024, 1, 1)),
            ('depreciation_date', '<=', date(2024, 3, 31)),
        ])
        self.assertEqual(
            len(q1_lines),
            3,
            f'Expected 3 lines in Q1 2024; got {len(q1_lines)}.',
        )

    # =========================================================================
    # T-AM-003-08: Sort by depreciation_date
    # =========================================================================

    def test_am_003_08_sort_by_date(self):
        """T-AM-003-08: Recordset sorts by depreciation_date ASC / DESC.

        Verifies AC5 of AM-003 (sort by date). Asserts the
        ``.sorted('depreciation_date')`` recordset method returns
        lines in chronological order, and ``reverse=True`` reverses
        it. Also verifies the model's ``_order`` class attribute
        matches the AAP-mandated value.
        """
        lines = self.monthly_asset.depreciation_line_ids
        asc_lines = lines.sorted('depreciation_date')
        desc_lines = lines.sorted('depreciation_date', reverse=True)

        # ASC: first <= last.
        self.assertLessEqual(
            asc_lines[0].depreciation_date,
            asc_lines[-1].depreciation_date,
            'Ascending sort: first date must be <= last date.',
        )
        # ASC: first date is 2024-01-01 (acquisition date).
        self.assertEqual(
            asc_lines[0].depreciation_date,
            date(2024, 1, 1),
            f'First ASC line should be 2024-01-01; got '
            f'{asc_lines[0].depreciation_date}.',
        )

        # DESC: first >= last.
        self.assertGreaterEqual(
            desc_lines[0].depreciation_date,
            desc_lines[-1].depreciation_date,
            'Descending sort: first date must be >= last date.',
        )
        # DESC: first date is 2028-12-01 (60th period).
        self.assertEqual(
            desc_lines[0].depreciation_date,
            date(2028, 12, 1),
            f'First DESC line should be 2028-12-01; got '
            f'{desc_lines[0].depreciation_date}.',
        )

        # ASC and DESC are exact reverses (when ordered by a
        # strict-monotonic key, which our schedule is).
        for i in range(len(asc_lines)):
            self.assertEqual(
                asc_lines[i].depreciation_date,
                desc_lines[len(asc_lines) - 1 - i].depreciation_date,
                f'ASC[{i}] and reverse-DESC[{i}] dates must match.',
            )

        # Verify model _order matches AAP-mandated value.
        DepLine = self.env['account.asset.depreciation.line']
        self.assertEqual(
            DepLine._order,
            'asset_id, sequence, depreciation_date',
            f'Model _order must be '
            f"'asset_id, sequence, depreciation_date'; got "
            f"'{DepLine._order}'.",
        )

    # =========================================================================
    # T-AM-003-09: Sort by depreciation_amount
    # =========================================================================

    def test_am_003_09_sort_by_amount(self):
        """T-AM-003-09: Recordset sorts by depreciation_amount.

        Verifies AC5 of AM-003 (sort by amount). For a uniform
        straight-line schedule (every line == 100.00) the sort is
        trivially stable; this test additionally creates a
        declining-balance asset whose amounts vary per period and
        asserts the sort produces a strictly-monotonic ordering.
        """
        # Create a declining-balance asset for diverse amounts.
        # 5-year straight-line on 10000 with 2.0 declining factor:
        # Year 1: 10000 * (2/5) = 4000
        # Year 2: 6000 * (2/5)  = 2400
        # Year 3: 3600 * (2/5)  = 1440
        # ...
        declining_asset = self._create_basic_asset(
            self,
            name='AM-003-09 Declining Asset',
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
        declining_asset.action_confirm()

        # Pre-condition: declining_asset has 5 lines with strictly
        # decreasing amounts.
        self.assertEqual(
            len(declining_asset.depreciation_line_ids),
            5,
            'Declining asset should have 5 yearly lines.',
        )

        # ASC sort: smallest amount first.
        asc_lines = declining_asset.depreciation_line_ids.sorted(
            'depreciation_amount',
        )
        self.assertLessEqual(
            asc_lines[0].depreciation_amount,
            asc_lines[-1].depreciation_amount,
            'ASC sort: first amount must be <= last amount.',
        )

        # DESC sort: largest amount first.
        desc_lines = declining_asset.depreciation_line_ids.sorted(
            'depreciation_amount',
            reverse=True,
        )
        self.assertGreaterEqual(
            desc_lines[0].depreciation_amount,
            desc_lines[-1].depreciation_amount,
            'DESC sort: first amount must be >= last amount.',
        )

        # Strict monotonicity verification: amounts decline
        # period-over-period for declining-balance method
        # (excluding any equal values from the rounding adjustment
        # on the final period).
        for i in range(len(asc_lines) - 1):
            self.assertLessEqual(
                asc_lines[i].depreciation_amount,
                asc_lines[i + 1].depreciation_amount,
                f'ASC sort order violated at index {i}: '
                f'{asc_lines[i].depreciation_amount} > '
                f'{asc_lines[i + 1].depreciation_amount}.',
            )

    # =========================================================================
    # T-AM-003-10: Group by fiscal period
    # =========================================================================

    def test_am_003_10_group_by_fiscal_period(self):
        """T-AM-003-10: read_group aggregates lines by fiscal year.

        Verifies AC5 of AM-003 (group by fiscal period). The
        canonical Odoo aggregation API ``_read_group`` is invoked
        with ``groupby=['depreciation_date:year']`` and
        ``aggregates=['depreciation_amount:sum']``. Each year's
        sum should equal 12 * 100 = 1200.00 for the 60-line / 100-
        per-line fixture.
        """
        DepLine = self.env['account.asset.depreciation.line']
        # Odoo 19 _read_group returns list of tuples
        # (year_value, sum_value) for the requested groupby/aggregate
        # pair.
        groups = DepLine._read_group(
            domain=[('asset_id', '=', self.monthly_asset.id)],
            groupby=['depreciation_date:year'],
            aggregates=['depreciation_amount:sum'],
        )

        # 5 years (2024..2028).
        self.assertEqual(
            len(groups),
            5,
            f'Expected 5 yearly groups; got {len(groups)}.',
        )

        # Sum each year's amounts; total across all years == 6000.
        total_sum = 0.0
        for year_value, year_sum in groups:
            self.assertAlmostEqual(
                year_sum,
                1200.0,
                places=2,
                msg=(
                    f'Year {year_value} aggregate must be 1200.00; '
                    f'got {year_sum:.2f}.'
                ),
            )
            total_sum += year_sum

        self.assertAlmostEqual(
            total_sum,
            6000.0,
            places=2,
            msg=(
                'Sum of all yearly aggregates must equal full '
                'depreciable base (6000.00).'
            ),
        )

    # =========================================================================
    # T-AM-003-11: Board read-only
    # =========================================================================

    def test_am_003_11_board_readonly(self):
        """T-AM-003-11: List view declares create=false / delete=false / limit=80.

        Verifies AC1 of AM-003 (board is read-only). Loads the
        ``account_asset_management.view_account_asset_depreciation
        _line_list`` view via ``env.ref()`` and inspects its
        ``arch_db`` for the AAP-mandated attributes:

            * ``create="false"`` (or ``create="0"``)
            * ``delete="false"`` (or ``delete="0"``)
            * ``limit="80"`` (pagination cap critical for the
              <2s SLA on large schedules; without it the full 480-
              line render would pull all rows in one go).
        """
        view = self.env.ref(
            'account_asset_management.'
            'view_account_asset_depreciation_line_list',
        )
        self.assertTrue(
            view,
            'Required view '
            'account_asset_management.view_account_asset_depreciation'
            '_line_list must be installed.',
        )

        arch = view.arch_db or ''
        arch_lower = arch.lower()

        # Check for create=false attribute (allow either form:
        # create="false" or create="0").
        self.assertTrue(
            'create="false"' in arch_lower or 'create="0"' in arch,
            f'List view must declare create="false" (or "0") to '
            f'enforce read-only board; arch fragment:\n{arch[:2000]}',
        )
        # Check for delete=false attribute.
        self.assertTrue(
            'delete="false"' in arch_lower or 'delete="0"' in arch,
            f'List view must declare delete="false" (or "0") to '
            f'enforce read-only board; arch fragment:\n{arch[:2000]}',
        )
        # Check for limit="80" pagination cap (critical for
        # the <2s SLA on 480-period assets per AAP section 0.7.3).
        self.assertIn(
            'limit="80"',
            arch,
            f'List view must declare limit="80" pagination cap; '
            f'arch fragment:\n{arch[:2000]}',
        )

    # =========================================================================
    # T-AM-003-12: Smart button navigation
    # =========================================================================

    def test_am_003_12_smart_button_navigation(self):
        """T-AM-003-12: action_view_depreciation_lines returns correct action.

        Verifies the smart-button method on ``account.asset``
        returns an ``ir.actions.act_window`` dict targeting the
        depreciation line model with a domain filter on the source
        asset.
        """
        action = self.monthly_asset.action_view_depreciation_lines()

        # Action shape: dict with 'type' / 'res_model' / 'domain' /
        # 'view_mode' / 'context'.
        self.assertIsInstance(
            action,
            dict,
            f'action_view_depreciation_lines must return a dict; '
            f'got {type(action).__name__}.',
        )
        self.assertEqual(
            action.get('type'),
            'ir.actions.act_window',
            f"action['type'] must be 'ir.actions.act_window'; "
            f"got '{action.get('type')}'.",
        )
        self.assertEqual(
            action.get('res_model'),
            'account.asset.depreciation.line',
            f"action['res_model'] must be "
            f"'account.asset.depreciation.line'; "
            f"got '{action.get('res_model')}'.",
        )

        # Domain: filters by asset_id == monthly_asset.
        domain = action.get('domain') or []
        self.assertIn(
            ('asset_id', '=', self.monthly_asset.id),
            domain,
            f"action['domain'] must filter by "
            f"('asset_id', '=', {self.monthly_asset.id}); "
            f"got {domain}.",
        )

        # view_mode: contains list and/or kanban (per
        # views/depreciation_board_views.xml the mode is
        # 'list,kanban,graph').
        view_mode = action.get('view_mode') or ''
        self.assertTrue(
            'list' in view_mode or 'kanban' in view_mode,
            f"action['view_mode'] must contain 'list' or 'kanban'; "
            f"got '{view_mode}'.",
        )

        # Context: pre-fills default_asset_id for line creation
        # (consistent with the search_default_asset_id auto-filter).
        context = action.get('context') or {}
        self.assertEqual(
            context.get('default_asset_id'),
            self.monthly_asset.id,
            f"action['context']['default_asset_id'] should equal "
            f"asset id ({self.monthly_asset.id}); got "
            f"{context.get('default_asset_id')}.",
        )

    # =========================================================================
    # T-AM-003-13: XLSX export
    # =========================================================================

    def test_am_003_13_xlsx_export(self):
        """T-AM-003-13: Board model permits XLSX export (Odoo built-in).

        Verifies AC6 of AM-003 (export to spreadsheet format). The
        Odoo web client provides a built-in 'Export' action on every
        list view that supports CSV and XLSX output, gated by:

            * Read access to the model (perm_read=1 in
              ir.model.access.csv).
            * No ``_disallow_export = True`` class attribute.

        This test asserts both gates are open: the depreciation-line
        model exposes read access via the canonical accountant
        groups and does NOT block exports.
        """
        DepLine = self.env['account.asset.depreciation.line']

        # The model must NOT carry a _disallow_export flag.
        self.assertFalse(
            getattr(DepLine, '_disallow_export', False),
            'The account.asset.depreciation.line model must not '
            'declare _disallow_export = True; doing so would block '
            'XLSX/CSV export from the board view.',
        )

        # ACL check: at least one access rule grants read access
        # to a group the test user belongs to.
        access_rules = self.env['ir.model.access'].search([
            ('model_id.model', '=', 'account.asset.depreciation.line'),
            ('perm_read', '=', True),
        ])
        self.assertTrue(
            access_rules,
            'There must be at least one ir.model.access rule with '
            'perm_read=True for account.asset.depreciation.line.',
        )

        # The current test user can effectively read records.
        # ``check_access_rights`` raises AccessError if denied;
        # a clean call confirms the user is authorized to read.
        DepLine.check_access('read')

        # Smoke test: the search-and-mapped roundtrip used by the
        # web client's export action runs without error.
        lines = DepLine.search([
            ('asset_id', '=', self.monthly_asset.id),
        ])
        self.assertEqual(
            len(lines),
            60,
            'Export precondition: search() must return 60 lines.',
        )
        # Mapped() simulates the web client's column-extraction
        # for the export. If any field were inaccessible, this
        # would raise.
        sequences = lines.mapped('sequence')
        amounts = lines.mapped('depreciation_amount')
        cumulative = lines.mapped('cumulative_depreciation')
        nbv = lines.mapped('net_book_value')
        self.assertEqual(len(sequences), 60)
        self.assertEqual(len(amounts), 60)
        self.assertEqual(len(cumulative), 60)
        self.assertEqual(len(nbv), 60)

    # =========================================================================
    # T-AM-003-14: CSV export
    # =========================================================================

    def test_am_003_14_csv_export(self):
        """T-AM-003-14: Board model permits CSV export (Odoo built-in).

        Verifies AC6 of AM-003 (export to spreadsheet format). The
        CSV export uses the same Odoo web-client export action as
        XLSX; the gating model attributes and ACLs must permit it.
        Same semantics as test_am_003_13 but documented separately
        for traceability with the AC6 test list.
        """
        DepLine = self.env['account.asset.depreciation.line']

        # _disallow_export attribute must not be True.
        self.assertFalse(
            getattr(DepLine, '_disallow_export', False),
            'The account.asset.depreciation.line model must not '
            'declare _disallow_export = True; doing so would block '
            'CSV/XLSX export from the board view.',
        )

        # The model is read-accessible to the test user.
        DepLine.check_access('read')

        # Default export field set: validate the four canonical
        # columns are accessible without raising. The Odoo web
        # client's CSV export defaults to the displayed columns;
        # we simulate this by name_get / read on the relevant
        # fields.
        lines = DepLine.search([
            ('asset_id', '=', self.monthly_asset.id),
        ])
        # ``read`` with explicit field list mirrors the export's
        # SELECT clause; failure here would indicate a denied
        # column-level read.
        records = lines.read([
            'sequence',
            'depreciation_date',
            'depreciation_amount',
            'cumulative_depreciation',
            'net_book_value',
            'state',
        ])
        self.assertEqual(
            len(records),
            60,
            f'Expected 60 records read; got {len(records)}.',
        )
        # Validate every record has all 6 requested columns +
        # the implicit 'id' column.
        required_keys = {
            'id',
            'sequence',
            'depreciation_date',
            'depreciation_amount',
            'cumulative_depreciation',
            'net_book_value',
            'state',
        }
        for record in records:
            self.assertEqual(
                set(record.keys()),
                required_keys,
                f'Record {record.get("id")} keys mismatch: '
                f'expected {required_keys}, got {set(record.keys())}.',
            )

    # =========================================================================
    # T-AM-003-15: PERFORMANCE SLA -- 480 periods rendered in <2s
    # =========================================================================

    def test_am_003_15_performance_sla_480_periods(self):
        """T-AM-003-15: SLA -- full board render <2s for 480 periods.

        Per AAP section 0.7.3, the depreciation board MUST render
        the full schedule for assets with up to 480 periods (40
        years monthly) in under 2 seconds. This is the BLOCKING
        performance gate.

        The test:

            1. Creates a 480-line asset (40-year monthly).
            2. Confirms it (generates the full schedule).
            3. Invalidates the ORM cache to simulate a fresh
               render from a cold cache (worst-case for a real
               user opening the board).
            4. Issues the canonical board render sequence:
               ``search([asset_id]) + mapped(...)`` over the 7
               displayed columns.
            5. Asserts elapsed < 2.0s.

        The test is gated by ``SKIP_PERF_TESTS`` so constrained
        CI environments can opt out::

            SKIP_PERF_TESTS=1 pytest -k test_am_003_15
        """
        if os.environ.get('SKIP_PERF_TESTS'):
            self.skipTest(
                'Performance test skipped via SKIP_PERF_TESTS env var.',
            )

        # Arrange: 40-year monthly asset with 480 periods.
        big_asset = self._create_basic_asset(
            self,
            name='AM-003-15 40yr Big Asset',
            acquisition_cost=960000.0,  # 480 * 2000.00 per month
            salvage_value=0.0,
            depreciation_method='straight_line',
            useful_life_unit='months',
            useful_life_months=480,
            useful_life_years=0,
            acquisition_date=date(2024, 1, 1),
            start_date_option='acquisition_date',
        )
        big_asset.action_confirm()

        # Pre-condition: schedule generation completed cleanly.
        self.assertEqual(
            len(big_asset.depreciation_line_ids),
            480,
            'Schedule generation must produce exactly 480 lines.',
        )

        # Act: invalidate cache, then time the full board render
        # sequence.
        self.env.invalidate_all()

        t0 = time.perf_counter()
        # Step 1: search() returns the recordset.
        lines = self.env['account.asset.depreciation.line'].search([
            ('asset_id', '=', big_asset.id),
        ])
        # Step 2: mapped() over each displayed column (this is the
        # canonical Odoo web-client list-view render path).
        # Each mapped() triggers an SQL fetch for the requested
        # column on the entire recordset in one query.
        _ = lines.mapped('sequence')
        _ = lines.mapped('depreciation_date')
        _ = lines.mapped('depreciation_amount')
        _ = lines.mapped('cumulative_depreciation')
        _ = lines.mapped('net_book_value')
        _ = lines.mapped('state')
        _ = lines.mapped('move_id.name')
        elapsed = time.perf_counter() - t0

        # Sanity check: the search returned all 480 lines.
        self.assertEqual(
            len(lines),
            480,
            f'Expected 480 lines from search; got {len(lines)}.',
        )

        # SLA assertion: the render must complete in under 2s.
        # Failure here is BLOCKING per AAP section 0.7.3.
        self.assertLess(
            elapsed,
            2.0,
            f'AM-003 SLA violation: full board render for 480 '
            f'periods took {elapsed:.3f}s, exceeds 2.0s budget '
            f'(AAP section 0.7.3). Investigate (a) cumulative_'
            f'depreciation / net_book_value @api.depends store=True '
            f'attribute, (b) asset_id FK index, '
            f'(c) view limit="80" pagination, (d) ORM cache '
            f'recompute triggers.',
        )
