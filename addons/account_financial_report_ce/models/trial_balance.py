# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Trial Balance Report Model

Implements FR-005: Trial Balance Report
User Story: As an Accountant, I want to generate a trial balance showing all
account balances with debit and credit totals so that I can verify that debits
equal credits and prepare for financial statement generation.

Acceptance Criteria:
- Scenario 1: Generate Trial Balance for specific date
- Scenario 2: Show all accounts with balances
- Scenario 3: Display debit and credit columns
- Scenario 4: Verify total debits equal total credits
- Scenario 5: Option for showing only accounts with activity
- Scenario 6: Comparative Trial Balance
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class TrialBalanceReport(models.TransientModel):
    """
    Trial Balance Report.

    Shows all account balances with debit and credit columns,
    verifying the fundamental rule that debits must equal credits.
    """
    _name = 'account.trial.balance.report'
    _description = 'Trial Balance Report'
    _inherit = 'account.financial.report.abstract'

    # -------------------------------------------------------------------------
    # TRIAL BALANCE SPECIFIC FIELDS
    # -------------------------------------------------------------------------

    date_to = fields.Date(
        string='As of Date',
        required=True,
        default=fields.Date.context_today,
        help="Generate Trial Balance as of this date.",
    )

    date_from = fields.Date(
        string='From Date',
        help="Optional start date to show only period activity.",
    )

    show_balance_zero = fields.Boolean(
        string='Show Zero Balances',
        default=False,
        help="Include accounts with zero balance.",
    )

    show_hierarchy = fields.Boolean(
        string='Show Account Groups',
        default=False,
        help="Display accounts grouped by account group/type.",
    )

    show_analytic = fields.Boolean(
        string='Include Analytic',
        default=False,
        help="Show analytic account breakdown.",
    )

    display_type = fields.Selection(
        selection=[
            ('balance', 'Balance Only'),
            ('debit_credit', 'Debit/Credit Columns'),
            ('both', 'Both'),
        ],
        string='Display Type',
        default='both',
        help="How to display account balances.",
    )

    # -------------------------------------------------------------------------
    # COMPUTED REPORT DATA
    # -------------------------------------------------------------------------

    line_ids = fields.One2many(
        comodel_name='account.trial.balance.report.line',
        inverse_name='report_id',
        string='Account Lines',
        compute='_compute_report_data',
    )

    total_debit = fields.Monetary(
        string='Total Debit',
        currency_field='currency_id',
        compute='_compute_report_data',
    )

    total_credit = fields.Monetary(
        string='Total Credit',
        currency_field='currency_id',
        compute='_compute_report_data',
    )

    is_balanced = fields.Boolean(
        string='Is Balanced',
        compute='_compute_report_data',
        help="True if total debits equal total credits.",
    )

    difference = fields.Monetary(
        string='Difference',
        currency_field='currency_id',
        compute='_compute_report_data',
        help="Difference between total debits and credits (should be 0).",
    )

    @api.depends('date_from', 'date_to', 'company_id', 'target_move',
                 'show_balance_zero', 'show_hierarchy', 'display_type',
                 'enable_comparison', 'comparison_date_to')
    def _compute_report_data(self):
        """
        Compute Trial Balance report data.

        For each account:
        1. Calculate total debit (all debit entries)
        2. Calculate total credit (all credit entries)
        3. Calculate balance (debit - credit)
        4. Sum totals and verify balance
        """
        for report in self:
            report.currency_id = report.company_id.currency_id

            # Get all accounts (Odoo 19.0: company_ids Many2many)
            accounts = self.env['account.account'].search([
                ('company_ids', 'in', report.company_id.ids),
            ], order='code')

            # Compute balances
            if report.date_from:
                # Period balance (activity during period)
                balances = report._compute_account_balance(
                    accounts,
                    date_from=report.date_from,
                    date_to=report.date_to,
                )
            else:
                # Cumulative balance to date
                balances = report._compute_account_balance(
                    accounts,
                    date_to=report.date_to,
                )

            # Generate lines
            lines = []
            Line = self.env['account.trial.balance.report.line']
            total_debit = 0.0
            total_credit = 0.0

            for account in accounts:
                bal = balances.get(account.id, {})
                debit = bal.get('debit', 0.0)
                credit = bal.get('credit', 0.0)
                balance = bal.get('balance', 0.0)

                # Skip zero balance if not showing them
                if not report.show_balance_zero and balance == 0 and debit == 0 and credit == 0:
                    continue

                # Debit balance vs Credit balance display
                debit_balance = balance if balance > 0 else 0.0
                credit_balance = -balance if balance < 0 else 0.0

                lines.append(Line.new({
                    'report_id': report.id,
                    'account_id': account.id,
                    'code': account.code,
                    'name': account.name,
                    'account_type': account.account_type,
                    'debit': debit,
                    'credit': credit,
                    'balance': balance,
                    'debit_balance': debit_balance,
                    'credit_balance': credit_balance,
                    'currency_id': report.currency_id.id,
                }))

                total_debit += debit_balance
                total_credit += credit_balance

            report.line_ids = lines
            report.total_debit = total_debit
            report.total_credit = total_credit
            report.difference = round(total_debit - total_credit, 2)
            report.is_balanced = report.difference == 0

    def action_generate_report(self):
        """Generate and display the Trial Balance report."""
        self.ensure_one()
        if not self.date_to:
            raise UserError(_("Please specify the As of Date."))

        self._compute_report_data()

        return {
            'name': _('Trial Balance as of %s') % self.date_to,
            'type': 'ir.actions.act_window',
            'res_model': 'account.trial.balance.report',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'inline',
        }


class TrialBalanceReportLine(models.TransientModel):
    """Trial Balance Report Line."""
    _name = 'account.trial.balance.report.line'
    _description = 'Trial Balance Report Line'
    _order = 'code'

    report_id = fields.Many2one(
        comodel_name='account.trial.balance.report',
        string='Report',
        ondelete='cascade',
    )
    account_id = fields.Many2one('account.account', string='Account')
    code = fields.Char(string='Code')
    name = fields.Char(string='Account Name')
    account_type = fields.Char(string='Type')

    # Actual debit/credit totals
    debit = fields.Monetary(string='Period Debit', currency_field='currency_id')
    credit = fields.Monetary(string='Period Credit', currency_field='currency_id')
    balance = fields.Monetary(string='Net Balance', currency_field='currency_id')

    # Debit/Credit balance columns (for trial balance format)
    debit_balance = fields.Monetary(string='Debit Balance', currency_field='currency_id')
    credit_balance = fields.Monetary(string='Credit Balance', currency_field='currency_id')

    # Comparison
    comparison_debit = fields.Monetary(string='Prior Debit', currency_field='currency_id')
    comparison_credit = fields.Monetary(string='Prior Credit', currency_field='currency_id')
    variance = fields.Monetary(string='Variance', currency_field='currency_id')

    currency_id = fields.Many2one('res.currency', string='Currency')

    def action_drilldown(self):
        """Drill down to account transactions."""
        self.ensure_one()
        return self.report_id.action_drilldown(
            account_id=self.account_id.id,
            date_from=self.report_id.date_from,
            date_to=self.report_id.date_to,
        )
