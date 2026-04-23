
# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Test Suite for BM-001: Budget Definition

Implements comprehensive tests for ``budget.budget`` header and
``budget.budget.line`` detail models, plus the
``account.analytic.account`` ``_inherit`` extension (budget-aware
computed fields). Covers all six BDD scenarios from the ticket:

* Scenario 1 — Create a new budget with required fields (name +
  fiscal period) and optional owner/description. The budget saves in
  ``draft`` state with an auto-generated unique reference.
* Scenario 2 — Add budget lines with a GL account (expense/income
  types only) and a non-negative planned amount. Server-side
  ``_check_account_type`` rejects balance-sheet account types
  (``asset_*``, ``liability_*``, ``equity``, ``off_balance``).
* Scenario 3 — Attach an analytic distribution via ``analytic.mixin``
  to a budget line. The distribution is stored as a JSON dict of
  ``{"analytic_account_id": percentage}`` pairs; multi-plan keys use
  comma-separated IDs.
* Scenario 4 — ``action_confirm`` validates (a) state=='draft',
  (b) at least one line exists, and (c) at least one line carries a
  positive ``planned_amount``. Failure raises ``UserError`` with a
  specific message.
* Scenario 5 — Duplicate via ``copy`` produces a fresh draft record:
  name gets a ``(copy)`` suffix, reference resets so ``create``
  re-generates a unique one, ``copied_from_id`` is set to the source,
  and the source budget itself is left unchanged.
* Scenario 6 — Reference uniqueness is enforced per-company via the
  ``_unique_reference_per_company`` Odoo-19 ``models.Constraint``.
  The ``ir.sequence`` code ``budget.budget`` generates values
  monotonically per company.

Additional assertions cover:

* ``_check_dates`` — rejects ``date_from > date_to`` with
  ``ValidationError``.
* State transitions — ``action_close`` (confirmed→closed),
  ``action_reset_draft`` requires ``account.group_account_manager``
  (rejects non-managers with ``UserError``), ``action_cancel``
  refuses to cancel a closed budget.
* ``account.analytic.account`` computed fields
  ``budget_line_ids`` / ``budget_line_count`` / ``budget_amount_planned``
  / ``budget_amount_actual`` / ``budget_consumption_percent`` plus
  the ``_search_budget_line_ids`` search helper and the
  ``action_open_budget_lines`` action.
* Smart-button actions ``action_open_lines`` and
  ``action_open_alerts`` on ``budget.budget``.

Target: >=80% line coverage per Rule R-04 for BM-001.

This file uses an inline ``setUpClass`` (no shared ``common.py``) per
the Checkpoint 6 instruction that BM-001 tests must be self-contained
and mirror the pattern established in ``test_bm_003.py`` /
``test_bm_005.py``.
"""

from datetime import date

from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tools import float_compare, mute_logger

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestBudgetDefinition(AccountTestInvoicingCommon):
    """
    Test class for BM-001: Budget Definition.

    Validates ``budget.budget``, ``budget.budget.line`` and the
    ``account.analytic.account`` extension.  The class sets up a
    minimal chart of accounts (expense, expense_other, income,
    cash), an analytic plan with two analytic accounts (``Sales``
    and ``Marketing``), and a journal reference to generate
    actuals for analytic-aware budget tests.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        AccountAccount = cls.env['account.account']

        # ----------------------------------------------------------
        # Test GL accounts — XTEST.* namespace so we never collide
        # with the chart of accounts loaded by the Odoo test harness.
        # Account types cover the allow list (expense / expense_other
        # / income) plus one balance-sheet asset type used for
        # rejection tests.
        # ----------------------------------------------------------
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
        cls.test_receivable = AccountAccount.create({
            'code': 'XTEST.11000',
            'name': 'Test Receivable',
            'account_type': 'asset_receivable',
            'reconcile': True,
        })

        # ----------------------------------------------------------
        # Analytic plan + two analytic accounts for Scenario 3
        # (analytic distribution) and for the
        # ``account.analytic.account`` ``_inherit`` extension tests.
        # ----------------------------------------------------------
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

        # Convenience handle for posting balanced journal entries.
        cls.journal_misc = cls.company_data['default_journal_misc']

        # ----------------------------------------------------------
        # A confirmed-ready budget covering fiscal year 2024 is
        # NOT created here. Each test creates its own budget so the
        # initial state is deterministic (draft, no lines) for
        # Scenario 1 / 4 / 5 assertions.
        # ----------------------------------------------------------

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------

    def _make_budget(self, name='FY2024', date_from=None, date_to=None,
                     user_id=None, description=None):
        """Create a draft budget with optional overrides.

        Defaults to a full FY2024 window (2024-01-01 → 2024-12-31)
        so that subsequent tests can add lines with matching dates.
        """
        vals = {
            'name': name,
            'date_from': date_from or date(2024, 1, 1),
            'date_to': date_to or date(2024, 12, 31),
        }
        if user_id is not None:
            vals['user_id'] = user_id
        if description is not None:
            vals['description'] = description
        return self.env['budget.budget'].create(vals)

    def _post_entry(self, account, amount, entry_date,
                    analytic_distribution=None):
        """Create and post a balanced journal entry (debit account,
        credit cash) optionally with an analytic distribution.
        Returns the resulting ``account.move``.
        """
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

    # ------------------------------------------------------------------
    # Scenario 1 — Create budget with required + optional fields
    # ------------------------------------------------------------------

    def test_bm001_scenario1_create_budget_defaults_to_draft(self):
        """Creating a budget with name + fiscal period saves in draft."""
        budget = self._make_budget(name='FY2024')
        self.assertEqual(budget.state, 'draft')
        self.assertEqual(budget.name, 'FY2024')
        self.assertEqual(budget.date_from, date(2024, 1, 1))
        self.assertEqual(budget.date_to, date(2024, 12, 31))
        # Active default is True
        self.assertTrue(budget.active)

    def test_bm001_scenario1_reference_is_generated_and_non_blank(self):
        """``ir.sequence`` populates ``reference`` to a non-New value."""
        budget = self._make_budget(name='FY2024 Seq Test')
        self.assertTrue(budget.reference)
        # The sequence prefix from budget_data.xml is "BUD/" — absence
        # of the literal "New" placeholder is the primary invariant,
        # and the reference is a non-empty string.
        self.assertNotEqual(budget.reference, 'New')

    def test_bm001_scenario1_optional_user_id_is_persisted(self):
        """Optional ``user_id`` saves without validation error."""
        budget = self._make_budget(
            name='FY2024 Owner',
            user_id=self.env.user.id,
        )
        self.assertEqual(budget.user_id, self.env.user)

    def test_bm001_scenario1_optional_description_is_persisted(self):
        """Optional description is stored as entered."""
        budget = self._make_budget(
            name='FY2024 Desc',
            description='Primary operating budget for 2024 fiscal year.',
        )
        self.assertEqual(
            budget.description,
            'Primary operating budget for 2024 fiscal year.',
        )

    def test_bm001_scenario1_period_type_default_is_annual(self):
        """``period_type`` default is ``annual`` per model definition."""
        budget = self._make_budget()
        self.assertEqual(budget.period_type, 'annual')

    def test_bm001_scenario1_company_id_defaults_to_env_company(self):
        """``company_id`` defaults to ``self.env.company``."""
        budget = self._make_budget()
        self.assertEqual(budget.company_id, self.env.company)
        # Currency cascades from the company.
        self.assertEqual(budget.currency_id, self.env.company.currency_id)

    # ------------------------------------------------------------------
    # Scenario 2 — Add budget lines (with valid/invalid account types)
    # ------------------------------------------------------------------

    def test_bm001_scenario2_add_line_with_expense_account(self):
        """A budget line with an ``expense`` account is accepted."""
        budget = self._make_budget()
        line = self.env['budget.budget.line'].create({
            'budget_id': budget.id,
            'account_id': self.test_expense.id,
            'planned_amount': 100000.0,
        })
        self.assertEqual(line.account_type, 'expense')
        self.assertAlmostEqual(line.planned_amount, 100000.0, places=2)
        self.assertIn(line, budget.line_ids)

    def test_bm001_scenario2_add_line_with_income_account(self):
        """A budget line with an ``income`` account is accepted."""
        budget = self._make_budget()
        line = self.env['budget.budget.line'].create({
            'budget_id': budget.id,
            'account_id': self.test_revenue.id,
            'planned_amount': 200000.0,
        })
        self.assertEqual(line.account_type, 'income')
        self.assertAlmostEqual(line.planned_amount, 200000.0, places=2)

    def test_bm001_scenario2_add_line_with_expense_other(self):
        """Account type ``expense_other`` is on the allow list."""
        budget = self._make_budget()
        line = self.env['budget.budget.line'].create({
            'budget_id': budget.id,
            'account_id': self.test_expense_marketing.id,
            'planned_amount': 50000.0,
        })
        self.assertEqual(line.account_type, 'expense_other')

    def test_bm001_scenario2_reject_line_with_asset_account(self):
        """``_check_account_type`` rejects balance-sheet accounts."""
        budget = self._make_budget()
        with self.assertRaises(ValidationError) as ctx:
            self.env['budget.budget.line'].create({
                'budget_id': budget.id,
                'account_id': self.test_cash.id,
                'planned_amount': 10000.0,
            })
        # The message identifies the offending account type and lists
        # the allow list — assert key fragments to confirm the match.
        self.assertIn('asset_cash', str(ctx.exception))
        self.assertIn('not allowed', str(ctx.exception))

    def test_bm001_scenario2_reject_line_with_receivable_account(self):
        """Receivable account (asset_receivable) is rejected."""
        budget = self._make_budget()
        with self.assertRaises(ValidationError):
            self.env['budget.budget.line'].create({
                'budget_id': budget.id,
                'account_id': self.test_receivable.id,
                'planned_amount': 1000.0,
            })

    def test_bm001_scenario2_reject_negative_planned_amount(self):
        """``_check_planned_amount`` rejects negative amounts."""
        budget = self._make_budget()
        with self.assertRaises(ValidationError) as ctx:
            self.env['budget.budget.line'].create({
                'budget_id': budget.id,
                'account_id': self.test_expense.id,
                'planned_amount': -500.0,
            })
        self.assertIn('negative', str(ctx.exception))

    def test_bm001_scenario2_accept_zero_planned_amount(self):
        """A planned amount of zero is a legitimate placeholder."""
        budget = self._make_budget()
        line = self.env['budget.budget.line'].create({
            'budget_id': budget.id,
            'account_id': self.test_expense.id,
            'planned_amount': 0.0,
        })
        self.assertAlmostEqual(line.planned_amount, 0.0, places=2)

    def test_bm001_scenario2_line_cascades_company_and_currency(self):
        """Line ``company_id`` / ``currency_id`` cascade from budget."""
        budget = self._make_budget()
        line = self.env['budget.budget.line'].create({
            'budget_id': budget.id,
            'account_id': self.test_expense.id,
            'planned_amount': 1000.0,
        })
        self.assertEqual(line.company_id, budget.company_id)
        self.assertEqual(line.currency_id, budget.currency_id)

    def test_bm001_scenario2_line_display_name_contains_account(self):
        """``display_name`` renders account + optional description."""
        budget = self._make_budget()
        line = self.env['budget.budget.line'].create({
            'budget_id': budget.id,
            'account_id': self.test_expense.id,
            'planned_amount': 1000.0,
        })
        self.assertIn(
            self.test_expense.display_name,
            line.display_name,
        )

    # ------------------------------------------------------------------
    # Scenario 3 — Analytic distribution on budget lines
    # ------------------------------------------------------------------

    def test_bm001_scenario3_single_plan_analytic_distribution(self):
        """Single-plan distribution key stores as JSON dict."""
        budget = self._make_budget()
        distribution = {str(self.analytic_sales.id): 100.0}
        line = self.env['budget.budget.line'].create({
            'budget_id': budget.id,
            'account_id': self.test_expense.id,
            'planned_amount': 100000.0,
            'analytic_distribution': distribution,
        })
        self.assertTrue(line.analytic_distribution)
        # The analytic_distribution JSON dict preserves the ID->% mapping.
        self.assertEqual(
            line.analytic_distribution[str(self.analytic_sales.id)],
            100.0,
        )

    def test_bm001_scenario3_split_distribution_across_accounts(self):
        """Split 50/50 distribution across two analytic accounts."""
        budget = self._make_budget()
        distribution = {
            str(self.analytic_sales.id): 50.0,
            str(self.analytic_marketing.id): 50.0,
        }
        line = self.env['budget.budget.line'].create({
            'budget_id': budget.id,
            'account_id': self.test_expense.id,
            'planned_amount': 100000.0,
            'analytic_distribution': distribution,
        })
        # Distribution dict must preserve both entries with 50.0 each.
        self.assertAlmostEqual(
            line.analytic_distribution[str(self.analytic_sales.id)],
            50.0, places=2,
        )
        self.assertAlmostEqual(
            line.analytic_distribution[str(self.analytic_marketing.id)],
            50.0, places=2,
        )

    def test_bm001_scenario3_multi_plan_comma_separated_key(self):
        """Multi-plan keys use comma-separated IDs (analytic.mixin)."""
        budget = self._make_budget()
        combo_key = f"{self.analytic_sales.id},{self.analytic_marketing.id}"
        distribution = {combo_key: 100.0}
        line = self.env['budget.budget.line'].create({
            'budget_id': budget.id,
            'account_id': self.test_expense.id,
            'planned_amount': 100000.0,
            'analytic_distribution': distribution,
        })
        self.assertEqual(line.analytic_distribution[combo_key], 100.0)

    # ------------------------------------------------------------------
    # Scenario 4 — State transitions (action_confirm + failures)
    # ------------------------------------------------------------------

    def test_bm001_scenario4_action_confirm_happy_path(self):
        """Draft → Confirmed with at least one positive line."""
        budget = self._make_budget()
        self.env['budget.budget.line'].create({
            'budget_id': budget.id,
            'account_id': self.test_expense.id,
            'planned_amount': 100000.0,
        })
        budget.action_confirm()
        self.assertEqual(budget.state, 'confirmed')

    def test_bm001_scenario4_action_confirm_rejects_non_draft(self):
        """``action_confirm`` raises UserError on confirmed budget."""
        budget = self._make_budget()
        self.env['budget.budget.line'].create({
            'budget_id': budget.id,
            'account_id': self.test_expense.id,
            'planned_amount': 100000.0,
        })
        budget.action_confirm()
        # Attempt to confirm again: state is already 'confirmed'.
        with self.assertRaises(UserError) as ctx:
            budget.action_confirm()
        self.assertIn('draft', str(ctx.exception))

    def test_bm001_scenario4_action_confirm_rejects_no_lines(self):
        """``action_confirm`` raises UserError when no lines exist."""
        budget = self._make_budget()
        with self.assertRaises(UserError) as ctx:
            budget.action_confirm()
        self.assertIn('no budget lines', str(ctx.exception))

    def test_bm001_scenario4_action_confirm_rejects_all_zero_lines(self):
        """``action_confirm`` requires at least one positive line."""
        budget = self._make_budget()
        self.env['budget.budget.line'].create({
            'budget_id': budget.id,
            'account_id': self.test_expense.id,
            'planned_amount': 0.0,
        })
        with self.assertRaises(UserError) as ctx:
            budget.action_confirm()
        self.assertIn('positive planned amount', str(ctx.exception))

    def test_bm001_scenario4_action_close_happy_path(self):
        """Confirmed → Closed via ``action_close``."""
        budget = self._make_budget()
        self.env['budget.budget.line'].create({
            'budget_id': budget.id,
            'account_id': self.test_expense.id,
            'planned_amount': 100000.0,
        })
        budget.action_confirm()
        budget.action_close()
        self.assertEqual(budget.state, 'closed')

    def test_bm001_scenario4_action_close_rejects_draft(self):
        """``action_close`` raises UserError on non-confirmed budget."""
        budget = self._make_budget()
        with self.assertRaises(UserError) as ctx:
            budget.action_close()
        self.assertIn('confirmed', str(ctx.exception))

    def test_bm001_scenario4_action_reset_draft_requires_manager(self):
        """``action_reset_draft`` rejects users without manager group."""
        # Create a non-manager user.
        manager_group = self.env.ref('account.group_account_manager')
        user_group = self.env.ref('account.group_account_user')
        non_manager = self.env['res.users'].create({
            'name': 'Std Accountant',
            'login': 'bm001_non_manager',
            'group_ids': [Command.link(user_group.id)],
        })
        budget = self._make_budget()
        self.env['budget.budget.line'].create({
            'budget_id': budget.id,
            'account_id': self.test_expense.id,
            'planned_amount': 100000.0,
        })
        budget.action_confirm()
        # Attempt reset as non-manager.
        with self.assertRaises(UserError) as ctx:
            budget.with_user(non_manager).action_reset_draft()
        self.assertIn('managers', str(ctx.exception))
        # Verify manager group is NOT in the user's groups.
        self.assertNotIn(manager_group, non_manager.group_ids)

    def test_bm001_scenario4_action_reset_draft_allowed_for_manager(self):
        """A user with manager group may reset a confirmed budget."""
        manager_group = self.env.ref('account.group_account_manager')
        user_group = self.env.ref('account.group_account_user')
        # Managers also need the user group in the account module.
        manager = self.env['res.users'].create({
            'name': 'Acct Manager',
            'login': 'bm001_manager',
            'group_ids': [
                Command.link(user_group.id),
                Command.link(manager_group.id),
            ],
        })
        budget = self._make_budget()
        self.env['budget.budget.line'].create({
            'budget_id': budget.id,
            'account_id': self.test_expense.id,
            'planned_amount': 100000.0,
        })
        budget.action_confirm()
        budget.with_user(manager).action_reset_draft()
        self.assertEqual(budget.state, 'draft')

    def test_bm001_scenario4_action_reset_draft_idempotent_for_draft(self):
        """``action_reset_draft`` is a no-op on already-draft budgets."""
        manager_group = self.env.ref('account.group_account_manager')
        user_group = self.env.ref('account.group_account_user')
        manager = self.env['res.users'].create({
            'name': 'Acct Manager Idempotent',
            'login': 'bm001_manager_idem',
            'group_ids': [
                Command.link(user_group.id),
                Command.link(manager_group.id),
            ],
        })
        budget = self._make_budget()
        # State is draft — reset should be a no-op and not raise.
        budget.with_user(manager).action_reset_draft()
        self.assertEqual(budget.state, 'draft')

    def test_bm001_scenario4_action_cancel_allowed_for_draft(self):
        """``action_cancel`` transitions any non-closed budget."""
        budget = self._make_budget()
        budget.action_cancel()
        self.assertEqual(budget.state, 'cancelled')

    def test_bm001_scenario4_action_cancel_allowed_for_confirmed(self):
        """A confirmed budget can be cancelled."""
        budget = self._make_budget()
        self.env['budget.budget.line'].create({
            'budget_id': budget.id,
            'account_id': self.test_expense.id,
            'planned_amount': 100000.0,
        })
        budget.action_confirm()
        budget.action_cancel()
        self.assertEqual(budget.state, 'cancelled')

    def test_bm001_scenario4_action_cancel_rejects_closed(self):
        """``action_cancel`` raises UserError on a closed budget."""
        budget = self._make_budget()
        self.env['budget.budget.line'].create({
            'budget_id': budget.id,
            'account_id': self.test_expense.id,
            'planned_amount': 100000.0,
        })
        budget.action_confirm()
        budget.action_close()
        with self.assertRaises(UserError) as ctx:
            budget.action_cancel()
        self.assertIn('Closed', str(ctx.exception))

    # ------------------------------------------------------------------
    # Date validation (_check_dates constraint)
    # ------------------------------------------------------------------

    def test_bm001_check_dates_rejects_inverted_range(self):
        """``_check_dates`` rejects date_from > date_to."""
        with self.assertRaises(ValidationError) as ctx:
            self.env['budget.budget'].create({
                'name': 'Bad Dates',
                'date_from': date(2024, 12, 31),
                'date_to': date(2024, 1, 1),
            })
        self.assertIn('on or before', str(ctx.exception))

    def test_bm001_check_dates_accepts_equal_dates(self):
        """A single-day budget (date_from == date_to) is legal."""
        budget = self.env['budget.budget'].create({
            'name': 'Single Day',
            'date_from': date(2024, 6, 15),
            'date_to': date(2024, 6, 15),
        })
        self.assertEqual(budget.date_from, budget.date_to)

    # ------------------------------------------------------------------
    # Scenario 5 — Duplication via copy()
    # ------------------------------------------------------------------

    def test_bm001_scenario5_copy_produces_draft_with_suffix(self):
        """``copy`` returns a fresh draft with ``(copy)`` suffix."""
        budget = self._make_budget(name='FY2024')
        self.env['budget.budget.line'].create({
            'budget_id': budget.id,
            'account_id': self.test_expense.id,
            'planned_amount': 100000.0,
        })
        budget.action_confirm()
        copy = budget.copy()
        self.assertEqual(copy.state, 'draft')
        self.assertIn('(copy)', copy.name)
        self.assertIn('FY2024', copy.name)

    def test_bm001_scenario5_copy_regenerates_reference(self):
        """``copy`` regenerates a unique reference."""
        budget = self._make_budget(name='FY2024 Ref Test')
        copy = budget.copy()
        self.assertTrue(copy.reference)
        self.assertNotEqual(copy.reference, budget.reference)

    def test_bm001_scenario5_copy_sets_copied_from_id(self):
        """``copy`` sets ``copied_from_id`` to the source budget."""
        budget = self._make_budget(name='FY2024 Source')
        copy = budget.copy()
        self.assertEqual(copy.copied_from_id, budget)

    def test_bm001_scenario5_copy_duplicates_lines(self):
        """``line_ids`` is copied to the duplicate (copy=True)."""
        budget = self._make_budget()
        self.env['budget.budget.line'].create({
            'budget_id': budget.id,
            'account_id': self.test_expense.id,
            'planned_amount': 100000.0,
        })
        self.env['budget.budget.line'].create({
            'budget_id': budget.id,
            'account_id': self.test_revenue.id,
            'planned_amount': 200000.0,
        })
        copy = budget.copy()
        self.assertEqual(len(copy.line_ids), 2)
        # Verify the duplicated lines belong to the copy, not the source.
        for line in copy.line_ids:
            self.assertEqual(line.budget_id, copy)

    def test_bm001_scenario5_source_unchanged_after_copy(self):
        """Copying does not mutate the source budget."""
        budget = self._make_budget(name='Untouched Source')
        self.env['budget.budget.line'].create({
            'budget_id': budget.id,
            'account_id': self.test_expense.id,
            'planned_amount': 100000.0,
        })
        budget.action_confirm()
        original_state = budget.state
        original_name = budget.name
        original_line_count = len(budget.line_ids)
        budget.copy()
        # Source is unaffected.
        self.assertEqual(budget.state, original_state)
        self.assertEqual(budget.name, original_name)
        self.assertEqual(len(budget.line_ids), original_line_count)

    def test_bm001_scenario5_copy_with_explicit_name_honours_default(self):
        """When ``default={'name': ...}`` is passed, no (copy) suffix."""
        budget = self._make_budget(name='FY2024 Source')
        copy = budget.copy(default={'name': 'Explicit Name'})
        self.assertEqual(copy.name, 'Explicit Name')
        self.assertNotIn('(copy)', copy.name)

    # ------------------------------------------------------------------
    # Scenario 6 — Reference uniqueness + searchability
    # ------------------------------------------------------------------

    def test_bm001_scenario6_reference_is_unique_per_company(self):
        """``_unique_reference_per_company`` UNIQUE constraint fires."""
        budget1 = self._make_budget(name='A')
        # Attempt to force a duplicate reference on the same company.
        with self.assertRaises(Exception):  # noqa: BLE001 (psycopg2 IntegrityError wrap)
            with mute_logger('odoo.sql_db'):
                budget2 = self._make_budget(name='B')
                budget2.reference = budget1.reference
                # Flush so the UNIQUE constraint is enforced.
                budget2.flush_recordset()
                self.env.cr.flush()

    def test_bm001_scenario6_references_are_monotonically_unique(self):
        """Sequential budgets receive distinct references."""
        b1 = self._make_budget(name='Seq1')
        b2 = self._make_budget(name='Seq2')
        b3 = self._make_budget(name='Seq3')
        refs = {b1.reference, b2.reference, b3.reference}
        # All three must be distinct (and non-empty).
        self.assertEqual(len(refs), 3)

    def test_bm001_scenario6_search_by_name(self):
        """Searching budgets by ``name`` returns matching records."""
        b1 = self._make_budget(name='Q1 Marketing Budget')
        b2 = self._make_budget(name='Q2 Marketing Budget')
        self._make_budget(name='FY2025 Ops')  # control
        results = self.env['budget.budget'].search([
            ('name', 'ilike', 'marketing'),
        ])
        self.assertIn(b1, results)
        self.assertIn(b2, results)

    def test_bm001_scenario6_search_by_reference(self):
        """Searching by ``reference`` returns the matching record."""
        budget = self._make_budget(name='FindMe')
        results = self.env['budget.budget'].search([
            ('reference', '=', budget.reference),
        ])
        self.assertEqual(len(results), 1)
        self.assertEqual(results, budget)

    def test_bm001_scenario6_search_by_state(self):
        """Search for only ``draft`` budgets excludes confirmed ones."""
        draft = self._make_budget(name='Still Draft')
        confirmed = self._make_budget(name='Ready')
        self.env['budget.budget.line'].create({
            'budget_id': confirmed.id,
            'account_id': self.test_expense.id,
            'planned_amount': 1000.0,
        })
        confirmed.action_confirm()
        drafts = self.env['budget.budget'].search([
            ('state', '=', 'draft'),
            ('name', 'in', [draft.name, confirmed.name]),
        ])
        self.assertIn(draft, drafts)
        self.assertNotIn(confirmed, drafts)

    def test_bm001_scenario6_filter_active_records(self):
        """Active-only search excludes archived budgets."""
        budget = self._make_budget(name='Archivable')
        budget.action_archive()
        active = self.env['budget.budget'].search([
            ('active', '=', True),
            ('id', '=', budget.id),
        ])
        self.assertEqual(len(active), 0)
        # Search with archived context returns it.
        with_archived = self.env['budget.budget'].with_context(
            active_test=False,
        ).search([('id', '=', budget.id)])
        self.assertEqual(len(with_archived), 1)

    # ------------------------------------------------------------------
    # Computed totals + smart buttons
    # ------------------------------------------------------------------

    def test_bm001_total_planned_sums_line_planned_amounts(self):
        """``total_planned`` sums all line planned amounts."""
        budget = self._make_budget()
        self.env['budget.budget.line'].create({
            'budget_id': budget.id,
            'account_id': self.test_expense.id,
            'planned_amount': 100000.0,
        })
        self.env['budget.budget.line'].create({
            'budget_id': budget.id,
            'account_id': self.test_expense_marketing.id,
            'planned_amount': 50000.0,
        })
        self.assertAlmostEqual(budget.total_planned, 150000.0, places=2)
        self.assertEqual(
            float_compare(
                budget.total_planned, 150000.0, precision_digits=2,
            ),
            0,
        )

    def test_bm001_line_count_matches_line_ids_len(self):
        """``line_count`` reflects the number of attached lines."""
        budget = self._make_budget()
        self.assertEqual(budget.line_count, 0)
        self.env['budget.budget.line'].create({
            'budget_id': budget.id,
            'account_id': self.test_expense.id,
            'planned_amount': 1000.0,
        })
        self.env['budget.budget.line'].create({
            'budget_id': budget.id,
            'account_id': self.test_revenue.id,
            'planned_amount': 2000.0,
        })
        self.assertEqual(budget.line_count, 2)

    def test_bm001_action_open_lines_returns_act_window(self):
        """Smart button ``action_open_lines`` returns an act_window."""
        budget = self._make_budget()
        action = budget.action_open_lines()
        self.assertEqual(action['type'], 'ir.actions.act_window')
        self.assertEqual(action['res_model'], 'budget.budget.line')
        self.assertIn(('budget_id', '=', budget.id), action['domain'])
        self.assertEqual(
            action['context']['default_budget_id'],
            budget.id,
        )

    def test_bm001_action_open_alerts_returns_act_window(self):
        """Smart button ``action_open_alerts`` returns an act_window."""
        budget = self._make_budget()
        action = budget.action_open_alerts()
        self.assertEqual(action['type'], 'ir.actions.act_window')
        self.assertEqual(action['res_model'], 'budget.alert')
        self.assertIn(('budget_id', '=', budget.id), action['domain'])

    # ------------------------------------------------------------------
    # account.analytic.account extension (_inherit)
    # ------------------------------------------------------------------

    def test_bm001_analytic_budget_line_ids_with_distribution(self):
        """Analytic account exposes linked budget lines via distribution."""
        budget = self._make_budget()
        distribution = {str(self.analytic_sales.id): 100.0}
        line = self.env['budget.budget.line'].create({
            'budget_id': budget.id,
            'account_id': self.test_expense.id,
            'planned_amount': 100000.0,
            'analytic_distribution': distribution,
        })
        # Invalidate cache so the computed field re-runs from DB.
        self.analytic_sales.invalidate_recordset()
        self.assertIn(line, self.analytic_sales.budget_line_ids)

    def test_bm001_analytic_budget_line_count(self):
        """``budget_line_count`` reflects linked line count."""
        budget = self._make_budget()
        distribution = {str(self.analytic_marketing.id): 100.0}
        self.env['budget.budget.line'].create({
            'budget_id': budget.id,
            'account_id': self.test_expense.id,
            'planned_amount': 50000.0,
            'analytic_distribution': distribution,
        })
        self.analytic_marketing.invalidate_recordset()
        self.assertGreaterEqual(self.analytic_marketing.budget_line_count, 1)

    def test_bm001_analytic_budget_amount_planned_aggregation(self):
        """``budget_amount_planned`` aggregates weighted amounts."""
        budget = self._make_budget()
        # 100% to Sales
        self.env['budget.budget.line'].create({
            'budget_id': budget.id,
            'account_id': self.test_expense.id,
            'planned_amount': 100000.0,
            'analytic_distribution': {str(self.analytic_sales.id): 100.0},
        })
        self.analytic_sales.invalidate_recordset()
        # 100% of 100000 = 100000
        self.assertAlmostEqual(
            self.analytic_sales.budget_amount_planned,
            100000.0,
            places=2,
        )

    def test_bm001_analytic_budget_amount_weighted_distribution(self):
        """50/50 distribution yields 50% of planned on each analytic."""
        budget = self._make_budget()
        distribution = {
            str(self.analytic_sales.id): 50.0,
            str(self.analytic_marketing.id): 50.0,
        }
        self.env['budget.budget.line'].create({
            'budget_id': budget.id,
            'account_id': self.test_expense.id,
            'planned_amount': 200000.0,
            'analytic_distribution': distribution,
        })
        self.analytic_sales.invalidate_recordset()
        self.analytic_marketing.invalidate_recordset()
        # 50% of 200000 = 100000 on EACH analytic account.
        self.assertAlmostEqual(
            self.analytic_sales.budget_amount_planned,
            100000.0, places=2,
        )
        self.assertAlmostEqual(
            self.analytic_marketing.budget_amount_planned,
            100000.0, places=2,
        )

    def test_bm001_analytic_search_budget_line_ids_in_operator(self):
        """``_search_budget_line_ids`` supports the ``in`` operator."""
        budget = self._make_budget()
        line = self.env['budget.budget.line'].create({
            'budget_id': budget.id,
            'account_id': self.test_expense.id,
            'planned_amount': 10000.0,
            'analytic_distribution': {str(self.analytic_sales.id): 100.0},
        })
        # Search: "analytics whose budget_line_ids include this line"
        analytics = self.env['account.analytic.account'].search([
            ('budget_line_ids', 'in', [line.id]),
        ])
        self.assertIn(self.analytic_sales, analytics)

    def test_bm001_analytic_search_budget_line_ids_not_in_operator(self):
        """``_search_budget_line_ids`` supports the ``not in`` operator."""
        budget = self._make_budget()
        line = self.env['budget.budget.line'].create({
            'budget_id': budget.id,
            'account_id': self.test_expense.id,
            'planned_amount': 10000.0,
            'analytic_distribution': {str(self.analytic_sales.id): 100.0},
        })
        analytics = self.env['account.analytic.account'].search([
            ('budget_line_ids', 'not in', [line.id]),
            ('id', 'in', [
                self.analytic_sales.id, self.analytic_marketing.id,
            ]),
        ])
        # Marketing is NOT referenced by the line → included.
        self.assertIn(self.analytic_marketing, analytics)
        self.assertNotIn(self.analytic_sales, analytics)

    def test_bm001_analytic_action_open_budget_lines_returns_act_window(self):
        """Smart button returns an ``ir.actions.act_window``."""
        budget = self._make_budget()
        self.env['budget.budget.line'].create({
            'budget_id': budget.id,
            'account_id': self.test_expense.id,
            'planned_amount': 10000.0,
            'analytic_distribution': {str(self.analytic_sales.id): 100.0},
        })
        self.analytic_sales.invalidate_recordset()
        action = self.analytic_sales.action_open_budget_lines()
        self.assertEqual(action['type'], 'ir.actions.act_window')
        self.assertEqual(action['res_model'], 'budget.budget.line')
        # Context preserves the default_company_id for consistency.
        self.assertIn('default_company_id', action['context'])

    def test_bm001_analytic_budget_amount_actual_with_posted_entry(self):
        """``budget_amount_actual`` aggregates posted move line balance."""
        budget = self._make_budget()
        distribution = {str(self.analytic_sales.id): 100.0}
        self.env['budget.budget.line'].create({
            'budget_id': budget.id,
            'account_id': self.test_expense.id,
            'planned_amount': 100000.0,
            'analytic_distribution': distribution,
        })
        # Post 40,000 against the same account with the same distribution
        self._post_entry(
            self.test_expense, 40000.0, date(2024, 6, 15),
            analytic_distribution=distribution,
        )
        self.analytic_sales.invalidate_recordset()
        # budget_amount_actual is balance (positive debit on expense).
        self.assertAlmostEqual(
            self.analytic_sales.budget_amount_actual,
            40000.0,
            places=2,
        )

    def test_bm001_analytic_budget_consumption_percent(self):
        """``budget_consumption_percent`` = actual / planned * 100."""
        budget = self._make_budget()
        distribution = {str(self.analytic_sales.id): 100.0}
        self.env['budget.budget.line'].create({
            'budget_id': budget.id,
            'account_id': self.test_expense.id,
            'planned_amount': 100000.0,
            'analytic_distribution': distribution,
        })
        self._post_entry(
            self.test_expense, 25000.0, date(2024, 3, 10),
            analytic_distribution=distribution,
        )
        self.analytic_sales.invalidate_recordset()
        # 25000 / 100000 * 100 = 25.0
        self.assertAlmostEqual(
            self.analytic_sales.budget_consumption_percent,
            25.0,
            places=2,
        )

    # ------------------------------------------------------------------
    # Chatter + tracking (mail.thread inheritance)
    # ------------------------------------------------------------------

    def test_bm001_action_confirm_posts_chatter_message(self):
        """``action_confirm`` posts a chatter note for the audit trail."""
        budget = self._make_budget()
        self.env['budget.budget.line'].create({
            'budget_id': budget.id,
            'account_id': self.test_expense.id,
            'planned_amount': 100000.0,
        })
        before = len(budget.message_ids)
        budget.action_confirm()
        after = len(budget.message_ids)
        # action_confirm posts a note -> message_ids grows by at least 1.
        self.assertGreater(after, before)
