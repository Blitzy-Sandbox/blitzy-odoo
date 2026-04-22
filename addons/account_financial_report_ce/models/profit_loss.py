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
from odoo.fields import Command


class ProfitLossReport(models.TransientModel):
    """
    Profit & Loss Statement Report.

    Generates an income statement showing revenues, expenses, and net income
    for a specified period with support for comparative analysis and
    drill-down to source transactions.

    The P&L statement follows GAAP/IFRS presentation format:
      - Revenue (Operating)
      - Cost of Goods Sold
      - Gross Profit
      - Operating Expenses (with depreciation breakdown)
      - Operating Income
      - Other Income / Expenses (Non-operating)
      - Net Income

    Per FR-002 Acceptance Criteria:
      - Revenue and expenses classified into operating and non-operating
      - Gross profit calculation (Revenue - COGS)
      - Operating income derived from gross profit minus operating expenses
      - Comparative analysis with absolute and percentage variance
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

    # -------------------------------------------------------------------------
    # ACCOUNT TYPE CLASSIFICATIONS
    # -------------------------------------------------------------------------
    # Revenue and income types are separated to prevent double-counting:
    # - 'income' = core operating revenue (e.g. product sales, service fees)
    # - 'income_other' = non-operating / miscellaneous income
    # Previously REVENUE_TYPES included both, causing income_other to appear
    # in both total_revenue AND total_other_income.  This is now corrected.
    # -------------------------------------------------------------------------

    # Operating revenue: core business income only
    OPERATING_REVENUE_TYPES = ['income']
    # Non-operating income: miscellaneous / other income sources
    OTHER_INCOME_TYPES = ['income_other']
    # Backward-compatible alias — now only includes operating revenue
    REVENUE_TYPES = ['income']
    # All expense account types (for cross-reference)
    EXPENSE_TYPES = ['expense', 'expense_depreciation', 'expense_direct_cost']
    # Cost of goods sold: direct costs
    COGS_TYPES = ['expense_direct_cost']
    # General operating expenses (excluding COGS and depreciation)
    GENERAL_EXPENSE_TYPES = ['expense']
    # Depreciation and amortization expenses
    DEPRECIATION_TYPES = ['expense_depreciation']

    # -------------------------------------------------------------------------
    # COMPUTED REPORT DATA
    # -------------------------------------------------------------------------

    total_revenue = fields.Monetary(
        string='Total Revenue',
        currency_field='currency_id',
        help="Total operating revenue (income account type only).",
    )

    total_cogs = fields.Monetary(
        string='Cost of Goods Sold',
        currency_field='currency_id',
        help="Total direct costs (expense_direct_cost account type).",
    )

    gross_profit = fields.Monetary(
        string='Gross Profit',
        currency_field='currency_id',
        help="Revenue minus Cost of Goods Sold.",
    )

    total_general_expenses = fields.Monetary(
        string='General & Administrative Expenses',
        currency_field='currency_id',
        help="General operating expenses excluding COGS and depreciation.",
    )

    total_depreciation = fields.Monetary(
        string='Depreciation & Amortization',
        currency_field='currency_id',
        help="Depreciation and amortization expenses "
             "(expense_depreciation account type).",
    )

    total_operating_expenses = fields.Monetary(
        string='Operating Expenses',
        currency_field='currency_id',
        help="Sum of general expenses and depreciation (excludes COGS).",
    )

    operating_income = fields.Monetary(
        string='Operating Income',
        currency_field='currency_id',
        help="Gross Profit minus total Operating Expenses.",
    )

    total_other_income = fields.Monetary(
        string='Other Income',
        currency_field='currency_id',
        help="Non-operating income (income_other account type).",
    )

    total_other_expenses = fields.Monetary(
        string='Other Expenses',
        currency_field='currency_id',
        help="Non-operating expenses.  Odoo's standard chart of accounts "
             "does not define a dedicated non-operating expense type; this "
             "field is reserved for custom account type extensions.",
    )

    net_income = fields.Monetary(
        string='Net Income',
        currency_field='currency_id',
        help="Final bottom line: Operating Income + Other Income "
             "- Other Expenses.",
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
        """Compute net other income (other income minus other expenses)."""
        for rec in self:
            rec.total_other = rec.total_other_income - rec.total_other_expenses

    line_ids = fields.One2many(
        comodel_name='account.profit.loss.report.line',
        inverse_name='report_id',
        string='Report Lines',
    )

    # -------------------------------------------------------------------------
    # CORE COMPUTATION METHODS
    # -------------------------------------------------------------------------

    def _compute_report_data(self):
        """
        Compute all Profit & Loss report data.

        Performs the complete P&L computation pipeline:

        1. Operating Revenue aggregation ('income' accounts only)
        2. COGS computation ('expense_direct_cost' accounts)
        3. Gross Profit derivation (Revenue - COGS)
        4. Operating Expenses with depreciation breakdown
        5. Operating Income (Gross Profit - Operating Expenses)
        6. Non-operating Other Income ('income_other' accounts)
        7. Non-operating Other Expenses (reserved for custom types)
        8. Net Income final calculation
        9. Comparative period analysis (when enabled)
        10. Hierarchical report line generation

        All balance computations delegate to the base-class method
        ``_compute_account_balance`` which uses ``read_group`` for
        SQL-level aggregation, meeting the <30-second performance
        target for 100 000 transactions.

        Per FR-002 Acceptance Criteria:
          - Scenario 1: Complete P&L for date range
          - Scenario 4: Gross profit = Revenue - COGS
          - Scenario 5: Net income fully computed
          - Scenario 6: Comparative period with variance
        """
        for report in self:
            report.currency_id = report.company_id.currency_id

            # =================================================================
            # 1. OPERATING REVENUE (Scenario 2: Operating revenue)
            # Only 'income' type accounts — 'income_other' is classified
            # separately as non-operating to prevent double-counting.
            # =================================================================
            revenue_accounts = self.env['account.account'].search(
                report._get_account_domain(report.OPERATING_REVENUE_TYPES),
            )
            revenue_balances = report._compute_account_balance(
                revenue_accounts,
                date_from=report.date_from,
                date_to=report.date_to,
            )
            # Revenue has credit balance (negative in Odoo), so negate
            report.total_revenue = -sum(
                b['balance'] for b in revenue_balances.values()
            )

            # =================================================================
            # 2. COST OF GOODS SOLD ('expense_direct_cost')
            # =================================================================
            cogs_accounts = self.env['account.account'].search(
                report._get_account_domain(report.COGS_TYPES),
            )
            cogs_balances = report._compute_account_balance(
                cogs_accounts,
                date_from=report.date_from,
                date_to=report.date_to,
            )
            report.total_cogs = sum(
                b['balance'] for b in cogs_balances.values()
            )

            # =================================================================
            # 3. GROSS PROFIT (Scenario 4)
            # =================================================================
            report.gross_profit = report.total_revenue - report.total_cogs

            # =================================================================
            # 4. OPERATING EXPENSES with depreciation breakdown (Scenario 3)
            # Split into General & Administrative and Depreciation for proper
            # subtotal hierarchy in the report lines.
            # =================================================================

            # 4a. General & Administrative ('expense' type, excluding COGS)
            general_expense_accounts = self.env['account.account'].search(
                report._get_account_domain(report.GENERAL_EXPENSE_TYPES),
            )
            general_expense_balances = report._compute_account_balance(
                general_expense_accounts,
                date_from=report.date_from,
                date_to=report.date_to,
            )
            report.total_general_expenses = sum(
                b['balance'] for b in general_expense_balances.values()
            )

            # 4b. Depreciation & Amortization ('expense_depreciation')
            depreciation_accounts = self.env['account.account'].search(
                report._get_account_domain(report.DEPRECIATION_TYPES),
            )
            depreciation_balances = report._compute_account_balance(
                depreciation_accounts,
                date_from=report.date_from,
                date_to=report.date_to,
            )
            report.total_depreciation = sum(
                b['balance'] for b in depreciation_balances.values()
            )

            # 4c. Total Operating Expenses = General + Depreciation
            report.total_operating_expenses = (
                report.total_general_expenses + report.total_depreciation
            )

            # =================================================================
            # 5. OPERATING INCOME
            # =================================================================
            report.operating_income = (
                report.gross_profit - report.total_operating_expenses
            )

            # =================================================================
            # 6. OTHER INCOME — non-operating ('income_other')
            # =================================================================
            other_income_accounts = self.env['account.account'].search(
                report._get_account_domain(report.OTHER_INCOME_TYPES),
            )
            other_income_balances = report._compute_account_balance(
                other_income_accounts,
                date_from=report.date_from,
                date_to=report.date_to,
            )
            report.total_other_income = -sum(
                b['balance'] for b in other_income_balances.values()
            )

            # =================================================================
            # 7. OTHER EXPENSES — non-operating
            # Odoo's standard chart of accounts does not include a dedicated
            # non-operating expense account type.  This field remains 0.0
            # under the default chart; it is reserved for custom extensions
            # where businesses define non-operating expense accounts.
            # =================================================================
            report.total_other_expenses = 0.0

            # =================================================================
            # 8. NET INCOME (Scenario 5)
            # =================================================================
            report.net_income = (
                report.operating_income
                + report.total_other_income
                - report.total_other_expenses
            )

            # =================================================================
            # 9. COMPARATIVE PERIOD (Scenario 6)
            # =================================================================
            comparison_data = {}
            if (report.enable_comparison
                    and report.comparison_date_from
                    and report.comparison_date_to):
                comparison_data = report._compute_comparison_data()

            # =================================================================
            # 10. GENERATE REPORT LINES
            # =================================================================
            report.line_ids = report._generate_report_lines(
                revenue_accounts=revenue_accounts,
                revenue_balances=revenue_balances,
                cogs_accounts=cogs_accounts,
                cogs_balances=cogs_balances,
                general_expense_accounts=general_expense_accounts,
                general_expense_balances=general_expense_balances,
                depreciation_accounts=depreciation_accounts,
                depreciation_balances=depreciation_balances,
                other_income_accounts=other_income_accounts,
                other_income_balances=other_income_balances,
                comparison_data=comparison_data,
            )

    # -------------------------------------------------------------------------
    # COMPARATIVE PERIOD COMPUTATION
    # -------------------------------------------------------------------------

    def _compute_comparison_data(self):
        """
        Compute P&L metrics for the comparison period.

        Mirrors the primary ``_compute_report_data`` logic but uses the
        comparison date range (``comparison_date_from`` to
        ``comparison_date_to``).  Returns a dictionary of comparison
        totals and per-account balances for line-level variance.

        Returns:
            dict: Comparison data with keys:
                - ``total_revenue``, ``total_cogs``, ``gross_profit``
                - ``total_general_expenses``, ``total_depreciation``,
                  ``total_operating_expenses``
                - ``operating_income``, ``total_other_income``,
                  ``total_other_expenses``, ``net_income``
                - ``revenue_balances``, ``cogs_balances``,
                  ``general_expense_balances``, ``depreciation_balances``,
                  ``other_income_balances`` (per-account dicts)

        Per FR-002 Scenario 6:
            "Comparative P&L with variance analysis"
        """
        self.ensure_one()
        comp = {}
        comp_from = self.comparison_date_from
        comp_to = self.comparison_date_to

        # Operating Revenue
        revenue_accounts = self.env['account.account'].search(
            self._get_account_domain(self.OPERATING_REVENUE_TYPES),
        )
        rev_bal = self._compute_account_balance(
            revenue_accounts, date_from=comp_from, date_to=comp_to,
        )
        comp['total_revenue'] = -sum(
            b['balance'] for b in rev_bal.values()
        )
        comp['revenue_balances'] = rev_bal

        # COGS
        cogs_accounts = self.env['account.account'].search(
            self._get_account_domain(self.COGS_TYPES),
        )
        cogs_bal = self._compute_account_balance(
            cogs_accounts, date_from=comp_from, date_to=comp_to,
        )
        comp['total_cogs'] = sum(
            b['balance'] for b in cogs_bal.values()
        )
        comp['cogs_balances'] = cogs_bal

        # Gross Profit
        comp['gross_profit'] = comp['total_revenue'] - comp['total_cogs']

        # General & Administrative expenses
        general_accounts = self.env['account.account'].search(
            self._get_account_domain(self.GENERAL_EXPENSE_TYPES),
        )
        gen_bal = self._compute_account_balance(
            general_accounts, date_from=comp_from, date_to=comp_to,
        )
        comp['total_general_expenses'] = sum(
            b['balance'] for b in gen_bal.values()
        )
        comp['general_expense_balances'] = gen_bal

        # Depreciation & Amortization
        depr_accounts = self.env['account.account'].search(
            self._get_account_domain(self.DEPRECIATION_TYPES),
        )
        depr_bal = self._compute_account_balance(
            depr_accounts, date_from=comp_from, date_to=comp_to,
        )
        comp['total_depreciation'] = sum(
            b['balance'] for b in depr_bal.values()
        )
        comp['depreciation_balances'] = depr_bal

        # Total Operating Expenses
        comp['total_operating_expenses'] = (
            comp['total_general_expenses'] + comp['total_depreciation']
        )

        # Operating Income
        comp['operating_income'] = (
            comp['gross_profit'] - comp['total_operating_expenses']
        )

        # Other Income (income_other)
        other_accounts = self.env['account.account'].search(
            self._get_account_domain(self.OTHER_INCOME_TYPES),
        )
        other_bal = self._compute_account_balance(
            other_accounts, date_from=comp_from, date_to=comp_to,
        )
        comp['total_other_income'] = -sum(
            b['balance'] for b in other_bal.values()
        )
        comp['other_income_balances'] = other_bal

        # Other Expenses (no standard Odoo type; reserved for extensions)
        comp['total_other_expenses'] = 0.0

        # Net Income
        comp['net_income'] = (
            comp['operating_income']
            + comp['total_other_income']
            - comp['total_other_expenses']
        )

        return comp

    # -------------------------------------------------------------------------
    # REPORT LINE GENERATION
    # -------------------------------------------------------------------------

    def _generate_report_lines(
        self,
        revenue_accounts,
        revenue_balances,
        cogs_accounts,
        cogs_balances,
        general_expense_accounts,
        general_expense_balances,
        depreciation_accounts,
        depreciation_balances,
        other_income_accounts,
        other_income_balances,
        comparison_data=None,
    ):
        """
        Generate hierarchical P&L report lines.

        Creates a structured income-statement following GAAP/IFRS
        presentation::

            REVENUE
              [Account detail lines]
            COST OF GOODS SOLD
              [Account detail lines]
            GROSS PROFIT
            OPERATING EXPENSES
              General & Administrative
                [Account detail lines]
              Depreciation & Amortization
                [Account detail lines]
            OPERATING INCOME
            OTHER INCOME
              [Account detail lines]
            OTHER EXPENSES
            NET OTHER INCOME / EXPENSES
            NET INCOME

        When ``comparison_data`` is provided, each line includes
        ``comparison_amount``, ``variance_absolute``, and
        ``variance_percentage`` columns.

        Args:
            revenue_accounts: Recordset of operating revenue accounts.
            revenue_balances: Per-account balance dict for revenue.
            cogs_accounts: Recordset of COGS accounts.
            cogs_balances: Per-account balance dict for COGS.
            general_expense_accounts: Recordset of general expense accounts.
            general_expense_balances: Per-account balance dict.
            depreciation_accounts: Recordset of depreciation accounts.
            depreciation_balances: Per-account balance dict.
            other_income_accounts: Recordset of other-income accounts.
            other_income_balances: Per-account balance dict.
            comparison_data: Optional dict from ``_compute_comparison_data``.

        Returns:
            list: ``fields.Command`` operations for the ``line_ids`` field.
        """
        self.ensure_one()
        line_commands = [Command.clear()]
        seq = [0]  # mutable counter shared by nested helpers
        comp = comparison_data or {}
        has_comparison = bool(comp) and self.enable_comparison

        # -- helper: build value dict for a single line ----------------------
        def _line_vals(name, amount, level=0, is_total=False,
                       account_ids=None, comp_amount=None,
                       is_group=False, account_id=None,
                       account_code='', account_name='',
                       section=None):
            """Return a dict of column values for one report line.

            Args:
                name: Display label for the line.
                amount: Monetary amount for the line.
                level: Indentation level (0=section, 1=subsection, 2=detail).
                is_total: Whether this line is a total / summary row.
                account_ids: List of account record IDs for drill-down.
                comp_amount: Comparison period amount (or None).
                is_group: True for section / sub-section headers.
                account_id: Single account record ID for template drill-down.
                account_code: Account code string for template display.
                account_name: Account name string for template display.
                section: P&L section identifier ('revenue', 'cogs',
                    'expense', 'other') for QWeb template filtering.
            """
            vals = {
                'sequence': seq[0],
                'name': name,
                'level': level,
                'amount': amount,
                'is_total': is_total,
                'is_group': is_group,
                'currency_id': self.currency_id.id,
            }
            if section:
                vals['section'] = section
            if account_id:
                vals['account_id'] = account_id
            if account_code:
                vals['account_code'] = account_code
            if account_name:
                vals['account_name'] = account_name
            if account_ids:
                vals['account_ids'] = [(6, 0, account_ids)]
            if has_comparison and comp_amount is not None:
                variance = self._compute_variance(amount, comp_amount)
                vals['comparison_amount'] = comp_amount
                vals['variance_absolute'] = variance['absolute']
                vals['variance_percentage'] = variance['percentage']
            return vals

        # -- helper: add per-account detail lines for a section --------------
        def _account_lines(accounts, balances, level, sign=1,
                           comp_balances=None, section=None):
            """Append account-level detail lines to *line_commands*.

            Args:
                accounts: Recordset of account.account records.
                balances: Per-account balance dict from
                    ``_compute_account_balance``.
                level: Indentation level for these detail lines.
                sign: Multiplier for balance sign normalisation
                    (-1 for credit-normal accounts like revenue).
                comp_balances: Optional comparison-period balance dict.
                section: P&L section identifier for QWeb filtering.
            """
            for account in accounts.sorted(key=lambda a: a.code):
                bal = balances.get(account.id, {})
                amount = bal.get('balance', 0.0) * sign
                if self.hide_zero_balance and not amount:
                    continue
                seq[0] += 1
                comp_amt = None
                if comp_balances:
                    cb = comp_balances.get(account.id, {})
                    comp_amt = cb.get('balance', 0.0) * sign
                line_commands.append(Command.create(_line_vals(
                    name='%s - %s' % (account.code, account.name),
                    amount=amount,
                    level=level,
                    account_ids=[account.id],
                    comp_amount=comp_amt,
                    is_group=False,
                    account_id=account.id,
                    account_code=account.code,
                    account_name=account.name,
                    section=section,
                )))

        # =================================================================
        # REVENUE SECTION
        # The template creates its own static "REVENUE" section header,
        # so the section-level header line is intentionally left without
        # a ``section`` value.  Only account detail lines receive
        # ``section='revenue'`` for the template's filter.
        # =================================================================
        seq[0] = 100
        line_commands.append(Command.create(_line_vals(
            _('REVENUE'),
            self.total_revenue,
            level=0,
            is_total=True,
            is_group=True,
            comp_amount=comp.get('total_revenue'),
        )))
        _account_lines(
            revenue_accounts, revenue_balances,
            level=1, sign=-1,
            comp_balances=comp.get('revenue_balances'),
            section='revenue',
        )

        # =================================================================
        # COST OF GOODS SOLD SECTION
        # =================================================================
        seq[0] = 200
        line_commands.append(Command.create(_line_vals(
            _('COST OF GOODS SOLD'),
            self.total_cogs,
            level=0,
            is_total=True,
            is_group=True,
            comp_amount=comp.get('total_cogs'),
        )))
        _account_lines(
            cogs_accounts, cogs_balances,
            level=1, sign=1,
            comp_balances=comp.get('cogs_balances'),
            section='cogs',
        )

        # =================================================================
        # GROSS PROFIT
        # =================================================================
        seq[0] = 300
        line_commands.append(Command.create(_line_vals(
            _('GROSS PROFIT'),
            self.gross_profit,
            level=0,
            is_total=True,
            is_group=True,
            comp_amount=comp.get('gross_profit'),
        )))

        # =================================================================
        # OPERATING EXPENSES SECTION
        # =================================================================
        seq[0] = 400
        line_commands.append(Command.create(_line_vals(
            _('OPERATING EXPENSES'),
            self.total_operating_expenses,
            level=0,
            is_total=True,
            is_group=True,
            comp_amount=comp.get('total_operating_expenses'),
        )))

        # -- General & Administrative subsection --
        # Subsection headers receive ``section='expense'`` so they
        # appear inside the template's OPERATING EXPENSES block.
        seq[0] = 410
        line_commands.append(Command.create(_line_vals(
            _('General & Administrative'),
            self.total_general_expenses,
            level=1,
            is_total=True,
            is_group=True,
            comp_amount=comp.get('total_general_expenses'),
            section='expense',
        )))
        _account_lines(
            general_expense_accounts, general_expense_balances,
            level=2, sign=1,
            comp_balances=comp.get('general_expense_balances'),
            section='expense',
        )

        # -- Depreciation & Amortization subsection --
        seq[0] = 450
        line_commands.append(Command.create(_line_vals(
            _('Depreciation & Amortization'),
            self.total_depreciation,
            level=1,
            is_total=True,
            is_group=True,
            comp_amount=comp.get('total_depreciation'),
            section='expense',
        )))
        _account_lines(
            depreciation_accounts, depreciation_balances,
            level=2, sign=1,
            comp_balances=comp.get('depreciation_balances'),
            section='expense',
        )

        # =================================================================
        # OPERATING INCOME
        # =================================================================
        seq[0] = 500
        line_commands.append(Command.create(_line_vals(
            _('OPERATING INCOME'),
            self.operating_income,
            level=0,
            is_total=True,
            is_group=True,
            comp_amount=comp.get('operating_income'),
        )))

        # =================================================================
        # OTHER INCOME / EXPENSES SECTION
        # =================================================================
        seq[0] = 600
        line_commands.append(Command.create(_line_vals(
            _('OTHER INCOME'),
            self.total_other_income,
            level=0,
            is_group=True,
            comp_amount=comp.get('total_other_income'),
        )))
        _account_lines(
            other_income_accounts, other_income_balances,
            level=1, sign=-1,
            comp_balances=comp.get('other_income_balances'),
            section='other',
        )

        # Other Expenses line (0.0 under standard Odoo chart)
        seq[0] = 650
        line_commands.append(Command.create(_line_vals(
            _('OTHER EXPENSES'),
            self.total_other_expenses,
            level=0,
            is_group=True,
            comp_amount=comp.get('total_other_expenses'),
        )))

        # Net Other Income / Expenses subtotal
        net_other = self.total_other_income - self.total_other_expenses
        comp_net_other = None
        if comp:
            comp_net_other = (
                comp.get('total_other_income', 0.0)
                - comp.get('total_other_expenses', 0.0)
            )
        seq[0] = 660
        line_commands.append(Command.create(_line_vals(
            _('NET OTHER INCOME / EXPENSES'),
            net_other,
            level=0,
            is_total=True,
            is_group=True,
            comp_amount=comp_net_other,
        )))

        # =================================================================
        # NET INCOME
        # =================================================================
        seq[0] = 700
        line_commands.append(Command.create(_line_vals(
            _('NET INCOME'),
            self.net_income,
            level=0,
            is_total=True,
            is_group=True,
            comp_amount=comp.get('net_income'),
        )))

        return line_commands

    # -------------------------------------------------------------------------
    # ACTION METHODS
    # -------------------------------------------------------------------------

    def action_generate_report(self):
        """
        Generate and display the Profit & Loss report.

        Validates that the required date parameters are present, triggers
        the full computation pipeline, and returns a window action to
        display the populated report form.

        Returns:
            dict: ``ir.actions.act_window`` action dictionary.

        Raises:
            UserError: If ``date_from`` or ``date_to`` is not specified.

        Per FR-002 Scenario 1:
            "Given I am logged in as CFO
             When I select P&L report and specify date range
             Then the system generates the income statement"
        """
        self.ensure_one()
        if not self.date_from or not self.date_to:
            raise UserError(
                _("Please specify the date range for the P&L report."),
            )

        self._compute_report_data()

        return {
            'name': _('Profit & Loss: %s to %s') % (
                self.date_from, self.date_to,
            ),
            'type': 'ir.actions.act_window',
            'res_model': 'account.profit.loss.report',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'inline',
        }

    def action_print_pdf(self):
        """
        Generate PDF version of the P&L report.

        Delegates to the ``ir.actions.report`` engine with the QWeb
        template registered for this report type.  ``config=False``
        prevents Odoo from redirecting to the document-layout
        configurator when the company has no external report layout
        set, which would otherwise return an ``ir.actions.act_window``
        instead of the expected ``ir.actions.report`` action.

        Returns:
            dict: Report action dictionary for PDF generation.

        Per FR-007 Acceptance Criteria:
            "Given I am viewing a P&L report
             When I select Export to PDF
             Then I receive a PDF document with proper formatting"
        """
        self.ensure_one()
        return self.env.ref(
            'account_financial_report_ce.action_report_profit_loss',
        ).report_action(self, config=False)

    def action_export_xlsx(self):
        """
        Export the P&L report to Excel (.xlsx) format.

        Delegates to the base-class ``action_export_xlsx`` which builds an
        in-memory ``openpyxl`` workbook using the column definitions from
        :meth:`_get_xlsx_columns` and the row data from
        :meth:`_get_xlsx_data`, stores the result as an ``ir.attachment``,
        and returns a download URL action that points at the generated
        attachment via ``/web/content/<id>?download=true``.

        Per FR-007 Acceptance Criteria:
            "Given I am viewing a P&L report
             When I select Export to Excel
             Then I receive an XLSX file with data in tabular format"

        Performance target: <10 seconds for 100 000 transactions.

        Returns:
            dict: ``ir.actions.act_url`` action dict pointing at the
            generated ``ir.attachment`` download URL.
        """
        self.ensure_one()
        return super().action_export_xlsx()


class ProfitLossReportLine(models.TransientModel):
    """
    Profit & Loss Report Line.

    Represents a single line in the P&L report with support for
    hierarchical display (section headers, subsections, account detail),
    comparative period amounts, and drill-down navigation to the
    underlying journal entries.
    """

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
    level = fields.Integer(
        string='Level',
        default=0,
        help="Hierarchy level: 0 = Section header, "
             "1 = Subsection, 2 = Account detail.",
    )
    amount = fields.Monetary(
        string='Amount',
        currency_field='currency_id',
    )
    comparison_amount = fields.Monetary(
        string='Comparison',
        currency_field='currency_id',
    )
    variance_absolute = fields.Monetary(
        string='Variance',
        currency_field='currency_id',
    )
    variance_percentage = fields.Float(string='Variance %')
    currency_id = fields.Many2one('res.currency', string='Currency')
    account_ids = fields.Many2many('account.account', string='Accounts')
    is_total = fields.Boolean(string='Is Total', default=False)

    # -----------------------------------------------------------------
    # TEMPLATE-FACING FIELDS
    # QWeb ``profit_loss_report.xml`` references these names for
    # section filtering, group-vs-detail rendering, drill-down links,
    # and monetary display.  They complement the canonical fields
    # above and are populated by ``_generate_report_lines``.
    # -----------------------------------------------------------------

    section = fields.Selection(
        selection=[
            ('revenue', 'Revenue'),
            ('cogs', 'Cost of Goods Sold'),
            ('expense', 'Operating Expenses'),
            ('other', 'Other Income/Expenses'),
        ],
        string='Report Section',
        help="P&L section this line belongs to. Used by the QWeb "
             "template to filter lines into the correct section block.",
    )

    is_group = fields.Boolean(
        string='Is Group Header',
        default=False,
        help="True for section/sub-section header rows, False for "
             "individual account detail lines.",
    )

    account_id = fields.Many2one(
        comodel_name='account.account',
        string='Account',
        help="Primary account for drill-down (first element of "
             "account_ids when the line represents a single account).",
    )

    account_code = fields.Char(
        string='Account Code',
        help="Account code for display in the report template.",
    )

    account_name = fields.Char(
        string='Account Name',
        help="Account name for display in the report template.",
    )

    balance = fields.Monetary(
        related='amount',
        string='Balance',
        readonly=True,
        help="Alias of 'amount' for QWeb template compatibility.",
    )

    balance_compare = fields.Monetary(
        related='comparison_amount',
        string='Balance Compare',
        readonly=True,
        help="Alias of 'comparison_amount' for QWeb template "
             "compatibility.",
    )

    def action_drilldown(self):
        """
        Navigate to the source journal items for this report line.

        Opens a filtered list view of ``account.move.line`` records
        that compose the amount displayed on this line.  Applies the
        report's date range and target-move filters.

        Returns:
            dict: ``ir.actions.act_window`` action showing filtered
                  journal items, or ``False`` if no accounts are linked.

        Per FR-007 Acceptance Criteria:
            "When I click on a line item amount
             Then I am navigated to a filtered view of the underlying
             journal entries that comprise that amount"
        """
        self.ensure_one()
        if not self.account_ids:
            return False

        domain = self.report_id._get_move_line_domain(
            date_from=self.report_id.date_from,
            date_to=self.report_id.date_to,
            account_ids=self.account_ids.ids,
        )

        return {
            'name': _('Journal Items - %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'account.move.line',
            'view_mode': 'list,form',
            'domain': domain,
            'context': {
                'search_default_posted': (
                    self.report_id.target_move == 'posted'
                ),
            },
        }
