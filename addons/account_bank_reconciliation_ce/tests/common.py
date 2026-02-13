# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Shared test fixtures and helper utilities for the Bank Reconciliation CE module.

Provides :class:`BankReconciliationTestCommon` which extends
:class:`~odoo.addons.account.tests.common.AccountTestInvoicingCommon` with
bank reconciliation-specific test data:

* Bank journals (``bank_journal``, ``bank_journal_2``)
* Bank, suspense, and write-off accounts
* Sample bank statement with two statement lines (positive and negative)
* Posted customer invoice and vendor bill as matching candidates
* Additional partners for reconciliation-specific scenarios
* Helper methods for creating statement lines, invoices, and bills on the fly
* Static generators for sample CSV, OFX, QIF, and CAMT.053 file content
  (base64-encoded, ready for Odoo ``Binary`` field assignment)

All dependent test modules in ``account_bank_reconciliation_ce`` import this
class to obtain consistent, reusable test data and avoid fixture duplication.
"""

import base64
import os

from odoo import Command, fields
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class BankReconciliationTestCommon(AccountTestInvoicingCommon):
    """Base test class with shared fixtures for bank reconciliation tests.

    Inherits all fixtures from :class:`AccountTestInvoicingCommon` including:

    * ``company_data`` dict with default journals, accounts, taxes
    * ``partner_a``, ``partner_b``
    * ``product_a``, ``product_b``
    * ``tax_sale_a``, ``tax_purchase_a``
    * The :meth:`collect_company_accounting_data` helper

    Adds bank-reconciliation-specific data such as bank journals, a sample
    bank statement with lines, posted invoices/bills for matching, additional
    partners, and utility methods for dynamic test data creation.
    """

    @classmethod
    def setUpClass(cls):
        """Prepare common test data for all bank reconciliation tests."""
        super().setUpClass()

        # ==== Bank Journals ====
        # Primary bank journal from the standard company_data fixture
        cls.bank_journal = cls.company_data['default_journal_bank']
        # Second bank journal for multi-journal / cross-journal tests
        cls.bank_journal_2 = cls.bank_journal.copy()

        # ==== Bank & Suspense Accounts ====
        cls.bank_account = cls.bank_journal.default_account_id
        cls.suspense_account = cls.bank_journal.suspense_account_id

        # ==== Write-off Account ====
        # Used when reconciliation requires small-difference write-off entries.
        # Search for an expense account to avoid reusing the main expense
        # account from company_data (keeps write-off amounts isolated).
        cls.write_off_account = cls.env['account.account'].search([
            ('company_ids', 'in', cls.env.company.ids),
            ('account_type', '=', 'expense'),
        ], limit=1)

        # ==== Additional Partners for Reconciliation Tests ====
        # partner_a and partner_b are already available from the parent class.
        # These additional partners carry reconciliation-specific attributes.
        cls.partner_reconcile = cls.env['res.partner'].create({
            'name': 'Reconciliation Test Partner',
            'email': 'reconcile@test.com',
            'company_id': False,
        })
        cls.partner_supplier = cls.env['res.partner'].create({
            'name': 'Test Supplier Ltd',
            'email': 'supplier@test.com',
            'supplier_rank': 1,
            'company_id': False,
        })

        # ==== Sample Bank Statement ====
        # A statement with two lines:
        #   st_line_1 → positive (customer payment)  → matches test_invoice
        #   st_line_2 → negative (supplier payment)   → matches test_bill
        cls.bank_statement = cls.env['account.bank.statement'].create({
            'name': 'Test Statement 001',
            'line_ids': [
                (0, 0, {
                    'date': fields.Date.today(),
                    'payment_ref': 'Payment INV/2024/001',
                    'partner_id': cls.partner_a.id,
                    'journal_id': cls.bank_journal.id,
                    'amount': 1000.0,
                }),
                (0, 0, {
                    'date': fields.Date.today(),
                    'payment_ref': 'Supplier Payment',
                    'partner_id': cls.partner_b.id,
                    'journal_id': cls.bank_journal.id,
                    'amount': -500.0,
                }),
            ],
        })
        cls.st_line_1 = cls.bank_statement.line_ids.filtered(
            lambda line: line.amount > 0,
        )
        cls.st_line_2 = cls.bank_statement.line_ids.filtered(
            lambda line: line.amount < 0,
        )

        # ==== Sample Posted Invoice (Matching Candidate for st_line_1) ====
        cls.test_invoice = cls.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': cls.partner_a.id,
            'invoice_date': fields.Date.today(),
            'journal_id': cls.company_data['default_journal_sale'].id,
            'invoice_line_ids': [
                Command.create({
                    'name': 'Test Product',
                    'quantity': 1,
                    'price_unit': 1000.0,
                    'account_id': cls.company_data['default_account_revenue'].id,
                }),
            ],
        })
        cls.test_invoice.action_post()
        cls.invoice_receivable_line = cls.test_invoice.line_ids.filtered(
            lambda line: line.account_id.account_type == 'asset_receivable',
        )

        # ==== Sample Posted Bill (Matching Candidate for st_line_2) ====
        cls.test_bill = cls.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': cls.partner_b.id,
            'invoice_date': fields.Date.today(),
            'journal_id': cls.company_data['default_journal_purchase'].id,
            'invoice_line_ids': [
                Command.create({
                    'name': 'Test Expense',
                    'quantity': 1,
                    'price_unit': 500.0,
                    'account_id': cls.company_data['default_account_expense'].id,
                }),
            ],
        })
        cls.test_bill.action_post()
        cls.bill_payable_line = cls.test_bill.line_ids.filtered(
            lambda line: line.account_id.account_type == 'liability_payable',
        )

    # ------------------------------------------------------------------
    # Helper Methods — File Loading
    # ------------------------------------------------------------------

    def _load_test_file(self, filename):
        """Load a sample file from the ``test_files/`` directory.

        Reads the raw bytes of the file located at
        ``<module>/tests/test_files/<filename>`` and returns them as
        base64-encoded bytes suitable for assignment to Odoo ``Binary``
        fields (e.g. the import wizard's ``data_file`` field).

        Args:
            filename (str): Name of the file inside the ``test_files/``
                directory (e.g. ``'sample.csv'``).

        Returns:
            bytes: Base64-encoded file content.

        Raises:
            FileNotFoundError: If the requested file does not exist.
        """
        test_files_dir = os.path.join(
            os.path.dirname(__file__), 'test_files',
        )
        filepath = os.path.join(test_files_dir, filename)
        with open(filepath, 'rb') as fh:
            return base64.b64encode(fh.read())

    # ------------------------------------------------------------------
    # Helper Methods — Statement Lines
    # ------------------------------------------------------------------

    def create_bank_statement_line(self, amount, payment_ref='Test Payment',
                                   partner=None, date=None, journal=None,
                                   statement=None):
        """Create a single bank statement line with sensible defaults.

        This follows the pattern from
        ``addons/account/tests/test_account_bank_statement.py``
        (``create_bank_transaction``) but simplified for reconciliation tests.

        Args:
            amount (float): Transaction amount (positive for credit,
                negative for debit).
            payment_ref (str): Payment reference / label.
            partner (recordset | None): ``res.partner`` record. Omit for
                partner-less transactions.
            date (date | str | None): Transaction date.  Defaults to today.
            journal (recordset | None): ``account.journal`` record.
                Defaults to ``self.bank_journal``.
            statement (recordset | None): ``account.bank.statement`` to
                attach the line to.

        Returns:
            recordset: Created ``account.bank.statement.line`` record.
        """
        vals = {
            'date': date or fields.Date.today(),
            'payment_ref': payment_ref,
            'amount': amount,
            'journal_id': (journal or self.bank_journal).id,
        }
        if partner:
            vals['partner_id'] = partner.id
        if statement:
            vals['statement_id'] = statement.id
        return self.env['account.bank.statement.line'].create(vals)

    # ------------------------------------------------------------------
    # Helper Methods — Invoices / Bills
    # ------------------------------------------------------------------

    def create_posted_invoice(self, amount, partner=None, date=None, ref=None):
        """Create and post a customer invoice (matching candidate).

        Args:
            amount (float): Positive unit price for the single invoice line.
            partner (recordset | None): ``res.partner`` record.
                Defaults to ``self.partner_a``.
            date (date | str | None): Invoice date.  Defaults to today.
            ref (str | None): Optional reference (shown on the journal entry).

        Returns:
            recordset: Posted ``account.move`` record (``move_type='out_invoice'``).
        """
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': (partner or self.partner_a).id,
            'invoice_date': date or fields.Date.today(),
            'ref': ref,
            'journal_id': self.company_data['default_journal_sale'].id,
            'invoice_line_ids': [
                Command.create({
                    'name': ref or 'Test Product',
                    'quantity': 1,
                    'price_unit': amount,
                    'account_id': self.company_data['default_account_revenue'].id,
                }),
            ],
        })
        move.action_post()
        return move

    def create_posted_bill(self, amount, partner=None, date=None, ref=None):
        """Create and post a vendor bill (matching candidate).

        Args:
            amount (float): Positive unit price for the single bill line.
            partner (recordset | None): ``res.partner`` record.
                Defaults to ``self.partner_b``.
            date (date | str | None): Invoice/bill date.  Defaults to today.
            ref (str | None): Optional reference (shown on the journal entry).

        Returns:
            recordset: Posted ``account.move`` record (``move_type='in_invoice'``).
        """
        move = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': (partner or self.partner_b).id,
            'invoice_date': date or fields.Date.today(),
            'ref': ref,
            'journal_id': self.company_data['default_journal_purchase'].id,
            'invoice_line_ids': [
                Command.create({
                    'name': ref or 'Test Expense',
                    'quantity': 1,
                    'price_unit': amount,
                    'account_id': self.company_data['default_account_expense'].id,
                }),
            ],
        })
        move.action_post()
        return move

    # ------------------------------------------------------------------
    # Static Generators — Sample Import File Content
    # ------------------------------------------------------------------
    # Each generator returns ``base64``-encoded bytes suitable for direct
    # assignment to Odoo ``Binary`` fields (e.g. the import wizard's
    # ``data_file`` field).

    @staticmethod
    def _get_sample_csv_content(delimiter=',', encoding='utf-8',
                                include_header=True):
        """Generate sample CSV bank statement content for import testing.

        Produces three transaction lines:
        1. Customer payment   +1 000.00
        2. Supplier payment     -500.00
        3. Bank fee              -25.00

        Args:
            delimiter (str): Column separator (default ``','``).
            encoding (str): Text encoding (default ``'utf-8'``).
            include_header (bool): Whether to prepend a header row.

        Returns:
            bytes: Base64-encoded CSV content.
        """
        lines = []
        if include_header:
            lines.append(delimiter.join([
                'Date', 'Label', 'Amount', 'Reference', 'Partner',
            ]))
        lines.append(delimiter.join([
            '2024-01-15', 'Payment INV/2024/001', '1000.00',
            'REF001', 'partner_a',
        ]))
        lines.append(delimiter.join([
            '2024-01-16', 'Supplier Payment', '-500.00',
            'REF002', 'Test Supplier Ltd',
        ]))
        lines.append(delimiter.join([
            '2024-01-17', 'Bank Fee', '-25.00',
            'FEE001', '',
        ]))
        content = '\n'.join(lines)
        return base64.b64encode(content.encode(encoding))

    @staticmethod
    def _get_sample_ofx_content():
        """Generate minimal OFX (v1 SGML) bank statement content.

        Contains two transactions matching the CSV sample:
        * CREDIT  +1 000.00  (TXN001)
        * DEBIT     -500.00  (TXN002)

        Returns:
            bytes: Base64-encoded OFX content.
        """
        ofx_data = (
            'OFXHEADER:100\n'
            'DATA:OFXSGML\n'
            'VERSION:102\n'
            '<OFX>\n'
            '<BANKMSGSRSV1>\n'
            '<STMTTRNRS>\n'
            '<STMTRS>\n'
            '<CURDEF>USD\n'
            '<BANKACCTFROM>\n'
            '<BANKID>123456789\n'
            '<ACCTID>987654321\n'
            '<ACCTTYPE>CHECKING\n'
            '</BANKACCTFROM>\n'
            '<BANKTRANLIST>\n'
            '<STMTTRN>\n'
            '<TRNTYPE>CREDIT\n'
            '<DTPOSTED>20240115\n'
            '<TRNAMT>1000.00\n'
            '<FITID>TXN001\n'
            '<NAME>Payment INV/2024/001\n'
            '</STMTTRN>\n'
            '<STMTTRN>\n'
            '<TRNTYPE>DEBIT\n'
            '<DTPOSTED>20240116\n'
            '<TRNAMT>-500.00\n'
            '<FITID>TXN002\n'
            '<NAME>Supplier Payment\n'
            '</STMTTRN>\n'
            '</BANKTRANLIST>\n'
            '</STMTRS>\n'
            '</STMTTRNRS>\n'
            '</BANKMSGSRSV1>\n'
            '</OFX>\n'
        )
        return base64.b64encode(ofx_data.encode('utf-8'))

    @staticmethod
    def _get_sample_qif_content():
        """Generate sample QIF (Quicken Interchange Format) content.

        Contains two transactions:
        * 01/15/2024  +1 000.00  Payment INV/2024/001  (REF001)
        * 01/16/2024    -500.00  Supplier Payment       (REF002)

        Returns:
            bytes: Base64-encoded QIF content.
        """
        qif_data = (
            '!Type:Bank\n'
            'D01/15/2024\n'
            'T1000.00\n'
            'PPayment INV/2024/001\n'
            'NREF001\n'
            '^\n'
            'D01/16/2024\n'
            'T-500.00\n'
            'PSupplier Payment\n'
            'NREF002\n'
            '^\n'
        )
        return base64.b64encode(qif_data.encode('utf-8'))

    @staticmethod
    def _get_sample_camt053_content():
        """Generate minimal ISO 20022 CAMT.053 XML bank statement content.

        Structure follows ``urn:iso:std:iso:20022:tech:xsd:camt.053.001.02``:

        * Opening balance (OPBD): 5 000.00 USD  (2024-01-14)
        * Entry 1: CREDIT  1 000.00 USD  INV/2024/001       (2024-01-15)
        * Entry 2: DEBIT     500.00 USD  SUPPLIER/2024/001   (2024-01-16)
        * Closing balance (CLBD): 5 500.00 USD  (2024-01-16)

        Returns:
            bytes: Base64-encoded XML content.
        """
        xml_data = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<Document xmlns="urn:iso:std:iso:20022:tech:xsd:'
            'camt.053.001.02">\n'
            '<BkToCstmrStmt>\n'
            '<Stmt>\n'
            '<Id>STMT001</Id>\n'
            # Opening balance
            '<Bal>\n'
            '<Tp><CdOrPrtry><Cd>OPBD</Cd></CdOrPrtry></Tp>\n'
            '<Amt Ccy="USD">5000.00</Amt>\n'
            '<CdtDbtInd>CRDT</CdtDbtInd>\n'
            '<Dt><Dt>2024-01-14</Dt></Dt>\n'
            '</Bal>\n'
            # Entry 1 — customer payment (credit)
            '<Ntry>\n'
            '<Amt Ccy="USD">1000.00</Amt>\n'
            '<CdtDbtInd>CRDT</CdtDbtInd>\n'
            '<BookgDt><Dt>2024-01-15</Dt></BookgDt>\n'
            '<NtryDtls><TxDtls><Refs>'
            '<EndToEndId>INV/2024/001</EndToEndId>'
            '</Refs></TxDtls></NtryDtls>\n'
            '</Ntry>\n'
            # Entry 2 — supplier payment (debit)
            '<Ntry>\n'
            '<Amt Ccy="USD">500.00</Amt>\n'
            '<CdtDbtInd>DBIT</CdtDbtInd>\n'
            '<BookgDt><Dt>2024-01-16</Dt></BookgDt>\n'
            '<NtryDtls><TxDtls><Refs>'
            '<EndToEndId>SUPPLIER/2024/001</EndToEndId>'
            '</Refs></TxDtls></NtryDtls>\n'
            '</Ntry>\n'
            # Closing balance
            '<Bal>\n'
            '<Tp><CdOrPrtry><Cd>CLBD</Cd></CdOrPrtry></Tp>\n'
            '<Amt Ccy="USD">5500.00</Amt>\n'
            '<CdtDbtInd>CRDT</CdtDbtInd>\n'
            '<Dt><Dt>2024-01-16</Dt></Dt>\n'
            '</Bal>\n'
            '</Stmt>\n'
            '</BkToCstmrStmt>\n'
            '</Document>\n'
        )
        return base64.b64encode(xml_data.encode('utf-8'))
