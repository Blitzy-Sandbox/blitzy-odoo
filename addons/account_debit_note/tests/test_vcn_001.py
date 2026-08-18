# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""Acceptance tests for STORY-001-02-05 -- vendor credit notes raised from a posted vendor bill.

This suite covers Scenario 1 of that story -- the returned line reverses as one
balanced credit note debiting Accounts Payable 2000 and crediting Expense 6100 --
together with the amount-validation portion of Scenario 4, which refuses a linked
vendor credit note that carries no value.  The story's allocation, tax reversal,
cash refund and lock-date behaviour are deliberately not exercised here; they are
out of scope for this change and no test below asserts anything about them.

    T-VCN-001-01  Vendor credit note reverses one bill line as one balanced entry
    T-VCN-001-02  Zero-value credit note refused, no entry created
    T-VCN-001-03  Negative-value credit note refused, no entry created
    T-VCN-001-04  Credit note posts in the bill currency with HALF-UP rounding
    T-VCN-001-05  Credit note sequence distinct from a plain unlinked refund
    T-VCN-001-06  Default vendor-bill path remains a debit note

Each test method's docstring begins with its BDD identifier so that the Odoo test
runner prints the scenario-to-method mapping in its log; a failing line is then
traceable back to the story criterion it came from without opening this file.

``@tagged('post_install', '-at_install')`` is used because every test below
instantiates the ``account.debit.note`` wizard and reads its
``create_vendor_credit_note`` opt-in.  The field, the wizard form that exposes it
and the wizard's access rights only exist in the registry once
``account_debit_note`` has finished installing, so the class must run after the
install phase rather than during it.
"""

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon

# ---------------------------------------------------------------------------
# Story fixture figures.  Kept as module constants so that a figure is stated
# once and every assertion below follows it.
# ---------------------------------------------------------------------------

# Account codes the story names.  Both are asserted by code rather than by name
# or id, which is what makes an assertion readable against the chart itself.
CODE_ACCOUNTS_PAYABLE = '2000'
CODE_EXPENSE = '6100'

# The three untaxed lines of the archetype bill.  Line 2 -- the software
# subscription -- is the returned line the credit note reverses.
LINE_ADVISORY = 'Advisory services'
LINE_SUBSCRIPTION = 'Software subscription'
LINE_FREIGHT = 'Freight and handling'

AMOUNT_ADVISORY = 6000.0
AMOUNT_SUBSCRIPTION = 4200.0
AMOUNT_FREIGHT = 2250.0
AMOUNT_BILL_TOTAL = 12450.0

STORY_BILL_LINES = (
    (LINE_ADVISORY, AMOUNT_ADVISORY, 1.0),
    (LINE_SUBSCRIPTION, AMOUNT_SUBSCRIPTION, 1.0),
    (LINE_FREIGHT, AMOUNT_FREIGHT, 1.0),
)

# Dates.  The bill date, the credit-note date and the date of the unlinked
# refund all sit inside March 2025 so that the credit note and the plain refund
# of T-VCN-001-05 compete for the same monthly sequence range.
BILL_DATE = '2025-03-14'
CREDIT_NOTE_DATE = '2025-03-20'
PLAIN_REFUND_DATE = '2025-03-25'

CREDIT_NOTE_REFERENCE = 'CN-2024-0117'
CREDIT_NOTE_REASON = f'Vendor credit note {CREDIT_NOTE_REFERENCE}'

# T-VCN-001-04 -- an alternate currency whose rounding increment is 0.05 rather
# than the usual 0.01.  quantity 2.5 x unit price 4.01 keeps the line amount at
# exactly 10.025 before rounding, which is a tie at a 0.05 increment; HALF-UP
# takes a tie away from zero, so the posted amount must be 10.05.
ROUNDING_INCREMENT = 0.05
ROUNDING_QUANTITY = 2.5
ROUNDING_UNIT_PRICE = 4.01
ROUNDING_LINE_AMOUNT = 10.025
ROUNDING_EXPECTED_TOTAL = 10.05

# T-VCN-001-05 -- the amount of the ordinary, unlinked vendor credit note that
# competes with the linked one for the journal's refund sequence.
AMOUNT_PLAIN_REFUND = 1000.0


@tagged('post_install', '-at_install')
class TestVendorCreditNote(AccountTestInvoicingCommon):
    """STORY-001-02-05 -- Manage Vendor Credit Notes and Refunds.

    Story: ``tickets/EPIC-001/FEATURE-001-02/STORY-001-02-05-manage-vendor-credit-notes.md``.

    The suite builds on ``AccountTestInvoicingCommon``, which supplies the test
    company, its chart of accounts, its Purchase journal and the invoice factory
    helpers used below.  On top of that it seeds only what the story names and the
    generic chart does not provide in the shape it names: Accounts Payable 2000,
    Expense 6100 and the vendor whose payable property points at 2000.

    Test method naming convention: ``test_vcn_001_<NN>_<snake_summary>``, where
    ``<NN>`` is the BDD scenario number zero-padded to two digits and
    ``<snake_summary>`` is a snake_case summary of the outcome asserted.

    Every monetary assertion is made through ``res.currency.compare_amounts`` or
    ``res.currency.is_zero`` rather than through raw float equality, so that each
    comparison happens at the rounding increment of the currency the amount is
    denominated in.  ``compare_amounts`` is used for "these two amounts are
    equal" and ``is_zero`` for "this difference is zero", because rounding before
    the subtraction and rounding after it are not the same test.

    Branch-to-test mapping
    ----------------------
    The branches this change adds, and the tests that reach each of them:

        * ``account.debit.note._prepare_default_values``
          -- the opt-in branch, ``create_vendor_credit_note`` true and the source
             ``move_type == 'in_invoice'``, producing ``in_refund``
             -> test_vcn_001_01 / 04 / 05
          -- the falsy path, where the same source still produces the shipped
             ``in_invoice`` debit note
             -> test_vcn_001_06

        * ``account.move._check_vendor_credit_note_positive_total``
          -- the raising path, a linked ``in_refund`` whose currency-rounded
             total is not above zero
             -> test_vcn_001_02 (zero) / 03 (negative)
          -- the passing path, a linked ``in_refund`` with a positive total
             -> test_vcn_001_01 / 04 / 05

        * ``account.move._post`` override
          -- delegation to ``super()._post(soft=soft)`` after the guard passes
             -> test_vcn_001_01 / 04 / 05
          -- refusal raised before ``super()._post`` is ever entered
             -> test_vcn_001_02 / 03

        * ``account.move._get_last_sequence_domain``
          -- the ``in_refund`` path, now excluded from the debit-note domain
             split so that linked and unlinked refunds share one refund pool
             -> test_vcn_001_05
          -- the retained invoice-type path, where a vendor-bill debit note
             still receives its own domain
             -> test_vcn_001_06 (and the module's existing suite)
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.company_currency = cls.company_data['currency']
        cls.purchase_journal = cls.company_data['default_journal_purchase']

        # Accounts Payable 2000 and Expense 6100.  The generic chart of accounts
        # loaded by this test company offers neither in the shape the story
        # names: its payable is 2110, and 6100 exists under another name.
        cls.account_payable_2000 = cls._vcn_account(
            code=CODE_ACCOUNTS_PAYABLE,
            name='Accounts Payable',
            account_type='liability_payable',
            reconcile=True,
        )
        cls.account_expense_6100 = cls._vcn_account(
            code=CODE_EXPENSE,
            name='Expense',
            account_type='expense',
            reconcile=False,
        )

        # The vendor of the archetype bill.  Its payable property is what puts
        # the bill's and the credit note's payable line on 2000 rather than on
        # the chart's own payable account.
        cls.vendor = cls.env['res.partner'].create({
            'name': 'Acme Industrial Supplies',
            'invoice_sending_method': 'manual',
            'invoice_edi_format': False,
            'company_id': False,
        })
        cls.vendor.with_company(cls.env.company).write({
            'property_account_payable_id': cls.account_payable_2000.id,
            'property_account_receivable_id': cls.company_data['default_account_receivable'].id,
        })

    # -------------------------------------------------------------------------
    # Fixtures
    # -------------------------------------------------------------------------

    @classmethod
    def _vcn_account(cls, code, name, account_type, reconcile):
        """Return the account carrying ``code`` in the test company, creating it if absent.

        An ``account.account`` code is unique per company and is stored as a
        company-dependent value, so the lookup is scoped to the company before
        anything is written.  A code that already exists is reused and only
        renamed -- creating a second record on an existing code is refused
        outright -- while a code the chart does not carry is created in full.
        Written this way the fixture holds whichever chart template the test
        company happens to load.
        """
        company = cls.env.company
        AccountAccount = cls.env['account.account'].with_company(company)
        account = AccountAccount.search(
            [
                *AccountAccount._check_company_domain(company),
                ('code', '=', code),
            ],
            limit=1,
        )
        if account:
            account.name = name
            if account.account_type != account_type:
                account.account_type = account_type
            # Only ever turn reconciliation on, and only where the story
            # requires it: the expense account plays no part in reconciliation
            # and flipping its flag would be a change nothing here asks for.
            if reconcile and not account.reconcile:
                account.reconcile = True
            return account
        return AccountAccount.create({
            'name': name,
            'code': code,
            'account_type': account_type,
            'reconcile': reconcile,
            'company_ids': [Command.set(company.ids)],
        })

    def _create_story_bill(self, lines=None, currency=None, invoice_date=BILL_DATE):
        """Create and post the story's vendor bill, and return it.

        The bill is a posted ``in_invoice`` in the company's Purchase journal for
        the story's vendor, carrying untaxed lines coded to Expense 6100 and a
        single payable line on Accounts Payable 2000.  ``lines`` is a sequence of
        ``(name, price_unit, quantity)`` tuples and defaults to the story's three
        lines of 6,000.00, 4,200.00 and 2,250.00.

        Taxes are cleared explicitly on every line: ``account.move.line.tax_ids``
        is a computed field that only recomputes on a product change, so an
        empty value given at creation keeps the line untaxed for good.  Scenario
        1 of the story is the untaxed reversal; the taxed one is Scenario 2 and
        is out of scope here.
        """
        is_story_fixture = lines is None
        bill_lines = STORY_BILL_LINES if is_story_fixture else lines
        bill = self._create_invoice(
            move_type='in_invoice',
            invoice_date=fields.Date.from_string(invoice_date),
            date=fields.Date.from_string(invoice_date),
            post=True,
            partner_id=self.vendor,
            journal_id=self.purchase_journal,
            currency_id=currency or self.company_currency,
            invoice_line_ids=[
                self._prepare_invoice_line(
                    name=name,
                    price_unit=price_unit,
                    quantity=quantity,
                    tax_ids=[],
                    account_id=self.account_expense_6100,
                )
                for name, price_unit, quantity in bill_lines
            ],
        )

        # Fixture sanity: the Given of every scenario below depends on each of
        # these, so they are asserted here once rather than restated per test.
        self.assertEqual(bill.move_type, 'in_invoice', "The fixture must be a vendor bill, which is the only source the vendor-credit-note opt-in accepts.")
        self.assertEqual(bill.state, 'posted', "The fixture bill must be posted: the Debit Note wizard refuses any source that is not posted.")
        self.assertEqual(bill.journal_id, self.purchase_journal, "The fixture bill must sit in the company's Purchase journal, which is the journal the credit note is asserted to reuse.")
        self.assertEqual(
            set(bill.invoice_line_ids.mapped('account_id.code')),
            {CODE_EXPENSE},
            f"Every product line of the fixture bill must be coded to Expense {CODE_EXPENSE}, which is the account the credit note gives the charge back to.",
        )
        payable_lines = bill.line_ids.filtered(lambda line: line.display_type == 'payment_term')
        self.assertEqual(len(payable_lines), 1, "The fixture bill must carry exactly one payable line, which is the obligation the credit note reduces.")
        self.assertEqual(
            payable_lines.account_id.code,
            CODE_ACCOUNTS_PAYABLE,
            f"The fixture bill's payable line must sit on Accounts Payable {CODE_ACCOUNTS_PAYABLE}, not on the chart's own payable account.",
        )
        self.assertTrue(
            bill.currency_id.is_zero(bill.amount_tax),
            f"The fixture bill must be untaxed: Scenario 1 reverses an untaxed line, but its tax amount reads {bill.amount_tax} {bill.currency_id.name}.",
        )
        expected_total = sum(bill.invoice_line_ids.mapped('price_subtotal'))
        self.assertEqual(
            bill.currency_id.compare_amounts(bill.amount_total, expected_total),
            0,
            f"The fixture bill's total of {bill.amount_total} {bill.currency_id.name} must equal the sum of its untaxed lines, {expected_total} {bill.currency_id.name}.",
        )
        if is_story_fixture:
            self.assertEqual(
                bill.currency_id.compare_amounts(bill.amount_total, AMOUNT_BILL_TOTAL),
                0,
                f"The story's bill totals {AMOUNT_BILL_TOTAL:.2f} across its three lines, but the fixture reads {bill.amount_total} {bill.currency_id.name}.",
            )
        return bill

    def _create_vendor_credit_note(self, bill, keep_line=LINE_SUBSCRIPTION, reason=CREDIT_NOTE_REASON, date=CREDIT_NOTE_DATE):
        """Raise a draft, linked vendor credit note from ``bill`` and return it.

        The shipped Debit Note wizard is opened the way the module's own suite
        opens it -- through the ``active_model``/``active_ids`` context that the
        Debit Note action supplies -- with the ``create_vendor_credit_note``
        opt-in set, so the copy comes out as an ``in_refund`` rather than as the
        vendor debit note the same wizard produces by default.

        ``copy_lines`` brings across every line of the bill rather than only the
        credited one, so the copy is trimmed down to the line named
        ``keep_line``: the story credits line 2 of the bill alone.  Pass
        ``keep_line=False`` to keep the copy exactly as the wizard produced it.

        The result is located through ``debit_origin_id`` -- the module's source
        link -- and ``ensure_one`` proves that raising a credit note produced
        exactly one linked move.
        """
        wizard = self.env['account.debit.note'].with_context(
            active_model='account.move',
            active_ids=bill.ids,
        ).create({
            'date': fields.Date.from_string(date),
            'reason': reason,
            'copy_lines': True,
            'create_vendor_credit_note': True,
        })
        wizard.create_debit()

        credit_note = self.env['account.move'].search([('debit_origin_id', '=', bill.id)])
        credit_note.ensure_one()
        if keep_line:
            credit_note.invoice_line_ids.filtered(lambda line: line.name != keep_line).unlink()
        return credit_note

    def _posted_movement(self, account, partner):
        """Return the signed posted balance ``partner`` carries on ``account``.

        Only journal items whose move is posted are counted, so a draft or a
        refused document contributes nothing.  A vendor obligation sits on the
        credit side, so the returned figure is negative while money is owed.
        """
        lines = self.env['account.move.line'].search([
            ('account_id', '=', account.id),
            ('partner_id', '=', partner.id),
            ('parent_state', '=', 'posted'),
        ])
        return sum(lines.mapped('balance'))

    def _assert_unnumbered(self, move, document_label):
        """Assert that ``move`` carries no journal sequence number.

        Odoo represents an unnumbered document either as the ``/`` placeholder or
        as an empty number, and only assigns a real number when a move is posted.
        Neither form is a sequence number issued by the journal, which is what
        the story requires of a refused credit note.
        """
        self.assertFalse(
            move.name and move.name != '/',
            f"A refused vendor credit note must receive no sequence number from the Purchase journal, but the {document_label} reads a number of {move.name!r}.",
        )
        self.assertFalse(
            move.sequence_number,
            f"A refused vendor credit note must consume no position in the journal's sequence, but the {document_label} reads sequence number {move.sequence_number}.",
        )

    def _assert_refused_credit_note(self, credit_note, bill, payable_before, description):
        """Assert the shared outcome of a refused linked vendor credit note.

        A refusal leaves the credit note exactly where it stood -- draft and
        unnumbered -- and leaves the payable sub-ledger untouched: not one of its
        journal items is posted, and the movement the attempt contributed to
        Accounts Payable 2000 measures 0.00 in the company currency.
        """
        currency = self.company_currency
        self.assertEqual(
            credit_note.state,
            'draft',
            f"A refused {description} vendor credit note must stay in state 'draft', but it reads {credit_note.state!r}.",
        )
        self._assert_unnumbered(credit_note, f"refused {description} credit note")
        self.assertFalse(
            credit_note.line_ids.filtered(lambda line: line.parent_state == 'posted'),
            f"A refused {description} vendor credit note must leave no posted journal item behind.",
        )

        payable_after = self._posted_movement(self.account_payable_2000, self.vendor)
        self.assertEqual(
            currency.compare_amounts(payable_after, payable_before),
            0,
            f"Accounts Payable {CODE_ACCOUNTS_PAYABLE} must be unchanged by a refused {description} credit note: it read {payable_before} {currency.name} before the attempt and {payable_after} {currency.name} after it.",
        )
        self.assertTrue(
            currency.is_zero(payable_after - payable_before),
            f"The movement a refused {description} credit note contributes to Accounts Payable {CODE_ACCOUNTS_PAYABLE} must measure 0.00 {currency.name}, but it measures {payable_after - payable_before}.",
        )
        self.assertEqual(
            currency.compare_amounts(payable_after, -AMOUNT_BILL_TOTAL),
            0,
            f"The vendor must still owe the bill in full after the refusal: Accounts Payable {CODE_ACCOUNTS_PAYABLE} must read a credit of {AMOUNT_BILL_TOTAL:.2f} {currency.name}, but it reads {payable_after}.",
        )
        self.assertEqual(
            bill.state,
            'posted',
            f"The source bill must be left posted by a refused {description} credit note, but it reads {bill.state!r}.",
        )
        self.assertEqual(
            currency.compare_amounts(bill.amount_total, AMOUNT_BILL_TOTAL),
            0,
            f"The source bill's total must be left at {AMOUNT_BILL_TOTAL:.2f} {currency.name} by a refused {description} credit note, but it reads {bill.amount_total}.",
        )

    # =========================================================================
    # T-VCN-001-01: The returned line reverses as one balanced credit note
    #               debiting Accounts Payable 2000 and crediting Expense 6100
    # =========================================================================

    def test_vcn_001_01_vendor_credit_note_reverses_bill_line_balanced(self):
        """T-VCN-001-01: a vendor credit note reverses one bill line as one balanced entry.

        Given posted vendor bill in the Purchase journal of the test company for
        Acme Industrial Supplies, dated 2025-03-14, carrying three untaxed lines
        of 6,000.00, 4,200.00 and 2,250.00 against Expense 6100 that total
        12,450.00, and one open payable line of 12,450.00 on Accounts Payable
        2000,
        When the returned software subscription of 4,200.00 is credited back
        through the Debit Note wizard in vendor-credit-note mode and the result
        is posted, dated 2025-03-20,
        Then exactly one linked ``account.move`` with ``move_type = 'in_refund'``
        stands posted in the same Purchase journal and the same currency,
        carrying the accounting date and the credit-note date 2025-03-20, a
        reference that names the bill it reverses, and a sequence number issued
        by that journal; it debits Accounts Payable 2000 by 4,200.00 on one
        payable line carrying the vendor and credits Expense 6100 by 4,200.00,
        its total debits equal its total credits at a difference of 0.00, and the
        source bill is left posted with its three lines unchanged.
        """
        bill = self._create_story_bill()
        currency = bill.currency_id
        subtotals_before = {line.name: line.price_subtotal for line in bill.invoice_line_ids}
        payable_before = self._posted_movement(self.account_payable_2000, self.vendor)
        self.assertEqual(
            currency.compare_amounts(payable_before, -AMOUNT_BILL_TOTAL),
            0,
            f"Before the reversal the vendor must owe {AMOUNT_BILL_TOTAL:.2f} {currency.name} on Accounts Payable {CODE_ACCOUNTS_PAYABLE}, but the sub-ledger reads {payable_before}.",
        )

        credit_note = self._create_vendor_credit_note(bill)

        # One entry, and one only.
        self.assertEqual(
            len(bill.debit_note_ids),
            1,
            f"Crediting the bill must create exactly one linked move, but the bill reports {len(bill.debit_note_ids)}.",
        )
        self.assertEqual(
            credit_note.move_type,
            'in_refund',
            f"The opt-in must turn a posted vendor bill into a vendor credit note, so the result's move_type must be 'in_refund' but reads {credit_note.move_type!r}.",
        )
        self.assertEqual(
            credit_note.state,
            'draft',
            f"The wizard must hand the Clerk a draft to review before posting, but the credit note reads state {credit_note.state!r}.",
        )
        self.assertEqual(
            len(credit_note.invoice_line_ids),
            1,
            f"Only the returned line is credited, so the draft must carry one product line but carries {len(credit_note.invoice_line_ids)}.",
        )

        credit_note.action_post()

        # Identity and linkage.
        self.assertEqual(
            credit_note.state,
            'posted',
            f"A vendor credit note of {AMOUNT_SUBSCRIPTION:.2f} {currency.name} must post, but it reads state {credit_note.state!r}.",
        )
        self.assertEqual(
            credit_note.journal_id,
            bill.journal_id,
            f"The credit note must be raised in the bill's own Purchase journal {bill.journal_id.display_name!r}, but it reads {credit_note.journal_id.display_name!r}.",
        )
        self.assertEqual(
            credit_note.journal_id.type,
            'purchase',
            f"The credit note's journal must be of type 'purchase', but it reads {credit_note.journal_id.type!r}.",
        )
        self.assertEqual(
            credit_note.currency_id,
            bill.currency_id,
            f"The credit note must keep the bill's currency {bill.currency_id.name}, but it reads {credit_note.currency_id.name}.",
        )
        self.assertEqual(
            credit_note.date,
            fields.Date.from_string(CREDIT_NOTE_DATE),
            f"The accounting date must be the {CREDIT_NOTE_DATE} the Clerk stated, but it reads {credit_note.date}.",
        )
        self.assertEqual(
            credit_note.invoice_date,
            fields.Date.from_string(CREDIT_NOTE_DATE),
            f"The credit-note date is a separately readable field and must also be {CREDIT_NOTE_DATE}, but it reads {credit_note.invoice_date}.",
        )
        self.assertIn(
            bill.name,
            credit_note.ref,
            f"The reference must name the bill it reverses ({bill.name}), but it reads {credit_note.ref!r}.",
        )
        self.assertIn(
            CREDIT_NOTE_REFERENCE,
            credit_note.ref,
            f"The reference must carry the vendor's own credit-note reference {CREDIT_NOTE_REFERENCE}, but it reads {credit_note.ref!r}.",
        )
        self.assertTrue(
            credit_note.name and credit_note.name != '/',
            f"Posting must issue a sequence number from the Purchase journal, but the credit note reads a number of {credit_note.name!r}.",
        )
        self.assertEqual(
            credit_note.debit_origin_id,
            bill,
            f"The credit note must stay linked to its source bill, but debit_origin_id reads {credit_note.debit_origin_id.display_name!r}.",
        )
        self.assertIn(
            credit_note,
            bill.debit_note_ids,
            "The bill must reach its credit note through the inverse of that link, so that one record is readable from the other in both directions.",
        )
        self.assertFalse(
            credit_note.reversed_entry_id,
            "reversed_entry_id must stay empty: setting it would hand the credit note to the platform's automatic reconciliation, which is allocation and is out of scope here.",
        )

        # Direction: debit Accounts Payable 2000, credit Expense 6100.
        payable_lines = credit_note.line_ids.filtered(lambda line: line.account_id.code == CODE_ACCOUNTS_PAYABLE)
        expense_lines = credit_note.line_ids.filtered(lambda line: line.account_id.code == CODE_EXPENSE)
        self.assertEqual(
            len(credit_note.line_ids),
            2,
            f"The reversal of one untaxed line is two journal items, one per side, but the entry carries {len(credit_note.line_ids)}.",
        )
        self.assertEqual(
            len(payable_lines),
            1,
            f"The entry must carry exactly one line on Accounts Payable {CODE_ACCOUNTS_PAYABLE}, but it carries {len(payable_lines)}.",
        )
        self.assertEqual(
            len(expense_lines),
            1,
            f"The entry must carry exactly one line on Expense {CODE_EXPENSE}, but it carries {len(expense_lines)}.",
        )
        self.assertEqual(
            currency.compare_amounts(payable_lines.debit, AMOUNT_SUBSCRIPTION),
            0,
            f"The entry must debit Accounts Payable {CODE_ACCOUNTS_PAYABLE} by {AMOUNT_SUBSCRIPTION:.2f} {currency.name}, but that line debits {payable_lines.debit}.",
        )
        self.assertTrue(
            currency.is_zero(payable_lines.credit),
            f"The Accounts Payable {CODE_ACCOUNTS_PAYABLE} line must carry no credit, but it credits {payable_lines.credit} {currency.name}.",
        )
        self.assertEqual(
            payable_lines.partner_id,
            self.vendor,
            f"The payable line must carry the vendor {self.vendor.name}, because it is the line an allocation would later consume, but it reads {payable_lines.partner_id.display_name!r}.",
        )
        self.assertEqual(
            currency.compare_amounts(expense_lines.credit, AMOUNT_SUBSCRIPTION),
            0,
            f"The entry must credit Expense {CODE_EXPENSE} by {AMOUNT_SUBSCRIPTION:.2f} {currency.name}, giving back the charge the bill recognised, but that line credits {expense_lines.credit}.",
        )
        self.assertTrue(
            currency.is_zero(expense_lines.debit),
            f"The Expense {CODE_EXPENSE} line must carry no debit, but it debits {expense_lines.debit} {currency.name}.",
        )
        self.assertEqual(
            currency.compare_amounts(credit_note.amount_total, AMOUNT_SUBSCRIPTION),
            0,
            f"The credit note must total the credited {AMOUNT_SUBSCRIPTION:.2f} {currency.name}, but it totals {credit_note.amount_total}.",
        )

        # Balance: total debits equal total credits at a difference of 0.00.
        total_debit = sum(credit_note.line_ids.mapped('debit'))
        total_credit = sum(credit_note.line_ids.mapped('credit'))
        self.assertEqual(
            currency.compare_amounts(total_debit, total_credit),
            0,
            f"The entry must balance: total debits of {total_debit} {currency.name} must equal total credits of {total_credit} {currency.name}.",
        )
        self.assertTrue(
            currency.is_zero(total_debit - total_credit),
            f"The difference between the entry's total debits and total credits must measure 0.00 {currency.name}, but it measures {total_debit - total_credit}.",
        )
        self.assertEqual(
            currency.compare_amounts(total_debit, AMOUNT_SUBSCRIPTION),
            0,
            f"Both sides of the entry must measure the credited {AMOUNT_SUBSCRIPTION:.2f} {currency.name}, but its total debits measure {total_debit}.",
        )

        # The payable sub-ledger moved by the credited amount, in the direction
        # that reduces what the company still owes.
        payable_after = self._posted_movement(self.account_payable_2000, self.vendor)
        self.assertEqual(
            currency.compare_amounts(payable_after, payable_before + AMOUNT_SUBSCRIPTION),
            0,
            f"The posted credit note must reduce the vendor's Accounts Payable {CODE_ACCOUNTS_PAYABLE} balance by {AMOUNT_SUBSCRIPTION:.2f} {currency.name}: it read {payable_before} before and must read {payable_before + AMOUNT_SUBSCRIPTION} after, but it reads {payable_after}.",
        )

        # The source bill is reversed, never rewritten.
        self.assertEqual(
            bill.state,
            'posted',
            f"The original bill must be left untouched in state 'posted', but it reads {bill.state!r}.",
        )
        self.assertEqual(
            bill.move_type,
            'in_invoice',
            f"The original bill must still be a vendor bill, but its move_type reads {bill.move_type!r}.",
        )
        self.assertEqual(
            currency.compare_amounts(bill.amount_total, AMOUNT_BILL_TOTAL),
            0,
            f"The original bill must still total {AMOUNT_BILL_TOTAL:.2f} {currency.name}, but it totals {bill.amount_total}.",
        )
        self.assertEqual(
            set(bill.invoice_line_ids.mapped('name')),
            {LINE_ADVISORY, LINE_SUBSCRIPTION, LINE_FREIGHT},
            "The original bill must keep all three of its lines, because a posted entry is reversed rather than edited.",
        )
        for line in bill.invoice_line_ids:
            self.assertEqual(
                currency.compare_amounts(line.price_subtotal, subtotals_before[line.name]),
                0,
                f"The bill line {line.name!r} must still read {subtotals_before[line.name]} {currency.name}, but it reads {line.price_subtotal}.",
            )

    # =========================================================================
    # T-VCN-001-02: A credit note carrying no value cannot post and nothing
    #               reaches Accounts Payable 2000
    # =========================================================================

    def test_vcn_001_02_zero_value_credit_note_refused_no_entry_created(self):
        """T-VCN-001-02: a zero-value credit note is refused and creates no entry.

        Given a draft, linked vendor credit note in the Purchase journal of the
        test company for Acme Industrial Supplies, dated 2025-03-20, whose one
        product line was keyed at a quantity of 0.00 so that the document totals
        0.00, while the source bill stands posted with an open payable of
        12,450.00,
        When the Clerk attempts to post that credit note,
        Then posting is refused with a validation message that names the document
        and the check that failed and states the remedy, the record stays in
        state 'draft' with no sequence number issued by the journal, and the
        movement the refused attempt contributed to Accounts Payable 2000
        measures 0.00.
        """
        bill = self._create_story_bill()
        currency = bill.currency_id
        payable_before = self._posted_movement(self.account_payable_2000, self.vendor)

        credit_note = self._create_vendor_credit_note(bill)
        credited_line = credit_note.invoice_line_ids
        credited_line.ensure_one()
        credited_line.quantity = 0.0

        # The line stays a real product line: the refusal under test is the
        # positive-total guard, not the platform's own guard against a document
        # that carries no line at all.
        self.assertEqual(
            credited_line.display_type,
            'product',
            f"The zero-value credit note must keep a real product line, so that the refusal proved here is the positive-total check rather than the guard against an empty document, but the line reads display_type {credited_line.display_type!r}.",
        )
        self.assertTrue(
            currency.is_zero(credit_note.amount_total),
            f"The credit note under test must total 0.00 {currency.name}, but it totals {credit_note.amount_total}.",
        )

        with self.assertRaises(UserError) as refusal:
            credit_note.action_post()

        message = str(refusal.exception)
        self.assertIn(
            credit_note.ref,
            message,
            f"The refusal must name the document it refuses ({credit_note.ref!r}), but it reads {message!r}.",
        )
        self.assertIn(
            'greater than zero',
            message,
            f"The refusal must state the check that failed -- the total must be greater than zero -- but it reads {message!r}.",
        )
        self.assertIn(
            'credited quantity',
            message,
            f"The refusal must state the remedy, which is to state the credited quantity and amount, but it reads {message!r}.",
        )
        self.assertIn(
            'post it again',
            message,
            f"The refusal must tell the Clerk to post again once the amount is stated, but it reads {message!r}.",
        )
        self.assertNotIn(
            "Even magicians can't post nothing!",
            message,
            f"The refusal proved here is the positive-total check on a document that does carry a line, not the platform's guard against an empty one, but the message reads {message!r}.",
        )

        self._assert_refused_credit_note(credit_note, bill, payable_before, 'zero-value')

    # =========================================================================
    # T-VCN-001-03: A credit note carrying a negative value cannot post and
    #               nothing reaches Accounts Payable 2000
    # =========================================================================

    def test_vcn_001_03_negative_value_credit_note_refused_no_entry_created(self):
        """T-VCN-001-03: a negative-value credit note is refused and creates no entry.

        Given a draft, linked vendor credit note in the Purchase journal of the
        test company for Acme Industrial Supplies, dated 2025-03-20, whose one
        product line was keyed at a negative unit price so that the document
        totals -4,200.00, while the source bill stands posted with an open
        payable of 12,450.00,
        When the Clerk attempts to post that credit note,
        Then posting is refused by the vendor-credit-note check rather than by
        the platform's own negative-total message, the record stays in state
        'draft' with no sequence number issued by the journal, and the movement
        the refused attempt contributed to Accounts Payable 2000 measures 0.00.
        """
        bill = self._create_story_bill()
        currency = bill.currency_id
        payable_before = self._posted_movement(self.account_payable_2000, self.vendor)

        credit_note = self._create_vendor_credit_note(bill)
        credited_line = credit_note.invoice_line_ids
        credited_line.ensure_one()
        credited_line.price_unit = -AMOUNT_SUBSCRIPTION

        self.assertEqual(
            currency.compare_amounts(credit_note.amount_total, -AMOUNT_SUBSCRIPTION),
            0,
            f"The credit note under test must total {-AMOUNT_SUBSCRIPTION:.2f} {currency.name}, but it totals {credit_note.amount_total}.",
        )

        with self.assertRaises(UserError) as refusal:
            credit_note.action_post()

        message = str(refusal.exception)
        self.assertIn(
            credit_note.ref,
            message,
            f"The refusal must name the document it refuses ({credit_note.ref!r}), but it reads {message!r}.",
        )
        self.assertIn(
            'greater than zero',
            message,
            f"The refusal must state the check that failed -- the total must be greater than zero -- but it reads {message!r}.",
        )
        self.assertIn(
            'credited quantity',
            message,
            f"The refusal must state the remedy, which is to state the credited quantity and amount, but it reads {message!r}.",
        )
        self.assertNotIn(
            'negative total amount',
            message,
            f"The vendor-credit-note check runs before the platform's generic negative-total validation, so the Clerk must read the credit-note message rather than an instruction to create a credit note, but the message reads {message!r}.",
        )

        self._assert_refused_credit_note(credit_note, bill, payable_before, 'negative-value')

    # =========================================================================
    # T-VCN-001-04: The credit note posts in the bill's own currency and rounds
    #               half-up at that currency's rounding increment
    # =========================================================================

    def test_vcn_001_04_credit_note_posts_in_bill_currency_half_up_rounding(self):
        """T-VCN-001-04: the credit note posts in the bill currency with HALF-UP rounding.

        Given a posted vendor bill denominated in EUR, a currency configured with
        a rounding increment of 0.05 rather than the usual 0.01, carrying one
        untaxed line whose amount before rounding is exactly 10.025 -- a tie at
        that increment,
        When that line is credited back through the Debit Note wizard in
        vendor-credit-note mode and the result is posted,
        Then the credit note is denominated in the bill's own EUR rather than in
        the company currency, its total is the 10.05 that half-up rounding
        produces by taking the tie away from zero, and the entry balances at a
        difference of 0.00 in both the document currency and the company
        currency.
        """
        eur = self.setup_other_currency('EUR', rounding=ROUNDING_INCREMENT)
        cents = self.company_currency
        self.assertEqual(
            cents.compare_amounts(eur.rounding, ROUNDING_INCREMENT),
            0,
            f"The alternate currency must carry the non-standard rounding increment {ROUNDING_INCREMENT}, but it reads {eur.rounding}.",
        )
        self.assertNotEqual(
            eur,
            cents,
            f"The rounding fixture only proves anything if the document currency differs from the company currency {cents.name}.",
        )

        # The rounding contract itself, stated independently of any document:
        # 10.025 / 0.05 = 200.5 is a tie, and half-up takes a tie away from zero.
        self.assertEqual(
            cents.compare_amounts(eur.round(ROUNDING_LINE_AMOUNT), ROUNDING_EXPECTED_TOTAL),
            0,
            f"Rounding {ROUNDING_LINE_AMOUNT} at an increment of {ROUNDING_INCREMENT} must give {ROUNDING_EXPECTED_TOTAL:.2f} under half-up, but it gives {eur.round(ROUNDING_LINE_AMOUNT)}.",
        )

        bill = self._create_story_bill(
            lines=[(LINE_SUBSCRIPTION, ROUNDING_UNIT_PRICE, ROUNDING_QUANTITY)],
            currency=eur,
        )
        self.assertEqual(
            bill.currency_id,
            eur,
            f"The bill must be denominated in {eur.name}, but it reads {bill.currency_id.name}.",
        )
        self.assertEqual(
            cents.compare_amounts(bill.amount_total, ROUNDING_EXPECTED_TOTAL),
            0,
            f"The bill's line amount of {ROUNDING_LINE_AMOUNT} must post as {ROUNDING_EXPECTED_TOTAL:.2f} {eur.name} under half-up rounding, but the bill totals {bill.amount_total}.",
        )

        credit_note = self._create_vendor_credit_note(bill)
        credit_note.action_post()

        self.assertEqual(
            credit_note.state,
            'posted',
            f"The credit note must post, but it reads state {credit_note.state!r}.",
        )
        self.assertEqual(
            credit_note.currency_id,
            eur,
            f"The credit note must keep the bill's own currency {eur.name} rather than falling back to the company currency, but it reads {credit_note.currency_id.name}.",
        )
        self.assertEqual(
            credit_note.currency_id,
            bill.currency_id,
            "The credit note and the bill it reverses must share one currency.",
        )
        self.assertEqual(
            eur.compare_amounts(credit_note.amount_total, ROUNDING_EXPECTED_TOTAL),
            0,
            f"Compared at the {eur.name} increment of {ROUNDING_INCREMENT}, the credit note must total {ROUNDING_EXPECTED_TOTAL:.2f} but totals {credit_note.amount_total}.",
        )
        self.assertEqual(
            cents.compare_amounts(credit_note.amount_total, ROUNDING_EXPECTED_TOTAL),
            0,
            f"Compared to the cent, the credit note must total exactly {ROUNDING_EXPECTED_TOTAL:.2f} {eur.name} -- half-up takes the 10.025 tie away from zero -- but it totals {credit_note.amount_total}.",
        )

        # Direction, in the document currency.
        payable_lines = credit_note.line_ids.filtered(lambda line: line.account_id.code == CODE_ACCOUNTS_PAYABLE)
        expense_lines = credit_note.line_ids.filtered(lambda line: line.account_id.code == CODE_EXPENSE)
        self.assertEqual(
            len(payable_lines),
            1,
            f"The entry must carry exactly one line on Accounts Payable {CODE_ACCOUNTS_PAYABLE}, but it carries {len(payable_lines)}.",
        )
        self.assertEqual(
            len(expense_lines),
            1,
            f"The entry must carry exactly one line on Expense {CODE_EXPENSE}, but it carries {len(expense_lines)}.",
        )
        self.assertEqual(
            cents.compare_amounts(payable_lines.amount_currency, ROUNDING_EXPECTED_TOTAL),
            0,
            f"The entry must debit Accounts Payable {CODE_ACCOUNTS_PAYABLE} by {ROUNDING_EXPECTED_TOTAL:.2f} {eur.name}, but that line reads {payable_lines.amount_currency}.",
        )
        self.assertEqual(
            cents.compare_amounts(expense_lines.amount_currency, -ROUNDING_EXPECTED_TOTAL),
            0,
            f"The entry must credit Expense {CODE_EXPENSE} by {ROUNDING_EXPECTED_TOTAL:.2f} {eur.name}, but that line reads {expense_lines.amount_currency}.",
        )

        # Balance in the source currency.
        source_debit = sum(line.amount_currency for line in credit_note.line_ids if line.amount_currency > 0.0)
        source_credit = -sum(line.amount_currency for line in credit_note.line_ids if line.amount_currency < 0.0)
        self.assertEqual(
            eur.compare_amounts(source_debit, source_credit),
            0,
            f"In {eur.name} the entry must balance: total debits of {source_debit} must equal total credits of {source_credit}.",
        )
        self.assertTrue(
            eur.is_zero(source_debit - source_credit),
            f"The difference between the entry's total debits and total credits must measure 0.00 {eur.name}, but it measures {source_debit - source_credit}.",
        )
        self.assertEqual(
            eur.compare_amounts(source_debit, ROUNDING_EXPECTED_TOTAL),
            0,
            f"Both sides of the entry must measure {ROUNDING_EXPECTED_TOTAL:.2f} {eur.name}, but its total debits measure {source_debit}.",
        )

        # Balance in the company currency, where the books are kept.
        total_debit = sum(credit_note.line_ids.mapped('debit'))
        total_credit = sum(credit_note.line_ids.mapped('credit'))
        self.assertEqual(
            cents.compare_amounts(total_debit, total_credit),
            0,
            f"In the company currency {cents.name} the entry must balance: total debits of {total_debit} must equal total credits of {total_credit}.",
        )
        self.assertTrue(
            cents.is_zero(total_debit - total_credit),
            f"The difference between the entry's total debits and total credits must measure 0.00 {cents.name}, but it measures {total_debit - total_credit}.",
        )

    # =========================================================================
    # T-VCN-001-05: A linked credit note and a plain unlinked refund in the same
    #               journal and period receive different sequence numbers
    # =========================================================================

    def test_vcn_001_05_credit_note_sequence_distinct_from_plain_refund(self):
        """T-VCN-001-05: the credit note's sequence number is distinct from a plain refund's.

        Given a posted vendor bill in the Purchase journal of the test company,
        that journal keeping a dedicated debit-note sequence as well as the
        platform's dedicated refund sequence,
        When one linked vendor credit note dated 2025-03-20 and one ordinary
        unlinked vendor credit note dated 2025-03-25 are both posted in that same
        journal and the same month,
        Then both post and receive different sequence numbers, so that two
        refunds cannot be numbered alike: refunds share the single refund pool
        the platform keeps for them, and the debit-note domain split that would
        otherwise hand both of them the same next number is applied only to
        invoice-type documents.

        The unlinked refund is built directly rather than through the wizard,
        which by design produces only documents that carry a source link and
        refuses a source that already carries one.
        """
        bill = self._create_story_bill()
        self.assertTrue(
            self.purchase_journal.debit_sequence,
            "The journal must keep a dedicated debit-note sequence, otherwise the domain split this test guards against never runs.",
        )
        self.assertTrue(
            self.purchase_journal.refund_sequence,
            "The journal must keep a dedicated refund sequence, otherwise both documents would draw from the invoice pool and the collision this test guards against could not arise.",
        )

        linked_credit_note = self._create_vendor_credit_note(bill)
        linked_credit_note.action_post()

        plain_refund = self._create_invoice(
            move_type='in_refund',
            invoice_date=fields.Date.from_string(PLAIN_REFUND_DATE),
            date=fields.Date.from_string(PLAIN_REFUND_DATE),
            post=True,
            partner_id=self.vendor,
            journal_id=self.purchase_journal,
            currency_id=self.company_currency,
            invoice_line_ids=[
                self._prepare_invoice_line(
                    name='Unlinked vendor credit note',
                    price_unit=AMOUNT_PLAIN_REFUND,
                    quantity=1.0,
                    tax_ids=[],
                    account_id=self.account_expense_6100,
                ),
            ],
        )

        self.assertEqual(
            linked_credit_note.state,
            'posted',
            f"The linked vendor credit note must post, but it reads state {linked_credit_note.state!r}.",
        )
        self.assertEqual(
            plain_refund.state,
            'posted',
            f"The unlinked vendor credit note must post, but it reads state {plain_refund.state!r}.",
        )
        self.assertEqual(
            plain_refund.move_type,
            'in_refund',
            f"The second document must be an ordinary vendor credit note, but its move_type reads {plain_refund.move_type!r}.",
        )
        self.assertTrue(
            linked_credit_note.debit_origin_id,
            "The first document must carry the source link, because that link is what an ungated domain split keys on.",
        )
        self.assertFalse(
            plain_refund.debit_origin_id,
            "The second document must carry no source link, so that the two documents fall on opposite sides of that split.",
        )

        # Same journal, same period: neither the journal clause nor the date
        # range of the sequence domain can mask a collision here.
        self.assertEqual(
            linked_credit_note.journal_id,
            plain_refund.journal_id,
            "Both documents must sit in the same journal for the comparison to mean anything.",
        )
        self.assertEqual(
            (linked_credit_note.date.year, linked_credit_note.date.month),
            (plain_refund.date.year, plain_refund.date.month),
            f"Both documents must sit in the same month, but they read {linked_credit_note.date} and {plain_refund.date}.",
        )

        self.assertTrue(
            linked_credit_note.name and linked_credit_note.name != '/',
            f"The linked vendor credit note must receive a sequence number, but it reads {linked_credit_note.name!r}.",
        )
        self.assertTrue(
            plain_refund.name and plain_refund.name != '/',
            f"The unlinked vendor credit note must receive a sequence number, but it reads {plain_refund.name!r}.",
        )
        self.assertNotEqual(
            linked_credit_note.name,
            plain_refund.name,
            f"Two vendor credit notes in the same journal and the same period must receive different numbers, but both read {linked_credit_note.name!r}.",
        )
        self.assertEqual(
            linked_credit_note.sequence_prefix,
            plain_refund.sequence_prefix,
            f"Both documents must draw from the one refund sequence pool of that journal, but they read the prefixes {linked_credit_note.sequence_prefix!r} and {plain_refund.sequence_prefix!r}.",
        )
        self.assertNotEqual(
            linked_credit_note.sequence_number,
            plain_refund.sequence_number,
            f"Sharing one pool, the two documents must occupy different positions in it, but both read position {linked_credit_note.sequence_number}.",
        )

    # =========================================================================
    # T-VCN-001-06: Without the opt-in, a posted vendor bill still produces the
    #               shipped debit note
    # =========================================================================

    def test_vcn_001_06_default_vendor_bill_path_remains_debit_note(self):
        """T-VCN-001-06: without the opt-in a vendor bill still produces a debit note.

        Given a posted vendor bill in the Purchase journal of the test company,
        raised in the same way as the bill every other scenario here reverses,
        When the Clerk runs the Debit Note wizard against it without asking for a
        vendor credit note,
        Then the opt-in reads false by default and the result is still a draft
        vendor bill debit note linked to its source by ``debit_origin_id``, so
        that the behaviour the module shipped is preserved for everyone who does
        not ask for the new one.

        This test uses its own bill: the wizard refuses a source that already
        carries a source link, so the bill reversed by another scenario cannot be
        reused here.
        """
        bill = self._create_story_bill()

        wizard = self.env['account.debit.note'].with_context(
            active_model='account.move',
            active_ids=bill.ids,
        ).create({
            'date': fields.Date.from_string(CREDIT_NOTE_DATE),
            'reason': 'Freight undercharged on the original bill',
        })
        self.assertFalse(
            wizard.create_vendor_credit_note,
            "The vendor-credit-note mode must be opt-in: the wizard field must read false unless the Clerk sets it.",
        )
        self.assertEqual(
            wizard.move_type,
            'in_invoice',
            f"The wizard must read the source type from the selected bill, but it reads {wizard.move_type!r}.",
        )

        wizard.create_debit()

        debit_note = self.env['account.move'].search([('debit_origin_id', '=', bill.id)])
        debit_note.ensure_one()
        self.assertEqual(
            debit_note.move_type,
            'in_invoice',
            f"Without the opt-in a vendor bill must still produce a vendor bill debit note, but the result reads move_type {debit_note.move_type!r}.",
        )
        self.assertEqual(
            debit_note.state,
            'draft',
            f"A debit note must be created in draft, as it always was, but the result reads state {debit_note.state!r}.",
        )
        self.assertEqual(
            debit_note.debit_origin_id,
            bill,
            f"The debit note must stay linked to the bill it corrects, but debit_origin_id reads {debit_note.debit_origin_id.display_name!r}.",
        )
        self.assertEqual(
            debit_note.journal_id,
            bill.journal_id,
            f"The debit note must be raised in the bill's own journal {bill.journal_id.display_name!r}, but it reads {debit_note.journal_id.display_name!r}.",
        )
        self.assertFalse(
            debit_note.invoice_line_ids,
            "Lines must not be copied unless the Clerk asks for them, which is the behaviour the module shipped.",
        )
        self.assertFalse(
            debit_note.reversed_entry_id,
            "The debit-note path must leave reversed_entry_id empty, exactly as it did before the vendor-credit-note mode was added.",
        )
        self.assertEqual(
            bill.state,
            'posted',
            f"The source bill must be left posted, but it reads {bill.state!r}.",
        )
        self.assertEqual(
            bill.move_type,
            'in_invoice',
            f"The source bill must still be a vendor bill, but its move_type reads {bill.move_type!r}.",
        )
