# -*- coding: utf-8 -*-
# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Cash Flow Statement Report Model

Implements FR-003: Cash Flow Statement
User Story: As a CFO, I want to generate a cash flow statement showing cash
movements from operating, investing, and financing activities so that I can
analyze the company's liquidity and cash management.

Acceptance Criteria:
- Scenario 1: Generate Cash Flow Statement for date range
- Scenario 2: Operating activities section (indirect method)
- Scenario 3: Investing activities section
- Scenario 4: Financing activities section
- Scenario 5: Net change in cash reconciliation
- Scenario 6: Comparative Cash Flow with variance analysis
"""

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class CashFlowReport(models.TransientModel):
    """
    Cash Flow Statement Report.
    
    Generates statement of cash flows using the indirect method,
    showing cash from operating, investing, and financing activities.
    """
    _name = 'account.cash.flow.report'
    _description = 'Cash Flow Statement Report'
    _inherit = 'account.financial.report.abstract'

    # -------------------------------------------------------------------------
    # CASH FLOW SPECIFIC FIELDS
    # -------------------------------------------------------------------------
    
    date_from = fields.Date(
        string='From Date',
        required=True,
        help="Start date of the cash flow period.",
    )
    
    date_to = fields.Date(
        string='To Date',
        required=True,
        default=fields.Date.context_today,
        help="End date of the cash flow period.",
    )
    
    method = fields.Selection(
        selection=[
            ('indirect', 'Indirect Method'),
            ('direct', 'Direct Method'),
        ],
        string='Method',
        default='indirect',
        help="Cash flow calculation method. Indirect method starts with "
             "net income and adjusts for non-cash items.",
    )
    
    # Account types for cash flow classification
    CASH_TYPES = ['asset_cash']
    RECEIVABLE_TYPES = ['asset_receivable']
    PAYABLE_TYPES = ['liability_payable']
    FIXED_ASSET_TYPES = ['asset_fixed']
    EQUITY_TYPES = ['equity']
    LIABILITY_TYPES = ['liability_non_current']
    
    # -------------------------------------------------------------------------
    # COMPUTED REPORT DATA
    # -------------------------------------------------------------------------
    
    # Opening and closing cash
    opening_cash = fields.Monetary(
        string='Opening Cash',
        currency_field='currency_id',
        compute='_compute_report_data',
    )
    
    closing_cash = fields.Monetary(
        string='Closing Cash',
        currency_field='currency_id',
        compute='_compute_report_data',
    )
    
    # Operating Activities
    net_income = fields.Monetary(
        string='Net Income',
        currency_field='currency_id',
        compute='_compute_report_data',
    )
    
    depreciation_amortization = fields.Monetary(
        string='Depreciation & Amortization',
        currency_field='currency_id',
        compute='_compute_report_data',
    )
    
    change_in_receivables = fields.Monetary(
        string='Change in Receivables',
        currency_field='currency_id',
        compute='_compute_report_data',
    )
    
    change_in_payables = fields.Monetary(
        string='Change in Payables',
        currency_field='currency_id',
        compute='_compute_report_data',
    )
    
    change_in_inventory = fields.Monetary(
        string='Change in Inventory',
        currency_field='currency_id',
        compute='_compute_report_data',
    )
    
    cash_from_operating = fields.Monetary(
        string='Cash from Operating Activities',
        currency_field='currency_id',
        compute='_compute_report_data',
    )
    
    # Investing Activities
    capital_expenditures = fields.Monetary(
        string='Capital Expenditures',
        currency_field='currency_id',
        compute='_compute_report_data',
    )
    
    asset_disposals = fields.Monetary(
        string='Proceeds from Asset Sales',
        currency_field='currency_id',
        compute='_compute_report_data',
    )
    
    cash_from_investing = fields.Monetary(
        string='Cash from Investing Activities',
        currency_field='currency_id',
        compute='_compute_report_data',
    )
    
    # Financing Activities
    debt_proceeds = fields.Monetary(
        string='Proceeds from Borrowings',
        currency_field='currency_id',
        compute='_compute_report_data',
    )
    
    debt_repayments = fields.Monetary(
        string='Debt Repayments',
        currency_field='currency_id',
        compute='_compute_report_data',
    )
    
    dividends_paid = fields.Monetary(
        string='Dividends Paid',
        currency_field='currency_id',
        compute='_compute_report_data',
    )
    
    cash_from_financing = fields.Monetary(
        string='Cash from Financing Activities',
        currency_field='currency_id',
        compute='_compute_report_data',
    )
    
    # Net change
    net_change_in_cash = fields.Monetary(
        string='Net Change in Cash',
        currency_field='currency_id',
        compute='_compute_report_data',
    )
    
    is_reconciled = fields.Boolean(
        string='Is Reconciled',
        compute='_compute_report_data',
        help="True if Opening + Net Change = Closing",
    )
    
    line_ids = fields.One2many(
        comodel_name='account.cash.flow.report.line',
        inverse_name='report_id',
        string='Report Lines',
        compute='_compute_report_data',
    )

    @api.depends('date_from', 'date_to', 'company_id', 'target_move', 'method')
    def _compute_report_data(self):
        """
        Compute Cash Flow Statement data.
        
        For indirect method:
        1. Start with Net Income from P&L
        2. Add back non-cash expenses (depreciation)
        3. Adjust for changes in working capital
        4. Calculate investing activities
        5. Calculate financing activities
        6. Verify cash reconciliation
        """
        for report in self:
            report.currency_id = report.company_id.currency_id
            
            # Get opening cash balance
            cash_accounts = self.env['account.account'].search(
                report._get_account_domain(report.CASH_TYPES)
            )
            
            # Opening cash (balance as of date_from - 1)
            opening_balances = report._compute_account_balance(
                cash_accounts, 
                date_to=fields.Date.subtract(report.date_from, days=1)
            )
            report.opening_cash = sum(b['balance'] for b in opening_balances.values())
            
            # Closing cash (balance as of date_to)
            closing_balances = report._compute_account_balance(
                cash_accounts, date_to=report.date_to
            )
            report.closing_cash = sum(b['balance'] for b in closing_balances.values())
            
            # ----------------------------------------------------------------
            # OPERATING ACTIVITIES (Indirect Method)
            # ----------------------------------------------------------------
            
            # Net Income from P&L
            pl_report = self.env['account.profit.loss.report'].new({
                'company_id': report.company_id.id,
                'date_from': report.date_from,
                'date_to': report.date_to,
                'target_move': report.target_move,
            })
            pl_report._compute_report_data()
            report.net_income = pl_report.net_income
            
            # Depreciation (non-cash expense add-back)
            depreciation_accounts = self.env['account.account'].search(
                report._get_account_domain(['expense_depreciation'])
            )
            depreciation_balances = report._compute_account_balance(
                depreciation_accounts,
                date_from=report.date_from,
                date_to=report.date_to
            )
            report.depreciation_amortization = sum(
                b['balance'] for b in depreciation_balances.values()
            )
            
            # Change in Receivables
            receivable_accounts = self.env['account.account'].search(
                report._get_account_domain(report.RECEIVABLE_TYPES)
            )
            opening_ar = report._compute_account_balance(
                receivable_accounts,
                date_to=fields.Date.subtract(report.date_from, days=1)
            )
            closing_ar = report._compute_account_balance(
                receivable_accounts, date_to=report.date_to
            )
            report.change_in_receivables = -(
                sum(b['balance'] for b in closing_ar.values()) -
                sum(b['balance'] for b in opening_ar.values())
            )
            
            # Change in Payables
            payable_accounts = self.env['account.account'].search(
                report._get_account_domain(report.PAYABLE_TYPES)
            )
            opening_ap = report._compute_account_balance(
                payable_accounts,
                date_to=fields.Date.subtract(report.date_from, days=1)
            )
            closing_ap = report._compute_account_balance(
                payable_accounts, date_to=report.date_to
            )
            report.change_in_payables = -(
                sum(b['balance'] for b in closing_ap.values()) -
                sum(b['balance'] for b in opening_ap.values())
            )
            
            # Inventory changes (placeholder - requires inventory module)
            report.change_in_inventory = 0.0
            
            # Cash from Operating Activities
            report.cash_from_operating = (
                report.net_income +
                report.depreciation_amortization +
                report.change_in_receivables +
                report.change_in_payables +
                report.change_in_inventory
            )
            
            # ----------------------------------------------------------------
            # INVESTING ACTIVITIES
            # ----------------------------------------------------------------
            
            # Fixed asset changes
            fixed_asset_accounts = self.env['account.account'].search(
                report._get_account_domain(report.FIXED_ASSET_TYPES)
            )
            opening_fa = report._compute_account_balance(
                fixed_asset_accounts,
                date_to=fields.Date.subtract(report.date_from, days=1)
            )
            closing_fa = report._compute_account_balance(
                fixed_asset_accounts, date_to=report.date_to
            )
            fa_change = (
                sum(b['balance'] for b in closing_fa.values()) -
                sum(b['balance'] for b in opening_fa.values())
            )
            
            # Simplified: all FA increases are CapEx, decreases are disposals
            report.capital_expenditures = -max(fa_change, 0)
            report.asset_disposals = -min(fa_change, 0)
            
            report.cash_from_investing = (
                report.capital_expenditures + report.asset_disposals
            )
            
            # ----------------------------------------------------------------
            # FINANCING ACTIVITIES
            # ----------------------------------------------------------------
            
            # Long-term debt changes
            debt_accounts = self.env['account.account'].search(
                report._get_account_domain(report.LIABILITY_TYPES)
            )
            opening_debt = report._compute_account_balance(
                debt_accounts,
                date_to=fields.Date.subtract(report.date_from, days=1)
            )
            closing_debt = report._compute_account_balance(
                debt_accounts, date_to=report.date_to
            )
            debt_change = -(
                sum(b['balance'] for b in closing_debt.values()) -
                sum(b['balance'] for b in opening_debt.values())
            )
            
            report.debt_proceeds = max(debt_change, 0)
            report.debt_repayments = -min(debt_change, 0)
            report.dividends_paid = 0.0  # Would need specific dividend accounts
            
            report.cash_from_financing = (
                report.debt_proceeds - 
                report.debt_repayments - 
                report.dividends_paid
            )
            
            # ----------------------------------------------------------------
            # NET CHANGE AND RECONCILIATION
            # ----------------------------------------------------------------
            
            report.net_change_in_cash = (
                report.cash_from_operating +
                report.cash_from_investing +
                report.cash_from_financing
            )
            
            # Verify: Opening + Net Change = Closing
            expected_closing = report.opening_cash + report.net_change_in_cash
            report.is_reconciled = abs(expected_closing - report.closing_cash) < 0.01
            
            report.line_ids = []  # Placeholder for line generation

    def action_generate_report(self):
        """Generate and display the Cash Flow Statement."""
        self.ensure_one()
        if not self.date_from or not self.date_to:
            raise UserError(_("Please specify the date range."))
        
        self._compute_report_data()
        
        return {
            'name': _('Cash Flow: %s to %s') % (self.date_from, self.date_to),
            'type': 'ir.actions.act_window',
            'res_model': 'account.cash.flow.report',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'inline',
        }


class CashFlowReportLine(models.TransientModel):
    """Cash Flow Report Line."""
    _name = 'account.cash.flow.report.line'
    _description = 'Cash Flow Report Line'
    _order = 'sequence, id'
    
    report_id = fields.Many2one(
        comodel_name='account.cash.flow.report',
        string='Report',
        ondelete='cascade',
    )
    sequence = fields.Integer(string='Sequence', default=10)
    name = fields.Char(string='Label', required=True)
    level = fields.Integer(string='Level', default=0)
    amount = fields.Monetary(string='Amount', currency_field='currency_id')
    comparison_amount = fields.Monetary(string='Comparison', currency_field='currency_id')
    variance_absolute = fields.Monetary(string='Variance', currency_field='currency_id')
    variance_percentage = fields.Float(string='Variance %')
    currency_id = fields.Many2one('res.currency', string='Currency')
    activity_type = fields.Selection(
        selection=[
            ('operating', 'Operating'),
            ('investing', 'Investing'),
            ('financing', 'Financing'),
        ],
        string='Activity Type',
    )
    is_total = fields.Boolean(string='Is Total', default=False)
