# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""Acceptance tests for STORY-001-02-05 -- vendor credit notes raised from a posted vendor bill.

Scope: Scenario 1 of that story -- the returned line reverses as one balanced
credit note debiting Accounts Payable 2000 and crediting Expense 6100 -- and the
amount-validation portion of Scenario 4, which refuses a linked vendor credit note
carrying no value.  Allocation, tax reversal, cash refund and lock-date behaviour
are out of scope and are not exercised; the boundary assertions that keep them out
of the delivered behaviour, such as an empty ``reversed_entry_id``, do remain.

    T-VCN-001-01  Vendor credit note reverses one bill line as one balanced entry
    T-VCN-001-02  Zero-value credit note refused, no posted ledger entry
    T-VCN-001-03  Negative-value credit note refused, no posted ledger entry
    T-VCN-001-04  Credit note posts in the bill currency with HALF-UP rounding
    T-VCN-001-05  Credit note sequence distinct from a plain unlinked refund
    T-VCN-001-06  Default vendor-bill path remains a debit note

Each test docstring begins with its BDD identifier, so the test runner prints the
scenario-to-method mapping and a failing line is traceable to its story criterion.

``@tagged('post_install', '-at_install')``: the ``create_vendor_credit_note``
opt-in, the wizard form exposing it and the wizard's access rights exist in the
registry only once ``account_debit_note`` has finished installing.
"""

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import Form, tagged
from odoo.tools.float_utils import float_compare

from odoo.addons.account.tests.common import AccountTestInvoicingCommon

CODE_ACCOUNTS_PAYABLE = '2000'
CODE_EXPENSE = '6100'

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

BILL_DATE = '2025-03-14'
CREDIT_NOTE_DATE = '2025-03-20'
PLAIN_REFUND_DATE = '2025-03-25'

CREDIT_NOTE_REFERENCE = 'CN-2024-0117'
CREDIT_NOTE_REASON = f'Vendor credit note {CREDIT_NOTE_REFERENCE}'

# Quantity 2.5 x unit price 4.01 is exactly 10.025, a tie at an increment of 0.05;
# HALF-UP takes a tie away from zero, so 10.05 posts rather than 10.00.
ROUNDING_INCREMENT = 0.05
ROUNDING_QUANTITY = 2.5
ROUNDING_UNIT_PRICE = 4.01
ROUNDING_LINE_AMOUNT = 10.025
ROUNDING_EXPECTED_TOTAL = 10.05
ROUNDING_TIE_TOWARD_ZERO = 10.0
CENT_PRECISION_DIGITS = 2

AMOUNT_PLAIN_REFUND = 1000.0

OTHER_PURCHASE_JOURNAL_NAME = 'Secondary Purchases'
OTHER_PURCHASE_JOURNAL_CODE = 'BILL2'

# The wizard form the Debit Note action opens, named so that the form-level
# assertions read the arch the Clerk is served.
WIZARD_FORM_VIEW = 'account_debit_note.view_account_debit_note'


@tagged('post_install', '-at_install')
class TestVendorCreditNote(AccountTestInvoicingCommon):
    """STORY-001-02-05 -- Manage Vendor Credit Notes and Refunds.

    Story: ``tickets/EPIC-001/FEATURE-001-02/STORY-001-02-05-manage-vendor-credit-notes.md``.

    The suite builds on ``AccountTestInvoicingCommon`` and seeds only what the
    story names and the generic chart does not carry in that shape: Accounts
    Payable 2000, Expense 6100 and the vendor whose payable property points at
    2000.  Method naming: ``test_vcn_001_<NN>_<snake_summary>``, ``<NN>`` being
    the BDD scenario number zero-padded to two digits.

    Monetary assertions go through ``res.currency.compare_amounts`` for "these two
    amounts are equal" and ``res.currency.is_zero`` for "this difference is zero",
    rounding before the subtraction and rounding after it not being the same test.
    In ``test_vcn_001_04`` the 0.05-denominated EUR values under test are also
    compared with ``float_compare(..., precision_digits=2)``, since 10.03 and 10.05
    are one amount at an increment of 0.05.  A keyed or copied value, such as a
    quantity or a unit price, is compared exactly.

    Branch-to-test mapping
    ----------------------
        * ``account.debit.note._prepare_default_values``: the opt-in branch on an
          ``in_invoice`` source, producing ``in_refund`` -> 01 / 04 / 05; the
          opt-in on a source that is not a vendor bill, where the existing
          refund-to-invoice mapping still decides the result -> 06; the
          default-off path, for one selected bill and for several -> 06 (and, for
          the other source types, the module's existing suite).
        * ``account.move._check_vendor_credit_note_positive_total``: raising on a
          linked ``in_refund`` whose currency-rounded total is not above zero ->
          02 (zero, keyed and by carrying no line at all) / 03 (negative); passing
          on a positive total -> 01 / 04 / 05; inapplicable without a source link
          -> 02 / 03; inapplicable for a vendor bill rather than a credit note
          -> 02.
        * ``account.move._post``: delegation to ``super()._post(soft=soft)`` after
          the guard passes -> 01 / 04 / 05 / 06; refusal raised before
          ``super()._post`` is entered -> 02 / 03.
        * ``account.move._get_last_sequence_domain``: the ``in_refund`` path,
          excluded from the debit-origin split so linked and unlinked refunds
          share one refund pool -> 05; the retained invoice-type split, a bill
          numbered among documents carrying no source link and its debit note
          among those that do -> 06.
        * the opt-in's own visibility on the wizard form, which the arch decides
          from the source type alone: offered for a posted vendor bill and served
          unticked -> 01; withheld for a source that is not a vendor bill -> 06.
        * the journal the copy is recorded in, taken from Use Specific Journal
          when it is named and from the source's own journal otherwise -> 01
          (names the bill's journal) / 02 / 03 / 04 / 05 / 06 (leave it empty).
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.company_currency = cls.company_data['currency']
        cls.purchase_journal = cls.company_data['default_journal_purchase']

        # A loaded chart pads its template codes out to the chart's code width, so
        # 2000 and 6100 are free to be created unless the chart itself carries them.
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

    @classmethod
    def _vcn_account(cls, code, name, account_type, reconcile):
        """Return the account carrying ``code`` in the test company, creating it if absent.

        The lookup is company-scoped and made with ``active_test=False``, because an
        archived account keeps its code and skipping it would put a second account
        on the same code.  A code the chart carries is reused and brought to what
        the story names in a single ``write``: a payable account that is not
        reconcilable is refused, so type and reconciliation flag must land together.
        The flag is only ever turned on, turning it off being refused while partial
        reconciliations are pending.
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

        A posted ``in_invoice`` in the company's Purchase journal for the story's
        vendor, carrying untaxed lines coded to Expense 6100 and a single payable
        line on Accounts Payable 2000.  ``lines`` is a sequence of
        ``(name, price_unit, quantity)`` tuples and defaults to the story's three
        lines of 6,000.00, 4,200.00 and 2,250.00.  The fixture supplies no taxes
        explicitly, Scenario 1 of the story being the untaxed reversal; the taxed
        one is Scenario 2 and is out of scope here.
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

    def _create_vendor_credit_note(self, bill, keep_line=LINE_SUBSCRIPTION, reason=CREDIT_NOTE_REASON, date=CREDIT_NOTE_DATE, journal=None, copy_lines=True):
        """Raise a draft, linked vendor credit note from ``bill`` and return it.

        The Debit Note wizard is opened through the ``active_model``/``active_ids``
        context the Debit Note action supplies, with ``create_vendor_credit_note``
        set, so the copy comes out as an ``in_refund``.  ``journal`` names a journal
        under Use Specific Journal; left out, the field stays empty.

        ``copy_lines`` brings across every line of the bill, so the copy is trimmed
        to the line named ``keep_line`` -- the story credits line 2 alone; pass
        ``keep_line=False`` to keep the copy as the wizard produced it.  Passing
        ``copy_lines=False`` is the route that produces a credit note carrying no line
        at all, the wizard clearing the copied lines instead of bringing them across.

        The entry count is taken before and after, because "one linked move" and
        "one new move" are different statements and the story allows one entry.
        """
        wizard = self.env['account.debit.note'].with_context(
            active_model='account.move',
            active_ids=bill.ids,
        ).create({
            'date': fields.Date.from_string(date),
            'reason': reason,
            'copy_lines': copy_lines,
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

    def _wizard_form(self, moves):
        """Open the Debit Note wizard on ``moves`` as the form the Clerk is served.

        ``Form`` loads the wizard's own arch and applies its modifiers, so an
        assertion made through it states what the screen offers, hides and refuses
        to let a field be set to, rather than what the model underneath it accepts.
        The form is not saved: a request that is meant to be carried out is made
        through ``_create_vendor_credit_note`` instead.
        """
        return Form(
            self.env['account.debit.note'].with_context(
                active_model='account.move',
                active_ids=moves.ids,
            ),
            view=WIZARD_FORM_VIEW,
        )

    def _posted_movement(self, account, partner):
        """Return the signed posted balance ``partner`` carries on ``account``.

        Only items of posted moves are counted, so a draft or refused document
        contributes nothing, and a vendor obligation sitting on the credit side
        makes the figure negative while money is owed.
        """
        lines = self.env['account.move.line'].search([
            ('account_id', '=', account.id),
            ('partner_id', '=', partner.id),
            ('parent_state', '=', 'posted'),
        ])
        return sum(lines.mapped('balance'))

    def _assert_unnumbered(self, move, document_label):
        """Assert that ``move`` carries no journal sequence number.

        ``/`` is the number a document reads until a journal numbers it at posting,
        so a document that drew a number, one that consumed a sequence position and
        one numbered then returned to draft each fail on their own assertion.
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

        Keying on the id makes the comparison an identity check as well as a value
        check: a line replaced by another carrying the same amount is a different
        record, and a reversal must leave the source document alone.
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

        The document's own currency measures the line amount and
        ``amount_currency``; the company currency measures ``debit``, ``credit``
        and ``balance``.  Keyed values -- quantity, unit price, account, name --
        are compared exactly, any difference in them being a rewrite.
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

    def _assert_refused_credit_note(self, credit_note, bill, payable_before, lines_before, description, expected_payable=-AMOUNT_BILL_TOTAL):
        """Assert the shared outcome of a refused linked vendor credit note.

        A refusal leaves the credit note draft and unnumbered, linked by
        ``debit_origin_id`` alone, and leaves the source bill and Accounts Payable
        2000 as ``lines_before`` and ``payable_before`` recorded them.
        ``expected_payable`` is what the vendor must still owe on 2000 in absolute
        terms, which is one bill's total unless a case has posted more than one bill.
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
            currency.compare_amounts(payable_after, expected_payable),
            0,
            f"The vendor must still owe every posted bill in full after the refusal: Accounts Payable {CODE_ACCOUNTS_PAYABLE} must read {expected_payable:.2f} {currency.name}, but it reads {payable_after}.",
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

        Given a posted vendor bill in the Purchase journal of the test company for
        Acme Industrial Supplies, dated 2025-03-14, carrying three untaxed lines of
        6,000.00, 4,200.00 and 2,250.00 against Expense 6100 that total 12,450.00,
        and one open payable line of 12,450.00 on Accounts Payable 2000,
        When the returned software subscription of 4,200.00 is credited back through
        the Debit Note wizard in vendor-credit-note mode and the result is posted,
        dated 2025-03-20,
        Then exactly one linked ``account.move`` with ``move_type = 'in_refund'``
        stands posted in the same Purchase journal and the same currency, carrying
        the accounting date and the credit-note date 2025-03-20, a reference that
        names the bill it reverses, and a sequence number issued by that journal; it
        debits Accounts Payable 2000 by 4,200.00 on one payable line carrying the
        vendor and credits Expense 6100 by 4,200.00, its total debits equal its
        total credits at a difference of 0.00, and the source bill is left posted
        with its three lines unchanged.

        The bill's own Purchase journal is named under Use Specific Journal, so the
        journal the entry is numbered in is the one the request asked for rather than
        the one it would have fallen back to.  The form is read before the request is
        made, because the opt-in is a control the Clerk is offered rather than a flag a
        caller passes: for a vendor bill the form offers it and serves it unticked.
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

        # What the form offers for this selection, before the same request is made
        # against the model: the opt-in is the one control this change adds to the
        # screen, and the form offers it exactly where the new branch can fire.
        wizard_form = self._wizard_form(bill)
        self.assertEqual(
            wizard_form.move_type,
            'in_invoice',
            f"The form must read the source type from the selected bill, which is what decides whether the opt-in is offered, but it reads {wizard_form.move_type!r}.",
        )
        self.assertFalse(
            wizard_form._get_modifier('create_vendor_credit_note', 'invisible'),
            "The opt-in must be offered on the form for a posted vendor bill, which is the one source the new branch acts on.",
        )
        self.assertFalse(
            wizard_form.create_vendor_credit_note,
            "The form must serve the opt-in unticked, so that a Clerk who does not ask for a credit note still receives the debit note the wizard has always produced.",
        )

        credit_note = self._create_vendor_credit_note(bill, journal=bill.journal_id)

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

        payable_after = self._posted_movement(self.account_payable_2000, self.vendor)
        self.assertEqual(
            currency.compare_amounts(payable_after, payable_before + AMOUNT_SUBSCRIPTION),
            0,
            f"The posted credit note must reduce the vendor's Accounts Payable {CODE_ACCOUNTS_PAYABLE} balance by {AMOUNT_SUBSCRIPTION:.2f} {currency.name}: it read {payable_before} before and must read {payable_before + AMOUNT_SUBSCRIPTION} after, but it reads {payable_after}.",
        )

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
        self._assert_move_lines_unchanged(bill, lines_before, 'the reversed bill')

    # =========================================================================
    # T-VCN-001-02: A credit note carrying no value cannot post and nothing
    #               reaches Accounts Payable 2000
    # =========================================================================

    def test_vcn_001_02_zero_value_credit_note_refused_no_entry_created(self):
        """T-VCN-001-02: a zero-value credit note is refused and posts no ledger entry.

        Given a draft, linked vendor credit note in the Purchase journal of the test
        company for Acme Industrial Supplies, dated 2025-03-20, whose one product
        line was keyed at a quantity of 0.00 so that the document totals 0.00, while
        the source bill stands posted with an open payable of 12,450.00,
        When the Clerk attempts to post that credit note,
        Then posting is refused with a validation message that names the document and
        the check that failed and states the remedy, the record stays in state
        'draft' with no sequence number issued by the journal, and the movement the
        refused attempt contributed to Accounts Payable 2000 measures 0.00.  A draft
        move remains; what must not exist is a posted ledger entry.

        Three further readings stand here, each in its own subTest so that one
        failing hides none of the others.  The route that reaches the same refusal
        without a keyed line -- the opt-in taken with Copy Lines left off, so the copy
        carries no line at all -- is put through the same attempt: the module's check
        runs before the platform's own guard against an empty document, so it is the
        credit-note message that answers, while an unlinked document carrying no line
        still reads the platform's own words.  And both halves of the guard's predicate
        are exercised by carrying the same 0.00 total past it twice, on an unlinked
        vendor credit note and on a linked vendor bill debit note, which both post.
        """
        bill = self._create_story_bill()
        currency = bill.currency_id
        lines_before = self._snapshot_move_lines(bill)
        payable_before = self._posted_movement(self.account_payable_2000, self.vendor)

        credit_note = self._create_vendor_credit_note(bill)
        credited_line = credit_note.invoice_line_ids
        credited_line.ensure_one()
        credited_line.quantity = 0.0

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

        with self.subTest('a linked credit note carrying no line at all'):
            no_line_bill = self._create_story_bill()
            no_line_payable_before = self._posted_movement(self.account_payable_2000, self.vendor)
            no_line_lines_before = self._snapshot_move_lines(no_line_bill)
            no_line_credit_note = self._create_vendor_credit_note(no_line_bill, keep_line=False, copy_lines=False)
            self.assertFalse(
                no_line_credit_note.line_ids,
                f"Leaving Copy Lines off must produce a credit note carrying no journal item at all, which is the other route to a document of no value, but it carries {len(no_line_credit_note.line_ids)}.",
            )
            self.assertTrue(
                currency.is_zero(no_line_credit_note.amount_total),
                f"A credit note carrying no line must total 0.00 {currency.name}, but it totals {no_line_credit_note.amount_total}.",
            )

            with self.assertRaises(UserError) as no_line_refusal:
                no_line_credit_note.action_post()

            no_line_message = str(no_line_refusal.exception)
            self.assertIn(
                'greater than zero',
                no_line_message,
                f"The credit-note check runs before the platform's guard against an empty document, so a linked credit note carrying no line must read the credit-note message, but it reads {no_line_message!r}.",
            )
            self.assertNotIn(
                "Even magicians can't post nothing!",
                no_line_message,
                f"That same ordering means the platform's own words cannot be what this document is refused with, but it reads {no_line_message!r}.",
            )
            self._assert_refused_credit_note(
                no_line_credit_note,
                no_line_bill,
                no_line_payable_before,
                no_line_lines_before,
                'no-line',
                expected_payable=-2 * AMOUNT_BILL_TOTAL,
            )

            unlinked_no_line_refund = self._create_invoice(
                move_type='in_refund',
                invoice_date=fields.Date.from_string(PLAIN_REFUND_DATE),
                date=fields.Date.from_string(PLAIN_REFUND_DATE),
                post=False,
                partner_id=self.vendor,
                journal_id=self.purchase_journal,
                currency_id=self.company_currency,
                invoice_line_ids=[],
            )
            self.assertFalse(
                unlinked_no_line_refund.debit_origin_id,
                "The comparison document must carry no source link, which is what leaves the platform's own guard to answer for it.",
            )
            self.assertFalse(
                unlinked_no_line_refund.line_ids,
                f"The comparison document must carry no journal item either, but it carries {len(unlinked_no_line_refund.line_ids)}.",
            )

            with self.assertRaises(UserError) as platform_no_line_refusal:
                unlinked_no_line_refund.action_post()

            platform_no_line_message = str(platform_no_line_refusal.exception)
            self.assertIn(
                "Even magicians can't post nothing!",
                platform_no_line_message,
                f"A document carrying no line and reversing no bill of ours must be refused by the platform's own guard, in its own words, but it reads {platform_no_line_message!r}.",
            )
            self.assertEqual(
                unlinked_no_line_refund.state,
                'draft',
                f"That refusal must leave the comparison document in state 'draft', but it reads {unlinked_no_line_refund.state!r}.",
            )
            # The comparison document reads an unset name rather than the '/' the
            # wizard hands a credit note it raises: both say the journal has not
            # numbered the document, and only the wizard's copy is given the '/'.
            self.assertIn(
                unlinked_no_line_refund.name,
                (False, '/'),
                f"That refusal must leave the comparison document unnumbered by its journal, but it reads a number of {unlinked_no_line_refund.name!r}.",
            )
            self.assertFalse(
                unlinked_no_line_refund.sequence_number,
                f"That refusal must leave the comparison document occupying no position in the journal's sequence, but it reads sequence number {unlinked_no_line_refund.sequence_number}.",
            )

        with self.subTest('an unlinked vendor credit note carrying no value'):
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

        with self.subTest('a linked vendor bill debit note carrying no value'):
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
        """T-VCN-001-03: a negative-value credit note is refused and posts no ledger entry.

        Given a draft, linked vendor credit note in the Purchase journal of the test
        company for Acme Industrial Supplies, dated 2025-03-20, whose one product
        line was keyed at a negative unit price so that the document totals
        -4,200.00, while the source bill stands posted with an open payable of
        12,450.00,
        When the Clerk attempts to post that credit note,
        Then posting is refused by the vendor-credit-note check rather than by
        account's own negative-total message, the record stays in state 'draft' with
        no sequence number issued by the journal, and the movement the refused
        attempt contributed to Accounts Payable 2000 measures 0.00.  A draft move
        remains; what must not exist is a posted ledger entry.

        An unlinked vendor credit note carrying the same negative total is put
        through the same attempt, and reads account's own refusal instead, so the
        check's requirement for a source bill is asserted rather than assumed.
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

        Given a posted vendor bill denominated in EUR, a currency configured with a
        rounding increment of 0.05 rather than the usual 0.01, carrying one untaxed
        line whose amount before rounding is exactly 10.025 -- a tie at that
        increment,
        When that line is credited back through the Debit Note wizard in
        vendor-credit-note mode and the result is posted,
        Then the credit note is denominated in the bill's own EUR rather than in the
        company currency, its total is the 10.05 that half-up rounding produces by
        taking the tie away from zero, and the entry balances at a difference of 0.00
        in both the document currency and the company currency.

        The EUR figures under test are compared through EUR, at the 0.05 increment
        they are stated in, and to the cent as well, since two amounts differing by
        less than an increment are one amount at that increment.  ``debit``,
        ``credit`` and ``balance`` are read in the company currency and nothing else
        is, so no EUR claim depends on the company currency's precision.
        """
        eur = self.setup_other_currency('EUR', rounding=ROUNDING_INCREMENT)
        company_currency = self.company_currency
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

        Given a posted vendor bill in the Purchase journal of the test company, that
        journal keeping a dedicated debit-note sequence as well as the refund
        sequence of ``account``,
        When one linked vendor credit note dated 2025-03-20 and one ordinary unlinked
        vendor credit note dated 2025-03-25 are both posted in that same journal and
        the same month,
        Then both post and receive different sequence numbers, so that two refunds
        cannot be numbered alike: refunds share one refund pool, and the
        debit-origin domain split that would otherwise hand both of them the same
        next number applies only to invoice-type documents.

        Both the rule and its outcome are asserted: neither refund's numbering range
        is narrowed by its source link, and the numbers the journal issued differ.
        The unlinked refund is built directly, the wizard producing only documents
        that carry a source link.
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

        for refund, label in ((linked_credit_note, 'linked'), (plain_refund, 'unlinked')):
            refund_domain = refund._get_last_sequence_domain()[0]
            self.assertNotIn(
                'debit_origin_id',
                refund_domain,
                f"A vendor credit note must be numbered from the journal's whole refund pool, so its numbering range must not be narrowed by the source link, but the {label} credit note is numbered within {refund_domain!r}.",
            )

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
    # T-VCN-001-06: Without the opt-in, a posted vendor bill still produces a
    #               vendor bill debit note
    # =========================================================================

    def test_vcn_001_06_default_vendor_bill_path_remains_debit_note(self):
        """T-VCN-001-06: without the opt-in a vendor bill still produces a debit note.

        Given a posted vendor bill in the Purchase journal of the test company,
        raised in the same way as the bill every other scenario here reverses,
        When the Clerk runs the Debit Note wizard against it without asking for a
        vendor credit note,
        Then the opt-in reads false by default and the result is a draft vendor bill
        debit note linked to its source by ``debit_origin_id``, which the journal
        numbers in the debit-note range kept for such a document, apart from the
        range the bill itself was numbered in.

        Two further readings of the default-off path are settled here.  The opt-in
        alone does not produce a credit note: set on a posted vendor credit note, the
        existing refund-to-invoice mapping still decides the result and a vendor bill
        is what comes out, because the new branch acts on a vendor bill and on nothing
        else, which the form states as well by withholding the option for that source.
        And the debit-origin split still keys the debit-note range of invoice-type
        documents, both ranges being read off the documents and the debit note posted to
        compare its number with the bill's, while a selection of several bills with the
        opt-in left alone still raises one debit note per bill.
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

        with self.subTest('the opt-in set on a source that is not a vendor bill'):
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
            refund_form = self._wizard_form(posted_refund)
            self.assertTrue(
                refund_form._get_modifier('create_vendor_credit_note', 'invisible'),
                "The form must withhold the opt-in for a source that is not a vendor bill, which the arch decides from the source type alone.",
            )
            self.assertEqual(
                opt_in_wizard._prepare_default_values(posted_refund)['move_type'],
                'in_invoice',
                "A vendor credit note must still be corrected by a vendor bill, as the module has always done, even when the vendor-credit-note opt-in is set: the new mode applies to a vendor bill and to nothing else.",
            )

            opt_in_wizard.create_debit()

            refund_correction = self.env['account.move'].search([('debit_origin_id', '=', posted_refund.id)])
            refund_correction.ensure_one()
            self.assertEqual(
                refund_correction.move_type,
                'in_invoice',
                f"With the opt-in set on a source that is not a vendor bill, the existing refund-to-invoice mapping must still decide the result, so a vendor bill must come out but it reads move_type {refund_correction.move_type!r}.",
            )
            self.assertEqual(
                refund_correction.state,
                'draft',
                f"That result must be created in draft, as the module has always done, but it reads state {refund_correction.state!r}.",
            )
            self.assertEqual(
                refund_correction.debit_origin_id,
                posted_refund,
                f"That result must stay linked to the vendor credit note it corrects, but debit_origin_id reads {refund_correction.debit_origin_id.display_name!r}.",
            )
            self.assertEqual(
                posted_refund.state,
                'posted',
                f"The source must be left posted, but it reads {posted_refund.state!r}.",
            )

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

        with self.subTest('several selected bills with the opt-in left alone'):
            first_bill = self._create_story_bill()
            second_bill = self._create_story_bill()
            bills = first_bill + second_bill
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
