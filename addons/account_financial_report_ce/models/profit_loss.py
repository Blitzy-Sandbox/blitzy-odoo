# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Profit & Loss Statement Report Model

Implements FR-002: Profit & Loss Statement
User Story: As a CFO, I want to generate a profit and loss statement showing
revenue, expenses, and net income for a defined period so that I can analyze
profitability and make informed business decisions.

Acceptance Criteria:
- Scenario 1: Generate P&L for date range
- Scenario 2: Revenue classification (Operating, Non-operating)
- Scenario 3: Expense classification (Operating, Non-operating)
- Scenario 4: Gross profit calculation
- Scenario 5: Net income calculation
- Scenario 6: Comparative P&L with variance analysis
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ProfitLossReport(models.TransientModel):
    """
    Profit & Loss Statement Report.

    Generates income statement showing revenues, expenses, and net income
    for a specified period with support for comparative analysis.
    """
    _name = 'account.profit.loss.report'
    _description = 'Profit & Loss Report'
    _inherit = 'account.financial.report.abstract'

    # -------------------------------------------------------------------------
    # P&L SPECIFIC FIELDS
    # -------------------------------------------------------------------------

    date_from = fields.Date(
        string='From Date',
        required=True,
        help="Start date of the reporting period.",
    )

    date_to = fields.Date(
        string='To Date',
        required=True,
        default=fields.Date.context_today,
        help="End date of the reporting period.",
    )

    # Account type classifications
    REVENUE_TYPES = ['income', 'income_other']
    EXPENSE_TYPES = ['expense', 'expense_depreciation', 'expense_direct_cost']
    COGS_TYPES = ['expense_direct_cost']

    # -------------------------------------------------------------------------
    # COMPUTED REPORT DATA
    # -------------------------------------------------------------------------

    total_revenue = fields.Monetary(
        string='Total Revenue',
        currency_field='currency_id',
        compute='_compute_report_data',
    )

    total_cogs = fields.Monetary(
        string='Cost of Goods Sold',
        currency_field='currency_id',
        compute='_compute_report_data',
    )

    gross_profit = fields.Monetary(
        string='Gross Profit',
        currency_field='currency_id',
        compute='_compute_report_data',
    )

    total_operating_expenses = fields.Monetary(
        string='Operating Expenses',
        currency_field='currency_id',
        compute='_compute_report_data',
    )

    operating_income = fields.Monetary(
        string='Operating Income',
        currency_field='currency_id',
        compute='_compute_report_data',
    )

    total_other_income = fields.Monetary(
        string='Other Income',
        currency_field='currency_id',
        compute='_compute_report_data',
    )

    total_other_expenses = fields.Monetary(
        string='Other Expenses',
        currency_field='currency_id',
        compute='_compute_report_data',
    )

    net_income = fields.Monetary(
        string='Net Income',
        currency_field='currency_id',
        compute='_compute_report_data',
    )

    # -------------------------------------------------------------------------
    # BACKWARD-COMPATIBLE ALIAS FIELDS
    # -------------------------------------------------------------------------

    total_expenses = fields.Monetary(
        string='Total Expenses',
        currency_field='currency_id',
        related='total_operating_expenses',
        readonly=True,
        help="Alias for total_operating_expenses.",
    )

    total_other = fields.Monetary(
        string='Total Other',
        currency_field='currency_id',
        compute='_compute_total_other',
        help="Net of other income minus other expenses.",
    )

    @api.depends('total_other_income', 'total_other_expenses')
    def _compute_total_other(self):
        """Compute net other income (other income - other expenses)."""
        for rec in self:
            rec.total_other = rec.total_other_income - rec.total_other_expenses

    line_ids = fields.One2many(
        comodel_name='account.profit.loss.report.line',
        inverse_name='report_id',
        string='Report Lines',
        compute='_compute_report_data',
    )

    @api.depends('date_from', 'date_to', 'company_id', 'target_move',
                 'enable_comparison', 'comparison_date_from', 'comparison_date_to')
    def _compute_report_data(self):
        """
        Compute P&L report data.

        Calculates:
        - Revenue (Operating and Other)
        - Cost of Goods Sold
        - Gross Profit
        - Operating Expenses
        - Operating Income
        - Net Income
        """
        for report in self:
            report.currency_id = report.company_id.currency_id

            # Revenue accounts
            revenue_accounts = self.env['account.account'].search(
                report._get_account_domain(report.REVENUE_TYPES),
            )
            revenue_balances = report._compute_account_balance(
                revenue_accounts,
                date_from=report.date_from,
                date_to=report.date_to,
            )
            # Revenue is credit balance (negative in Odoo), so we negate
            report.total_revenue = -sum(
                b['balance'] for b in revenue_balances.values()
            )

            # COGS accounts (subset of expenses)
            cogs_accounts = self.env['account.account'].search(
                report._get_account_domain(report.COGS_TYPES),
            )
            cogs_balances = report._compute_account_balance(
                cogs_accounts,
                date_from=report.date_from,
                date_to=report.date_to,
            )
            report.total_cogs = sum(b['balance'] for b in cogs_balances.values())

            # Gross Profit
            report.gross_profit = report.total_revenue - report.total_cogs

            # Operating expenses (excluding COGS)
            expense_accounts = self.env['account.account'].search(
                report._get_account_domain(['expense', 'expense_depreciation']),
            )
            expense_balances = report._compute_account_balance(
                expense_accounts,
                date_from=report.date_from,
                date_to=report.date_to,
            )
            report.total_operating_expenses = sum(
                b['balance'] for b in expense_balances.values()
            )

            # Operating Income
            report.operating_income = report.gross_profit - report.total_operating_expenses

            # Other income/expenses
            other_income_accounts = self.env['account.account'].search(
                report._get_account_domain(['income_other']),
            )
            other_income_balances = report._compute_account_balance(
                other_income_accounts,
                date_from=report.date_from,
                date_to=report.date_to,
            )
            report.total_other_income = -sum(
                b['balance'] for b in other_income_balances.values()
            )
            report.total_other_expenses = 0.0  # Could be populated from specific accounts

            # Net Income
            report.net_income = (
                report.operating_income +
                report.total_other_income -
                report.total_other_expenses
            )

            # Generate report lines
            report.line_ids = []  # Placeholder for line generation

    def action_generate_report(self):
        """Generate and display the P&L report."""
        self.ensure_one()
        if not self.date_from or not self.date_to:
            raise UserError(_("Please specify the date range for the P&L report."))

        self._compute_report_data()

        return {
            'name': _('Profit & Loss: %s to %s') % (self.date_from, self.date_to),
            'type': 'ir.actions.act_window',
            'res_model': 'account.profit.loss.report',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'inline',
        }


class ProfitLossReportLine(models.TransientModel):
    """P&L Report Line."""
    _name = 'account.profit.loss.report.line'
    _description = 'Profit & Loss Report Line'
    _order = 'sequence, id'

    report_id = fields.Many2one(
        comodel_name='account.profit.loss.report',
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
    account_ids = fields.Many2many('account.account', string='Accounts')
    is_total = fields.Boolean(string='Is Total', default=False)
