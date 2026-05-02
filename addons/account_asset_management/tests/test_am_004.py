# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Tests for AM-004: Automatic Depreciation Entries user story.

Covers the following BDD scenarios from
``tickets/stories/asset-management/AM-004-automatic-depreciation-entries.md``:

    T-AM-004-01  Cron posts scheduled-date entries: DR expense / CR accumulated
    T-AM-004-02  Batch processing produces summary report dict with counts
    T-AM-004-03  Draft mode creates draft moves (auto_post_depreciation=False)
    T-AM-004-04  Auto-post mode posts moves immediately (auto_post_depreciation=True)
    T-AM-004-05  Prorated depreciation for mid-period acquisitions
    T-AM-004-06  Cron logging: success/skip/error counts in returned dict
    T-AM-004-07  Error: locked period -> line skipped with error recorded
    T-AM-004-08  Error: missing configuration -> line skipped with error recorded
    T-AM-004-09  Idempotency: already-posted lines skipped on re-run
    T-AM-004-10  Asset auto-closes when NBV <= salvage_value
    T-AM-004-11  Fully-depreciated asset cron run is no-op
    T-AM-004-12  Batch fault-tolerance: one bad asset does not block others
    T-AM-004-13  *** GATE 13: ir_cron record registered and invokable ***
    T-AM-004-14  Perf: 100 assets processed < 30s
    T-AM-004-15  Perf: 1,000 assets processed < 5min (skipped unless SLOW_TESTS env)

Each test method's docstring starts with the BDD scenario ID for traceability.

Tests use ``freeze_time`` from ``freezegun`` to control the "current date"
for deterministic cron triggering behavior. The cron filters depreciation
lines by ``depreciation_date <= fields.Date.context_today(self)``, which
respects the frozen clock so test assertions remain stable across runs.

AAP Rule Compliance
-------------------
* R-01 (Module independence) -- This file imports ONLY from the Python
  standard library (``logging``, ``os``, ``time``, ``datetime``,
  ``unittest.mock``), the third-party ``freezegun`` package, the
  ``odoo`` framework, and the local ``.common`` sibling module within
  the same ``account_asset_management`` package. NO imports from the
  three sibling Community Edition modules
  (``account_budget_management``, ``account_deferred_revenue``,
  ``account_payment_followup``).
* R-02 (No Enterprise dependencies) -- This file contains NO references
  to Odoo Enterprise addon names (``account_asset``,
  ``account_accountant``, ``account_reports``, ``account_followup``,
  ``account_deferred_revenue``).
* R-04 (Per-story coverage gate) -- Tests exercise every documented
  branch of the AM-004 cron path: success posting (test_01),
  draft/auto-post toggle (test_03/04), idempotency (test_09),
  auto-close (test_10), no-op for closed assets (test_11), per-line
  skip via UserError (test_07/08), per-asset error via Exception
  (test_12), and the registered cron's metadata + invocation
  (test_13). Performance tests (test_14, test_15) verify cron
  scaling against the AAP-stated SLAs (100 assets <30s, 1000
  assets <5min).
* R-06 (``ir.cron`` via XML) -- ``test_am_004_13_cron_registered_and_invokable``
  is the canonical Gate 13 enforcement test: it loads the cron via
  ``self.env.ref('account_asset_management.ir_cron_asset_depreciation')``
  (proving the XML record is registered by the module installer)
  and calls ``cron.method_direct_trigger()`` (proving the cron is
  manually invokable). NO Python-level scheduling primitives
  (``threading.Timer``, ``APScheduler``, ``sched``) are imported or
  exercised.
* R-07 (No unjustified ``sudo``) -- This file contains NO ``.sudo()``
  calls. The test user provisioned by ``AccountTestInvoicingCommon``
  has both ``account.group_account_user`` and
  ``account.group_account_manager`` group memberships, providing
  full CRUD on every model touched by the tests via
  ``security/ir.model.access.csv``.
"""

import logging
import os
import time
from datetime import date, datetime  # noqa: F401 -- imported per agent_prompt
from unittest.mock import patch

from freezegun import freeze_time

from odoo import (  # noqa: F401 -- Command/fields imported per agent_prompt
    Command,
    fields,
)
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import AssetManagementTestCommon

_logger = logging.getLogger(__name__)


@tagged('post_install', '-at_install')
class TestAutomaticDepreciationEntries(AssetManagementTestCommon):
    """AM-004 -- Automatic Depreciation Entries (cron-driven).

    Covers all 15 test scenarios for the AM-004 story. Each test
    method's name encodes both its scenario ID (``test_am_004_NN_``)
    and its scenario summary (e.g. ``cron_posts_scheduled_entries``).

    Usage of ``freeze_time``
    ------------------------
    The cron's filter uses ``fields.Date.context_today(self)`` to
    compute "today", which respects the ``freezegun`` decorator. All
    cron-invoking tests therefore set a deterministic frozen date so
    the count of "due" depreciation lines is computable in advance.

    Pattern::

        @freeze_time('2024-12-31')
        def test_am_004_NN_...(self):
            ...

    Auto-post toggle
    ----------------
    The asset category fixture ``cls.asset_category_it`` is created
    with ``auto_post_depreciation=False`` (matching common.py line 271).
    Tests that need auto-post behavior either (a) create a fresh
    category with ``auto_post_depreciation=True``, (b) update the
    fixture's flag inline (Odoo's transactional test runner rolls
    back the change at test teardown), or (c) bypass the category
    entirely (no category = auto_post defaults to False).
    """

    # =========================================================================
    # Helpers (test-local convenience methods)
    # =========================================================================

    @classmethod
    def _build_open_asset(
        cls,
        name='AM-004 Test Asset',
        useful_life_unit='months',
        useful_life_months=60,
        useful_life_years=0,
        acquisition_cost=6000.0,
        salvage_value=0.0,
        acquisition_date=None,
        category_id=None,
        auto_post=False,
        **overrides,
    ):
        """Build a draft asset, attach a category w/ ``auto_post`` flag, confirm.

        Returns a confirmed (state='open') ``account.asset`` record with
        a fully-generated depreciation schedule. The asset's category is
        either:

            * ``cls.asset_category_it`` with ``auto_post_depreciation``
              set to ``auto_post`` (default ``False``), OR
            * the explicit ``category_id`` recordset passed by the caller.

        For monthly-life assets with ``acquisition_cost=6000`` and
        ``useful_life_months=60``, each line's amount is
        ``6000.0 / 60 = 100.0`` (the AM-004-01 fixture).
        """
        # Pick a category and toggle its auto_post_depreciation flag.
        # Tests run inside Odoo's per-test SAVEPOINT so flag changes
        # are rolled back at tearDown -- safe to mutate the class
        # fixture inline without polluting other tests.
        if category_id is None:
            category = cls.asset_category_it
            category.auto_post_depreciation = auto_post
            category_id = category.id
        # Build asset values; defaults satisfy the cron's domain
        # ('state'='open', and once confirmed, depreciation_line_ids
        # populated) on confirmation.
        if acquisition_date is None:
            acquisition_date = date(2024, 1, 1)
        asset = cls._create_basic_asset(
            cls,
            name=name,
            useful_life_unit=useful_life_unit,
            useful_life_months=useful_life_months,
            useful_life_years=useful_life_years,
            acquisition_cost=acquisition_cost,
            salvage_value=salvage_value,
            acquisition_date=acquisition_date,
            category_id=category_id,
            **overrides,
        )
        cls._confirm_asset(cls, asset)
        return asset

    # =========================================================================
    # T-AM-004-01: Cron posts scheduled depreciation entries
    # =========================================================================

    @freeze_time('2024-12-31')
    def test_am_004_01_cron_posts_scheduled_entries(self):
        """T-AM-004-01: Cron posts depreciation entries due by today.

        Verifies the canonical happy-path:

            * 60-line monthly schedule on a 5-year asset acquired
              2024-01-01.
            * Frozen at 2024-12-31, exactly 12 lines (Jan-Dec 2024)
              are due (depreciation_date <= today).
            * After cron runs:
                - Each due line transitions draft -> posted.
                - Each due line has a populated ``move_id`` linking
                  to a posted ``account.move`` (auto_post=True).
                - The move has a debit line on
                  ``expense_account_id`` and a credit line on
                  ``accumulated_depreciation_account_id``.
                - Each move carries ``asset_id == asset`` and
                  ``asset_entry_type == 'depreciation'``.
            * The cron's return dict reports success > 0 and
              errors == 0.
        """
        asset = self._build_open_asset(
            name='AM-004-01 Asset',
            acquisition_cost=6000.0,
            useful_life_unit='months',
            useful_life_months=60,
            useful_life_years=0,
            acquisition_date=date(2024, 1, 1),
            salvage_value=0.0,
            auto_post=True,
        )
        # Pre-conditions: 60 draft lines, asset is open.
        self.assertEqual(asset.state, 'open')
        self.assertEqual(len(asset.depreciation_line_ids), 60)
        draft_count_before = len(asset.depreciation_line_ids.filtered(
            lambda line: line.state == 'draft',
        ))
        self.assertEqual(draft_count_before, 60)

        # Act: invoke the cron entry point directly.
        result = self.env['account.asset']._cron_post_depreciation_entries()

        # Assert: result dict shape and counts.
        self.assertIsInstance(result, dict)
        self.assertIn('success', result)
        self.assertIn('skipped', result)
        self.assertIn('errors', result)
        self.assertEqual(result['errors'], 0)
        # 12 lines (Jan-Dec 2024) should have posted.
        self.assertEqual(result['success'], 12)
        self.assertEqual(result['skipped'], 0)

        # Assert: due lines are now posted; future lines remain draft.
        posted_lines = asset.depreciation_line_ids.filtered(
            lambda line: line.state == 'posted',
        )
        self.assertEqual(len(posted_lines), 12)
        draft_lines = asset.depreciation_line_ids.filtered(
            lambda line: line.state == 'draft',
        )
        self.assertEqual(len(draft_lines), 48)

        # Assert: every posted line links to a posted account.move
        # with the correct DR/CR account assignment, asset_id, and
        # asset_entry_type.
        for line in posted_lines:
            self.assertTrue(
                line.move_id,
                f'Posted line {line.id} should have move_id set.',
            )
            move = line.move_id
            self.assertEqual(
                move.state,
                'posted',
                f'Move {move.id} should be posted (auto_post=True).',
            )
            self.assertEqual(
                move.asset_id,
                asset,
                'Move asset_id must back-reference the source asset.',
            )
            self.assertEqual(
                move.asset_entry_type,
                'depreciation',
                "Move asset_entry_type must be 'depreciation'.",
            )
            # DR side: expense account.
            debit_lines = move.line_ids.filtered(lambda ml: ml.debit > 0)
            self.assertEqual(len(debit_lines), 1)
            self.assertEqual(
                debit_lines.account_id,
                asset.expense_account_id,
            )
            # CR side: accumulated depreciation account.
            credit_lines = move.line_ids.filtered(lambda ml: ml.credit > 0)
            self.assertEqual(len(credit_lines), 1)
            self.assertEqual(
                credit_lines.account_id,
                asset.accumulated_depreciation_account_id,
            )
            # Balanced entry.
            self.assertEqual(
                debit_lines.debit,
                credit_lines.credit,
                'DR and CR amounts must balance.',
            )
            # Per-period amount = 6000 / 60 = 100.00.
            self.assertAlmostEqual(
                debit_lines.debit,
                100.0,
                places=2,
                msg='Per-period depreciation amount must be 100.00.',
            )

    # =========================================================================
    # T-AM-004-02: Cron returns summary dict with success/skip/error keys
    # =========================================================================

    @freeze_time('2024-12-31')
    def test_am_004_02_batch_summary_dict(self):
        """T-AM-004-02: Cron returns a summary dict with the three counters.

        Multiple assets with different acquisition dates are processed
        in a single cron invocation. The return value must be a dict
        carrying the canonical keys ``'success'``, ``'skipped'``,
        ``'errors'`` (one int each) so cron operators / logs can
        understand the batch's outcome at a glance.
        """
        # Three assets with different schedules.
        asset1 = self._build_open_asset(
            name='AM-004-02 Asset 1',
            acquisition_cost=1200.0,
            useful_life_unit='months',
            useful_life_months=12,
            useful_life_years=0,
            acquisition_date=date(2024, 1, 1),
            auto_post=True,
        )
        asset2 = self._build_open_asset(
            name='AM-004-02 Asset 2',
            acquisition_cost=600.0,
            useful_life_unit='months',
            useful_life_months=6,
            useful_life_years=0,
            acquisition_date=date(2024, 6, 1),
            auto_post=True,
        )
        asset3 = self._build_open_asset(
            name='AM-004-02 Asset 3',
            acquisition_cost=2400.0,
            useful_life_unit='months',
            useful_life_months=24,
            useful_life_years=0,
            acquisition_date=date(2024, 1, 1),
            auto_post=True,
        )
        result = self.env['account.asset']._cron_post_depreciation_entries()

        # Assert: result dict has the three required keys (each an int).
        self.assertIsInstance(result, dict)
        self.assertIn('success', result)
        self.assertIn('skipped', result)
        self.assertIn('errors', result)
        self.assertIsInstance(result['success'], int)
        self.assertIsInstance(result['skipped'], int)
        self.assertIsInstance(result['errors'], int)

        # Assert: total success >= sum of due lines across all assets.
        # asset1: 12 lines all due (Jan-Dec 2024) at 2024-12-31.
        # asset2: 6 lines all due (Jun-Nov 2024) at 2024-12-31.
        # asset3: 12 lines due (Jan-Dec 2024) at 2024-12-31 (out of 24).
        # Total: 30. Result['success'] must equal 30 exactly.
        self.assertEqual(result['success'], 30)
        self.assertEqual(result['errors'], 0)

        # Cross-check the per-asset state.
        for asset, expected_posted in (
            (asset1, 12),
            (asset2, 6),
            (asset3, 12),
        ):
            posted = asset.depreciation_line_ids.filtered(
                lambda line: line.state == 'posted',
            )
            self.assertEqual(
                len(posted),
                expected_posted,
                f'Asset {asset.name} should have '
                f'{expected_posted} posted lines.',
            )

    # =========================================================================
    # T-AM-004-03: Draft mode (auto_post_depreciation=False)
    # =========================================================================

    @freeze_time('2024-06-30')
    def test_am_004_03_draft_mode(self):
        """T-AM-004-03: ``auto_post_depreciation=False`` -> moves stay draft.

        When the asset's category has ``auto_post_depreciation`` set
        to ``False``, the cron creates the journal entries but does
        NOT post them. Verifies:

            * Each due depreciation line transitions to ``state='posted'``.
            * Each due line's ``move_id`` is set, but ``move.state``
              is ``'draft'`` (i.e., the move was created but not
              posted -- it appears in the accountant's pending review
              queue).
        """
        asset = self._build_open_asset(
            name='AM-004-03 Draft Mode Asset',
            acquisition_cost=1200.0,
            useful_life_unit='months',
            useful_life_months=12,
            useful_life_years=0,
            acquisition_date=date(2024, 1, 1),
            auto_post=False,  # explicit draft mode
        )
        result = self.env['account.asset']._cron_post_depreciation_entries()
        self.assertEqual(result['errors'], 0)

        posted_lines = asset.depreciation_line_ids.filtered(
            lambda line: line.state == 'posted',
        )
        # 6 lines (Jan-Jun 2024) are due at 2024-06-30 inclusive.
        self.assertEqual(len(posted_lines), 6)
        for line in posted_lines:
            self.assertTrue(
                line.move_id,
                'Each posted line must have move_id set even in draft mode.',
            )
            self.assertEqual(
                line.move_id.state,
                'draft',
                'Move state must be draft when '
                'auto_post_depreciation=False.',
            )
            # Even draft moves carry the asset back-reference.
            self.assertEqual(line.move_id.asset_id, asset)
            self.assertEqual(line.move_id.asset_entry_type, 'depreciation')

    # =========================================================================
    # T-AM-004-04: Auto-post mode (auto_post_depreciation=True)
    # =========================================================================

    @freeze_time('2024-06-30')
    def test_am_004_04_auto_post_mode(self):
        """T-AM-004-04: ``auto_post_depreciation=True`` -> moves auto-posted.

        When the asset's category has ``auto_post_depreciation`` set
        to ``True``, the cron both creates AND posts the journal
        entries in a single invocation. Verifies:

            * Each due depreciation line is in ``state='posted'``.
            * Each due line's ``move_id`` is in ``state='posted'``.
        """
        asset = self._build_open_asset(
            name='AM-004-04 Auto-Post Asset',
            acquisition_cost=1200.0,
            useful_life_unit='months',
            useful_life_months=12,
            useful_life_years=0,
            acquisition_date=date(2024, 1, 1),
            auto_post=True,
        )
        result = self.env['account.asset']._cron_post_depreciation_entries()
        self.assertEqual(result['errors'], 0)

        posted_lines = asset.depreciation_line_ids.filtered(
            lambda line: line.state == 'posted',
        )
        self.assertEqual(len(posted_lines), 6)
        for line in posted_lines:
            self.assertTrue(line.move_id)
            self.assertEqual(
                line.move_id.state,
                'posted',
                'Move must be posted when auto_post_depreciation=True.',
            )

    # =========================================================================
    # T-AM-004-05: Mid-period acquisition / start_date_option behaviour
    # =========================================================================

    def test_am_004_05_prorated_midperiod(self):
        """T-AM-004-05: ``start_date_option`` controls schedule start.

        Verifies that the ``start_date_option`` selector behaves
        correctly for mid-month acquisition dates:

            * ``acquisition_date``: depreciation starts on the
              acquisition date (mid-month boundary preserved).
            * ``first_day_next_month``: depreciation starts on the
              first day of the month following acquisition (clean
              fiscal-month boundary).
            * ``first_day_current_month``: depreciation starts on the
              first day of the acquisition month (back-dates to start
              of acquisition month).

        For each sub-case, the schedule's first line is checked
        against the expected ``depreciation_date``. Per-period
        amounts are equal in straight-line mode (no per-day
        proration in the implementation) -- "proration" is delivered
        by the start_date_option selector.
        """
        # Acquisition mid-month: 15 January 2024.
        acq = date(2024, 1, 15)

        # Sub-case A: acquisition_date option keeps mid-month boundary.
        with self.subTest(start_date_option='acquisition_date'):
            asset_a = self._build_open_asset(
                name='AM-004-05 Mid-Period A',
                acquisition_cost=1200.0,
                useful_life_unit='months',
                useful_life_months=12,
                useful_life_years=0,
                acquisition_date=acq,
                start_date_option='acquisition_date',
                auto_post=False,
            )
            first_line_a = asset_a.depreciation_line_ids.sorted(
                'sequence',
            )[0]
            self.assertEqual(
                first_line_a.depreciation_date,
                acq,
                "First line must use the acquisition date as start "
                "when start_date_option='acquisition_date'.",
            )

        # Sub-case B: first_day_next_month rolls forward to Feb 1.
        with self.subTest(start_date_option='first_day_next_month'):
            asset_b = self._build_open_asset(
                name='AM-004-05 Mid-Period B',
                acquisition_cost=1200.0,
                useful_life_unit='months',
                useful_life_months=12,
                useful_life_years=0,
                acquisition_date=acq,
                start_date_option='first_day_next_month',
                auto_post=False,
            )
            first_line_b = asset_b.depreciation_line_ids.sorted(
                'sequence',
            )[0]
            self.assertEqual(
                first_line_b.depreciation_date,
                date(2024, 2, 1),
                "First line must roll to Feb 1 when "
                "start_date_option='first_day_next_month'.",
            )

        # Sub-case C: first_day_current_month back-dates to Jan 1.
        with self.subTest(start_date_option='first_day_current_month'):
            asset_c = self._build_open_asset(
                name='AM-004-05 Mid-Period C',
                acquisition_cost=1200.0,
                useful_life_unit='months',
                useful_life_months=12,
                useful_life_years=0,
                acquisition_date=acq,
                start_date_option='first_day_current_month',
                auto_post=False,
            )
            first_line_c = asset_c.depreciation_line_ids.sorted(
                'sequence',
            )[0]
            self.assertEqual(
                first_line_c.depreciation_date,
                date(2024, 1, 1),
                "First line must back-date to Jan 1 when "
                "start_date_option='first_day_current_month'.",
            )

        # Total depreciation invariant: sum of line amounts equals
        # acquisition_cost - salvage_value, regardless of option.
        for asset in (asset_a, asset_b, asset_c):
            total_amount = sum(
                line.depreciation_amount
                for line in asset.depreciation_line_ids
            )
            self.assertAlmostEqual(
                total_amount,
                1200.0,
                places=2,
                msg=(
                    f'Total schedule for asset {asset.name} must equal '
                    f'(acquisition_cost - salvage_value)=1200.00.'
                ),
            )

    # =========================================================================
    # T-AM-004-06: Cron emits structured INFO log records
    # =========================================================================

    @freeze_time('2024-12-31')
    def test_am_004_06_cron_logging(self):
        """T-AM-004-06: Cron emits structured INFO log records for audit.

        The cron MUST emit at least one INFO-level log record on the
        ``odoo.addons.account_asset_management`` logger so that an
        operator inspecting the cron history can verify the run's
        outcome. The standard pattern emits two records per run:

            * START:    "AM-004 cron starting: N open asset(s) ..."
            * COMPLETE: "AM-004 cron completed: success=X, skipped=Y,
              errors=Z"

        This test runs against a healthy single-asset fixture and
        therefore expects ZERO ERROR-level records (only INFO).
        """
        asset = self._build_open_asset(
            name='AM-004-06 Logging Asset',
            acquisition_cost=1200.0,
            useful_life_unit='months',
            useful_life_months=12,
            useful_life_years=0,
            acquisition_date=date(2024, 1, 1),
            auto_post=True,
        )
        # IMPORTANT: pass ``level=logging.INFO`` (the integer 20) and NOT
        # the string ``'INFO'``. Odoo's ``netsvc.py`` registers a custom
        # log level with::
        #
        #     logging.RUNBOT = 25
        #     logging.addLevelName(logging.RUNBOT, "INFO")
        #
        # which overrides the standard logging module's ``'INFO' -> 20``
        # mapping. ``unittest.TestCase.assertLogs`` resolves a string
        # level via ``logging.getLevelName(level)``, which now returns
        # ``25`` instead of ``20``. With the logger threshold set to
        # 25, the cron's ``_logger.info(...)`` calls (emitted at the
        # standard level 20) are silently filtered out and ``cm.records``
        # remains empty -- producing a misleading "no logs of level
        # INFO or higher triggered" assertion failure even though the
        # cron actually emitted records at level 20.
        #
        # Passing the integer ``logging.INFO`` (20) bypasses
        # ``getLevelName`` entirely and sets the watched logger to the
        # correct threshold so that level-20 INFO records are captured.
        with self.assertLogs(
            'odoo.addons.account_asset_management',
            level=logging.INFO,
        ) as log_capture:
            result = self.env['account.asset'].\
                _cron_post_depreciation_entries()

        # At least one INFO record must have been emitted.
        self.assertGreater(
            len(log_capture.records),
            0,
            'Cron must emit at least one INFO log record.',
        )

        # No ERROR records on a healthy run.
        error_records = [
            rec for rec in log_capture.records
            if rec.levelno >= logging.ERROR
        ]
        self.assertEqual(
            len(error_records),
            0,
            f'Cron must NOT emit ERROR records on a healthy run; '
            f'got {len(error_records)}: '
            f'{[r.getMessage() for r in error_records]}',
        )

        # At least one record should mention either "AM-004",
        # "depreciation", or counts so an operator can find it.
        all_messages = ' '.join(
            rec.getMessage() for rec in log_capture.records
        )
        self.assertTrue(
            any(
                kw in all_messages.lower()
                for kw in ('am-004', 'depreciation', 'cron')
            ),
            'Log records should reference AM-004 / depreciation / cron '
            f'context. Got: {all_messages}',
        )

        # Sanity-check that the logged run actually posted entries.
        self.assertGreater(result['success'], 0)
        self.assertEqual(result['errors'], 0)
        # The asset should also have at least one posted line for traceability.
        self.assertGreater(
            len(asset.depreciation_line_ids.filtered(
                lambda line: line.state == 'posted',
            )),
            0,
        )

    # =========================================================================
    # T-AM-004-07: Locked period -> lines skipped with error recorded
    # =========================================================================

    @freeze_time('2024-12-31')
    def test_am_004_07_locked_period_skipped(self):
        """T-AM-004-07: Lines in locked fiscal periods are skipped.

        IMPLEMENTATION NOTE: Odoo 19.0 Community Edition's
        ``account.move._post()`` (``addons/account/models/account_move.py``)
        AUTO-DEFERS move dates that fall within a configured lock
        period instead of raising ``UserError``. Specifically, in the
        ``_post`` method::

            for move in to_post:
                affects_tax_report = move._affect_tax_report()
                lock_dates = move._get_violated_lock_dates(
                    move.date, affects_tax_report,
                )
                if lock_dates:
                    move.date = move._get_accounting_date(
                        move._get_accounting_date_source(),
                        affects_tax_report, lock_dates=lock_dates,
                    )

        any move whose date violates ``fiscalyear_lock_date``,
        ``hard_lock_date``, ``sale_lock_date``, ``purchase_lock_date``,
        or ``tax_lock_date`` is silently shifted forward to the next
        valid date BEFORE the lock-date check (``_check_fiscal_lock_dates``)
        runs. The check then sees the deferred date and passes. As a
        result, simply setting ``self.env.company.fiscalyear_lock_date``
        does NOT cause posting to raise -- the move's date is
        rewritten in-place, the move is posted normally, and the
        cron sees no ``UserError``.

        However, the AM-004 ticket explicitly requires the cron to
        gracefully skip postings that DO raise UserError (per AC2
        and AC6: "fault tolerance: lock-date violations skipped"),
        and the cron's implementation has a per-line ``except UserError
        -> skip_count += 1`` branch that exists precisely to handle
        this case. To exercise that branch in a test (and to model
        the semantics of a hardened deployment that customizes
        ``_post`` to BLOCK rather than auto-defer locked-period
        postings, e.g. via a ``post_init_hook`` or downstream addon),
        this test patches ``account.move.action_post`` to raise
        ``UserError`` when the move's date falls within the locked
        period (``date <= 2024-06-30``).

        Patching ``account.move.action_post`` (rather than the
        per-asset depreciation line's ``action_post`` or the cron
        method itself) targets the EXACT integration point where a
        real lock-date enforcement would fire, and allows healthy
        unlocked moves to pass through to the original Odoo
        implementation unchanged.

        Verifies:

            * Lines with ``depreciation_date <= 2024-06-30``
              remain in ``state='draft'`` (the patched action_post
              raised UserError before the depreciation line's
              ``write({'state': 'posted'})`` executed).
            * Lines with ``depreciation_date > 2024-06-30`` are
              posted normally (the patched function delegates to
              the real ``action_post`` for unlocked dates).
            * ``result['skipped'] >= 6`` (six locked lines were
              recorded as skipped via the cron's per-line
              ``except UserError`` handler).
            * ``result['success'] >= 6`` (six unlocked lines posted).
            * Cron does NOT raise (fault tolerance preserved).
        """
        asset = self._build_open_asset(
            name='AM-004-07 Locked Period Asset',
            acquisition_cost=1200.0,
            useful_life_unit='months',
            useful_life_months=12,
            useful_life_years=0,
            acquisition_date=date(2024, 1, 1),
            auto_post=True,
        )

        # Define the locked-period boundary. All moves dated on or
        # before this date are considered "locked" and must raise
        # UserError on posting -- the cron must catch and count
        # them as skipped.
        lock_date = date(2024, 6, 30)

        # Capture the real action_post implementation. We delegate
        # to it for unlocked moves (date > lock_date) so that the
        # six healthy lines (Jul-Dec) still produce real posted
        # journal entries with all the standard side effects.
        AccountMove = type(self.env['account.move'])
        original_action_post = AccountMove.action_post

        def patched_action_post(move_self):
            """Raise UserError for locked-period moves; else delegate.

            Mirrors the semantics that a strict-lock-date deployment
            would impose via a custom override / post_init_hook on
            ``account.move._post`` (one that BLOCKS rather than
            auto-defers). The check uses the move's CURRENT date
            attribute (which has not yet been rewritten by
            ``_get_accounting_date``) to identify locked postings.
            """
            for move in move_self:
                if move.date and move.date <= lock_date:
                    msg = (
                        f'You cannot add/modify entries prior to '
                        f'and inclusive of: Lock Date '
                        f'({lock_date.isoformat()}). '
                        f'Move date {move.date.isoformat()} is locked.'
                    )
                    raise UserError(msg)
            # Delegate unlocked moves to the original implementation
            # so they post normally with all standard side effects.
            return original_action_post(move_self)

        # Apply the patch for the duration of the cron run only.
        # ``autospec=True`` preserves the bound-method signature so
        # ``self`` is passed through correctly to the side_effect
        # callable.
        with patch.object(
            AccountMove,
            'action_post',
            autospec=True,
            side_effect=patched_action_post,
        ):
            result = self.env['account.asset']._cron_post_depreciation_entries()

        # Locked lines (Jan-Jun) should remain draft -- the patched
        # action_post raised UserError BEFORE the line's
        # ``write({'state': 'posted', ...})`` executed.
        locked_lines = asset.depreciation_line_ids.filtered(
            lambda line: line.depreciation_date <= lock_date,
        )
        self.assertEqual(
            len(locked_lines),
            6,
            'Fixture sanity check: 6 lines should be in the '
            'locked period (Jan-Jun 2024).',
        )
        for line in locked_lines:
            self.assertEqual(
                line.state,
                'draft',
                f'Line dated {line.depreciation_date} (locked) must '
                f'remain draft after cron run; got {line.state}. '
                f'The cron should have caught the UserError raised '
                f'by the patched action_post and incremented '
                f'skip_count without writing the line state.',
            )

        # Unlocked lines (Jul-Dec) should be posted normally.
        unlocked_lines = asset.depreciation_line_ids.filtered(
            lambda line: line.depreciation_date > lock_date
            and line.depreciation_date <= date(2024, 12, 31),
        )
        # Six lines covering Jul-Dec.
        self.assertEqual(
            len(unlocked_lines),
            6,
            'Fixture sanity check: 6 lines should be in the '
            'unlocked period (Jul-Dec 2024).',
        )
        posted_unlocked = unlocked_lines.filtered(
            lambda line: line.state == 'posted',
        )
        self.assertEqual(
            len(posted_unlocked),
            6,
            'All 6 unlocked lines must post normally despite '
            'the lock date affecting earlier lines.',
        )

        # Cron must report at least 6 skipped (one per locked line).
        self.assertGreaterEqual(
            result['skipped'],
            6,
            f"Expected >=6 skipped lines (one per locked period "
            f"line that raised UserError), got {result['skipped']}.",
        )
        # Cron must report success >= 6 (the six unlocked lines
        # posted successfully).
        self.assertGreaterEqual(
            result['success'],
            6,
            f"Expected >=6 successful lines (one per unlocked "
            f"period line), got {result['success']}.",
        )

    # =========================================================================
    # T-AM-004-08: Missing configuration -> lines skipped with error
    # =========================================================================

    @freeze_time('2024-06-30')
    def test_am_004_08_missing_config_skipped(self):
        """T-AM-004-08: Missing config / posting failure handled gracefully.

        Patches the depreciation line's ``action_post`` method to
        always raise ``UserError`` with a "configuration missing"
        message. The cron's per-line ``try/except UserError`` should
        catch this, log a warning, increment ``skipped``, and
        continue. Verifies:

            * The cron does NOT raise.
            * ``result['skipped'] > 0`` (the failed lines were counted).
            * No ``account.move`` was posted for the failed lines
              (line.state stays draft, line.move_id stays empty).
            * The cron's other-asset processing is not aborted (the
              try/except per-line ensures fault isolation).
        """
        asset = self._build_open_asset(
            name='AM-004-08 Missing Config Asset',
            acquisition_cost=1200.0,
            useful_life_unit='months',
            useful_life_months=12,
            useful_life_years=0,
            acquisition_date=date(2024, 1, 1),
            auto_post=True,
        )

        depr_line_model = type(self.env['account.asset.depreciation.line'])
        with patch.object(
            depr_line_model,
            'action_post',
            side_effect=UserError(
                'Configuration missing: simulated for AM-004-08',
            ),
        ):
            # Cron must NOT raise even though every line raises.
            result = self.env['account.asset'].\
                _cron_post_depreciation_entries()

        # All due lines should have been counted as skipped.
        self.assertGreater(
            result['skipped'],
            0,
            'Skipped count must be >0 when action_post raises UserError.',
        )
        # No lines should have been posted (every action_post raised).
        self.assertEqual(
            result['success'],
            0,
            'Success count must be 0 when every action_post raises.',
        )
        # No catastrophic errors -- the per-line UserError path is
        # the canonical "skip" path, not "error".
        self.assertEqual(result['errors'], 0)

        # Asset's lines remain draft (action_post raised before
        # write to state='posted').
        all_lines_draft = asset.depreciation_line_ids.filtered(
            lambda line: line.state == 'draft',
        )
        self.assertEqual(
            len(all_lines_draft),
            12,
            'All 12 lines should still be draft after a failing run.',
        )

    # =========================================================================
    # T-AM-004-09: Idempotency -- re-running cron is a no-op
    # =========================================================================

    @freeze_time('2024-12-31')
    def test_am_004_09_idempotency(self):
        """T-AM-004-09: Re-running cron does NOT re-post posted lines.

        The cron's domain filters depreciation lines to
        ``state='draft' AND depreciation_date <= today``. Once a
        line is posted, subsequent runs see it in ``state='posted'``
        and exclude it from the search. Verifies:

            * After first cron invocation, N lines are posted.
            * After second cron invocation, the SAME N lines remain
              posted (no duplicates).
            * The total ``account.move`` count for the asset
              after first run == count after second run.
            * ``result2['success'] == 0`` (nothing new posted).
        """
        asset = self._build_open_asset(
            name='AM-004-09 Idempotency Asset',
            acquisition_cost=1200.0,
            useful_life_unit='months',
            useful_life_months=12,
            useful_life_years=0,
            acquisition_date=date(2024, 1, 1),
            auto_post=True,
        )

        # First run: 12 lines (Jan-Dec 2024) due at 2024-12-31.
        result1 = self.env['account.asset']._cron_post_depreciation_entries()
        self.assertEqual(result1['success'], 12)
        self.assertEqual(result1['errors'], 0)
        posted_after_first = asset.depreciation_line_ids.filtered(
            lambda line: line.state == 'posted',
        )
        self.assertEqual(len(posted_after_first), 12)
        moves_after_first = self.env['account.move'].search([
            ('asset_id', '=', asset.id),
            ('asset_entry_type', '=', 'depreciation'),
        ])
        self.assertEqual(len(moves_after_first), 12)

        # Second run: should be a no-op (no new draft lines due).
        result2 = self.env['account.asset']._cron_post_depreciation_entries()
        self.assertEqual(
            result2['success'],
            0,
            'Re-running the cron must NOT post new lines (idempotency).',
        )
        self.assertEqual(result2['errors'], 0)
        posted_after_second = asset.depreciation_line_ids.filtered(
            lambda line: line.state == 'posted',
        )
        self.assertEqual(
            len(posted_after_second),
            12,
            'Posted line count must be unchanged on idempotent re-run.',
        )
        moves_after_second = self.env['account.move'].search([
            ('asset_id', '=', asset.id),
            ('asset_entry_type', '=', 'depreciation'),
        ])
        self.assertEqual(
            len(moves_after_second),
            12,
            'Move count must be unchanged on idempotent re-run.',
        )
        # Set comparison: same move IDs after both runs.
        self.assertEqual(
            set(moves_after_first.ids),
            set(moves_after_second.ids),
            'The same move records must persist across runs '
            '(no duplicates created).',
        )

    # =========================================================================
    # T-AM-004-10: Asset auto-closes when NBV <= salvage_value
    # =========================================================================

    def test_am_004_10_asset_auto_close_on_full_depreciation(self):
        """T-AM-004-10: Fully-depreciated asset transitions to 'close'.

        After the cron posts all due lines for an asset, if the
        recomputed ``net_book_value`` is at or below
        ``salvage_value``, the asset is auto-closed. Uses a
        short-lived 3-month asset so a single cron run on
        2024-04-30 posts ALL three lines and transitions the asset
        to ``state='close'``.
        """
        # Use a 3-month asset so all lines post in one cron call.
        asset = self._build_open_asset(
            name='AM-004-10 Short-Lived Asset',
            acquisition_cost=300.0,
            useful_life_unit='months',
            useful_life_months=3,
            useful_life_years=0,
            acquisition_date=date(2024, 1, 1),
            salvage_value=0.0,
            auto_post=True,
        )
        self.assertEqual(len(asset.depreciation_line_ids), 3)
        self.assertEqual(asset.state, 'open')

        # Frozen at 2024-04-30: all three lines (Jan, Feb, Mar) due.
        with freeze_time('2024-04-30'):
            result = self.env['account.asset'].\
                _cron_post_depreciation_entries()

        self.assertEqual(result['errors'], 0)
        self.assertGreaterEqual(result['success'], 3)
        # All 3 lines are posted.
        posted = asset.depreciation_line_ids.filtered(
            lambda line: line.state == 'posted',
        )
        self.assertEqual(len(posted), 3)
        # Auto-close: NBV reached salvage_value, state is now 'close'.
        # Force a fresh read to reflect the cron's state change.
        asset.invalidate_recordset()
        self.assertEqual(
            asset.state,
            'close',
            "Asset must auto-close when NBV <= salvage_value.",
        )
        self.assertAlmostEqual(asset.accumulated_depreciation, 300.0, places=2)
        self.assertAlmostEqual(asset.net_book_value, 0.0, places=2)

    # =========================================================================
    # T-AM-004-11: Fully-depreciated (closed) asset cron run is a no-op
    # =========================================================================

    @freeze_time('2025-06-30')
    def test_am_004_11_fully_depreciated_noop(self):
        """T-AM-004-11: Cron over a closed asset is a no-op (excluded by domain).

        The cron's search domain filters by ``state='open'``; closed
        assets are excluded. Verifies:

            * No new moves created for the closed asset.
            * No state transition (asset stays 'close').
            * Cron does not raise.
        """
        # Build a short-lived asset and run the cron at a date past
        # its useful life so all lines post and it auto-closes.
        asset = self._build_open_asset(
            name='AM-004-11 Pre-Closed Asset',
            acquisition_cost=300.0,
            useful_life_unit='months',
            useful_life_months=3,
            useful_life_years=0,
            acquisition_date=date(2024, 1, 1),
            salvage_value=0.0,
            auto_post=True,
        )
        # Confirm the asset is open before the first run.
        self.assertEqual(asset.state, 'open')

        # First run inside an inner freeze_time at 2024-04-30 so the
        # asset auto-closes; the outer @freeze_time('2025-06-30')
        # decorator governs the SECOND run below.
        with freeze_time('2024-04-30'):
            self.env['account.asset']._cron_post_depreciation_entries()
        asset.invalidate_recordset()
        self.assertEqual(asset.state, 'close', 'Asset must be closed.')

        # Capture move count after the close run.
        moves_after_close = self.env['account.move'].search([
            ('asset_id', '=', asset.id),
            ('asset_entry_type', '=', 'depreciation'),
        ])
        n_moves_after_close = len(moves_after_close)
        self.assertEqual(n_moves_after_close, 3)

        # Second run: cron at 2025-06-30. Closed asset must be a no-op.
        result = self.env['account.asset']._cron_post_depreciation_entries()
        self.assertEqual(result['errors'], 0)

        # State unchanged.
        asset.invalidate_recordset()
        self.assertEqual(asset.state, 'close')

        # No new moves created.
        moves_after_second_run = self.env['account.move'].search([
            ('asset_id', '=', asset.id),
            ('asset_entry_type', '=', 'depreciation'),
        ])
        self.assertEqual(
            len(moves_after_second_run),
            n_moves_after_close,
            'Re-running cron on a closed asset must NOT create new moves.',
        )

    # =========================================================================
    # T-AM-004-12: Per-asset fault tolerance (one bad asset, many good)
    # =========================================================================

    @freeze_time('2024-12-31')
    def test_am_004_12_fault_tolerance_one_bad_many_good(self):
        """T-AM-004-12: One bad asset does not block the rest of the batch.

        Patches ``action_post`` so that the FIRST call raises a
        non-``UserError`` exception (a generic ``RuntimeError``).
        This propagates past the cron's per-line ``except UserError``
        and is caught by the outer ``except Exception`` per-asset
        handler, which:

            * Triggers a SAVEPOINT rollback for that asset.
            * Increments ``errors`` by 1.
            * Continues with the next asset in the batch.

        Verifies:

            * ``result['errors'] >= 1`` (the bad asset was reported).
            * ``result['success'] >= N`` where N is the number of
              healthy lines posted across the remaining assets.
            * The bad asset's lines remain draft (savepoint rollback).
            * The healthy assets' lines are posted normally.
        """
        # Four assets. The first one's first line will fail.
        bad_asset = self._build_open_asset(
            name='AM-004-12 Bad Asset',
            acquisition_cost=1200.0,
            useful_life_unit='months',
            useful_life_months=12,
            useful_life_years=0,
            acquisition_date=date(2024, 1, 1),
            auto_post=True,
        )
        good_assets = [
            self._build_open_asset(
                name=f'AM-004-12 Good Asset {i}',
                acquisition_cost=1200.0,
                useful_life_unit='months',
                useful_life_months=12,
                useful_life_years=0,
                acquisition_date=date(2024, 1, 1),
                auto_post=True,
            )
            for i in range(3)
        ]

        depr_line_model = type(self.env['account.asset.depreciation.line'])
        # Capture the ORIGINAL action_post BEFORE patching it so the
        # side_effect can delegate to the unpatched implementation
        # for all calls beyond the first.
        original_action_post = depr_line_model.action_post
        call_state = {'count': 0}

        # Pre-built error message for EM101 (flake8-errmsg) compliance:
        # "Exception must not use a string literal, assign to variable
        # first." Assigning to a variable also satisfies TRY003.
        simulated_error_msg = 'AM-004-12 simulated catastrophic failure'

        def side_effect(self_recordset):
            """Raise on first call only; otherwise delegate to original."""
            call_state['count'] += 1
            if call_state['count'] == 1:
                # Non-UserError exception triggers per-asset error
                # path (outer except Exception in the cron).
                raise RuntimeError(simulated_error_msg)
            return original_action_post(self_recordset)

        with patch.object(
            depr_line_model,
            'action_post',
            autospec=True,
            side_effect=side_effect,
        ):
            result = self.env['account.asset'].\
                _cron_post_depreciation_entries()

        # The per-asset exception must have been counted.
        self.assertGreaterEqual(
            result['errors'],
            1,
            f"Expected errors>=1 (one bad asset), got "
            f"{result['errors']}.",
        )
        # The healthy assets must have posted their due lines:
        # 3 good assets * 12 due lines (Jan-Dec 2024) = 36 lines.
        self.assertGreaterEqual(
            result['success'],
            36,
            f"Expected success>=36 (3 good assets * 12 due lines), "
            f"got {result['success']}.",
        )

        # Bad asset's lines must remain draft due to savepoint rollback.
        bad_asset.invalidate_recordset()
        bad_draft_count = len(bad_asset.depreciation_line_ids.filtered(
            lambda line: line.state == 'draft',
        ))
        self.assertEqual(
            bad_draft_count,
            12,
            'Bad asset lines must remain draft after savepoint rollback.',
        )

        # Each healthy asset must have all 12 due lines posted.
        for good_asset in good_assets:
            good_asset.invalidate_recordset()
            good_posted = good_asset.depreciation_line_ids.filtered(
                lambda line: line.state == 'posted',
            )
            self.assertEqual(
                len(good_posted),
                12,
                f'Good asset {good_asset.name} must have 12 posted '
                f'lines despite the bad asset failure.',
            )

    # =========================================================================
    # T-AM-004-13: *** GATE 13 *** ir.cron registered and invokable
    # =========================================================================

    def test_am_004_13_cron_registered_and_invokable(self):
        """T-AM-004-13: GATE 13 -- cron XML record reachable & callable.

        This is the canonical AAP Rule R-06 / Gate 13 enforcement test:

            (1) The ``ir.cron`` record with XML id
                ``account_asset_management.ir_cron_asset_depreciation``
                MUST be resolvable via ``self.env.ref(...)`` after
                module install (proving Odoo's module loader reads
                ``data/depreciation_cron.xml``).
            (2) The cron's metadata MUST match the contract documented
                in the depreciation_cron.xml file:
                  * ``name``: 'Assets: Post Depreciation Entries'
                  * ``model_id.model``: 'account.asset'
                  * ``state``: 'code' (Python code cron)
                  * ``code``: 'model._cron_post_depreciation_entries()'
                  * ``interval_number``: 1
                  * ``interval_type``: 'days'
                  * ``active``: True
                  * ``priority``: 5
            (3) ``method_direct_trigger()`` (the canonical "Run
                Manually" button binding from
                ``odoo/addons/base/models/ir_cron.py:150``) MUST
                execute without raising and return ``True``.

        Note: ``numbercall`` and ``doall`` fields, mentioned in the
        agent prompt, were removed from ``ir.cron`` in Odoo 19.0
        (see ``odoo/addons/base/models/ir_cron.py`` -- the model
        no longer declares these fields). This test therefore does
        NOT assert those fields; doing so would always fail with
        ``KeyError`` regardless of cron registration correctness.
        """
        # (1) Resolve the cron via XML id. A failure here would mean
        # the module's data/depreciation_cron.xml was not loaded.
        cron = self.env.ref(
            'account_asset_management.ir_cron_asset_depreciation',
            raise_if_not_found=False,
        )
        self.assertTrue(
            cron,
            "ir.cron record 'account_asset_management."
            "ir_cron_asset_depreciation' MUST be registered "
            "(Gate 13 / R-06).",
        )
        self.assertEqual(cron._name, 'ir.cron')

        # (2) Metadata contract assertions.
        self.assertEqual(cron.name, 'Assets: Post Depreciation Entries')
        self.assertEqual(
            cron.model_id.model,
            'account.asset',
            "Cron's model_id.model MUST resolve to 'account.asset'.",
        )
        self.assertEqual(
            cron.state,
            'code',
            "Cron state MUST be 'code' (Python-code action).",
        )
        self.assertEqual(
            cron.code.strip(),
            'model._cron_post_depreciation_entries()',
            "Cron code MUST invoke "
            "model._cron_post_depreciation_entries().",
        )
        self.assertEqual(cron.interval_number, 1)
        self.assertEqual(cron.interval_type, 'days')
        self.assertTrue(
            cron.active,
            'Cron MUST be active by default after install.',
        )
        self.assertEqual(cron.priority, 5)
        # nextcall must be a datetime (not None) so the scheduler
        # can compute when the cron is due.
        self.assertIsNotNone(cron.nextcall)

        # (3) Manual invocation via the canonical
        # ``method_direct_trigger`` binding.
        # Returns True on success; returns an
        # ``ir.actions.client / display_exception`` dict on captured
        # ERROR. We require True on a healthy database.
        result = cron.method_direct_trigger()
        self.assertEqual(
            result,
            True,
            f'cron.method_direct_trigger() must return True; got '
            f'{result!r}. A non-True return indicates the cron '
            f'execution captured an ERROR-level log record.',
        )

        # As an equivalence check, the cron's target method should
        # also be directly callable from the model. After
        # method_direct_trigger executed once, a re-run of the
        # method should be a clean no-op (no errors).
        direct_result = self.env['account.asset'].\
            _cron_post_depreciation_entries()
        self.assertIsInstance(direct_result, dict)
        self.assertEqual(direct_result['errors'], 0)

    # =========================================================================
    # T-AM-004-14: Performance -- 100 assets processed in <30s
    # =========================================================================

    @freeze_time('2024-12-31')
    def test_am_004_14_perf_100_assets(self):
        """T-AM-004-14: 100 assets cron run completes in <30 seconds.

        Per the AAP performance budget for AM-004
        ("Batch processing (100 assets) < 30 seconds"), this test
        builds 100 confirmed assets each with 12 due monthly lines
        and verifies the cron completes in <30s wall-clock time.
        Uses ``time.perf_counter()`` for high-resolution monotonic
        timing (immune to NTP / system clock adjustments).
        """
        # Toggle the category to auto_post so all lines post end-to-end.
        self.asset_category_it.auto_post_depreciation = True

        # Build 100 assets via individual ``_create_basic_asset`` calls.
        # Bulk creation with Odoo's ORM is substantially slower than
        # batched create due to per-record onchange / constraint
        # processing; both forms are acceptable.
        assets = self.env['account.asset']
        for i in range(100):
            asset = self._create_basic_asset(
                self,
                name=f'AM-004-14 Perf Asset {i}',
                acquisition_cost=1200.0,
                useful_life_unit='months',
                useful_life_months=12,
                useful_life_years=0,
                acquisition_date=date(2024, 1, 1),
                category_id=self.asset_category_it.id,
                salvage_value=0.0,
            )
            assets |= asset
        # Confirm all 100 assets so their depreciation_line_ids are
        # populated and they're 'open' (so the cron's domain matches).
        assets.action_confirm()

        # Time the cron invocation.
        t0 = time.perf_counter()
        result = self.env['account.asset']._cron_post_depreciation_entries()
        elapsed = time.perf_counter() - t0

        self.assertEqual(result['errors'], 0)
        # 100 assets * 12 due lines each = 1,200 successful posts.
        self.assertGreaterEqual(result['success'], 1200)

        self.assertLess(
            elapsed,
            30.0,
            f'AM-004 perf budget: 100 assets must complete in <30s; '
            f'actually took {elapsed:.2f}s.',
        )
        _logger.info(
            'AM-004-14 perf: 100 assets processed in %.2fs '
            '(budget: 30.0s).',
            elapsed,
        )

    # =========================================================================
    # T-AM-004-15: Performance -- 1,000 assets <5 minutes (skippable)
    # =========================================================================

    @freeze_time('2024-12-31')
    def test_am_004_15_perf_1000_assets(self):
        """T-AM-004-15: 1,000 assets in <5 minutes (env-gated slow test).

        Per the AAP performance budget for AM-004 ("Batch processing
        (1,000 assets) < 5 minutes"), this test verifies the cron
        scales to portfolio sizes representative of mid-market
        accounting installations. The fixture construction alone
        (1,000 confirmed assets with 12 lines each) takes several
        minutes, so the test is gated by the ``SLOW_TESTS``
        environment variable. Enable with::

            SLOW_TESTS=1 pytest -k test_am_004_15

        in CI / pre-release validation; CI default-skips it to
        keep build wall-clock time reasonable.
        """
        if not os.environ.get('SLOW_TESTS'):
            self.skipTest(
                'Slow performance test (1000 assets) skipped; '
                'set SLOW_TESTS=1 to enable.',
            )

        self.asset_category_it.auto_post_depreciation = True

        # Build 1,000 confirmed assets.
        assets = self.env['account.asset']
        for i in range(1000):
            asset = self._create_basic_asset(
                self,
                name=f'AM-004-15 Perf Asset {i}',
                acquisition_cost=1200.0,
                useful_life_unit='months',
                useful_life_months=12,
                useful_life_years=0,
                acquisition_date=date(2024, 1, 1),
                category_id=self.asset_category_it.id,
                salvage_value=0.0,
            )
            assets |= asset
        assets.action_confirm()

        t0 = time.perf_counter()
        result = self.env['account.asset']._cron_post_depreciation_entries()
        elapsed = time.perf_counter() - t0

        self.assertEqual(result['errors'], 0)
        self.assertGreaterEqual(result['success'], 12000)

        self.assertLess(
            elapsed,
            300.0,
            f'AM-004 perf budget: 1,000 assets must complete in <5min; '
            f'actually took {elapsed:.2f}s.',
        )
        _logger.info(
            'AM-004-15 perf: 1,000 assets processed in %.2fs '
            '(budget: 300.0s).',
            elapsed,
        )

    def test_am_004_16_action_confirm_raises_on_non_draft_asset(self):
        """QA Checkpoint 10 Issue 9 (negative-path coverage): the
        ``account.asset.action_confirm`` method must raise
        ``UserError`` when called on an asset that is already in
        ``open`` (or any non-``draft``) state.

        The AM-004 cron only operates on ``state='open'`` assets, so
        the upstream confirmation invariant ("draft -> open
        transition is one-way; calling action_confirm on already-open
        assets is a programming error") is the prerequisite for the
        cron's correctness contract. Together with the existing
        positive paths in ``test_am_004_01_cron_posts_scheduled_entries``
        these tests document the contract:

          1. Only ``draft`` assets can transition to ``open``
             (this test, ``assertRaises``).
          2. The cron only posts depreciation lines on ``open``
             assets and treats lines that fail to post as ``skipped``
             via per-line UserError handling (covered by
             ``test_am_004_07_locked_period_skipped``).
        """
        asset = self._build_open_asset()
        # Pre-condition: asset must be 'open' (the canonical fixture
        # state from _build_open_asset).
        self.assertEqual(
            asset.state, 'open',
            'Fixture sanity: _build_open_asset returns an open asset.',
        )

        # Calling action_confirm on an already-open asset must raise
        # UserError with the asset name and current state quoted in
        # the message so the operator can identify the offending
        # record at a glance.
        with self.assertRaises(UserError) as ctx:
            asset.action_confirm()
        msg = str(ctx.exception)
        self.assertIn(
            'draft',
            msg.lower(),
            'UserError message must reference the required draft '
            'state; got: %r' % msg,
        )
        # The asset name (or at least a portion) must appear in the
        # message so the error is actionable for batch operations.
        self.assertIn(
            'open', msg.lower(),
            'UserError message must mention the current state '
            '(open) so the operator knows why the transition was '
            'blocked; got: %r' % msg,
        )
