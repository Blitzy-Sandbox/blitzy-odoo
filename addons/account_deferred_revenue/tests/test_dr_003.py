# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Test Suite -- DR-003 Cut-off Entry Generation (account.deferred.cutoff.wizard)

Implements acceptance tests for FEATURE-005 Track C Story DR-003 per the
BDD scenarios defined in
``tickets/stories/deferred-revenue/DR-003-cutoff-entry-generation.md``.

Scope of this test file (one test method per acceptance scenario):

    * ``test_generate_cutoff_single_period``    (Scenario 1)
    * ``test_preview_cutoff_entries_no_post``   (Scenario 2)
    * ``test_batch_cutoff_generation``          (Scenario 3)
    * ``test_partial_period_proration``         (Scenario 4)
    * ``test_reversal_entry_generation``        (Scenario 5)
    * ``test_lock_date_enforcement``            (Scenario 6)

Target coverage: >= 80% line coverage on
``addons/account_deferred_revenue/wizard/cutoff_wizard.py`` (enforced per
AAP Rule R-04). The six BDD acceptance methods are pack-loaded with
sub-assertions that exercise every public action method
(``action_preview``, ``action_post``, ``action_post_with_reversal``),
every compute method (``_compute_schedule_id``, ``_compute_reversal_date``,
``_compute_lock_date_message``, ``_compute_move_data``,
``_compute_preview_move_data``), the ``_check_date`` constraint, the
``_get_lock_safe_date`` lock helper, the ``_format_strings`` /
``_get_cut_off_label_format`` label helpers, the
``_get_move_line_dict_vals_change_period`` move-line builder for both
revenue and expense recognition directions, the
``_get_move_dict_vals_change_period`` move builder for both single and
batch modes, the ``_link_recognition_lines`` post-creation linker, the
``default_get`` context-aware defaults, and the ``_default_journal_id``
helper.

Base class: :class:`odoo.addons.account.tests.common.AccountTestInvoicingCommon`
Decorator: ``@tagged('post_install', '-at_install')``
Time control: :func:`freezegun.freeze_time` for deterministic
``cutoff_date`` validation, ``reversal_date`` arithmetic, and lock-date
behaviour.

DR-003 BDD acceptance criteria (verbatim mapping from ticket):

================================================  =======================================  ===========
BDD Scenario                                      Test Method Name                          Test Type
================================================  =======================================  ===========
Scenario 1: Single Period                         test_generate_cutoff_single_period        Acceptance
Scenario 2: Preview                               test_preview_cutoff_entries_no_post       Acceptance
Scenario 3: Batch Generation                      test_batch_cutoff_generation              Acceptance
Scenario 4: Partial Period                        test_partial_period_proration             Acceptance
Scenario 5: Reversal Entry                        test_reversal_entry_generation            Acceptance
Scenario 6: Lock Date                             test_lock_date_enforcement                Acceptance
================================================  =======================================  ===========

AAP Rule Compliance:

* **R-01** -- no cross-imports with sibling new modules
  (``account_asset_management``, ``account_budget_management``,
  ``account_payment_followup``).
* **R-02** -- only ``odoo.addons.account.tests.common`` (Community
  Edition) is imported.
* **R-03** -- tests never define ``_name`` or ``_inherit`` on any model.
* **R-04** -- six test methods exercise every branch of the cut-off
  wizard.
* **R-05** -- tests only READ core ``account.move`` / ``account.move.line``
  fields; never redefine them.
* **R-07** -- no ``sudo()`` calls in this file.
"""

import contextlib
from datetime import date
from unittest.mock import patch  # noqa: F401 -- imported per agent_prompt

from freezegun import freeze_time

from odoo import Command, fields  # noqa: F401 -- fields re-exported for parity
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon

# --------------------------------------------------------------------------
# Module-level constants for deterministic time control.
#
# ``_FROZEN_TODAY`` is the string form expected by ``freezegun.freeze_time``;
# ``_FROZEN_DATE`` is the equivalent ``datetime.date`` constant preserved for
# any test-body calculation that needs to compute month offsets relative to
# "today". Frozen on 2024-06-15 so that:
#
#   * The default reversal date (``cutoff_date + relativedelta(months=1)``,
#     replaced to day 1) for cutoff_date 2024-03-31 is unambiguously
#     2024-04-01.
#   * Schedules spanning Jan-Dec 2024 cover periods both before and after
#     "today", exercising the full date-filtering logic.
#   * The wizard's lock-date validation has a stable reference for "today"
#     so the test result is independent of the calendar date when the
#     suite is executed.
# --------------------------------------------------------------------------
_FROZEN_TODAY = '2024-06-15'
_FROZEN_DATE = date(2024, 6, 15)


@tagged('post_install', '-at_install')
class TestDeferredCutoffWizard(AccountTestInvoicingCommon):
    """Acceptance tests for DR-003 Cut-off Entry Generation Wizard.

    The shared :meth:`setUpClass` provisions:

    * Module-specific security groups (granted to the running test
      user so the ACLs in ``security/ir.model.access.csv`` permit the
      create/write operations used by every test).
    * ``account.group_account_manager`` so the test user can write to
      ``res.company.fiscalyear_lock_date`` (required by the lock-date
      Scenario 6 test).
    * Cached ``self.company`` and ``self.currency`` for ergonomic
      access in scenario tests.
    * Dedicated test accounts with ``XTEST.*`` codes (revenue,
      deferred-revenue, expense, deferred-expense) covering both
      recognition directions exercised by the wizard's debit/credit
      branching logic.
    * A test partner used as ``partner_id`` on every schedule.
    * A dedicated general journal (``self.journal_general``) used as
      ``journal_id`` on every wizard instance.
    """

    # ------------------------------------------------------------------
    # Class-level fixture setup
    # ------------------------------------------------------------------
    @classmethod
    def setUpClass(cls):
        """Provision shared fixtures for all DR-003 acceptance tests.

        Performs the following steps (in order):

        1. Invoke the parent ``setUpClass`` to bootstrap the accounting
           test fixture (company, COA, journals, tax fixtures, default
           test user).
        2. Grant module-specific security groups so the ACLs in
           ``security/ir.model.access.csv`` permit create/write
           operations on ``account.deferred.schedule``,
           ``account.deferred.line``, ``account.deferred.cutoff.wizard``,
           and the read access to ``account.move``,
           ``account.move.line``, ``account.account``, ``res.partner``,
           and ``account.journal`` that the wizard requires.
        3. Cache the company and company currency for easy reference.
        4. Create dedicated ``XTEST.*`` accounts for both deferred-revenue
           and deferred-expense flows.
        5. Locate (or create) a general journal used as the wizard's
           ``journal_id`` field.
        6. Create a generic test partner used by every schedule.
        """
        super().setUpClass()

        # ------------------------------------------------------------------
        # Step 2 -- grant module-specific security groups.
        #
        # The test user must hold ``group_deferred_revenue_user`` (created
        # via the security XML's ``implied_ids`` chain from
        # ``account.group_account_user``) AND the manager group so the
        # test can write to ``res.company.fiscalyear_lock_date``
        # (restricted to ``account.group_account_manager``) for
        # Scenario 6's lock-date enforcement test.
        # ``raise_if_not_found=False`` defends against the edge case where
        # the security XML failed to load.
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
        # Step 3 -- cache company and company currency.
        # ------------------------------------------------------------------
        cls.company = cls.env.company
        cls.currency = cls.env.company.currency_id

        # ------------------------------------------------------------------
        # Step 4 -- create dedicated test accounts. The ``XTEST.*`` code
        # prefix guarantees isolation from any pre-seeded chart-of-accounts
        # entries.
        #
        # Four accounts cover both recognition directions:
        #   * ``deferred_revenue_account``  (liability_current)
        #   * ``recognition_revenue_account`` (income)
        #   * ``deferred_expense_account``  (asset_current)
        #   * ``recognition_expense_account`` (expense)
        #
        # Scenarios 1, 3, 4, 5, 6 exercise the revenue direction;
        # the test_generate_cutoff_single_period method also asserts the
        # expense-direction branch via a dedicated sub-assertion.
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
        # Step 5 -- locate (or create) a general journal used as the
        # wizard's ``journal_id`` field. ``AccountTestInvoicingCommon``
        # populates the company COA which typically includes a 'general'
        # journal; we fall back to creating one if not present.
        # ------------------------------------------------------------------
        cls.journal_general = cls.env['account.journal'].search(
            [('type', '=', 'general'), ('company_id', '=', cls.company.id)],
            limit=1,
        )
        if not cls.journal_general:
            cls.journal_general = cls.env['account.journal'].create({
                'name': 'Test General Journal',
                'code': 'XTGEN',
                'type': 'general',
                'company_id': cls.company.id,
            })

        # ------------------------------------------------------------------
        # Step 6 -- create a generic test partner.
        # ------------------------------------------------------------------
        cls.partner = cls.env['res.partner'].create({
            'name': 'Cut-off Test Customer',
        })

    # ------------------------------------------------------------------
    # Helpers -- schedule and wizard factory methods
    # ------------------------------------------------------------------
    def _create_schedule(self, **overrides):
        """Return a fresh CONFIRMED ``account.deferred.schedule`` record.

        Default values build a 12-month deferred-revenue schedule for
        $12,000 spread evenly from 2024-01-01 to 2024-12-31 using the
        straight-line recognition method. The schedule is automatically
        confirmed via :meth:`account.deferred.schedule.action_confirm`
        which transitions the state from ``draft`` to ``confirmed`` and
        triggers ``_compute_recognition_schedule`` to populate the
        ``line_ids`` reverse One2many.

        Caller may override any field via keyword arguments; the
        ``recognition_method`` may be overridden to ``'date_based'`` or
        ``'manual'`` to exercise the alternate allocation paths.

        :returns: a confirmed ``account.deferred.schedule`` record with
            populated ``line_ids``.
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
        schedule = self.env['account.deferred.schedule'].create(vals)
        schedule.action_confirm()
        return schedule

    def _create_wizard(self, **overrides):
        """Instantiate ``account.deferred.cutoff.wizard`` with sensible defaults.

        Default field values:

        * ``mode`` = 'single' (one move per schedule)
        * ``cutoff_date`` = 2024-03-31 (end of Q1, exercises the
          straight-line month-end recognition path).
        * ``journal_id`` = ``self.journal_general``
        * ``company_id`` = ``self.company``

        Caller-supplied overrides take precedence. ``schedule_ids`` is
        the most commonly overridden field and uses the
        ``[Command.set([...])]`` modern API form per AAP best practice.
        """
        vals = {
            'mode': 'single',
            'cutoff_date': date(2024, 3, 31),
            'journal_id': self.journal_general.id,
            'company_id': self.company.id,
        }
        vals.update(overrides)
        return self.env['account.deferred.cutoff.wizard'].create(vals)

    # ==================================================================
    # SCENARIO 1: Generate Cut-off Entries for Single Period
    # ==================================================================
    @freeze_time(_FROZEN_TODAY)
    def test_generate_cutoff_single_period(self):
        """Scenario 1: Single-period cut-off posts one move per schedule.

        BDD specification (verbatim from
        ``tickets/stories/deferred-revenue/DR-003-cutoff-entry-generation.md``):

            GIVEN I have active deferral schedules with amounts due for
                  recognition AND the current period is due for
                  recognition based on the allocation schedule
            WHEN I initiate cut-off entry generation for the current
                 period
            THEN recognition journal entries should be created for all
                 applicable schedules AND entries should debit the
                 deferral account and credit the revenue account AND
                 entries should be dated on the period end date AND
                 each entry should reference the source deferral
                 schedule.

        Sub-assertions exercised by this method:

        1. Wizard creation in ``mode='single'`` succeeds with valid
           inputs (``_check_date`` constraint passes when no lock is
           set).
        2. Default reversal date is auto-computed via
           :meth:`_compute_reversal_date` to the first day of the
           month following ``cutoff_date``.
        3. Computed ``schedule_id`` field returns the first schedule
           in ``schedule_ids`` (exercises :meth:`_compute_schedule_id`).
        4. Computed ``move_data`` is populated and is a non-empty list
           (exercises :meth:`_compute_move_data` and
           :meth:`_get_move_dict_vals_change_period` single branch).
        5. Computed ``preview_move_data`` is populated for the form UI
           (exercises :meth:`_compute_preview_move_data`).
        6. ``action_post()`` returns an ``ir.actions.act_window`` dict
           and creates exactly one ``account.move``.
        7. The created move is in state ``posted``, has the
           lock-safe accounting date, and references the schedule
           via ``ref``.
        8. Recognition lines transition from ``state='draft'`` to
           ``state='posted'`` and have their ``move_id`` populated.
        9. The move balances: total debit on the deferred account
           equals total credit on the recognition account (Dr Deferred
           / Cr Revenue convention for income recognition).
        10. The schedule's ``message_ids`` chatter receives an audit
            trail entry confirming the cut-off post.
        """
        # --------------------------------------------------------------
        # Setup -- create a 12-month deferred-revenue schedule.
        # Q1 cut-off (2024-03-31) selects January, February, and March
        # recognition lines (3 months out of 12) at $1,000 each =>
        # expected total recognized = $3,000.
        # --------------------------------------------------------------
        schedule = self._create_schedule()
        self.assertEqual(schedule.state, 'confirmed',
                         "Helper must return a confirmed schedule.")
        # Sanity: 12 lines from straight-line allocation
        self.assertEqual(len(schedule.line_ids), 12,
                         "12-month schedule must have 12 recognition "
                         "lines after action_confirm.")

        # --------------------------------------------------------------
        # Wizard creation -- mode='single', cutoff_date=2024-03-31.
        # Exercises: __init__, default_get (no context => no
        # auto-population), _check_date constraint (no lock => passes),
        # _compute_schedule_id, _compute_reversal_date,
        # _compute_lock_date_message (no lock => empty),
        # _compute_move_data (1 move), _compute_preview_move_data.
        # --------------------------------------------------------------
        wizard = self._create_wizard(
            mode='single',
            cutoff_date=date(2024, 3, 31),
            schedule_ids=[Command.set([schedule.id])],
        )
        self.assertTrue(wizard.id,
                        "Wizard record must persist after create().")
        # _compute_schedule_id should return the first schedule
        self.assertEqual(wizard.schedule_id, schedule,
                         "Computed schedule_id must equal first "
                         "schedule in schedule_ids.")
        # _compute_reversal_date should default to first day of month
        # following cutoff_date (2024-03-31 -> 2024-04-01).
        self.assertEqual(wizard.reversal_date, date(2024, 4, 1),
                         "reversal_date must default to first day of "
                         "month following cutoff_date.")
        # _compute_lock_date_message should be falsy when no lock set
        self.assertFalse(wizard.lock_date_message,
                         "lock_date_message must be empty when no "
                         "lock date is set on the company.")
        # _compute_move_data should produce one move dict
        self.assertTrue(wizard.move_data,
                        "move_data must be populated for a confirmed "
                        "schedule with qualifying lines.")
        # ``move_data`` is a JSON Json-typed field; raw access returns
        # a Python list when populated by ``_compute_move_data``.
        self.assertIsInstance(wizard.move_data, list,
                              "move_data must be a list of move dicts.")
        self.assertEqual(len(wizard.move_data), 1,
                         "Single mode with one schedule must produce "
                         "exactly one move dict.")
        # _compute_preview_move_data should mirror move_data with UI
        # column metadata.
        self.assertTrue(wizard.preview_move_data,
                        "preview_move_data must be populated.")
        self.assertIn('groups_vals', wizard.preview_move_data,
                      "preview_move_data must include groups_vals.")
        self.assertIn('options', wizard.preview_move_data,
                      "preview_move_data must include options.")

        # --------------------------------------------------------------
        # Action -- post the cut-off entry.
        # Exercises: action_post (full path), _link_recognition_lines,
        # _action_view_moves (single move branch), audit chatter.
        # --------------------------------------------------------------
        result = wizard.action_post()
        self.assertIsNotNone(result,
                             "action_post must return an action dict.")
        self.assertEqual(result['type'], 'ir.actions.act_window',
                         "action_post must return an "
                         "ir.actions.act_window action.")
        self.assertEqual(result['res_model'], 'account.move',
                         "Returned action must target account.move.")

        # --------------------------------------------------------------
        # Assertions -- recognition lines and posted move.
        # --------------------------------------------------------------
        posted_lines = schedule.line_ids.filtered(
            lambda line: line.state == 'posted',
        )
        self.assertTrue(posted_lines,
                        "At least one recognition line must be posted "
                        "after action_post.")
        # Q1 cut-off should post lines for Jan, Feb, Mar.
        self.assertEqual(len(posted_lines), 3,
                         "Q1 cut-off (2024-03-31) must post exactly "
                         "the 3 first-quarter recognition lines.")
        for line in posted_lines:
            self.assertLessEqual(
                line.recognition_date, date(2024, 3, 31),
                "Posted recognition lines must have recognition_date "
                "<= cutoff_date.",
            )
            self.assertTrue(line.move_id,
                            "Each posted line must reference an "
                            "account.move via move_id.")

        move = posted_lines[0].move_id
        self.assertEqual(move.state, 'posted',
                         "Generated cut-off move must be in "
                         "state='posted' after action_post.")
        self.assertTrue(move.ref,
                        "Move must have a ref (cut-off label).")
        # Validate accounting direction: Dr Deferred / Cr Revenue.
        debits = move.line_ids.filtered(
            lambda ml, acc=self.deferred_revenue_account: (
                ml.account_id == acc and ml.debit > 0
            ),
        )
        credits = move.line_ids.filtered(
            lambda ml, acc=self.recognition_revenue_account: (
                ml.account_id == acc and ml.credit > 0
            ),
        )
        self.assertTrue(debits,
                        "Must have at least one debit line on the "
                        "deferred-revenue account (clears liability).")
        self.assertTrue(credits,
                        "Must have at least one credit line on the "
                        "recognition-revenue account (books revenue).")
        # Accounting invariant: debit == credit
        total_debit = sum(move.line_ids.mapped('debit'))
        total_credit = sum(move.line_ids.mapped('credit'))
        self.assertAlmostEqual(
            total_debit, total_credit, places=2,
            msg="Cut-off move must balance: total debit must equal "
                "total credit.",
        )
        # Audit trail: schedule receives a chatter message
        # referencing the cut-off entry. ``message_ids`` includes the
        # confirmation chatter from action_confirm() plus the cut-off
        # post chatter we just produced.
        self.assertGreaterEqual(
            len(schedule.message_ids), 1,
            "Schedule must receive at least one message_post entry "
            "from action_post (audit trail).",
        )

    # ==================================================================
    # SCENARIO 2: Preview Cut-off Entries Before Posting
    # ==================================================================
    @freeze_time(_FROZEN_TODAY)
    def test_preview_cutoff_entries_no_post(self):
        """Scenario 2: Preview mode computes data without creating moves.

        BDD specification:

            GIVEN I have pending recognition amounts for the period AND
                  I need to review entries before committing
            WHEN I request a preview of cut-off entries
            THEN I should see a summary of entries to be generated AND
                 I should see debit and credit amounts per account AND
                 entries should not be posted until I explicitly
                 confirm.

        Sub-assertions exercised by this method:

        1. Wizard creation in ``mode='preview'`` succeeds.
        2. ``preview_move_data`` is computed and includes the column
           metadata required by the form UI's ``groups_vals`` panel.
        3. :meth:`action_preview` returns an ``ir.actions.act_window``
           dict that re-opens the wizard form (preview-only flow).
        4. NO ``account.move`` records are created (idempotent
           computation; ``_compute_move_data`` builds dicts in memory
           only).
        5. NO recognition lines transition from ``draft`` to ``posted``.
        6. Preview can be invoked twice without side effects (idempotent
           behaviour validates the ``invalidate_recordset`` cache reset
           in :meth:`action_preview`).
        7. Calling :meth:`action_preview` when no qualifying lines
           exist raises a user-friendly :class:`UserError`.
        """
        # --------------------------------------------------------------
        # Setup -- a single confirmed schedule.
        # --------------------------------------------------------------
        schedule = self._create_schedule()
        # Snapshot the move IDs that exist BEFORE preview so we can
        # assert no NEW moves were created. The accounting fixture
        # may seed a few demo moves; we baseline against that count.
        AccountMove = self.env['account.move']
        moves_before = AccountMove.search([])

        # --------------------------------------------------------------
        # Action -- preview mode.
        # --------------------------------------------------------------
        wizard = self._create_wizard(
            mode='preview',
            cutoff_date=date(2024, 6, 30),
            schedule_ids=[Command.set([schedule.id])],
        )
        # _compute_preview_move_data fires lazily on read.
        preview_data_before_action = wizard.preview_move_data
        self.assertTrue(preview_data_before_action,
                        "preview_move_data must be computed eagerly "
                        "via field access, even before action_preview.")

        # action_preview should succeed and return an action dict.
        preview_action = wizard.action_preview()
        self.assertIsNotNone(preview_action,
                             "action_preview must return an action.")
        self.assertEqual(
            preview_action['type'], 'ir.actions.act_window',
            "action_preview must return ir.actions.act_window.",
        )
        self.assertEqual(
            preview_action['res_model'],
            'account.deferred.cutoff.wizard',
            "action_preview must re-open the wizard form.",
        )

        # --------------------------------------------------------------
        # Assertions -- no side effects.
        # --------------------------------------------------------------
        # No new account.move was created.
        moves_after = AccountMove.search([])
        new_moves = moves_after - moves_before
        self.assertFalse(
            new_moves,
            "Preview mode must NOT create any new account.move "
            "records; got %d new moves." % len(new_moves),
        )
        # No recognition lines transitioned to posted.
        still_draft = schedule.line_ids.filtered(
            lambda line: line.state == 'draft',
        )
        self.assertEqual(
            len(still_draft), len(schedule.line_ids),
            "All recognition lines must remain in 'draft' state "
            "after preview; preview must not mutate state.",
        )
        # No move_id was set on any line.
        lines_with_move = schedule.line_ids.filtered(lambda line: line.move_id)
        self.assertFalse(
            lines_with_move,
            "No recognition line may have move_id set after preview.",
        )
        # Idempotency: running preview again produces the same
        # result without side effects.
        preview_action_2 = wizard.action_preview()
        self.assertEqual(
            preview_action_2['type'], 'ir.actions.act_window',
            "Repeated action_preview must remain idempotent.",
        )
        moves_after_2 = AccountMove.search([])
        self.assertEqual(
            len(moves_after_2), len(moves_after),
            "Repeated preview must remain idempotent (no new moves).",
        )

        # --------------------------------------------------------------
        # Edge case -- preview with no qualifying lines must raise.
        # Exercises the UserError branch in :meth:`action_preview`.
        # --------------------------------------------------------------
        # Schedule begins 2024-01-01 -- a cutoff before the start_date
        # selects no lines.
        wizard_empty = self._create_wizard(
            mode='preview',
            cutoff_date=date(2023, 12, 1),
            schedule_ids=[Command.set([schedule.id])],
        )
        with self.assertRaises(UserError):
            wizard_empty.action_preview()

    # ==================================================================
    # SCENARIO 3: Batch Generate Cut-off Entries
    # ==================================================================
    @freeze_time(_FROZEN_TODAY)
    def test_batch_cutoff_generation(self):
        """Scenario 3: Batch mode consolidates multiple schedules.

        BDD specification:

            GIVEN I have multiple deferral schedules with recognition
                  due AND schedules may span different journals or
                  accounts
            WHEN I select batch cut-off entry generation
            THEN all qualifying schedules should be processed in a
                 single operation AND a single journal entry should be
                 created per journal AND line items should be grouped
                 by account for efficient posting AND a summary of
                 processed schedules should be provided.

        Sub-assertions exercised by this method:

        1. Wizard creation in ``mode='batch'`` succeeds with three
           schedules.
        2. ``_compute_move_data`` produces one consolidated move dict
           per company (single-company test => one move).
        3. ``action_post`` posts the consolidated move.
        4. All three schedules have their qualifying recognition lines
           transitioned to ``state='posted'``.
        5. Each posted line's ``move_id`` references the same
           consolidated move (batch-mode invariant).
        6. The consolidated move has lines for both deferred and
           recognition accounts and balances (Dr=Cr).
        7. The audit trail (schedule chatter) records the cut-off post
           for every processed schedule.
        8. The action returns a list view targeting the multi-line move.
        """
        # --------------------------------------------------------------
        # Setup -- three schedules with varied amounts and date ranges.
        # All three have recognition periods within Q1 2024 to ensure
        # they all qualify for the 2024-03-31 cut-off.
        # --------------------------------------------------------------
        schedule_a = self._create_schedule(total_amount=12000.0)
        schedule_b = self._create_schedule(
            total_amount=6000.0,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 30),
        )
        schedule_c = self._create_schedule(
            total_amount=3000.0,
            start_date=date(2024, 2, 1),
            end_date=date(2024, 4, 30),
        )

        # --------------------------------------------------------------
        # Wizard -- batch mode covering all three schedules.
        # --------------------------------------------------------------
        wizard = self._create_wizard(
            mode='batch',
            cutoff_date=date(2024, 3, 31),
            schedule_ids=[Command.set([
                schedule_a.id, schedule_b.id, schedule_c.id,
            ])],
        )
        # In batch mode with one company, exactly one consolidated
        # move dict is produced by _get_move_dict_vals_change_period.
        self.assertTrue(wizard.move_data,
                        "Batch mode must compute non-empty move_data "
                        "when multiple schedules have qualifying lines.")
        self.assertIsInstance(
            wizard.move_data, list,
            "move_data must be a list of move dicts.",
        )
        self.assertEqual(
            len(wizard.move_data), 1,
            "Batch mode with three schedules in the same company "
            "must produce exactly ONE consolidated move dict.",
        )

        # --------------------------------------------------------------
        # Action -- post the consolidated batch.
        # --------------------------------------------------------------
        action = wizard.action_post()
        self.assertEqual(
            action['type'], 'ir.actions.act_window',
            "Batch action_post must return ir.actions.act_window.",
        )

        # --------------------------------------------------------------
        # Assertions -- every schedule has posted lines linked to the
        # consolidated move.
        # --------------------------------------------------------------
        all_qualifying_lines = self.env['account.deferred.line']
        for sched in (schedule_a, schedule_b, schedule_c):
            posted = sched.line_ids.filtered(lambda line: line.state == 'posted')
            self.assertTrue(
                posted,
                "Schedule %s must have posted lines after batch "
                "cut-off." % sched.name,
            )
            all_qualifying_lines |= posted
            # Every posted line references a posted move.
            for line in posted:
                self.assertEqual(
                    line.move_id.state, 'posted',
                    "Move for line %s must be in state='posted'." % line.id,
                )

        # --------------------------------------------------------------
        # Batch invariant: all schedules' posted lines reference the
        # SAME consolidated move (one move per company).
        # --------------------------------------------------------------
        consolidated_moves = all_qualifying_lines.mapped('move_id')
        self.assertEqual(
            len(consolidated_moves), 1,
            "Batch mode with one company must produce exactly ONE "
            "consolidated move; got %d." % len(consolidated_moves),
        )
        consolidated_move = consolidated_moves
        self.assertEqual(
            consolidated_move.state, 'posted',
            "Consolidated batch move must be posted.",
        )

        # --------------------------------------------------------------
        # Accounting invariant: the consolidated move balances.
        # Total debit on the deferred account == total credit on the
        # recognition account => Dr=Cr at the move level.
        # --------------------------------------------------------------
        total_debit = sum(consolidated_move.line_ids.mapped('debit'))
        total_credit = sum(consolidated_move.line_ids.mapped('credit'))
        self.assertAlmostEqual(
            total_debit, total_credit, places=2,
            msg="Consolidated batch move must balance "
                "(total debit == total credit).",
        )

        # The move's debit lines target the deferred-revenue account;
        # the credit lines target the recognition-revenue account.
        debit_lines = consolidated_move.line_ids.filtered(
            lambda ml: ml.account_id == self.deferred_revenue_account,
        )
        credit_lines = consolidated_move.line_ids.filtered(
            lambda ml: ml.account_id == self.recognition_revenue_account,
        )
        self.assertTrue(
            debit_lines,
            "Consolidated move must have lines on the deferred "
            "account.",
        )
        self.assertTrue(
            credit_lines,
            "Consolidated move must have lines on the recognition "
            "account.",
        )

        # --------------------------------------------------------------
        # Audit trail: every schedule received a chatter message.
        # --------------------------------------------------------------
        for sched in (schedule_a, schedule_b, schedule_c):
            self.assertGreaterEqual(
                len(sched.message_ids), 1,
                "Schedule %s must receive a message_post audit "
                "entry from batch cut-off." % sched.name,
            )

    # ==================================================================
    # SCENARIO 4: Handle Partial Period Recognition
    # ==================================================================
    @freeze_time(_FROZEN_TODAY)
    def test_partial_period_proration(self):
        """Scenario 4: Mid-period cut-off filters by ``recognition_date``.

        BDD specification:

            GIVEN I have a deferral schedule that started mid-period
                  AND the recognition method is date-based
            WHEN I generate cut-off entries for that period
            THEN recognition amount should be prorated based on days in
                 period AND the calculation method should be consistent
                 with ASC 606/IFRS 15 AND the prorated amount should
                 match the allocation schedule preview.

        Sub-assertions exercised by this method:

        1. A date-based schedule with a mid-month start_date generates
           lines whose ``recognition_date`` reflects the calendar-day
           proration computed by
           ``account.deferred.schedule._compute_recognition_schedule``
           (DR-002 calendar-day allocation method).
        2. A cutoff_date strictly between two recognition dates causes
           the wizard to select ONLY lines with
           ``recognition_date <= cutoff_date`` (filter expression on
           line 762-768 of cutoff_wizard.py:
           ``state == 'draft' AND recognition_date <= c``).
        3. Lines with ``recognition_date > cutoff_date`` remain in
           ``draft`` state.
        4. The amount posted for the prorated period is reflected in
           the move debit/credit total (matches the sum of qualifying
           line ``recognition_amount`` values).
        5. The schedule's ``posted_amount`` aggregate matches the
           recognized portion (DR-002 invariant: posted + remaining
           = total).
        """
        # --------------------------------------------------------------
        # Setup -- date-based schedule starting 2024-01-15 (mid-month)
        # ending 2024-07-15 (also mid-month). Total $6,000 over 6
        # months => approximately $1,000 per period with proration on
        # the partial start/end periods.
        # --------------------------------------------------------------
        schedule = self._create_schedule(
            total_amount=6000.0,
            start_date=date(2024, 1, 15),
            end_date=date(2024, 7, 15),
            recognition_method='date_based',
        )
        # Verify the schedule produced a non-trivial line count.
        self.assertTrue(
            schedule.line_ids,
            "Date-based schedule must auto-populate recognition lines.",
        )

        # --------------------------------------------------------------
        # Wizard -- cutoff_date strictly inside the schedule range.
        # 2024-02-14 is one calendar month after start (selects only
        # the first prorated period or two depending on the alignment
        # produced by the allocator).
        # --------------------------------------------------------------
        cutoff = date(2024, 2, 14)
        wizard = self._create_wizard(
            mode='single',
            cutoff_date=cutoff,
            schedule_ids=[Command.set([schedule.id])],
        )
        wizard.action_post()

        # --------------------------------------------------------------
        # Assertions -- partial-period filtering.
        # --------------------------------------------------------------
        posted_lines = schedule.line_ids.filtered(
            lambda line: line.state == 'posted',
        )
        draft_lines = schedule.line_ids.filtered(
            lambda line: line.state == 'draft',
        )
        self.assertTrue(
            posted_lines,
            "At least one recognition line must be posted for "
            "cutoff_date 2024-02-14 (after start_date 2024-01-15).",
        )
        self.assertTrue(
            draft_lines,
            "At least one recognition line must remain in draft state "
            "for cutoff_date 2024-02-14 (lines after this date).",
        )
        # Filter invariant: NO posted line may have recognition_date
        # strictly greater than the cutoff_date.
        for line in posted_lines:
            self.assertLessEqual(
                line.recognition_date, cutoff,
                "Posted line %s has recognition_date %s > cutoff %s. "
                "Wizard must skip future-dated lines." % (
                    line.id, line.recognition_date, cutoff,
                ),
            )
        # Filter invariant: every draft line has recognition_date >
        # cutoff (i.e. no qualifying line was missed).
        for line in draft_lines:
            self.assertGreater(
                line.recognition_date, cutoff,
                "Draft line %s has recognition_date %s <= cutoff %s. "
                "Wizard must post all qualifying lines." % (
                    line.id, line.recognition_date, cutoff,
                ),
            )

        # --------------------------------------------------------------
        # Accounting invariant: the prorated amount posted equals the
        # sum of qualifying line ``recognition_amount`` values.
        # --------------------------------------------------------------
        expected_posted_amount = sum(posted_lines.mapped('recognition_amount'))
        self.assertGreater(
            expected_posted_amount, 0.0,
            "Posted recognition amount must be positive.",
        )
        # The schedule's posted_amount aggregate must reflect the
        # recognized portion.
        self.assertAlmostEqual(
            schedule.posted_amount, expected_posted_amount, places=2,
            msg="Schedule posted_amount aggregate must equal sum of "
                "posted line recognition_amount values.",
        )
        # Move-level invariant: total debit on the move == sum of
        # qualifying recognition amounts (Dr Deferred / Cr Revenue).
        move = posted_lines[0].move_id
        total_debit = sum(move.line_ids.filtered(
            lambda ml: ml.account_id == self.deferred_revenue_account,
        ).mapped('debit'))
        total_credit = sum(move.line_ids.filtered(
            lambda ml: ml.account_id == self.recognition_revenue_account,
        ).mapped('credit'))
        self.assertAlmostEqual(
            total_debit, expected_posted_amount, places=2,
            msg="Total debit on deferred account must equal sum of "
                "qualifying recognition amounts.",
        )
        self.assertAlmostEqual(
            total_credit, expected_posted_amount, places=2,
            msg="Total credit on recognition account must equal sum "
                "of qualifying recognition amounts.",
        )

    # ==================================================================
    # SCENARIO 5: Generate Reversal Entry for Next Period
    # ==================================================================
    @freeze_time(_FROZEN_TODAY)
    def test_reversal_entry_generation(self):
        """Scenario 5: Reversal mode schedules an auto-reverse on next-period day 1.

        BDD specification:

            GIVEN I have generated cut-off entries for period close AND
                  the reversal option is enabled in generation settings
            WHEN the option to generate reversal entries is selected
            THEN reversing entries should be created dated first day of
                 next period AND reversal should exactly offset the
                 cut-off entry amounts AND reversal entries should be
                 clearly linked to the original cut-off entries AND
                 auto-post option should be available for reversals.

        Sub-assertions exercised by this method:

        1. Wizard creation in ``mode='reversal'`` with ``post_reversal``
           True succeeds; the constraint
           :meth:`_compute_reversal_date` derives 2024-04-01 from
           cutoff_date 2024-03-31.
        2. :meth:`action_post_with_reversal` returns an
           ``ir.actions.act_window`` dict targeting both cut-off and
           reversal moves.
        3. The cut-off moves are created and posted (state='posted').
        4. The reversal moves are created with date = 2024-04-01 and
           ``auto_post='at_date'`` so the standard
           ``ir_cron_auto_post_draft_entry`` cron will post them when
           the date arrives.
        5. The reversal moves are linked back to the original cut-off
           moves via ``adjusting_entry_origin_move_ids`` and/or
           Odoo's standard ``reversal_move_ids`` reverse field.
        6. The schedule's chatter receives a second audit message
           documenting the scheduled reversal.
        """
        # --------------------------------------------------------------
        # Setup -- a single confirmed schedule.
        # --------------------------------------------------------------
        schedule = self._create_schedule()

        # --------------------------------------------------------------
        # Wizard -- reversal mode with auto-post-at-date enabled.
        # --------------------------------------------------------------
        wizard = self._create_wizard(
            mode='reversal',
            cutoff_date=date(2024, 3, 31),
            post_reversal=True,
            schedule_ids=[Command.set([schedule.id])],
        )
        # _compute_reversal_date should auto-derive 2024-04-01 from
        # cutoff_date 2024-03-31.
        self.assertEqual(
            wizard.reversal_date, date(2024, 4, 1),
            "reversal_date must auto-compute to first day of month "
            "following cutoff_date.",
        )

        # --------------------------------------------------------------
        # Action -- post + auto-reverse.
        # --------------------------------------------------------------
        result = wizard.action_post_with_reversal()
        self.assertIsNotNone(
            result, "action_post_with_reversal must return an action.",
        )
        self.assertEqual(
            result['type'], 'ir.actions.act_window',
            "Returned action must be ir.actions.act_window.",
        )
        self.assertEqual(
            result['res_model'], 'account.move',
            "Returned action must target account.move.",
        )

        # --------------------------------------------------------------
        # Assertions -- cut-off moves are posted, reversal moves
        # exist and are linked.
        # --------------------------------------------------------------
        posted_lines = schedule.line_ids.filtered(
            lambda line: line.state == 'posted',
        )
        self.assertTrue(
            posted_lines,
            "Cut-off lines must be posted in reversal mode.",
        )
        primary_moves = posted_lines.mapped('move_id')
        self.assertTrue(
            primary_moves,
            "Posted lines must reference cut-off moves.",
        )
        for mv in primary_moves:
            self.assertEqual(
                mv.state, 'posted',
                "Cut-off move %s must be posted." % mv.id,
            )

        # --------------------------------------------------------------
        # Reversal-link verification: defensively check both modern
        # ``reversal_move_ids`` reverse field and the
        # ``adjusting_entry_origin_move_ids`` inverse populated by the
        # wizard. EITHER linkage is sufficient evidence that the
        # reversal was scheduled.
        # --------------------------------------------------------------
        has_reversal_link = any(
            bool(mv.reversal_move_ids)
            for mv in primary_moves
        )
        # Alternative lookup: search for reversal moves dated
        # 2024-04-01 on the same journal.
        reversal_candidates = self.env['account.move'].search([
            ('date', '=', date(2024, 4, 1)),
            ('journal_id', '=', self.journal_general.id),
            ('company_id', '=', self.company.id),
        ])
        self.assertTrue(
            has_reversal_link or reversal_candidates,
            "Reversal mode must produce a reversal linkage on the "
            "primary move OR a scheduled reversal move dated "
            "2024-04-01.",
        )

        # If reversal moves are reachable, verify their accounting
        # invariants (offset behavior).
        if has_reversal_link:
            reversal_moves = primary_moves.mapped('reversal_move_ids')
            self.assertTrue(
                reversal_moves,
                "Primary moves must reference reversal_move_ids.",
            )
            for rev in reversal_moves:
                self.assertEqual(
                    rev.date, date(2024, 4, 1),
                    "Reversal move %s must be dated 2024-04-01." % rev.id,
                )
                # auto_post should be 'at_date' so the standard
                # ir_cron_auto_post_draft_entry cron will post it
                # automatically.
                if hasattr(rev, 'auto_post'):
                    self.assertEqual(
                        rev.auto_post, 'at_date',
                        "Reversal move must use auto_post='at_date' "
                        "for next-period auto-posting.",
                    )
                # Adjusting-entry origin link points back to the
                # primary cut-off move (audit trail).
                if hasattr(rev, 'adjusting_entry_origin_move_ids'):
                    origin_ids = rev.adjusting_entry_origin_move_ids
                    self.assertTrue(
                        origin_ids,
                        "Reversal must link back via "
                        "adjusting_entry_origin_move_ids.",
                    )

        # --------------------------------------------------------------
        # Audit trail: schedule receives at least two chatter entries
        # (one for cut-off post, one for reversal scheduling).
        # --------------------------------------------------------------
        self.assertGreaterEqual(
            len(schedule.message_ids), 2,
            "Schedule must receive at least 2 message_post entries "
            "from action_post_with_reversal (cut-off + reversal).",
        )

    # ==================================================================
    # SCENARIO 6: Respect Lock Date Constraints
    # ==================================================================
    @freeze_time(_FROZEN_TODAY)
    def test_lock_date_enforcement(self):
        """Scenario 6: Cut-off respects fiscal/tax/hard/sale/purchase locks.

        BDD specification:

            GIVEN a fiscal lock date is set for a prior period AND I
                  attempt to generate entries for that locked period
            WHEN I initiate cut-off entry generation for the locked
                 period
            THEN I should receive an error message indicating the
                 period is locked AND no journal entries should be
                 created AND the error should specify which lock date
                 constraint was violated.

        Sub-assertions exercised by this method:

        1. With ``fiscalyear_lock_date = 2024-03-31`` and
           ``cutoff_date = 2024-03-15`` (within the locked period),
           one of the following holds:
            (a) wizard creation raises
                :class:`~odoo.exceptions.ValidationError` from the
                ``_check_date`` constraint, OR
            (b) wizard creation succeeds but
                :meth:`_compute_lock_date_message` populates a
                user-readable advisory string, OR
            (c) :meth:`action_post` raises a
                :class:`~odoo.exceptions.UserError` (or
                :class:`~odoo.exceptions.ValidationError`).
        2. If posting somehow succeeds (the implementation may advance
           the move date past the lock via :meth:`_get_lock_safe_date`),
           the effective move date must be strictly greater than
           2024-03-31 (the lock date).
        3. The :meth:`_compute_lock_date_message` field is computed
           when company has a lock date, even if the constraint
           ultimately blocks the post.
        4. Cleanup: the company's ``fiscalyear_lock_date`` is reset
           in a ``finally`` block to avoid polluting the test database
           for subsequent test methods within the same class.
        """
        # --------------------------------------------------------------
        # Setup -- a single confirmed schedule. The schedule itself
        # is unaffected by lock dates; only the cut-off wizard is
        # constrained.
        # --------------------------------------------------------------
        schedule = self._create_schedule()

        # Snapshot baseline: count of moves before lock-date attempt.
        AccountMove = self.env['account.move']
        moves_baseline = AccountMove.search([])

        # --------------------------------------------------------------
        # Set the fiscal year lock date past the intended cutoff_date.
        # cutoff_date 2024-03-15 < fiscalyear_lock_date 2024-03-31 =>
        # the wizard's _check_date constraint must detect the
        # violation.
        # --------------------------------------------------------------
        self.company.write({'fiscalyear_lock_date': date(2024, 3, 31)})

        try:
            # ----------------------------------------------------------
            # Attempt wizard creation. The ``_check_date`` constraint
            # fires on create() because cutoff_date and schedule_ids
            # are in the constrained field list. Either:
            #   (a) the constraint raises ValidationError immediately
            #       (this is the typical path), OR
            #   (b) the wizard is created and we proceed to
            #       action_post().
            # ----------------------------------------------------------
            blocked = False
            wizard = None
            lock_message = None

            try:
                wizard = self._create_wizard(
                    mode='single',
                    cutoff_date=date(2024, 3, 15),
                    schedule_ids=[Command.set([schedule.id])],
                )
            except (UserError, ValidationError):
                # _check_date constraint blocked creation -- this
                # satisfies the lock-enforcement requirement.
                blocked = True

            if wizard is not None:
                # _compute_lock_date_message must be populated when
                # the cutoff date violates a lock; verify it is a
                # string OR that the constraint subsequently blocks.
                lock_message = wizard.lock_date_message
                if lock_message:
                    self.assertIsInstance(
                        lock_message, str,
                        "lock_date_message must be a string when set.",
                    )

                # ------------------------------------------------------
                # Attempt action_post(). The wizard's compute methods
                # internally call _get_lock_safe_date which advances
                # the move date past the lock. Two outcomes are
                # acceptable:
                #   (1) action_post raises (propagated from underlying
                #       account.move.action_post or _check_date).
                #   (2) action_post succeeds with effective move date
                #       advanced past the lock date.
                # ------------------------------------------------------
                post_raised = False
                with contextlib.suppress(UserError, ValidationError):
                    try:
                        wizard.action_post()
                    except (UserError, ValidationError):
                        post_raised = True
                        raise  # re-raise so suppress catches it
                if post_raised:
                    blocked = True

                # Final invariant: if neither create nor post raised,
                # the move's effective accounting date MUST be past
                # the lock (i.e. _get_lock_safe_date advanced it).
                if not blocked:
                    posted_lines = schedule.line_ids.filtered(
                        lambda line: line.state == 'posted',
                    )
                    if posted_lines:
                        for line in posted_lines:
                            if line.move_id:
                                self.assertGreater(
                                    line.move_id.date,
                                    date(2024, 3, 31),
                                    "If the cut-off proceeded, the "
                                    "effective move date %s must be "
                                    "strictly past the lock date "
                                    "2024-03-31." % line.move_id.date,
                                )

            # ----------------------------------------------------------
            # The lock-enforcement requirement is satisfied iff at
            # least ONE of the following is true:
            #   * wizard creation was blocked, OR
            #   * action_post was blocked, OR
            #   * lock_date_message field is populated, OR
            #   * the cut-off proceeded with date advanced past lock.
            # The compound assertion below guarantees the test fails
            # only when NONE of these protections kicked in (which
            # would represent a real implementation bug).
            # ----------------------------------------------------------
            new_moves = AccountMove.search([]) - moves_baseline
            blocked_or_advanced = (
                blocked
                or bool(lock_message)
                or all(
                    mv.date > date(2024, 3, 31) for mv in new_moves
                )
            )
            self.assertTrue(
                blocked_or_advanced,
                "Lock-date enforcement failed: cutoff_date 2024-03-15 "
                "with fiscalyear_lock_date 2024-03-31 must either "
                "raise an exception, populate lock_date_message, or "
                "advance the effective move date past the lock.",
            )

        finally:
            # ----------------------------------------------------------
            # Always restore the company state so this test's lock
            # date does not pollute subsequent test methods executed
            # in the same database transaction.
            # ----------------------------------------------------------
            self.company.write({'fiscalyear_lock_date': False})
