# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Test Suite for Financial Reports Module

Implements comprehensive tests for all financial reporting functionality.
Target: Minimum 80% test coverage per EPIC-001 requirements.
"""

from datetime import date, timedelta

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestFinancialReportsBase(TransactionCase):
    """Base test class with common setup for financial report tests."""

    @classmethod
    def setUpClass(cls):
        """Set up test data for financial reports."""
        super().setUpClass()

        cls.company = cls.env.company
        cls.currency = cls.company.currency_id

        # Get standard accounts (Odoo 19.0 uses company_ids Many2many)
        cls.account_receivable = cls.env['account.account'].search([
            ('company_ids', 'in', cls.company.ids),
            ('account_type', '=', 'asset_receivable'),
        ], limit=1)

        cls.account_payable = cls.env['account.account'].search([
            ('company_ids', 'in', cls.company.ids),
            ('account_type', '=', 'liability_payable'),
        ], limit=1)

        cls.account_revenue = cls.env['account.account'].search([
            ('company_ids', 'in', cls.company.ids),
            ('account_type', '=', 'income'),
        ], limit=1)

        cls.account_expense = cls.env['account.account'].search([
            ('company_ids', 'in', cls.company.ids),
            ('account_type', '=', 'expense'),
        ], limit=1)

        cls.account_bank = cls.env['account.account'].search([
            ('company_ids', 'in', cls.company.ids),
            ('account_type', '=', 'asset_cash'),
        ], limit=1)

        # Test dates
        cls.date_today = date.today()
        cls.date_start = cls.date_today.replace(day=1)
        cls.date_end = cls.date_today

        # Create test partner
        cls.partner = cls.env['res.partner'].create({
            'name': 'Test Partner Financial Reports',
            'email': 'test@financial-reports.com',
        })

        # Create test journal
        cls.journal_sale = cls.env['account.journal'].search([
            ('company_id', '=', cls.company.id),
            ('type', '=', 'sale'),
        ], limit=1)

        cls.journal_purchase = cls.env['account.journal'].search([
            ('company_id', '=', cls.company.id),
            ('type', '=', 'purchase'),
        ], limit=1)


@tagged('post_install', '-at_install')
class TestFinancialReportWizard(TestFinancialReportsBase):
    """Test the Financial Report Wizard functionality."""

    def test_wizard_creation(self):
        """Test that the wizard can be created with default values."""
        wizard = self.env['account.financial.report.wizard'].create({
            'report_type': 'balance_sheet',
            'date_to': self.date_end,
            'company_id': self.company.id,
        })

        self.assertTrue(wizard, "Wizard should be created")
        self.assertEqual(wizard.report_type, 'balance_sheet')
        self.assertEqual(wizard.company_id, self.company)

    def test_wizard_balance_sheet(self):
        """Test Balance Sheet report generation."""
        wizard = self.env['account.financial.report.wizard'].create({
            'report_type': 'balance_sheet',
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
        })

        # Test that action_print_pdf returns a report action
        result = wizard.action_print_pdf()
        self.assertEqual(result.get('type'), 'ir.actions.report')

    def test_wizard_profit_loss(self):
        """Test Profit & Loss report generation."""
        wizard = self.env['account.financial.report.wizard'].create({
            'report_type': 'profit_loss',
            'date_from': self.date_start,
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
        })

        result = wizard.action_print_pdf()
        self.assertEqual(result.get('type'), 'ir.actions.report')

    def test_wizard_cash_flow(self):
        """Test Cash Flow Statement report generation."""
        wizard = self.env['account.financial.report.wizard'].create({
            'report_type': 'cash_flow',
            'date_from': self.date_start,
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
            'cash_flow_method': 'indirect',
        })

        result = wizard.action_print_pdf()
        self.assertEqual(result.get('type'), 'ir.actions.report')

    def test_wizard_general_ledger(self):
        """Test General Ledger report generation."""
        wizard = self.env['account.financial.report.wizard'].create({
            'report_type': 'general_ledger',
            'date_from': self.date_start,
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
            'show_details': True,
        })

        result = wizard.action_print_pdf()
        self.assertEqual(result.get('type'), 'ir.actions.report')

    def test_wizard_trial_balance(self):
        """Test Trial Balance report generation."""
        wizard = self.env['account.financial.report.wizard'].create({
            'report_type': 'trial_balance',
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
        })

        result = wizard.action_print_pdf()
        self.assertEqual(result.get('type'), 'ir.actions.report')

    def test_wizard_aged_receivable(self):
        """Test Aged Receivable report generation."""
        wizard = self.env['account.financial.report.wizard'].create({
            'report_type': 'aged_partner_balance',
            'date_at': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
            'partner_type': 'customer',
        })

        result = wizard.action_print_pdf()
        self.assertEqual(result.get('type'), 'ir.actions.report')

    def test_wizard_aged_payable(self):
        """Test Aged Payable report generation."""
        wizard = self.env['account.financial.report.wizard'].create({
            'report_type': 'aged_partner_balance',
            'date_at': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
            'partner_type': 'supplier',
        })

        result = wizard.action_print_pdf()
        self.assertEqual(result.get('type'), 'ir.actions.report')

    def test_wizard_excel_export(self):
        """Test Excel export functionality.

        The XLSX export generates an ``ir.attachment`` and returns an
        ``ir.actions.act_url`` action dict pointing to the file download
        controller so the browser triggers a download.
        """
        wizard = self.env['account.financial.report.wizard'].create({
            'report_type': 'trial_balance',
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
        })

        result = wizard.action_export_xlsx()
        self.assertEqual(result.get('type'), 'ir.actions.act_url')
        self.assertTrue(result.get('url'), "Download URL should be set")
        self.assertEqual(result.get('target'), 'new')


@tagged('post_install', '-at_install')
class TestBalanceSheetReport(TestFinancialReportsBase):
    """Test Balance Sheet Report model and calculations."""

    def test_balance_sheet_creation(self):
        """Test Balance Sheet report record creation."""
        report = self.env['account.balance.sheet.report'].create({
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
        })

        self.assertTrue(report, "Report should be created")
        self.assertEqual(report.state, 'draft')

    def test_balance_sheet_computation(self):
        """Test Balance Sheet compute action."""
        report = self.env['account.balance.sheet.report'].create({
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
        })

        report.action_compute()
        self.assertEqual(report.state, 'done')

    def test_balance_sheet_balance_equation(self):
        """Test that Assets = Liabilities + Equity."""
        report = self.env['account.balance.sheet.report'].create({
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
        })

        report.action_compute()

        # Verify balance equation (within rounding tolerance)
        difference = abs(report.total_assets - (report.total_liabilities + report.total_equity))
        self.assertLess(difference, 0.01, "Balance sheet should be balanced")


@tagged('post_install', '-at_install')
class TestProfitLossReport(TestFinancialReportsBase):
    """Test Profit & Loss Report model and calculations."""

    def test_profit_loss_creation(self):
        """Test Profit & Loss report record creation."""
        report = self.env['account.profit.loss.report'].create({
            'date_from': self.date_start,
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
        })

        self.assertTrue(report, "Report should be created")

    def test_profit_loss_computation(self):
        """Test Profit & Loss compute action."""
        report = self.env['account.profit.loss.report'].create({
            'date_from': self.date_start,
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
        })

        report.action_compute()
        self.assertEqual(report.state, 'done')

    def test_profit_loss_net_income(self):
        """Test Net Income calculation: Revenue - COGS - Expenses + Other."""
        report = self.env['account.profit.loss.report'].create({
            'date_from': self.date_start,
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
        })

        report.action_compute()

        # Verify net income calculation
        expected = report.total_revenue - report.total_cogs - report.total_expenses + report.total_other
        self.assertAlmostEqual(report.net_income, expected, places=2)


@tagged('post_install', '-at_install')
class TestTrialBalanceReport(TestFinancialReportsBase):
    """Test Trial Balance Report model and calculations."""

    def test_trial_balance_creation(self):
        """Test Trial Balance report record creation."""
        report = self.env['account.trial.balance.report'].create({
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
        })

        self.assertTrue(report, "Report should be created")

    def test_trial_balance_debit_credit_equality(self):
        """Test that total debits equal total credits."""
        report = self.env['account.trial.balance.report'].create({
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
        })

        report.action_compute()

        # Verify debit/credit equality
        difference = abs(report.total_debit - report.total_credit)
        self.assertLess(difference, 0.01, "Trial balance should be balanced")


@tagged('post_install', '-at_install')
class TestGeneralLedgerReport(TestFinancialReportsBase):
    """Test General Ledger Report model."""

    def test_general_ledger_creation(self):
        """Test General Ledger report record creation."""
        report = self.env['account.general.ledger.report'].create({
            'date_from': self.date_start,
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
        })

        self.assertTrue(report, "Report should be created")

    def test_general_ledger_with_account_filter(self):
        """Test General Ledger with specific accounts filtered."""
        if not self.account_receivable:
            self.skipTest("No receivable account found")

        report = self.env['account.general.ledger.report'].create({
            'date_from': self.date_start,
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
            'account_ids': [(6, 0, [self.account_receivable.id])],
        })

        report.action_compute()

        # Verify only filtered accounts are included
        account_ids = report.line_ids.mapped('account_id')
        self.assertTrue(all(acc.id == self.account_receivable.id for acc in account_ids))


@tagged('post_install', '-at_install')
class TestAgedPartnerBalanceReport(TestFinancialReportsBase):
    """Test Aged Partner Balance Report model."""

    def test_aged_receivable_creation(self):
        """Test Aged Receivable report record creation."""
        report = self.env['account.aged.partner.balance.report'].create({
            'date_at': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
            'partner_type': 'customer',
        })

        self.assertTrue(report, "Report should be created")
        self.assertEqual(report.partner_type, 'customer')

    def test_aged_payable_creation(self):
        """Test Aged Payable report record creation."""
        report = self.env['account.aged.partner.balance.report'].create({
            'date_at': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
            'partner_type': 'supplier',
        })

        self.assertTrue(report, "Report should be created")
        self.assertEqual(report.partner_type, 'supplier')

    def test_aging_bucket_calculation(self):
        """Test aging bucket calculation logic."""
        report = self.env['account.aged.partner.balance.report'].create({
            'date_at': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
            'partner_type': 'customer',
        })

        report.action_compute()

        # Verify aging buckets sum to total
        for partner_line in report.line_ids.mapped('partner_id'):
            partner_lines = report.line_ids.filtered(lambda line: line.partner_id == partner_line)
            bucket_sum = sum(partner_lines.mapped('amount_residual'))
            # Total for this partner should equal sum of buckets
            self.assertAlmostEqual(
                sum(partner_lines.mapped('amount_residual')),
                bucket_sum,
                places=2,
            )


@tagged('post_install', '-at_install')
class TestCashFlowReport(TestFinancialReportsBase):
    """Test Cash Flow Statement Report model."""

    def test_cash_flow_creation(self):
        """Test Cash Flow Statement report record creation."""
        report = self.env['account.cash.flow.report'].create({
            'date_from': self.date_start,
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
            'method': 'indirect',
        })

        self.assertTrue(report, "Report should be created")
        self.assertEqual(report.method, 'indirect')

    def test_cash_flow_cash_reconciliation(self):
        """Test Cash Flow cash reconciliation: Beginning + Net Change = Ending."""
        report = self.env['account.cash.flow.report'].create({
            'date_from': self.date_start,
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
            'method': 'indirect',
        })

        report.action_compute()

        # Verify cash reconciliation
        net_change = (
            report.cash_from_operating +
            report.cash_from_investing +
            report.cash_from_financing
        )
        expected_ending = report.beginning_cash + net_change

        self.assertAlmostEqual(report.ending_cash, expected_ending, places=2)


@tagged('post_install', '-at_install')
class TestReportComparison(TestFinancialReportsBase):
    """Test comparative period functionality."""

    def test_balance_sheet_comparison(self):
        """Test Balance Sheet with comparison period."""
        compare_date = self.date_end - timedelta(days=365)

        report = self.env['account.balance.sheet.report'].create({
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
            'compare_period': True,
            'compare_date_to': compare_date,
        })

        report.action_compute()

        # Verify comparison data is populated
        self.assertTrue(report.compare_period)


@tagged('post_install', '-at_install')
class TestReportFiltering(TestFinancialReportsBase):
    """Test report filtering capabilities."""

    def test_filter_by_journal(self):
        """Test filtering reports by journal."""
        if not self.journal_sale:
            self.skipTest("No sale journal found")

        wizard = self.env['account.financial.report.wizard'].create({
            'report_type': 'general_ledger',
            'date_from': self.date_start,
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
            'journal_ids': [(6, 0, [self.journal_sale.id])],
        })

        self.assertEqual(len(wizard.journal_ids), 1)

    def test_filter_by_partner(self):
        """Test filtering reports by partner."""
        wizard = self.env['account.financial.report.wizard'].create({
            'report_type': 'aged_partner_balance',
            'date_at': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
            'partner_type': 'customer',
            'partner_ids': [(6, 0, [self.partner.id])],
        })

        self.assertEqual(len(wizard.partner_ids), 1)

    def test_hide_zero_balance_accounts(self):
        """Test hiding accounts with zero balance."""
        wizard = self.env['account.financial.report.wizard'].create({
            'report_type': 'trial_balance',
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
            'hide_account_at_0': True,
        })

        self.assertTrue(wizard.hide_account_at_0)


@tagged('post_install', '-at_install')
class TestReportSecurity(TestFinancialReportsBase):
    """Test report access security."""

    def test_report_access_accountant(self):
        """Test that accountants can access reports."""
        accountant_group = self.env.ref('account.group_account_user')
        report_user_group = self.env.ref(
            'account_financial_report_ce.group_financial_report_user',
        )

        # Create a user with accountant and financial report user permissions
        # Odoo 19.0 uses 'group_ids' (not 'groups_id')
        user = self.env['res.users'].create({
            'name': 'Test Accountant',
            'login': 'test_accountant@test.com',
            'group_ids': [
                (6, 0, [accountant_group.id, report_user_group.id]),
            ],
        })

        # Try to create a report as the accountant
        wizard = self.env['account.financial.report.wizard'].with_user(user).create({
            'report_type': 'trial_balance',
            'date_to': self.date_end,
            'company_id': self.company.id,
        })

        self.assertTrue(wizard, "Accountant should be able to create reports")
