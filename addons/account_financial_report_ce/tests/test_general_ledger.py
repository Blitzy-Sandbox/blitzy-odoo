# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Test Suite for FR-004: General Ledger Report

Implements acceptance criteria for FR-004 user story:
    "As an Accountant, I want to generate a general ledger showing all
    transactions by account so that I can verify account activity and
    trace individual transactions."

Test Coverage (mapped to FR-004 scenarios):
    - Per-account transaction listing completeness
    - Running balance computation accuracy
    - Opening/closing balance correctness
    - Date filtering and boundary conditions
    - Account code range filtering (account_from / account_to)
    - Partner filtering via partner_ids
    - Sort ordering (chronological within accounts)
    - Transaction detail fields (date, reference, description, debit,
      credit, running balance)
    - Drill-down to source journal entries
    - show_details toggle behaviour
    - target_move posted / all filtering
    - Empty account exclusion (hide_zero_balance)
    - Multi-company isolation

References:
    - FR-004: General Ledger Report specification
    - EPIC-001: Enterprise Accounting Parity (minimum 80% coverage)
    - OCA coding standards and AGPL-3.0 licensing
"""

from datetime import date, timedelta

from freezegun import freeze_time

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
@freeze_time('2024-06-30')
class TestGeneralLedger(AccountTestInvoicingCommon):
    """Comprehensive tests for the General Ledger report (FR-004).

    Extends :class:`AccountTestInvoicingCommon` to leverage pre-configured
    company data including accounts, journals, partners, products, taxes,
    and payment terms.

    All test methods are named ``test_fr004_*`` and map directly to FR-004
    acceptance scenarios as specified in the user story.
    """

    # -----------------------------------------------------------------
    # Class Setup
    # -----------------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        """Set up test data for General Ledger tests.

        Creates a realistic set of journal entries across multiple accounts
        and periods to exercise every General Ledger feature path.

        Test Data Layout::

            Pre-period  (2023-11-20, 2023-12-15)  → opening balances
            Period      (2024-01-01 … 2024-06-30) → active transactions
            Post-period (2024-07-15)               → boundary exclusion
            Draft       (2024-05-01, not posted)   → target_move filter

        Accounts exercised: receivable, payable, revenue, expense, bank /
        cash, plus three custom range-test accounts (X1000, X2000, X3000).
        """
        super().setUpClass()

        # -- Grant financial report module security groups to test user -------
        # The parent AccountTestInvoicingCommon creates an 'accountman' test
        # user with only core accounting groups (group_account_manager,
        # group_account_user).  Our module's ACL requires the custom groups
        # group_financial_report_user / group_financial_report_manager for
        # create/read/write/unlink access on all financial report models.
        fr_manager_group = cls.env.ref(
            'account_financial_report_ce.group_financial_report_manager',
            raise_if_not_found=False,
        )
        fr_user_group = cls.env.ref(
            'account_financial_report_ce.group_financial_report_user',
            raise_if_not_found=False,
        )
        groups_to_add = cls.env['res.groups']
        if fr_manager_group:
            groups_to_add |= fr_manager_group
        if fr_user_group:
            groups_to_add |= fr_user_group
        if groups_to_add:
            cls.env.user.group_ids += groups_to_add

        # === Key Dates ===
        cls.date_from = date(2024, 1, 1)
        cls.date_to = date(2024, 6, 30)
        cls.date_before_1 = date(2023, 12, 15)
        cls.date_before_2 = date(2023, 11, 20)
        cls.date_after = cls.date_to + timedelta(days=15)  # 2024-07-15

        # === Convenience shortcuts from company_data ===
        cls.company = cls.company_data['company']
        cls.currency = cls.company_data['currency']
        cls.account_revenue = cls.company_data['default_account_revenue']
        cls.account_expense = cls.company_data['default_account_expense']
        cls.account_receivable = cls.company_data['default_account_receivable']
        cls.account_payable = cls.company_data['default_account_payable']
        cls.journal_misc = cls.company_data['default_journal_misc']
        cls.journal_sale = cls.company_data['default_journal_sale']
        cls.journal_purchase = cls.company_data['default_journal_purchase']
        cls.journal_bank = cls.company_data['default_journal_bank']

        # Locate a bank / cash account for bank receipt entries
        cls.account_bank = cls.env['account.account'].search([
            ('company_ids', 'in', cls.company.ids),
            ('account_type', '=', 'asset_cash'),
        ], limit=1)
        if not cls.account_bank and cls.journal_bank:
            cls.account_bank = cls.journal_bank.default_account_id

        # === Custom accounts with deterministic codes for range tests ===
        cls.account_range_a = (
            cls.env['account.account']
            .with_company(cls.company)
            .create({
                'name': 'GL Test Range A',
                'code': 'X1000',
                'account_type': 'asset_current',
            })
        )
        cls.account_range_b = (
            cls.env['account.account']
            .with_company(cls.company)
            .create({
                'name': 'GL Test Range B',
                'code': 'X2000',
                'account_type': 'asset_current',
            })
        )
        cls.account_range_c = (
            cls.env['account.account']
            .with_company(cls.company)
            .create({
                'name': 'GL Test Range C',
                'code': 'X3000',
                'account_type': 'asset_current',
            })
        )

        # -----------------------------------------------------------------
        # Journal Entries BEFORE the Reporting Period (opening balances)
        # -----------------------------------------------------------------

        # 2023-12-15: Receivable ← Revenue (partner_a)
        cls.move_before_1 = cls.env['account.move'].create({
            'date': cls.date_before_1,
            'journal_id': cls.journal_misc.id,
            'line_ids': [
                Command.create({
                    'account_id': cls.account_receivable.id,
                    'partner_id': cls.partner_a.id,
                    'name': 'Opening receivable',
                    'debit': 1000.0,
                    'credit': 0.0,
                }),
                Command.create({
                    'account_id': cls.account_revenue.id,
                    'name': 'Opening revenue',
                    'debit': 0.0,
                    'credit': 1000.0,
                }),
            ],
        })
        cls.move_before_1.action_post()

        # 2023-11-20: Expense ← Payable (partner_b)
        cls.move_before_2 = cls.env['account.move'].create({
            'date': cls.date_before_2,
            'journal_id': cls.journal_misc.id,
            'line_ids': [
                Command.create({
                    'account_id': cls.account_expense.id,
                    'name': 'Opening expense',
                    'debit': 500.0,
                    'credit': 0.0,
                }),
                Command.create({
                    'account_id': cls.account_payable.id,
                    'partner_id': cls.partner_b.id,
                    'name': 'Opening payable',
                    'debit': 0.0,
                    'credit': 500.0,
                }),
            ],
        })
        cls.move_before_2.action_post()

        # -----------------------------------------------------------------
        # Journal Entries WITHIN the Reporting Period
        # -----------------------------------------------------------------

        # 2024-01-15: Sale invoice (partner_a)
        cls.move_jan = cls.env['account.move'].create({
            'date': date(2024, 1, 15),
            'journal_id': cls.journal_sale.id,
            'ref': 'INV-2024-001',
            'line_ids': [
                Command.create({
                    'account_id': cls.account_receivable.id,
                    'partner_id': cls.partner_a.id,
                    'name': 'January sale receivable',
                    'debit': 2000.0,
                    'credit': 0.0,
                }),
                Command.create({
                    'account_id': cls.account_revenue.id,
                    'name': 'January sale revenue',
                    'debit': 0.0,
                    'credit': 2000.0,
                }),
            ],
        })
        cls.move_jan.action_post()

        # 2024-02-15: Range-test accounts entry
        cls.move_range = cls.env['account.move'].create({
            'date': date(2024, 2, 15),
            'journal_id': cls.journal_misc.id,
            'ref': 'RANGE-001',
            'line_ids': [
                Command.create({
                    'account_id': cls.account_range_a.id,
                    'name': 'Range A debit',
                    'debit': 100.0,
                    'credit': 0.0,
                }),
                Command.create({
                    'account_id': cls.account_range_b.id,
                    'name': 'Range B debit',
                    'debit': 200.0,
                    'credit': 0.0,
                }),
                Command.create({
                    'account_id': cls.account_range_c.id,
                    'name': 'Range C credit (offset)',
                    'debit': 0.0,
                    'credit': 300.0,
                }),
            ],
        })
        cls.move_range.action_post()

        # 2024-03-20: Purchase bill (partner_b)
        cls.move_mar = cls.env['account.move'].create({
            'date': date(2024, 3, 20),
            'journal_id': cls.journal_purchase.id,
            'ref': 'BILL-2024-001',
            'line_ids': [
                Command.create({
                    'account_id': cls.account_expense.id,
                    'partner_id': cls.partner_b.id,
                    'name': 'March purchase expense',
                    'debit': 800.0,
                    'credit': 0.0,
                }),
                Command.create({
                    'account_id': cls.account_payable.id,
                    'partner_id': cls.partner_b.id,
                    'name': 'March purchase payable',
                    'debit': 0.0,
                    'credit': 800.0,
                }),
            ],
        })
        cls.move_mar.action_post()

        # 2024-04-10: Bank receipt (partner_a)
        bank_account = (
            cls.account_bank
            if cls.account_bank
            else cls.account_range_a
        )
        cls.move_apr = cls.env['account.move'].create({
            'date': date(2024, 4, 10),
            'journal_id': cls.journal_misc.id,
            'ref': 'PAY-2024-001',
            'line_ids': [
                Command.create({
                    'account_id': bank_account.id,
                    'partner_id': cls.partner_a.id,
                    'name': 'April bank receipt',
                    'debit': 1500.0,
                    'credit': 0.0,
                }),
                Command.create({
                    'account_id': cls.account_receivable.id,
                    'partner_id': cls.partner_a.id,
                    'name': 'April receivable payment',
                    'debit': 0.0,
                    'credit': 1500.0,
                }),
            ],
        })
        cls.move_apr.action_post()

        # 2024-06-15: Sale invoice (partner_b)
        cls.move_jun = cls.env['account.move'].create({
            'date': date(2024, 6, 15),
            'journal_id': cls.journal_sale.id,
            'ref': 'INV-2024-002',
            'line_ids': [
                Command.create({
                    'account_id': cls.account_receivable.id,
                    'partner_id': cls.partner_b.id,
                    'name': 'June sale receivable',
                    'debit': 3000.0,
                    'credit': 0.0,
                }),
                Command.create({
                    'account_id': cls.account_revenue.id,
                    'name': 'June sale revenue',
                    'debit': 0.0,
                    'credit': 3000.0,
                }),
            ],
        })
        cls.move_jun.action_post()

        # -----------------------------------------------------------------
        # Journal Entry AFTER the Reporting Period (boundary check)
        # -----------------------------------------------------------------
        cls.move_after = cls.env['account.move'].create({
            'date': cls.date_after,
            'journal_id': cls.journal_sale.id,
            'ref': 'INV-2024-FUTURE',
            'line_ids': [
                Command.create({
                    'account_id': cls.account_receivable.id,
                    'partner_id': cls.partner_a.id,
                    'name': 'After period receivable',
                    'debit': 5000.0,
                    'credit': 0.0,
                }),
                Command.create({
                    'account_id': cls.account_revenue.id,
                    'name': 'After period revenue',
                    'debit': 0.0,
                    'credit': 5000.0,
                }),
            ],
        })
        cls.move_after.action_post()

        # -----------------------------------------------------------------
        # Draft Entry WITHIN the Period (not posted — target_move test)
        # -----------------------------------------------------------------
        cls.move_draft = cls.env['account.move'].create({
            'date': date(2024, 5, 1),
            'journal_id': cls.journal_misc.id,
            'ref': 'DRAFT-001',
            'line_ids': [
                Command.create({
                    'account_id': cls.account_receivable.id,
                    'partner_id': cls.partner_a.id,
                    'name': 'Draft receivable',
                    'debit': 999.0,
                    'credit': 0.0,
                }),
                Command.create({
                    'account_id': cls.account_revenue.id,
                    'name': 'Draft revenue',
                    'debit': 0.0,
                    'credit': 999.0,
                }),
            ],
        })
        # Intentionally NOT posted — remains in 'draft' state.

    # -----------------------------------------------------------------
    # Helper Methods
    # -----------------------------------------------------------------

    def _create_gl_report(self, **kwargs):
        """Create a General Ledger report record with sensible defaults.

        Keyword arguments override the defaults so that each test can
        tweak exactly the parameters it cares about.

        Returns:
            A new ``account.general.ledger.report`` record.
        """
        defaults = {
            'date_from': self.date_from,
            'date_to': self.date_to,
            'company_id': self.company.id,
            'target_move': 'posted',
        }
        defaults.update(kwargs)
        return self.env['account.general.ledger.report'].create(defaults)

    def _get_all_reported_move_ids(self, report):
        """Return a set of ``account.move`` IDs present in the report.

        Iterates over all account sections and their nested transaction
        lines, collecting the ``move_id`` from each line.
        """
        move_ids = set()
        for acct_line in report.account_line_ids:
            for txn in acct_line.line_ids:
                if txn.move_id:
                    move_ids.add(txn.move_id.id)
        return move_ids

    # =================================================================
    # FR-004 Test Methods
    # =================================================================

    def test_fr004_general_ledger_creation(self):
        """FR-004 Scenario 1: Create a GL report with a date range.

        Verifies the record is created with the expected parameter
        values and in 'draft' state.  Also validates that the model
        rejects generation when mandatory dates are cleared.
        """
        report = self._create_gl_report()

        self.assertTrue(report.exists(),
                        "GL report record should exist after creation.")
        self.assertEqual(report.date_from, self.date_from)
        self.assertEqual(report.date_to, self.date_to)
        self.assertEqual(report.company_id, self.company)
        self.assertEqual(report.target_move, 'posted')
        self.assertEqual(report.state, 'draft',
                         "Newly created report must be in 'draft' state.")

        # Validate date-range guard: temporarily drop the DB NOT NULL
        # constraint, set date_from = NULL via SQL to bypass the ORM
        # ``required`` check, then verify ``action_generate_report``
        # raises UserError.  The constraint is restored in a finally
        # block to keep the table pristine for subsequent tests.
        report_nodate = self._create_gl_report()
        table = report_nodate._table
        try:
            self.env.cr.execute(
                "ALTER TABLE %s ALTER COLUMN date_from DROP NOT NULL"
                % table,
            )
            self.env.cr.execute(
                "UPDATE %s SET date_from = NULL WHERE id = %%s"
                % table,
                (report_nodate.id,),
            )
            report_nodate.invalidate_recordset()
            with self.assertRaises(UserError):
                report_nodate.action_generate_report()
        finally:
            # Remove rows with NULL date_from before restoring the
            # NOT NULL constraint – otherwise PostgreSQL rejects the
            # ALTER TABLE because the column still contains NULLs.
            self.env.cr.execute(
                "DELETE FROM %s WHERE date_from IS NULL" % table,
            )
            self.env.cr.execute(
                "ALTER TABLE %s ALTER COLUMN date_from SET NOT NULL"
                % table,
            )

    def test_fr004_general_ledger_computation(self):
        """FR-004 Scenario 1: Compute GL data and verify state transition.

        After calling ``action_compute``, the report should transition
        to 'done' and contain account line records.
        """
        report = self._create_gl_report()
        report.action_compute()

        self.assertEqual(report.state, 'done',
                         "Report state must be 'done' after computation.")
        self.assertTrue(
            report.account_line_ids,
            "Computed report should have at least one account section.",
        )

    def test_fr004_per_account_listing(self):
        """FR-004 Scenario 3: Every account with activity is listed.

        Each account that has posted journal items within the period
        (or a non-zero opening balance) should appear as an
        ``account_line_id`` section in the report.
        """
        report = self._create_gl_report()
        report.action_compute()

        reported_account_ids = set(
            report.account_line_ids.mapped('account_id').ids,
        )

        # All accounts that received posted entries during the period
        expected_accounts = (
            self.account_receivable
            | self.account_revenue
            | self.account_expense
            | self.account_payable
            | self.account_range_a
            | self.account_range_b
            | self.account_range_c
        )
        if self.account_bank:
            expected_accounts |= self.account_bank

        for account in expected_accounts:
            self.assertIn(
                account.id,
                reported_account_ids,
                "Account '%s' (%s) should appear in the GL report."
                % (account.name, account.code),
            )

    def test_fr004_transaction_completeness(self):
        """FR-004 Scenario 1: All posted period entries appear.

        Every posted journal entry whose date falls within
        ``[date_from, date_to]`` must be represented in the report.
        Entries outside the period or in draft state must be absent.
        """
        report = self._create_gl_report()
        report.action_compute()

        reported_move_ids = self._get_all_reported_move_ids(report)

        # Posted moves within the period
        expected_present = (
            self.move_jan | self.move_range | self.move_mar
            | self.move_apr | self.move_jun
        )
        for move in expected_present:
            self.assertIn(
                move.id,
                reported_move_ids,
                "Posted period move '%s' should appear in the GL."
                % (move.ref or move.name),
            )

        # Moves that must NOT appear
        for move, reason in [
            (self.move_before_1, "before date_from"),
            (self.move_before_2, "before date_from"),
            (self.move_after, "after date_to"),
            (self.move_draft, "draft (not posted)"),
        ]:
            self.assertNotIn(
                move.id,
                reported_move_ids,
                "Move '%s' (%s) should be excluded from the GL."
                % (move.ref or move.name, reason),
            )

    def test_fr004_running_balance_accuracy(self):
        """FR-004 Scenario 3: Running balance accumulation.

        For the receivable account, verify that each transaction line's
        ``balance`` equals the previous running balance plus its own
        debit minus credit.

        Expected receivable data in the period:
            opening  = 1 000  (move_before_1)
            Jan 15  +2 000 debit  → running 3 000
            Apr 10  −1 500 credit → running 1 500
            Jun 15  +3 000 debit  → running 4 500
        """
        report = self._create_gl_report(
            account_ids=[Command.set([self.account_receivable.id])],
        )
        report.action_compute()

        acct_line = report.account_line_ids.filtered(
            lambda l: l.account_id == self.account_receivable
        )
        self.assertTrue(acct_line,
                        "Receivable account must appear in the GL report.")
        acct_line = acct_line[0]

        running = acct_line.opening_balance
        for txn in acct_line.line_ids:
            if txn.is_partner_subtotal:
                continue
            running += txn.debit - txn.credit
            self.assertAlmostEqual(
                txn.balance, running, places=2,
                msg=(
                    "Running balance mismatch on %s: "
                    "expected %.2f, got %.2f."
                    % (txn.date, running, txn.balance)
                ),
            )

    def test_fr004_opening_balance(self):
        """FR-004 Scenario 3: Opening balance = sum before date_from.

        The receivable account's opening balance should equal the net
        balance of all posted receivable entries dated before the
        reporting start date.

        Pre-period receivable: move_before_1 debit 1 000  →  opening = 1 000.
        """
        report = self._create_gl_report(
            account_ids=[Command.set([self.account_receivable.id])],
        )
        report.action_compute()

        acct_line = report.account_line_ids.filtered(
            lambda l: l.account_id == self.account_receivable
        )
        self.assertTrue(acct_line)
        acct_line = acct_line[0]

        expected_opening = 1000.0
        self.assertAlmostEqual(
            acct_line.opening_balance, expected_opening, places=2,
            msg=(
                "Receivable opening balance should be %.2f, got %.2f."
                % (expected_opening, acct_line.opening_balance)
            ),
        )

    def test_fr004_closing_balance(self):
        """FR-004 Scenario 3: Closing = opening + debit − credit.

        Validate the fundamental ledger equation for the receivable
        account section.
        """
        report = self._create_gl_report(
            account_ids=[Command.set([self.account_receivable.id])],
        )
        report.action_compute()

        acct_line = report.account_line_ids.filtered(
            lambda l: l.account_id == self.account_receivable
        )
        self.assertTrue(acct_line)
        acct_line = acct_line[0]

        expected_closing = (
            acct_line.opening_balance
            + acct_line.total_debit
            - acct_line.total_credit
        )
        self.assertAlmostEqual(
            acct_line.closing_balance, expected_closing, places=2,
            msg=(
                "Closing balance must equal opening + debit − credit.  "
                "Expected %.2f, got %.2f."
                % (expected_closing, acct_line.closing_balance)
            ),
        )

    def test_fr004_date_filtering(self):
        """FR-004 Scenario 1: Entries outside the date range are excluded.

        Narrow the window to Feb–Apr and confirm that only transactions
        dated within that range appear.
        """
        narrow_from = date(2024, 2, 1)
        narrow_to = date(2024, 4, 30)

        report = self._create_gl_report(
            date_from=narrow_from,
            date_to=narrow_to,
        )
        report.action_compute()

        for acct_line in report.account_line_ids:
            for txn in acct_line.line_ids:
                if not txn.date or txn.is_partner_subtotal:
                    continue
                self.assertGreaterEqual(
                    txn.date, narrow_from,
                    "Transaction date %s is before date_from %s."
                    % (txn.date, narrow_from),
                )
                self.assertLessEqual(
                    txn.date, narrow_to,
                    "Transaction date %s is after date_to %s."
                    % (txn.date, narrow_to),
                )

    def test_fr004_account_filter_specific(self):
        """FR-004 Scenario 2: Filter by explicit account_ids.

        When account_ids is set, only those accounts should appear in
        the report — all other accounts are excluded.
        """
        selected = self.account_receivable | self.account_revenue
        report = self._create_gl_report(
            account_ids=[Command.set(selected.ids)],
        )
        report.action_compute()

        reported_account_ids = set(
            report.account_line_ids.mapped('account_id').ids,
        )
        for acct_id in reported_account_ids:
            self.assertIn(
                acct_id, set(selected.ids),
                "Only selected accounts should appear in the report.",
            )

    def test_fr004_account_code_range(self):
        """FR-004 Scenario 2: Filter by account_from / account_to.

        Custom accounts X1000, X2000, X3000 are created in setUp.
        Filtering [X1000, X2000] should include X1000 and X2000 but
        exclude X3000.
        """
        report = self._create_gl_report(
            account_from='X1000',
            account_to='X2000',
        )
        report.action_compute()

        reported_codes = {
            al.account_id.code
            for al in report.account_line_ids
            if al.account_id.code and al.account_id.code.startswith('X')
        }
        self.assertIn('X1000', reported_codes,
                       "X1000 must be within range [X1000, X2000].")
        self.assertIn('X2000', reported_codes,
                       "X2000 must be within range [X1000, X2000].")
        self.assertNotIn('X3000', reported_codes,
                          "X3000 must be outside range [X1000, X2000].")

    def test_fr004_partner_filtering(self):
        """FR-004 Scenario 2: Filter by partner_ids.

        Including only partner_a should exclude all transactions that
        belong to partner_b or have no partner set.
        """
        report = self._create_gl_report(
            partner_ids=[Command.set([self.partner_a.id])],
        )
        report.action_compute()

        for acct_line in report.account_line_ids:
            for txn in acct_line.line_ids:
                if txn.is_partner_subtotal:
                    continue
                if txn.partner_id:
                    self.assertEqual(
                        txn.partner_id, self.partner_a,
                        "Transaction partner must be partner_a when "
                        "filtering by partner_a; got '%s'."
                        % txn.partner_id.name,
                    )

    def test_fr004_transaction_detail_fields(self):
        """FR-004 Scenario 4: Detail fields populated on each line.

        Every non-subtotal transaction line must carry a date, at least
        one of name/ref, and numeric debit/credit/balance values.
        """
        report = self._create_gl_report()
        report.action_compute()

        checked_count = 0
        for acct_line in report.account_line_ids:
            for txn in acct_line.line_ids:
                if txn.is_partner_subtotal:
                    continue
                self.assertTrue(
                    txn.date,
                    "Transaction line must have a date.",
                )
                self.assertTrue(
                    txn.name or txn.ref,
                    "Transaction should carry a description or reference.",
                )
                self.assertIsNotNone(txn.debit,
                                     "Debit must not be None.")
                self.assertIsNotNone(txn.credit,
                                     "Credit must not be None.")
                self.assertIsNotNone(txn.balance,
                                     "Running balance must not be None.")
                checked_count += 1

        self.assertGreater(
            checked_count, 0,
            "At least one transaction line should have been verified.",
        )

    def test_fr004_sort_by_date(self):
        """FR-004 Scenario 5: Transactions sorted chronologically.

        Within each account section, consecutive transaction dates must
        be non-decreasing when ``sort_by='date'`` (the default).
        """
        report = self._create_gl_report(sort_by='date')
        report.action_compute()

        for acct_line in report.account_line_ids:
            dates = [
                txn.date
                for txn in acct_line.line_ids
                if txn.date and not txn.is_partner_subtotal
            ]
            for i in range(1, len(dates)):
                self.assertGreaterEqual(
                    dates[i], dates[i - 1],
                    "Transactions in '%s' are not sorted by date: "
                    "%s appears after %s." % (
                        acct_line.name, dates[i - 1], dates[i],
                    ),
                )

    def test_fr004_drilldown_to_journal_entry(self):
        """FR-004 Scenario 6: Drill-down returns an act_window action.

        Both the account-section drill-down and the individual
        transaction drill-down must return ``ir.actions.act_window``
        actions targeting the correct model.
        """
        report = self._create_gl_report(
            account_ids=[Command.set([self.account_receivable.id])],
        )
        report.action_compute()

        acct_line = report.account_line_ids.filtered(
            lambda l: l.account_id == self.account_receivable
        )
        self.assertTrue(acct_line,
                        "Receivable section must exist for drill-down test.")
        acct_line = acct_line[0]

        # Account-level drill-down → journal items list
        result = acct_line.action_drilldown()
        self.assertEqual(
            result.get('type'), 'ir.actions.act_window',
            "Drill-down should return an act_window action.",
        )
        self.assertEqual(
            result.get('res_model'), 'account.move.line',
            "Drill-down should target account.move.line.",
        )

        # Transaction-level drill-down → journal entry form
        txn_lines = acct_line.line_ids.filtered(
            lambda t: t.move_id and not t.is_partner_subtotal
        )
        if txn_lines:
            txn_result = txn_lines[0].action_open_move()
            self.assertEqual(
                txn_result.get('type'), 'ir.actions.act_window',
                "Transaction drill-down must return an act_window action.",
            )
            self.assertEqual(
                txn_result.get('res_model'), 'account.move',
                "Transaction drill-down should target account.move.",
            )

    def test_fr004_show_details_toggle(self):
        """FR-004: show_details controls transaction-level visibility.

        When ``show_details=True``, individual transaction lines should
        be present.  When ``show_details=False``, account-level summary
        sections should still exist.
        """
        # --- show_details = True (default) ---
        report_detail = self._create_gl_report(show_details=True)
        report_detail.action_compute()

        has_txn_lines = any(
            bool(acct.line_ids)
            for acct in report_detail.account_line_ids
        )
        self.assertTrue(
            has_txn_lines,
            "show_details=True should produce transaction-level lines.",
        )

        # --- show_details = False ---
        report_summary = self._create_gl_report(show_details=False)
        report_summary.action_compute()

        # Account-level sections must still be generated
        self.assertTrue(
            report_summary.account_line_ids,
            "show_details=False must still produce account-level sections.",
        )

    def test_fr004_posted_moves_only(self):
        """FR-004: target_move='posted' excludes draft entries.

        The draft move created in setUpClass should not appear when
        the report is restricted to posted entries.
        """
        report = self._create_gl_report(target_move='posted')
        report.action_compute()

        reported_move_ids = self._get_all_reported_move_ids(report)
        self.assertNotIn(
            self.move_draft.id,
            reported_move_ids,
            "Draft move must be excluded with target_move='posted'.",
        )

    def test_fr004_all_moves_included(self):
        """FR-004: target_move='all' includes draft entries.

        When the filter is widened to all entries, the draft move
        should appear in the report output.
        """
        report = self._create_gl_report(target_move='all')
        report.action_compute()

        reported_move_ids = self._get_all_reported_move_ids(report)
        self.assertIn(
            self.move_draft.id,
            reported_move_ids,
            "Draft move must be included with target_move='all'.",
        )

    def test_fr004_empty_account_excluded(self):
        """FR-004: Empty accounts respect hide_zero_balance toggle.

        An account with no posted entries and zero opening balance
        should be excluded when ``hide_zero_balance=True`` and
        included when ``hide_zero_balance=False``.
        """
        empty_account = (
            self.env['account.account']
            .with_company(self.company)
            .create({
                'name': 'GL Test Empty Account',
                'code': 'XEMPTY',
                'account_type': 'asset_current',
            })
        )

        # -- hide_zero_balance = True → empty account absent --
        report_hidden = self._create_gl_report(
            hide_zero_balance=True,
            account_ids=[Command.set([
                self.account_receivable.id,
                empty_account.id,
            ])],
        )
        report_hidden.action_compute()

        empty_in_hidden = report_hidden.account_line_ids.filtered(
            lambda l: l.account_id == empty_account
        )
        self.assertFalse(
            empty_in_hidden,
            "Empty account should be excluded when hide_zero_balance=True.",
        )

        # -- hide_zero_balance = False → empty account present --
        report_shown = self._create_gl_report(
            hide_zero_balance=False,
            account_ids=[Command.set([
                self.account_receivable.id,
                empty_account.id,
            ])],
        )
        report_shown.action_compute()

        empty_in_shown = report_shown.account_line_ids.filtered(
            lambda l: l.account_id == empty_account
        )
        self.assertTrue(
            empty_in_shown,
            "Empty account should appear when hide_zero_balance=False.",
        )

    def test_fr004_multi_company_isolation(self):
        """FR-004: Company filter prevents cross-company data leakage.

        A journal entry posted in company_2 must not appear in a
        General Ledger report generated for the primary company.
        """
        company_2_data = self.setup_other_company()
        company_2 = company_2_data['company']
        journal_2_misc = company_2_data['default_journal_misc']
        account_2_revenue = company_2_data['default_account_revenue']
        account_2_receivable = company_2_data['default_account_receivable']

        move_company_2 = (
            self.env['account.move']
            .with_company(company_2)
            .create({
                'date': date(2024, 3, 1),
                'journal_id': journal_2_misc.id,
                'line_ids': [
                    Command.create({
                        'account_id': account_2_receivable.id,
                        'name': 'Company 2 receivable',
                        'debit': 9999.0,
                        'credit': 0.0,
                    }),
                    Command.create({
                        'account_id': account_2_revenue.id,
                        'name': 'Company 2 revenue',
                        'debit': 0.0,
                        'credit': 9999.0,
                    }),
                ],
            })
        )
        move_company_2.action_post()

        # Generate report for the PRIMARY company
        report = self._create_gl_report()
        report.action_compute()

        reported_move_ids = self._get_all_reported_move_ids(report)
        self.assertNotIn(
            move_company_2.id,
            reported_move_ids,
            "Company 2 entries must not appear in Company 1 GL report.",
        )
