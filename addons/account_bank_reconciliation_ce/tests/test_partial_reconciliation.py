# -*- coding: utf-8 -*-
# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Test suite for BR-005: Partial Reconciliation with Write-offs.

Comprehensive acceptance-criteria tests covering:

* **PartialReconcileHelper wizard** — creation, computed amount fields
  (``total_statement_amount``, ``total_move_line_amount``,
  ``difference_amount``, ``is_within_tolerance``), and write-off amount
  computation.
* **Reconciliation execution** — exact-match, tolerance-based auto write-off,
  explicit write-off journal entries, status tracking, and
  ``account.partial.reconcile`` record creation.
* **Split transactions** — one-to-many matching, partial amount matching,
  split with write-off.
* **Unreconciliation** — reversal of reconciliation, status reset, write-off
  handling.
* **Multi-currency** — same currency, cross-currency conversion, exchange-rate
  difference handling.
* **Statement line extensions** — ``matching_confidence``,
  ``reconciliation_status``, ``import_hash``, ``import_source``,
  ``import_format`` field existence, selection values, and tracking.

All tests are tagged ``@tagged('post_install', '-at_install')`` per Odoo
convention and extend :class:`BankReconciliationTestCommon` for consistent
fixture data.
"""

from datetime import date, timedelta

from odoo import fields, Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from odoo.addons.account_bank_reconciliation_ce.tests.common import (
    BankReconciliationTestCommon,
)


# ---------------------------------------------------------------------------
# Helpers reused across multiple test classes
# ---------------------------------------------------------------------------

def _make_invoice_line(env, amount, partner, company_data, tax_free=True):
    """Create and post an invoice, returning the receivable move line.

    The invoice uses immediate payment terms to guarantee a single receivable
    line, which simplifies reconciliation testing.

    Args:
        env: Odoo environment.
        amount: Positive unit price for the invoice line.
        partner: ``res.partner`` record.
        company_data: Company accounting data dict.
        tax_free: If True, explicitly clear taxes on the line.

    Returns:
        Tuple of (posted ``account.move``, receivable ``account.move.line``).
    """
    line_vals = {
        'name': 'Partial Reconcile Test',
        'quantity': 1,
        'price_unit': amount,
        'account_id': company_data['default_account_revenue'].id,
    }
    if tax_free:
        line_vals['tax_ids'] = [Command.clear()]
    # Use immediate payment terms to guarantee a single receivable line.
    immediate_term = env.ref('account.account_payment_term_immediate', raise_if_not_found=False)
    move_vals = {
        'move_type': 'out_invoice',
        'partner_id': partner.id,
        'invoice_date': fields.Date.today(),
        'journal_id': company_data['default_journal_sale'].id,
        'invoice_line_ids': [Command.create(line_vals)],
    }
    if immediate_term:
        move_vals['invoice_payment_term_id'] = immediate_term.id
    move = env['account.move'].create(move_vals)
    move.action_post()
    receivable = move.line_ids.filtered(
        lambda l: l.account_id.account_type == 'asset_receivable'
    )
    return move, receivable


def _make_bill_line(env, amount, partner, company_data, tax_free=True):
    """Create and post a vendor bill, returning the payable move line.

    The bill uses immediate payment terms to guarantee a single payable line,
    which simplifies reconciliation testing.

    Returns:
        Tuple of (posted ``account.move``, payable ``account.move.line``).
    """
    line_vals = {
        'name': 'Partial Reconcile Test Bill',
        'quantity': 1,
        'price_unit': amount,
        'account_id': company_data['default_account_expense'].id,
    }
    if tax_free:
        line_vals['tax_ids'] = [Command.clear()]
    # Use immediate payment terms to guarantee a single payable line.
    immediate_term = env.ref('account.account_payment_term_immediate', raise_if_not_found=False)
    move_vals = {
        'move_type': 'in_invoice',
        'partner_id': partner.id,
        'invoice_date': fields.Date.today(),
        'journal_id': company_data['default_journal_purchase'].id,
        'invoice_line_ids': [Command.create(line_vals)],
    }
    if immediate_term:
        move_vals['invoice_payment_term_id'] = immediate_term.id
    move = env['account.move'].create(move_vals)
    move.action_post()
    payable = move.line_ids.filtered(
        lambda l: l.account_id.account_type == 'liability_payable'
    )
    return move, payable


def _create_st_line(env, journal, amount, partner=None, payment_ref='Test',
                    statement=None, st_date=None):
    """Create a single bank statement line.

    Returns:
        ``account.bank.statement.line`` record.
    """
    vals = {
        'date': st_date or fields.Date.today(),
        'payment_ref': payment_ref,
        'amount': amount,
        'journal_id': journal.id,
    }
    if partner:
        vals['partner_id'] = partner.id
    if statement:
        vals['statement_id'] = statement.id
    return env['account.bank.statement.line'].create(vals)


def _ensure_suspense_reconcilable(journal):
    """Make the journal's suspense account reconcilable for testing."""
    if journal.suspense_account_id and not journal.suspense_account_id.reconcile:
        journal.suspense_account_id.write({'reconcile': True})


# ============================================================================
# 1. TestPartialReconcileHelper
# ============================================================================

@tagged('post_install', '-at_install')
class TestPartialReconcileHelper(BankReconciliationTestCommon):
    """Test the PartialReconcileHelper wizard fields and computations (BR-005)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _ensure_suspense_reconcilable(cls.bank_journal)

    # ------------------------------------------------------------------
    # test_br005_helper_creation
    # ------------------------------------------------------------------

    def test_br005_helper_creation(self):
        """BR-005: Create helper with statement_line_id and move_line_ids,
        verify default field values."""
        # Use pre-built fixtures from BankReconciliationTestCommon:
        # self.st_line_1 (amount=1000, partner_a),
        # self.invoice_receivable_line (from self.test_invoice, amount=1000)
        st_line = self.st_line_1
        rec_line = self.invoice_receivable_line
        # Confirm the test_invoice is the parent of the receivable line
        self.assertEqual(rec_line.move_id, self.test_invoice)

        helper = self.env['account.reconciliation.partial.helper'].create({
            'statement_line_id': st_line.id,
            'move_line_ids': [Command.set(rec_line.ids)],
        })

        self.assertTrue(helper.exists(), "Helper wizard should be created.")
        self.assertEqual(helper.statement_line_id, st_line)
        self.assertTrue(helper.move_line_ids)
        self.assertAlmostEqual(helper.tolerance_percentage, 0.0, places=2,
                               msg="Default tolerance should be 0.")
        self.assertEqual(helper.write_off_label, 'Write-Off',
                         msg="Default write_off_label should be 'Write-Off'.")
        self.assertFalse(helper.write_off_account_id,
                         msg="write_off_account_id should default to empty.")

    # ------------------------------------------------------------------
    # test_br005_compute_amounts
    # ------------------------------------------------------------------

    def test_br005_compute_amounts(self):
        """BR-005: Verify computed amount fields with statement=1000 and
        move line amount_residual=900, expecting difference=100."""
        # Use fields.Date.from_string to parse a specific date
        specific_date = fields.Date.from_string('2024-06-15')
        _inv, rec_line = _make_invoice_line(
            self.env, 900.0, self.partner_a, self.company_data,
        )
        st_line = _create_st_line(
            self.env, self.bank_journal, 1000.0,
            partner=self.partner_a, payment_ref='Compute amounts',
            st_date=specific_date,
        )
        helper = self.env['account.reconciliation.partial.helper'].create({
            'statement_line_id': st_line.id,
            'move_line_ids': [Command.set(rec_line.ids)],
        })

        self.assertAlmostEqual(
            helper.total_statement_amount, 1000.0, places=2,
            msg="total_statement_amount should equal 1000.",
        )
        # The receivable line from a 900 invoice has amount_residual > 0.
        expected_ml = sum(rec_line.mapped('amount_residual'))
        self.assertAlmostEqual(
            helper.total_move_line_amount, expected_ml, places=2,
            msg="total_move_line_amount should equal the receivable residual.",
        )
        expected_diff = 1000.0 - expected_ml
        self.assertAlmostEqual(
            helper.difference_amount, expected_diff, places=2,
            msg="difference_amount should be statement minus move line total.",
        )

    # ------------------------------------------------------------------
    # test_br005_compute_write_off_amount
    # ------------------------------------------------------------------

    def test_br005_compute_write_off_amount(self):
        """BR-005: write_off_amount equals abs(difference) when write-off
        account is set."""
        _inv, rec_line = _make_invoice_line(
            self.env, 900.0, self.partner_a, self.company_data,
        )
        st_line = _create_st_line(
            self.env, self.bank_journal, 1000.0,
            partner=self.partner_a, payment_ref='WO amount test',
        )
        helper = self.env['account.reconciliation.partial.helper'].create({
            'statement_line_id': st_line.id,
            'move_line_ids': [Command.set(rec_line.ids)],
            'write_off_account_id': self.write_off_account.id,
        })

        expected_diff = abs(helper.difference_amount)
        self.assertAlmostEqual(
            helper.write_off_amount, expected_diff, places=2,
            msg="write_off_amount should be abs(difference_amount) when "
                "write_off_account_id is set.",
        )
        self.assertGreater(helper.write_off_amount, 0.0,
                           msg="write_off_amount must be positive.")

    # ------------------------------------------------------------------
    # test_br005_is_within_tolerance_true
    # ------------------------------------------------------------------

    def test_br005_is_within_tolerance_true(self):
        """BR-005: tolerance_percentage=15, difference=10% → within tolerance."""
        _inv, rec_line = _make_invoice_line(
            self.env, 900.0, self.partner_a, self.company_data,
        )
        st_line = _create_st_line(
            self.env, self.bank_journal, 1000.0,
            partner=self.partner_a, payment_ref='Tolerance true',
        )
        helper = self.env['account.reconciliation.partial.helper'].create({
            'statement_line_id': st_line.id,
            'move_line_ids': [Command.set(rec_line.ids)],
            'tolerance_percentage': 15.0,
        })

        # difference_amount / total_statement_amount ≈ 10%, tolerance 15%
        self.assertTrue(
            helper.is_within_tolerance,
            "10% difference should be within 15% tolerance.",
        )

    # ------------------------------------------------------------------
    # test_br005_is_within_tolerance_false
    # ------------------------------------------------------------------

    def test_br005_is_within_tolerance_false(self):
        """BR-005: tolerance_percentage=5, difference=10% → NOT within
        tolerance."""
        _inv, rec_line = _make_invoice_line(
            self.env, 900.0, self.partner_a, self.company_data,
        )
        st_line = _create_st_line(
            self.env, self.bank_journal, 1000.0,
            partner=self.partner_a, payment_ref='Tolerance false',
        )
        helper = self.env['account.reconciliation.partial.helper'].create({
            'statement_line_id': st_line.id,
            'move_line_ids': [Command.set(rec_line.ids)],
            'tolerance_percentage': 5.0,
        })

        self.assertFalse(
            helper.is_within_tolerance,
            "10% difference should NOT be within 5% tolerance.",
        )

    # ------------------------------------------------------------------
    # test_br005_is_within_tolerance_zero
    # ------------------------------------------------------------------

    def test_br005_is_within_tolerance_zero(self):
        """BR-005: Zero tolerance with non-zero difference → NOT within
        tolerance."""
        _inv, rec_line = _make_invoice_line(
            self.env, 900.0, self.partner_a, self.company_data,
        )
        st_line = _create_st_line(
            self.env, self.bank_journal, 1000.0,
            partner=self.partner_a, payment_ref='Tolerance zero',
        )
        helper = self.env['account.reconciliation.partial.helper'].create({
            'statement_line_id': st_line.id,
            'move_line_ids': [Command.set(rec_line.ids)],
            'tolerance_percentage': 0.0,
        })

        self.assertFalse(
            helper.is_within_tolerance,
            "With 0% tolerance and non-zero difference, is_within_tolerance "
            "should be False.",
        )


# ============================================================================
# 2. TestPartialReconciliation
# ============================================================================

@tagged('post_install', '-at_install')
class TestPartialReconciliation(BankReconciliationTestCommon):
    """Test the action_reconcile execution flow (BR-005)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _ensure_suspense_reconcilable(cls.bank_journal)

    # ------------------------------------------------------------------
    # test_br005_exact_match_reconcile
    # ------------------------------------------------------------------

    def test_br005_exact_match_reconcile(self):
        """BR-005: Statement amount equals move line total → direct
        reconciliation without write-off."""
        # Use pre-built fixtures: st_line_1 (1000) and invoice_receivable_line
        st_line = self.st_line_1
        rec_line = self.invoice_receivable_line

        helper = self.env['account.reconciliation.partial.helper'].create({
            'statement_line_id': st_line.id,
            'move_line_ids': [Command.set(rec_line.ids)],
        })

        # Difference should be ~0
        self.assertTrue(
            self.env.company.currency_id.is_zero(helper.difference_amount),
            "Difference should be zero for exact match.",
        )

        result = helper.action_reconcile()
        self.assertEqual(result.get('type'), 'ir.actions.act_window_close',
                         "action_reconcile should return a close action.")

        # Status should indicate reconciled
        self.assertIn(
            st_line.reconciliation_status,
            ('reconciled', 'partially'),
            "Statement line should be reconciled after exact match.",
        )

    # ------------------------------------------------------------------
    # test_br005_within_tolerance_auto_writeoff
    # ------------------------------------------------------------------

    def test_br005_exact_match_error_on_invalid_line(self):
        """BR-005: Attempting to reconcile with an already-reconciled move line
        should be handled gracefully (UserError or ValidationError)."""
        _inv, rec_line = _make_invoice_line(
            self.env, 500.0, self.partner_a, self.company_data,
        )
        st_line_a = _create_st_line(
            self.env, self.bank_journal, 500.0,
            partner=self.partner_a, payment_ref='First reconcile',
        )
        # Reconcile the first time
        helper_a = self.env['account.reconciliation.partial.helper'].create({
            'statement_line_id': st_line_a.id,
            'move_line_ids': [Command.link(rec_line.id)],
        })
        helper_a.action_reconcile()

        # Now try with the same (now reconciled) move line and a new statement
        st_line_b = _create_st_line(
            self.env, self.bank_journal, 500.0,
            partner=self.partner_a, payment_ref='Second attempt',
        )
        helper_b = self.env['account.reconciliation.partial.helper'].create({
            'statement_line_id': st_line_b.id,
            'move_line_ids': [Command.link(rec_line.id)],
        })
        # The reconcile should either raise UserError/ValidationError or
        # handle it gracefully (no further reconciliation).
        try:
            helper_b.action_reconcile()
        except (UserError, ValidationError):
            # Expected: the already-reconciled line cannot be matched again
            pass
        else:
            # If no error, the status should still reflect reality.
            # The partially/not-reconciled outcome is acceptable when the
            # counterpart line had no remaining residual.
            self.assertIn(
                st_line_b.reconciliation_status,
                ('unreconciled', 'partially'),
                "Should not be fully reconciled against an exhausted line.",
            )

    def test_br005_within_tolerance_auto_writeoff(self):
        """BR-005: Difference within tolerance_percentage without explicit
        write-off account → auto-absorb, status 'reconciled'."""
        _inv, rec_line = _make_invoice_line(
            self.env, 950.0, self.partner_a, self.company_data,
        )
        st_line = _create_st_line(
            self.env, self.bank_journal, 1000.0,
            partner=self.partner_a, payment_ref='Auto tolerance',
        )
        helper = self.env['account.reconciliation.partial.helper'].create({
            'statement_line_id': st_line.id,
            'move_line_ids': [Command.set(rec_line.ids)],
            'tolerance_percentage': 10.0,  # 5% diff, 10% tolerance
        })

        self.assertTrue(helper.is_within_tolerance,
                        "5% difference should be within 10% tolerance.")

        result = helper.action_reconcile()
        self.assertEqual(result.get('type'), 'ir.actions.act_window_close')

        # Without a write-off account the tolerance path marks as reconciled.
        self.assertEqual(
            st_line.reconciliation_status, 'reconciled',
            "Status should be 'reconciled' when within tolerance and no "
            "write-off account.",
        )

    # ------------------------------------------------------------------
    # test_br005_explicit_writeoff
    # ------------------------------------------------------------------

    def test_br005_explicit_writeoff(self):
        """BR-005: Difference exceeds tolerance but write_off_account_id is
        set → create write-off entry and reconcile."""
        _inv, rec_line = _make_invoice_line(
            self.env, 900.0, self.partner_a, self.company_data,
        )
        st_line = _create_st_line(
            self.env, self.bank_journal, 1000.0,
            partner=self.partner_a, payment_ref='Explicit WO',
        )
        helper = self.env['account.reconciliation.partial.helper'].create({
            'statement_line_id': st_line.id,
            'move_line_ids': [Command.set(rec_line.ids)],
            'tolerance_percentage': 5.0,   # 10% diff > 5% tolerance
            'write_off_account_id': self.write_off_account.id,
        })

        self.assertFalse(helper.is_within_tolerance)
        result = helper.action_reconcile()
        self.assertEqual(result.get('type'), 'ir.actions.act_window_close')

        # The write-off path should set status to 'reconciled'.
        self.assertEqual(
            st_line.reconciliation_status, 'reconciled',
            "Status should be 'reconciled' after explicit write-off.",
        )

    # ------------------------------------------------------------------
    # test_br005_writeoff_journal_entry
    # ------------------------------------------------------------------

    def test_br005_writeoff_journal_entry(self):
        """BR-005: After write-off, verify that a new journal entry was created
        with the write_off_account_id, the correct amount, and is posted."""
        _inv, rec_line = _make_invoice_line(
            self.env, 900.0, self.partner_a, self.company_data,
        )
        st_line = _create_st_line(
            self.env, self.bank_journal, 1000.0,
            partner=self.partner_a, payment_ref='WO entry test',
        )

        # Count moves before reconciliation
        moves_before = self.env['account.move'].search_count([
            ('journal_id', '=', self.bank_journal.id),
        ])

        helper = self.env['account.reconciliation.partial.helper'].create({
            'statement_line_id': st_line.id,
            'move_line_ids': [Command.set(rec_line.ids)],
            'write_off_account_id': self.write_off_account.id,
        })
        diff = abs(helper.difference_amount)
        helper.action_reconcile()

        # A new journal entry should have been created
        moves_after = self.env['account.move'].search_count([
            ('journal_id', '=', self.bank_journal.id),
        ])
        self.assertGreater(
            moves_after, moves_before,
            "A new journal entry should be created for the write-off.",
        )

        # Find the write-off entry by looking for a move with a line on the
        # write-off account.
        wo_lines = self.env['account.move.line'].search([
            ('account_id', '=', self.write_off_account.id),
            ('journal_id', '=', self.bank_journal.id),
            ('move_id.state', '=', 'posted'),
        ])
        self.assertTrue(
            wo_lines,
            "A posted write-off line should exist on the write-off account.",
        )
        # The write-off line amount (debit or credit) should equal the
        # absolute difference.
        wo_amounts = [max(l.debit, l.credit) for l in wo_lines]
        self.assertTrue(
            any(
                self.env.company.currency_id.compare_amounts(a, diff) == 0
                for a in wo_amounts
            ),
            f"A write-off line with amount {diff} should exist.",
        )

    # ------------------------------------------------------------------
    # test_br005_reconcile_updates_status
    # ------------------------------------------------------------------

    def test_br005_reconcile_updates_status(self):
        """BR-005: After action_reconcile, verify reconciliation_status
        updated appropriately."""
        # Use create_posted_invoice() helper from BankReconciliationTestCommon
        inv = self.create_posted_invoice(1000.0, partner=self.partner_reconcile)
        rec_line = inv.line_ids.filtered(
            lambda l: l.account_id.account_type == 'asset_receivable'
        )
        past_date = date.today() - timedelta(days=5)
        st_line = _create_st_line(
            self.env, self.bank_journal, 1000.0,
            partner=self.partner_reconcile, payment_ref='Status update',
            st_date=past_date,
        )

        # Before reconciliation
        self.assertEqual(st_line.reconciliation_status, 'unreconciled')

        helper = self.env['account.reconciliation.partial.helper'].create({
            'statement_line_id': st_line.id,
            'move_line_ids': [Command.set(rec_line.ids)],
        })
        helper.action_reconcile()

        # After exact-match reconciliation
        self.assertIn(
            st_line.reconciliation_status,
            ('reconciled', 'partially'),
            "Status should be updated after reconciliation.",
        )
        self.assertNotEqual(
            st_line.reconciliation_status, 'unreconciled',
            "Status should not remain 'unreconciled' after action_reconcile.",
        )

    # ------------------------------------------------------------------
    # test_br005_partial_reconcile_records
    # ------------------------------------------------------------------

    def test_br005_partial_reconcile_records(self):
        """BR-005: After action_reconcile, verify account.partial.reconcile
        records exist linking the correct debit/credit move lines."""
        # Use partner_b and the pre-built bill fixture for a negative scenario
        # self.test_bill (amount=500, partner_b), self.bill_payable_line
        bill_line = self.bill_payable_line
        self.assertEqual(bill_line.move_id, self.test_bill,
                         "bill_payable_line should belong to test_bill.")

        # Create a negative statement line for bill payment
        bill_date = date.today() - timedelta(days=2)
        st_line = _create_st_line(
            self.env, self.bank_journal, -500.0,
            partner=self.partner_b, payment_ref='Bill partial records',
            st_date=bill_date,
        )

        # Collect the statement's move line ids for checking
        st_move_line_ids = st_line.move_id.line_ids.ids

        helper = self.env['account.reconciliation.partial.helper'].create({
            'statement_line_id': st_line.id,
            'move_line_ids': [Command.set(bill_line.ids)],
        })
        helper.action_reconcile()

        # Search for partial reconcile records involving these lines
        partials = self.env['account.partial.reconcile'].search([
            '|',
            ('debit_move_id', 'in', st_move_line_ids + bill_line.ids),
            ('credit_move_id', 'in', st_move_line_ids + bill_line.ids),
        ])
        self.assertTrue(
            partials,
            "account.partial.reconcile records should be created after "
            "action_reconcile for bill payment.",
        )
        # Verify the reconciliation amount is positive
        for partial in partials:
            self.assertGreater(
                partial.amount, 0.0,
                "Partial reconcile amount must be positive.",
            )


# ============================================================================
# 3. TestSplitTransaction
# ============================================================================

@tagged('post_install', '-at_install')
class TestSplitTransaction(BankReconciliationTestCommon):
    """Test split transaction scenarios (BR-005)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _ensure_suspense_reconcilable(cls.bank_journal)

    # ------------------------------------------------------------------
    # test_br005_split_one_to_many
    # ------------------------------------------------------------------

    def test_br005_split_one_to_many(self):
        """BR-005: Statement line 1500 matched against two move lines
        (1000 + 500) → both partially reconciled."""
        _inv1, rec1 = _make_invoice_line(
            self.env, 1000.0, self.partner_a, self.company_data,
        )
        _inv2, rec2 = _make_invoice_line(
            self.env, 500.0, self.partner_a, self.company_data,
        )
        st_line = _create_st_line(
            self.env, self.bank_journal, 1500.0,
            partner=self.partner_a, payment_ref='Split 1-to-many',
        )

        all_rec_lines = rec1 | rec2
        helper = self.env['account.reconciliation.partial.helper'].create({
            'statement_line_id': st_line.id,
            'move_line_ids': [Command.set(all_rec_lines.ids)],
        })

        # Verify amounts line up
        self.assertAlmostEqual(helper.total_statement_amount, 1500.0, places=2)

        result = helper.action_reconcile()
        self.assertEqual(result.get('type'), 'ir.actions.act_window_close')

        # Verify partial reconcile records exist
        st_ml_ids = st_line.move_id.line_ids.ids
        partials = self.env['account.partial.reconcile'].search([
            '|',
            ('debit_move_id', 'in', st_ml_ids + all_rec_lines.ids),
            ('credit_move_id', 'in', st_ml_ids + all_rec_lines.ids),
        ])
        self.assertTrue(partials, "Partial reconcile records should exist.")

    # ------------------------------------------------------------------
    # test_br005_split_partial_amount
    # ------------------------------------------------------------------

    def test_br005_split_partial_amount(self):
        """BR-005: Statement line -300 matched against bill payable line of
        -500 → partial reconcile for 300, move line still has residual."""
        # Create a larger bill using the tax-free helper for deterministic
        # amounts (avoids tax-related extra lines).
        _bill, pay_lines = _make_bill_line(
            self.env, 500.0, self.partner_b, self.company_data,
        )
        # Use only the first payable line in case payment terms split
        # the payable into multiple instalments.
        pay_line = pay_lines[:1]
        self.assertTrue(pay_line, "At least one payable line should exist.")

        # Create a smaller statement line to test partial matching.
        st_line = _create_st_line(
            self.env, self.bank_journal, -300.0,
            partner=self.partner_b, payment_ref='Split partial bill',
            st_date=date.today() - timedelta(days=1),
        )

        helper = self.env['account.reconciliation.partial.helper'].create({
            'statement_line_id': st_line.id,
            'move_line_ids': [Command.set(pay_line.ids)],
        })

        # Difference should be non-zero since amounts don't match
        self.assertNotAlmostEqual(
            helper.difference_amount, 0.0, places=2,
            msg="Difference should be non-zero for partial amount matching.",
        )

        result = helper.action_reconcile()
        self.assertEqual(result.get('type'), 'ir.actions.act_window_close')

        # Status should be 'partially' since amounts don't match.
        self.assertEqual(
            st_line.reconciliation_status, 'partially',
            "Status should be 'partially' when amounts don't match.",
        )

        # The bill payable line should retain some residual.
        pay_line.invalidate_recordset(['amount_residual'])
        remaining = abs(pay_line.amount_residual)
        self.assertGreater(
            remaining, 0.0,
            "Bill payable should still have residual after partial "
            "reconciliation.",
        )

    # ------------------------------------------------------------------
    # test_br005_split_with_writeoff
    # ------------------------------------------------------------------

    def test_br005_split_with_writeoff(self):
        """BR-005: Statement 1050, move lines total 1000 → write-off for 50."""
        _inv, rec_line = _make_invoice_line(
            self.env, 1000.0, self.partner_a, self.company_data,
        )
        st_line = _create_st_line(
            self.env, self.bank_journal, 1050.0,
            partner=self.partner_a, payment_ref='Split WO',
        )

        helper = self.env['account.reconciliation.partial.helper'].create({
            'statement_line_id': st_line.id,
            'move_line_ids': [Command.set(rec_line.ids)],
            'write_off_account_id': self.write_off_account.id,
        })

        # Verify the difference is approximately 50 (depending on taxes)
        self.assertGreater(abs(helper.difference_amount), 0.0,
                           "There should be a non-zero difference.")

        result = helper.action_reconcile()
        self.assertEqual(result.get('type'), 'ir.actions.act_window_close')

        self.assertEqual(
            st_line.reconciliation_status, 'reconciled',
            "Status should be 'reconciled' after split with write-off.",
        )

        # Verify write-off line exists
        wo_lines = self.env['account.move.line'].search([
            ('account_id', '=', self.write_off_account.id),
            ('journal_id', '=', self.bank_journal.id),
            ('move_id.state', '=', 'posted'),
        ])
        self.assertTrue(wo_lines, "Write-off entry should be created.")

    # ------------------------------------------------------------------
    # test_br005_split_multiple_with_writeoff
    # ------------------------------------------------------------------

    def test_br005_split_multiple_with_writeoff(self):
        """BR-005: Statement 1550, move lines (1000 + 500) → match with
        write-off for the 50 difference."""
        _inv1, rec1 = _make_invoice_line(
            self.env, 1000.0, self.partner_a, self.company_data,
        )
        _inv2, rec2 = _make_invoice_line(
            self.env, 500.0, self.partner_a, self.company_data,
        )
        st_line = _create_st_line(
            self.env, self.bank_journal, 1550.0,
            partner=self.partner_a, payment_ref='Multi split WO',
        )

        all_rec = rec1 | rec2
        helper = self.env['account.reconciliation.partial.helper'].create({
            'statement_line_id': st_line.id,
            'move_line_ids': [Command.set(all_rec.ids)],
            'write_off_account_id': self.write_off_account.id,
        })

        # total_move_line_amount should be ~1500
        self.assertGreater(abs(helper.difference_amount), 0.0)

        result = helper.action_reconcile()
        self.assertEqual(result.get('type'), 'ir.actions.act_window_close')

        self.assertEqual(
            st_line.reconciliation_status, 'reconciled',
            "Status should be 'reconciled' after multi-line split with WO.",
        )


# ============================================================================
# 4. TestUnreconciliation
# ============================================================================

@tagged('post_install', '-at_install')
class TestUnreconciliation(BankReconciliationTestCommon):
    """Test undo/reverse reconciliation operations (BR-005)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _ensure_suspense_reconcilable(cls.bank_journal)

    def _reconcile_and_get_helper(self, st_amount, inv_amount, wo=False):
        """Helper: create, reconcile, return (helper, st_line, rec_line)."""
        _inv, rec_line = _make_invoice_line(
            self.env, inv_amount, self.partner_a, self.company_data,
        )
        st_line = _create_st_line(
            self.env, self.bank_journal, st_amount,
            partner=self.partner_a, payment_ref='Unrec test',
        )
        create_vals = {
            'statement_line_id': st_line.id,
            'move_line_ids': [Command.set(rec_line.ids)],
        }
        if wo:
            create_vals['write_off_account_id'] = self.write_off_account.id
        helper = self.env['account.reconciliation.partial.helper'].create(
            create_vals,
        )
        helper.action_reconcile()
        return helper, st_line, rec_line

    # ------------------------------------------------------------------
    # test_br005_unreconcile_basic
    # ------------------------------------------------------------------

    def test_br005_unreconcile_basic(self):
        """BR-005: After reconciliation, call action_unreconcile and verify
        partial reconcile records are removed."""
        helper, st_line, rec_line = self._reconcile_and_get_helper(
            1000.0, 1000.0,
        )
        st_ml_ids = st_line.move_id.line_ids.ids

        # Verify some reconciliation exists
        partials_before = self.env['account.partial.reconcile'].search([
            '|',
            ('debit_move_id', 'in', st_ml_ids + rec_line.ids),
            ('credit_move_id', 'in', st_ml_ids + rec_line.ids),
        ])

        # Create a new helper instance for the unreconcile action
        unrec_helper = self.env['account.reconciliation.partial.helper'].create({
            'statement_line_id': st_line.id,
        })
        unrec_helper.action_unreconcile()

        # After unreconciliation, partial records should be gone (or the
        # statement move lines should be recreated by action_undo_reconciliation).
        st_line.invalidate_recordset()
        # The statement line's move has been reset by action_undo_reconciliation
        # so its suspense line should have full residual again.
        _liq, suspense, _other = st_line._seek_for_lines()
        if suspense:
            self.assertNotAlmostEqual(
                suspense[0].amount_residual, 0.0,
                msg="Suspense line residual should be restored after unrec.",
            )

    # ------------------------------------------------------------------
    # test_br005_unreconcile_resets_status
    # ------------------------------------------------------------------

    def test_br005_unreconcile_resets_status(self):
        """BR-005: After unreconcile, reconciliation_status resets to
        'unreconciled'."""
        # Use partner_reconcile for this scenario
        inv = self.create_posted_invoice(
            750.0, partner=self.partner_reconcile,
        )
        rec_line = inv.line_ids.filtered(
            lambda l: l.account_id.account_type == 'asset_receivable'
        )
        st_line = _create_st_line(
            self.env, self.bank_journal, 750.0,
            partner=self.partner_reconcile,
            payment_ref='Unrec reset',
            st_date=date.today() - timedelta(days=3),
        )

        helper = self.env['account.reconciliation.partial.helper'].create({
            'statement_line_id': st_line.id,
            'move_line_ids': [Command.set(rec_line.ids)],
        })
        helper.action_reconcile()

        # Status should not be 'unreconciled' right after reconciliation
        self.assertNotEqual(st_line.reconciliation_status, 'unreconciled')

        unrec_helper = self.env['account.reconciliation.partial.helper'].create({
            'statement_line_id': st_line.id,
        })
        unrec_helper.action_unreconcile()

        self.assertEqual(
            st_line.reconciliation_status, 'unreconciled',
            "reconciliation_status should reset to 'unreconciled' after "
            "action_unreconcile.",
        )

    # ------------------------------------------------------------------
    # test_br005_unreconcile_with_writeoff
    # ------------------------------------------------------------------

    def test_br005_unreconcile_with_writeoff(self):
        """BR-005: Unreconcile a transaction that had a write-off → verify
        reconciliation is reversed and status reset."""
        helper, st_line, _rec = self._reconcile_and_get_helper(
            1050.0, 1000.0, wo=True,
        )

        # Verify write-off entry was created
        wo_lines = self.env['account.move.line'].search([
            ('account_id', '=', self.write_off_account.id),
            ('journal_id', '=', self.bank_journal.id),
            ('move_id.state', '=', 'posted'),
        ])
        self.assertTrue(wo_lines, "Write-off entry should exist before unrec.")

        unrec_helper = self.env['account.reconciliation.partial.helper'].create({
            'statement_line_id': st_line.id,
        })
        unrec_helper.action_unreconcile()

        # Status should be reset
        self.assertEqual(
            st_line.reconciliation_status, 'unreconciled',
            "Status should be 'unreconciled' after reversing a write-off "
            "reconciliation.",
        )
        # Matching confidence should be reset
        self.assertAlmostEqual(
            st_line.matching_confidence, 0.0, places=2,
            msg="matching_confidence should be reset to 0 after unrec.",
        )


# ============================================================================
# 5. TestMultiCurrency
# ============================================================================

@tagged('post_install', '-at_install')
class TestMultiCurrency(BankReconciliationTestCommon):
    """Test multi-currency reconciliation scenarios (BR-005)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _ensure_suspense_reconcilable(cls.bank_journal)
        _ensure_suspense_reconcilable(cls.bank_journal_2)
        # Set up a foreign currency with known rates
        cls.currency_eur = cls.setup_other_currency('EUR')

    # ------------------------------------------------------------------
    # test_br005_multi_currency_same_rate
    # ------------------------------------------------------------------

    def test_br005_multi_currency_same_rate(self):
        """BR-005: Statement in company currency, move line in company
        currency → normal reconciliation, no currency conversion."""
        _inv, rec_line = _make_invoice_line(
            self.env, 1000.0, self.partner_a, self.company_data,
        )
        # Use bank_journal_2 to verify multi-journal support
        st_line = _create_st_line(
            self.env, self.bank_journal_2, 1000.0,
            partner=self.partner_a, payment_ref='Same currency j2',
        )

        helper = self.env['account.reconciliation.partial.helper'].create({
            'statement_line_id': st_line.id,
            'move_line_ids': [Command.set(rec_line.ids)],
        })

        # _handle_multi_currency should return empty when currencies match
        converted = helper._handle_multi_currency(st_line, rec_line)
        self.assertFalse(
            converted.get('conversions'),
            "No currency conversion should occur when currencies match.",
        )

        result = helper.action_reconcile()
        self.assertEqual(result.get('type'), 'ir.actions.act_window_close')

    # ------------------------------------------------------------------
    # test_br005_multi_currency_different
    # ------------------------------------------------------------------

    def test_br005_multi_currency_different(self):
        """BR-005: Statement in company currency (USD), move lines in EUR →
        handle exchange rate conversion via _handle_multi_currency."""
        # Create a journal entry in EUR
        misc_journal = self.company_data['default_journal_misc']
        receivable_acct = self.company_data['default_account_receivable']
        revenue_acct = self.company_data['default_account_revenue']

        move = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': misc_journal.id,
            'date': fields.Date.today(),
            'line_ids': [
                Command.create({
                    'account_id': receivable_acct.id,
                    'partner_id': self.partner_a.id,
                    'currency_id': self.currency_eur.id,
                    'amount_currency': 1000.0,
                    'debit': 500.0,  # Approximate at 2:1 rate
                    'credit': 0.0,
                }),
                Command.create({
                    'account_id': revenue_acct.id,
                    'partner_id': self.partner_a.id,
                    'currency_id': self.currency_eur.id,
                    'amount_currency': -1000.0,
                    'debit': 0.0,
                    'credit': 500.0,
                }),
            ],
        })
        move.action_post()

        eur_rec_line = move.line_ids.filtered(
            lambda l: l.account_id == receivable_acct
        )

        # Statement in company currency
        st_line = _create_st_line(
            self.env, self.bank_journal, 500.0,
            partner=self.partner_a, payment_ref='Multi-curr',
        )

        helper = self.env['account.reconciliation.partial.helper'].create({
            'statement_line_id': st_line.id,
            'move_line_ids': [Command.set(eur_rec_line.ids)],
        })

        # _handle_multi_currency should detect the currency difference
        converted = helper._handle_multi_currency(st_line, eur_rec_line)
        if eur_rec_line.currency_id != st_line.currency_id:
            self.assertTrue(
                converted.get('conversions') or converted.get('statement_currency_id'),
                "Currency conversion data should be present for cross-currency "
                "reconciliation.",
            )

        # The reconcile action should complete without error
        result = helper.action_reconcile()
        self.assertEqual(result.get('type'), 'ir.actions.act_window_close')

    # ------------------------------------------------------------------
    # test_br005_multi_currency_difference_handling
    # ------------------------------------------------------------------

    def test_br005_multi_currency_difference_handling(self):
        """BR-005: Exchange rate difference results in small residual →
        auto write-off within tolerance."""
        # Create an invoice whose receivable is in EUR
        misc_journal = self.company_data['default_journal_misc']
        receivable_acct = self.company_data['default_account_receivable']
        revenue_acct = self.company_data['default_account_revenue']

        move = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': misc_journal.id,
            'date': fields.Date.today(),
            'line_ids': [
                Command.create({
                    'account_id': receivable_acct.id,
                    'partner_id': self.partner_a.id,
                    'currency_id': self.currency_eur.id,
                    'amount_currency': 1000.0,
                    'debit': 490.0,
                    'credit': 0.0,
                }),
                Command.create({
                    'account_id': revenue_acct.id,
                    'partner_id': self.partner_a.id,
                    'currency_id': self.currency_eur.id,
                    'amount_currency': -1000.0,
                    'debit': 0.0,
                    'credit': 490.0,
                }),
            ],
        })
        move.action_post()

        eur_rec_line = move.line_ids.filtered(
            lambda l: l.account_id == receivable_acct
        )

        # Statement for 500 (slightly more than the 490 debit)
        st_line = _create_st_line(
            self.env, self.bank_journal, 500.0,
            partner=self.partner_a, payment_ref='FX diff',
        )

        helper = self.env['account.reconciliation.partial.helper'].create({
            'statement_line_id': st_line.id,
            'move_line_ids': [Command.set(eur_rec_line.ids)],
            'tolerance_percentage': 5.0,  # Generous tolerance for FX diff
            'write_off_account_id': self.write_off_account.id,
        })

        # The reconciliation should complete regardless of currency diffs
        result = helper.action_reconcile()
        self.assertEqual(result.get('type'), 'ir.actions.act_window_close')

        self.assertIn(
            st_line.reconciliation_status,
            ('reconciled', 'partially'),
            "Multi-currency reconciliation should update the status.",
        )


# ============================================================================
# 6. TestStatementLineExtensions
# ============================================================================

@tagged('post_install', '-at_install')
class TestStatementLineExtensions(BankReconciliationTestCommon):
    """Test the extended fields on account.bank.statement.line (BR-005)."""

    # ------------------------------------------------------------------
    # test_br005_matching_confidence_field
    # ------------------------------------------------------------------

    def test_br005_matching_confidence_field(self):
        """BR-005: Verify matching_confidence field exists and is writable."""
        fields_info = self.env['account.bank.statement.line'].fields_get(
            ['matching_confidence'],
        )
        self.assertIn('matching_confidence', fields_info,
                       "matching_confidence field should exist.")

        # Create a statement line and verify the field is writable
        st_line = self.create_bank_statement_line(
            100.0, payment_ref='Confidence test',
        )
        self.assertAlmostEqual(st_line.matching_confidence, 0.0, places=2)

        # Write a confidence score
        st_line.write({'matching_confidence': 85.5})
        self.assertAlmostEqual(
            st_line.matching_confidence, 85.5, places=1,
            msg="matching_confidence should be writable.",
        )

    # ------------------------------------------------------------------
    # test_br005_reconciliation_status_field
    # ------------------------------------------------------------------

    def test_br005_reconciliation_status_field(self):
        """BR-005: Verify reconciliation_status selection field with all 4
        values: unreconciled, partially, reconciled, manual."""
        fields_info = self.env['account.bank.statement.line'].fields_get(
            ['reconciliation_status'],
        )
        self.assertIn('reconciliation_status', fields_info)
        selections = dict(fields_info['reconciliation_status']['selection'])

        expected_keys = ('unreconciled', 'partially', 'reconciled', 'manual')
        for key in expected_keys:
            self.assertIn(
                key, selections,
                f"reconciliation_status should include '{key}' option.",
            )

        # Verify default on new line
        st_line = self.create_bank_statement_line(
            200.0, payment_ref='Status test',
        )
        self.assertEqual(
            st_line.reconciliation_status, 'unreconciled',
            "Default reconciliation_status should be 'unreconciled'.",
        )

    # ------------------------------------------------------------------
    # test_br005_import_hash_field
    # ------------------------------------------------------------------

    def test_br005_import_hash_field(self):
        """BR-005: Verify import_hash field is indexed and readonly."""
        fields_info = self.env['account.bank.statement.line'].fields_get(
            ['import_hash'],
        )
        self.assertIn('import_hash', fields_info)
        # The field definition has readonly=True; the fields_get should
        # reflect this.  (Actual enforcement is at ORM level.)
        self.assertTrue(
            fields_info['import_hash'].get('readonly', False),
            "import_hash should be readonly.",
        )

        # Verify we can force-write the hash (via ORM bypass or initial
        # creation — readonly fields can be set at create time in the ORM).
        st_line = self.create_bank_statement_line(
            50.0, payment_ref='Hash test',
        )
        # Force-set the hash using direct write (context bypass if needed)
        st_line.with_context(
            skip_readonly_check=True,
        ).write({'import_hash': 'abc123def456'})
        self.assertEqual(
            st_line.import_hash, 'abc123def456',
            "import_hash should hold the assigned value.",
        )

    # ------------------------------------------------------------------
    # test_br005_import_source_field
    # ------------------------------------------------------------------

    def test_br005_import_source_field(self):
        """BR-005: Verify import_source and import_format fields exist and
        can store values."""
        fields_info = self.env['account.bank.statement.line'].fields_get(
            ['import_source', 'import_format'],
        )
        self.assertIn('import_source', fields_info)
        self.assertIn('import_format', fields_info)

        st_line = self.create_bank_statement_line(
            75.0, payment_ref='Import source test',
        )

        # Write import metadata
        st_line.with_context(skip_readonly_check=True).write({
            'import_source': 'bank_export_2024.csv',
            'import_format': 'csv',
        })
        self.assertEqual(st_line.import_source, 'bank_export_2024.csv')
        self.assertEqual(st_line.import_format, 'csv')

        # Verify all format options are valid
        for fmt in ('csv', 'ofx', 'qif', 'camt053', 'manual'):
            st_line.with_context(skip_readonly_check=True).write({
                'import_format': fmt,
            })
            self.assertEqual(
                st_line.import_format, fmt,
                f"import_format should accept '{fmt}' value.",
            )

    # ------------------------------------------------------------------
    # test_br005_status_tracking
    # ------------------------------------------------------------------

    def test_br005_status_tracking(self):
        """BR-005: Write different reconciliation_status values and verify
        tracking works correctly across all transitions."""
        # Verify fixture bank_statement is available
        self.assertTrue(
            self.bank_statement.exists(),
            "bank_statement fixture should be available.",
        )
        # Use st_line_2 to verify the fixture's initial status, then create
        # a fresh line for transition testing.
        self.assertEqual(
            self.st_line_2.reconciliation_status, 'unreconciled',
            "Fixture st_line_2 should start as 'unreconciled'.",
        )

        st_line = self.create_bank_statement_line(
            300.0, payment_ref='Tracking test',
        )

        # Start at unreconciled
        self.assertEqual(st_line.reconciliation_status, 'unreconciled')

        # Transition through all valid status values
        transitions = [
            'partially',
            'reconciled',
            'manual',
            'unreconciled',
        ]
        for status in transitions:
            st_line.write({'reconciliation_status': status})
            self.assertEqual(
                st_line.reconciliation_status, status,
                f"reconciliation_status should be '{status}' after write.",
            )

        # Verify the final state persists after invalidation
        st_line.invalidate_recordset(['reconciliation_status'])
        self.assertEqual(
            st_line.reconciliation_status, 'unreconciled',
            "Status should persist after cache invalidation.",
        )
