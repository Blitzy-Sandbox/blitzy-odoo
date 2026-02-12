# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Financial Report Base Model

This module provides the base abstract model for all financial reports
in the Enterprise Accounting suite. It defines common fields, methods,
and report generation logic shared across Balance Sheet, P&L, Cash Flow,
General Ledger, Trial Balance, and Aged Partner Balance reports.

Technical Discovery Notes (per FR-001 through FR-007):
- Integrates with account.move and account.move.line for transaction data
- Uses account.account for chart of accounts classification
- Supports multi-company and multi-currency operations
- Provides comparative period analysis capabilities
- Enables drill-down to source transactions

Constraints Enforced:
- AGPL-3.0 license (this file)
- No Enterprise module dependencies
- OCA coding standards compliance
"""

from odoo import _, api, fields, models


class FinancialReportAbstract(models.AbstractModel):
    """
    Abstract base model for financial reports.

    This model provides common functionality for all financial reports:
    - Report parameter management (date ranges, comparison periods)
    - Account aggregation and classification
    - Multi-currency support
    - Export capabilities (PDF, Excel)
    - Drill-down navigation to source documents

    Per EPIC-001 User Stories:
    - CFO can generate GAAP/IFRS compliant reports
    - Accountant can verify with drill-down to transactions
    - Auditor can validate data integrity
    """
    _name = 'account.financial.report.abstract'
    _description = 'Financial Report Abstract Base'

    # -------------------------------------------------------------------------
    # REPORT CONFIGURATION FIELDS
    # -------------------------------------------------------------------------

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        help="Company for which the report is generated.",
    )

    date_from = fields.Date(
        string='Start Date',
        help="Start date for the reporting period. "
             "For Balance Sheet, this is typically the fiscal year start.",
    )

    date_to = fields.Date(
        string='End Date',
        required=True,
        help="End date / As-of date for the report. "
             "Balance Sheet shows position as of this date.",
    )

    target_move = fields.Selection(
        selection=[
            ('posted', 'All Posted Entries'),
            ('all', 'All Entries'),
        ],
        string='Target Moves',
        required=True,
        default='posted',
        help="Select which journal entries to include in the report.",
    )

    # -------------------------------------------------------------------------
    # COMPARATIVE PERIOD FIELDS (per FR-001 Scenario 5)
    # -------------------------------------------------------------------------

    enable_comparison = fields.Boolean(
        string='Enable Comparison',
        default=False,
        help="Enable comparative period analysis.",
    )

    comparison_date_from = fields.Date(
        string='Comparison Start Date',
        help="Start date for the comparison period.",
    )

    comparison_date_to = fields.Date(
        string='Comparison End Date',
        help="End date for the comparison period.",
    )

    show_variance = fields.Boolean(
        string='Show Variance',
        default=True,
        help="Display variance columns (absolute and percentage).",
    )

    # -------------------------------------------------------------------------
    # DISPLAY OPTIONS
    # -------------------------------------------------------------------------

    hierarchy_level = fields.Selection(
        selection=[
            ('all', 'All Levels'),
            ('summary', 'Summary Only'),
            ('detail', 'Detail with Transactions'),
        ],
        string='Display Level',
        default='all',
        help="Level of detail to display in the report.",
    )

    hide_zero_balance = fields.Boolean(
        string='Hide Zero Balance',
        default=False,
        help="Hide accounts with zero balance from the report.",
    )

    # -------------------------------------------------------------------------
    # REPORT STATE
    # -------------------------------------------------------------------------

    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('done', 'Done'),
        ],
        string='State',
        default='draft',
        help="Current state of the report computation.",
    )

    # -------------------------------------------------------------------------
    # CURRENCY FIELDS
    # -------------------------------------------------------------------------

    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency',
        help="Currency for report display. "
             "Defaults to company currency if not specified.",
    )

    # -------------------------------------------------------------------------
    # COMMON METHODS
    # -------------------------------------------------------------------------

    @api.model
    def _get_account_domain(self, account_types=None):
        """
        Build domain for filtering accounts.

        Args:
            account_types: List of account type codes to filter.
                          If None, returns all accounts.

        Returns:
            Domain list for account.account search.

        Technical Note:
            In Odoo 19.0, account.account uses company_ids (Many2many)
            instead of company_id.
        """
        domain = [('company_ids', 'in', self.company_id.ids)]
        if account_types:
            domain.append(('account_type', 'in', account_types))
        return domain

    @api.model
    def _get_move_line_domain(self, date_from=None, date_to=None, account_ids=None):
        """
        Build domain for filtering journal items (account.move.line).

        Args:
            date_from: Start date for filtering (inclusive)
            date_to: End date for filtering (inclusive)
            account_ids: List of account IDs to include

        Returns:
            Domain list for account.move.line search.

        Constraints:
            - Respects target_move selection (posted/all)
            - Filters by company_id
            - Supports multi-currency via amount_currency
        """
        domain = [
            ('company_id', '=', self.company_id.id),
        ]

        # Filter by move state
        if self.target_move == 'posted':
            domain.append(('parent_state', '=', 'posted'))

        # Date filters
        if date_from:
            domain.append(('date', '>=', date_from))
        if date_to:
            domain.append(('date', '<=', date_to))

        # Account filter
        if account_ids:
            domain.append(('account_id', 'in', account_ids))

        return domain

    def _compute_account_balance(self, accounts, date_from=None, date_to=None):
        """
        Compute balance for a set of accounts.

        This method aggregates debit, credit, and balance for the specified
        accounts within the given date range.

        Args:
            accounts: Recordset of account.account records
            date_from: Start date (optional, for P&L type accounts)
            date_to: End date (required for balance computation)

        Returns:
            Dict mapping account_id to balance dict:
            {
                account_id: {
                    'debit': total_debit,
                    'credit': total_credit,
                    'balance': total_balance,
                }
            }

        Implementation Note:
            Balance Sheet accounts (Assets, Liabilities, Equity) use
            cumulative balance from inception to date_to.

            P&L accounts (Income, Expense) use period balance
            from date_from to date_to.
        """
        result = {}
        if not accounts:
            return result

        domain = self._get_move_line_domain(
            date_from=date_from,
            date_to=date_to,
            account_ids=accounts.ids,
        )

        # Use read_group for efficient aggregation
        move_lines = self.env['account.move.line'].read_group(
            domain=domain,
            fields=['account_id', 'debit:sum', 'credit:sum', 'balance:sum'],
            groupby=['account_id'],
        )

        for line in move_lines:
            account_id = line['account_id'][0]
            result[account_id] = {
                'debit': line['debit'] or 0.0,
                'credit': line['credit'] or 0.0,
                'balance': line['balance'] or 0.0,
            }

        # Ensure all accounts are in result (even with zero balance)
        for account in accounts:
            if account.id not in result:
                result[account.id] = {
                    'debit': 0.0,
                    'credit': 0.0,
                    'balance': 0.0,
                }

        return result

    def _compute_variance(self, current_value, comparison_value):
        """
        Compute variance between current and comparison period values.

        Args:
            current_value: Value for current period
            comparison_value: Value for comparison period

        Returns:
            Dict with variance analysis:
            {
                'absolute': current_value - comparison_value,
                'percentage': percentage change (0 if comparison is 0),
            }

        Per FR-001 Scenario 5:
            "Variance columns showing absolute difference and percentage change"
        """
        absolute = current_value - comparison_value

        if comparison_value:
            percentage = (absolute / abs(comparison_value)) * 100
        else:
            percentage = 0.0 if current_value == 0 else 100.0

        return {
            'absolute': absolute,
            'percentage': round(percentage, 2),
        }

    def _validate_accounting_equation(self, assets, liabilities, equity):
        """
        Validate the fundamental accounting equation: Assets = Liabilities + Equity

        Per FR-001 Scenario 6:
            "total assets equals total liabilities plus total equity,
             confirming the fundamental accounting equation (A = L + E)"

        Args:
            assets: Total assets amount
            liabilities: Total liabilities amount
            equity: Total equity amount

        Returns:
            Dict with validation results:
            {
                'is_balanced': bool,
                'difference': amount (should be 0 if balanced),
            }
        """
        expected_total = liabilities + equity
        difference = round(assets - expected_total, 2)

        return {
            'is_balanced': difference == 0,
            'difference': difference,
        }

    # -------------------------------------------------------------------------
    # EXPORT METHODS (per FR-007)
    # -------------------------------------------------------------------------

    def action_print_pdf(self):
        """
        Export report to PDF format.

        Per FR-007 Acceptance Criteria:
            "Given I am viewing a financial report
             When I select Export to PDF
             Then I receive a PDF document with proper formatting"

        Returns an ir.actions.report action dict that triggers QWeb PDF rendering.
        Subclasses can override to specify their own report template.
        """
        self.ensure_one()
        # Map model to report XML ID
        report_map = {
            'account.balance.sheet.report': 'account_financial_report_ce.action_report_balance_sheet',
            'account.profit.loss.report': 'account_financial_report_ce.action_report_profit_loss',
            'account.cash.flow.report': 'account_financial_report_ce.action_report_cash_flow',
            'account.general.ledger.report': 'account_financial_report_ce.action_report_general_ledger',
            'account.trial.balance.report': 'account_financial_report_ce.action_report_trial_balance',
            'account.aged.partner.balance.report': 'account_financial_report_ce.action_report_aged_partner_balance',
        }
        report_xml_id = report_map.get(self._name)
        if report_xml_id:
            report_action = self.env.ref(report_xml_id)
            # Use config=False to return ir.actions.report directly
            # instead of the layout configurator ir.actions.act_window
            return report_action.report_action(self, config=False)
        return {
            'type': 'ir.actions.report',
            'report_name': 'account_financial_report_ce.report_generic',
            'report_type': 'qweb-pdf',
            'data': {'report_id': self.id},
        }

    def action_export_xlsx(self):
        """
        Export report to Excel format.

        Per FR-007 Acceptance Criteria:
            "Given I am viewing a financial report
             When I select Export to Excel
             Then I receive an XLSX file with data in tabular format"

        Returns an ir.actions.report action dict for Excel export.
        The actual XLSX generation is handled programmatically.
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.report',
            'report_name': f'account_financial_report_ce.{self._name.replace(".", "_")}_xlsx',
            'report_type': 'qweb-pdf',
            'data': {'report_id': self.id, 'output_format': 'xlsx'},
        }

    # -------------------------------------------------------------------------
    # DRILL-DOWN METHODS (per FR-007)
    # -------------------------------------------------------------------------

    def action_drilldown(self, account_id, date_from=None, date_to=None):
        """
        Navigate to source transactions for a report line.

        Per FR-007 Acceptance Criteria:
            "Given I am viewing a financial report
             When I click on a line item amount
             Then I am navigated to a filtered view of the underlying
             journal entries that comprise that amount"

        Args:
            account_id: ID of the account to drill into
            date_from: Start date filter
            date_to: End date filter

        Returns:
            Action dict to open journal items view with appropriate filters
        """
        domain = self._get_move_line_domain(
            date_from=date_from,
            date_to=date_to,
            account_ids=[account_id],
        )

        return {
            'name': _('Journal Items'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move.line',
            'view_mode': 'list,form',
            'domain': domain,
            'context': {
                'search_default_posted': self.target_move == 'posted',
            },
        }

    # -------------------------------------------------------------------------
    # COMPUTATION ACTION
    # -------------------------------------------------------------------------

    def action_compute(self):
        """
        Compute report data and transition state to 'done'.

        This is the primary entry point for report generation. Delegates
        to _compute_report_data() which must be implemented by concrete
        subclasses.

        Returns:
            True to keep the wizard open with computed data.
        """
        self.ensure_one()
        self._compute_report_data()
        self.write({'state': 'done'})
        return True


class FinancialReportLine(models.AbstractModel):
    """
    Abstract model for financial report line items.

    This model represents a single line in a financial report,
    with support for hierarchical display and account aggregation.
    """
    _name = 'account.financial.report.line.abstract'
    _description = 'Financial Report Line Abstract'
    _order = 'sequence, id'

    sequence = fields.Integer(
        string='Sequence',
        default=10,
        help="Display order for the report line.",
    )

    name = fields.Char(
        string='Label',
        required=True,
        help="Display label for the report line.",
    )

    level = fields.Integer(
        string='Level',
        default=0,
        help="Hierarchy level (0 = root, higher = nested).",
    )

    parent_id = fields.Many2one(
        comodel_name='account.financial.report.line.abstract',
        string='Parent Line',
        help="Parent line for hierarchical reports.",
    )

    amount = fields.Monetary(
        string='Amount',
        currency_field='currency_id',
        help="Computed amount for this report line.",
    )

    comparison_amount = fields.Monetary(
        string='Comparison Amount',
        currency_field='currency_id',
        help="Amount for comparison period.",
    )

    variance_absolute = fields.Monetary(
        string='Variance',
        currency_field='currency_id',
        help="Absolute variance (current - comparison).",
    )

    variance_percentage = fields.Float(
        string='Variance %',
        help="Percentage variance.",
    )

    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency',
    )

    account_ids = fields.Many2many(
        comodel_name='account.account',
        string='Accounts',
        help="Accounts included in this report line.",
    )

    is_total = fields.Boolean(
        string='Is Total Line',
        default=False,
        help="Indicates this is a total/subtotal line.",
    )
