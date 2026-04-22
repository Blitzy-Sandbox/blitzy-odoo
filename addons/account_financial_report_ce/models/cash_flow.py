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

Technical Notes:
- Indirect method starts with Net Income from the P&L report and adjusts
  for non-cash items and changes in working capital.
- Direct method groups actual cash receipts and disbursements by activity.
- All ``_compute_account_balance`` calls delegate to ``read_group`` on
  ``account.move.line`` for efficient SQL-level aggregation (< 30 s target
  with 100 K transactions).
- ``fields.Date.subtract`` is validated as an Odoo 19.0 API
  (delegates to ``odoo.tools.date_utils.subtract``).
"""

from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command


class CashFlowReport(models.TransientModel):
    """Cash Flow Statement Report.

    Generates a statement of cash flows using the indirect or direct method,
    showing cash from operating, investing, and financing activities.

    The indirect method (default) reconciles Net Income to net cash provided
    by operating activities by adjusting for non-cash items (depreciation)
    and changes in working capital accounts.

    The direct method groups all cash receipts and cash payments into
    operating, investing, and financing categories by analysing journal
    entries posted to cash-type accounts.

    Inherits common report parameters, multi-currency support, comparative
    period analysis, and drill-down navigation from
    ``account.financial.report.abstract``.
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
             "net income and adjusts for non-cash items. Direct method "
             "groups actual cash receipts and disbursements.",
    )

    # Account types for cash flow classification
    CASH_TYPES = ['asset_cash']
    RECEIVABLE_TYPES = ['asset_receivable']
    PAYABLE_TYPES = ['liability_payable']
    INVENTORY_TYPES = ['asset_current']
    FIXED_ASSET_TYPES = ['asset_fixed']
    NON_CURRENT_ASSET_TYPES = ['asset_non_current']
    EQUITY_TYPES = ['equity']
    EQUITY_UNAFFECTED_TYPES = ['equity_unaffected']
    LIABILITY_TYPES = ['liability_non_current']

    # Income/Expense types for direct-method classification
    INCOME_TYPES = ['income', 'income_other']
    EXPENSE_TYPES = ['expense', 'expense_depreciation', 'expense_direct_cost']

    # -------------------------------------------------------------------------
    # COMPUTED REPORT DATA
    # -------------------------------------------------------------------------

    # Opening and closing cash
    opening_cash = fields.Monetary(
        string='Opening Cash',
        currency_field='currency_id',
    )

    closing_cash = fields.Monetary(
        string='Closing Cash',
        currency_field='currency_id',
    )

    # Operating Activities
    net_income = fields.Monetary(
        string='Net Income',
        currency_field='currency_id',
    )

    depreciation_amortization = fields.Monetary(
        string='Depreciation & Amortization',
        currency_field='currency_id',
    )

    change_in_receivables = fields.Monetary(
        string='Change in Receivables',
        currency_field='currency_id',
    )

    change_in_payables = fields.Monetary(
        string='Change in Payables',
        currency_field='currency_id',
    )

    change_in_inventory = fields.Monetary(
        string='Change in Inventory',
        currency_field='currency_id',
    )

    cash_from_operating = fields.Monetary(
        string='Cash from Operating Activities',
        currency_field='currency_id',
    )

    # Investing Activities
    capital_expenditures = fields.Monetary(
        string='Capital Expenditures',
        currency_field='currency_id',
    )

    asset_disposals = fields.Monetary(
        string='Proceeds from Asset Sales',
        currency_field='currency_id',
    )

    cash_from_investing = fields.Monetary(
        string='Cash from Investing Activities',
        currency_field='currency_id',
    )

    # Financing Activities
    debt_proceeds = fields.Monetary(
        string='Proceeds from Borrowings',
        currency_field='currency_id',
    )

    debt_repayments = fields.Monetary(
        string='Debt Repayments',
        currency_field='currency_id',
    )

    equity_proceeds = fields.Monetary(
        string='Equity Proceeds',
        currency_field='currency_id',
        help="Net cash from share issuances or buybacks.",
    )

    dividends_paid = fields.Monetary(
        string='Dividends Paid',
        currency_field='currency_id',
    )

    cash_from_financing = fields.Monetary(
        string='Cash from Financing Activities',
        currency_field='currency_id',
    )

    # Net change
    net_change_in_cash = fields.Monetary(
        string='Net Change in Cash',
        currency_field='currency_id',
    )

    is_reconciled = fields.Boolean(
        string='Is Reconciled',
        help="True if Opening + Net Change = Closing",
    )

    # -------------------------------------------------------------------------
    # BACKWARD-COMPATIBLE ALIAS FIELDS
    # -------------------------------------------------------------------------

    beginning_cash = fields.Monetary(
        string='Beginning Cash',
        currency_field='currency_id',
        related='opening_cash',
        readonly=True,
        help="Alias for opening_cash.",
    )

    ending_cash = fields.Monetary(
        string='Ending Cash',
        currency_field='currency_id',
        related='closing_cash',
        readonly=True,
        help="Alias for closing_cash.",
    )

    # -----------------------------------------------------------------
    # TEMPLATE-FACING COMPARISON FIELDS
    # QWeb ``cash_flow_report.xml`` references ``doc.beginning_cash_compare``
    # and ``doc.net_income_compare`` for comparison column display in the
    # report header / summary rows.  These are populated by
    # ``_compute_report_data`` when comparison is enabled.
    # -----------------------------------------------------------------

    beginning_cash_compare = fields.Monetary(
        string='Beginning Cash (Comparison)',
        currency_field='currency_id',
        help="Opening cash balance for the comparison period.",
    )

    net_income_compare = fields.Monetary(
        string='Net Income (Comparison)',
        currency_field='currency_id',
        help="Net income for the comparison period.",
    )

    line_ids = fields.One2many(
        comodel_name='account.cash.flow.report.line',
        inverse_name='report_id',
        string='Report Lines',
    )

    # -------------------------------------------------------------------------
    # COMPUTATION METHODS
    # -------------------------------------------------------------------------

    def _compute_report_data(self):
        """Compute Cash Flow Statement data for every record in *self*.

        Dispatches to the indirect or direct method depending on the
        ``method`` field value:

        **Indirect method** (default, per ASC 230):
          1. Start with Net Income from the P&L report.
          2. Add back non-cash expenses (depreciation / amortization).
          3. Adjust for changes in working capital (receivables, payables,
             inventory).
          4. Calculate investing activities (fixed-asset and non-current-asset
             changes).
          5. Calculate financing activities (debt and equity changes).
          6. Verify cash reconciliation
             (``opening + net_change == closing``).

        **Direct method**:
          Analyses journal entries posted to cash accounts and categorises
          each cash movement into operating, investing, or financing based
          on the counterpart account type.

        Performance:
          All balance queries delegate to ``_compute_account_balance`` which
          uses ``read_group`` for SQL-level aggregation.  The target is
          < 30 seconds for 100 000 transactions.
        """
        for report in self:
            report.currency_id = report.company_id.currency_id

            # -----------------------------------------------------------------
            # CASH BALANCES (opening / closing)
            # -----------------------------------------------------------------
            cash_accounts = self.env['account.account'].search(
                report._get_account_domain(report.CASH_TYPES),
            )

            # Opening cash: cumulative balance up to the day before date_from
            opening_balances = report._compute_account_balance(
                cash_accounts,
                date_to=fields.Date.subtract(report.date_from, days=1),
            )
            report.opening_cash = sum(
                b['balance'] for b in opening_balances.values()
            )

            # Closing cash: cumulative balance up to date_to
            closing_balances = report._compute_account_balance(
                cash_accounts, date_to=report.date_to,
            )
            report.closing_cash = sum(
                b['balance'] for b in closing_balances.values()
            )

            # -----------------------------------------------------------------
            # DISPATCH to the selected method
            # -----------------------------------------------------------------
            if report.method == 'direct':
                report._compute_direct_method(cash_accounts)
            else:
                report._compute_indirect_method()

            # -----------------------------------------------------------------
            # NET CHANGE AND RECONCILIATION (Scenario 5)
            # -----------------------------------------------------------------
            report.net_change_in_cash = (
                report.cash_from_operating
                + report.cash_from_investing
                + report.cash_from_financing
            )

            # Verify: Opening + Net Change should equal Closing
            expected_closing = report.opening_cash + report.net_change_in_cash
            report.is_reconciled = (
                abs(expected_closing - report.closing_cash) < 0.01
            )

            # -----------------------------------------------------------------
            # COMPARATIVE PERIOD (Scenario 6)
            # -----------------------------------------------------------------
            comparison_data = {}
            if report.enable_comparison and report.comparison_date_from \
                    and report.comparison_date_to:
                comparison_data = report._compute_comparison_data()

            # Populate template-facing comparison doc-level fields
            if comparison_data:
                report.beginning_cash_compare = comparison_data.get(
                    'opening_cash', 0.0,
                )
                report.net_income_compare = comparison_data.get(
                    'net_income', 0.0,
                )
            else:
                report.beginning_cash_compare = 0.0
                report.net_income_compare = 0.0

            # -----------------------------------------------------------------
            # GENERATE REPORT LINES
            # -----------------------------------------------------------------
            report.line_ids = (
                [Command.clear()]
                + report._generate_report_lines(comparison_data)
            )

    # -------------------------------------------------------------------------
    # INDIRECT METHOD
    # -------------------------------------------------------------------------

    def _compute_indirect_method(self):
        """Compute cash flow sections using the *indirect* method.

        The indirect method starts with Net Income (from the in-memory
        Profit & Loss report) and adjusts for:
        - Non-cash charges (depreciation & amortization).
        - Changes in working capital (receivables, payables, inventory).
        - Investing activities (fixed and non-current asset changes).
        - Financing activities (debt and equity changes).

        All values are written directly to *self* (single-record context
        guaranteed by the caller loop).
        """
        self.ensure_one()
        report = self

        # ==================================================================
        # OPERATING ACTIVITIES (Scenario 2)
        # ==================================================================

        # --- Net Income from P&L ---
        pl_report = self.env['account.profit.loss.report'].new({
            'company_id': report.company_id.id,
            'date_from': report.date_from,
            'date_to': report.date_to,
            'target_move': report.target_move,
        })
        pl_report._compute_report_data()
        report.net_income = pl_report.net_income

        # --- Depreciation add-back (non-cash expense) ---
        depreciation_accounts = self.env['account.account'].search(
            report._get_account_domain(['expense_depreciation']),
        )
        depreciation_balances = report._compute_account_balance(
            depreciation_accounts,
            date_from=report.date_from,
            date_to=report.date_to,
        )
        report.depreciation_amortization = sum(
            b['balance'] for b in depreciation_balances.values()
        )

        # --- Change in Receivables ---
        report.change_in_receivables = report._compute_working_capital_delta(
            report.RECEIVABLE_TYPES,
        )

        # --- Change in Payables ---
        report.change_in_payables = report._compute_working_capital_delta(
            report.PAYABLE_TYPES,
        )

        # --- Change in Inventory ---
        # Inventory is tracked under ``asset_current`` accounts.  In a
        # pure accounting installation (without the ``stock`` module) there
        # may be no inventory-specific accounts.  We compute the delta for
        # all ``asset_current`` accounts and treat the result as inventory
        # change.  If no such accounts exist the value is 0.0.
        report.change_in_inventory = report._compute_working_capital_delta(
            report.INVENTORY_TYPES,
        )

        # --- Cash from Operating Activities total ---
        report.cash_from_operating = (
            report.net_income
            + report.depreciation_amortization
            + report.change_in_receivables
            + report.change_in_payables
            + report.change_in_inventory
        )

        # ==================================================================
        # INVESTING ACTIVITIES (Scenario 3)
        # ==================================================================
        # Use only ``asset_fixed`` accounts for investing activities under the
        # indirect method.  The ``asset_non_current`` type (which includes
        # accumulated depreciation contra-asset accounts) is intentionally
        # excluded because the depreciation impact is already captured by the
        # depreciation add-back in operating activities above.  Including it
        # here would double-count the non-cash depreciation expense.
        investing_types = list(report.FIXED_ASSET_TYPES)
        investing_accounts = self.env['account.account'].search(
            report._get_account_domain(investing_types),
        )
        opening_inv = report._compute_account_balance(
            investing_accounts,
            date_to=fields.Date.subtract(report.date_from, days=1),
        )
        closing_inv = report._compute_account_balance(
            investing_accounts, date_to=report.date_to,
        )
        inv_change = (
            sum(b['balance'] for b in closing_inv.values())
            - sum(b['balance'] for b in opening_inv.values())
        )

        # Simplified heuristic: net increase in long-lived assets is treated
        # as capital expenditure (cash outflow, negative); net decrease is
        # treated as disposal proceeds (cash inflow, positive).
        report.capital_expenditures = -max(inv_change, 0)
        report.asset_disposals = -min(inv_change, 0)

        report.cash_from_investing = (
            report.capital_expenditures + report.asset_disposals
        )

        # ==================================================================
        # FINANCING ACTIVITIES (Scenario 4)
        # ==================================================================

        # --- Long-term debt changes ---
        debt_accounts = self.env['account.account'].search(
            report._get_account_domain(report.LIABILITY_TYPES),
        )
        opening_debt = report._compute_account_balance(
            debt_accounts,
            date_to=fields.Date.subtract(report.date_from, days=1),
        )
        closing_debt = report._compute_account_balance(
            debt_accounts, date_to=report.date_to,
        )
        # Liability accounts have credit-normal balances (negative in Odoo);
        # we negate so that an *increase* in liabilities gives a positive
        # (cash inflow) value.
        debt_change = -(
            sum(b['balance'] for b in closing_debt.values())
            - sum(b['balance'] for b in opening_debt.values())
        )

        report.debt_proceeds = max(debt_change, 0)
        report.debt_repayments = -min(debt_change, 0)

        # --- Equity changes (share issuance / buybacks) ---
        equity_accounts = self.env['account.account'].search(
            report._get_account_domain(report.EQUITY_TYPES),
        )
        opening_eq = report._compute_account_balance(
            equity_accounts,
            date_to=fields.Date.subtract(report.date_from, days=1),
        )
        closing_eq = report._compute_account_balance(
            equity_accounts, date_to=report.date_to,
        )
        # Equity is credit-normal; negate so increases are positive cash.
        equity_change = -(
            sum(b['balance'] for b in closing_eq.values())
            - sum(b['balance'] for b in opening_eq.values())
        )
        report.equity_proceeds = equity_change

        # --- Dividends paid ---
        # Dividends paid reduce retained earnings / equity_unaffected.
        # Without a dedicated "dividends payable" account type in Odoo's
        # standard chart we approximate by looking at debit movements on
        # equity_unaffected accounts during the period (these represent
        # distributions to shareholders).  If the stock module or a
        # specific dividend account is not configured, the value stays 0.
        #
        # KNOWN LIMITATION (CP3 Finding #8, Business Logic MINOR):
        # This heuristic is deliberately conservative — the raw
        # ``debit`` aggregate on equity-unaffected accounts may over- or
        # under-state dividends in the presence of:
        #   * Reversal entries that debit-then-credit the same account
        #     on adjacent dates (both legs contribute to ``debit`` sums);
        #   * Re-classifications between equity and equity-unaffected
        #     (chart-of-accounts remapping) that touch these accounts for
        #     reasons unrelated to distributions;
        #   * Mid-period stock option exercises booked against retained
        #     earnings in some jurisdictions.
        # Semantically the heuristic prefers FALSE-NEGATIVES (under-
        # reporting dividends, overstating financing cash-flow) over
        # FALSE-POSITIVES.  Accountants needing strict classification
        # should tag dividend journal items explicitly and extend this
        # branch with a tag-aware filter.  See ``tests/test_cash_flow.py``
        # for the current invariants the heuristic must preserve.
        dividend_accounts = self.env['account.account'].search(
            report._get_account_domain(report.EQUITY_UNAFFECTED_TYPES),
        )
        if dividend_accounts:
            dividend_balances = report._compute_account_balance(
                dividend_accounts,
                date_from=report.date_from,
                date_to=report.date_to,
            )
            # Debit movements on equity accounts represent outflows
            # (dividends / distributions).  We take the total debit as a
            # proxy for dividends paid (shown as a negative cash flow).
            total_debit = sum(
                b.get('debit', 0.0) for b in dividend_balances.values()
            )
            report.dividends_paid = total_debit
        else:
            report.dividends_paid = 0.0

        report.cash_from_financing = (
            report.debt_proceeds
            - report.debt_repayments
            + report.equity_proceeds
            - report.dividends_paid
        )

    # -------------------------------------------------------------------------
    # DIRECT METHOD
    # -------------------------------------------------------------------------

    def _compute_direct_method(self, cash_accounts):
        """Compute cash flow sections using the *direct* method.

        The direct method analyses all journal entries that touch cash-type
        accounts during the period.  Each cash movement is classified into
        operating, investing, or financing based on the *counterpart*
        account type.

        Args:
            cash_accounts: Recordset of ``account.account`` records whose
                ``account_type`` is ``asset_cash``.

        Counterpart classification rules:
        - **Operating**: income, expense, receivable, payable, current
          asset / liability accounts.
        - **Investing**: fixed asset and non-current asset accounts.
        - **Financing**: non-current liability and equity accounts.

        When the direct method is selected the individual adjustment fields
        (``depreciation_amortization``, ``change_in_receivables``, etc.) are
        set to ``0.0`` because they are artefacts of the indirect method.
        """
        self.ensure_one()
        report = self

        if not cash_accounts:
            report.net_income = 0.0
            report.depreciation_amortization = 0.0
            report.change_in_receivables = 0.0
            report.change_in_payables = 0.0
            report.change_in_inventory = 0.0
            report.cash_from_operating = 0.0
            report.capital_expenditures = 0.0
            report.asset_disposals = 0.0
            report.cash_from_investing = 0.0
            report.debt_proceeds = 0.0
            report.debt_repayments = 0.0
            report.equity_proceeds = 0.0
            report.dividends_paid = 0.0
            report.cash_from_financing = 0.0
            return

        # Account-type sets used for counterpart classification.
        # Operating types (income, expense, receivable, payable, inventory,
        # current liabilities, prepayments) are handled as the default
        # fallback when a counterpart does not match investing or financing.
        investing_types = set(
            report.FIXED_ASSET_TYPES + report.NON_CURRENT_ASSET_TYPES,
        )
        financing_types = set(
            report.LIABILITY_TYPES + report.EQUITY_TYPES
            + report.EQUITY_UNAFFECTED_TYPES,
        )

        # Build domain to fetch journal items on cash accounts in the period
        domain = report._get_move_line_domain(
            date_from=report.date_from,
            date_to=report.date_to,
            account_ids=cash_accounts.ids,
        )

        # Fetch all cash-account journal items in the period
        cash_lines = self.env['account.move.line'].search(domain)

        operating_total = 0.0
        investing_total = 0.0
        financing_total = 0.0

        for line in cash_lines:
            # Determine the cash effect: positive = cash inflow
            cash_amount = line.debit - line.credit

            # Find counterpart lines on the same journal entry
            counterpart_lines = line.move_id.line_ids.filtered(
                lambda ml: ml.id != line.id
                and ml.account_id.id not in cash_accounts.ids,
            )

            if not counterpart_lines:
                # If no counterpart (rare), classify as operating
                operating_total += cash_amount
                continue

            # Classify by the dominant counterpart account type
            counterpart_types = set(
                counterpart_lines.mapped('account_id.account_type'),
            )

            if counterpart_types & investing_types:
                investing_total += cash_amount
            elif counterpart_types & financing_types:
                financing_total += cash_amount
            else:
                # Default to operating (covers income, expense, WC, etc.)
                operating_total += cash_amount

        # Populate section totals
        report.cash_from_operating = operating_total
        report.cash_from_investing = investing_total
        report.cash_from_financing = financing_total

        # Individual adjustment fields are not meaningful for the direct
        # method — zero them out to avoid confusion.
        report.net_income = 0.0
        report.depreciation_amortization = 0.0
        report.change_in_receivables = 0.0
        report.change_in_payables = 0.0
        report.change_in_inventory = 0.0
        report.capital_expenditures = 0.0
        report.asset_disposals = 0.0
        report.debt_proceeds = 0.0
        report.debt_repayments = 0.0
        report.equity_proceeds = 0.0
        report.dividends_paid = 0.0

    # -------------------------------------------------------------------------
    # WORKING CAPITAL HELPER
    # -------------------------------------------------------------------------

    def _compute_working_capital_delta(self, account_types):
        """Compute the period change for a set of working-capital accounts.

        The delta is calculated as::

            -(closing_balance - opening_balance)

        The negation follows the standard cash-flow sign convention:

        - An *increase* in an asset (e.g. receivables grow) means cash was
          *used* → negative adjustment to operating cash.
        - A *decrease* in an asset means cash was *received* → positive
          adjustment.
        - The inverse applies for liability accounts (payables).

        Args:
            account_types: List of ``account_type`` codes to include.

        Returns:
            ``float`` — The signed working-capital adjustment amount.
        """
        self.ensure_one()
        accounts = self.env['account.account'].search(
            self._get_account_domain(account_types),
        )
        if not accounts:
            return 0.0

        opening = self._compute_account_balance(
            accounts,
            date_to=fields.Date.subtract(self.date_from, days=1),
        )
        closing = self._compute_account_balance(
            accounts, date_to=self.date_to,
        )
        return -(
            sum(b['balance'] for b in closing.values())
            - sum(b['balance'] for b in opening.values())
        )

    # -------------------------------------------------------------------------
    # COMPARATIVE PERIOD
    # -------------------------------------------------------------------------

    def _compute_comparison_data(self):
        """Compute cash flow figures for the comparison period.

        Creates an ephemeral ``account.cash.flow.report`` record via
        ``new()`` with the comparison date range, computes its data, and
        returns a dict of field values that can be used for variance
        calculation in line generation.

        Returns:
            ``dict`` mapping field names to their comparison-period values,
            e.g. ``{'opening_cash': 1000.0, 'net_income': 500.0, ...}``.
        """
        self.ensure_one()
        comp = self.env['account.cash.flow.report'].new({
            'company_id': self.company_id.id,
            'date_from': self.comparison_date_from,
            'date_to': self.comparison_date_to,
            'target_move': self.target_move,
            'method': self.method,
            'enable_comparison': False,
        })
        comp._compute_report_data()

        return {
            'opening_cash': comp.opening_cash,
            'closing_cash': comp.closing_cash,
            'net_income': comp.net_income,
            'depreciation_amortization': comp.depreciation_amortization,
            'change_in_receivables': comp.change_in_receivables,
            'change_in_payables': comp.change_in_payables,
            'change_in_inventory': comp.change_in_inventory,
            'cash_from_operating': comp.cash_from_operating,
            'capital_expenditures': comp.capital_expenditures,
            'asset_disposals': comp.asset_disposals,
            'cash_from_investing': comp.cash_from_investing,
            'debt_proceeds': comp.debt_proceeds,
            'debt_repayments': comp.debt_repayments,
            'equity_proceeds': comp.equity_proceeds,
            'dividends_paid': comp.dividends_paid,
            'cash_from_financing': comp.cash_from_financing,
            'net_change_in_cash': comp.net_change_in_cash,
        }

    # -------------------------------------------------------------------------
    # REPORT LINE GENERATION
    # -------------------------------------------------------------------------

    def _generate_report_lines(self, comparison_data=None):
        """Generate hierarchical report lines for the Cash Flow Statement.

        Creates a list of ``Command.create`` tuples suitable for assigning
        to the ``line_ids`` One2many field.  The hierarchy mirrors the
        standard cash flow statement layout::

            Opening Cash Balance
            OPERATING ACTIVITIES
              Net Income
              Depreciation & Amortization
              Change in Receivables
              Change in Payables
              Change in Inventory
              *Cash from Operating Activities*
            INVESTING ACTIVITIES
              Capital Expenditures
              Proceeds from Asset Sales
              *Cash from Investing Activities*
            FINANCING ACTIVITIES
              Proceeds from Borrowings
              Debt Repayments
              Equity Proceeds
              Dividends Paid
              *Cash from Financing Activities*
            NET CHANGE IN CASH
            Closing Cash Balance

        Args:
            comparison_data: Optional ``dict`` of comparison-period values
                returned by ``_compute_comparison_data()``.  When provided,
                each line receives ``comparison_amount``, ``variance_absolute``
                and ``variance_percentage`` columns.

        Returns:
            ``list`` of ``Command.create(vals)`` tuples.
        """
        self.ensure_one()
        comp = comparison_data or {}
        lines = []
        seq = 0

        def _make_line(name, amount, level=1, is_total=False,
                       activity_type=False, comp_field=None):
            """Build a ``Command.create`` tuple for a single report line.

            Args:
                name:          Display label.
                amount:        Current-period monetary amount.
                level:         Indentation depth (0 = section header).
                is_total:      Whether this is a subtotal / total row.
                activity_type: ``'operating'``, ``'investing'``,
                               ``'financing'``, or ``False``.
                comp_field:    Key into *comparison_data* for the
                               comparison-period value.

            Returns:
                ``Command.create(vals)`` tuple.
            """
            nonlocal seq
            seq += 10

            vals = {
                'sequence': seq,
                'name': name,
                'level': level,
                'amount': amount,
                'is_total': is_total,
                'activity_type': activity_type,
                'currency_id': self.currency_id.id,
            }

            if comp and comp_field and comp_field in comp:
                comp_amount = comp[comp_field]
                variance = self._compute_variance(amount, comp_amount)
                vals.update({
                    'comparison_amount': comp_amount,
                    'variance_absolute': variance['absolute'],
                    'variance_percentage': variance['percentage'],
                })

            return Command.create(vals)

        # ---- Opening Cash Balance ----
        lines.append(_make_line(
            _('Opening Cash Balance'), self.opening_cash,
            level=0, is_total=True, comp_field='opening_cash',
        ))

        # ==================================================================
        # OPERATING ACTIVITIES
        # ==================================================================
        lines.append(_make_line(
            _('OPERATING ACTIVITIES'), self.cash_from_operating,
            level=0, is_total=True, activity_type='operating',
            comp_field='cash_from_operating',
        ))

        if self.method == 'indirect':
            lines.append(_make_line(
                _('Net Income'), self.net_income,
                level=1, activity_type='operating',
                comp_field='net_income',
            ))
            lines.append(_make_line(
                _('Depreciation & Amortization'),
                self.depreciation_amortization,
                level=1, activity_type='operating',
                comp_field='depreciation_amortization',
            ))
            lines.append(_make_line(
                _('Change in Receivables'), self.change_in_receivables,
                level=1, activity_type='operating',
                comp_field='change_in_receivables',
            ))
            lines.append(_make_line(
                _('Change in Payables'), self.change_in_payables,
                level=1, activity_type='operating',
                comp_field='change_in_payables',
            ))
            lines.append(_make_line(
                _('Change in Inventory'), self.change_in_inventory,
                level=1, activity_type='operating',
                comp_field='change_in_inventory',
            ))
        else:
            # Direct method — single operating total already shown in header
            lines.append(_make_line(
                _('Net Cash from Operations'), self.cash_from_operating,
                level=1, activity_type='operating',
                comp_field='cash_from_operating',
            ))

        # Subtotal
        lines.append(_make_line(
            _('Cash from Operating Activities'), self.cash_from_operating,
            level=1, is_total=True, activity_type='operating',
            comp_field='cash_from_operating',
        ))

        # ==================================================================
        # INVESTING ACTIVITIES
        # ==================================================================
        lines.append(_make_line(
            _('INVESTING ACTIVITIES'), self.cash_from_investing,
            level=0, is_total=True, activity_type='investing',
            comp_field='cash_from_investing',
        ))

        if self.method == 'indirect':
            lines.append(_make_line(
                _('Capital Expenditures'), self.capital_expenditures,
                level=1, activity_type='investing',
                comp_field='capital_expenditures',
            ))
            lines.append(_make_line(
                _('Proceeds from Asset Sales'), self.asset_disposals,
                level=1, activity_type='investing',
                comp_field='asset_disposals',
            ))
        else:
            lines.append(_make_line(
                _('Net Cash from Investing'), self.cash_from_investing,
                level=1, activity_type='investing',
                comp_field='cash_from_investing',
            ))

        lines.append(_make_line(
            _('Cash from Investing Activities'), self.cash_from_investing,
            level=1, is_total=True, activity_type='investing',
            comp_field='cash_from_investing',
        ))

        # ==================================================================
        # FINANCING ACTIVITIES
        # ==================================================================
        lines.append(_make_line(
            _('FINANCING ACTIVITIES'), self.cash_from_financing,
            level=0, is_total=True, activity_type='financing',
            comp_field='cash_from_financing',
        ))

        if self.method == 'indirect':
            lines.append(_make_line(
                _('Proceeds from Borrowings'), self.debt_proceeds,
                level=1, activity_type='financing',
                comp_field='debt_proceeds',
            ))
            lines.append(_make_line(
                _('Debt Repayments'), self.debt_repayments,
                level=1, activity_type='financing',
                comp_field='debt_repayments',
            ))
            lines.append(_make_line(
                _('Equity Proceeds'), self.equity_proceeds,
                level=1, activity_type='financing',
                comp_field='equity_proceeds',
            ))
            lines.append(_make_line(
                _('Dividends Paid'), self.dividends_paid,
                level=1, activity_type='financing',
                comp_field='dividends_paid',
            ))
        else:
            lines.append(_make_line(
                _('Net Cash from Financing'), self.cash_from_financing,
                level=1, activity_type='financing',
                comp_field='cash_from_financing',
            ))

        lines.append(_make_line(
            _('Cash from Financing Activities'), self.cash_from_financing,
            level=1, is_total=True, activity_type='financing',
            comp_field='cash_from_financing',
        ))

        # ==================================================================
        # NET CHANGE & CLOSING
        # ==================================================================
        lines.append(_make_line(
            _('NET CHANGE IN CASH'), self.net_change_in_cash,
            level=0, is_total=True,
            comp_field='net_change_in_cash',
        ))

        lines.append(_make_line(
            _('Closing Cash Balance'), self.closing_cash,
            level=0, is_total=True,
            comp_field='closing_cash',
        ))

        return lines

    # -------------------------------------------------------------------------
    # ACTION METHODS
    # -------------------------------------------------------------------------

    def action_generate_report(self):
        """Generate and display the Cash Flow Statement.

        Validates that ``date_from`` and ``date_to`` are provided, triggers
        the computation, and returns a window action pointing at the
        current record's form view.

        Returns:
            ``dict`` — ``ir.actions.act_window`` action.

        Raises:
            :class:`~odoo.exceptions.UserError`: If the date range is
                incomplete.
        """
        self.ensure_one()
        if not self.date_from or not self.date_to:
            raise UserError(_("Please specify the date range."))

        if self.date_from > self.date_to:
            raise UserError(_(
                "The start date (%s) must be before or equal to the "
                "end date (%s).",
            ) % (self.date_from, self.date_to))

        self._compute_report_data()

        return {
            'name': _('Cash Flow: %s to %s') % (self.date_from, self.date_to),
            'type': 'ir.actions.act_window',
            'res_model': 'account.cash.flow.report',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'inline',
        }

    def action_print_pdf(self):
        """Generate a PDF version of the Cash Flow Statement.

        Delegates to the ``ir.actions.report`` action registered for the
        cash flow report QWeb template.  ``config=False`` prevents Odoo
        from redirecting to the document-layout configurator when the
        company has no external report layout set, which would otherwise
        return an ``ir.actions.act_window`` instead of the expected
        ``ir.actions.report`` action.

        Returns:
            ``dict`` — ``ir.actions.report`` action dictionary for PDF
            generation.
        """
        self.ensure_one()
        return self.env.ref(
            'account_financial_report_ce.action_report_cash_flow',
        ).report_action(self, config=False)

    def action_export_xlsx(self):
        """Export Cash Flow Statement to Excel (.xlsx) format.

        Delegates to the base-class ``action_export_xlsx`` which builds
        an in-memory ``openpyxl`` workbook using the column definitions
        from :meth:`_get_xlsx_columns` and the row data from
        :meth:`_get_xlsx_data`, stores the result as an
        ``ir.attachment``, and returns a download URL action pointing
        at the generated attachment via
        ``/web/content/<id>?download=true``.

        The base pipeline includes both the report data sheet and a
        supplementary ``Report Parameters`` sheet containing company,
        date range, target moves, and comparison metadata for
        audit/traceability.

        Per FR-007 Acceptance Criteria:
            "Given I am viewing a Cash Flow Statement
             When I select Export to Excel
             Then I receive an XLSX file with data in tabular format"

        Performance target: <10 seconds for 100 000 transactions.

        Returns:
            dict: ``ir.actions.act_url`` action dict pointing at the
            generated ``ir.attachment`` download URL.
        """
        self.ensure_one()
        return super().action_export_xlsx()


class CashFlowReportLine(models.TransientModel):
    """Cash Flow Report Line.

    Represents a single line in the Cash Flow Statement report.
    Lines are organised hierarchically:
    - ``level=0``: Section headers (Operating, Investing, Financing).
    - ``level=1``: Detail or subtotal lines within a section.

    The ``activity_type`` field classifies each line into the relevant
    cash-flow section for filtering and styling purposes.
    """

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
    comparison_amount = fields.Monetary(
        string='Comparison', currency_field='currency_id',
    )
    variance_absolute = fields.Monetary(
        string='Variance', currency_field='currency_id',
    )
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

    # -----------------------------------------------------------------
    # TEMPLATE-FACING FIELDS
    # QWeb ``cash_flow_report.xml`` references ``line.amount_compare``
    # for comparison column display.  This is an alias for the canonical
    # ``comparison_amount`` field.
    # -----------------------------------------------------------------

    amount_compare = fields.Monetary(
        related='comparison_amount',
        string='Amount Compare',
        readonly=True,
        help="Alias of 'comparison_amount' for QWeb template "
             "compatibility.",
    )

    def action_drilldown(self):
        """Drill down to the journal items underlying this report line.

        Uses the parent report's date range and the line's activity type
        to build an appropriate domain filter.  Section-header and total
        lines open all journal items for the associated activity type;
        detail lines open items filtered to the relevant account types.

        Returns:
            ``dict`` — ``ir.actions.act_window`` action opening
            ``account.move.line`` list view, or ``False`` if drill-down
            is not applicable.
        """
        self.ensure_one()
        report = self.report_id
        if not report:
            return False

        # Map activity types to the account types they encompass
        activity_account_map = {
            'operating': (
                report.INCOME_TYPES + report.EXPENSE_TYPES
                + report.RECEIVABLE_TYPES + report.PAYABLE_TYPES
                + report.INVENTORY_TYPES
            ),
            'investing': (
                report.FIXED_ASSET_TYPES + report.NON_CURRENT_ASSET_TYPES
            ),
            'financing': (
                report.LIABILITY_TYPES + report.EQUITY_TYPES
                + report.EQUITY_UNAFFECTED_TYPES
            ),
        }

        account_types = activity_account_map.get(self.activity_type)
        if not account_types:
            # Opening / closing / net-change lines → show cash account items
            account_types = report.CASH_TYPES

        accounts = self.env['account.account'].search(
            report._get_account_domain(account_types),
        )
        if not accounts:
            return False

        domain = report._get_move_line_domain(
            date_from=report.date_from,
            date_to=report.date_to,
            account_ids=accounts.ids,
        )

        return {
            'name': _('Journal Items — %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'account.move.line',
            'view_mode': 'list,form',
            'domain': domain,
            'context': {
                'search_default_posted': report.target_move == 'posted',
            },
        }
