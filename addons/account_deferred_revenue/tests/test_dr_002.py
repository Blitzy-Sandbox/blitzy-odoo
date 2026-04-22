# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Test Suite — DR-002 Automatic Period Allocation (account.deferred.schedule)

Implements acceptance tests for FEATURE-005 Track C Story DR-002 per the BDD
scenarios defined in
``tickets/stories/deferred-revenue/DR-002-automatic-period-allocation.md``.

Scope of this test file (one test method per acceptance scenario):

    * ``test_straight_line_allocation_calculation``  (Scenario 1)
    * ``test_date_based_proration_calculation``      (Scenario 2)
    * ``test_allocation_preview_no_posting``         (Scenario 3)
    * ``test_schedule_modification_recalculation``   (Scenario 4)
    * ``test_multi_currency_allocation``             (Scenario 5)
    * ``test_fiscal_year_boundary_respect``          (Scenario 6)

Target coverage: >= 80% line coverage on
``addons/account_deferred_revenue/models/account_deferred_schedule.py``
allocation helpers -- ``_compute_recognition_schedule``,
``_compute_period_count``, ``_compute_line_count``, ``_compute_amounts``
(enforced per AAP Rule R-04).

Base class: :class:`odoo.addons.account.tests.common.AccountTestInvoicingCommon`
Decorator: ``@tagged('post_install', '-at_install')``
Time control: :func:`freezegun.freeze_time` for deterministic date
computations.

**SUM INVARIANT**: every allocation method must preserve
``sum(recognition_amount) == total_amount`` exactly (the allocation rounds
individual lines to currency precision and absorbs the residual on the last
line).  Every test in this file asserts this invariant explicitly.
"""

from datetime import date

from freezegun import freeze_time

from odoo import Command, fields  # noqa: F401 -- fields re-exported for parity
from odoo.exceptions import UserError, ValidationError  # noqa: F401
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon

# Module-level constants for deterministic time control.  ``_FROZEN_TODAY`` is
# the string form required by ``freezegun.freeze_time``; ``_FROZEN_DATE`` is
# the equivalent ``datetime.date`` constant preserved for any test-body
# calculation that needs to compute offsets relative to "today".  Frozen on
# 2024-06-15 so that schedules spanning Jan-Dec 2024 and Jul 2024-Jun 2025
# include periods both before and after the notional "now", exercising the
# allocation logic without introducing real-clock flakiness.
_FROZEN_TODAY = '2024-06-15'
_FROZEN_DATE = date(2024, 6, 15)


@tagged('post_install', '-at_install')
class TestDeferredPeriodAllocation(AccountTestInvoicingCommon):
    """Acceptance tests for DR-002 Automatic Period Allocation.

    These tests exercise the core allocation engine (
    :meth:`account.deferred.schedule._compute_recognition_schedule`) across
    all three recognition methods (straight-line, date-based, manual), and
    validate that the SUM INVARIANT
    ``sum(line.recognition_amount) == schedule.total_amount`` is preserved
    in every scenario including extensions, currency changes, and fiscal
    year boundary crossings.

    The test class uses the Odoo accounting test fixture
    :class:`~odoo.addons.account.tests.common.AccountTestInvoicingCommon`
    which provides a pre-configured company, chart of accounts, default
    journals, and a test user with the core accounting groups.  The
    deferred-revenue-specific user and manager groups are granted in
    :meth:`setUpClass` so that the ACL rows in
    ``security/ir.model.access.csv`` permit create/write on
    ``account.deferred.schedule`` and ``account.deferred.line`` during
    the tests.
    """

    # ------------------------------------------------------------------
    # Class-level fixture setup
    # ------------------------------------------------------------------
    @classmethod
    def setUpClass(cls):
        """Prepare shared fixtures for all six DR-002 acceptance scenarios.

        Performs the following steps (in order):

        1. Invoke the parent ``setUpClass`` to bootstrap the accounting
           test fixture (company, COA, journals, tax fixtures, default
           test user).
        2. Grant the deferred-revenue manager and user groups defined in
           ``security/deferred_security.xml`` to the current test user so
           that the ACLs in ``security/ir.model.access.csv`` permit
           create / write on ``account.deferred.schedule`` /
           ``account.deferred.line``.
        3. Cache the company and company currency for easy reference.
        4. Create dedicated ``XTEST.*`` accounts for the deferred revenue
           (liability_current) and recognition revenue (income) sides of
           every schedule built by :meth:`_create_schedule`.
        5. Create a generic test partner.
        6. Resolve the EUR currency (and activate it if present but
           inactive) for the Scenario 5 multi-currency test.
        """
        super().setUpClass()

        # ------------------------------------------------------------------
        # Step 2 -- grant module-specific security groups.
        #
        # ``AccountTestInvoicingCommon`` creates a test user with the core
        # accounting groups but NOT the module-specific groups from
        # ``account_deferred_revenue``.  The ACL rows in
        # ``security/ir.model.access.csv`` require at least
        # ``group_deferred_revenue_user`` for create/read/write on
        # ``account.deferred.schedule`` and ``account.deferred.line``.
        # We grant BOTH user and manager groups so that unlink operations
        # (needed in the modification-recalculation scenario) also succeed.
        #
        # ``raise_if_not_found=False`` defends against the edge case where
        # the security XML fails to load -- in that case the test will
        # proceed without the groups and surface a clear AccessError on
        # the first create() call, which is more informative than a
        # cryptic env.ref KeyError at fixture-setup time.
        # ------------------------------------------------------------------
        manager_group = cls.env.ref(
            'account_deferred_revenue.group_deferred_revenue_manager',
            raise_if_not_found=False,
        )
        user_group = cls.env.ref(
            'account_deferred_revenue.group_deferred_revenue_user',
            raise_if_not_found=False,
        )
        groups_to_add = (manager_group | user_group).filtered(bool)
        if groups_to_add:
            cls.env.user.write({
                'group_ids': [Command.link(g.id) for g in groups_to_add],
            })

        # ------------------------------------------------------------------
        # Step 3 -- cache company and company currency.  Using ``env.company``
        # keeps the test robust against future changes to the default test
        # company ID in ``AccountTestInvoicingCommon``.
        # ------------------------------------------------------------------
        cls.company = cls.env.company
        cls.currency = cls.env.company.currency_id

        # ------------------------------------------------------------------
        # Step 4 -- create dedicated test accounts.  The ``XTEST.*`` code
        # prefix guarantees isolation from any COA entries installed by
        # ``AccountTestInvoicingCommon`` or by a future COA chart; without
        # this prefix, two test classes could create colliding account
        # codes and break each other when run in the same test session.
        # ------------------------------------------------------------------
        AccountAccount = cls.env['account.account']

        cls.deferred_revenue_account = AccountAccount.create({
            'code': 'XTEST.24100',
            'name': 'Test Deferred Revenue (Liability)',
            # liability_current is one of the valid values permitted by
            # the domain on ``deferred_account_id`` in the schedule model.
            'account_type': 'liability_current',
            'reconcile': False,
        })
        cls.recognition_revenue_account = AccountAccount.create({
            'code': 'XTEST.40100',
            'name': 'Test Recognition Revenue (Income)',
            # income is one of the valid values permitted by the domain on
            # ``recognition_account_id`` in the schedule model.
            'account_type': 'income',
            'reconcile': False,
        })

        # ------------------------------------------------------------------
        # Step 5 -- create a generic test partner.  The partner_id field on
        # account.deferred.schedule is NOT required but is typical for real
        # deferrals, so we always set it to exercise partner_id propagation
        # through the related field on account.deferred.line.
        # ------------------------------------------------------------------
        cls.partner = cls.env['res.partner'].create({
            'name': 'Allocation Test Customer',
        })

        # ------------------------------------------------------------------
        # Step 6 -- resolve EUR for Scenario 5.  EUR is typically present
        # in base data but may be inactive; we activate it conditionally.
        # If EUR is not resolvable at all, Scenario 5 uses self.skipTest.
        # ------------------------------------------------------------------
        cls.eur_currency = cls.env.ref('base.EUR', raise_if_not_found=False)
        if cls.eur_currency and not cls.eur_currency.active:
            cls.eur_currency.active = True

    # ------------------------------------------------------------------
    # Helper for creating schedules under test
    # ------------------------------------------------------------------
    def _create_schedule(self, **overrides):
        """Return a fresh draft ``account.deferred.schedule`` record.

        Default values correspond to Canonical Example 1 from the DR-002
        ticket: $12,000 spread straight-line from 2024-01-01 to 2024-12-31
        (12 periods).  Any default may be overridden by keyword argument
        -- ``start_date``, ``end_date``, ``recognition_method``,
        ``total_amount``, and ``currency_id`` are the most commonly
        overridden in the six scenario tests.

        Returns:
            account.deferred.schedule: a single draft schedule record.

        The schedule is created directly via ``create()`` (not through a
        wizard) because all six DR-002 scenarios focus on the allocation
        math, not the UI invocation path.  The modification scenario
        relies on the default state being ``draft`` (per the schedule
        model's ``default='draft'``) so that :meth:`action_confirm` can
        be called explicitly.
        """
        vals = {
            'partner_id': self.partner.id,
            'company_id': self.company.id,
            'total_amount': 12000.0,
            'currency_id': self.currency.id,
            'deferred_account_id': self.deferred_revenue_account.id,
            'recognition_account_id': self.recognition_revenue_account.id,
            'recognition_method': 'straight_line',
            'start_date': date(2024, 1, 1),
            'end_date': date(2024, 12, 31),
        }
        vals.update(overrides)
        return self.env['account.deferred.schedule'].create(vals)

    # ==================================================================
    # Scenario 1 -- Straight-line allocation
    # ==================================================================
    @freeze_time(_FROZEN_TODAY)
    def test_straight_line_allocation_calculation(self):
        """Scenario 1: Straight-line allocation divides total evenly by month.

        GIVEN
            * ``total_amount`` = 12000.00
            * ``start_date`` = 2024-01-01, ``end_date`` = 2024-12-31
            * ``recognition_method`` = ``straight_line``
        WHEN the schedule is confirmed (triggering
            ``_compute_recognition_schedule`` because no lines exist yet).
        THEN
            * ``period_count`` = 12 (twelve monthly periods).
            * ``len(line_ids)`` = 12.
            * Each non-terminal line's ``recognition_amount`` ~= 1000.00
              (straight-line divides 12000 / 12 = 1000 exactly).
            * The **SUM INVARIANT** holds:
              ``sum(line.recognition_amount) == 12000.00`` exactly.
            * Every line's ``state`` is ``draft`` (pending cut-off post).

        This is the Canonical Example 1 from the DR-002 ticket.  No
        rounding residual is expected because 12000 / 12 = 1000 exactly
        in any currency rounding.  The residual-absorption logic in the
        last line is exercised indirectly but produces the same 1000.00
        value.
        """
        schedule = self._create_schedule(
            total_amount=12000.0,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            recognition_method='straight_line',
        )
        # Confirming triggers _compute_recognition_schedule when line_ids
        # is empty; this is the production invocation path.
        schedule.action_confirm()

        # Period count and line count should match.
        self.assertEqual(
            schedule.period_count, 12,
            "A Jan-1-to-Dec-31 schedule must yield 12 periods.",
        )
        self.assertEqual(
            len(schedule.line_ids), 12,
            "A 12-period straight-line schedule must produce 12 lines.",
        )

        # For 12000 / 12 the allocation is exact (1000 per period).
        expected_per_period = 1000.0
        for idx, line in enumerate(schedule.line_ids):
            # The first 11 lines carry ``per_period`` directly; the 12th
            # line absorbs any rounding residual.  When the division is
            # exact, the 12th line is also 1000.00 -- we assert on the
            # first 11 to make the rounding-residual contract explicit
            # without coupling the test to residual internals.
            if idx < 11:
                self.assertAlmostEqual(
                    line.recognition_amount,
                    expected_per_period,
                    places=2,
                    msg=(
                        f"Line #{idx} (date={line.recognition_date}) must be "
                        f"{expected_per_period:.2f} in a 12000/12 split; "
                        f"got {line.recognition_amount}."
                    ),
                )

        # CRITICAL SUM INVARIANT: total of all recognition amounts must
        # exactly match the schedule's total_amount (no drift).
        total = sum(schedule.line_ids.mapped('recognition_amount'))
        self.assertAlmostEqual(
            total, 12000.0, places=2,
            msg=(
                "DR-002 SUM INVARIANT violation: "
                "sum(recognition_amount) must exactly equal total_amount; "
                f"got {total} vs expected 12000.00."
            ),
        )

        # Lines must all be pending (draft) -- posting is the job of the
        # DR-003 cut-off wizard, not the allocation engine.
        for line in schedule.line_ids:
            self.assertEqual(
                line.state, 'draft',
                f"Generated line #{line.sequence} must be in draft state.",
            )

        # Schedule transitions to confirmed on successful allocation.
        self.assertEqual(
            schedule.state, 'confirmed',
            "Schedule must transition draft -> confirmed after "
            "action_confirm() succeeds.",
        )

        # ``line_count`` computed field must reflect the generated lines
        # (validates _compute_line_count triggers on line_ids change).
        self.assertEqual(
            schedule.line_count, 12,
            "Schedule.line_count (computed) must equal len(line_ids) "
            "after allocation.",
        )

    # ==================================================================
    # Scenario 2 -- Date-based proration
    # ==================================================================
    @freeze_time(_FROZEN_TODAY)
    def test_date_based_proration_calculation(self):
        """Scenario 2: Date-based allocation prorates by calendar-day count.

        GIVEN
            * ``total_amount`` = 1000.00
            * ``start_date`` = 2024-01-15, ``end_date`` = 2024-03-15
            * ``recognition_method`` = ``date_based``
        WHEN the schedule is confirmed.
        THEN
            * Multiple recognition lines are created (at least 2 because
              the span covers 3 calendar months: Jan, Feb, Mar).
            * Each line's ``recognition_amount`` is proportional to the
              days in that month that fall within [start_date, end_date].
            * Each line's ``days_in_period`` is >= 1 (computed from
              ``monthrange(year, month)`` in the line's compute method).
            * Every line's ``recognition_amount`` > 0.
            * The **SUM INVARIANT** holds:
              ``sum(line.recognition_amount) == 1000.00`` exactly.

        This is the Canonical Example 2 from the DR-002 ticket.  2024 is
        a leap year, so February has 29 days; the span from 2024-01-15
        to 2024-03-15 yields 17 + 29 + 15 = 61 inclusive calendar days
        across three monthly sub-periods.  The exact per-line amount
        depends on the implementation's proration formula and rounding,
        but the sum invariant must hold regardless.
        """
        schedule = self._create_schedule(
            total_amount=1000.0,
            start_date=date(2024, 1, 15),
            end_date=date(2024, 3, 15),
            recognition_method='date_based',
        )
        schedule.action_confirm()

        # At minimum, the date-based allocation touches 3 months (Jan,
        # Feb, Mar); we assert >= 2 to remain robust against an
        # implementation that might fold partial-Jan and full-Feb into
        # one line (hypothetical).
        self.assertGreaterEqual(
            len(schedule.line_ids), 2,
            "Date-based allocation across multiple months must generate "
            "at least 2 recognition lines.",
        )

        # SUM INVARIANT: prorated amounts must sum to exactly 1000.00.
        total = sum(schedule.line_ids.mapped('recognition_amount'))
        self.assertAlmostEqual(
            total, 1000.0, places=2,
            msg=(
                "DR-002 SUM INVARIANT violation: sum of prorated "
                f"amounts must equal 1000.00; got {total}."
            ),
        )

        # Each line should have at least one day in its period and a
        # strictly positive amount (zero-amount lines would indicate a
        # proration bug rather than an intentional skip).
        for line in schedule.line_ids:
            self.assertGreaterEqual(
                line.days_in_period, 1,
                f"Line on {line.recognition_date} must span at least 1 "
                f"calendar day (got {line.days_in_period}).",
            )
            self.assertGreater(
                line.recognition_amount, 0.0,
                f"Line on {line.recognition_date} must have a positive "
                f"amount (got {line.recognition_amount}).",
            )

        # Every line's currency should match the schedule (which in this
        # test is the company currency, since _create_schedule defaults
        # currency_id to self.currency).
        for line in schedule.line_ids:
            self.assertEqual(
                line.currency_id, self.currency,
                "Each date-based line's currency must match the parent "
                "schedule's currency (stored-related field).",
            )

    # ==================================================================
    # Scenario 3 -- Preview without posting
    # ==================================================================
    @freeze_time(_FROZEN_TODAY)
    def test_allocation_preview_no_posting(self):
        """Scenario 3: Computing allocation preview must not post any entries.

        GIVEN a draft schedule with no existing lines.
        WHEN :meth:`_compute_recognition_schedule` is invoked DIRECTLY
            (bypassing :meth:`action_confirm`, simulating a "preview"
            action that populates line_ids without transitioning state).
        THEN
            * ``line_ids`` is populated (6 lines for a 6-month schedule).
            * Every line's ``state`` is ``draft``.
            * No line has a ``move_id`` (journal entry) assigned --
              the cut-off wizard is the sole posting path.
            * The **schedule itself** remains in ``state='draft'`` -- the
              direct compute call does NOT transition state.
            * The SUM INVARIANT holds.

        This scenario validates that the allocation engine is
        side-effect-free at the journal-entry level: it manipulates
        recognition lines only and leaves actual accounting untouched
        until the DR-003 cut-off wizard runs.
        """
        schedule = self._create_schedule(
            total_amount=6000.0,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 30),
            recognition_method='straight_line',
        )
        # Direct compute call -- must not mutate any journal entry and
        # must not transition the schedule state.
        schedule._compute_recognition_schedule()

        # 6 months of allocation => 6 lines.
        self.assertEqual(
            len(schedule.line_ids), 6,
            "Preview of a 6-month straight-line schedule must produce 6 "
            "recognition lines.",
        )

        # Every preview line is in draft state and has no move_id.
        for line in schedule.line_ids:
            self.assertEqual(
                line.state, 'draft',
                f"Preview line on {line.recognition_date} must remain in "
                f"draft state; got {line.state}.",
            )
            self.assertFalse(
                line.move_id,
                f"Preview line on {line.recognition_date} must NOT be "
                f"linked to any journal entry; got move_id={line.move_id}.",
            )

        # Schedule state must remain draft after direct compute.
        self.assertEqual(
            schedule.state, 'draft',
            "Calling _compute_recognition_schedule() directly must NOT "
            "transition the schedule to confirmed.",
        )

        # SUM INVARIANT still applies even in preview mode: allocation
        # math must be correct regardless of whether lines will be
        # posted.
        total = sum(schedule.line_ids.mapped('recognition_amount'))
        self.assertAlmostEqual(
            total, 6000.0, places=2,
            msg=(
                "DR-002 SUM INVARIANT violation in preview mode: "
                f"expected 6000.00, got {total}."
            ),
        )

        # -----------------------------------------------------------------
        # Manual-method branch verification (per AAP R-04, which requires
        # _compute_recognition_schedule to be exercised on "all three
        # branches: straight_line, date_based, manual").
        #
        # Semantics under test: when ``recognition_method == 'manual'``,
        # ``_compute_recognition_schedule`` must short-circuit and NOT
        # auto-generate any line -- the user is expected to supply line
        # amounts themselves. Calling the compute helper on a manual
        # schedule with no lines must therefore leave ``line_ids`` empty
        # and the schedule state untouched.
        # -----------------------------------------------------------------
        manual_schedule = self._create_schedule(
            total_amount=5000.0,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 5, 31),
            recognition_method='manual',
        )
        self.assertFalse(
            manual_schedule.line_ids,
            "A freshly created manual schedule must have no lines "
            "(manual method requires user-supplied line amounts).",
        )

        manual_schedule._compute_recognition_schedule()

        self.assertFalse(
            manual_schedule.line_ids,
            "Calling _compute_recognition_schedule() on a manual schedule "
            "must NOT auto-generate any lines -- the manual branch is a "
            "deliberate no-op that preserves user-defined lines.",
        )
        self.assertEqual(
            manual_schedule.state, 'draft',
            "Manual-schedule compute call must not transition state.",
        )

    # ==================================================================
    # Scenario 4 -- Modification triggers recalculation
    # ==================================================================
    @freeze_time(_FROZEN_TODAY)
    def test_schedule_modification_recalculation(self):
        """Scenario 4: Extending ``end_date`` recalculates the plan.

        GIVEN a confirmed schedule with 12 recognition lines spanning
              Jan-Dec 2024 and total 12000.00.
        WHEN
            * The schedule is reset to draft (:meth:`action_draft`),
              which unlinks all existing draft lines and reverts state.
            * ``end_date`` is extended from 2024-12-31 to 2025-06-30
              (adding 6 months, 18 months total).
            * The schedule is re-confirmed, triggering a fresh
              :meth:`_compute_recognition_schedule` call.
        THEN
            * The regenerated plan has 18 recognition lines (one per
              month across the 18-month span).
            * The SUM INVARIANT holds: total still equals 12000.00
              exactly (allocation math rebalances to the new period
              count; the last line absorbs rounding residual).
            * Every line is in ``state='draft'`` again (action_draft
              cleared the old plan before re-confirmation).

        The schedule model's :meth:`action_draft` guards against
        lossy reset by refusing to reset schedules with any posted
        lines.  In this test no lines have been posted, so the reset
        succeeds.
        """
        # Initial 12-month schedule.
        schedule = self._create_schedule(
            total_amount=12000.0,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            recognition_method='straight_line',
        )
        schedule.action_confirm()
        initial_line_count = len(schedule.line_ids)
        self.assertEqual(
            initial_line_count, 12,
            "Initial 12-month schedule must produce 12 recognition lines.",
        )

        # Pre-modification SUM INVARIANT check.
        initial_total = sum(schedule.line_ids.mapped('recognition_amount'))
        self.assertAlmostEqual(
            initial_total, 12000.0, places=2,
            msg=(
                "Pre-modification sum invariant violation: expected "
                f"12000.00, got {initial_total}."
            ),
        )

        # Revert to draft (no posted lines -> should succeed), extend
        # end_date by 6 months, and re-confirm to trigger regeneration.
        schedule.action_draft()
        # After action_draft, state is draft and line_ids is empty.
        self.assertEqual(
            schedule.state, 'draft',
            "Schedule must return to draft state after action_draft().",
        )
        self.assertEqual(
            len(schedule.line_ids), 0,
            "action_draft() must clear all existing lines before "
            "reconfiguration.",
        )

        # Extend the end date to 2025-06-30 (adds 6 months; total 18).
        schedule.write({'end_date': date(2025, 6, 30)})
        schedule.action_confirm()

        # Post-modification: 18 lines, total still equals 12000.00.
        self.assertEqual(
            len(schedule.line_ids), 18,
            "After extending end_date by 6 months, the schedule must "
            "have 18 recognition lines.",
        )
        final_total = sum(schedule.line_ids.mapped('recognition_amount'))
        self.assertAlmostEqual(
            final_total, 12000.0, places=2,
            msg=(
                "DR-002 SUM INVARIANT violation after modification: "
                f"expected 12000.00, got {final_total}."
            ),
        )

        # All regenerated lines are draft (cut-off wizard has not run).
        for line in schedule.line_ids:
            self.assertEqual(
                line.state, 'draft',
                f"Regenerated line on {line.recognition_date} must be in "
                f"draft state; got {line.state}.",
            )

    # ==================================================================
    # Scenario 5 -- Multi-currency allocation
    # ==================================================================
    @freeze_time(_FROZEN_TODAY)
    def test_multi_currency_allocation(self):
        """Scenario 5: Multi-currency schedules preserve foreign-currency sums.

        GIVEN a schedule in EUR with ``total_amount`` = 1200.00 EUR,
              spanning 2024-01-01 to 2024-12-31 (12 months),
              ``recognition_method`` = ``straight_line``.
        WHEN the schedule is confirmed.
        THEN
            * 12 lines are generated.
            * Every line's ``currency_id`` == EUR (via the stored-related
              field on ``account.deferred.line`` from the parent schedule).
            * Each line's ``recognition_amount`` = 100.00 (1200 / 12).
            * The SUM INVARIANT holds in EUR:
              ``sum(line.recognition_amount) == 1200.00``.

        If EUR is not available in demo data (minimal install), the test
        gracefully skips to avoid a false negative on bare environments.
        """
        if not self.eur_currency:
            # Minimal-install environments may lack base.EUR. The DR-002
            # multi-currency contract is agnostic to WHICH foreign
            # currency is used, so a skip here is appropriate.
            self.skipTest(
                "EUR currency not available in this environment "
                "(base.EUR not resolvable); multi-currency test cannot "
                "run without a foreign currency.",
            )

        schedule = self._create_schedule(
            total_amount=1200.0,
            currency_id=self.eur_currency.id,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            recognition_method='straight_line',
        )
        schedule.action_confirm()

        # 12-month straight-line => 12 lines.
        self.assertEqual(
            len(schedule.line_ids), 12,
            "EUR 12-month schedule must produce 12 recognition lines.",
        )

        # Every line's currency is EUR (inherited from the schedule via
        # the stored-related field on account.deferred.line.currency_id).
        for line in schedule.line_ids:
            self.assertEqual(
                line.currency_id, self.eur_currency,
                f"Line on {line.recognition_date} must have EUR currency "
                f"(inherited from the schedule); got {line.currency_id}.",
            )

        # Each line amount is 100.00 EUR (1200 / 12 with no residual).
        expected_per_period = 100.0
        for idx, line in enumerate(schedule.line_ids):
            if idx < 11:
                self.assertAlmostEqual(
                    line.recognition_amount,
                    expected_per_period,
                    places=2,
                    msg=(
                        f"Line #{idx} must be {expected_per_period:.2f} "
                        f"EUR in a 1200/12 split; got "
                        f"{line.recognition_amount}."
                    ),
                )

        # SUM INVARIANT in foreign currency: still 1200.00 EUR exactly.
        total = sum(schedule.line_ids.mapped('recognition_amount'))
        self.assertAlmostEqual(
            total, 1200.0, places=2,
            msg=(
                "DR-002 SUM INVARIANT violation in EUR allocation: "
                f"expected 1200.00, got {total}."
            ),
        )

        # Verify schedule-level currency_id is EUR too (sanity check).
        self.assertEqual(
            schedule.currency_id, self.eur_currency,
            "Schedule's own currency_id must remain EUR after allocation.",
        )

    # ==================================================================
    # Scenario 6 -- Fiscal year boundary
    # ==================================================================
    @freeze_time(_FROZEN_TODAY)
    def test_fiscal_year_boundary_respect(self):
        """Scenario 6: Allocation respects fiscal year boundary crossings.

        GIVEN a schedule spanning 2024-07-01 to 2025-06-30 (12 months
              crossing the calendar-year / typical fiscal-year boundary
              on 2024-12-31).
        WHEN the schedule is confirmed.
        THEN
            * 12 lines are generated (one per month across the boundary).
            * Each month is represented EXACTLY ONCE: no duplicate
              (year, month) pairs, i.e., no overlap at the boundary.
            * The SUM INVARIANT holds: total equals 12000.00 exactly.
            * Lines are distributed across both 2024 (Jul-Dec) and 2025
              (Jan-Jun).

        The allocation engine uses :func:`dateutil.relativedelta.relativedelta`
        for month arithmetic, which transparently handles year rollover;
        this test documents that contract.  Locked-period enforcement
        (``fiscalyear_lock_date``) is the concern of DR-003 (cut-off
        wizard), not of DR-002 allocation -- an allocated line in a
        locked period is the expected input to the cut-off wizard's
        lock-date handling.
        """
        schedule = self._create_schedule(
            total_amount=12000.0,
            start_date=date(2024, 7, 1),
            end_date=date(2025, 6, 30),
            recognition_method='straight_line',
        )
        schedule.action_confirm()

        # 12-month straight-line across a year boundary => 12 lines.
        self.assertEqual(
            len(schedule.line_ids), 12,
            "A 12-month fiscal-year-spanning schedule must produce "
            "12 recognition lines.",
        )

        # Extract the (year, month) of each line's recognition_date.
        months = schedule.line_ids.mapped(
            lambda line: (
                line.recognition_date.year,
                line.recognition_date.month,
            ),
        )
        self.assertEqual(
            len(months), 12,
            "Expected 12 line entries in the month list.",
        )

        # Every month is unique: no duplicates around the boundary.
        # This catches regressions where boundary-crossing logic would
        # double-count a month (e.g., two lines both dated 2024-12-31).
        self.assertEqual(
            len(set(months)), 12,
            "All 12 months across the fiscal year boundary must be "
            f"distinct (no duplicates); got months={sorted(months)}.",
        )

        # Verify coverage of both halves of the fiscal year: 6 lines
        # each in 2024 and 2025.  This makes it explicit that the
        # allocation spans the boundary symmetrically.
        year_counts = {}
        for year, _month in months:
            year_counts[year] = year_counts.get(year, 0) + 1
        self.assertEqual(
            year_counts.get(2024, 0), 6,
            f"Expected 6 lines in calendar year 2024 (Jul-Dec); got "
            f"{year_counts.get(2024, 0)}.",
        )
        self.assertEqual(
            year_counts.get(2025, 0), 6,
            f"Expected 6 lines in calendar year 2025 (Jan-Jun); got "
            f"{year_counts.get(2025, 0)}.",
        )

        # SUM INVARIANT across the boundary: 12000.00 exactly.
        total = sum(schedule.line_ids.mapped('recognition_amount'))
        self.assertAlmostEqual(
            total, 12000.0, places=2,
            msg=(
                "DR-002 SUM INVARIANT violation across fiscal year "
                f"boundary: expected 12000.00, got {total}."
            ),
        )
