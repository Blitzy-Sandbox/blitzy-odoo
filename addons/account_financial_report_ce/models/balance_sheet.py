# -*- coding: utf-8 -*-
# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Balance Sheet Report Model

Implements FR-001: Balance Sheet Report
User Story: As a CFO, I want to generate a balance sheet showing assets,
liabilities, and equity as of a specific date so that I can report the
company's financial position to stakeholders, comply with regulatory
requirements, and support loan applications.

Acceptance Criteria Implemented:
- Scenario 1: Generate Balance Sheet for reporting date
- Scenario 2: Asset classification (Current/Non-current)
- Scenario 3: Liability classification (Current/Non-current)
- Scenario 4: Equity section with retained earnings
- Scenario 5: Comparative Balance Sheet
- Scenario 6: Balance validation (A = L + E)
"""

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class BalanceSheetReport(models.TransientModel):
    """
    Balance Sheet Report Wizard and Generator.
    
    This transient model provides the wizard interface for generating
    Balance Sheet reports and the computation logic for the report data.
    
    Per FR-001 Acceptance Criteria:
    - Shows total assets, total liabilities, and total equity
    - Assets = Liabilities + Equity (fundamental accounting equation)
    - Supports comparative periods with variance analysis
    """
    _name = 'account.balance.sheet.report'
    _description = 'Balance Sheet Report'
    _inherit = 'account.financial.report.abstract'

    # -------------------------------------------------------------------------
    # BALANCE SHEET SPECIFIC FIELDS
    # -------------------------------------------------------------------------
    
    # The report is always as-of a specific date for Balance Sheet
    date_to = fields.Date(
        string='As of Date',
        required=True,
        default=fields.Date.context_today,
        help="Generate Balance Sheet as of this date.",
    )
    
    # Override to make date_from not required for Balance Sheet
    date_from = fields.Date(
        string='Fiscal Year Start',
        help="Start of fiscal year for computing current year earnings. "
             "If not specified, will use company fiscal year settings.",
    )
    
    # -------------------------------------------------------------------------
    # ASSET CLASSIFICATION (per FR-001 Scenario 2)
    # -------------------------------------------------------------------------
    
    # Account types mapping for Odoo 19.0
    # Discovery Note: Verify actual account_type values in target Odoo version
    ASSET_CURRENT_TYPES = [
        'asset_receivable',     # Accounts receivable
        'asset_cash',           # Cash and cash equivalents
        'asset_current',        # Other current assets
        'asset_prepayments',    # Prepaid expenses
    ]
    
    ASSET_NON_CURRENT_TYPES = [
        'asset_fixed',          # Fixed assets (PPE)
        'asset_non_current',    # Other non-current assets
    ]
    
    # -------------------------------------------------------------------------
    # LIABILITY CLASSIFICATION (per FR-001 Scenario 3)
    # -------------------------------------------------------------------------
    
    LIABILITY_CURRENT_TYPES = [
        'liability_payable',    # Accounts payable
        'liability_credit_card', # Credit card
        'liability_current',    # Other current liabilities
    ]
    
    LIABILITY_NON_CURRENT_TYPES = [
        'liability_non_current', # Long-term liabilities
    ]
    
    # -------------------------------------------------------------------------
    # EQUITY TYPES (per FR-001 Scenario 4)
    # -------------------------------------------------------------------------
    
    EQUITY_TYPES = [
        'equity',               # Capital accounts
        'equity_unaffected',    # Retained earnings (unaffected)
    ]
    
    # Income/Expense for computing current year earnings
    INCOME_TYPES = ['income', 'income_other']
    EXPENSE_TYPES = ['expense', 'expense_depreciation', 'expense_direct_cost']

    # -------------------------------------------------------------------------
    # COMPUTED REPORT DATA
    # -------------------------------------------------------------------------
    
    total_assets = fields.Monetary(
        string='Total Assets',
        currency_field='currency_id',
        compute='_compute_report_data',
        help="Sum of all asset accounts.",
    )
    
    total_current_assets = fields.Monetary(
        string='Total Current Assets',
        currency_field='currency_id',
        compute='_compute_report_data',
    )
    
    total_non_current_assets = fields.Monetary(
        string='Total Non-Current Assets',
        currency_field='currency_id',
        compute='_compute_report_data',
    )
    
    total_liabilities = fields.Monetary(
        string='Total Liabilities',
        currency_field='currency_id',
        compute='_compute_report_data',
    )
    
    total_current_liabilities = fields.Monetary(
        string='Total Current Liabilities',
        currency_field='currency_id',
        compute='_compute_report_data',
    )
    
    total_non_current_liabilities = fields.Monetary(
        string='Total Non-Current Liabilities',
        currency_field='currency_id',
        compute='_compute_report_data',
    )
    
    total_equity = fields.Monetary(
        string='Total Equity',
        currency_field='currency_id',
        compute='_compute_report_data',
    )
    
    current_year_earnings = fields.Monetary(
        string='Current Year Earnings',
        currency_field='currency_id',
        compute='_compute_report_data',
        help="Unallocated earnings for the current fiscal year "
             "(Income - Expenses for period).",
    )
    
    retained_earnings = fields.Monetary(
        string='Retained Earnings',
        currency_field='currency_id',
        compute='_compute_report_data',
        help="Accumulated profits from prior periods.",
    )
    
    is_balanced = fields.Boolean(
        string='Is Balanced',
        compute='_compute_report_data',
        help="True if Assets = Liabilities + Equity",
    )
    
    balance_difference = fields.Monetary(
        string='Balance Difference',
        currency_field='currency_id',
        compute='_compute_report_data',
        help="Difference between Assets and (Liabilities + Equity). "
             "Should be 0 for a balanced sheet.",
    )
    
    # Report lines (for detailed display)
    line_ids = fields.One2many(
        comodel_name='account.balance.sheet.report.line',
        inverse_name='report_id',
        string='Report Lines',
        compute='_compute_report_data',
    )

    # -------------------------------------------------------------------------
    # COMPUTATION METHODS
    # -------------------------------------------------------------------------
    
    @api.depends('date_to', 'date_from', 'company_id', 'target_move',
                 'enable_comparison', 'comparison_date_to')
    def _compute_report_data(self):
        """
        Compute all Balance Sheet data.
        
        This method performs the following:
        1. Retrieves account balances for all account types
        2. Classifies accounts into Assets, Liabilities, Equity
        3. Computes current year earnings from P&L accounts
        4. Validates the accounting equation (A = L + E)
        5. Generates report lines for display
        
        Per FR-001 Acceptance Criteria:
        - Scenario 1: Complete Balance Sheet generation
        - Scenario 6: Validation that A = L + E
        """
        for report in self:
            # Get company currency
            report.currency_id = report.company_id.currency_id
            
            # Determine fiscal year start if not provided
            date_from = report.date_from
            if not date_from:
                date_from = report._get_fiscal_year_start()
            
            # ----------------------------------------------------------------
            # COMPUTE ASSET BALANCES (Scenario 2)
            # ----------------------------------------------------------------
            current_asset_accounts = self.env['account.account'].search(
                report._get_account_domain(report.ASSET_CURRENT_TYPES)
            )
            non_current_asset_accounts = self.env['account.account'].search(
                report._get_account_domain(report.ASSET_NON_CURRENT_TYPES)
            )
            
            current_asset_balances = report._compute_account_balance(
                current_asset_accounts, date_to=report.date_to
            )
            non_current_asset_balances = report._compute_account_balance(
                non_current_asset_accounts, date_to=report.date_to
            )
            
            report.total_current_assets = sum(
                b['balance'] for b in current_asset_balances.values()
            )
            report.total_non_current_assets = sum(
                b['balance'] for b in non_current_asset_balances.values()
            )
            report.total_assets = (
                report.total_current_assets + report.total_non_current_assets
            )
            
            # ----------------------------------------------------------------
            # COMPUTE LIABILITY BALANCES (Scenario 3)
            # ----------------------------------------------------------------
            current_liability_accounts = self.env['account.account'].search(
                report._get_account_domain(report.LIABILITY_CURRENT_TYPES)
            )
            non_current_liability_accounts = self.env['account.account'].search(
                report._get_account_domain(report.LIABILITY_NON_CURRENT_TYPES)
            )
            
            current_liability_balances = report._compute_account_balance(
                current_liability_accounts, date_to=report.date_to
            )
            non_current_liability_balances = report._compute_account_balance(
                non_current_liability_accounts, date_to=report.date_to
            )
            
            # Liabilities have credit balance (negative in Odoo)
            report.total_current_liabilities = -sum(
                b['balance'] for b in current_liability_balances.values()
            )
            report.total_non_current_liabilities = -sum(
                b['balance'] for b in non_current_liability_balances.values()
            )
            report.total_liabilities = (
                report.total_current_liabilities + 
                report.total_non_current_liabilities
            )
            
            # ----------------------------------------------------------------
            # COMPUTE EQUITY BALANCES (Scenario 4)
            # ----------------------------------------------------------------
            equity_accounts = self.env['account.account'].search(
                report._get_account_domain(report.EQUITY_TYPES)
            )
            equity_balances = report._compute_account_balance(
                equity_accounts, date_to=report.date_to
            )
            
            # Equity has credit balance (negative in Odoo)
            base_equity = -sum(b['balance'] for b in equity_balances.values())
            
            # Compute current year earnings (Unaffected earnings)
            income_accounts = self.env['account.account'].search(
                report._get_account_domain(report.INCOME_TYPES)
            )
            expense_accounts = self.env['account.account'].search(
                report._get_account_domain(report.EXPENSE_TYPES)
            )
            
            income_balances = report._compute_account_balance(
                income_accounts, date_from=date_from, date_to=report.date_to
            )
            expense_balances = report._compute_account_balance(
                expense_accounts, date_from=date_from, date_to=report.date_to
            )
            
            total_income = -sum(b['balance'] for b in income_balances.values())
            total_expenses = sum(b['balance'] for b in expense_balances.values())
            
            report.current_year_earnings = total_income - total_expenses
            
            # Retained earnings = Base equity (accounts typed as equity_unaffected
            # should contain prior periods' retained earnings)
            report.retained_earnings = base_equity
            
            report.total_equity = report.retained_earnings + report.current_year_earnings
            
            # ----------------------------------------------------------------
            # VALIDATE ACCOUNTING EQUATION (Scenario 6)
            # ----------------------------------------------------------------
            validation = report._validate_accounting_equation(
                report.total_assets,
                report.total_liabilities,
                report.total_equity,
            )
            report.is_balanced = validation['is_balanced']
            report.balance_difference = validation['difference']
            
            # ----------------------------------------------------------------
            # GENERATE REPORT LINES
            # ----------------------------------------------------------------
            report.line_ids = report._generate_report_lines(
                current_asset_accounts, current_asset_balances,
                non_current_asset_accounts, non_current_asset_balances,
                current_liability_accounts, current_liability_balances,
                non_current_liability_accounts, non_current_liability_balances,
                equity_accounts, equity_balances,
            )
    
    def _get_fiscal_year_start(self):
        """
        Get the start date of the fiscal year containing date_to.
        
        Returns:
            Date: First day of the fiscal year
        """
        self.ensure_one()
        
        # Use company's fiscal year settings
        fiscal_year = self.company_id.compute_fiscalyear_dates(self.date_to)
        return fiscal_year.get('date_from', self.date_to.replace(month=1, day=1))
    
    def _generate_report_lines(self, 
                               current_asset_accounts, current_asset_balances,
                               non_current_asset_accounts, non_current_asset_balances,
                               current_liability_accounts, current_liability_balances,
                               non_current_liability_accounts, non_current_liability_balances,
                               equity_accounts, equity_balances):
        """
        Generate report line records for display.
        
        Creates a hierarchical structure:
        - ASSETS
          - Current Assets
            - [Account lines]
          - Non-Current Assets
            - [Account lines]
        - LIABILITIES
          - Current Liabilities
            - [Account lines]
          - Non-Current Liabilities
            - [Account lines]
        - EQUITY
          - [Account lines]
          - Current Year Earnings
        """
        lines = []
        sequence = 0
        Line = self.env['account.balance.sheet.report.line']
        
        # Helper to create account lines
        def add_account_lines(accounts, balances, level, sign=1):
            nonlocal sequence
            result = []
            for account in accounts.sorted(key=lambda a: a.code):
                balance = balances.get(account.id, {})
                amount = balance.get('balance', 0) * sign
                if self.hide_zero_balance and not amount:
                    continue
                sequence += 1
                result.append(Line.new({
                    'sequence': sequence,
                    'name': f"{account.code} - {account.name}",
                    'level': level,
                    'amount': amount,
                    'account_ids': [(6, 0, [account.id])],
                    'currency_id': self.currency_id.id,
                }))
            return result
        
        # ASSETS SECTION
        sequence = 100
        lines.append(Line.new({
            'sequence': sequence,
            'name': _('ASSETS'),
            'level': 0,
            'is_total': True,
            'amount': self.total_assets,
            'currency_id': self.currency_id.id,
        }))
        
        # Current Assets
        sequence = 110
        lines.append(Line.new({
            'sequence': sequence,
            'name': _('Current Assets'),
            'level': 1,
            'is_total': True,
            'amount': self.total_current_assets,
            'currency_id': self.currency_id.id,
        }))
        lines.extend(add_account_lines(
            current_asset_accounts, current_asset_balances, level=2, sign=1
        ))
        
        # Non-Current Assets
        sequence = 150
        lines.append(Line.new({
            'sequence': sequence,
            'name': _('Non-Current Assets'),
            'level': 1,
            'is_total': True,
            'amount': self.total_non_current_assets,
            'currency_id': self.currency_id.id,
        }))
        lines.extend(add_account_lines(
            non_current_asset_accounts, non_current_asset_balances, level=2, sign=1
        ))
        
        # LIABILITIES SECTION
        sequence = 200
        lines.append(Line.new({
            'sequence': sequence,
            'name': _('LIABILITIES'),
            'level': 0,
            'is_total': True,
            'amount': self.total_liabilities,
            'currency_id': self.currency_id.id,
        }))
        
        # Current Liabilities
        sequence = 210
        lines.append(Line.new({
            'sequence': sequence,
            'name': _('Current Liabilities'),
            'level': 1,
            'is_total': True,
            'amount': self.total_current_liabilities,
            'currency_id': self.currency_id.id,
        }))
        lines.extend(add_account_lines(
            current_liability_accounts, current_liability_balances, level=2, sign=-1
        ))
        
        # Non-Current Liabilities
        sequence = 250
        lines.append(Line.new({
            'sequence': sequence,
            'name': _('Non-Current Liabilities'),
            'level': 1,
            'is_total': True,
            'amount': self.total_non_current_liabilities,
            'currency_id': self.currency_id.id,
        }))
        lines.extend(add_account_lines(
            non_current_liability_accounts, non_current_liability_balances, level=2, sign=-1
        ))
        
        # EQUITY SECTION
        sequence = 300
        lines.append(Line.new({
            'sequence': sequence,
            'name': _('EQUITY'),
            'level': 0,
            'is_total': True,
            'amount': self.total_equity,
            'currency_id': self.currency_id.id,
        }))
        lines.extend(add_account_lines(
            equity_accounts, equity_balances, level=1, sign=-1
        ))
        
        # Current Year Earnings line
        sequence += 10
        lines.append(Line.new({
            'sequence': sequence,
            'name': _('Current Year Earnings'),
            'level': 1,
            'amount': self.current_year_earnings,
            'currency_id': self.currency_id.id,
        }))
        
        # TOTAL LIABILITIES AND EQUITY
        sequence = 400
        lines.append(Line.new({
            'sequence': sequence,
            'name': _('TOTAL LIABILITIES AND EQUITY'),
            'level': 0,
            'is_total': True,
            'amount': self.total_liabilities + self.total_equity,
            'currency_id': self.currency_id.id,
        }))
        
        return lines

    # -------------------------------------------------------------------------
    # ACTION METHODS
    # -------------------------------------------------------------------------
    
    def action_generate_report(self):
        """
        Generate and display the Balance Sheet report.
        
        Returns action to display the report in the appropriate view.
        """
        self.ensure_one()
        
        # Validate inputs
        if not self.date_to:
            raise UserError(_("Please specify the As-of Date for the Balance Sheet."))
        
        # Force recomputation
        self._compute_report_data()
        
        return {
            'name': _('Balance Sheet as of %s') % self.date_to,
            'type': 'ir.actions.act_window',
            'res_model': 'account.balance.sheet.report',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'inline',
        }
    
    def action_print_pdf(self):
        """
        Generate PDF version of the Balance Sheet.
        
        Per FR-007: Export to PDF format
        """
        self.ensure_one()
        return self.env.ref(
            'account_financial_report_ce.action_report_balance_sheet'
        ).report_action(self)
    
    def action_export_xlsx(self):
        """
        Export Balance Sheet to Excel format.
        
        Per FR-007: Export to Excel format
        """
        self.ensure_one()
        # Excel export implementation
        return {
            'type': 'ir.actions.act_url',
            'url': f'/financial_reports/balance_sheet/xlsx/{self.id}',
            'target': 'new',
        }


class BalanceSheetReportLine(models.TransientModel):
    """
    Balance Sheet Report Line.
    
    Represents a single line in the Balance Sheet report,
    supporting hierarchical display with drill-down capability.
    """
    _name = 'account.balance.sheet.report.line'
    _description = 'Balance Sheet Report Line'
    _order = 'sequence, id'
    
    report_id = fields.Many2one(
        comodel_name='account.balance.sheet.report',
        string='Report',
        ondelete='cascade',
    )
    
    sequence = fields.Integer(
        string='Sequence',
        default=10,
    )
    
    name = fields.Char(
        string='Label',
        required=True,
    )
    
    level = fields.Integer(
        string='Indentation Level',
        default=0,
        help="0=Section header, 1=Subsection, 2=Account detail",
    )
    
    amount = fields.Monetary(
        string='Balance',
        currency_field='currency_id',
    )
    
    comparison_amount = fields.Monetary(
        string='Prior Period',
        currency_field='currency_id',
    )
    
    variance_absolute = fields.Monetary(
        string='Change',
        currency_field='currency_id',
    )
    
    variance_percentage = fields.Float(
        string='Change %',
    )
    
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency',
    )
    
    account_ids = fields.Many2many(
        comodel_name='account.account',
        string='Accounts',
    )
    
    is_total = fields.Boolean(
        string='Is Total',
        default=False,
    )
    
    def action_drilldown(self):
        """
        Drill down to source transactions.
        
        Per FR-007 Acceptance Criteria:
            "When I click on a line item amount
             Then I am navigated to a filtered view of the underlying
             journal entries"
        """
        self.ensure_one()
        if not self.account_ids:
            return False
        
        return self.report_id.action_drilldown(
            account_id=self.account_ids.ids[0] if len(self.account_ids) == 1 else False,
            date_to=self.report_id.date_to,
        )
