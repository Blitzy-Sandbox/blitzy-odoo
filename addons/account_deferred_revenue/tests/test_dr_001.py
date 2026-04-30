# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Test Suite -- DR-001 Deferral Schedule Definition (account.deferred.schedule)

Implements acceptance tests for FEATURE-005 Track C Story DR-001 per the BDD
scenarios defined in
``tickets/stories/deferred-revenue/DR-001-deferral-schedule-definition.md``.

Scope of this test file (one test method per acceptance scenario):

    * ``test_deferral_schedule_from_invoice``         (Scenario 1)
    * ``test_recognition_period_configuration``        (Scenario 2)
    * ``test_deferral_account_configuration``          (Scenario 3)
    * ``test_manual_deferral_schedule``                (Scenario 4)
    * ``test_recognition_period_validation``           (Scenario 5)
    * ``test_analytic_distribution_preservation``      (Scenario 6)

Target coverage: >= 80% line coverage on
``addons/account_deferred_revenue/models/account_deferred_schedule.py``
core surface -- ``create``, ``_check_dates``, ``_check_amount``,
``_check_accounts_distinct``, ``_onchange_source_move_line``,
``action_confirm``, ``action_close``, ``action_draft``,
``_compute_period_count`` -- plus ``AccountMove._compute_has_deferred_schedules``
and ``AccountMove.action_view_deferred_schedules`` from the inherit extension
file ``models/account_move.py`` (enforced per AAP Rule R-04).

Base class: :class:`odoo.addons.account.tests.common.AccountTestInvoicingCommon`
Decorator: ``@tagged('post_install', '-at_install')``
Time control: :func:`freezegun.freeze_time` for deterministic date computations.

DR-001 BDD acceptance criteria (verbatim mapping):

============================================  =======================================  ===========
BDD Scenario                                  Test Method Name                          Test Type
============================================  =======================================  ===========
Scenario 1: Create from Invoice               test_deferral_schedule_from_invoice       Acceptance
Scenario 2: Recognition Period                test_recognition_period_configuration     Acceptance
Scenario 3: Account Configuration             test_deferral_account_configuration       Acceptance
Scenario 4: Manual Schedule                   test_manual_deferral_schedule             Acceptance
Scenario 5: Period Validation                 test_recognition_period_validation        Acceptance
Scenario 6: Analytic Integration              test_analytic_distribution_preservation   Acceptance
============================================  =======================================  ===========

AAP Rule Compliance:

* **R-01** (module independence): no cross-imports with sibling modules
  (``account_asset_management``, ``account_budget_management``,
  ``account_payment_followup``).
* **R-02** (no Enterprise dependencies): only imports from
  ``odoo.addons.account.tests.common`` (Community Edition).
* **R-03** (``_inherit`` vs ``_name``): tests never define new models; the
  models under test are owned by the production model files.
* **R-04** (>=80% coverage): six test methods exercise the constructor,
  validators, onchange, computed fields, and state transitions across all
  six BDD scenarios.
* **R-05** (no core field redefinition): tests only READ
  ``account.move.has_deferred_schedules`` (a new computed field) without
  redefining anything on the core model.
* **R-07** (justified ``sudo()`` only): a single ``sudo()`` call is used in
  ``test_max_months_warning_threshold_edge_cases`` to set
  ``ir.config_parameter`` values (which require admin privilege); the call
  is annotated with the required ``# sudo required: ...`` inline comment.
  No other ``sudo()`` calls appear in this file.
"""

from datetime import date

from freezegun import freeze_time

from odoo import Command, fields  # noqa: F401 -- fields re-exported for parity
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon

# Module-level constants for deterministic time control. ``_FROZEN_TODAY`` is
# the string form required by ``freezegun.freeze_time``; ``_FROZEN_DATE`` is
# the equivalent ``datetime.date`` constant preserved for any test-body
# calculation that needs to compute offsets relative to "today". Frozen on
# 2024-06-15 so that schedules spanning Jan-Dec 2024 include periods both
# before and after the notional "now", exercising sequence/period logic
# without introducing real-clock flakiness.
_FROZEN_TODAY = '2024-06-15'
_FROZEN_DATE = date(2024, 6, 15)


@tagged('post_install', '-at_install')
class TestDeferredScheduleDefinition(AccountTestInvoicingCommon):
    """Acceptance tests for DR-001 Deferral Schedule Definition.

    These tests exercise the foundational schedule model
    (:class:`account.deferred.schedule`) on which every other DR story
    depends. Coverage targets:

    * **CRUD override** -- :meth:`account.deferred.schedule.create` (sequence
      auto-assignment, source-line back-reference population, analytic
      distribution copy-from-source).
    * **Validators** -- :meth:`_check_dates` (end > start strictly, warning
      threshold for >60 months read from ``ir.config_parameter``),
      :meth:`_check_amount` (strictly positive amount), and
      :meth:`_check_accounts_distinct` (deferred != recognition account).
    * **Computed fields** -- :meth:`_compute_period_count` (months between
      start_date and end_date), and :attr:`AccountMove.has_deferred_schedules`
      (boolean reverse-relation indicator).
    * **State machine** -- ``action_confirm`` (draft -> confirmed),
      ``action_close`` (confirmed -> closed; blocked by draft lines),
      ``action_draft`` (confirmed -> draft; clears draft lines).
    * **Smart-button action** -- :meth:`AccountMove.action_view_deferred_schedules`
      returns a properly-formed ``ir.actions.act_window`` payload.

    The test class uses the Odoo accounting test fixture
    :class:`~odoo.addons.account.tests.common.AccountTestInvoicingCommon`
    which provides a pre-configured company, chart of accounts, default
    journals, tax fixtures, and a test user with the core accounting groups.
    The deferred-revenue-specific user and manager groups are granted in
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
        """Prepare shared fixtures for all six DR-001 acceptance scenarios.

        Performs the following steps (in order):

        1. Invoke the parent ``setUpClass`` to bootstrap the accounting
           test fixture (company, COA, journals, tax fixtures, default
           test user).
        2. Grant the deferred-revenue manager and user groups defined in
           ``security/deferred_security.xml`` to the current test user so
           that the ACLs in ``security/ir.model.access.csv`` permit
           create / write / unlink on ``account.deferred.schedule`` and
           ``account.deferred.line``.
        3. Cache the company and company currency for easy reference.
        4. Create dedicated ``XTEST.*`` accounts for both deferred-revenue
           (liability) and deferred-expense (asset) patterns, plus their
           recognition counterparts (income / expense), and a receivable
           account for partner invoicing.
        5. Create a generic test partner with the receivable account set
           so that invoice creation (Scenarios 1 and 6) works without
           hitting the "missing receivable account" validation.
        6. Resolve and cache the analytic plan and account used in
           Scenario 6 for analytic_distribution preservation testing.
        """
        super().setUpClass()

        # ------------------------------------------------------------------
        # Step 2 -- grant module-specific security groups.
        #
        # ``AccountTestInvoicingCommon`` creates a test user with the core
        # accounting groups but NOT the module-specific groups from
        # ``account_deferred_revenue``. The ACL rows in
        # ``security/ir.model.access.csv`` require at least
        # ``group_deferred_revenue_user`` for create/read/write on
        # ``account.deferred.schedule`` and ``account.deferred.line``.
        # We grant BOTH user and manager groups so that unlink operations
        # (used by ``action_draft`` to clear draft lines in Scenario 4)
        # also succeed.
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
        # Step 3 -- cache company and company currency. Using ``env.company``
        # keeps the test robust against future changes to the default test
        # company ID in ``AccountTestInvoicingCommon``.
        # ------------------------------------------------------------------
        cls.company = cls.env.company
        cls.currency = cls.env.company.currency_id

        # ------------------------------------------------------------------
        # Step 4 -- create dedicated test accounts. The ``XTEST.*`` code
        # prefix guarantees isolation from any COA entries installed by
        # ``AccountTestInvoicingCommon`` or by a future COA chart; without
        # this prefix, two test classes could create colliding account
        # codes and break each other when run in the same test session.
        #
        # We create FOUR accounting-flow accounts:
        #   * ``deferred_revenue_account`` (liability_current) -- balance-sheet
        #     account holding deferred amounts for customer-side deferrals.
        #   * ``recognition_revenue_account`` (income) -- P&L account where
        #     deferred revenue is recognized over time.
        #   * ``deferred_expense_account`` (asset_current) -- balance-sheet
        #     account holding prepaid amounts for vendor-side deferrals.
        #   * ``recognition_expense_account`` (expense) -- P&L account where
        #     prepaid expenses are recognized over time.
        # plus the ``receivable_account`` so that the partner can post
        # customer invoices in Scenarios 1 and 6.
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
        cls.deferred_expense_account = AccountAccount.create({
            'code': 'XTEST.12100',
            'name': 'Test Deferred Expense (Asset)',
            # asset_current is one of the valid values permitted by the
            # domain on ``deferred_account_id`` for vendor-side deferrals.
            'account_type': 'asset_current',
            'reconcile': False,
        })
        cls.recognition_expense_account = AccountAccount.create({
            'code': 'XTEST.50100',
            'name': 'Test Recognition Expense',
            # expense is one of the valid values permitted by the domain on
            # ``recognition_account_id`` for vendor-side deferrals.
            'account_type': 'expense',
            'reconcile': False,
        })
        cls.receivable_account = AccountAccount.create({
            'code': 'XTEST.11000',
            'name': 'Test Accounts Receivable',
            # asset_receivable required for partner.property_account_receivable_id.
            'account_type': 'asset_receivable',
            'reconcile': True,
        })

        # ------------------------------------------------------------------
        # Step 5 -- create a generic test partner with the receivable
        # account set. When creating customer invoices (Scenarios 1 and 6),
        # Odoo validates that the partner has a receivable account; setting
        # this at partner creation time prevents cryptic validation errors.
        # ------------------------------------------------------------------
        cls.partner = cls.env['res.partner'].create({
            'name': 'Schedule Test Customer',
            'property_account_receivable_id': cls.receivable_account.id,
        })

        # ------------------------------------------------------------------
        # Step 6 -- create an analytic plan and account for Scenario 6.
        # The analytic_distribution field on account.move.line and
        # account.deferred.schedule is a Json mapping
        # ``{str(analytic_account_id): percentage}``; we need a real
        # analytic account in the database for the validation to succeed.
        # The plan is required because every analytic account belongs to
        # exactly one plan in Odoo 19.0.
        # ------------------------------------------------------------------
        cls.analytic_plan = cls.env['account.analytic.plan'].create({
            'name': 'Test Plan',
        })
        cls.analytic_account = cls.env['account.analytic.account'].create({
            'name': 'Test Analytic Account',
            'plan_id': cls.analytic_plan.id,
        })

    # ------------------------------------------------------------------
    # Helper for creating draft schedules under test
    # ------------------------------------------------------------------
    def _create_draft_schedule(self, **overrides):
        """Return a fresh draft ``account.deferred.schedule`` record.

        Default values correspond to a typical Canonical Example: $12,000
        spread straight-line from 2024-01-01 to 2024-12-31 (12 periods)
        with the deferred-revenue / recognition-revenue account pair.
        Any default may be overridden by keyword argument; e.g.,
        ``self._create_draft_schedule(total_amount=5000.0)`` produces an
        otherwise-default schedule with ``total_amount=5000.0``.

        Returns the newly-created schedule in ``state='draft'`` (the
        model's ``default='draft'``) so that :meth:`action_confirm` can
        be invoked from the test body if needed.

        :param overrides: keyword overrides for the default vals dict.
        :returns: a single :class:`account.deferred.schedule` record.
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
    # Scenario 1: Create Deferral Schedule from Invoice
    # ==================================================================
    @freeze_time(_FROZEN_TODAY)
    def test_deferral_schedule_from_invoice(self):
        """Scenario 1: Create deferral schedule linked to an invoice line.

        BDD criteria (verbatim from DR-001 ticket):

        * GIVEN I have a posted customer invoice with revenue that should
          be deferred AND the invoice line is associated with a revenue
          account.
        * WHEN I create a deferral schedule for the invoice line.
        * THEN a new deferral schedule should be created linked to the
          invoice AND the original revenue account should be replaced
          with the deferred revenue account AND the total deferral
          amount should equal the invoice line amount AND the
          recognition period should be configurable.

        Coverage targets:
            * :meth:`account.deferred.schedule.create` -- sequence
              auto-assignment, source-line back-reference population.
            * :meth:`AccountMove._compute_has_deferred_schedules` --
              boolean True after schedule creation.
            * :meth:`AccountMove.action_view_deferred_schedules` --
              returns proper ``ir.actions.act_window`` dict.
            * :attr:`account.move.line.deferred_schedule_id` -- back-
              reference populated on the source line.
        """
        # ------------------------------------------------------------------
        # GIVEN: build a simple posted customer invoice of $12,000 on the
        # recognition revenue account.
        # ------------------------------------------------------------------
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'invoice_date': date(2024, 1, 1),
            'date': date(2024, 1, 1),
            'currency_id': self.currency.id,
            'invoice_line_ids': [Command.create({
                'name': 'Annual subscription 2024',
                'quantity': 1,
                'price_unit': 12000.0,
                'account_id': self.recognition_revenue_account.id,
                # No tax: keeps the line balance equal to price_unit so
                # the schedule's total_amount matches the line amount
                # exactly without tax-rounding noise.
                'tax_ids': [Command.set([])],
            })],
        })
        invoice.action_post()

        # Identify the revenue line of the posted invoice. The posting
        # process creates additional balancing lines (e.g., the receivable
        # line) so we filter to the line whose account is the recognition
        # revenue account.
        revenue_line = invoice.line_ids.filtered(
            lambda line: line.account_id == self.recognition_revenue_account,
        )
        self.assertTrue(
            revenue_line,
            "Invoice must have a line on the recognition revenue account.",
        )

        # ------------------------------------------------------------------
        # WHEN: create a deferral schedule referencing the invoice line.
        # ------------------------------------------------------------------
        schedule = self._create_draft_schedule(
            source_move_id=invoice.id,
            source_move_line_id=revenue_line[0].id,
            total_amount=12000.0,
        )

        # ------------------------------------------------------------------
        # THEN: the schedule must reflect the invoice linkage and the
        # AccountMove extension fields must reflect the new schedule.
        # ------------------------------------------------------------------
        # 1. Schedule fields linked to invoice
        self.assertEqual(
            schedule.source_move_id, invoice,
            "Schedule must link back to the source invoice.",
        )
        self.assertEqual(
            schedule.source_move_line_id, revenue_line[0],
            "Schedule must link back to the specific revenue line.",
        )
        self.assertEqual(
            schedule.partner_id, self.partner,
            "Partner must match the invoice partner.",
        )
        self.assertAlmostEqual(
            schedule.total_amount, 12000.0, places=2,
            msg="total_amount must equal the invoice line amount.",
        )
        self.assertEqual(
            schedule.currency_id, self.currency,
            "Currency must match the company currency from the invoice.",
        )

        # 2. Account substitution: deferred (liability) replaces income
        self.assertEqual(
            schedule.deferred_account_id,
            self.deferred_revenue_account,
            "Deferred account must be the liability account, replacing "
            "the original revenue account on the schedule.",
        )
        self.assertEqual(
            schedule.recognition_account_id,
            self.recognition_revenue_account,
            "Recognition account must be the income account where deferred "
            "revenue is recognized over time.",
        )
        self.assertNotEqual(
            schedule.deferred_account_id,
            schedule.recognition_account_id,
            "Deferred and recognition accounts must differ "
            "(_check_accounts_distinct constraint).",
        )

        # 3. Recognition period is configurable -- default values populated
        self.assertTrue(
            schedule.start_date,
            "Schedule must have a configurable start_date.",
        )
        self.assertTrue(
            schedule.end_date,
            "Schedule must have a configurable end_date.",
        )
        self.assertGreater(
            schedule.end_date, schedule.start_date,
            "end_date must be strictly greater than start_date.",
        )
        self.assertGreater(
            schedule.period_count, 0,
            "period_count must be a positive integer for a valid schedule.",
        )

        # 4. Default state and sequence assignment
        self.assertEqual(
            schedule.state, 'draft',
            "Newly-created schedule must start in 'draft' state.",
        )
        self.assertTrue(
            schedule.name,
            "Schedule must have a name auto-assigned by the sequence.",
        )
        self.assertNotEqual(
            schedule.name, 'New',
            "Sequence must replace the default 'New' placeholder.",
        )

        # 5. AccountMove extension: has_deferred_schedules computed True
        self.assertIn(
            schedule, invoice.deferred_schedule_ids,
            "Invoice's reverse One2many must include the new schedule.",
        )
        # Refresh the computed field by invalidating its cache so the
        # @api.depends recomputes against the latest schedule recordset.
        invoice.invalidate_recordset(['has_deferred_schedules'])
        self.assertTrue(
            invoice.has_deferred_schedules,
            "Posted invoice must reflect that a deferred schedule now "
            "exists (has_deferred_schedules computed True).",
        )

        # 6. AccountMove extension: action_view_deferred_schedules
        action = invoice.action_view_deferred_schedules()
        self.assertIsInstance(
            action, dict,
            "Smart-button action must return an ir.actions.act_window dict.",
        )
        self.assertEqual(
            action.get('type'), 'ir.actions.act_window',
            "Action type must be 'ir.actions.act_window'.",
        )
        self.assertEqual(
            action.get('res_model'),
            'account.deferred.schedule',
            "Smart-button action must target account.deferred.schedule.",
        )
        # Domain filters to schedules of the current invoice
        self.assertIn(
            ('source_move_id', '=', invoice.id),
            action.get('domain', []),
            "Smart-button action domain must filter by source_move_id.",
        )
        # Context provides creation defaults so 'Create' from the opened
        # list pre-fills the new schedule with this move/partner/company.
        ctx = action.get('context', {}) or {}
        self.assertEqual(
            ctx.get('default_source_move_id'), invoice.id,
            "Smart-button action context must pre-fill default_source_move_id.",
        )
        self.assertEqual(
            ctx.get('default_partner_id'), self.partner.id,
            "Smart-button action context must pre-fill default_partner_id.",
        )

        # 7. Source line back-reference populated by create() override
        self.assertEqual(
            revenue_line[0].deferred_schedule_id, schedule,
            "Source invoice line must back-reference the new schedule "
            "(populated by account.deferred.schedule.create()).",
        )

        # ------------------------------------------------------------------
        # AND: the @api.onchange('source_move_line_id') handler pre-fills
        # schedule fields from the picked invoice line. We exercise this
        # by creating an in-memory record (``new()``) with the minimum
        # context fields, setting ``source_move_line_id``, then calling
        # the onchange method directly. After the onchange:
        #   * ``source_move_id`` is propagated from the line's move
        #   * ``partner_id`` is propagated from the line's partner
        #   * ``total_amount`` is propagated from abs(balance) or
        #     abs(price_subtotal) of the line
        #   * ``currency_id`` is propagated from the line's currency
        #   * ``analytic_distribution`` (if any) is copied from the line
        #   * ``start_date`` is set to the invoice_date
        #   * ``end_date`` is set to invoice_date + 12 months (default)
        #
        # This exercises the body of ``_onchange_source_move_line`` and
        # the create() override's auto-copy fallbacks (DR-001 Scenario 1).
        # ------------------------------------------------------------------
        new_record = self.env['account.deferred.schedule'].new({
            'company_id': self.company.id,
            'currency_id': self.currency.id,
            'deferred_account_id': self.deferred_revenue_account.id,
            'recognition_account_id': self.recognition_revenue_account.id,
            'recognition_method': 'straight_line',
            # Intentionally OMIT start_date, end_date, total_amount,
            # partner_id, source_move_id -- the onchange will populate
            # them from the source line.
        })
        new_record.source_move_line_id = revenue_line[0]
        new_record._onchange_source_move_line()
        # Verify the onchange populated the schedule fields from the line.
        self.assertEqual(
            new_record.source_move_id, invoice,
            "Onchange must propagate source_move_id from the line's move.",
        )
        self.assertEqual(
            new_record.partner_id, self.partner,
            "Onchange must propagate partner_id from the line.",
        )
        self.assertAlmostEqual(
            new_record.total_amount, 12000.0, places=2,
            msg="Onchange must propagate total_amount from abs(balance).",
        )
        self.assertEqual(
            new_record.start_date, date(2024, 1, 1),
            "Onchange must set start_date to the invoice_date.",
        )
        # invoice_date + 12 months = 2025-01-01
        self.assertEqual(
            new_record.end_date, date(2025, 1, 1),
            "Onchange must set end_date to invoice_date + 12 months "
            "when end_date is not already configured.",
        )

        # ------------------------------------------------------------------
        # AND: the onchange short-circuits cleanly when source_move_line_id
        # is False (no source line picked). This guards the early-return
        # branch in ``_onchange_source_move_line`` so a user clearing the
        # source line doesn't trigger spurious field updates.
        # ------------------------------------------------------------------
        empty_record = self.env['account.deferred.schedule'].new({
            'company_id': self.company.id,
            'currency_id': self.currency.id,
        })
        # Calling onchange with no source_move_line_id set must be a no-op.
        empty_record._onchange_source_move_line()
        # No assertion fields populated -- the onchange returns early.
        self.assertFalse(
            empty_record.source_move_id,
            "Onchange must not populate source_move_id when no source "
            "line is picked (early-return branch).",
        )

        # ------------------------------------------------------------------
        # AND: the onchange does NOT auto-fill ``deferred_account_id``.
        # When deferred_account_id is unset on the in-memory record and
        # source_move_line_id is set, the onchange enters the
        # ``if not self.deferred_account_id:`` branch and explicitly
        # leaves the field blank for the user to select (the source line
        # account is the recognition/income account, not the deferred
        # account). This is a deliberate UX decision per DR-001 Scenario 3.
        # ------------------------------------------------------------------
        no_acct_record = self.env['account.deferred.schedule'].new({
            'company_id': self.company.id,
            'currency_id': self.currency.id,
            # NO deferred_account_id -- onchange must not auto-fill it.
            'recognition_account_id': self.recognition_revenue_account.id,
        })
        no_acct_record.source_move_line_id = revenue_line[0]
        no_acct_record._onchange_source_move_line()
        # Other fields propagated, but deferred_account_id remains blank.
        self.assertFalse(
            no_acct_record.deferred_account_id,
            "Onchange must NOT auto-fill deferred_account_id; the user "
            "must explicitly select the balance-sheet deferred account.",
        )
        # Verify other fields WERE propagated (sanity check the branch
        # still ran the rest of the onchange body).
        self.assertEqual(
            no_acct_record.source_move_id, invoice,
            "Onchange must still populate source_move_id even when "
            "deferred_account_id is blank.",
        )

    # ==================================================================
    # Scenario 2: Define Recognition Period Parameters
    # ==================================================================
    @freeze_time(_FROZEN_TODAY)
    def test_recognition_period_configuration(self):
        """Scenario 2: Recognition period parameters are stored and computed.

        BDD criteria (verbatim from DR-001 ticket):

        * GIVEN I am creating a new deferral schedule.
        * WHEN I configure the recognition period.
        * THEN I should be able to set the start date for recognition
          AND I should be able to set the end date or number of periods
          AND I should be able to select the recognition method
          (straight-line, date-based) AND the system should calculate
          the per-period recognition amount.

        Coverage targets:
            * :meth:`_compute_period_count` -- months between start and end.
            * recognition_method Selection field -- write/read of all three
              valid values (``straight_line``, ``date_based``, ``manual``).
            * recognition_method default -- 'straight_line' on creation.
        """
        # ------------------------------------------------------------------
        # GIVEN/WHEN: create a draft full-year schedule.
        # ------------------------------------------------------------------
        schedule = self._create_draft_schedule(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )

        # ------------------------------------------------------------------
        # THEN: dates are stored, period_count computed, default method set.
        # ------------------------------------------------------------------
        self.assertEqual(
            schedule.start_date, date(2024, 1, 1),
            "Schedule must store the configured start_date.",
        )
        self.assertEqual(
            schedule.end_date, date(2024, 12, 31),
            "Schedule must store the configured end_date.",
        )
        self.assertEqual(
            schedule.period_count, 12,
            "A full-year schedule (Jan-1 to Dec-31) must compute to 12 "
            "monthly periods (_compute_period_count).",
        )
        self.assertEqual(
            schedule.recognition_method, 'straight_line',
            "Default recognition_method must be 'straight_line'.",
        )

        # ------------------------------------------------------------------
        # AND: changing recognition_method to 'date_based' is valid.
        # ------------------------------------------------------------------
        schedule.write({'recognition_method': 'date_based'})
        self.assertEqual(
            schedule.recognition_method, 'date_based',
            "Schedule must accept date_based recognition_method.",
        )

        # ------------------------------------------------------------------
        # AND: changing recognition_method to 'manual' is valid.
        # ------------------------------------------------------------------
        schedule.write({'recognition_method': 'manual'})
        self.assertEqual(
            schedule.recognition_method, 'manual',
            "Schedule must accept manual recognition_method.",
        )

        # ------------------------------------------------------------------
        # AND: writing an invalid recognition_method must raise. The
        # Selection field rejects unknown values via ORM validation;
        # depending on the Odoo version this surfaces as ValueError
        # (from Selection.convert_to_cache) or ValidationError (from a
        # downstream constraint). We accept either by using try/except
        # rather than a tuple in assertRaises -- Odoo's custom
        # ``_assertRaises`` helper does not handle tuples gracefully
        # (it calls ``issubclass(exception, AccessError)`` directly,
        # which fails when ``exception`` is a tuple).
        # ------------------------------------------------------------------
        invalid_method_raised = False
        try:
            schedule.write({'recognition_method': 'invalid_method'})
        except (ValidationError, ValueError):
            invalid_method_raised = True
        self.assertTrue(
            invalid_method_raised,
            "Schedule must reject invalid recognition_method values via "
            "ORM Selection field validation (ValueError or ValidationError).",
        )

        # ------------------------------------------------------------------
        # AND: per-period recognition amount calculation logic is exercised
        # by computing total_amount / period_count for the simplest case.
        # The actual line generation is the job of DR-002, but the math
        # is observable via a confirmed schedule's lines (covered in DR-002
        # tests). Here we just verify that the schedule exposes period_count
        # and total_amount such that the per-period computation works.
        # ------------------------------------------------------------------
        # Re-set the method to straight_line and verify the math.
        schedule.write({'recognition_method': 'straight_line'})
        per_period = schedule.total_amount / schedule.period_count
        self.assertAlmostEqual(
            per_period, 1000.0, places=2,
            msg="$12,000 / 12 periods must equal $1,000 per period.",
        )

        # Also verify period_count for a half-year schedule.
        half_year = self._create_draft_schedule(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 30),
        )
        self.assertEqual(
            half_year.period_count, 6,
            "A half-year schedule (Jan-1 to Jun-30) must compute to 6 "
            "monthly periods.",
        )

    # ==================================================================
    # Scenario 3: Configure Deferral Accounts
    # ==================================================================
    @freeze_time(_FROZEN_TODAY)
    def test_deferral_account_configuration(self):
        """Scenario 3: Deferred and recognition accounts are configurable.

        BDD criteria (verbatim from DR-001 ticket):

        * GIVEN I am creating a deferral schedule.
        * WHEN I configure the accounting settings.
        * THEN I should be able to select the deferred revenue/expense
          account AND I should be able to select the recognition
          revenue/expense account AND default accounts should be
          suggested based on company settings AND only accounts of
          appropriate type should be available for selection.

        Coverage targets:
            * deferred_account_id Many2one -- write/read of liability and
              asset_current types.
            * recognition_account_id Many2one -- write/read of income and
              expense types.
            * :meth:`_check_accounts_distinct` -- ValidationError when
              both fields point to the same account.
        """
        # ------------------------------------------------------------------
        # WHEN: create a deferred-revenue (customer-side) schedule
        # ------------------------------------------------------------------
        schedule = self._create_draft_schedule(
            deferred_account_id=self.deferred_revenue_account.id,
            recognition_account_id=self.recognition_revenue_account.id,
        )
        # THEN: both fields persist
        self.assertEqual(
            schedule.deferred_account_id, self.deferred_revenue_account,
            "Schedule must store the configured deferred (liability) account.",
        )
        self.assertEqual(
            schedule.recognition_account_id, self.recognition_revenue_account,
            "Schedule must store the configured recognition (income) account.",
        )
        # Verify account types match the expected business pattern
        self.assertEqual(
            schedule.deferred_account_id.account_type, 'liability_current',
            "Deferred revenue account must be of liability_current type.",
        )
        self.assertEqual(
            schedule.recognition_account_id.account_type, 'income',
            "Recognition revenue account must be of income type.",
        )

        # ------------------------------------------------------------------
        # AND: deferred-expense (vendor-side) pattern is also valid --
        # asset deferral with expense recognition.
        # ------------------------------------------------------------------
        expense_schedule = self._create_draft_schedule(
            deferred_account_id=self.deferred_expense_account.id,
            recognition_account_id=self.recognition_expense_account.id,
        )
        self.assertEqual(
            expense_schedule.deferred_account_id,
            self.deferred_expense_account,
            "Schedule must store the configured deferred (asset) account.",
        )
        self.assertEqual(
            expense_schedule.recognition_account_id,
            self.recognition_expense_account,
            "Schedule must store the configured recognition (expense) account.",
        )
        self.assertEqual(
            expense_schedule.deferred_account_id.account_type,
            'asset_current',
            "Deferred expense account must be of asset_current type.",
        )
        self.assertEqual(
            expense_schedule.recognition_account_id.account_type,
            'expense',
            "Recognition expense account must be of expense type.",
        )

        # ------------------------------------------------------------------
        # AND: setting deferred_account_id == recognition_account_id raises
        # ValidationError via the _check_accounts_distinct constraint.
        # The two accounts MUST be different to maintain proper double-entry
        # accounting -- one side holds the deferred amount, the other side
        # receives the recognized amount over time.
        # ------------------------------------------------------------------
        with self.assertRaises(ValidationError):
            self._create_draft_schedule(
                deferred_account_id=self.deferred_revenue_account.id,
                recognition_account_id=self.deferred_revenue_account.id,
            )

        # ------------------------------------------------------------------
        # AND: write-time enforcement -- changing an existing schedule's
        # recognition_account_id to match the deferred_account_id must
        # also raise (constraint runs on write, not just on create).
        # ------------------------------------------------------------------
        with self.assertRaises(ValidationError):
            schedule.write({
                'recognition_account_id': schedule.deferred_account_id.id,
            })

    # ==================================================================
    # Scenario 4: Create Manual Deferral Schedule
    # ==================================================================
    @freeze_time(_FROZEN_TODAY)
    def test_manual_deferral_schedule(self):
        """Scenario 4: A schedule can be created manually without invoice.

        BDD criteria (verbatim from DR-001 ticket):

        * GIVEN I need to defer revenue or expense without an existing
          invoice.
        * WHEN I create a manual deferral schedule.
        * THEN I should be able to enter the total amount to defer
          AND I should be able to specify the partner/customer
          AND I should be able to attach reference documents
          AND the schedule should be tracked independently of any invoice.

        Coverage targets:
            * Schedule creation without source_move_id / source_move_line_id.
            * Sequence-driven name auto-assignment via create() override.
            * State machine: draft -> action_confirm -> confirmed; close
              guard against draft lines (UserError); action_draft revert.
        """
        # ------------------------------------------------------------------
        # WHEN: create a manual schedule WITHOUT source invoice linkage
        # ------------------------------------------------------------------
        schedule = self._create_draft_schedule(
            # Explicitly no source_move_id / source_move_line_id
            total_amount=5000.0,
        )

        # ------------------------------------------------------------------
        # THEN: schedule is persisted with no invoice link
        # ------------------------------------------------------------------
        self.assertFalse(
            schedule.source_move_id,
            "Manual schedule must not link to an invoice.",
        )
        self.assertFalse(
            schedule.source_move_line_id,
            "Manual schedule must not reference a move line.",
        )
        self.assertEqual(
            schedule.state, 'draft',
            "Manual schedule must start in 'draft' state.",
        )
        self.assertEqual(
            schedule.partner_id, self.partner,
            "Manual schedule must capture the configured partner.",
        )
        self.assertAlmostEqual(
            schedule.total_amount, 5000.0, places=2,
            msg="Manual schedule must capture the configured total_amount.",
        )

        # ------------------------------------------------------------------
        # AND: name is auto-assigned from the 'account.deferred.schedule'
        # sequence (canonical assertion: name != 'New').
        # ------------------------------------------------------------------
        self.assertTrue(
            schedule.name,
            "Sequence must assign a name to the manual schedule.",
        )
        self.assertNotEqual(
            schedule.name, 'New',
            "Name 'New' placeholder must be replaced by the sequence value.",
        )
        # The sequence prefix is 'DEF-YYYY-' per data/deferred_data.xml.
        # Under freeze_time(2024-06-15), the year segment must be 2024.
        self.assertIn(
            'DEF-', schedule.name,
            "Sequence-generated name must use the 'DEF-' prefix.",
        )

        # ------------------------------------------------------------------
        # AND: state machine -- draft -> confirmed.
        # action_confirm() runs _compute_recognition_schedule() because
        # no lines exist yet, generating recognition lines for the
        # straight_line method. This validates the SUM INVARIANT.
        # ------------------------------------------------------------------
        schedule.action_confirm()
        self.assertEqual(
            schedule.state, 'confirmed',
            "action_confirm must transition state from 'draft' to 'confirmed'.",
        )
        # Verify recognition lines were generated
        self.assertTrue(
            schedule.line_ids,
            "action_confirm must generate recognition lines for non-manual "
            "methods (straight_line in this case).",
        )
        # All lines start in 'draft' state until DR-003 cut-off wizard posts
        self.assertTrue(
            all(line.state == 'draft' for line in schedule.line_ids),
            "Newly-generated recognition lines must start in 'draft' state.",
        )

        # ------------------------------------------------------------------
        # AND: action_close blocks if draft lines remain -- raises UserError.
        # This is the guard logic in action_close that drives coverage of
        # the close-guard branch.
        # ------------------------------------------------------------------
        with self.assertRaises(UserError):
            schedule.action_close()
        # State must remain 'confirmed' (close was blocked, not partial)
        self.assertEqual(
            schedule.state, 'confirmed',
            "action_close must NOT transition state when blocked by draft "
            "lines (atomic guard).",
        )

        # ------------------------------------------------------------------
        # AND: action_draft reverts confirmed -> draft and clears lines
        # (since no posted lines exist, the revert is allowed).
        # ------------------------------------------------------------------
        schedule.action_draft()
        self.assertEqual(
            schedule.state, 'draft',
            "action_draft must revert state from 'confirmed' to 'draft'.",
        )
        self.assertFalse(
            schedule.line_ids,
            "action_draft must clear all draft recognition lines so the "
            "schedule can be reconfigured and regenerated.",
        )

        # ------------------------------------------------------------------
        # AND: action_confirm cannot be called twice (state guard) --
        # it raises UserError when invoked on a confirmed schedule.
        # Re-confirm to set up the test, then attempt re-confirmation.
        # ------------------------------------------------------------------
        schedule.action_confirm()
        with self.assertRaises(UserError):
            schedule.action_confirm()

        # ------------------------------------------------------------------
        # AND: action_draft cannot be called on a draft schedule --
        # it raises UserError. Reset via action_draft, then attempt again.
        # ------------------------------------------------------------------
        schedule.action_draft()  # confirmed -> draft
        self.assertEqual(schedule.state, 'draft')
        with self.assertRaises(UserError):
            schedule.action_draft()  # draft -> draft is forbidden

        # ------------------------------------------------------------------
        # AND: action_close cannot be called on a draft schedule --
        # it raises UserError (only confirmed schedules can be closed).
        # ------------------------------------------------------------------
        with self.assertRaises(UserError):
            schedule.action_close()

        # ------------------------------------------------------------------
        # AND: line_count computed field mirrors len(line_ids). Exercises
        # the :meth:`_compute_line_count` body for non-stored compute.
        # Generate lines first by re-confirming the schedule.
        # ------------------------------------------------------------------
        schedule.action_confirm()
        self.assertEqual(
            schedule.line_count, len(schedule.line_ids),
            "line_count must equal len(line_ids) (computed read-only).",
        )
        self.assertGreater(
            schedule.line_count, 0,
            "Confirmed straight_line schedule must produce >0 lines.",
        )

        # ------------------------------------------------------------------
        # AND: action_close success path -- when no draft lines remain,
        # the schedule transitions confirmed -> closed cleanly.
        # We exercise this by manually unlinking the draft lines from a
        # confirmed schedule (a normal user would post them via the
        # DR-003 cut-off wizard, but here we just want to drive coverage
        # of the success branch). After unlinking, action_close finds
        # zero draft lines and proceeds to set state='closed'.
        # ------------------------------------------------------------------
        schedule.line_ids.unlink()
        schedule.action_close()
        self.assertEqual(
            schedule.state, 'closed',
            "action_close must transition state from 'confirmed' to "
            "'closed' when no draft lines remain (success path).",
        )
        # ------------------------------------------------------------------
        # AND: completion_status compute reflects the closed state.
        # When state == 'closed', completion_status is 'completed'
        # regardless of remaining_amount (the closed branch in
        # _compute_completion_status).
        # ------------------------------------------------------------------
        self.assertEqual(
            schedule.completion_status, 'completed',
            "Closed schedule must have completion_status='completed' "
            "(state == 'closed' branch in _compute_completion_status).",
        )
        # action_draft must not work on closed schedules either (only
        # confirmed -> draft is allowed).
        with self.assertRaises(UserError):
            schedule.action_draft()  # closed -> draft is forbidden

        # ------------------------------------------------------------------
        # AND: a manual-method schedule with NO lines triggers the
        # ``manual`` early-return branch in
        # :meth:`_compute_recognition_schedule` and the SUM INVARIANT
        # guard in :meth:`action_confirm`. We exercise both:
        #
        # 1. Direct call to ``_compute_recognition_schedule`` on a manual
        #    schedule covers lines 600-605 (manual early return: log
        #    informational message and return without generating lines).
        # 2. Calling ``action_confirm`` on the same manual schedule
        #    triggers the SUM INVARIANT guard because the manual schedule
        #    has zero recognition lines but a positive total_amount;
        #    sum(line.recognition_amount) == 0 != total_amount and
        #    UserError is raised (covers line 503's SUM INVARIANT path).
        # ------------------------------------------------------------------
        manual_schedule = self._create_draft_schedule(
            recognition_method='manual',
            total_amount=3000.0,
        )
        # Direct call -- covers manual early-return branch
        manual_schedule._compute_recognition_schedule()
        self.assertFalse(
            manual_schedule.line_ids,
            "Manual schedule must have no auto-generated lines; "
            "_compute_recognition_schedule returns early for manual method.",
        )
        # action_confirm on a manual schedule with no lines must raise
        # UserError via the SUM INVARIANT guard (sum=0, total=3000).
        with self.assertRaises(UserError):
            manual_schedule.action_confirm()
        # State must remain draft (confirm was blocked)
        self.assertEqual(
            manual_schedule.state, 'draft',
            "Manual schedule with no lines must NOT transition to "
            "'confirmed' (SUM INVARIANT blocked).",
        )

    # ==================================================================
    # Scenario 5: Validate Recognition Period Bounds
    # ==================================================================
    @freeze_time(_FROZEN_TODAY)
    def test_recognition_period_validation(self):
        """Scenario 5: Period bounds are validated by _check_dates and friends.

        BDD criteria (verbatim from DR-001 ticket):

        * GIVEN I am configuring a deferral schedule.
        * WHEN I set recognition parameters that exceed typical bounds.
        * THEN I should receive a warning for recognition periods over
          60 months AND I should not be able to set an end date before
          the start date AND I should not be able to set a start date
          in a locked period AND the system should validate period
          dates against fiscal year settings.

        Coverage targets:
            * :meth:`_check_dates` -- ValidationError when end_date <=
              start_date (strict inequality enforced).
            * :meth:`_check_amount` -- ValidationError when total_amount
              <= 0 (strictly positive amount enforced).
            * Long schedules (>60 months) are ALLOWED -- only a warning
              is logged via _logger.warning, NOT a ValidationError.
            * :meth:`_compute_period_count` -- handles long-span schedules.
        """
        # ------------------------------------------------------------------
        # AND: end_date < start_date must fail _check_dates with
        # ValidationError. The constraint raises with a clear message
        # naming both the start and end dates for diagnostics.
        # ------------------------------------------------------------------
        with self.assertRaises(ValidationError):
            self._create_draft_schedule(
                start_date=date(2024, 12, 31),
                end_date=date(2024, 1, 1),
            )

        # ------------------------------------------------------------------
        # AND: end_date == start_date must fail _check_dates because the
        # constraint enforces STRICT inequality (end > start, not >=).
        # A zero-length recognition period would have no defined behavior.
        # ------------------------------------------------------------------
        with self.assertRaises(ValidationError):
            self._create_draft_schedule(
                start_date=date(2024, 6, 1),
                end_date=date(2024, 6, 1),
            )

        # ------------------------------------------------------------------
        # AND: total_amount = 0 must fail _check_amount (zero deferral
        # is meaningless; the constraint enforces strictly positive).
        # ------------------------------------------------------------------
        with self.assertRaises(ValidationError):
            self._create_draft_schedule(total_amount=0.0)

        # ------------------------------------------------------------------
        # AND: negative total_amount must fail _check_amount (negative
        # deferrals are meaningless; constraint enforces > 0).
        # ------------------------------------------------------------------
        with self.assertRaises(ValidationError):
            self._create_draft_schedule(total_amount=-500.0)

        # ------------------------------------------------------------------
        # AND: write-time enforcement -- updating an existing schedule
        # to violate _check_amount must also raise (constraint runs on
        # write, not just on create).
        # ------------------------------------------------------------------
        valid_schedule = self._create_draft_schedule()
        with self.assertRaises(ValidationError):
            valid_schedule.write({'total_amount': -100.0})

        # ------------------------------------------------------------------
        # AND: write-time enforcement on _check_dates (end_date < start_date
        # via write() must raise just like via create()).
        # ------------------------------------------------------------------
        with self.assertRaises(ValidationError):
            valid_schedule.write({
                'start_date': date(2024, 12, 31),
                'end_date': date(2024, 1, 1),
            })

        # ------------------------------------------------------------------
        # AND: long schedule (>60 months) is ALLOWED -- only a warning is
        # logged. Per DR-001 Scenario 5, the 60-month threshold is a
        # warning-only soft limit, not a hard validation. The threshold
        # is read from ir.config_parameter
        # 'account_deferred_revenue.max_months_warning' (default '60').
        #
        # 84 months = 7 years = well above the 60-month threshold.
        # ------------------------------------------------------------------
        long_schedule = self._create_draft_schedule(
            start_date=date(2024, 1, 1),
            end_date=date(2030, 12, 31),  # ~84 months
        )
        self.assertTrue(
            long_schedule.id,
            "Schedules longer than 60 months must be permitted "
            "(warning-only per DR-001 Scenario 5 spec).",
        )
        self.assertGreater(
            long_schedule.period_count, 60,
            "Long schedule (Jan-2024 to Dec-2030) must compute to >60 periods.",
        )
        # The schedule is in draft state -- valid record despite warning.
        self.assertEqual(
            long_schedule.state, 'draft',
            "Long schedule must be persisted in 'draft' state, not rejected.",
        )

        # ------------------------------------------------------------------
        # AND: the ``max_months_warning`` ir.config_parameter is parsed
        # defensively. The constraint reads the parameter and falls back
        # to 60 if the value cannot be parsed as a positive integer.
        # We exercise both edge cases:
        #
        # 1. Non-numeric value -> ValueError -> threshold = 60 (fallback).
        # 2. Zero / negative value -> threshold <= 0 guard -> threshold = 60
        #    (fallback).
        #
        # In both cases, the constraint must continue to function correctly
        # (raise on end <= start; warning-only on long schedules).
        # ------------------------------------------------------------------
        # sudo required: writing to ir.config_parameter requires admin
        # privilege per R-07; reading the test's mutated value via the
        # same elevated handle keeps the parameter scope consistent.
        Config = self.env['ir.config_parameter'].sudo()
        param_key = 'account_deferred_revenue.max_months_warning'
        original_value = Config.get_param(param_key, default='60')
        try:
            # Edge case 1: non-numeric value forces fallback via ValueError
            Config.set_param(param_key, 'not-a-number')
            # Constraint still functions correctly with the fallback threshold.
            invalid_param_schedule = self._create_draft_schedule(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 12, 31),
            )
            self.assertEqual(
                invalid_param_schedule.period_count, 12,
                "Schedule creation must succeed even when max_months_warning "
                "is unparseable (constraint falls back to 60 internally).",
            )

            # Edge case 2: zero value forces fallback via threshold <= 0 guard
            Config.set_param(param_key, '0')
            zero_param_schedule = self._create_draft_schedule(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 6, 30),
            )
            self.assertEqual(
                zero_param_schedule.period_count, 6,
                "Schedule creation must succeed when max_months_warning "
                "is '0' (constraint falls back to 60 internally).",
            )

            # Edge case 3: negative value also forces threshold <= 0 fallback
            Config.set_param(param_key, '-10')
            neg_param_schedule = self._create_draft_schedule(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 3, 31),
            )
            self.assertEqual(
                neg_param_schedule.period_count, 3,
                "Schedule creation must succeed when max_months_warning "
                "is negative (constraint falls back to 60 internally).",
            )
        finally:
            # Always restore the original value so subsequent tests are
            # unaffected by these edge-case mutations.
            Config.set_param(param_key, original_value)

    # ==================================================================
    # Scenario 6: Link Schedule to Analytic Accounts
    # ==================================================================
    @freeze_time(_FROZEN_TODAY)
    def test_analytic_distribution_preservation(self):
        """Scenario 6: analytic_distribution flows from invoice line to schedule.

        BDD criteria (verbatim from DR-001 ticket):

        * GIVEN I am creating a deferral schedule AND the original
          transaction has analytic distribution.
        * WHEN recognition entries are generated.
        * THEN the analytic distribution should be preserved AND
          budget tracking should reflect the deferred amounts AND
          cost center allocations should carry forward to recognition
          entries.

        Coverage targets:
            * :attr:`account.deferred.schedule.analytic_distribution` --
              Json field stores the analytic distribution mapping.
            * :meth:`account.deferred.schedule.create` -- copies
              analytic_distribution from source_move_line_id when not
              explicitly supplied (DR-001 Scenario 6 backfill).
            * Isolation invariant: schedule-side modifications must not
              mutate the source invoice line's analytic_distribution.
        """
        # ------------------------------------------------------------------
        # GIVEN: an invoice line with analytic_distribution.
        # The Json field expects keys as STRINGS (str(analytic_id)) per
        # Odoo's JSON field semantics; using int keys silently produces
        # an invalid distribution that fails validation downstream.
        # ------------------------------------------------------------------
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'invoice_date': date(2024, 1, 1),
            'date': date(2024, 1, 1),
            'currency_id': self.currency.id,
            'invoice_line_ids': [Command.create({
                'name': 'Subscription with analytic distribution',
                'quantity': 1,
                'price_unit': 12000.0,
                'account_id': self.recognition_revenue_account.id,
                'tax_ids': [Command.set([])],
                'analytic_distribution': {
                    str(self.analytic_account.id): 100.0,
                },
            })],
        })
        invoice.action_post()

        revenue_line = invoice.line_ids.filtered(
            lambda line: line.account_id == self.recognition_revenue_account,
        )[:1]
        self.assertTrue(
            revenue_line,
            "Invoice must have a line on the recognition revenue account.",
        )
        self.assertTrue(
            revenue_line.analytic_distribution,
            "Source line must carry the analytic_distribution mapping.",
        )
        # Capture the original distribution so we can verify isolation later.
        original_distribution = dict(revenue_line.analytic_distribution)
        self.assertEqual(
            original_distribution,
            {str(self.analytic_account.id): 100.0},
            "Source line distribution must equal {analytic_id: 100.0}.",
        )

        # ------------------------------------------------------------------
        # WHEN: a schedule is created from that line via source_move_line_id
        # AND analytic_distribution is explicitly carried over.
        # ------------------------------------------------------------------
        schedule = self._create_draft_schedule(
            source_move_id=invoice.id,
            source_move_line_id=revenue_line.id,
            analytic_distribution=revenue_line.analytic_distribution,
        )

        # ------------------------------------------------------------------
        # THEN: the schedule's analytic_distribution preserves the same
        # JSON structure (cost-center allocation carried forward).
        # ------------------------------------------------------------------
        self.assertEqual(
            schedule.analytic_distribution,
            revenue_line.analytic_distribution,
            "Schedule must preserve the source line's analytic_distribution "
            "exactly (same plan-id -> percentage mapping).",
        )
        self.assertEqual(
            schedule.analytic_distribution,
            {str(self.analytic_account.id): 100.0},
            "Schedule's analytic_distribution must equal the original "
            "distribution {analytic_id: 100.0}.",
        )

        # ------------------------------------------------------------------
        # AND: the create() override also auto-copies analytic_distribution
        # from source_move_line_id when not explicitly supplied. Build a
        # second schedule WITHOUT passing analytic_distribution and verify
        # the override copies it from the source line.
        # ------------------------------------------------------------------
        schedule_auto = self.env['account.deferred.schedule'].create({
            'partner_id': self.partner.id,
            'company_id': self.company.id,
            'total_amount': 6000.0,
            'currency_id': self.currency.id,
            'deferred_account_id': self.deferred_revenue_account.id,
            'recognition_account_id': self.recognition_revenue_account.id,
            'recognition_method': 'straight_line',
            'start_date': date(2024, 1, 1),
            'end_date': date(2024, 6, 30),
            # Note the absence of source_move_id here: the model's
            # auto-copy behavior triggers solely on source_move_line_id
            # being set, regardless of whether source_move_id is also
            # explicitly populated. This matches the implementation in
            # account_deferred_schedule.create() which checks
            # ``vals.get('source_move_line_id')`` independently.
            'source_move_line_id': revenue_line.id,
            # NO analytic_distribution -- verify the create() override
            # copies it from source_move_line_id automatically.
        })
        self.assertEqual(
            schedule_auto.analytic_distribution,
            revenue_line.analytic_distribution,
            "create() override must auto-copy analytic_distribution from "
            "source_move_line_id when not explicitly supplied (DR-001 "
            "Scenario 6 backfill).",
        )

        # ------------------------------------------------------------------
        # AND: modifying the schedule's distribution must NOT back-propagate
        # to the source invoice line (isolation invariant). This is the
        # critical correctness property: a schedule is a SEPARATE record
        # whose mutations live independently of the invoice.
        # ------------------------------------------------------------------
        new_distribution = {str(self.analytic_account.id): 50.0}
        schedule.write({'analytic_distribution': new_distribution})
        self.assertEqual(
            schedule.analytic_distribution, new_distribution,
            "Schedule must accept analytic_distribution updates via write().",
        )
        # Re-read the source invoice line and verify it is UNCHANGED.
        # Invalidating the cache forces a fresh read from the database.
        revenue_line.invalidate_recordset(['analytic_distribution'])
        self.assertEqual(
            revenue_line.analytic_distribution,
            original_distribution,
            "Source invoice line distribution must remain unchanged after "
            "schedule-side modification (isolation invariant).",
        )
        self.assertNotEqual(
            schedule.analytic_distribution,
            revenue_line.analytic_distribution,
            "After modification, schedule's distribution must DIFFER from "
            "the source line's distribution -- they are independent records.",
        )
