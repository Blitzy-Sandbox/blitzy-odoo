# -*- coding: utf-8 -*-
# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Financial Report Wizard

Unified wizard for generating all financial reports:
- Balance Sheet (FR-001)
- Profit & Loss Statement (FR-002)
- Cash Flow Statement (FR-003)
- General Ledger (FR-004)
- Trial Balance (FR-005)
- Aged Partner Balance (FR-006)

This wizard provides a consistent entry point for all reports,
with common parameters and report-specific options.
"""

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class FinancialReportWizard(models.TransientModel):
    """
    Unified Financial Report Wizard.
    
    Provides selection of report type and common parameters,
    then delegates to specific report models.
    """
    _name = 'account.financial.report.wizard'
    _description = 'Financial Report Wizard'

    # -------------------------------------------------------------------------
    # REPORT SELECTION
    # -------------------------------------------------------------------------
    
    report_type = fields.Selection(
        selection=[
            ('balance_sheet', 'Balance Sheet'),
            ('profit_loss', 'Profit & Loss Statement'),
            ('cash_flow', 'Cash Flow Statement'),
            ('general_ledger', 'General Ledger'),
            ('trial_balance', 'Trial Balance'),
            ('aged_receivable', 'Aged Receivables'),
            ('aged_payable', 'Aged Payables'),
        ],
        string='Report Type',
        required=True,
        default='balance_sheet',
        help="Select the type of financial report to generate.",
    )
    
    # -------------------------------------------------------------------------
    # COMMON PARAMETERS
    # -------------------------------------------------------------------------
    
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    
    date_from = fields.Date(
        string='From Date',
        help="Start date (required for P&L, Cash Flow, General Ledger).",
    )
    
    date_to = fields.Date(
        string='To Date / As of Date',
        required=True,
        default=fields.Date.context_today,
        help="End date or as-of date for the report.",
    )
    
    target_move = fields.Selection(
        selection=[
            ('posted', 'All Posted Entries'),
            ('all', 'All Entries'),
        ],
        string='Target Moves',
        required=True,
        default='posted',
    )
    
    # -------------------------------------------------------------------------
    # COMPARISON OPTIONS
    # -------------------------------------------------------------------------
    
    enable_comparison = fields.Boolean(
        string='Enable Comparison',
        default=False,
    )
    
    comparison_date_from = fields.Date(
        string='Comparison From',
    )
    
    comparison_date_to = fields.Date(
        string='Comparison To',
    )
    
    # -------------------------------------------------------------------------
    # DISPLAY OPTIONS
    # -------------------------------------------------------------------------
    
    hide_zero_balance = fields.Boolean(
        string='Hide Zero Balances',
        default=False,
    )
    
    # -------------------------------------------------------------------------
    # GENERAL LEDGER SPECIFIC
    # -------------------------------------------------------------------------
    
    account_ids = fields.Many2many(
        comodel_name='account.account',
        string='Accounts',
        help="Filter by specific accounts (General Ledger, Trial Balance).",
    )
    
    include_initial_balance = fields.Boolean(
        string='Include Initial Balance',
        default=True,
    )
    
    sort_by = fields.Selection(
        selection=[
            ('date', 'Date'),
            ('ref', 'Reference'),
        ],
        string='Sort By',
        default='date',
    )
    
    # -------------------------------------------------------------------------
    # AGED BALANCE SPECIFIC
    # -------------------------------------------------------------------------
    
    partner_ids = fields.Many2many(
        comodel_name='res.partner',
        string='Partners',
        help="Filter by specific partners (Aged Balance reports).",
    )
    
    # -------------------------------------------------------------------------
    # VALIDATION
    # -------------------------------------------------------------------------
    
    @api.onchange('report_type')
    def _onchange_report_type(self):
        """Reset fields based on report type."""
        if self.report_type in ('balance_sheet', 'trial_balance'):
            self.date_from = False
        elif self.report_type in ('profit_loss', 'cash_flow', 'general_ledger'):
            if not self.date_from:
                # Default to fiscal year start
                fiscal_year = self.company_id.compute_fiscalyear_dates(self.date_to or fields.Date.today())
                self.date_from = fiscal_year.get('date_from')
    
    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for wizard in self:
            if wizard.date_from and wizard.date_to and wizard.date_from > wizard.date_to:
                raise UserError(_("From Date must be before To Date."))
    
    # -------------------------------------------------------------------------
    # ACTIONS
    # -------------------------------------------------------------------------
    
    def action_generate_report(self):
        """
        Generate the selected financial report.
        
        Creates appropriate report record and returns action to display it.
        """
        self.ensure_one()
        
        # Map report type to model
        report_models = {
            'balance_sheet': 'account.balance.sheet.report',
            'profit_loss': 'account.profit.loss.report',
            'cash_flow': 'account.cash.flow.report',
            'general_ledger': 'account.general.ledger.report',
            'trial_balance': 'account.trial.balance.report',
            'aged_receivable': 'account.aged.partner.balance.report',
            'aged_payable': 'account.aged.partner.balance.report',
        }
        
        model_name = report_models.get(self.report_type)
        if not model_name:
            raise UserError(_("Invalid report type selected."))
        
        # Prepare common values
        vals = {
            'company_id': self.company_id.id,
            'date_to': self.date_to,
            'target_move': self.target_move,
            'enable_comparison': self.enable_comparison,
            'hide_zero_balance': self.hide_zero_balance,
        }
        
        # Add date_from for period-based reports
        if self.report_type in ('profit_loss', 'cash_flow', 'general_ledger'):
            if not self.date_from:
                raise UserError(_("From Date is required for this report type."))
            vals['date_from'] = self.date_from
        
        # Add comparison dates
        if self.enable_comparison:
            vals['comparison_date_from'] = self.comparison_date_from
            vals['comparison_date_to'] = self.comparison_date_to
        
        # Add report-specific values
        if self.report_type == 'general_ledger':
            vals['account_ids'] = [(6, 0, self.account_ids.ids)]
            vals['include_initial_balance'] = self.include_initial_balance
            vals['sort_by'] = self.sort_by
        
        if self.report_type == 'trial_balance':
            vals['show_balance_zero'] = not self.hide_zero_balance
        
        if self.report_type in ('aged_receivable', 'aged_payable'):
            vals['report_type'] = 'receivable' if self.report_type == 'aged_receivable' else 'payable'
            vals['partner_ids'] = [(6, 0, self.partner_ids.ids)]
        
        # Create report and generate
        report = self.env[model_name].create(vals)
        return report.action_generate_report()
    
    def action_print_pdf(self):
        """Generate PDF report."""
        self.ensure_one()
        # Generate report first, then print
        action = self.action_generate_report()
        report_id = action.get('res_id')
        model = action.get('res_model')
        
        if report_id and model:
            report = self.env[model].browse(report_id)
            if hasattr(report, 'action_print_pdf'):
                return report.action_print_pdf()
        
        raise UserError(_("PDF export not available for this report type."))
    
    def action_export_xlsx(self):
        """Export report to Excel."""
        self.ensure_one()
        # Generate report first, then export
        action = self.action_generate_report()
        report_id = action.get('res_id')
        model = action.get('res_model')
        
        if report_id and model:
            report = self.env[model].browse(report_id)
            if hasattr(report, 'action_export_xlsx'):
                return report.action_export_xlsx()
        
        raise UserError(_("Excel export not available for this report type."))
