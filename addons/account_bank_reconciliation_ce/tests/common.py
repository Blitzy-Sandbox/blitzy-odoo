# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Shared test fixtures for the Bank Reconciliation module.

Provides common setup data including bank journals, accounts, partners,
sample bank statement files, and helper methods used across all
bank reconciliation test modules.
"""

import base64
import os
from datetime import date as dt_date

from odoo.tests.common import TransactionCase


class BankReconciliationTestCommon(TransactionCase):
    """Base test class with shared fixtures for bank reconciliation tests.

    Sets up:
      - Company and currency references
      - Bank journal with associated accounts
      - Standard accounts (receivable, payable, expense, bank, suspense)
      - Test partners (customer and supplier)
      - Helper methods for loading sample statement files
      - Helper methods for creating test move lines
    """

    @classmethod
    def setUpClass(cls):
        """Prepare common test data for all bank reconciliation tests."""
        super().setUpClass()

        cls.company = cls.env.company
        cls.currency = cls.company.currency_id

        # -----------------------------------------------------------------
        # Accounts
        # -----------------------------------------------------------------
        AccountAccount = cls.env['account.account']

        cls.account_receivable = AccountAccount.search([
            ('company_ids', 'in', cls.company.ids),
            ('account_type', '=', 'asset_receivable'),
        ], limit=1)

        cls.account_payable = AccountAccount.search([
            ('company_ids', 'in', cls.company.ids),
            ('account_type', '=', 'liability_payable'),
        ], limit=1)

        cls.account_bank = AccountAccount.search([
            ('company_ids', 'in', cls.company.ids),
            ('account_type', '=', 'asset_cash'),
        ], limit=1)

        cls.account_revenue = AccountAccount.search([
            ('company_ids', 'in', cls.company.ids),
            ('account_type', '=', 'income'),
        ], limit=1)

        cls.account_expense = AccountAccount.search([
            ('company_ids', 'in', cls.company.ids),
            ('account_type', '=', 'expense'),
        ], limit=1)

        # Suspense account for unreconciled statement lines
        cls.account_suspense = AccountAccount.search([
            ('company_ids', 'in', cls.company.ids),
            ('account_type', '=', 'asset_current'),
        ], limit=1)

        # -----------------------------------------------------------------
        # Bank journal
        # -----------------------------------------------------------------
        cls.bank_journal = cls.env['account.journal'].search([
            ('type', '=', 'bank'),
            ('company_id', '=', cls.company.id),
        ], limit=1)

        if not cls.bank_journal:
            # Create a minimal bank journal when none exist in demo data
            vals = {
                'name': 'Test Bank',
                'code': 'TBNK',
                'type': 'bank',
                'company_id': cls.company.id,
            }
            if cls.account_bank:
                vals['default_account_id'] = cls.account_bank.id
            cls.bank_journal = cls.env['account.journal'].create(vals)

        # Ensure the bank journal has a suspense account (required for
        # statement line creation in Odoo 19.0).
        if not cls.bank_journal.suspense_account_id:
            suspense_acct = AccountAccount.search([
                ('company_ids', 'in', cls.company.ids),
                ('account_type', '=', 'asset_current'),
            ], limit=1)
            if not suspense_acct:
                suspense_acct = AccountAccount.create({
                    'name': 'Bank Suspense Account',
                    'code': '999999',
                    'account_type': 'asset_current',
                    'company_ids': [(4, cls.company.id)],
                })
            cls.bank_journal.suspense_account_id = suspense_acct

        # -----------------------------------------------------------------
        # Partners
        # -----------------------------------------------------------------
        cls.partner_customer = cls.env['res.partner'].create({
            'name': 'Reconciliation Test Partner',
            'company_id': cls.company.id,
        })
        cls.partner_supplier = cls.env['res.partner'].create({
            'name': 'Test Supplier Ltd',
            'company_id': cls.company.id,
        })

    # -----------------------------------------------------------------
    # Helper - load sample files
    # -----------------------------------------------------------------

    @classmethod
    def _get_test_file_path(cls, filename):
        """Return the absolute path to a sample test file.

        Args:
            filename: Name of the file inside tests/test_files/.

        Returns:
            Absolute path string.
        """
        return os.path.join(
            os.path.dirname(__file__), 'test_files', filename,
        )

    @classmethod
    def _load_test_file(cls, filename):
        """Read a sample test file and return its base64-encoded content.

        Args:
            filename: Name of the file inside tests/test_files/.

        Returns:
            Base64-encoded bytes string suitable for Binary fields.
        """
        filepath = cls._get_test_file_path(filename)
        with open(filepath, 'rb') as fh:
            return base64.b64encode(fh.read())

    # -----------------------------------------------------------------
    # Helper - create journal entries for matching
    # -----------------------------------------------------------------

    @classmethod
    def _create_invoice_move(cls, partner, amount, move_type='out_invoice',
                             ref=None, date_val=None):
        """Create and post a simple journal entry for matching tests.

        Args:
            partner: res.partner record.
            amount: Monetary amount (positive).
            move_type: 'out_invoice' for customer, 'in_invoice' for supplier.
            ref: Optional reference string.
            date_val: Optional date; defaults to today.

        Returns:
            account.move recordset (posted).
        """
        move_date = date_val or dt_date.today()
        move_vals = {
            'move_type': move_type,
            'partner_id': partner.id,
            'date': move_date,
            'invoice_date': move_date,
            'ref': ref or '',
            'journal_id': cls.env['account.journal'].search([
                ('type', '=', 'sale' if move_type == 'out_invoice' else 'purchase'),
                ('company_id', '=', cls.company.id),
            ], limit=1).id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Test line',
                'quantity': 1,
                'price_unit': amount,
            })],
        }
        move = cls.env['account.move'].create(move_vals)
        move.action_post()
        return move
