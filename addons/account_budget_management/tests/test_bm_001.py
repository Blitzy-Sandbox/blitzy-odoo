# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Test Suite for BM-001: Budget Definition

Implements comprehensive tests for ``budget.budget`` and
``budget.budget.line`` model creation, validation, state transitions,
duplication, and analytic distribution as defined in the BM-001
acceptance criteria:

* Scenario 1 — Create budget record with required attributes (name,
  fiscal period) plus optional responsible-user / description, saving
  in ``draft`` state with an auto-generated unique reference.
* Scenario 2 — Assign budget lines linked to GL accounts (income /
  expense types only). Server-side ``_check_account_type`` rejects
  balance-sheet account types (``asset_*``, ``liability_*``, ``equity``,
  ``off_balance``).
* Scenario 3 — Analytic dimension assignment via ``analytic.mixin``
  ``analytic_distribution`` JSON field. Single-key and multi-key
  distributions are supported, and the inverse exposure on
  ``account.analytic.account.budget_line_ids`` powers smart-button
  navigation.
* Scenario 4 — Validation on activation: ``action_confirm`` requires
  the budget to be in ``draft``, to carry at least one line, and to
  have at least one line with a positive ``planned_amount``. Manager-
  gated ``action_reset_draft`` enforces the
  ``account.group_account_manager`` ACL. Closed budgets cannot be
  cancelled. Confirmed budgets cannot be re-confirmed.
* Scenario 5 — Duplication produces a fresh draft "(copy)" record
  with a regenerated reference and ``copied_from_id`` linkage to the
  source. Source budget remains unchanged. Lines are copied through
  ``line_ids.copy=True``.
* Scenario 6 — Reference uniqueness is enforced per-company via the
  ``_unique_reference_per_company`` ``models.Constraint`` (UNIQUE
  ``(reference, company_id)``).

Additional invariants exercised:

* Multi-company isolation through ``company_id`` and ``ir.rule``
  scoping (``with_company`` context switching).
* Date validation (``_check_dates`` rejects ``date_from > date_to``).
* Computed fields ``line_count`` and ``total_planned`` reflect the
  current children of each budget header.
* Smart-button action ``action_open_lines`` returns a properly
  configured ``ir.actions.act_window`` targeting
  ``budget.budget.line``.

Target: ≥80% line coverage per Rule R-04 on BM-001-scope code paths
(``budget.budget``, ``budget.budget.line``, and the BM-001 portion of
the ``account.analytic.account`` ``_inherit`` extension).
"""

from datetime import date

from psycopg2 import IntegrityError

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tools.misc import mute_logger

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestBudgetDefinition(AccountTestInvoicingCommon):
    """Test class for BM-001: Budget Definition.

    Validates the foundational capability to define budgets associated
    with GL accounts and analytic dimensions.  Extends
    :class:`AccountTestInvoicingCommon` to obtain standard company,
    chart-of-accounts, partners, and analytic-plan fixtures, then
    layers BM-001-specific test fixtures (dedicated GL accounts under
    the ``XTEST.*`` prefix, analytic plan + analytic accounts, and
    two reference users — a regular accounting user and an accounting
    manager) on top.

    The ``post_install`` tag ensures the module is fully installed —
    including security CSV rows, ``ir.sequence`` records, and the
    parent budget views — before any test method runs.  The
    ``-at_install`` tag prevents these tests from running against an
    only partially-installed registry during the early module-loading
    phase, which would cause failures on the
    ``account.analytic.account`` ``_inherit`` extension lookups.
    """

    @classmethod
    def setUpClass(cls):
        """Create the BM-001 test fixtures.

        Establishes:

        * A minimal set of dedicated GL accounts spanning the BM-001
          allow list (``expense``, ``expense_other``, ``income``) plus
          a balance-sheet ``asset_receivable`` account used for
          negative tests.
        * One analytic plan (``Test Departments``) with two analytic
          accounts (``Marketing`` and ``Operations``) to back the
          Scenario 3 distribution tests.
        * Two reference users — ``user_budget_owner`` carrying the
          standard ``account.group_account_user`` group, and
          ``user_manager`` carrying both the user group and the
          ``account.group_account_manager`` group required by
          ``action_reset_draft``.

        All fixtures are class-level (created once per test class
        invocation) so individual test methods can rely on stable
        IDs and avoid the per-test setup cost of re-creating the
        chart of accounts.
        """
        super().setUpClass()

        AccountAccount = cls.env['account.account']
        AnalyticPlan = cls.env['account.analytic.plan']
        AnalyticAccount = cls.env['account.analytic.account']

        # ----------------------------------------------------------
        # GL accounts — XTEST.* namespace so we never collide with the
        # chart of accounts loaded by AccountTestInvoicingCommon.  Each
        # account is created once per class with the minimum field set
        # required by the model (code + name + account_type).
        # ----------------------------------------------------------
        cls.test_expense = AccountAccount.create({
            'code': 'XTEST.60000',
            'name': 'Test Operating Expense',
            'account_type': 'expense',
        })
        cls.test_expense_other = AccountAccount.create({
            'code': 'XTEST.60500',
            'name': 'Test Other Expense',
            'account_type': 'expense_other',
        })
        cls.test_revenue = AccountAccount.create({
            'code': 'XTEST.40000',
            'name': 'Test Sales Revenue',
            'account_type': 'income',
        })
        # Balance-sheet account used purely for the
        # ``_check_account_type`` rejection test in Scenario 2.
        cls.test_receivable = AccountAccount.create({
            'code': 'XTEST.11000',
            'name': 'Test Receivable',
            'account_type': 'asset_receivable',
            'reconcile': True,
        })

        # ----------------------------------------------------------
        # Analytic plan + accounts (BM-001 Scenario 3).
        #
        # ``account.analytic.plan`` is a hierarchical model — root
        # plans have ``parent_id=False``, and ``account_ids`` is a
        # one-to-many to ``account.analytic.account`` records that
        # carry budget-line distribution percentages via the
        # ``analytic.mixin`` JSON field on ``budget.budget.line``.
        # ----------------------------------------------------------
        cls.analytic_plan = AnalyticPlan.create({
            'name': 'Test Departments',
        })
        cls.analytic_marketing = AnalyticAccount.create({
            'name': 'Marketing',
            'plan_id': cls.analytic_plan.id,
        })
        cls.analytic_operations = AnalyticAccount.create({
            'name': 'Operations',
            'plan_id': cls.analytic_plan.id,
        })

        # ----------------------------------------------------------
        # Reference users.
        #
        # ``user_budget_owner`` is a regular accounting user — the
        # default operator who can create / edit / confirm budgets but
        # must NOT be able to reset a confirmed budget back to draft
        # (Scenario 4).  ``user_manager`` carries the additional
        # ``account.group_account_manager`` group that grants the
        # reset privilege.
        # ----------------------------------------------------------
        cls.user_budget_owner = cls.env['res.users'].create({
            'name': 'Budget Owner',
            'login': 'budget_owner_bm001',
            'email': 'budget_owner@test.com',
            'group_ids': [
                Command.link(
                    cls.env.ref('account.group_account_user').id,
                ),
            ],
        })
        cls.user_manager = cls.env['res.users'].create({
            'name': 'Budget Manager',
            'login': 'budget_manager_bm001',
            'email': 'budget_manager@test.com',
            'group_ids': [
                Command.link(
                    cls.env.ref('account.group_account_user').id,
                ),
                Command.link(
                    cls.env.ref('account.group_account_manager').id,
                ),
            ],
        })

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------

    def _create_budget(self, **overrides):
        """Create a draft budget with sensible defaults.

        Defaults to a full FY2024 fiscal window (2024-01-01 →
        2024-12-31) and assigns ``user_budget_owner`` as the
        responsible user so subsequent tests have deterministic
        permission semantics.  Any keyword argument supplied via
        ``overrides`` replaces the corresponding default value
        before the create call — pass ``reference=...`` to bypass
        the sequence-driven auto-generation (used by
        :meth:`test_bm001_unique_reference_per_company_constraint`).

        Args:
            **overrides: Keyword arguments overriding the default
                ``name``, ``date_from``, ``date_to``, ``user_id``,
                or any other ``budget.budget`` field.

        Returns:
            recordset: The created ``budget.budget`` record.
        """
        vals = {
            'name': 'Annual Budget 2024',
            'date_from': date(2024, 1, 1),
            'date_to': date(2024, 12, 31),
            'user_id': self.user_budget_owner.id,
        }
        vals.update(overrides)
        return self.env['budget.budget'].create(vals)

    def _add_line(self, budget, **overrides):
        """Add a budget line to ``budget`` with sensible defaults.

        Defaults to the test expense account and a planned amount of
        10000.0 — both safely on the BM-001 allow list and well above
        the positive-line threshold for ``action_confirm``.

        Args:
            budget: The parent ``budget.budget`` recordset (must be
                a single record).
            **overrides: Keyword arguments overriding the default
                ``budget_id``, ``account_id``, ``planned_amount``,
                ``analytic_distribution``, or any other
                ``budget.budget.line`` field.

        Returns:
            recordset: The created ``budget.budget.line`` record.
        """
        vals = {
            'budget_id': budget.id,
            'account_id': self.test_expense.id,
            'planned_amount': 10000.0,
        }
        vals.update(overrides)
        return self.env['budget.budget.line'].create(vals)

    # ==================================================================
    # Scenario 1 — Create budget with required attributes
    # ==================================================================

    def test_bm001_create_budget_with_required_fields(self):
        """Creating a budget with required fields saves it in draft.

        Validates BM-001 Scenario 1: a freshly-created budget has
        ``state='draft'``, an auto-generated ``reference`` (NOT the
        ``'New'`` placeholder), the supplied name, the assigned
        responsible user, ``active=True``, and a ``currency_id``
        related to the company's currency.

        Uses ``fields.Date.to_date`` to construct the expected
        boundary values so the comparison runs through Odoo's
        canonical date converter — protecting the test against
        accidental string/date type mismatches at the ORM
        boundary.
        """
        budget = self._create_budget()
        self.assertEqual(budget.state, 'draft')
        self.assertTrue(budget.reference)
        self.assertNotEqual(budget.reference, 'New')
        self.assertEqual(budget.name, 'Annual Budget 2024')
        self.assertEqual(budget.user_id, self.user_budget_owner)
        self.assertTrue(budget.active)
        # currency_id is related to company_id.currency_id (stored
        # related field; loads the currency from the active company).
        self.assertEqual(
            budget.currency_id,
            self.env.company.currency_id,
        )
        # Round-trip the fiscal-window dates through
        # ``fields.Date.to_date`` to confirm the stored Date values
        # match the canonical ISO representation of the expected
        # boundaries (deterministic — no time-zone or naïve-datetime
        # ambiguity).
        self.assertEqual(
            budget.date_from,
            fields.Date.to_date('2024-01-01'),
        )
        self.assertEqual(
            budget.date_to,
            fields.Date.to_date('2024-12-31'),
        )

    def test_bm001_reference_auto_generated_via_sequence(self):
        """The ``reference`` field is populated via ``ir.sequence``.

        Verifies the BM-001 Scenario 6 acceptance criterion that
        each budget receives a unique system-generated reference.
        Two budgets created back-to-back must produce DISTINCT
        truthy reference values, proving that the sequence advances
        between create calls.
        """
        budget1 = self._create_budget(name='Budget One')
        budget2 = self._create_budget(name='Budget Two')
        self.assertTrue(budget1.reference)
        self.assertTrue(budget2.reference)
        self.assertNotEqual(budget1.reference, budget2.reference)

    def test_bm001_missing_required_date_from_raises(self):
        """Omitting ``date_from`` raises a database-level error.

        ``date_from`` is declared with ``required=True`` on
        ``budget.budget``, which translates to a NOT NULL constraint
        on the underlying column.  In the test context (which
        bypasses Odoo's HTTP-layer ``retrying`` wrapper that would
        re-raise the integrity error as a ``ValidationError``), the
        raw ``psycopg2.errors.NotNullViolation`` propagates — caught
        here via its parent ``psycopg2.IntegrityError`` class.

        ``mute_logger('odoo.sql_db')`` suppresses the noisy SQL
        error logging that would otherwise pollute the test output.
        """
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            with self.env.cr.savepoint():
                self.env['budget.budget'].create({
                    'name': 'Broken — Missing date_from',
                    'date_to': date(2024, 12, 31),
                })

    def test_bm001_missing_required_date_to_raises(self):
        """Omitting ``date_to`` raises a database-level error.

        Mirror of :meth:`test_bm001_missing_required_date_from_raises`
        for the ``date_to`` field.  Both endpoints of the fiscal
        window are required to define a budget; in the test context
        the NOT NULL violation surfaces as ``IntegrityError`` (the
        psycopg2 parent class of ``NotNullViolation``).
        """
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            with self.env.cr.savepoint():
                self.env['budget.budget'].create({
                    'name': 'Broken — Missing date_to',
                    'date_from': date(2024, 1, 1),
                })

    def test_bm001_date_from_after_date_to_constrains(self):
        """The ``@api.constrains`` rejects inverted date ranges.

        ``_check_dates`` raises ``ValidationError`` when
        ``date_from > date_to``.  Equal dates (single-day budgets)
        are explicitly allowed by the constraint logic, so the test
        uses dates spanning a full year in the wrong order.
        """
        with self.assertRaises(ValidationError):
            self._create_budget(
                date_from=date(2024, 12, 31),
                date_to=date(2024, 1, 1),
            )

    # ==================================================================
    # Scenario 2 — Assign budget lines to GL accounts
    #              (income / expense types only)
    # ==================================================================

    def test_bm001_budget_line_accepts_expense_account(self):
        """Budget lines can reference expense accounts.

        Verifies the BM-001 Scenario 2 acceptance criterion that GL
        accounts of type ``expense`` are accepted as budget-line
        targets.  The ``account_type`` related field cascades from
        ``account.account.account_type`` and is stored for indexed
        filtering.
        """
        budget = self._create_budget()
        line = self._add_line(budget, account_id=self.test_expense.id)
        self.assertEqual(line.account_id, self.test_expense)
        self.assertEqual(line.account_type, 'expense')

    def test_bm001_budget_line_accepts_income_account(self):
        """Budget lines can reference income accounts.

        Mirror of :meth:`test_bm001_budget_line_accepts_expense_account`
        for the income account allow-list entry.
        """
        budget = self._create_budget()
        line = self._add_line(budget, account_id=self.test_revenue.id)
        self.assertEqual(line.account_id, self.test_revenue)
        self.assertEqual(line.account_type, 'income')

    def test_bm001_budget_line_rejects_receivable_account(self):
        """Budget lines reject balance-sheet accounts.

        ``_check_account_type`` is an ``@api.constrains('account_id')``
        hook that raises ``ValidationError`` when the account's
        ``account_type`` is not in the BM-001 allow list (income /
        expense variants only).  ``asset_receivable`` is a
        balance-sheet type and must be rejected.
        """
        budget = self._create_budget()
        with self.assertRaises(ValidationError):
            self._add_line(budget, account_id=self.test_receivable.id)

    def test_bm001_budget_line_planned_amount_cannot_be_negative(self):
        """Planned amount cannot be negative.

        ``_check_planned_amount`` enforces the non-negative invariant
        — zero is allowed (placeholder rows for accounts that WILL
        have budget allocated later) but strictly negative values
        are categorically rejected.
        """
        budget = self._create_budget()
        with self.assertRaises(ValidationError):
            self._add_line(budget, planned_amount=-500.0)

    def test_bm001_display_name_includes_account_code(self):
        """``display_name`` is composed from account display name.

        ``_compute_display_name`` produces a human-readable label
        derived from ``account.account.display_name`` (which
        embeds the account ``code``) plus any optional
        ``description``.  The test confirms the account ``code``
        appears in the rendered display name.
        """
        budget = self._create_budget()
        line = self._add_line(budget)
        self.assertIn(
            self.test_expense.code,
            line.display_name or '',
        )

    # ==================================================================
    # Scenario 3 — Analytic distribution via analytic.mixin
    # ==================================================================

    def test_bm001_budget_line_accepts_analytic_distribution(self):
        """Budget line inherits ``analytic.mixin``; accepts JSON dict.

        Validates BM-001 Scenario 3 — a budget line can carry an
        analytic distribution targeting one or more analytic
        accounts via the JSON dict pattern established by
        ``analytic.mixin``.  The test verifies the simplest single-
        analytic case (100% of the line's planned amount on a
        single analytic dimension).
        """
        budget = self._create_budget()
        line = self._add_line(
            budget,
            analytic_distribution={
                str(self.analytic_marketing.id): 100.0,
            },
        )
        self.assertTrue(line.analytic_distribution)
        self.assertIn(
            str(self.analytic_marketing.id),
            line.analytic_distribution,
        )

    def test_bm001_budget_line_supports_multi_key_distribution(self):
        """Distribution supports multiple analytic accounts.

        BM-001 Scenario 3 explicitly allows distributions that span
        multiple analytic accounts within a plan, with percentages
        that sum to 100% per plan.  The test verifies a 60/40 split
        across the Marketing and Operations analytic accounts.
        """
        budget = self._create_budget()
        line = self._add_line(
            budget,
            analytic_distribution={
                str(self.analytic_marketing.id): 60.0,
                str(self.analytic_operations.id): 40.0,
            },
        )
        self.assertEqual(len(line.analytic_distribution), 2)
        self.assertAlmostEqual(
            line.analytic_distribution[
                str(self.analytic_marketing.id)
            ],
            60.0,
            places=2,
        )
        self.assertAlmostEqual(
            line.analytic_distribution[
                str(self.analytic_operations.id)
            ],
            40.0,
            places=2,
        )

    def test_bm001_analytic_account_exposes_budget_lines(self):
        """``account.analytic.account`` exposes budget_line_ids.

        Validates the BM-001 Scenario 3 inverse-relation requirement
        — a user viewing an analytic account sees every budget line
        referencing it via ``analytic_distribution``.  The
        ``_compute_budget_line_ids`` compute method delegates to
        ``analytic.mixin.distribution_analytic_account_ids`` for
        efficient JSONB GIN-indexed lookup, and the paired
        ``_search_budget_line_ids`` enables domain-based filtering
        (``[('budget_line_ids', 'in', [line.id])]``) on the analytic
        account model.

        The test also exercises the BM-001 sibling computed fields
        (``budget_line_count``, ``budget_amount_planned``,
        ``budget_consumption_percent``) and the smart-button action
        (``action_open_budget_lines``) — collectively these cover
        every BM-001-scope member exposed by the
        ``account.analytic.account`` ``_inherit`` extension.
        """
        budget = self._create_budget()
        line = self._add_line(
            budget,
            planned_amount=100000.0,
            analytic_distribution={
                str(self.analytic_marketing.id): 100.0,
            },
        )
        # Force a recompute by invalidating the cached value on the
        # analytic record before reading the computed fields.
        self.analytic_marketing.invalidate_recordset()
        # 1. ``budget_line_ids`` must be a recordset (not None) and
        # must include the line we just created.  The compute method
        # returns the empty recordset for un-saved analytic accounts;
        # for saved ones it issues a search() against the JSONB GIN
        # index.
        self.assertIsNotNone(self.analytic_marketing.budget_line_ids)
        self.assertIn(line, self.analytic_marketing.budget_line_ids)
        # 2. ``budget_line_count`` exposes a counter for the analytic-
        # form smart button (triggers ``_compute_budget_line_count``).
        self.assertGreaterEqual(
            self.analytic_marketing.budget_line_count,
            1,
        )
        # 3. ``budget_amount_planned`` weights the planned amount by
        # the distribution percentage (100% of 100,000 = 100,000) —
        # triggers ``_compute_budget_amounts``.
        self.assertAlmostEqual(
            self.analytic_marketing.budget_amount_planned,
            100000.0,
            places=2,
        )
        # 4. ``budget_consumption_percent`` is 0% with no posted
        # actuals (triggers the same ``_compute_budget_amounts`` —
        # planned > 0 path with zero actual).
        self.assertAlmostEqual(
            self.analytic_marketing.budget_consumption_percent,
            0.0,
            places=2,
        )
        # 5. The reverse-search domain (``budget_line_ids in [...]``)
        # routes through ``_search_budget_line_ids`` and resolves to
        # an indirect domain on ``id`` driven by the
        # ``analytic_distribution`` JSON keys.
        analytics = self.env['account.analytic.account'].search([
            ('budget_line_ids', 'in', [line.id]),
        ])
        self.assertIn(self.analytic_marketing, analytics)
        # 6. Smart-button action ``action_open_budget_lines`` returns
        # a properly configured ``ir.actions.act_window`` targeting
        # ``budget.budget.line``.
        action = self.analytic_marketing.action_open_budget_lines()
        self.assertEqual(action.get('type'), 'ir.actions.act_window')
        self.assertEqual(
            action.get('res_model'),
            'budget.budget.line',
        )

    # ==================================================================
    # Scenario 4 — State transitions
    #              (draft → confirmed → closed; manager-gated reset)
    # ==================================================================

    def test_bm001_action_confirm_with_valid_lines_succeeds(self):
        """Confirming a budget with a positive line transitions it.

        Validates BM-001 Scenario 4 happy path — a draft budget with
        at least one line carrying a positive ``planned_amount``
        transitions to ``confirmed`` via ``action_confirm``.
        """
        budget = self._create_budget()
        self._add_line(budget, planned_amount=5000.0)
        budget.action_confirm()
        self.assertEqual(budget.state, 'confirmed')

    def test_bm001_action_confirm_without_lines_raises(self):
        """Confirming a line-less budget raises UserError.

        BM-001 Scenario 4 validation: every confirmed budget must
        carry at least one budget line.  An empty budget is
        meaningless as a financial target and is rejected at the
        Python level (UserError, not a ValidationError, because the
        check is in an action method rather than ``@api.constrains``).
        """
        budget = self._create_budget()
        with self.assertRaises(UserError):
            budget.action_confirm()

    def test_bm001_action_confirm_with_zero_planned_line_raises(self):
        """Confirming with only zero-amount lines raises UserError.

        BM-001 Scenario 4 validation: a budget consisting entirely
        of zero-amount lines is meaningless as a financial target.
        At least ONE line must carry a strictly-positive planned
        amount before the budget can transition to confirmed.
        """
        budget = self._create_budget()
        self._add_line(budget, planned_amount=0.0)
        with self.assertRaises(UserError):
            budget.action_confirm()

    def test_bm001_action_confirm_from_non_draft_raises(self):
        """Cannot re-confirm an already-confirmed budget.

        ``action_confirm`` enforces the state precondition
        ``state == 'draft'``; calling it on a confirmed budget
        raises ``UserError`` with a message identifying the current
        state.
        """
        budget = self._create_budget()
        self._add_line(budget, planned_amount=5000.0)
        budget.action_confirm()
        with self.assertRaises(UserError):
            budget.action_confirm()

    def test_bm001_action_close_from_confirmed_succeeds(self):
        """Closing a confirmed budget transitions it to closed.

        BM-001 Scenario 4 closing transition: a confirmed budget
        moves to ``closed`` via ``action_close``.  No additional
        validation is performed at close time (the planning
        validations all ran at confirm).
        """
        budget = self._create_budget()
        self._add_line(budget, planned_amount=5000.0)
        budget.action_confirm()
        budget.action_close()
        self.assertEqual(budget.state, 'closed')

    def test_bm001_action_close_from_draft_raises(self):
        """Cannot close a draft budget.

        ``action_close`` enforces the state precondition
        ``state == 'confirmed'``.  Closing a draft budget skips the
        confirmation step and is therefore rejected.
        """
        budget = self._create_budget()
        with self.assertRaises(UserError):
            budget.action_close()

    def test_bm001_action_cancel_from_closed_raises(self):
        """Cannot cancel a closed budget.

        ``cancelled`` is an orthogonal terminal state distinct from
        ``closed`` — a closed budget has completed its fiscal
        lifecycle whereas a cancelled budget was abandoned before
        completion.  Re-cancelling a closed budget violates the
        state machine and raises ``UserError``.  A manager must
        first reset the budget to draft if cancellation is
        required.
        """
        budget = self._create_budget()
        self._add_line(budget, planned_amount=5000.0)
        budget.action_confirm()
        budget.action_close()
        with self.assertRaises(UserError):
            budget.action_cancel()

    def test_bm001_action_reset_draft_requires_manager(self):
        """Only account managers can reset a confirmed budget.

        Validates BM-001 Scenario 4 + security requirement:
        ``action_reset_draft`` checks
        ``self.env.user.has_group('account.group_account_manager')``
        before allowing the transition.  A regular accounting user
        (``account.group_account_user`` only) is rejected; a manager
        succeeds.

        The rejection can manifest as either ``UserError`` (the
        explicit Python-level guard inside
        :meth:`budget.budget.action_reset_draft`) or ``AccessError``
        (the ACL-level rejection raised by
        ``account.group_account_manager``-protected operations in
        a strict-security environment).  Odoo's overridden
        :meth:`assertRaises` does not natively support exception
        tuples (it calls ``issubclass(exception, AccessError)`` for
        a cache-clearing optimisation, which fails on tuples), so
        the test uses a plain ``try/except`` block scoped by an
        explicit ``cr.savepoint()`` so the failed action does not
        contaminate the surrounding test transaction.
        """
        budget = self._create_budget()
        self._add_line(budget, planned_amount=5000.0)
        budget.action_confirm()
        # Regular user cannot reset.  Use try/except + savepoint so we
        # can catch the union of (UserError, AccessError) without
        # tripping Odoo's tuple-incompatible assertRaises override.
        user_regular = self.user_budget_owner
        rejection_raised = False
        try:
            with self.env.cr.savepoint():
                budget.with_user(user_regular).action_reset_draft()
        except (UserError, AccessError):
            rejection_raised = True
        self.assertTrue(
            rejection_raised,
            'Regular user should be rejected with UserError or '
            'AccessError when calling action_reset_draft.',
        )
        # Manager succeeds.
        budget.with_user(self.user_manager).action_reset_draft()
        self.assertEqual(budget.state, 'draft')

    # ==================================================================
    # Scenario 5 — Duplication produces draft "(copy)" with
    #              ``copied_from_id`` audit-trail link
    # ==================================================================

    def test_bm001_copy_produces_draft_with_copy_suffix(self):
        """Duplicating creates a draft with ``(copy)`` suffix.

        Validates BM-001 Scenario 5 — the duplicate budget:

        * Is in ``draft`` state regardless of the source's state.
        * Has ``(copy)`` appended to its name (case-insensitive
          substring check tolerates locale-specific translations
          of the suffix).
        * Carries ``copied_from_id`` linking back to the source
          for audit-trail continuity.
        * Has its own freshly-generated ``reference`` distinct from
          the source's.
        """
        budget = self._create_budget()
        self._add_line(budget, planned_amount=10000.0)
        budget.action_confirm()
        clone = budget.copy()
        self.assertEqual(clone.state, 'draft')
        self.assertIn('copy', clone.name.lower())
        self.assertEqual(clone.copied_from_id, budget)
        # Reference must be regenerated (new sequence value, not the
        # original).  The ``copy_data`` override resets the reference
        # to ``_('New')``, and the ``create`` override then re-runs
        # the sequence.
        self.assertNotEqual(clone.reference, budget.reference)
        self.assertTrue(clone.reference)

    def test_bm001_copy_copies_lines(self):
        """Duplicating a budget copies its lines.

        Validates the BM-001 Scenario 5 acceptance criterion that
        the duplicate carries the same line structure as the source.
        ``line_ids`` is declared with ``copy=True`` so each line is
        cloned (and reattached to the duplicate via the
        ``budget_id`` Many2one).
        """
        budget = self._create_budget()
        self._add_line(budget, planned_amount=10000.0)
        self._add_line(
            budget,
            planned_amount=5000.0,
            account_id=self.test_revenue.id,
        )
        clone = budget.copy()
        self.assertEqual(len(clone.line_ids), 2)
        # All cloned lines belong to the duplicate, not the source.
        for line in clone.line_ids:
            self.assertEqual(line.budget_id, clone)

    # ==================================================================
    # Scenario 6 — Unique reference per company (SQL constraint)
    # ==================================================================

    def test_bm001_unique_reference_per_company_constraint(self):
        """Two budgets cannot share a reference within a company.

        Validates the BM-001 Scenario 6 invariant via the
        ``_unique_reference_per_company`` ``models.Constraint``
        (UNIQUE ``(reference, company_id)``).  The test forces a
        reference collision by passing the original reference value
        explicitly to the second create call — this bypasses the
        ``create`` override's sequence-based assignment (which only
        runs when the reference is absent or equal to the
        ``'New'`` placeholder).

        ``mute_logger('odoo.sql_db')`` suppresses the noisy
        psycopg2 error trace that would otherwise pollute the test
        output, and ``self.env.cr.savepoint()`` isolates the
        violation so the surrounding test transaction remains
        usable for cleanup.

        ``IntegrityError`` and ``mute_logger`` are imported at
        module top-level (per the OCA convention adopted across
        ``account_budget_management.tests``) — psycopg2 is a hard
        dependency of the Odoo runtime and is always importable in
        any valid test environment.
        """
        budget1 = self._create_budget()
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            with self.env.cr.savepoint():
                # Pass the original reference verbatim so the create
                # override's "if not vals.get('reference') ..." branch
                # does NOT regenerate the value — the SQL UNIQUE
                # constraint then rejects the duplicate at INSERT time.
                self._create_budget(
                    name='Duplicate Reference',
                    reference=budget1.reference,
                )

    # ==================================================================
    # Multi-Company Isolation
    # ==================================================================

    def test_bm001_multi_company_isolation(self):
        """Budgets are scoped by ``company_id``; ``ir.rule`` filters.

        Validates the BM-001 multi-company invariant: a budget
        created in company A is not visible from a search executed
        with the company A active context EXCLUDING company B's
        records (and vice versa).  The test uses
        :meth:`AccountTestInvoicingCommon.setup_other_company` to
        provision a second company with its own chart of accounts
        and journals, then creates one budget in each and confirms
        the visibility scoping.
        """
        company_a = self.company_data['company']
        company_b = self.setup_other_company()['company']
        budget_a = self._create_budget()
        self.assertEqual(budget_a.company_id, company_a)
        # Create budget_b in company_b's context — the ``with_company``
        # call switches ``self.env.company`` so the company_id default
        # lambda evaluates to company_b.  No user_id is supplied so
        # the default (env.user — admin in tests) applies; admin has
        # access to all companies and avoids a multi-company validation
        # error on the responsible-user assignment.
        budget_b = self.env['budget.budget'].with_company(company_b).create({
            'name': 'Company B Budget',
            'date_from': date(2024, 1, 1),
            'date_to': date(2024, 12, 31),
        })
        self.assertEqual(budget_b.company_id, company_b)
        # Search from company_a's perspective — budget_a appears,
        # budget_b is excluded by the multi-company ``ir.rule``.
        visible_a = self.env['budget.budget'].with_company(
            company_a,
        ).search([])
        self.assertIn(budget_a, visible_a)
        self.assertNotIn(budget_b, visible_a)

    # ==================================================================
    # Computed totals + smart-button actions
    # ==================================================================

    def test_bm001_line_count_and_total_planned_computed(self):
        """``line_count`` and ``total_planned`` reflect line_ids.

        Verifies the two BM-001 aggregate computed fields:

        * ``line_count`` (``_compute_line_count``) reports the number
          of attached budget lines.
        * ``total_planned`` (``_compute_total_planned``) sums the
          ``planned_amount`` across all lines as a stored field
          (``store=True``) so search/group-by operations can use the
          indexed column.
        """
        budget = self._create_budget()
        self._add_line(budget, planned_amount=10000.0)
        self._add_line(
            budget,
            planned_amount=5000.0,
            account_id=self.test_revenue.id,
        )
        self.assertEqual(budget.line_count, 2)
        self.assertAlmostEqual(budget.total_planned, 15000.0, places=2)

    def test_bm001_action_open_lines_returns_act_window(self):
        """``action_open_lines`` returns a properly configured action.

        The smart button on the budget form opens the line list
        filtered to the current budget.  The action must:

        * Be of type ``ir.actions.act_window``.
        * Target ``budget.budget.line`` as the model.
        * Carry a domain restricting results to the current
          budget's lines (via the ``budget_id`` filter).
        """
        budget = self._create_budget()
        self._add_line(budget)
        action = budget.action_open_lines()
        self.assertEqual(action.get('type'), 'ir.actions.act_window')
        self.assertEqual(
            action.get('res_model'),
            'budget.budget.line',
        )
        # The domain restricts to lines of THIS budget so the user
        # only sees the relevant rows.
        self.assertIn(
            ('budget_id', '=', budget.id),
            action.get('domain', []),
        )
