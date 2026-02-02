# -*- coding: utf-8 -*-
# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
General Ledger Report Model

Implements FR-004: General Ledger Report
User Story: As an Accountant, I want to generate a general ledger showing all
transactions by account so that I can verify account activity and trace
individual transactions.

Acceptance Criteria:
- Scenario 1: Generate General Ledger for date range
- Scenario 2: Filter by specific accounts or account ranges
- Scenario 3: Show opening balance, transactions, closing balance per account
- Scenario 4: Transaction detail with date, reference, description, debit, credit
- Scenario 5: Sort by date or document reference
- Scenario 6: Drill-down to source journal entries
"""

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class GeneralLedgerReport(models.TransientModel):
    """
    General Ledger Report.
    
    Shows all transactions for each account within a date range,
    with opening balance, transaction details, and closing balance.
    """
    _name = 'account.general.ledger.report'
    _description = 'General Ledger Report'
    _inherit = 'account.financial.report.abstract'

    # -------------------------------------------------------------------------
    # GENERAL LEDGER SPECIFIC FIELDS
    # -------------------------------------------------------------------------
    
    date_from = fields.Date(
        string='From Date',
        required=True,
        help="Start date for transactions to include.",
    )
    
    date_to = fields.Date(
        string='To Date',
        required=True,
        default=fields.Date.context_today,
        help="End date for transactions to include.",
    )
    
    account_ids = fields.Many2many(
        comodel_name='account.account',
        string='Accounts',
        help="Specific accounts to include. Leave empty for all accounts.",
    )
    
    account_from = fields.Char(
        string='From Account Code',
        help="Starting account code for range filter.",
    )
    
    account_to = fields.Char(
        string='To Account Code',
        help="Ending account code for range filter.",
    )
    
    include_initial_balance = fields.Boolean(
        string='Include Initial Balance',
        default=True,
        help="Show opening balance for each account.",
    )
    
    sort_by = fields.Selection(
        selection=[
            ('date', 'Date'),
            ('ref', 'Reference'),
            ('name', 'Description'),
        ],
        string='Sort By',
        default='date',
        help="Sort transactions within each account by this field.",
    )
    
    centralize = fields.Boolean(
        string='Centralize Partners',
        default=False,
        help="Group transactions by partner within each account.",
    )
    
    # -------------------------------------------------------------------------
    # COMPUTED REPORT DATA
    # -------------------------------------------------------------------------
    
    account_line_ids = fields.One2many(
        comodel_name='account.general.ledger.report.account',
        inverse_name='report_id',
        string='Account Lines',
        compute='_compute_report_data',
    )

    @api.depends('date_from', 'date_to', 'company_id', 'target_move',
                 'account_ids', 'account_from', 'account_to',
                 'include_initial_balance', 'sort_by')
    def _compute_report_data(self):
        """
        Compute General Ledger report data.
        
        For each account:
        1. Calculate opening balance
        2. Retrieve all transactions in date range
        3. Calculate running balance
        4. Calculate closing balance
        """
        for report in self:
            report.currency_id = report.company_id.currency_id
            
            # Determine which accounts to include
            domain = [('company_id', '=', report.company_id.id)]
            
            if report.account_ids:
                domain.append(('id', 'in', report.account_ids.ids))
            
            if report.account_from:
                domain.append(('code', '>=', report.account_from))
            
            if report.account_to:
                domain.append(('code', '<=', report.account_to))
            
            accounts = self.env['account.account'].search(domain, order='code')
            
            # Build account lines
            account_lines = []
            AccountLine = self.env['account.general.ledger.report.account']
            
            for account in accounts:
                # Opening balance
                if report.include_initial_balance:
                    opening_balance = report._compute_account_balance(
                        account,
                        date_to=fields.Date.subtract(report.date_from, days=1)
                    ).get(account.id, {}).get('balance', 0.0)
                else:
                    opening_balance = 0.0
                
                # Get transactions
                move_line_domain = report._get_move_line_domain(
                    date_from=report.date_from,
                    date_to=report.date_to,
                    account_ids=[account.id],
                )
                
                order_field = {
                    'date': 'date, id',
                    'ref': 'ref, date, id',
                    'name': 'name, date, id',
                }.get(report.sort_by, 'date, id')
                
                move_lines = self.env['account.move.line'].search(
                    move_line_domain, order=order_field
                )
                
                # Skip accounts with no activity if hiding zero balance
                if report.hide_zero_balance and not move_lines and opening_balance == 0:
                    continue
                
                # Create account line
                total_debit = sum(move_lines.mapped('debit'))
                total_credit = sum(move_lines.mapped('credit'))
                closing_balance = opening_balance + total_debit - total_credit
                
                account_line = AccountLine.new({
                    'report_id': report.id,
                    'account_id': account.id,
                    'name': f"{account.code} - {account.name}",
                    'opening_balance': opening_balance,
                    'total_debit': total_debit,
                    'total_credit': total_credit,
                    'closing_balance': closing_balance,
                    'currency_id': report.currency_id.id,
                })
                
                # Add transaction lines
                transaction_lines = []
                TransactionLine = self.env['account.general.ledger.report.line']
                running_balance = opening_balance
                
                for ml in move_lines:
                    running_balance += ml.debit - ml.credit
                    transaction_lines.append(TransactionLine.new({
                        'account_line_id': account_line.id,
                        'move_line_id': ml.id,
                        'date': ml.date,
                        'journal_id': ml.journal_id.id,
                        'move_id': ml.move_id.id,
                        'ref': ml.ref or ml.move_id.ref,
                        'name': ml.name,
                        'partner_id': ml.partner_id.id,
                        'debit': ml.debit,
                        'credit': ml.credit,
                        'balance': running_balance,
                        'currency_id': report.currency_id.id,
                    }))
                
                account_line.line_ids = transaction_lines
                account_lines.append(account_line)
            
            report.account_line_ids = account_lines

    def action_generate_report(self):
        """Generate and display the General Ledger report."""
        self.ensure_one()
        if not self.date_from or not self.date_to:
            raise UserError(_("Please specify the date range."))
        
        self._compute_report_data()
        
        return {
            'name': _('General Ledger: %s to %s') % (self.date_from, self.date_to),
            'type': 'ir.actions.act_window',
            'res_model': 'account.general.ledger.report',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'inline',
        }


class GeneralLedgerReportAccount(models.TransientModel):
    """General Ledger Account Section."""
    _name = 'account.general.ledger.report.account'
    _description = 'General Ledger Report Account'
    _order = 'name'
    
    report_id = fields.Many2one(
        comodel_name='account.general.ledger.report',
        string='Report',
        ondelete='cascade',
    )
    account_id = fields.Many2one('account.account', string='Account')
    name = fields.Char(string='Account Name')
    opening_balance = fields.Monetary(string='Opening Balance', currency_field='currency_id')
    total_debit = fields.Monetary(string='Total Debit', currency_field='currency_id')
    total_credit = fields.Monetary(string='Total Credit', currency_field='currency_id')
    closing_balance = fields.Monetary(string='Closing Balance', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', string='Currency')
    line_ids = fields.One2many(
        comodel_name='account.general.ledger.report.line',
        inverse_name='account_line_id',
        string='Transactions',
    )
    
    def action_drilldown(self):
        """Open account transactions."""
        self.ensure_one()
        return self.report_id.action_drilldown(
            account_id=self.account_id.id,
            date_from=self.report_id.date_from,
            date_to=self.report_id.date_to,
        )


class GeneralLedgerReportLine(models.TransientModel):
    """General Ledger Transaction Line."""
    _name = 'account.general.ledger.report.line'
    _description = 'General Ledger Report Transaction'
    _order = 'date, id'
    
    account_line_id = fields.Many2one(
        comodel_name='account.general.ledger.report.account',
        string='Account Line',
        ondelete='cascade',
    )
    move_line_id = fields.Many2one('account.move.line', string='Journal Item')
    date = fields.Date(string='Date')
    journal_id = fields.Many2one('account.journal', string='Journal')
    move_id = fields.Many2one('account.move', string='Journal Entry')
    ref = fields.Char(string='Reference')
    name = fields.Char(string='Description')
    partner_id = fields.Many2one('res.partner', string='Partner')
    debit = fields.Monetary(string='Debit', currency_field='currency_id')
    credit = fields.Monetary(string='Credit', currency_field='currency_id')
    balance = fields.Monetary(string='Running Balance', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', string='Currency')
    
    def action_open_move(self):
        """Open source journal entry."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.move_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
