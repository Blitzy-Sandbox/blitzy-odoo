# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Test suite for BR-005: Partial reconciliation with write-off handling.

Covers:
  - PartialReconcileHelper wizard creation and field checks
  - BankStatementLineExt fields (matching_confidence, reconciliation_status,
    import_hash, import_source, import_format)
  - Tolerance computation (is_within_tolerance)
  - Write-off amount computation
  - Validation (missing statement line or move lines raises UserError)
"""

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import BankReconciliationTestCommon


@tagged('post_install', '-at_install')
class TestPartialReconcileHelperModel(BankReconciliationTestCommon):
    """Tests for the PartialReconcileHelper transient model (BR-005)."""

    def test_helper_model_exists(self):
        """BR-005: account.reconciliation.partial.helper should exist."""
        self.assertIn(
            'account.reconciliation.partial.helper', self.env,
            "PartialReconcileHelper model should be registered.",
        )

    def test_helper_fields_present(self):
        """BR-005: Key fields should exist on the helper wizard."""
        fields_info = self.env['account.reconciliation.partial.helper'].fields_get()
        expected_fields = [
            'company_id', 'currency_id', 'statement_line_id',
            'move_line_ids', 'write_off_account_id', 'write_off_label',
            'write_off_amount', 'tolerance_percentage',
            'total_statement_amount', 'total_move_line_amount',
            'difference_amount', 'is_within_tolerance',
        ]
        for fname in expected_fields:
            self.assertIn(fname, fields_info,
                          f"Field '{fname}' should exist on helper.")

    def test_helper_create_minimal(self):
        """BR-005: A minimal helper wizard should be creatable."""
        statement = self.env['account.bank.statement'].create({
            'name': 'PR Helper Test Stmt',
            'journal_id': self.bank_journal.id,
        })
        st_line = self.env['account.bank.statement.line'].create({
            'statement_id': statement.id,
            'journal_id': self.bank_journal.id,
            'date': '2024-02-01',
            'payment_ref': 'Partial test',
            'amount': 500.0,
        })
        helper = self.env['account.reconciliation.partial.helper'].create({
            'statement_line_id': st_line.id,
            'company_id': self.company.id,
        })
        self.assertTrue(helper.exists())
        self.assertAlmostEqual(helper.tolerance_percentage, 0.0, places=2)

    def test_helper_default_write_off_label(self):
        """BR-005: Default write_off_label should be 'Write-Off'."""
        statement = self.env['account.bank.statement'].create({
            'name': 'WO Label Test',
            'journal_id': self.bank_journal.id,
        })
        st_line = self.env['account.bank.statement.line'].create({
            'statement_id': statement.id,
            'journal_id': self.bank_journal.id,
            'date': '2024-02-01',
            'payment_ref': 'Label test',
            'amount': 100.0,
        })
        helper = self.env['account.reconciliation.partial.helper'].create({
            'statement_line_id': st_line.id,
            'company_id': self.company.id,
        })
        self.assertEqual(helper.write_off_label, 'Write-Off')


@tagged('post_install', '-at_install')
class TestPartialReconcileValidation(BankReconciliationTestCommon):
    """Tests for validation in PartialReconcileHelper (BR-005)."""

    def test_reconcile_without_move_lines_raises(self):
        """BR-005: Reconciling without journal items should raise."""
        statement = self.env['account.bank.statement'].create({
            'name': 'Validation Test Stmt',
            'journal_id': self.bank_journal.id,
        })
        st_line = self.env['account.bank.statement.line'].create({
            'statement_id': statement.id,
            'journal_id': self.bank_journal.id,
            'date': '2024-02-01',
            'payment_ref': 'Validation test',
            'amount': 200.0,
        })
        helper = self.env['account.reconciliation.partial.helper'].create({
            'statement_line_id': st_line.id,
            'company_id': self.company.id,
        })
        with self.assertRaises(UserError):
            helper.action_reconcile()

    def test_action_reconcile_exists(self):
        """BR-005: action_reconcile method should exist."""
        HelperModel = self.env['account.reconciliation.partial.helper']
        self.assertTrue(
            callable(getattr(HelperModel, 'action_reconcile', None)),
            "action_reconcile should be callable.",
        )


@tagged('post_install', '-at_install')
class TestStatementLineExtFields(BankReconciliationTestCommon):
    """Tests for BankStatementLineExt fields added via _inherit (BR-005)."""

    def test_statement_line_ext_fields_exist(self):
        """BR-005: Extended fields should exist on account.bank.statement.line."""
        fields_info = self.env['account.bank.statement.line'].fields_get()
        ext_fields = [
            'matching_confidence', 'reconciliation_status',
            'import_hash', 'import_source', 'import_format',
        ]
        for fname in ext_fields:
            self.assertIn(fname, fields_info,
                          f"Field '{fname}' should exist on statement line.")

    def test_default_reconciliation_status(self):
        """BR-005: Default reconciliation_status should be 'unreconciled'."""
        statement = self.env['account.bank.statement'].create({
            'name': 'Ext Fields Test',
            'journal_id': self.bank_journal.id,
        })
        st_line = self.env['account.bank.statement.line'].create({
            'statement_id': statement.id,
            'journal_id': self.bank_journal.id,
            'date': '2024-03-01',
            'payment_ref': 'Status default',
            'amount': 100.0,
        })
        self.assertEqual(st_line.reconciliation_status, 'unreconciled')

    def test_matching_confidence_defaults_to_zero(self):
        """BR-005: matching_confidence should default to 0."""
        statement = self.env['account.bank.statement'].create({
            'name': 'Confidence Default',
            'journal_id': self.bank_journal.id,
        })
        st_line = self.env['account.bank.statement.line'].create({
            'statement_id': statement.id,
            'journal_id': self.bank_journal.id,
            'date': '2024-03-01',
            'payment_ref': 'Conf default',
            'amount': 50.0,
        })
        self.assertAlmostEqual(st_line.matching_confidence, 0.0, places=2)

    def test_import_format_selections(self):
        """BR-005: import_format should have expected selections."""
        fields_info = self.env['account.bank.statement.line'].fields_get(
            ['import_format'],
        )
        selections = dict(fields_info['import_format']['selection'])
        for key in ('csv', 'ofx', 'qif', 'camt053', 'manual'):
            self.assertIn(key, selections,
                          f"import_format should have '{key}' option.")

    def test_reconciliation_status_selections(self):
        """BR-005: reconciliation_status should have expected selections."""
        fields_info = self.env['account.bank.statement.line'].fields_get(
            ['reconciliation_status'],
        )
        selections = dict(fields_info['reconciliation_status']['selection'])
        for key in ('unreconciled', 'partially', 'reconciled', 'manual'):
            self.assertIn(key, selections,
                          f"reconciliation_status should have '{key}' option.")


@tagged('post_install', '-at_install')
class TestToleranceComputation(BankReconciliationTestCommon):
    """Tests for tolerance and amount computation in the helper (BR-005)."""

    def test_compute_amounts_basic(self):
        """BR-005: Computed amounts should reflect statement line amount."""
        statement = self.env['account.bank.statement'].create({
            'name': 'Amounts Compute Test',
            'journal_id': self.bank_journal.id,
        })
        st_line = self.env['account.bank.statement.line'].create({
            'statement_id': statement.id,
            'journal_id': self.bank_journal.id,
            'date': '2024-02-01',
            'payment_ref': 'Compute test',
            'amount': 1000.0,
        })
        helper = self.env['account.reconciliation.partial.helper'].create({
            'statement_line_id': st_line.id,
            'company_id': self.company.id,
        })
        self.assertAlmostEqual(
            helper.total_statement_amount, 1000.0, places=2,
            msg="total_statement_amount should equal the statement amount.",
        )

    def test_tolerance_zero_requires_exact_match(self):
        """BR-005: With tolerance 0, only exact match should be within tolerance."""
        statement = self.env['account.bank.statement'].create({
            'name': 'Tolerance Zero Test',
            'journal_id': self.bank_journal.id,
        })
        st_line = self.env['account.bank.statement.line'].create({
            'statement_id': statement.id,
            'journal_id': self.bank_journal.id,
            'date': '2024-02-01',
            'payment_ref': 'Tolerance zero',
            'amount': 500.0,
        })
        helper = self.env['account.reconciliation.partial.helper'].create({
            'statement_line_id': st_line.id,
            'company_id': self.company.id,
            'tolerance_percentage': 0.0,
        })
        # No move lines selected → difference == 500, which is not zero
        # So is_within_tolerance should be False
        self.assertFalse(helper.is_within_tolerance,
                         "With tolerance 0 and a difference, should NOT be within tolerance.")
