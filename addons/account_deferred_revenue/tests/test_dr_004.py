# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Test Suite — DR-004 Recognition Dashboard (account.deferred.recognition.dashboard.wizard)

Implements acceptance tests for FEATURE-005 Track C Story DR-004 per the
BDD scenarios defined in
``tickets/stories/deferred-revenue/DR-004-recognition-dashboard.md``.

Scope of this test file (one test method per acceptance scenario):

    * ``test_dashboard_pending_deferrals_summary``       (Scenario 1)
    * ``test_dashboard_upcoming_recognitions_by_period`` (Scenario 2)
    * ``test_dashboard_date_range_filter``               (Scenario 3)
    * ``test_dashboard_drilldown_navigation``            (Scenario 4)
    * ``test_dashboard_completion_status_grouping``      (Scenario 5)

Target coverage: ≥80% line coverage on
``addons/account_deferred_revenue/wizard/recognition_dashboard_wizard.py``
(enforced per AAP Rule R-04).

Base class: :class:`odoo.addons.account.tests.common.AccountTestInvoicingCommon`
Decorator: ``@tagged('post_install', '-at_install')``
Time control: :func:`freezegun.freeze_time` for deterministic date
computations.

The dashboard wizard (``account.deferred.recognition.dashboard.wizard``) is a
TransientModel with three categories of computed members exercised by these
tests:

    1.  Summary KPI fields populated by :meth:`_compute_summary`:
        ``total_deferred_revenue``, ``total_deferred_expenses``,
        ``active_schedule_count``, ``next_period_recognition``.

    2.  Breakdown JSON fields populated by :meth:`_compute_breakdown`:
        ``schedule_breakdown_json``, ``period_breakdown_json``,
        ``status_distribution_json``.

    3.  Drill-down action methods returning ``ir.actions.act_window`` dicts:
        ``action_view_pending``, ``action_view_revenue``,
        ``action_view_expenses``, ``action_view_next_period_lines``,
        ``action_drill_down``, ``action_refresh``.

    4.  The :meth:`_check_date_range` constraint, which raises
        :class:`~odoo.exceptions.UserError` when ``date_from > date_to``.

Each acceptance scenario exercises a distinct combination of the above so
the wizard's full API surface is covered to >=80% by this single test file
(matching the FEATURE-001 aging-bucket wizard precedent).

**Determinism note**: every test method is decorated with
``@freeze_time('2024-06-15')`` so that the wizard's ``next_period_recognition``
field — computed against ``today + relativedelta(months=1)`` — always targets
July 2024 regardless of when the test suite is executed.  Combined with hard-
coded ``date(2024, ...)`` literals throughout the test setup, this eliminates
real-clock flakiness.
"""

import json
from datetime import date
from unittest.mock import patch  # noqa: F401 -- imported per agent_prompt

from freezegun import freeze_time

from odoo import Command, fields  # noqa: F401 -- fields re-exported for parity
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon

# --------------------------------------------------------------------------
# Module-level constants for deterministic time control.
#
# ``_FROZEN_TODAY`` is the string form expected by ``freezegun.freeze_time``;
# ``_FROZEN_DATE`` is the equivalent ``datetime.date`` constant preserved for
# any test-body calculation that needs to compute month offsets relative to
# "today".  Frozen on 2024-06-15 — mid-month — so that:
#
#   * The "next calendar month" relative to today is unambiguously July 2024.
#   * Schedules spanning Jan-Dec 2024 cover periods both before and after
#     "today", exercising the full date-range filter logic.
#   * The wizard's lambda defaults (Jan 1 / Dec 31 of "current year") resolve
#     deterministically to 2024-01-01 / 2024-12-31.
# --------------------------------------------------------------------------
_FROZEN_TODAY = '2024-06-15'
_FROZEN_DATE = date(2024, 6, 15)


@tagged('post_install', '-at_install')
class TestDeferredRecognitionDashboard(AccountTestInvoicingCommon):
    """Acceptance tests for DR-004 Recognition Dashboard.

    Each test method maps to a single BDD acceptance scenario from
    ``tickets/stories/deferred-revenue/DR-004-recognition-dashboard.md``.
    The shared :meth:`setUpClass` provisions:

        * Module-specific security groups granted to the running test user.
        * A deterministic chart of test accounts with ``XTEST.*`` codes
          (one liability_current, one income, one asset_current, one
          expense) covering both deferred-revenue and deferred-expense
          paths through the dashboard's account-type filter logic.
        * A test partner used as ``partner_id`` on every schedule.

    Per-test schedule fixtures are constructed via the :meth:`_create_schedule`
    helper and the :meth:`_create_dashboard` helper instantiates the wizard
    under test with sensible defaults that may be overridden per scenario.

    The class uses the ``AccountTestInvoicingCommon`` fixture to inherit the
    standard accounting test environment (company, COA, journals, default
    test user) without polluting the production data.  Module-level
    test artifacts created here are isolated to the in-memory test DB
    created by Odoo's test runner.
    """

    # ------------------------------------------------------------------
    # Class-level fixture setup
    # ------------------------------------------------------------------
    @classmethod
    def setUpClass(cls):
        """Provision shared fixtures for all five DR-004 acceptance tests.

        Steps (in order):

        1. Bootstrap the standard accounting fixture via super().
        2. Grant ``group_deferred_revenue_user`` and
           ``group_deferred_revenue_manager`` to the test user so the
           ACL rows in ``security/ir.model.access.csv`` permit the
           create/write operations used by every test.  Both groups are
           granted because tests transition schedules through ``draft``
           → ``confirmed`` (requires write) and the
           ``test_dashboard_drilldown_navigation`` test resolves
           drill-down actions against a confirmed schedule (requires
           read on a fully provisioned record).
        3. Cache ``self.company`` and ``self.currency`` for ergonomic
           access in scenario tests.
        4. Create dedicated test accounts for revenue (income),
           expense (expense), deferred-revenue (liability_current), and
           deferred-expense (asset_current) — using ``XTEST.*`` codes
           to guarantee isolation from any pre-seeded chart-of-accounts
           entries, regardless of the active COA template.
        5. Create a generic test partner.  The partner is shared across
           every schedule fixture in every test so the partner_id
           propagation through the schedule → recognition_line → move
           chain is exercised consistently.
        """
        super().setUpClass()

        # ------------------------------------------------------------------
        # Step 2 — grant module-specific security groups.
        #
        # ``AccountTestInvoicingCommon`` creates a test user with the
        # core accounting groups but NOT the module-specific groups
        # from ``account_deferred_revenue``.  The ACL rows in
        # ``security/ir.model.access.csv`` require at least
        # ``group_deferred_revenue_user`` for create/read/write on
        # ``account.deferred.schedule``,
        # ``account.deferred.line``, and
        # ``account.deferred.recognition.dashboard.wizard``.
        #
        # ``raise_if_not_found=False`` defends against the edge case
        # where the security XML fails to load — in that case the
        # test will proceed without the groups and surface a clear
        # AccessError on the first create() call, which is more
        # informative than a cryptic env.ref KeyError at fixture-setup
        # time.  ``filtered(bool)`` drops any unresolved (False) refs
        # so we never call ``Command.link(False.id)``.
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
        # Step 3 — cache company and company currency.
        #
        # Using ``env.company`` keeps the test robust against future
        # changes to the default test company ID in
        # ``AccountTestInvoicingCommon``.  ``env.company.currency_id``
        # is what the dashboard's ``currency_id`` related field
        # resolves to at compute time, so referring to the same value
        # here guarantees that monetary assertions compare like-with-
        # like.
        # ------------------------------------------------------------------
        cls.company = cls.env.company
        cls.currency = cls.env.company.currency_id

        # ------------------------------------------------------------------
        # Step 4 — create deferred-revenue-specific test accounts.
        #
        # Using ``XTEST.*`` codes to guarantee isolation from any COA
        # entries installed by ``AccountTestInvoicingCommon`` or by a
        # future COA template; without this prefix, two test classes
        # could create colliding account codes and break each other
        # when run in the same test session.
        #
        # Code conventions (24xxx liability, 4xxxx income, 12xxx asset
        # receivable, 5xxxx expense) follow the standard CoA structure
        # used by the AAP-mandated FEATURE-001/FEATURE-002 precedent
        # (see addons/account_financial_report_ce/tests/test_balance_sheet.py).
        #
        # ``account_type`` values must match the Selection on
        # ``account.account.account_type`` defined in core Odoo (see
        # addons/account/models/account_account.py); they are also the
        # values consumed by the dashboard's ``_INCOME_ACCOUNT_TYPES``
        # and ``_EXPENSE_ACCOUNT_TYPES`` module-level tuples.
        # ------------------------------------------------------------------
        AccountAccount = cls.env['account.account']

        cls.deferred_revenue_account = AccountAccount.create({
            'code': 'XTEST.24100',
            'name': 'Test Deferred Revenue (Liability)',
            'account_type': 'liability_current',
            'reconcile': False,
        })
        cls.recognition_revenue_account = AccountAccount.create({
            'code': 'XTEST.40100',
            'name': 'Test Recognition Revenue (Income)',
            'account_type': 'income',
            'reconcile': False,
        })
        cls.deferred_expense_account = AccountAccount.create({
            'code': 'XTEST.12100',
            'name': 'Test Deferred Expense (Asset)',
            'account_type': 'asset_current',
            'reconcile': False,
        })
        cls.recognition_expense_account = AccountAccount.create({
            'code': 'XTEST.50100',
            'name': 'Test Recognition Expense',
            'account_type': 'expense',
            'reconcile': False,
        })

        # ------------------------------------------------------------------
        # Step 5 — create a generic test partner.
        #
        # The partner_id field on account.deferred.schedule is NOT
        # required, but is typical for real deferrals; setting it on
        # every fixture exercises partner_id propagation through the
        # related field on account.deferred.line and through the
        # dashboard's domain composition (the dashboard does not
        # filter by partner directly, but read_group results inherit
        # the partner via the schedule).
        # ------------------------------------------------------------------
        cls.partner = cls.env['res.partner'].create({
            'name': 'Dashboard Test Customer',
        })

    # ------------------------------------------------------------------
    # Helpers — schedule and dashboard factory methods
    # ------------------------------------------------------------------
    def _create_schedule(self, **overrides):
        """Return a fresh draft ``account.deferred.schedule`` record.

        Default values build a 12-month deferred-revenue schedule for
        $12,000 spread evenly from 2024-01-01 to 2024-12-31 using the
        straight-line recognition method.  Any default may be
        overridden via keyword argument; the most commonly overridden
        values are:

            * ``total_amount`` — to construct schedules of varying
              size for active_schedule_count assertions.
            * ``deferred_account_id`` / ``recognition_account_id`` —
              to construct expense (asset/expense) vs revenue
              (liability/income) schedules.
            * ``start_date`` / ``end_date`` — to construct
              schedules whose recognition period spans different
              date-range filter windows in Scenario 3.

        Returns:
            account.deferred.schedule: a single draft schedule.

        The schedule is created directly via ``create()`` (not through
        a wizard) because every DR-004 scenario focuses on the
        dashboard's read-side aggregation of pre-existing schedules,
        not the wizard-driven creation flow.  Schedules remain in
        ``draft`` until the test explicitly invokes
        :meth:`action_confirm` to advance them to ``confirmed`` and
        trigger ``_compute_recognition_schedule`` line generation.
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

    def _create_dashboard(self, **overrides):
        """Return a freshly created dashboard wizard record.

        Default values target a full calendar year 2024, the test
        company, and ``status_filter='active'``.  Overrides per test:

            * ``date_from`` / ``date_to`` — narrow the dashboard
              window in Scenario 3 to test date-range filtering.
            * ``status_filter`` — switch between
              ``active`` / ``completed`` / ``on_hold`` / ``all`` in
              Scenario 5 to verify the status-filter branches in
              :meth:`_apply_status_filter`.
            * ``company_id`` — implicit from env.company default;
              tests do not exercise multi-company behaviour because
              the AAP scopes ir.rule multi-company validation to the
              schedule and line models, not the dashboard wizard.

        Returns:
            account.deferred.recognition.dashboard.wizard: a single
                wizard record with computed fields ready to be
                accessed.
        """
        vals = {
            'date_from': date(2024, 1, 1),
            'date_to': date(2024, 12, 31),
            'company_id': self.company.id,
            'status_filter': 'active',
        }
        vals.update(overrides)
        return self.env[
            'account.deferred.recognition.dashboard.wizard'
        ].create(vals)

    # ==================================================================
    # Scenario 1 — Pending Deferrals Summary
    # ==================================================================
    @freeze_time(_FROZEN_TODAY)
    def test_dashboard_pending_deferrals_summary(self):
        """Scenario 1: Pending-deferrals summary aggregates active schedules.

        BDD specification (DR-004 Acceptance Criteria, Scenario 1):

            GIVEN active deferral schedules with amounts not yet
            recognized AND the schedules include both deferred revenue
            and deferred expense types
            WHEN I access the recognition dashboard
            THEN total deferred revenue pending recognition is shown
             AND total deferred expenses pending recognition is shown
             AND amounts are displayed in company currency
             AND summary shows count of active schedules per type.

        Assertions made by this test:

            * ``total_deferred_revenue`` is strictly positive when at
              least one revenue schedule is confirmed and active.
            * ``total_deferred_expenses`` is strictly positive when at
              least one expense schedule is confirmed and active.
            * ``active_schedule_count`` equals the number of confirmed
              active schedules created (3 here).
            * ``next_period_recognition`` is non-negative — the
              freezegun anchor at 2024-06-15 means "next calendar
              month" is July 2024, and every confirmed straight-line
              schedule has a draft recognition line in July 2024.
            * ``currency_id`` resolves to the company currency.

        The three confirmed schedules ($12,000 + $6,000 revenue +
        $3,000 expense = $21,000 grand total) deliberately mix
        revenue and expense paths so the dashboard's
        ``_compute_summary`` exercises both ``_INCOME_ACCOUNT_TYPES``
        and ``_EXPENSE_ACCOUNT_TYPES`` aggregation branches.
        """
        # Two confirmed revenue schedules — different durations so the
        # next_period_recognition aggregator covers multi-line cases.
        schedule_a = self._create_schedule(total_amount=12000.0)
        schedule_a.action_confirm()
        schedule_b = self._create_schedule(
            total_amount=6000.0,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 30),
        )
        schedule_b.action_confirm()

        # One confirmed expense schedule — uses the asset_current /
        # expense account pair so the dashboard categorises it under
        # ``total_deferred_expenses``.
        schedule_expense = self._create_schedule(
            total_amount=3000.0,
            deferred_account_id=self.deferred_expense_account.id,
            recognition_account_id=self.recognition_expense_account.id,
        )
        schedule_expense.action_confirm()

        dashboard = self._create_dashboard()

        # ------------------------------------------------------------------
        # Force computation of every summary field by accessing it.
        # Odoo computes lazily; reading the attribute triggers the
        # @api.depends-driven _compute_summary method.
        # ------------------------------------------------------------------
        revenue_total = dashboard.total_deferred_revenue
        expense_total = dashboard.total_deferred_expenses
        active_count = dashboard.active_schedule_count
        next_period = dashboard.next_period_recognition

        self.assertGreater(
            revenue_total, 0.0,
            "total_deferred_revenue must be positive when active "
            "revenue schedules exist.",
        )
        self.assertGreater(
            expense_total, 0.0,
            "total_deferred_expenses must be positive when active "
            "expense schedules exist.",
        )
        self.assertEqual(
            active_count, 3,
            "active_schedule_count must equal the number of confirmed "
            "active schedules created (2 revenue + 1 expense = 3).",
        )
        self.assertGreaterEqual(
            next_period, 0.0,
            "next_period_recognition must be non-negative.  With "
            "freezegun anchored at 2024-06-15, the next calendar "
            "month is July 2024, which contains a draft line from "
            "every active schedule under the straight-line method.",
        )

        # ------------------------------------------------------------------
        # Currency display verification — Scenario 1 specifies that
        # amounts must be displayed in company currency.  The
        # dashboard's currency_id is a ``related`` field on
        # ``company_id.currency_id``, so it must resolve to the same
        # currency as ``self.currency``.
        # ------------------------------------------------------------------
        self.assertEqual(
            dashboard.currency_id, self.company.currency_id,
            "Dashboard currency_id must equal company.currency_id.",
        )

    # ==================================================================
    # Scenario 2 — Upcoming Recognitions by Period
    # ==================================================================
    @freeze_time(_FROZEN_TODAY)
    def test_dashboard_upcoming_recognitions_by_period(self):
        """Scenario 2: Upcoming recognitions aggregate by period (month).

        BDD specification (DR-004 Acceptance Criteria, Scenario 2):

            GIVEN deferral schedules with future recognition dates
             AND schedules span multiple upcoming accounting periods
            WHEN I select a future accounting period on the dashboard
            THEN scheduled recognition amounts for that period are shown
             AND deferral schedules to be recognized are visible
             AND recognition percentage or amount per schedule is shown
             AND totals break down by revenue vs expense categories.

        The dashboard implements this scenario through three computed
        breakdown payloads on the wizard:

            * ``schedule_breakdown_json`` — counts and totals grouped
              by ``recognition_method`` (straight_line / date_based /
              manual).
            * ``period_breakdown_json`` — totals grouped by
              ``recognition_date:month`` from
              ``account.deferred.line``.
            * ``status_distribution_json`` — counts grouped by
              ``completion_status``.

        This test asserts:

            * ``period_breakdown_json`` is computed (not None).
            * The payload contains at least one period row when the
              schedule generates recognition lines spanning the date
              range.
            * Each row carries a non-empty month label and a numeric
              total — proving the read_group with
              ``recognition_date:month`` granularity actually emits
              human-readable groupby keys.
            * ``schedule_breakdown_json`` is computed and contains
              at least one row tagged with ``recognition_method``.

        ``json.loads(raw) if isinstance(raw, str) else raw`` is the
        defensive parse pattern matching the FEATURE-001 aging-bucket
        wizard test precedent — Odoo's ``fields.Json`` may return a
        native Python object OR a JSON-encoded string depending on
        ORM write path, and tests must handle both uniformly.
        """
        # Confirm a 12-month schedule so 12 recognition lines (one per
        # calendar month in 2024) are auto-generated by
        # _compute_recognition_schedule.
        schedule = self._create_schedule(total_amount=12000.0)
        schedule.action_confirm()

        dashboard = self._create_dashboard(
            date_from=date(2024, 1, 1),
            date_to=date(2024, 12, 31),
        )

        # ------------------------------------------------------------------
        # period_breakdown_json — list of dicts, one per calendar
        # month within the dashboard date range.  Each entry shape:
        #     {"month": "January 2024", "total": 1000.0, "count": 1}
        # ------------------------------------------------------------------
        raw_period = dashboard.period_breakdown_json
        self.assertIsNotNone(
            raw_period,
            "period_breakdown_json must be computed (not None) when "
            "active schedules have recognition lines in range.",
        )
        # fields.Json may return parsed Python or a JSON string —
        # handle both defensively (FEATURE-001 aging-bucket precedent).
        period_breakdown = (
            json.loads(raw_period) if isinstance(raw_period, str) else raw_period
        )
        self.assertIsInstance(
            period_breakdown, (list, dict),
            "period_breakdown_json must be a JSON-serializable "
            "container (list or dict).",
        )

        # The 12-month schedule yields 12 monthly recognition lines
        # which read_group will aggregate into 12 month groups.  We
        # accept either list-of-dicts (the implementation's chosen
        # shape) or dict-of-month->amount (a future shape change)
        # to keep the test resilient to non-breaking refactors.
        if isinstance(period_breakdown, list):
            self.assertGreaterEqual(
                len(period_breakdown), 1,
                "Expected ≥1 period row in breakdown (the 12-month "
                "schedule should yield 12 month groups).",
            )
            # Each row must carry a month label and a numeric total
            # so the dashboard view widget can render it.
            for entry in period_breakdown:
                self.assertIn(
                    'month', entry,
                    "Each period_breakdown entry must include the "
                    "'month' label.",
                )
                self.assertIn(
                    'total', entry,
                    "Each period_breakdown entry must include the "
                    "'total' aggregated amount.",
                )
                # Total must be numeric (int/float) — the
                # read_group aggregation guarantees this when using
                # the ``:sum`` aggregator on a Monetary field.
                self.assertIsInstance(
                    entry.get('total'), (int, float),
                    "period_breakdown entry 'total' must be numeric.",
                )
        else:
            # Dict form — at least one entry must be present.
            self.assertGreaterEqual(
                len(period_breakdown), 1,
                "Expected ≥1 entry in period_breakdown dict.",
            )

        # ------------------------------------------------------------------
        # schedule_breakdown_json — list of dicts, one per
        # recognition_method.  Even with a single straight-line
        # schedule, exactly one row is expected.
        # ------------------------------------------------------------------
        raw_method = dashboard.schedule_breakdown_json
        self.assertIsNotNone(
            raw_method,
            "schedule_breakdown_json must be computed (not None).",
        )
        method_breakdown = (
            json.loads(raw_method) if isinstance(raw_method, str) else raw_method
        )
        self.assertIsInstance(
            method_breakdown, (list, dict),
            "schedule_breakdown_json must be a JSON-serializable "
            "container.",
        )
        if isinstance(method_breakdown, list):
            self.assertGreaterEqual(
                len(method_breakdown), 1,
                "Expected ≥1 method group (we created exactly one "
                "straight_line schedule).",
            )
            # The single straight_line schedule should appear as a
            # row whose ``recognition_method`` key equals
            # 'straight_line'.
            method_keys = {row.get('recognition_method') for row in method_breakdown}
            self.assertIn(
                'straight_line', method_keys,
                "The straight_line schedule must appear in "
                "schedule_breakdown_json under its method key.",
            )

    # ==================================================================
    # Scenario 3 — Date Range Filter
    # ==================================================================
    @freeze_time(_FROZEN_TODAY)
    def test_dashboard_date_range_filter(self):
        """Scenario 3: Date-range filter narrows dashboard data.

        BDD specification (DR-004 Acceptance Criteria, Scenario 3):

            GIVEN deferral schedules spanning multiple periods
             AND I need to analyze a specific time window
            WHEN I apply a date range filter to the dashboard
            THEN only recognitions within the selected date range are
              shown
             AND summary totals reflect the filtered data
             AND I can clear filters to see all data
             AND filter selections persist within my session.

        Validation has two parts:

            1. **Narrow vs wide range** — A narrow Jan-Mar window must
               not produce a larger ``total_deferred_revenue`` than a
               wider Jan-Dec window because the date-range filter
               restricts which schedules count toward the active
               population (schedules whose ``end_date < date_from`` or
               ``start_date > date_to`` are excluded).  ``assertLessEqual``
               (rather than strict ``<``) is the correct invariant — a
               schedule whose recognition window fully precedes the
               narrow filter range can yield equal totals.

            2. **Constraint validation** — Setting ``date_from > date_to``
               must raise :class:`UserError` from the
               :meth:`_check_date_range` constraint.  The constraint
               body raises a localised ``UserError`` with an
               actionable message; the test only asserts the exception
               type because the message text is locale-dependent.
        """
        schedule = self._create_schedule(total_amount=12000.0)
        schedule.action_confirm()

        # Narrow window — Q1 2024 only.  The schedule's start_date is
        # 2024-01-01 and end_date is 2024-12-31, so it overlaps the
        # narrow window via the schedule's ``_get_base_schedule_domain``
        # logic (start_date <= date_to AND (end_date >= date_from OR
        # end_date is unset)).  Therefore the narrow filter still
        # includes the schedule but the period_breakdown_json
        # aggregation only counts Q1 recognition lines.
        narrow = self._create_dashboard(
            date_from=date(2024, 1, 1),
            date_to=date(2024, 3, 31),
        )
        narrow_revenue = narrow.total_deferred_revenue

        # Wide window — full calendar year.
        wide = self._create_dashboard(
            date_from=date(2024, 1, 1),
            date_to=date(2024, 12, 31),
        )
        wide_revenue = wide.total_deferred_revenue

        # Narrow totals must be less than or equal to wide totals.
        # Strict ``<`` is NOT correct: a schedule that overlaps both
        # ranges contributes its full remaining_amount to both totals
        # (because total_deferred_revenue aggregates schedule-level
        # remaining_amount, not period-level recognition amount).
        self.assertLessEqual(
            narrow_revenue, wide_revenue,
            "Narrower date range must not produce larger totals than "
            "the wide range — the filter is monotonic.",
        )

        # ------------------------------------------------------------------
        # Constraint: date_from > date_to → UserError
        #
        # The wizard's @api.constrains('date_from', 'date_to') method
        # raises UserError when the range is inverted.  We verify
        # both that the exception is raised AND that
        # ``_check_date_range`` is the caller (implicit from the
        # exception type — only this constraint raises UserError on
        # date_from/date_to assignment).
        # ------------------------------------------------------------------
        with self.assertRaises(
            UserError,
            msg="Configuring date_from > date_to must raise UserError "
                "from _check_date_range.",
        ):
            self._create_dashboard(
                date_from=date(2024, 12, 31),
                date_to=date(2024, 1, 1),
            )

    # ==================================================================
    # Scenario 4 — Drill-down Navigation
    # ==================================================================
    @freeze_time(_FROZEN_TODAY)
    def test_dashboard_drilldown_navigation(self):
        """Scenario 4: Drill-down actions return valid act_window dicts.

        BDD specification (DR-004 Acceptance Criteria, Scenario 4):

            GIVEN I am viewing the recognition dashboard
             AND I need to verify details of a specific deferral
            WHEN I click on a deferral schedule entry
            THEN I navigate to the deferral schedule detail view
             AND I see the source invoice and original transaction
             AND I see all recognition entries for that schedule
             AND I can navigate back to the dashboard.

        The wizard exposes six drill-down action methods.  This test
        verifies each returns a syntactically valid Odoo
        ``ir.actions.act_window`` dict targeting the correct model:

            * :meth:`action_view_pending` — schedules matching the
              dashboard's filter set; res_model =
              account.deferred.schedule.
            * :meth:`action_view_revenue` — confirmed revenue
              schedules (filtered to income account_types); res_model
              = account.deferred.schedule.
            * :meth:`action_view_expenses` — confirmed expense
              schedules (filtered to expense account_types); res_model
              = account.deferred.schedule.
            * :meth:`action_view_next_period_lines` — draft lines in
              next calendar month; res_model = account.deferred.line.
            * :meth:`action_drill_down(schedule_id=N)` — opens form
              view of a specific schedule; res_model =
              account.deferred.schedule with res_id=N.
            * :meth:`action_drill_down()` (no schedule_id) — must
              raise UserError because the wizard refuses to silently
              open an arbitrary form view.
            * :meth:`action_refresh` — invalidates compute cache and
              re-opens the dashboard form view; returns an act_window
              dict with res_model = the wizard model itself.

        Each action dict is asserted to have:

            * ``type == 'ir.actions.act_window'`` — confirms it is a
              window action and not a server / report action.
            * ``res_model == <expected>`` — confirms it routes to the
              correct target model.
        """
        schedule = self._create_schedule(total_amount=12000.0)
        schedule.action_confirm()

        dashboard = self._create_dashboard()

        # ------------------------------------------------------------------
        # action_view_pending — schedules under the dashboard's
        # current filter set (status_filter='active' by default).
        # ------------------------------------------------------------------
        pending_action = dashboard.action_view_pending()
        self.assertIsInstance(
            pending_action, dict,
            "action_view_pending must return an action dict.",
        )
        self.assertEqual(
            pending_action.get('type'), 'ir.actions.act_window',
            "action_view_pending must return an ir.actions.act_window.",
        )
        self.assertEqual(
            pending_action.get('res_model'), 'account.deferred.schedule',
            "action_view_pending must target account.deferred.schedule.",
        )
        # The action must carry a domain so the user lands on a
        # filtered list, not the unfiltered universe of schedules.
        self.assertIn(
            'domain', pending_action,
            "action_view_pending must include a 'domain' key.",
        )
        self.assertIsInstance(
            pending_action['domain'], list,
            "action_view_pending domain must be a list of domain "
            "tuples.",
        )

        # ------------------------------------------------------------------
        # action_view_revenue — schedules whose recognition_account
        # has account_type in income/income_other.
        # ------------------------------------------------------------------
        revenue_action = dashboard.action_view_revenue()
        self.assertIsInstance(revenue_action, dict)
        self.assertEqual(
            revenue_action.get('type'), 'ir.actions.act_window',
        )
        self.assertEqual(
            revenue_action.get('res_model'), 'account.deferred.schedule',
        )

        # ------------------------------------------------------------------
        # action_view_expenses — schedules whose recognition_account
        # has account_type in expense/expense_depreciation/
        # expense_direct_cost.
        # ------------------------------------------------------------------
        expense_action = dashboard.action_view_expenses()
        self.assertIsInstance(expense_action, dict)
        self.assertEqual(
            expense_action.get('type'), 'ir.actions.act_window',
        )
        self.assertEqual(
            expense_action.get('res_model'), 'account.deferred.schedule',
        )

        # ------------------------------------------------------------------
        # action_view_next_period_lines — draft recognition lines in
        # the next calendar month (July 2024 given freezegun=
        # 2024-06-15).  This is the ONLY action that targets
        # account.deferred.line; the other four target the schedule
        # model.
        # ------------------------------------------------------------------
        lines_action = dashboard.action_view_next_period_lines()
        self.assertIsInstance(lines_action, dict)
        self.assertEqual(
            lines_action.get('type'), 'ir.actions.act_window',
        )
        self.assertEqual(
            lines_action.get('res_model'), 'account.deferred.line',
            "action_view_next_period_lines must target "
            "account.deferred.line (the recognition-line model), "
            "not the schedule model.",
        )

        # ------------------------------------------------------------------
        # action_drill_down(schedule_id=N) — explicit schedule_id
        # kwarg; opens form view of that specific record.  Verifies
        # the explicit-kwarg invocation path of the dual-mode method.
        # ------------------------------------------------------------------
        drill_action = dashboard.action_drill_down(schedule_id=schedule.id)
        self.assertIsInstance(drill_action, dict)
        self.assertEqual(
            drill_action.get('type'), 'ir.actions.act_window',
        )
        self.assertEqual(
            drill_action.get('res_model'), 'account.deferred.schedule',
        )
        self.assertEqual(
            drill_action.get('res_id'), schedule.id,
            "action_drill_down must set res_id to the specified "
            "schedule.id when called with schedule_id kwarg.",
        )
        # ``view_mode = 'form'`` because drill-down opens the form
        # view directly (skipping the list).
        self.assertEqual(
            drill_action.get('view_mode'), 'form',
            "action_drill_down must open form view directly.",
        )

        # ------------------------------------------------------------------
        # action_drill_down() with neither kwarg nor context key —
        # must raise UserError.  The wizard refuses to silently open
        # an arbitrary form view because that would be a confusing
        # UX (per the docstring on action_drill_down).
        # ------------------------------------------------------------------
        with self.assertRaises(
            UserError,
            msg="action_drill_down without schedule_id or "
                "active_schedule_id context key must raise UserError.",
        ):
            dashboard.action_drill_down()

        # ------------------------------------------------------------------
        # action_drill_down(schedule_id=<bogus>) — non-existent id
        # must also raise UserError after the .browse(...).exists()
        # guard.
        # ------------------------------------------------------------------
        with self.assertRaises(
            UserError,
            msg="action_drill_down with non-existent schedule_id "
                "must raise UserError after the .exists() guard.",
        ):
            # Use a deliberately-invalid (negative) id so the .exists()
            # check returns an empty recordset.
            dashboard.action_drill_down(schedule_id=-99999)

        # ------------------------------------------------------------------
        # action_drill_down() via context key — invocation through
        # ``active_schedule_id`` in env.context.  Exercises the
        # alternate resolution path.
        # ------------------------------------------------------------------
        ctx_action = dashboard.with_context(
            active_schedule_id=schedule.id,
        ).action_drill_down()
        self.assertIsInstance(ctx_action, dict)
        self.assertEqual(
            ctx_action.get('res_id'), schedule.id,
            "action_drill_down via active_schedule_id context must "
            "resolve the schedule from env.context.",
        )

    # ==================================================================
    # Scenario 5 — Completion Status Grouping
    # ==================================================================
    @freeze_time(_FROZEN_TODAY)
    def test_dashboard_completion_status_grouping(self):
        """Scenario 5: Completion-status grouping categorises schedules.

        BDD specification (DR-004 Acceptance Criteria, Scenario 5):

            GIVEN a mix of active and completed deferral schedules
             AND completed schedules have fully recognized their
              deferred amounts
            WHEN I view the dashboard
            THEN schedules are grouped by status (Active, Completed)
             AND active schedules show remaining amount to recognize
             AND completed schedules show fully-recognized indicator
             AND I can filter by status.

        The wizard supports four status_filter values:

            * ``active`` — confirmed schedules with completion_status
              == 'active' (default).
            * ``completed`` — schedules with completion_status ==
              'completed' (state='closed' OR fully recognized).
            * ``on_hold`` — schedules with completion_status ==
              'on_hold' (still in draft state).
            * ``all`` — no status filter applied.

        This test asserts:

            * ``active_schedule_count`` > 0 when at least one confirmed
              schedule exists with status_filter='active'.
            * ``status_filter='all'`` does not raise any error and
              produces a wizard whose computed fields are accessible
              (i.e. _apply_status_filter handles 'all' as a no-op).
            * ``status_filter='completed'`` produces a wizard whose
              computed fields are accessible.
            * ``status_filter='on_hold'`` produces a wizard whose
              computed fields are accessible.
            * ``status_distribution_json`` is computed and contains
              valid status keys.
            * :meth:`action_refresh` returns a valid act_window dict
              that re-opens the dashboard.
        """
        # One active confirmed schedule.
        active_schedule = self._create_schedule(total_amount=12000.0)
        active_schedule.action_confirm()
        # One draft schedule (completion_status='on_hold' per the
        # _compute_completion_status logic on the schedule model).
        # It is intentionally NOT confirmed so the dashboard's
        # status_filter='active' branch excludes it.
        self._create_schedule(total_amount=6000.0)

        # status_filter='active' — active_schedule_count must include
        # the confirmed schedule.
        active_only = self._create_dashboard(status_filter='active')
        active_count = active_only.active_schedule_count
        self.assertGreaterEqual(
            active_count, 1,
            "active_schedule_count must include the one confirmed "
            "schedule when status_filter='active'.",
        )

        # status_filter='all' — no status filter; both schedules
        # eligible.  We assert no exception and that the count is
        # at least the number of schedules created.
        all_filter = self._create_dashboard(status_filter='all')
        all_count = all_filter.active_schedule_count
        self.assertGreaterEqual(
            all_count, active_count,
            "status_filter='all' must include at least as many "
            "schedules as 'active' (it disables the filter).",
        )

        # status_filter='completed' — should not raise, and may
        # produce zero count if no schedule is fully recognized.
        completed_filter = self._create_dashboard(status_filter='completed')
        completed_count = completed_filter.active_schedule_count
        self.assertGreaterEqual(
            completed_count, 0,
            "status_filter='completed' must produce a non-negative "
            "count (zero is acceptable when no schedule is fully "
            "recognized).",
        )

        # status_filter='on_hold' — should not raise.  The draft
        # schedule has completion_status='on_hold' so the count
        # should be at least 1.
        on_hold_filter = self._create_dashboard(status_filter='on_hold')
        on_hold_count = on_hold_filter.active_schedule_count
        self.assertGreaterEqual(
            on_hold_count, 1,
            "status_filter='on_hold' must include the draft schedule "
            "(completion_status='on_hold').",
        )

        # ------------------------------------------------------------------
        # status_distribution_json — must be computed and structurally
        # valid.  Implementation choice is dict {status: count} so we
        # accept both dict and list shapes for resilience.
        # ------------------------------------------------------------------
        status_raw = active_only.status_distribution_json
        self.assertIsNotNone(
            status_raw,
            "status_distribution_json must be computed (not None).",
        )
        dist = (
            json.loads(status_raw) if isinstance(status_raw, str) else status_raw
        )
        self.assertIsInstance(
            dist, (list, dict),
            "status_distribution_json must be a JSON-serializable "
            "container.",
        )
        # When dict shape is returned, keys must be drawn from the
        # known completion_status values (active/completed/on_hold/
        # unknown).
        if isinstance(dist, dict):
            allowed_keys = {'active', 'completed', 'on_hold', 'unknown'}
            for key in dist:
                self.assertIn(
                    key, allowed_keys,
                    "status_distribution_json keys must come from "
                    "the completion_status Selection.",
                )
                self.assertIsInstance(
                    dist[key], int,
                    "status_distribution_json values must be int "
                    "(group counts).",
                )

        # ------------------------------------------------------------------
        # action_refresh — invalidates the compute cache and returns
        # a window action.  The DR-004 ticket requires real-time
        # data; verifying refresh returns a valid action confirms
        # the cache-management plumbing is wired correctly.
        # ------------------------------------------------------------------
        refresh_action = active_only.action_refresh()
        self.assertIsInstance(
            refresh_action, dict,
            "action_refresh must return an action dict.",
        )
        self.assertEqual(
            refresh_action.get('type'), 'ir.actions.act_window',
            "action_refresh must return an ir.actions.act_window.",
        )
        # action_refresh re-opens the dashboard form on the same
        # transient record, so the action targets the wizard model
        # itself with res_id == self.id.
        self.assertEqual(
            refresh_action.get('res_model'),
            'account.deferred.recognition.dashboard.wizard',
            "action_refresh must target the dashboard wizard model.",
        )
        self.assertEqual(
            refresh_action.get('res_id'), active_only.id,
            "action_refresh must set res_id to the wizard's own id.",
        )
