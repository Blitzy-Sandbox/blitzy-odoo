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

Scenario 1 states its outcome for one bill, one credit note and one journal, and
the six cases above also guard that reading of it, inside the case each belongs
to rather than as cases of their own: the request the mode accepts is settled in
T-VCN-001-01, which reverses one bill in that bill's own journal and is refused
when another journal is named, and in T-VCN-001-06, which is where the mode is
asked for a source that is not one posted vendor bill and where the same
selection is then shown still raising the debit notes the module shipped with.

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
from odoo.tools.float_utils import float_compare

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
# The same tie taken the other way.  10.00 and 10.05 are two different multiples
# of that currency's own increment, so naming the wrong outcome is what lets the
# direction of the rounding be asserted in the currency the amount is stated in.
ROUNDING_TIE_TOWARD_ZERO = 10.0
# The cent, as a number of decimal places.  Amounts are asserted at this
# precision as well as at their currency's increment, because 10.03 and 10.05 are
# the same amount at an increment of 0.05 and different amounts to the cent.
CENT_PRECISION_DIGITS = 2

# T-VCN-001-05 -- the amount of the ordinary, unlinked vendor credit note that
# competes with the linked one for the journal's refund sequence.
AMOUNT_PLAIN_REFUND = 1000.0

# T-VCN-001-01 -- a second Purchase journal.  The wizard's journal selector is
# restricted to journals of the source's own type, so a journal that selector
# accepts is still not necessarily the journal of the bill being credited.
OTHER_PURCHASE_JOURNAL_NAME = 'Secondary Purchases'
OTHER_PURCHASE_JOURNAL_CODE = 'BILL2'


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
    the subtraction and rounding after it are not the same test.  Alongside those,
    and only in ``test_vcn_001_04``, each amount is compared to the cent as well
    with ``float_compare(..., precision_digits=2)``: the currency of that case
    rounds to 0.05, at which increment 10.03 and 10.05 are one amount, and the
    outcome under test is exactly 10.05.  A value keyed or copied unchanged --
    a quantity, a unit price -- is compared exactly, being what was keyed rather
    than an amount arrived at by arithmetic.

    Branch-to-test mapping
    ----------------------
    The branches this change adds, and the tests that reach each of them:

        * ``account.debit.note._prepare_default_values``
          -- the opt-in branch, ``create_vendor_credit_note`` true and the source
             ``move_type == 'in_invoice'``, producing ``in_refund``
             -> test_vcn_001_01 / 04 / 05
          -- the opt-in set on a source that is not a vendor bill, where the
             shipped credit-note-to-bill mapping still decides the result
             -> test_vcn_001_06
          -- the falsy path, where a vendor bill still produces the shipped
             ``in_invoice`` debit note, for one selected bill and for several
             -> test_vcn_001_06 (and, for the other source types, the module's
                test_00_debit_note_out_invoice and test_10_debit_note_in_refund)

        * ``account.move._check_vendor_credit_note_positive_total``
          -- the raising path, a linked ``in_refund`` whose currency-rounded
             total is not above zero
             -> test_vcn_001_02 (zero) / 03 (negative)
          -- the passing path, a linked ``in_refund`` with a positive total
             -> test_vcn_001_01 / 04 / 05
          -- inapplicable because the document carries no source link, at a
             total of zero and at a negative total
             -> test_vcn_001_02 / 03
          -- inapplicable because the document is a vendor bill rather than a
             vendor credit note, at a total of zero
             -> test_vcn_001_02

        * ``account.move._post`` override
          -- delegation to ``super()._post(soft=soft)`` after the guard passes
             -> test_vcn_001_01 / 04 / 05 / 06
          -- refusal raised before ``super()._post`` is ever entered
             -> test_vcn_001_02 / 03

        * ``account.move._get_last_sequence_domain``
          -- the ``in_refund`` path, now excluded from the debit-note domain
             split so that linked and unlinked refunds share one refund pool
             -> test_vcn_001_05, which reads the numbering range off both
                refunds and compares the numbers they were issued
          -- the retained invoice-type path, where a vendor bill is numbered
             among the documents carrying no source link and its debit note
             among those that do
             -> test_vcn_001_06, which reads both ranges and posts the debit
                note to compare its number with the bill's (and the module's
                existing suite)

        * ``account.debit.note._check_vendor_credit_note_request``
          -- the accepting path, one posted vendor bill and the bill's own
             journal, named or left empty
             -> test_vcn_001_01 (names it) / 02 / 03 / 04 / 05 (leave it empty)
          -- a journal other than the source bill's own
             -> test_vcn_001_01
          -- more than one selected source
             -> test_vcn_001_06
          -- a source that is not posted
             -> test_vcn_001_06
          -- a source that is not a vendor bill
             -> test_vcn_001_06
          -- never reached while the opt-in is off, which is what leaves the
             shipped debit-note path free to take several sources and another
             journal
             -> test_vcn_001_06 (and the module's existing suite)
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.company_currency = cls.company_data['currency']
        cls.purchase_journal = cls.company_data['default_journal_purchase']

        # Accounts Payable 2000 and Expense 6100.  Loading a chart template pads
        # every template code out to the chart's code width, so the generic chart
        # carries 211000 and 610000 rather than the 2110 and 6100 of its own
        # source data, and the two codes the story names are free to be created.
        # The helper reuses either code where a chart does carry it.
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

        # Asking for the same code again must find the account that answers to it
        # rather than add another one.  On a chart that already carries 2000 or
        # 6100 that is the path taken from the outset, so it is exercised here on
        # every chart: a fixture that put a second account on one of these codes
        # would leave the assertions below reading whichever of the two a search
        # happened to return, and this suite reads its accounts by code.
        for account, code, account_type, reconcile in (
            (cls.account_payable_2000, CODE_ACCOUNTS_PAYABLE, 'liability_payable', True),
            (cls.account_expense_6100, CODE_EXPENSE, 'expense', False),
        ):
            located = cls._vcn_account(code=code, name=account.name, account_type=account_type, reconcile=reconcile)
            assert located == account, (
                f"Account {code} must be located rather than created a second time, but a second call returned "
                f"{located.id} against the {account.id} the first one gave."
            )
            answering_code = cls.env['account.account'].with_company(cls.env.company).with_context(active_test=False).search([
                *cls.env['account.account']._check_company_domain(cls.env.company),
                ('code', '=', code),
            ])
            assert len(answering_code) == 1, (
                f"Exactly one account of the test company must answer to code {code}, but {len(answering_code)} do: "
                f"{answering_code.mapped('name')}."
            )
            assert account.active, f"Account {code} must stand active for the fixture to be usable, but it reads archived."
            assert account.account_type == account_type, (
                f"Account {code} must be typed {account_type!r} as the story names it, but it reads {account.account_type!r}."
            )
            if reconcile:
                assert account.reconcile, f"Account {code} must allow reconciliation, which the story requires of the payable account."

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

        An ``account.account`` code is meant to name one account per company and
        is stored as a company-dependent value, so the lookup is scoped to the
        company before anything is written, and it is made with
        ``active_test=False``: an archived account keeps its code, and a search
        that skipped it would create a second record on the same code, leaving
        two accounts answering to 2000 and the assertions below reading whichever
        of them a search happens to return.  A code the chart does carry is
        therefore reused and brought to what the story names -- unarchived,
        renamed, retyped and, where the story needs it, made reconcilable --
        while a code the chart does not carry is created in full.  Written this
        way the fixture holds whichever chart template the test company happens
        to load.

        The reuse is a single ``write``.  A payable account that is not
        reconcilable is refused by the platform, so the type and the
        reconciliation flag have to reach the record in one operation rather than
        leaving it momentarily in a state that cannot exist.  The flag is only
        ever turned on: the expense account plays no part in reconciliation, and
        turning the flag off is itself refused while partial reconciliations are
        pending, neither of which is a change anything here asks for.
        """
        company = cls.env.company
        AccountAccount = cls.env['account.account'].with_company(company).with_context(active_test=False)
        account = AccountAccount.search(
            [
                *AccountAccount._check_company_domain(company),
                ('code', '=', code),
            ],
            limit=1,
        )
        if account:
            reuse_values = {
                'active': True,
                'name': name,
                'account_type': account_type,
            }
            if reconcile and not account.reconcile:
                reuse_values['reconcile'] = True
            account.write(reuse_values)
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

    def _create_vendor_credit_note(self, bill, keep_line=LINE_SUBSCRIPTION, reason=CREDIT_NOTE_REASON, date=CREDIT_NOTE_DATE, journal=None):
        """Raise a draft, linked vendor credit note from ``bill`` and return it.

        The shipped Debit Note wizard is opened the way the module's own suite
        opens it -- through the ``active_model``/``active_ids`` context that the
        Debit Note action supplies -- with the ``create_vendor_credit_note``
        opt-in set, so the copy comes out as an ``in_refund`` rather than as the
        vendor debit note the same wizard produces by default.  ``journal`` names
        a journal under Use Specific Journal; left out, the field stays empty and
        the credit note follows the bill's own journal either way.

        ``copy_lines`` brings across every line of the bill rather than only the
        credited one, so the copy is trimmed down to the line named
        ``keep_line``: the story credits line 2 of the bill alone.  Pass
        ``keep_line=False`` to keep the copy exactly as the wizard produced it.

        The result is located through ``debit_origin_id`` -- the module's source
        link -- and ``ensure_one`` proves that exactly one linked move stands for
        the bill.  The count of journal entries is taken before and after the
        operation as well, because "one linked move" and "one new move" are
        different statements: a linked credit note plus an unlinked entry raised
        alongside it would satisfy the first and not the second, and the story
        allows one entry only.
        """
        wizard = self.env['account.debit.note'].with_context(
            active_model='account.move',
            active_ids=bill.ids,
        ).create({
            'date': fields.Date.from_string(date),
            'reason': reason,
            'copy_lines': True,
            'create_vendor_credit_note': True,
            'journal_id': journal.id if journal else False,
        })
        moves_before = self.env['account.move'].search([])
        wizard.create_debit()

        created_moves = self.env['account.move'].search([('id', 'not in', moves_before.ids)])
        self.assertEqual(
            len(created_moves),
            1,
            f"Raising a vendor credit note must create exactly one journal entry, but it created {len(created_moves)}: {created_moves.mapped('display_name')}.",
        )
        credit_note = self.env['account.move'].search([('debit_origin_id', '=', bill.id)])
        credit_note.ensure_one()
        self.assertEqual(
            created_moves,
            credit_note,
            f"The one entry the operation created must be the credit note linked to the bill, but the entry created reads {created_moves.mapped('display_name')} against a linked credit note of {credit_note.display_name!r}.",
        )
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

        One state is required here rather than any of several.  ``/`` is the
        number a document reads until a journal numbers it at posting, and the
        wizard states it on the credit note it raises, so a refused credit note
        reads exactly that: an unnumbered document, not one whose number was
        cleared.  The exact value is asserted, together with a sequence position
        of 0 and a document that has never been posted, so that a change issuing
        a real number fails on the first, a change consuming a position in the
        journal's sequence fails on the second, and a document that had been
        numbered and returned to draft -- which is not the case under test --
        fails on the third.
        """
        self.assertEqual(
            move.name,
            '/',
            f"A refused vendor credit note must be left reading the '/' of a document the journal has not numbered, but the {document_label} reads {move.name!r}.",
        )
        self.assertFalse(
            move.sequence_number,
            f"A refused vendor credit note must consume no position in the journal's sequence, but the {document_label} reads sequence number {move.sequence_number}.",
        )
        self.assertFalse(
            move.posted_before,
            f"A refused vendor credit note must never have been posted, so it can never have been numbered, but the {document_label} reads posted_before {move.posted_before!r}.",
        )

    def _snapshot_move_lines(self, move):
        """Return the material state of every journal item of ``move``, keyed by line id.

        Keying on the id is what makes the comparison an identity check as well as
        a value check: a line that was replaced by another carrying the same
        amount is a different record, and reversing a posted document must leave
        the document itself alone rather than rewrite it.
        """
        return {
            line.id: {
                'name': line.name,
                'display_type': line.display_type,
                'account': line.account_id,
                'partner': line.partner_id,
                'product': line.product_id,
                'currency': line.currency_id,
                'quantity': line.quantity,
                'price_unit': line.price_unit,
                'price_subtotal': line.price_subtotal,
                'amount_currency': line.amount_currency,
                'debit': line.debit,
                'credit': line.credit,
                'balance': line.balance,
            }
            for line in move.line_ids
        }

    def _assert_move_lines_unchanged(self, move, snapshot, description):
        """Assert that every journal item of ``move`` still reads what ``snapshot`` recorded.

        The document's own currency measures the figures the document is
        denominated in -- the line amount and ``amount_currency`` -- while the
        company currency measures the figures the books are kept in, which are
        ``debit``, ``credit`` and ``balance``.  The keyed values are compared
        exactly: a quantity, a unit price, an account and a name are what was
        keyed rather than amounts arrived at by arithmetic, so any difference at
        all in them is a rewrite of the source document.
        """
        document_currency = move.currency_id
        company_currency = self.company_currency
        self.assertEqual(
            set(move.line_ids.ids),
            set(snapshot),
            f"{description} must still carry exactly the journal items it carried before the operation: it held {sorted(snapshot)} and now holds {sorted(move.line_ids.ids)}.",
        )
        for line in move.line_ids:
            before = snapshot[line.id]
            self.assertEqual(
                line.name,
                before['name'],
                f"Line {line.id} of {description} must still be named {before['name']!r}, but it reads {line.name!r}.",
            )
            self.assertEqual(
                line.display_type,
                before['display_type'],
                f"Line {line.id} of {description} must still read display_type {before['display_type']!r}, but it reads {line.display_type!r}.",
            )
            self.assertEqual(
                line.account_id,
                before['account'],
                f"Line {line.id} of {description} must still sit on account {before['account'].code}, but it reads {line.account_id.code}.",
            )
            self.assertEqual(
                line.partner_id,
                before['partner'],
                f"Line {line.id} of {description} must still carry {before['partner'].display_name!r}, but it reads {line.partner_id.display_name!r}.",
            )
            self.assertEqual(
                line.product_id,
                before['product'],
                f"Line {line.id} of {description} must still carry the product {before['product'].display_name!r}, but it reads {line.product_id.display_name!r}.",
            )
            self.assertEqual(
                line.currency_id,
                before['currency'],
                f"Line {line.id} of {description} must still be denominated in {before['currency'].name}, but it reads {line.currency_id.name}.",
            )
            self.assertEqual(
                line.quantity,
                before['quantity'],
                f"Line {line.id} of {description} must still read a quantity of {before['quantity']}, but it reads {line.quantity}.",
            )
            self.assertEqual(
                line.price_unit,
                before['price_unit'],
                f"Line {line.id} of {description} must still read a unit price of {before['price_unit']}, but it reads {line.price_unit}.",
            )
            self.assertEqual(
                document_currency.compare_amounts(line.price_subtotal, before['price_subtotal']),
                0,
                f"Line {line.id} of {description} must still amount to {before['price_subtotal']} {document_currency.name}, but it amounts to {line.price_subtotal}.",
            )
            self.assertEqual(
                document_currency.compare_amounts(line.amount_currency, before['amount_currency']),
                0,
                f"Line {line.id} of {description} must still read {before['amount_currency']} {document_currency.name}, but it reads {line.amount_currency}.",
            )
            for field_name in ('debit', 'credit', 'balance'):
                self.assertEqual(
                    company_currency.compare_amounts(line[field_name], before[field_name]),
                    0,
                    f"Line {line.id} of {description} must still read a {field_name} of {before[field_name]} {company_currency.name}, but it reads {line[field_name]}.",
                )

    def _assert_refused_credit_note(self, credit_note, bill, payable_before, lines_before, description):
        """Assert the shared outcome of a refused linked vendor credit note.

        A refusal leaves the credit note exactly where it stood -- draft,
        unnumbered and linked to its source by nothing more than
        ``debit_origin_id`` -- and leaves the source bill and the payable
        sub-ledger untouched: not one of the credit note's journal items is
        posted, every journal item of the bill still reads what ``lines_before``
        recorded, and the movement the attempt contributed to Accounts Payable
        2000 measures 0.00 in the company currency.
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
        self.assertFalse(
            credit_note.reversed_entry_id,
            f"A refused {description} vendor credit note must still carry no reversal link: reversed_entry_id must stay empty, because setting it would hand the document to the platform's automatic reconciliation, which is allocation and is out of scope here, but it reads {credit_note.reversed_entry_id.display_name!r}.",
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
        self._assert_move_lines_unchanged(bill, lines_before, f"the source bill of the refused {description} credit note")

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

        The journal is settled here as well, because "the same Purchase journal"
        is one of the things this scenario asserts.  A credit note carries the
        sequence of the journal it is recorded in, so one recorded elsewhere would
        be numbered away from the bill it reverses and read out of another
        journal's books; the wizard's journal selector only narrows the choice to
        journals of the source's own type, and a company may keep several Purchase
        journals, so the selector alone does not settle it.  The reversal is
        therefore asked for twice: once naming a second Purchase journal, which is
        refused and records nothing there, and once naming the bill's own, which
        is accepted -- what is refused is a journal other than the bill's, not the
        Clerk's use of the field.
        """
        bill = self._create_story_bill()
        currency = bill.currency_id
        subtotals_before = {line.name: line.price_subtotal for line in bill.invoice_line_ids}
        lines_before = self._snapshot_move_lines(bill)
        payable_before = self._posted_movement(self.account_payable_2000, self.vendor)
        self.assertEqual(
            currency.compare_amounts(payable_before, -AMOUNT_BILL_TOTAL),
            0,
            f"Before the reversal the vendor must owe {AMOUNT_BILL_TOTAL:.2f} {currency.name} on Accounts Payable {CODE_ACCOUNTS_PAYABLE}, but the sub-ledger reads {payable_before}.",
        )

        # A journal other than the bill's own, refused before anything is copied.
        other_journal = self.env['account.journal'].create({
            'name': OTHER_PURCHASE_JOURNAL_NAME,
            'code': OTHER_PURCHASE_JOURNAL_CODE,
            'type': 'purchase',
            'company_id': self.env.company.id,
        })
        self.assertEqual(
            other_journal.type,
            bill.journal_id.type,
            f"The second journal must be of the source's own type, which is what the wizard's selector allows, but it reads {other_journal.type!r} against the bill's {bill.journal_id.type!r}.",
        )
        self.assertNotEqual(
            other_journal,
            bill.journal_id,
            "The second journal must not be the bill's own journal, otherwise there is nothing to refuse.",
        )
        with self.assertRaises(UserError) as refusal:
            self._create_vendor_credit_note(bill, journal=other_journal)

        message = str(refusal.exception)
        self.assertIn(
            bill.journal_id.display_name,
            message,
            f"The refusal must name the journal the credit note belongs in ({bill.journal_id.display_name!r}), but it reads {message!r}.",
        )
        self.assertIn(
            other_journal.display_name,
            message,
            f"The refusal must name the journal that was asked for ({other_journal.display_name!r}), but it reads {message!r}.",
        )
        self.assertFalse(
            self.env['account.move'].search([('debit_origin_id', '=', bill.id)]),
            "A refused journal must leave no credit note behind.",
        )
        self.assertFalse(
            self.env['account.move'].search([('journal_id', '=', other_journal.id)]),
            f"Nothing must be recorded in {OTHER_PURCHASE_JOURNAL_NAME}, so that no number is drawn from a journal the credit note does not belong to.",
        )

        # The bill's own journal, named rather than left empty, is accepted.
        credit_note = self._create_vendor_credit_note(bill, journal=bill.journal_id)

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
        self.assertEqual(
            credit_note.name,
            '/',
            f"The draft handed to the Clerk must be unnumbered, reading the '/' of a document no journal has numbered yet, but it reads {credit_note.name!r}.",
        )
        self.assertFalse(
            credit_note.sequence_number,
            f"The draft must occupy no position in the journal's sequence before it is posted, but it reads sequence number {credit_note.sequence_number}.",
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
        # Every journal item of the bill, taken as a whole: the same records, on
        # the same accounts, for the same quantities, unit prices and amounts as
        # before the reversal.  A line replaced by another of the same value would
        # be a rewrite of a posted document even though the total still agrees.
        self._assert_move_lines_unchanged(bill, lines_before, 'the reversed bill')

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

        The refusal belongs to the linked vendor credit note and to nothing else,
        so the same 0.00 total is also carried past it twice: an ordinary vendor
        credit note that reverses no bill of ours, and a vendor bill debit note,
        which does carry the source link but is not a credit note.  Both post.
        Without those two, a check that had lost either half of what it applies to
        -- the document being a vendor credit note, and the document it is linked
        to being a vendor bill -- would still be refusing exactly the one document
        this scenario keys at zero, and nothing here would notice.
        """
        bill = self._create_story_bill()
        currency = bill.currency_id
        lines_before = self._snapshot_move_lines(bill)
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
        # The remedy the story states is three things the Clerk must be told, so
        # each is asserted on its own: what quantity to state, what amount to
        # state, and that the document can then be posted.
        self.assertIn(
            'credited quantity',
            message,
            f"The refusal must tell the Clerk to state the credited quantity, but it reads {message!r}.",
        )
        self.assertIn(
            'credited amount',
            message,
            f"The refusal must tell the Clerk to state the credited amount as well as the quantity, but it reads {message!r}.",
        )
        self.assertIn(
            'post it again',
            message,
            f"The refusal must tell the Clerk to post the credit note again once the credited quantity and amount are stated, but it reads {message!r}.",
        )
        self.assertNotIn(
            "Even magicians can't post nothing!",
            message,
            f"The refusal proved here is the positive-total check on a document that does carry a line, not the platform's guard against an empty one, but the message reads {message!r}.",
        )

        self._assert_refused_credit_note(credit_note, bill, payable_before, lines_before, 'zero-value')

        # A vendor credit note of the same 0.00 that reverses no bill of ours: it
        # carries no source link, so the credit-note check has nothing to say
        # about it and the platform, which bans no zero-total document, posts it.
        unlinked_zero_refund = self._create_invoice(
            move_type='in_refund',
            invoice_date=fields.Date.from_string(PLAIN_REFUND_DATE),
            date=fields.Date.from_string(PLAIN_REFUND_DATE),
            post=False,
            partner_id=self.vendor,
            journal_id=self.purchase_journal,
            currency_id=self.company_currency,
            invoice_line_ids=[
                self._prepare_invoice_line(
                    name='Unlinked vendor credit note carrying no value',
                    price_unit=AMOUNT_SUBSCRIPTION,
                    quantity=0.0,
                    tax_ids=[],
                    account_id=self.account_expense_6100,
                ),
            ],
        )
        self.assertFalse(
            unlinked_zero_refund.debit_origin_id,
            "The comparison document must carry no source link, which is the half of the check this case removes.",
        )
        self.assertTrue(
            currency.is_zero(unlinked_zero_refund.amount_total),
            f"The comparison document must total the same 0.00 {currency.name} as the refused credit note, but it totals {unlinked_zero_refund.amount_total}.",
        )
        unlinked_zero_refund.action_post()
        self.assertEqual(
            unlinked_zero_refund.state,
            'posted',
            f"An ordinary vendor credit note carrying no value is not what the credit-note check governs and the platform bans no zero-total document, so it must post, but it reads state {unlinked_zero_refund.state!r}.",
        )

        # A vendor bill debit note of the same 0.00: it does carry the source link,
        # but it is a bill rather than a credit note, so the check is again silent.
        second_bill = self._create_story_bill()
        debit_note_wizard = self.env['account.debit.note'].with_context(
            active_model='account.move',
            active_ids=second_bill.ids,
        ).create({
            'date': fields.Date.from_string(CREDIT_NOTE_DATE),
            'reason': 'Freight undercharged on the original bill',
            'copy_lines': True,
        })
        debit_note_wizard.create_debit()
        zero_debit_note = self.env['account.move'].search([('debit_origin_id', '=', second_bill.id)])
        zero_debit_note.ensure_one()
        zero_debit_note.invoice_line_ids.quantity = 0.0
        self.assertEqual(
            zero_debit_note.move_type,
            'in_invoice',
            f"The comparison document must be a vendor bill debit note, which is the other half of the check this case removes, but it reads move_type {zero_debit_note.move_type!r}.",
        )
        self.assertEqual(
            zero_debit_note.debit_origin_id,
            second_bill,
            "The comparison document must carry the source link to its own bill, so that only its type distinguishes it from the refused credit note.",
        )
        self.assertTrue(
            currency.is_zero(zero_debit_note.amount_total),
            f"The comparison document must total the same 0.00 {currency.name} as the refused credit note, but it totals {zero_debit_note.amount_total}.",
        )
        zero_debit_note.action_post()
        self.assertEqual(
            zero_debit_note.state,
            'posted',
            f"A linked vendor bill debit note carrying no value is not a vendor credit note, so the credit-note check must leave it alone and it must post, but it reads state {zero_debit_note.state!r}.",
        )

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

        Which of the two refusals a Clerk reads is the point of this scenario, so
        an ordinary vendor credit note carrying the same negative total is put
        through the same attempt: it reverses no bill of ours, so the
        credit-note check has nothing to say about it and the platform's own
        negative-total refusal is what the Clerk reads instead.  A check that had
        lost the requirement for a source bill would answer for that document too,
        and would say so in its own words.
        """
        bill = self._create_story_bill()
        currency = bill.currency_id
        lines_before = self._snapshot_move_lines(bill)
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
        # The same three-part remedy is required of the negative case: a Clerk who
        # keyed a negative amount is told the same thing as one who keyed none.
        self.assertIn(
            'credited quantity',
            message,
            f"The refusal must tell the Clerk to state the credited quantity, but it reads {message!r}.",
        )
        self.assertIn(
            'credited amount',
            message,
            f"The refusal must tell the Clerk to state the credited amount as well as the quantity, but it reads {message!r}.",
        )
        self.assertIn(
            'post it again',
            message,
            f"The refusal must tell the Clerk to post the credit note again once the credited quantity and amount are stated, but it reads {message!r}.",
        )
        self.assertNotIn(
            'negative total amount',
            message,
            f"The vendor-credit-note check runs before the platform's generic negative-total validation, so the Clerk must read the credit-note message rather than an instruction to create a credit note, but the message reads {message!r}.",
        )

        self._assert_refused_credit_note(credit_note, bill, payable_before, lines_before, 'negative-value')

        # The same negative total on a vendor credit note that reverses no bill of
        # ours: the credit-note check does not govern it, so the refusal the Clerk
        # reads is the platform's own, in the platform's own words.
        unlinked_negative_refund = self._create_invoice(
            move_type='in_refund',
            invoice_date=fields.Date.from_string(PLAIN_REFUND_DATE),
            date=fields.Date.from_string(PLAIN_REFUND_DATE),
            post=False,
            partner_id=self.vendor,
            journal_id=self.purchase_journal,
            currency_id=self.company_currency,
            invoice_line_ids=[
                self._prepare_invoice_line(
                    name='Unlinked vendor credit note carrying a negative value',
                    price_unit=-AMOUNT_SUBSCRIPTION,
                    quantity=1.0,
                    tax_ids=[],
                    account_id=self.account_expense_6100,
                ),
            ],
        )
        self.assertFalse(
            unlinked_negative_refund.debit_origin_id,
            "The comparison document must carry no source link, which is the half of the check this case removes.",
        )
        self.assertEqual(
            currency.compare_amounts(unlinked_negative_refund.amount_total, -AMOUNT_SUBSCRIPTION),
            0,
            f"The comparison document must carry the same {-AMOUNT_SUBSCRIPTION:.2f} {currency.name} as the refused credit note, but it totals {unlinked_negative_refund.amount_total}.",
        )

        with self.assertRaises(UserError) as platform_refusal:
            unlinked_negative_refund.action_post()

        platform_message = str(platform_refusal.exception)
        self.assertIn(
            'negative total amount',
            platform_message,
            f"An ordinary vendor credit note carrying a negative total must be refused by the platform's own validation, in its own words, but it reads {platform_message!r}.",
        )
        self.assertNotIn(
            'greater than zero',
            platform_message,
            f"The vendor-credit-note check must not answer for a document that reverses no bill of ours, but the refusal reads {platform_message!r}.",
        )
        self.assertEqual(
            unlinked_negative_refund.state,
            'draft',
            f"The comparison document must be left in state 'draft' by that refusal, but it reads {unlinked_negative_refund.state!r}.",
        )

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

        Every EUR figure below is compared through EUR itself, at the 0.05
        increment the amount is actually stated in, and each is also compared to
        the cent, because two amounts that differ by less than an increment are
        one amount at that increment and a real difference to the cent.  The
        company currency is used for the figures the books are kept in --
        ``debit``, ``credit`` and ``balance`` -- and for nothing else, so that no
        EUR claim here depends on what precision the company currency happens to
        carry.
        """
        eur = self.setup_other_currency('EUR', rounding=ROUNDING_INCREMENT)
        company_currency = self.company_currency
        # The increment is a configuration figure rather than an amount in any
        # currency, so it is compared at the precision of the field holding it.
        self.assertEqual(
            float_compare(eur.rounding, ROUNDING_INCREMENT, precision_digits=6),
            0,
            f"The alternate currency must carry the non-standard rounding increment {ROUNDING_INCREMENT}, but it reads {eur.rounding}.",
        )
        self.assertNotEqual(
            eur,
            company_currency,
            f"The rounding fixture only proves anything if the document currency differs from the company currency {company_currency.name}.",
        )

        # The rounding contract itself, stated independently of any document:
        # 10.025 / 0.05 = 200.5 is a tie, and half-up takes a tie away from zero.
        rounded_line_amount = eur.round(ROUNDING_LINE_AMOUNT)
        self.assertEqual(
            eur.compare_amounts(rounded_line_amount, ROUNDING_EXPECTED_TOTAL),
            0,
            f"Rounding {ROUNDING_LINE_AMOUNT} at an increment of {ROUNDING_INCREMENT} must give {ROUNDING_EXPECTED_TOTAL:.2f} under half-up, but it gives {rounded_line_amount}.",
        )
        self.assertEqual(
            eur.compare_amounts(rounded_line_amount, ROUNDING_TIE_TOWARD_ZERO),
            1,
            f"Half-up must take the {ROUNDING_LINE_AMOUNT} tie away from zero, so the rounded figure must stand above {ROUNDING_TIE_TOWARD_ZERO:.2f} {eur.name} rather than at it, but it reads {rounded_line_amount}.",
        )
        self.assertEqual(
            float_compare(rounded_line_amount, ROUNDING_EXPECTED_TOTAL, precision_digits=CENT_PRECISION_DIGITS),
            0,
            f"To the cent, rounding {ROUNDING_LINE_AMOUNT} at an increment of {ROUNDING_INCREMENT} must give exactly {ROUNDING_EXPECTED_TOTAL:.2f}, but it gives {rounded_line_amount}.",
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
            eur.compare_amounts(bill.amount_total, ROUNDING_EXPECTED_TOTAL),
            0,
            f"The bill's line amount of {ROUNDING_LINE_AMOUNT} must post as {ROUNDING_EXPECTED_TOTAL:.2f} {eur.name} under half-up rounding, but the bill totals {bill.amount_total}.",
        )
        self.assertEqual(
            float_compare(bill.amount_total, ROUNDING_EXPECTED_TOTAL, precision_digits=CENT_PRECISION_DIGITS),
            0,
            f"To the cent, the bill must total exactly {ROUNDING_EXPECTED_TOTAL:.2f} {eur.name}, but it totals {bill.amount_total}.",
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
            eur.compare_amounts(credit_note.amount_total, ROUNDING_TIE_TOWARD_ZERO),
            1,
            f"The credit note's total must be the tie taken away from zero rather than toward it, so at the {eur.name} increment it must stand above {ROUNDING_TIE_TOWARD_ZERO:.2f} rather than at it, but it totals {credit_note.amount_total}.",
        )
        self.assertEqual(
            float_compare(credit_note.amount_total, ROUNDING_EXPECTED_TOTAL, precision_digits=CENT_PRECISION_DIGITS),
            0,
            f"To the cent, the credit note must total exactly {ROUNDING_EXPECTED_TOTAL:.2f} {eur.name} -- half-up takes the {ROUNDING_LINE_AMOUNT} tie away from zero -- but it totals {credit_note.amount_total}.",
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
            eur.compare_amounts(payable_lines.amount_currency, ROUNDING_EXPECTED_TOTAL),
            0,
            f"The entry must debit Accounts Payable {CODE_ACCOUNTS_PAYABLE} by {ROUNDING_EXPECTED_TOTAL:.2f} {eur.name}, but that line reads {payable_lines.amount_currency}.",
        )
        self.assertEqual(
            float_compare(payable_lines.amount_currency, ROUNDING_EXPECTED_TOTAL, precision_digits=CENT_PRECISION_DIGITS),
            0,
            f"To the cent, the Accounts Payable {CODE_ACCOUNTS_PAYABLE} line must read exactly {ROUNDING_EXPECTED_TOTAL:.2f} {eur.name}, but it reads {payable_lines.amount_currency}.",
        )
        self.assertEqual(
            eur.compare_amounts(expense_lines.amount_currency, -ROUNDING_EXPECTED_TOTAL),
            0,
            f"The entry must credit Expense {CODE_EXPENSE} by {ROUNDING_EXPECTED_TOTAL:.2f} {eur.name}, but that line reads {expense_lines.amount_currency}.",
        )
        self.assertEqual(
            float_compare(expense_lines.amount_currency, -ROUNDING_EXPECTED_TOTAL, precision_digits=CENT_PRECISION_DIGITS),
            0,
            f"To the cent, the Expense {CODE_EXPENSE} line must read exactly {-ROUNDING_EXPECTED_TOTAL:.2f} {eur.name}, but it reads {expense_lines.amount_currency}.",
        )

        # Balance in the source currency.  Which side a line falls on is decided
        # at the EUR increment rather than by the sign of a raw float: a figure
        # smaller than the increment is not a side of the entry, and reading it as
        # one would count rounding noise as a debit or a credit.
        sided_lines = credit_note.line_ids.filtered(lambda line: not eur.is_zero(line.amount_currency))
        self.assertEqual(
            len(sided_lines),
            2,
            f"Measured at the {eur.name} increment the entry must have exactly two sides, but {len(sided_lines)} of its {len(credit_note.line_ids)} journal items carry an amount.",
        )
        source_debit = sum(line.amount_currency for line in sided_lines if eur.compare_amounts(line.amount_currency, 0.0) > 0)
        source_credit = -sum(line.amount_currency for line in sided_lines if eur.compare_amounts(line.amount_currency, 0.0) < 0)
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
        self.assertEqual(
            float_compare(source_debit, ROUNDING_EXPECTED_TOTAL, precision_digits=CENT_PRECISION_DIGITS),
            0,
            f"To the cent, both sides of the entry must measure exactly {ROUNDING_EXPECTED_TOTAL:.2f} {eur.name}, but its total debits measure {source_debit}.",
        )

        # Balance in the company currency, where the books are kept.
        total_debit = sum(credit_note.line_ids.mapped('debit'))
        total_credit = sum(credit_note.line_ids.mapped('credit'))
        self.assertEqual(
            company_currency.compare_amounts(total_debit, total_credit),
            0,
            f"In the company currency {company_currency.name} the entry must balance: total debits of {total_debit} must equal total credits of {total_credit}.",
        )
        self.assertTrue(
            company_currency.is_zero(total_debit - total_credit),
            f"The difference between the entry's total debits and total credits must measure 0.00 {company_currency.name}, but it measures {total_debit - total_credit}.",
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

        Both the rule and its outcome are asserted: neither refund's numbering
        range is narrowed by its source link, and the numbers the journal then
        issued them differ.

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

        # The numbering rule itself, read off the documents rather than inferred
        # from the numbers they came out with: neither refund is numbered within a
        # range narrowed by its source link, which is what leaves them sharing the
        # one refund pool that the platform keeps continuous.
        for refund, label in ((linked_credit_note, 'linked'), (plain_refund, 'unlinked')):
            refund_domain = refund._get_last_sequence_domain()[0]
            self.assertNotIn(
                'debit_origin_id',
                refund_domain,
                f"A vendor credit note must be numbered from the journal's whole refund pool, so its numbering range must not be narrowed by the source link, but the {label} credit note is numbered within {refund_domain!r}.",
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
        vendor bill debit note linked to its source by ``debit_origin_id``, which
        the journal then numbers in the debit-note range it has always kept for
        such a document, apart from the range the bill itself was numbered in; so
        the behaviour the module shipped is preserved for everyone who does not
        ask for the new one.

        Three further things are settled here, because the shipped behaviour is
        what they protect.

        The first is that asking for the new mode is not by itself what produces a
        credit note: the source has to be a vendor bill.  A posted vendor credit
        note is put to the same wizard with the opt-in explicitly set, and the
        result type it maps to is still the vendor bill the module has always
        produced from a credit note, while the request as a whole is refused for
        naming a source that is not a bill.  Read together those two say that the
        mode is decided by the opt-in *and* the source type; a mode decided by the
        opt-in alone would answer the first of them differently.

        The second is that the debit-note range is still keyed on the source link
        for invoice-type documents.  The range each of the two invoice-type
        documents is numbered within is read off the documents themselves, and the
        debit note is then posted so that the number it receives can be compared
        with the bill's own.

        The third is what the mode's own rules take away from nobody.  A credit
        note gives back the charge of one named bill, so a source that is not
        posted has no charge to give back and a selection of several bills does not
        describe one operation a Clerk could review -- it describes as many credit
        notes as there are bills, each linked to a different source and numbered in
        the journal's refund sequence, out of a single unreviewed click.  Both are
        refused, and refused server-side rather than by the form: the two bills
        share a type, so the wizard reads that one type and offers the opt-in.  The
        very same selection is then put through the wizard again with the opt-in
        left alone, and it raises the two debit notes it always did.

        This test raises its own bill rather than reusing one from another
        scenario, which keeps each scenario's Given independent of what another
        left behind.  The wizard screens the source link of the document actually
        selected -- it refuses a selection in which any move carries a
        ``debit_origin_id`` of its own, that is, a selection of debit notes or
        credit notes rather than of bills -- so what a bill already carries on the
        inverse side, in ``debit_note_ids``, is not what stands in the way.
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

        # The opt-in on a source that is not a vendor bill.  A posted vendor credit
        # note still maps to the vendor bill the module has always produced from
        # one, so the new mode is decided by the opt-in together with the source
        # type rather than by the opt-in alone.
        posted_refund = self._create_invoice(
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
        opt_in_wizard = self.env['account.debit.note'].with_context(
            active_model='account.move',
            active_ids=posted_refund.ids,
        ).create({
            'date': fields.Date.from_string(CREDIT_NOTE_DATE),
            'reason': CREDIT_NOTE_REASON,
            'create_vendor_credit_note': True,
        })
        self.assertTrue(
            opt_in_wizard.create_vendor_credit_note,
            "The opt-in must be set for this case, which is what makes the source type the only thing left to decide the result.",
        )
        self.assertEqual(
            opt_in_wizard.move_type,
            'in_refund',
            f"The source of this case must be a vendor credit note, but the wizard reads {opt_in_wizard.move_type!r}.",
        )
        self.assertEqual(
            opt_in_wizard._prepare_default_values(posted_refund)['move_type'],
            'in_invoice',
            "A vendor credit note must still be corrected by a vendor bill, as the module has always done, even when the vendor-credit-note opt-in is set: the new mode applies to a vendor bill and to nothing else.",
        )

        with self.assertRaises(UserError) as refusal:
            opt_in_wizard.create_debit()

        message = str(refusal.exception)
        self.assertIn(
            posted_refund.display_name,
            message,
            f"The refusal must name the document it refuses ({posted_refund.display_name!r}), but it reads {message!r}.",
        )
        self.assertIn(
            'vendor bill',
            message,
            f"The refusal must state the condition the source fails -- only a vendor bill can be credited this way -- but it reads {message!r}.",
        )
        self.assertFalse(
            self.env['account.move'].search([('debit_origin_id', '=', posted_refund.id)]),
            "A source that is not a vendor bill must be left with nothing linked to it.",
        )
        self.assertEqual(
            posted_refund.state,
            'posted',
            f"That source must be left posted by the refusal, but it reads {posted_refund.state!r}.",
        )

        # The debit-note range is still keyed on the source link for invoice-type
        # documents: the bill is numbered among the documents carrying no source
        # link, and its debit note among those that do.
        bill_domain = bill._get_last_sequence_domain()[0]
        debit_note_domain = debit_note._get_last_sequence_domain()[0]
        self.assertIn(
            'debit_origin_id IS NULL',
            bill_domain,
            f"A vendor bill must be numbered among the documents of its journal that carry no source link, but it is numbered within {bill_domain!r}.",
        )
        self.assertIn(
            'debit_origin_id IS NOT NULL',
            debit_note_domain,
            f"A vendor bill debit note must be numbered among the documents of its journal that do carry a source link, which is the range the module has always given it, but it is numbered within {debit_note_domain!r}.",
        )

        # And the numbers themselves: the debit note is given a line so that it
        # can be posted, and the number it receives comes from its own range and
        # not from the range the bill was numbered in.
        debit_note.write({
            'invoice_line_ids': [
                Command.create({
                    'name': 'Freight undercharged on the original bill',
                    'quantity': 1.0,
                    'price_unit': AMOUNT_FREIGHT,
                    'tax_ids': [],
                    'account_id': self.account_expense_6100.id,
                }),
            ],
        })
        debit_note.action_post()
        self.assertEqual(
            debit_note.state,
            'posted',
            f"The debit note must post, as it always did, but it reads state {debit_note.state!r}.",
        )
        self.assertEqual(
            debit_note.sequence_prefix,
            f'D{bill.sequence_prefix}',
            f"A posted vendor bill debit note must be numbered in the journal's own debit-note range, D followed by the range the bill was numbered in ({bill.sequence_prefix!r}), but it reads {debit_note.sequence_prefix!r}.",
        )
        self.assertNotEqual(
            debit_note.name,
            bill.name,
            f"The debit note must carry a number of its own rather than the bill's, but both read {debit_note.name!r}.",
        )
        self.assertEqual(
            debit_note.debit_origin_id,
            bill,
            f"Posting must leave the debit note linked to the bill it corrects, but debit_origin_id reads {debit_note.debit_origin_id.display_name!r}.",
        )

        # A source that is not posted.  The wizard is reached with ``move_ids``
        # written directly, which is the path on which the Debit Note action's own
        # screening of the selection never runs.
        draft_bill = self._create_invoice(
            move_type='in_invoice',
            invoice_date=fields.Date.from_string(BILL_DATE),
            date=fields.Date.from_string(BILL_DATE),
            post=False,
            partner_id=self.vendor,
            journal_id=self.purchase_journal,
            currency_id=self.company_currency,
            invoice_line_ids=[
                self._prepare_invoice_line(
                    name=LINE_SUBSCRIPTION,
                    price_unit=AMOUNT_SUBSCRIPTION,
                    quantity=1.0,
                    tax_ids=[],
                    account_id=self.account_expense_6100,
                ),
            ],
        )
        self.assertEqual(
            draft_bill.state,
            'draft',
            f"This source must stand in state 'draft' for it to be the unposted case, but it reads {draft_bill.state!r}.",
        )
        draft_wizard = self.env['account.debit.note'].create({
            'date': fields.Date.from_string(CREDIT_NOTE_DATE),
            'reason': CREDIT_NOTE_REASON,
            'copy_lines': True,
            'create_vendor_credit_note': True,
            'move_ids': [Command.set(draft_bill.ids)],
        })
        with self.assertRaises(UserError) as refusal:
            draft_wizard.create_debit()

        message = str(refusal.exception)
        self.assertIn(
            draft_bill.display_name,
            message,
            f"The refusal must name the document it refuses ({draft_bill.display_name!r}), but it reads {message!r}.",
        )
        self.assertIn(
            'not posted',
            message,
            f"The refusal must state the condition the source fails -- it is not posted -- but it reads {message!r}.",
        )
        self.assertFalse(
            self.env['account.move'].search([('debit_origin_id', '=', draft_bill.id)]),
            "A draft bill must be left with no credit note linked to it.",
        )

        # Several selected bills at once, refused in vendor-credit-note mode.
        first_bill = self._create_story_bill()
        second_bill = self._create_story_bill()
        bills = first_bill + second_bill
        multi_wizard = self.env['account.debit.note'].with_context(
            active_model='account.move',
            active_ids=bills.ids,
        ).create({
            'date': fields.Date.from_string(CREDIT_NOTE_DATE),
            'reason': CREDIT_NOTE_REASON,
            'copy_lines': True,
            'create_vendor_credit_note': True,
        })
        self.assertEqual(
            multi_wizard.move_type,
            'in_invoice',
            f"A selection of vendor bills alone must read one source type, which is what exposes the opt-in and makes this refusal necessary, but the wizard reads {multi_wizard.move_type!r}.",
        )
        self.assertEqual(
            len(multi_wizard.move_ids),
            2,
            f"The wizard must hold both selected bills for this to be the multi-source case, but it holds {len(multi_wizard.move_ids)}.",
        )
        with self.assertRaises(UserError) as refusal:
            multi_wizard.create_debit()

        message = str(refusal.exception)
        self.assertIn(
            'exactly one vendor bill',
            message,
            f"The refusal must state the rule that failed -- a vendor credit note credits exactly one bill -- but it reads {message!r}.",
        )
        self.assertIn(
            'Create Vendor Credit Note',
            message,
            f"The refusal must state the remedy in the words of the control the Clerk ticked, but it reads {message!r}.",
        )
        self.assertFalse(
            self.env['account.move'].search([('debit_origin_id', 'in', bills.ids)]),
            "A refused multi-bill request must leave no credit note behind for either bill, not even one of the two.",
        )
        for refused_bill in bills:
            self.assertEqual(
                refused_bill.state,
                'posted',
                f"The bill {refused_bill.name} must be left posted by the refusal, but it reads {refused_bill.state!r}.",
            )
            self.assertEqual(
                self.company_currency.compare_amounts(refused_bill.amount_total, AMOUNT_BILL_TOTAL),
                0,
                f"The bill {refused_bill.name} must still total {AMOUNT_BILL_TOTAL:.2f} {self.company_currency.name} after the refusal, but it totals {refused_bill.amount_total}.",
            )

        # The same selection with the opt-in left alone: one debit note per bill,
        # exactly as the module shipped it.  The one-bill rule is a rule of the new
        # mode and takes nothing away from the old one.
        shipped_wizard = self.env['account.debit.note'].with_context(
            active_model='account.move',
            active_ids=bills.ids,
        ).create({
            'date': fields.Date.from_string(CREDIT_NOTE_DATE),
            'reason': 'Freight undercharged on both bills',
        })
        self.assertFalse(
            shipped_wizard.create_vendor_credit_note,
            "The opt-in must read false unless the Clerk sets it, which is what leaves the multi-document debit-note path open.",
        )
        shipped_wizard.create_debit()

        debit_notes = self.env['account.move'].search([('debit_origin_id', 'in', bills.ids)])
        self.assertEqual(
            len(debit_notes),
            2,
            f"Both selected bills must receive a debit note, as they always did, but {len(debit_notes)} were created.",
        )
        self.assertEqual(
            set(debit_notes.mapped('move_type')),
            {'in_invoice'},
            f"Without the opt-in every result must remain a vendor bill debit note, but the results read the types {set(debit_notes.mapped('move_type'))}.",
        )
        self.assertEqual(
            set(debit_notes.mapped('state')),
            {'draft'},
            f"Every debit note must be created in draft, as it always was, but the results read the states {set(debit_notes.mapped('state'))}.",
        )
        for corrected_bill in bills:
            self.assertEqual(
                len(corrected_bill.debit_note_ids),
                1,
                f"The bill {corrected_bill.name} must carry exactly one debit note of its own, but it reports {len(corrected_bill.debit_note_ids)}.",
            )
            self.assertEqual(
                corrected_bill.debit_note_ids.journal_id,
                corrected_bill.journal_id,
                f"The debit note of bill {corrected_bill.name} must sit in that bill's own journal, but it reads {corrected_bill.debit_note_ids.journal_id.display_name!r}.",
            )
