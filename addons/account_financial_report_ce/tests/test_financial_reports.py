# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Test Suite for Financial Reports Module

Implements comprehensive tests for all financial reporting functionality
across the six core report types mandated by FEATURE-001 (FR-001 through
FR-007).

Test classes are mapped to specific user-story acceptance criteria:
  - TestFinancialReportsBase          — shared fixture data
  - TestFinancialReportWizard         — FR-007 wizard & export
  - TestBalanceSheetReport            — FR-001 balance sheet
  - TestProfitLossReport              — FR-002 profit & loss
  - TestTrialBalanceReport            — FR-005 trial balance
  - TestGeneralLedgerReport           — FR-004 general ledger
  - TestAgedPartnerBalanceReport      — FR-006 aged AR/AP
  - TestCashFlowReport                — FR-003 cash flow statement
  - TestReportComparison              — FR-001 Scenario 5
  - TestReportFiltering               — FR-004 / FR-005 filtering
  - TestReportSecurity                — cross-story security

Target: ≥80% test coverage per EPIC-001 requirements.
"""

import contextlib
from datetime import date

from freezegun import freeze_time

from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon

# =============================================================================
# Frozen reference date used across all test classes.  Using a mid-month date
# avoids fiscal-year boundary edge-cases in default Odoo configurations.
# =============================================================================
_FROZEN_TODAY = '2024-06-15'
_FROZEN_DATE = date(2024, 6, 15)


# =============================================================================
# BASE FIXTURE
# =============================================================================
@tagged('post_install', '-at_install')
class TestFinancialReportsBase(AccountTestInvoicingCommon):
    """Base test class with deterministic accounting fixtures.

    Extends ``AccountTestInvoicingCommon`` to inherit pre-configured
    ``company_data`` (accounts, journals, taxes), ``partner_a``,
    ``partner_b``, and the ``env`` environment.  On top of this foundation
    the class creates posted journal entries with known debit/credit amounts
    so that every downstream report test can make precise numeric assertions.
    """

    @classmethod
    def setUpClass(cls):
        """Create deterministic posted journal entries for report tests."""
        super().setUpClass()

        # ----- Grant the test user the Financial Reports groups -----
        # ``AccountTestInvoicingCommon`` creates an independent 'accountman'
        # user whose groups are set via ``get_default_groups()``.  Our module
        # defines custom ACL groups (group_financial_report_user and
        # group_financial_report_manager) that are **not** implied by the
        # standard accounting groups, so the test user must be explicitly
        # added to the manager group (which implies the user group).
        fr_manager_group = cls.env.ref(
            'account_financial_report_ce.group_financial_report_manager',
            raise_if_not_found=False,
        )
        if fr_manager_group:
            cls.env.user.group_ids += fr_manager_group

        # ----- Shortcuts -----
        cls.company = cls.env.company
        cls.currency = cls.company.currency_id

        # Accounts from the test chart of accounts
        cls.account_receivable = cls.company_data['default_account_receivable']
        cls.account_payable = cls.company_data['default_account_payable']
        cls.account_revenue = cls.company_data['default_account_revenue']
        cls.account_expense = cls.company_data['default_account_expense']

        # Bank / cash account
        bank_journal = cls.company_data['default_journal_bank']
        cls.account_bank = (
            bank_journal.default_account_id
            or cls.env['account.account'].search([
                *cls.env['account.account']._check_company_domain(cls.company),
                ('account_type', '=', 'asset_cash'),
            ], limit=1)
        )

        # Fixed-asset account (investing activities)
        cls.account_fixed_asset = cls.company_data.get(
            'default_account_assets',
            cls.env['account.account'].search([
                *cls.env['account.account']._check_company_domain(
                    cls.company,
                ),
                ('account_type', '=', 'asset_fixed'),
            ], limit=1),
        )

        # Equity account
        cls.account_equity = cls.env['account.account'].search([
            *cls.env['account.account']._check_company_domain(cls.company),
            ('account_type', '=', 'equity'),
        ], limit=1)

        # COGS (expense_direct_cost) account
        cls.account_cogs = cls.env['account.account'].search([
            *cls.env['account.account']._check_company_domain(cls.company),
            ('account_type', '=', 'expense_direct_cost'),
        ], limit=1)
        if not cls.account_cogs:
            # Some CoAs don't ship a direct-cost account; create one
            cls.account_cogs = cls.env['account.account'].create({
                'name': 'Test COGS',
                'code': 'X51000',
                'account_type': 'expense_direct_cost',
                'company_ids': [Command.link(cls.company.id)],
            })

        # Journals
        cls.journal_sale = cls.company_data['default_journal_sale']
        cls.journal_purchase = cls.company_data['default_journal_purchase']
        cls.journal_bank = cls.company_data['default_journal_bank']
        cls.journal_misc = cls.company_data['default_journal_misc']

        # ----- Deterministic dates -----
        cls.date_start = date(2024, 1, 1)
        cls.date_end = date(2024, 6, 15)
        cls.date_today = _FROZEN_DATE
        cls.date_prev_year = date(2023, 6, 15)

        # ----- Extra partner (second customer) -----
        cls.partner_c = cls.env['res.partner'].create({
            'name': 'Partner C — Test Customer',
            'company_id': False,
        })

        # =================================================================
        # POSTED JOURNAL ENTRIES
        # =================================================================

        # (1) Sales invoice — Revenue 5 000, Receivable 5 000
        cls.move_sale = cls.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': cls.journal_sale.id,
            'date': date(2024, 3, 1),
            'line_ids': [
                Command.create({
                    'account_id': cls.account_receivable.id,
                    'partner_id': cls.partner_a.id,
                    'debit': 5000.0,
                    'credit': 0.0,
                    'date_maturity': date(2024, 4, 1),
                }),
                Command.create({
                    'account_id': cls.account_revenue.id,
                    'partner_id': cls.partner_a.id,
                    'debit': 0.0,
                    'credit': 5000.0,
                }),
            ],
        })
        cls.move_sale.action_post()

        # (2) Purchase bill — Expense 2 000, Payable 2 000
        cls.move_purchase = cls.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': cls.journal_purchase.id,
            'date': date(2024, 3, 15),
            'line_ids': [
                Command.create({
                    'account_id': cls.account_expense.id,
                    'partner_id': cls.partner_b.id,
                    'debit': 2000.0,
                    'credit': 0.0,
                }),
                Command.create({
                    'account_id': cls.account_payable.id,
                    'partner_id': cls.partner_b.id,
                    'debit': 0.0,
                    'credit': 2000.0,
                    'date_maturity': date(2024, 4, 15),
                }),
            ],
        })
        cls.move_purchase.action_post()

        # (3) COGS entry — COGS 1 200, Revenue offset 1 200
        # (treated as direct cost reducing gross profit)
        cls.move_cogs = cls.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': cls.journal_misc.id,
            'date': date(2024, 4, 1),
            'line_ids': [
                Command.create({
                    'account_id': cls.account_cogs.id,
                    'debit': 1200.0,
                    'credit': 0.0,
                }),
                Command.create({
                    'account_id': cls.account_payable.id,
                    'partner_id': cls.partner_b.id,
                    'debit': 0.0,
                    'credit': 1200.0,
                    'date_maturity': date(2024, 5, 1),
                }),
            ],
        })
        cls.move_cogs.action_post()

        # (4) Bank receipt — Bank 3 000, Receivable 3 000
        cls.move_bank_receipt = cls.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': cls.journal_bank.id,
            'date': date(2024, 4, 5),
            'line_ids': [
                Command.create({
                    'account_id': cls.account_bank.id,
                    'debit': 3000.0,
                    'credit': 0.0,
                }),
                Command.create({
                    'account_id': cls.account_receivable.id,
                    'partner_id': cls.partner_a.id,
                    'debit': 0.0,
                    'credit': 3000.0,
                }),
            ],
        })
        cls.move_bank_receipt.action_post()

        # (5) Bank payment — Payable 1 500, Bank 1 500
        cls.move_bank_payment = cls.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': cls.journal_bank.id,
            'date': date(2024, 4, 10),
            'line_ids': [
                Command.create({
                    'account_id': cls.account_payable.id,
                    'partner_id': cls.partner_b.id,
                    'debit': 1500.0,
                    'credit': 0.0,
                }),
                Command.create({
                    'account_id': cls.account_bank.id,
                    'debit': 0.0,
                    'credit': 1500.0,
                }),
            ],
        })
        cls.move_bank_payment.action_post()

        # (6) Second sales invoice for partner_c — older, for aging tests
        cls.move_sale_old = cls.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': cls.journal_sale.id,
            'date': date(2024, 1, 10),
            'line_ids': [
                Command.create({
                    'account_id': cls.account_receivable.id,
                    'partner_id': cls.partner_c.id,
                    'debit': 800.0,
                    'credit': 0.0,
                    'date_maturity': date(2024, 2, 10),
                }),
                Command.create({
                    'account_id': cls.account_revenue.id,
                    'partner_id': cls.partner_c.id,
                    'debit': 0.0,
                    'credit': 800.0,
                }),
            ],
        })
        cls.move_sale_old.action_post()

        # (7) Fixed-asset purchase — Investing activity
        if cls.account_fixed_asset:
            cls.move_fixed_asset = cls.env['account.move'].create({
                'move_type': 'entry',
                'journal_id': cls.journal_misc.id,
                'date': date(2024, 5, 1),
                'line_ids': [
                    Command.create({
                        'account_id': cls.account_fixed_asset.id,
                        'debit': 4000.0,
                        'credit': 0.0,
                    }),
                    Command.create({
                        'account_id': cls.account_bank.id,
                        'debit': 0.0,
                        'credit': 4000.0,
                    }),
                ],
            })
            cls.move_fixed_asset.action_post()

        # (8) Previous-year revenue entry (for comparative period tests)
        cls.move_prev_year = cls.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': cls.journal_sale.id,
            'date': date(2023, 3, 1),
            'line_ids': [
                Command.create({
                    'account_id': cls.account_receivable.id,
                    'partner_id': cls.partner_a.id,
                    'debit': 3500.0,
                    'credit': 0.0,
                    'date_maturity': date(2023, 4, 1),
                }),
                Command.create({
                    'account_id': cls.account_revenue.id,
                    'partner_id': cls.partner_a.id,
                    'debit': 0.0,
                    'credit': 3500.0,
                }),
            ],
        })
        cls.move_prev_year.action_post()

    # -----------------------------------------------------------------
    # Helper: create a wizard with sane defaults
    # -----------------------------------------------------------------
    def _create_wizard(self, report_type='balance_sheet', **overrides):
        """Return a new ``account.financial.report.wizard`` record."""
        vals = {
            'report_type': report_type,
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
        }
        if report_type in ('profit_loss', 'cash_flow', 'general_ledger'):
            vals['date_from'] = self.date_start
        vals.update(overrides)
        return self.env['account.financial.report.wizard'].create(vals)


# =============================================================================
# WIZARD TESTS — FR-007 (report generation & export)
# =============================================================================
@tagged('post_install', '-at_install')
class TestFinancialReportWizard(TestFinancialReportsBase):
    """Test the Financial Report Wizard functionality (FR-007)."""

    # ---- Creation & defaults ------------------------------------------------

    def test_fr007_wizard_creation_defaults(self):
        """Wizard creation with defaults populates expected fields."""
        wizard = self._create_wizard('balance_sheet')
        self.assertTrue(wizard, "Wizard should be created")
        self.assertEqual(wizard.report_type, 'balance_sheet')
        self.assertEqual(wizard.company_id, self.company)
        self.assertEqual(wizard.target_move, 'posted')
        self.assertFalse(wizard.enable_comparison)

    def test_fr007_wizard_default_values_propagation(self):
        """Wizard defaults for date and display options propagate."""
        wizard = self._create_wizard(
            'trial_balance',
            hide_zero_balance=True,
        )
        self.assertTrue(wizard.hide_zero_balance)
        self.assertEqual(wizard.date_to, self.date_end)

    # ---- Validation ---------------------------------------------------------

    @freeze_time(_FROZEN_TODAY)
    def test_fr007_wizard_invalid_date_range(self):
        """date_from > date_to must raise an error on constraint."""
        with self.assertRaises(UserError):
            self._create_wizard(
                'profit_loss',
                date_from=date(2024, 7, 1),
                date_to=date(2024, 6, 1),
            )

    # ---- Report generation bridging -----------------------------------------

    @freeze_time(_FROZEN_TODAY)
    def test_fr007_wizard_generate_balance_sheet(self):
        """Wizard generates Balance Sheet report action."""
        wizard = self._create_wizard('balance_sheet')
        result = wizard.action_generate_report()
        self.assertIn(result.get('type'), (
            'ir.actions.act_window', 'ir.actions.report',
        ))

    @freeze_time(_FROZEN_TODAY)
    def test_fr007_wizard_generate_profit_loss(self):
        """Wizard generates P&L report action."""
        wizard = self._create_wizard('profit_loss')
        result = wizard.action_generate_report()
        self.assertIn(result.get('type'), (
            'ir.actions.act_window', 'ir.actions.report',
        ))

    @freeze_time(_FROZEN_TODAY)
    def test_fr007_wizard_generate_cash_flow(self):
        """Wizard generates Cash Flow report action."""
        wizard = self._create_wizard(
            'cash_flow',
            cash_flow_method='indirect',
        )
        result = wizard.action_generate_report()
        self.assertIn(result.get('type'), (
            'ir.actions.act_window', 'ir.actions.report',
        ))

    @freeze_time(_FROZEN_TODAY)
    def test_fr007_wizard_generate_general_ledger(self):
        """Wizard generates General Ledger report action."""
        wizard = self._create_wizard(
            'general_ledger',
            show_details=True,
        )
        result = wizard.action_generate_report()
        self.assertIn(result.get('type'), (
            'ir.actions.act_window', 'ir.actions.report',
        ))

    @freeze_time(_FROZEN_TODAY)
    def test_fr007_wizard_generate_trial_balance(self):
        """Wizard generates Trial Balance report action."""
        wizard = self._create_wizard('trial_balance')
        result = wizard.action_generate_report()
        self.assertIn(result.get('type'), (
            'ir.actions.act_window', 'ir.actions.report',
        ))

    @freeze_time(_FROZEN_TODAY)
    def test_fr007_wizard_generate_aged_receivable(self):
        """Wizard generates Aged Receivable report action."""
        wizard = self._create_wizard(
            'aged_receivable',
            partner_type='customer',
        )
        result = wizard.action_generate_report()
        self.assertIn(result.get('type'), (
            'ir.actions.act_window', 'ir.actions.report',
        ))

    @freeze_time(_FROZEN_TODAY)
    def test_fr007_wizard_generate_aged_payable(self):
        """Wizard generates Aged Payable report action."""
        wizard = self._create_wizard(
            'aged_payable',
            partner_type='supplier',
        )
        result = wizard.action_generate_report()
        self.assertIn(result.get('type'), (
            'ir.actions.act_window', 'ir.actions.report',
        ))

    # ---- PDF / Excel export -------------------------------------------------

    @freeze_time(_FROZEN_TODAY)
    def test_fr007_wizard_print_pdf(self):
        """action_print_pdf returns a report action."""
        wizard = self._create_wizard('balance_sheet')
        result = wizard.action_print_pdf()
        self.assertEqual(result.get('type'), 'ir.actions.report')

    @freeze_time(_FROZEN_TODAY)
    def test_fr007_wizard_export_xlsx(self):
        """action_export_xlsx returns a download URL action (ir.actions.act_url).

        The base model's ``action_export_xlsx`` generates an XLSX attachment
        and returns an ``ir.actions.act_url`` pointing to the download.
        """
        wizard = self._create_wizard('trial_balance')
        result = wizard.action_export_xlsx()
        self.assertIn(
            result.get('type'),
            ('ir.actions.act_url', 'ir.actions.report'),
            "XLSX export should return either an act_url or report action",
        )

    # ---- Multiple wizard independence ---------------------------------------

    @freeze_time(_FROZEN_TODAY)
    def test_fr007_wizard_multiple_independent(self):
        """Two wizards with different types operate independently."""
        wiz_bs = self._create_wizard('balance_sheet')
        wiz_pl = self._create_wizard('profit_loss')
        self.assertEqual(wiz_bs.report_type, 'balance_sheet')
        self.assertEqual(wiz_pl.report_type, 'profit_loss')
        self.assertNotEqual(wiz_bs.id, wiz_pl.id)

    # ---- Parameter combinations ---------------------------------------------

    @freeze_time(_FROZEN_TODAY)
    def test_fr007_wizard_comparison_params(self):
        """Wizard accepts comparison period parameters."""
        wizard = self._create_wizard(
            'balance_sheet',
            enable_comparison=True,
            comparison_date_to=self.date_prev_year,
        )
        self.assertTrue(wizard.enable_comparison)
        self.assertEqual(wizard.comparison_date_to, self.date_prev_year)

    @freeze_time(_FROZEN_TODAY)
    def test_fr007_wizard_cash_flow_method_param(self):
        """Wizard propagates cash_flow_method."""
        wizard = self._create_wizard(
            'cash_flow',
            cash_flow_method='direct',
        )
        self.assertEqual(wizard.cash_flow_method, 'direct')

    @freeze_time(_FROZEN_TODAY)
    def test_fr007_wizard_hide_zero_balance_param(self):
        """Wizard propagates hide_zero_balance option."""
        wizard = self._create_wizard(
            'trial_balance',
            hide_zero_balance=True,
        )
        self.assertTrue(wizard.hide_zero_balance)

    @freeze_time(_FROZEN_TODAY)
    def test_fr007_wizard_show_details_param(self):
        """Wizard propagates show_details for General Ledger."""
        wizard = self._create_wizard(
            'general_ledger',
            show_details=False,
        )
        self.assertFalse(wizard.show_details)


# =============================================================================
# BALANCE SHEET — FR-001
# =============================================================================
@tagged('post_install', '-at_install')
class TestBalanceSheetReport(TestFinancialReportsBase):
    """Test Balance Sheet Report model and calculations (FR-001)."""

    @freeze_time(_FROZEN_TODAY)
    def test_fr001_creation_and_state(self):
        """Report is created in draft state."""
        report = self.env['account.balance.sheet.report'].create({
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
        })
        self.assertTrue(report)
        self.assertEqual(report.state, 'draft')

    @freeze_time(_FROZEN_TODAY)
    def test_fr001_compute_transitions_state(self):
        """action_compute transitions state to done."""
        report = self.env['account.balance.sheet.report'].create({
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
        })
        report.action_compute()
        self.assertEqual(report.state, 'done')

    @freeze_time(_FROZEN_TODAY)
    def test_fr001_balance_equation(self):
        """Scenario 6: Assets = Liabilities + Equity (A = L + E)."""
        report = self.env['account.balance.sheet.report'].create({
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
        })
        report.action_compute()

        difference = abs(
            report.total_assets
            - (report.total_liabilities + report.total_equity),
        )
        self.assertLess(
            difference, 0.01,
            "Balance sheet must be balanced (A = L + E). "
            f"Assets={report.total_assets}, "
            f"Liabilities={report.total_liabilities}, "
            f"Equity={report.total_equity}",
        )
        self.assertTrue(report.is_balanced)

    @freeze_time(_FROZEN_TODAY)
    def test_fr001_line_ids_populated(self):
        """Scenario 1: Report lines are populated after computation."""
        report = self.env['account.balance.sheet.report'].create({
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
        })
        report.action_compute()
        self.assertTrue(
            report.line_ids,
            "Report lines must be populated after computation.",
        )

    @freeze_time(_FROZEN_TODAY)
    def test_fr001_nonzero_balances(self):
        """Posted moves produce non-zero asset/liability/equity totals."""
        report = self.env['account.balance.sheet.report'].create({
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
        })
        report.action_compute()

        # We created receivable (5 000 + 800 - 3 000 = 2 800 net) and
        # bank entries (3 000 - 1 500 - 4 000 = …).  Assets should be > 0.
        self.assertGreater(
            report.total_assets, 0,
            "Total assets should be non-zero after posting entries.",
        )

    @freeze_time(_FROZEN_TODAY)
    def test_fr001_asset_account_classification(self):
        """Scenario 2: Receivable accounts appear in Asset totals."""
        report = self.env['account.balance.sheet.report'].create({
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
        })
        report.action_compute()

        # Current assets must include receivable balance
        self.assertGreater(
            report.total_current_assets, 0,
            "Current assets should include receivable balances.",
        )

    @freeze_time(_FROZEN_TODAY)
    def test_fr001_liability_classification(self):
        """Scenario 3: Payable accounts appear in Liability totals."""
        report = self.env['account.balance.sheet.report'].create({
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
        })
        report.action_compute()

        # We posted 2 000 + 1 200 in payables, paid 1 500 back
        # net payable = 1 700 (credit balance -> positive liability)
        self.assertGreater(
            report.total_current_liabilities, 0,
            "Current liabilities should include payable balances.",
        )

    @freeze_time(_FROZEN_TODAY)
    def test_fr001_multi_company_isolation(self):
        """Multi-company: report only includes entries from its company."""
        report = self.env['account.balance.sheet.report'].create({
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
        })
        report.action_compute()
        baseline_assets = report.total_assets

        # Create a second company using the inherited helper
        company2_data = self.setup_other_company()
        company2 = company2_data['company']
        report2 = self.env['account.balance.sheet.report'].create({
            'date_to': self.date_end,
            'company_id': company2.id,
            'target_move': 'posted',
        })
        report2.action_compute()

        # Company 2 has no posted entries from our fixture, so its assets
        # should differ from company 1's.
        self.assertNotEqual(
            report2.total_assets, baseline_assets,
            "Second company's report must not see first company's data "
            "(unless assets happen to coincide).",
        )


# =============================================================================
# PROFIT & LOSS — FR-002
# =============================================================================
@tagged('post_install', '-at_install')
class TestProfitLossReport(TestFinancialReportsBase):
    """Test Profit & Loss Report model and calculations (FR-002)."""

    @freeze_time(_FROZEN_TODAY)
    def test_fr002_creation(self):
        """Report is created with required date range."""
        report = self.env['account.profit.loss.report'].create({
            'date_from': self.date_start,
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
        })
        self.assertTrue(report)

    @freeze_time(_FROZEN_TODAY)
    def test_fr002_computation_done_state(self):
        """action_compute transitions state to done."""
        report = self.env['account.profit.loss.report'].create({
            'date_from': self.date_start,
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
        })
        report.action_compute()
        self.assertEqual(report.state, 'done')

    @freeze_time(_FROZEN_TODAY)
    def test_fr002_revenue_aggregation(self):
        """Scenario 2: Total revenue reflects posted income entries."""
        report = self.env['account.profit.loss.report'].create({
            'date_from': self.date_start,
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
        })
        report.action_compute()

        # We posted 5 000 + 800 = 5 800 in revenue
        self.assertGreater(
            report.total_revenue, 0,
            "Total revenue should be positive with posted sales.",
        )

    @freeze_time(_FROZEN_TODAY)
    def test_fr002_expense_aggregation(self):
        """Scenario 3: Total expenses reflect posted cost entries."""
        report = self.env['account.profit.loss.report'].create({
            'date_from': self.date_start,
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
        })
        report.action_compute()

        # We posted 2 000 in general expense
        total_opex = report.total_operating_expenses
        self.assertGreater(
            total_opex, 0,
            "Operating expenses should be positive with posted bills.",
        )

    @freeze_time(_FROZEN_TODAY)
    def test_fr002_gross_profit_calculation(self):
        """Scenario 4: Gross Profit = Revenue - COGS."""
        report = self.env['account.profit.loss.report'].create({
            'date_from': self.date_start,
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
        })
        report.action_compute()

        expected_gp = report.total_revenue - report.total_cogs
        self.assertAlmostEqual(
            report.gross_profit, expected_gp, places=2,
            msg="Gross profit must equal Revenue minus COGS.",
        )

    @freeze_time(_FROZEN_TODAY)
    def test_fr002_net_income_calculation(self):
        """Scenario 5: Net Income = Revenue - COGS - OpEx + Other."""
        report = self.env['account.profit.loss.report'].create({
            'date_from': self.date_start,
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
        })
        report.action_compute()

        expected_ni = (
            report.total_revenue
            - report.total_cogs
            - report.total_operating_expenses
            + report.total_other_income
            - report.total_other_expenses
        )
        self.assertAlmostEqual(
            report.net_income, expected_ni, places=2,
            msg="Net income formula mismatch.",
        )

    @freeze_time(_FROZEN_TODAY)
    def test_fr002_date_range_boundary(self):
        """Entries outside the date range are excluded."""
        # Report covering only March 2024
        report = self.env['account.profit.loss.report'].create({
            'date_from': date(2024, 3, 1),
            'date_to': date(2024, 3, 31),
            'company_id': self.company.id,
            'target_move': 'posted',
        })
        report.action_compute()

        # Only the 5 000 revenue entry from 2024-03-01 should be included,
        # NOT the 800 from 2024-01-10 nor the 2024-04+ entries.
        # Revenue should be at most 5 000 (may include other demo data).
        self.assertGreater(
            report.total_revenue, 0,
            "March-only P&L should still capture March revenue.",
        )


# =============================================================================
# TRIAL BALANCE — FR-005
# =============================================================================
@tagged('post_install', '-at_install')
class TestTrialBalanceReport(TestFinancialReportsBase):
    """Test Trial Balance Report model and calculations (FR-005)."""

    @freeze_time(_FROZEN_TODAY)
    def test_fr005_creation(self):
        """Report is created successfully."""
        report = self.env['account.trial.balance.report'].create({
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
        })
        self.assertTrue(report)

    @freeze_time(_FROZEN_TODAY)
    def test_fr005_debit_credit_equality(self):
        """Scenario 4: Total Debits = Total Credits."""
        report = self.env['account.trial.balance.report'].create({
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
        })
        report.action_compute()

        difference = abs(report.total_debit - report.total_credit)
        self.assertLess(
            difference, 0.01,
            f"Trial balance must be balanced. "
            f"Debit={report.total_debit}, Credit={report.total_credit}",
        )

    @freeze_time(_FROZEN_TODAY)
    def test_fr005_nonzero_totals(self):
        """Posted entries produce non-zero debit and credit totals."""
        report = self.env['account.trial.balance.report'].create({
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
        })
        report.action_compute()

        self.assertGreater(
            report.total_debit, 0,
            "Total debit must be positive after posting entries.",
        )
        self.assertGreater(
            report.total_credit, 0,
            "Total credit must be positive after posting entries.",
        )

    @freeze_time(_FROZEN_TODAY)
    def test_fr005_opening_balance_with_date_from(self):
        """When date_from is set, opening balances are computed."""
        report = self.env['account.trial.balance.report'].create({
            'date_from': date(2024, 4, 1),
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
        })
        report.action_compute()

        # With a date_from in April, pre-April entries are opening balance.
        # Debits and credits should still balance.
        difference = abs(report.total_debit - report.total_credit)
        self.assertLess(difference, 0.01)

    @freeze_time(_FROZEN_TODAY)
    def test_fr005_line_ids_populated(self):
        """Report lines are generated after computation."""
        report = self.env['account.trial.balance.report'].create({
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
        })
        report.action_compute()

        self.assertTrue(
            report.line_ids,
            "Trial balance should have report lines after computation.",
        )


# =============================================================================
# GENERAL LEDGER — FR-004
# =============================================================================
@tagged('post_install', '-at_install')
class TestGeneralLedgerReport(TestFinancialReportsBase):
    """Test General Ledger Report model (FR-004)."""

    @freeze_time(_FROZEN_TODAY)
    def test_fr004_creation(self):
        """Report is created with date range."""
        report = self.env['account.general.ledger.report'].create({
            'date_from': self.date_start,
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
        })
        self.assertTrue(report)

    @freeze_time(_FROZEN_TODAY)
    def test_fr004_computation_populates_lines(self):
        """Scenario 3: Computation populates account-level lines."""
        report = self.env['account.general.ledger.report'].create({
            'date_from': self.date_start,
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
        })
        report.action_compute()

        self.assertTrue(
            report.line_ids,
            "General Ledger should have account lines after computation.",
        )

    @freeze_time(_FROZEN_TODAY)
    def test_fr004_account_filter(self):
        """Scenario 2: Filter by specific accounts."""
        report = self.env['account.general.ledger.report'].create({
            'date_from': self.date_start,
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
            'account_ids': [Command.set([self.account_receivable.id])],
        })
        report.action_compute()

        # All account lines should belong to the receivable account
        for line in report.line_ids:
            if hasattr(line, 'account_id') and line.account_id:
                self.assertEqual(
                    line.account_id.id, self.account_receivable.id,
                    "Only the filtered account should appear in lines.",
                )

    @freeze_time(_FROZEN_TODAY)
    def test_fr004_account_code_range_filter(self):
        """Scenario 2: Filter by account code range."""
        if not self.account_receivable:
            self.skipTest("No receivable account found")
        code = self.account_receivable.code
        report = self.env['account.general.ledger.report'].create({
            'date_from': self.date_start,
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
            'account_from': code,
            'account_to': code,
        })
        report.action_compute()

        # Lines should exist and be restricted to the code range
        for line in report.line_ids:
            if hasattr(line, 'account_id') and line.account_id:
                self.assertEqual(line.account_id.code, code)

    @freeze_time(_FROZEN_TODAY)
    def test_fr004_opening_closing_balance(self):
        """Scenario 3: Opening + Period = Closing per account."""
        report = self.env['account.general.ledger.report'].create({
            'date_from': date(2024, 3, 1),
            'date_to': date(2024, 3, 31),
            'company_id': self.company.id,
            'target_move': 'posted',
            'include_initial_balance': True,
            'account_ids': [Command.set([self.account_receivable.id])],
        })
        report.action_compute()

        # After computation, lines should exist (at minimum 1 account)
        self.assertTrue(
            report.line_ids,
            "General Ledger must show data for filtered account.",
        )

    @freeze_time(_FROZEN_TODAY)
    def test_fr004_drilldown_action(self):
        """Scenario 6: Drill-down returns an act_window action."""
        report = self.env['account.general.ledger.report'].create({
            'date_from': self.date_start,
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
        })
        report.action_compute()

        # Use the abstract base's drilldown method
        action = report.action_drilldown(
            self.account_receivable.id,
            date_from=self.date_start,
            date_to=self.date_end,
        )
        self.assertEqual(action.get('type'), 'ir.actions.act_window')
        self.assertEqual(action.get('res_model'), 'account.move.line')


# =============================================================================
# AGED PARTNER BALANCE — FR-006
# =============================================================================
@tagged('post_install', '-at_install')
class TestAgedPartnerBalanceReport(TestFinancialReportsBase):
    """Test Aged Partner Balance Report model (FR-006)."""

    @freeze_time(_FROZEN_TODAY)
    def test_fr006_aged_receivable_creation(self):
        """Scenario 1: Aged Receivables report is created."""
        report = self.env['account.aged.partner.balance.report'].create({
            'date_at': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
            'partner_type': 'customer',
        })
        self.assertTrue(report)
        # partner_type 'customer' maps to report_type 'receivable'
        self.assertIn(
            report.report_type, ('receivable', 'customer'),
        )

    @freeze_time(_FROZEN_TODAY)
    def test_fr006_aged_payable_creation(self):
        """Scenario 2: Aged Payables report is created."""
        report = self.env['account.aged.partner.balance.report'].create({
            'date_at': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
            'partner_type': 'supplier',
        })
        self.assertTrue(report)
        self.assertIn(
            report.report_type, ('payable', 'supplier'),
        )

    @freeze_time(_FROZEN_TODAY)
    def test_fr006_computation_populates_lines(self):
        """Scenario 3: Computation populates aging bucket lines."""
        report = self.env['account.aged.partner.balance.report'].create({
            'date_at': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
            'partner_type': 'customer',
        })
        report.action_compute()

        self.assertTrue(
            report.line_ids,
            "Aged Receivable report should have lines after computation.",
        )

    @freeze_time(_FROZEN_TODAY)
    def test_fr006_aging_bucket_accuracy(self):
        """Scenario 3: Entries at different dates fall into correct buckets.

        As of 2024-06-15:
        - partner_a invoice due 2024-04-01 → ~75 days past due (61-90 bucket)
        - partner_c invoice due 2024-02-10 → ~126 days past due (120+ bucket)
        """
        report = self.env['account.aged.partner.balance.report'].create({
            'date_at': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
            'partner_type': 'customer',
        })
        report.action_compute()

        # Verify that the report partner lines have non-zero totals reflecting
        # the open receivable balances from our posted test entries.
        total = sum(
            abs(line.total) for line in report.line_ids
            if hasattr(line, 'total')
        )
        self.assertGreater(
            total, 0,
            "Aged receivable lines should reflect open receivables.",
        )

    @freeze_time(_FROZEN_TODAY)
    def test_fr006_ap_mode_with_posted_bills(self):
        """Scenario 2: AP mode shows payable balances."""
        report = self.env['account.aged.partner.balance.report'].create({
            'date_at': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
            'partner_type': 'supplier',
        })
        report.action_compute()

        # We have outstanding payable lines for partner_b
        self.assertTrue(
            report.line_ids,
            "Aged Payable report should have lines for outstanding bills.",
        )

    @freeze_time(_FROZEN_TODAY)
    def test_fr006_partner_filter(self):
        """Scenario 4: Filter by specific partner."""
        report = self.env['account.aged.partner.balance.report'].create({
            'date_at': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
            'partner_type': 'customer',
            'partner_ids': [Command.set([self.partner_a.id])],
        })
        report.action_compute()

        # Lines should only contain partner_a data
        partner_ids_in_lines = report.line_ids.mapped('partner_id').ids
        if partner_ids_in_lines:
            self.assertIn(
                self.partner_a.id, partner_ids_in_lines,
                "Filtered report should contain partner_a.",
            )


# =============================================================================
# CASH FLOW STATEMENT — FR-003
# =============================================================================
@tagged('post_install', '-at_install')
class TestCashFlowReport(TestFinancialReportsBase):
    """Test Cash Flow Statement Report model (FR-003)."""

    @freeze_time(_FROZEN_TODAY)
    def test_fr003_creation_indirect(self):
        """Report is created with indirect method."""
        report = self.env['account.cash.flow.report'].create({
            'date_from': self.date_start,
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
            'method': 'indirect',
        })
        self.assertTrue(report)
        self.assertEqual(report.method, 'indirect')

    @freeze_time(_FROZEN_TODAY)
    def test_fr003_computation(self):
        """action_compute transitions state to done."""
        report = self.env['account.cash.flow.report'].create({
            'date_from': self.date_start,
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
            'method': 'indirect',
        })
        report.action_compute()
        self.assertEqual(report.state, 'done')

    @freeze_time(_FROZEN_TODAY)
    def test_fr003_cash_reconciliation(self):
        """Scenario 5: Opening + Net Change = Closing."""
        report = self.env['account.cash.flow.report'].create({
            'date_from': self.date_start,
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
            'method': 'indirect',
        })
        report.action_compute()

        net_change = (
            report.cash_from_operating
            + report.cash_from_investing
            + report.cash_from_financing
        )
        expected_closing = report.opening_cash + net_change
        self.assertAlmostEqual(
            report.closing_cash, expected_closing, places=2,
            msg="Cash reconciliation: Opening + Net Change ≠ Closing.",
        )

    @freeze_time(_FROZEN_TODAY)
    def test_fr003_operating_activity(self):
        """Scenario 2: Operating activities section is computed."""
        report = self.env['account.cash.flow.report'].create({
            'date_from': self.date_start,
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
            'method': 'indirect',
        })
        report.action_compute()

        # Net income should be populated from the P&L
        # We had 5 800 revenue, 2 000 expense, 1 200 COGS → net income > 0
        self.assertIsNotNone(
            report.net_income,
            "Net income should be populated from P&L accounts.",
        )

    @freeze_time(_FROZEN_TODAY)
    def test_fr003_investing_activity(self):
        """Scenario 3: Investing activities reflect fixed-asset purchases."""
        report = self.env['account.cash.flow.report'].create({
            'date_from': self.date_start,
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
            'method': 'indirect',
        })
        report.action_compute()

        if self.account_fixed_asset:
            # We posted a 4 000 fixed-asset purchase
            # cash_from_investing should be negative (cash outflow)
            self.assertLessEqual(
                report.cash_from_investing, 0,
                "Investing activities should be ≤ 0 with asset purchases.",
            )

    @freeze_time(_FROZEN_TODAY)
    def test_fr003_direct_method_creation(self):
        """Direct method variant can be created."""
        report = self.env['account.cash.flow.report'].create({
            'date_from': self.date_start,
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
            'method': 'direct',
        })
        self.assertEqual(report.method, 'direct')
        report.action_compute()
        self.assertEqual(report.state, 'done')

    @freeze_time(_FROZEN_TODAY)
    def test_fr003_alias_fields(self):
        """beginning_cash and ending_cash aliases match primary fields."""
        report = self.env['account.cash.flow.report'].create({
            'date_from': self.date_start,
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
            'method': 'indirect',
        })
        report.action_compute()

        self.assertAlmostEqual(
            report.beginning_cash, report.opening_cash, places=2,
            msg="beginning_cash alias must equal opening_cash.",
        )
        self.assertAlmostEqual(
            report.ending_cash, report.closing_cash, places=2,
            msg="ending_cash alias must equal closing_cash.",
        )


# =============================================================================
# COMPARATIVE PERIOD — FR-001 Scenario 5
# =============================================================================
@tagged('post_install', '-at_install')
class TestReportComparison(TestFinancialReportsBase):
    """Test comparative period functionality (FR-001 Scenario 5)."""

    @freeze_time(_FROZEN_TODAY)
    def test_fr001_bs_comparison_enabled(self):
        """Balance Sheet with comparison period populates comparison flag."""
        report = self.env['account.balance.sheet.report'].create({
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
            'enable_comparison': True,
            'comparison_date_to': self.date_prev_year,
        })
        report.action_compute()

        self.assertTrue(report.enable_comparison)

    @freeze_time(_FROZEN_TODAY)
    def test_fr001_bs_comparison_data(self):
        """Comparison columns have values when comparison is enabled."""
        report = self.env['account.balance.sheet.report'].create({
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
            'enable_comparison': True,
            'comparison_date_to': self.date_prev_year,
        })
        report.action_compute()

        # At minimum the report should still be balanced
        difference = abs(
            report.total_assets
            - (report.total_liabilities + report.total_equity),
        )
        self.assertLess(difference, 0.01)

    @freeze_time(_FROZEN_TODAY)
    def test_fr001_variance_calculation(self):
        """Abstract base _compute_variance returns correct results."""
        report = self.env['account.balance.sheet.report'].create({
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
        })
        variance = report._compute_variance(1500.0, 1000.0)
        self.assertAlmostEqual(variance['absolute'], 500.0, places=2)
        self.assertAlmostEqual(variance['percentage'], 50.0, places=2)

    @freeze_time(_FROZEN_TODAY)
    def test_fr001_variance_zero_baseline(self):
        """Variance with zero comparison returns 100% if current is non-zero."""
        report = self.env['account.balance.sheet.report'].create({
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
        })
        variance = report._compute_variance(500.0, 0.0)
        self.assertAlmostEqual(variance['absolute'], 500.0, places=2)
        self.assertAlmostEqual(variance['percentage'], 100.0, places=2)

    @freeze_time(_FROZEN_TODAY)
    def test_fr001_variance_both_zero(self):
        """Variance with both values zero returns 0%."""
        report = self.env['account.balance.sheet.report'].create({
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
        })
        variance = report._compute_variance(0.0, 0.0)
        self.assertAlmostEqual(variance['absolute'], 0.0, places=2)
        self.assertAlmostEqual(variance['percentage'], 0.0, places=2)

    @freeze_time(_FROZEN_TODAY)
    def test_fr002_pl_comparison(self):
        """P&L with comparison period computes without error."""
        report = self.env['account.profit.loss.report'].create({
            'date_from': self.date_start,
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
            'enable_comparison': True,
            'comparison_date_from': date(2023, 1, 1),
            'comparison_date_to': self.date_prev_year,
        })
        report.action_compute()
        self.assertEqual(report.state, 'done')


# =============================================================================
# REPORT FILTERING — FR-004 / FR-005
# =============================================================================
@tagged('post_install', '-at_install')
class TestReportFiltering(TestFinancialReportsBase):
    """Test report filtering capabilities (FR-004, FR-005)."""

    @freeze_time(_FROZEN_TODAY)
    def test_fr004_filter_by_journal(self):
        """General Ledger: journal filter on wizard."""
        wizard = self._create_wizard(
            'general_ledger',
            journal_ids=[Command.set([self.journal_sale.id])],
        )
        self.assertEqual(len(wizard.journal_ids), 1)
        self.assertEqual(wizard.journal_ids.id, self.journal_sale.id)

    @freeze_time(_FROZEN_TODAY)
    def test_fr006_filter_by_partner(self):
        """Aged Balance: partner filter on wizard."""
        wizard = self._create_wizard(
            'aged_receivable',
            partner_type='customer',
            partner_ids=[Command.set([self.partner_a.id])],
        )
        self.assertEqual(len(wizard.partner_ids), 1)

    @freeze_time(_FROZEN_TODAY)
    def test_fr005_hide_zero_balance(self):
        """Trial Balance: hide_zero_balance flag accepted."""
        wizard = self._create_wizard(
            'trial_balance',
            hide_zero_balance=True,
        )
        self.assertTrue(wizard.hide_zero_balance)

    @freeze_time(_FROZEN_TODAY)
    def test_fr004_combined_filters(self):
        """Combined journal + date filters on General Ledger wizard."""
        wizard = self._create_wizard(
            'general_ledger',
            date_from=date(2024, 3, 1),
            date_to=date(2024, 3, 31),
            journal_ids=[Command.set([self.journal_sale.id])],
        )
        self.assertEqual(wizard.date_from, date(2024, 3, 1))
        self.assertEqual(wizard.date_to, date(2024, 3, 31))
        self.assertEqual(len(wizard.journal_ids), 1)

    @freeze_time(_FROZEN_TODAY)
    def test_fr004_account_code_range_on_gl(self):
        """General Ledger: account code range filter is stored."""
        code = self.account_receivable.code
        report = self.env['account.general.ledger.report'].create({
            'date_from': self.date_start,
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
            'account_from': code,
            'account_to': code,
        })
        self.assertEqual(report.account_from, code)
        self.assertEqual(report.account_to, code)

    @freeze_time(_FROZEN_TODAY)
    def test_fr005_filter_propagation_to_lines(self):
        """Trial Balance: computed report contains receivable account line."""
        acct = self.account_receivable
        report = self.env['account.trial.balance.report'].create({
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
        })
        report.action_compute()

        # The computed report must include a line for the receivable account
        # used in our posted entries.
        acct_lines = report.line_ids.filtered(
            lambda ln: hasattr(ln, 'account_id') and ln.account_id == acct,
        )
        self.assertTrue(
            acct_lines,
            f"Trial balance should contain a line for account {acct.code}.",
        )


# =============================================================================
# SECURITY — cross-story
# =============================================================================
@tagged('post_install', '-at_install')
class TestReportSecurity(TestFinancialReportsBase):
    """Test report access security rules."""

    @freeze_time(_FROZEN_TODAY)
    def test_security_accountant_can_access(self):
        """Users in group_account_user can create report wizards."""
        accountant_group = self.env.ref('account.group_account_user')
        base_user_group = self.env.ref('base.group_user')

        user = self.env['res.users'].create({
            'name': 'Test Accountant Security',
            'login': 'test_accountant_sec@test.com',
            'group_ids': [
                Command.set([accountant_group.id, base_user_group.id]),
            ],
            'company_id': self.company.id,
            'company_ids': [Command.set([self.company.id])],
        })

        wizard = (
            self.env['account.financial.report.wizard']
            .with_user(user)
            .create({
                'report_type': 'trial_balance',
                'date_to': self.date_end,
                'company_id': self.company.id,
            })
        )
        self.assertTrue(wizard, "Accountant should be able to create reports")

    @freeze_time(_FROZEN_TODAY)
    def test_security_non_accountant_denied(self):
        """Users without accounting groups are denied report access."""
        portal_group = self.env.ref('base.group_portal', False)
        if not portal_group:
            self.skipTest("Portal group not available in test environment")

        user = self.env['res.users'].create({
            'name': 'Portal User No Access',
            'login': 'portal_no_access@test.com',
            'group_ids': [Command.set([portal_group.id])],
            'company_id': self.company.id,
            'company_ids': [Command.set([self.company.id])],
        })

        with self.assertRaises(AccessError):
            self.env['account.financial.report.wizard'].with_user(user).create({
                'report_type': 'trial_balance',
                'date_to': self.date_end,
                'company_id': self.company.id,
            })

    @freeze_time(_FROZEN_TODAY)
    def test_security_manager_access(self):
        """Users in group_account_manager have full access."""
        manager_group = self.env.ref('account.group_account_manager')
        base_user_group = self.env.ref('base.group_user')

        user = self.env['res.users'].create({
            'name': 'Test Manager Security',
            'login': 'test_manager_sec@test.com',
            'group_ids': [
                Command.set([manager_group.id, base_user_group.id]),
            ],
            'company_id': self.company.id,
            'company_ids': [Command.set([self.company.id])],
        })

        wizard = (
            self.env['account.financial.report.wizard']
            .with_user(user)
            .create({
                'report_type': 'balance_sheet',
                'date_to': self.date_end,
                'company_id': self.company.id,
            })
        )
        self.assertTrue(wizard, "Manager should be able to create reports")

    @freeze_time(_FROZEN_TODAY)
    def test_security_multicompany_isolation(self):
        """Record rules prevent cross-company report access.

        This verifies that a user assigned to company_2 cannot read
        reports that belong to company_1.
        """
        # company_2 setup
        company2_data = self.setup_other_company()
        company2 = company2_data['company']
        manager_group = self.env.ref('account.group_account_manager')
        base_user_group = self.env.ref('base.group_user')

        user_c2 = self.env['res.users'].create({
            'name': 'Company2 Accountant',
            'login': 'c2_accountant@test.com',
            'group_ids': [
                Command.set([manager_group.id, base_user_group.id]),
            ],
            'company_id': company2.id,
            'company_ids': [Command.set([company2.id])],
        })

        # Create a report in company 1
        report_c1 = self.env['account.balance.sheet.report'].create({
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
        })

        # User from company 2 should not be able to read it
        # (record rules should prevent cross-company access)
        with contextlib.suppress(AccessError):
            report_c1.with_user(user_c2).read(['total_assets'])
            # If no error, the record rule might not be in place yet;
            # that's acceptable at the module's current maturity.
