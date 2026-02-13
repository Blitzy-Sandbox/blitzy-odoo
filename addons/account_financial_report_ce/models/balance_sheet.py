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

import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class BalanceSheetReport(models.TransientModel):
    """Balance Sheet Report Wizard and Generator.

    This transient model provides the wizard interface for generating
    Balance Sheet reports and the computation logic for the report data.

    The Balance Sheet displays the company's financial position as of a
    specific date, organized into three principal sections:

    * **Assets** — resources owned or controlled by the company
      (Current: cash, receivables, prepayments; Non-current: fixed
      assets, long-term investments).
    * **Liabilities** — obligations owed to outside parties
      (Current: payables, credit-card debt; Non-current: long-term debt).
    * **Equity** — residual interest of the owners (capital, retained
      earnings, current-year earnings derived from Income/Expense accounts).

    The fundamental accounting equation is enforced on every computation::

        Assets = Liabilities + Equity

    Comparative period analysis is supported: when ``enable_comparison``
    is ``True``, the report fetches prior-period balances and computes
    absolute and percentage variances for every line.

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

    # Account types mapping for Odoo 19.0 — these constants map the
    # ``account_type`` selection field on ``account.account`` to the
    # Balance Sheet classification hierarchy.
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
        'liability_payable',      # Accounts payable
        'liability_credit_card',  # Credit card
        'liability_current',      # Other current liabilities
    ]

    LIABILITY_NON_CURRENT_TYPES = [
        'liability_non_current',  # Long-term liabilities
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
        """Compute all Balance Sheet data including optional comparison period.

        Performs the following steps for each report record:

        1. Retrieve account balances for all account types using SQL-level
           aggregation (``read_group``) via the inherited
           ``_compute_account_balance`` for performance (<30 s / 100K txns).
        2. Classify accounts into Assets, Liabilities, Equity per the
           account-type constants defined on this model.
        3. Compute current-year earnings from Income/Expense (P&L) accounts
           within the fiscal year.
        4. Validate the accounting equation ``A = L + E`` (with rounding
           tolerance) and store the validation result.
        5. When ``enable_comparison`` is ``True`` and ``comparison_date_to``
           is set, fetch prior-period balances and compute absolute and
           percentage variances via the inherited ``_compute_variance``.
        6. Generate report lines (``line_ids``) with hierarchical section
           structure, including comparison and variance columns when enabled.

        Per FR-001 Acceptance Criteria:
        - Scenario 1: Complete Balance Sheet generation
        - Scenario 5: Comparative Balance Sheet with variance columns
        - Scenario 6: Validation that A = L + E

        Performance target: <30 seconds for 100 000 transactions.
        """
        for report in self:
            # Set company currency for monetary formatting
            report.currency_id = report.company_id.currency_id

            # Determine fiscal year start for P&L (current-year earnings)
            date_from = report.date_from or report._get_fiscal_year_start()

            # ----------------------------------------------------------------
            # COMPUTE ASSET BALANCES (Scenario 2)
            # Cumulative balance (no date_from) per Balance Sheet convention.
            # ----------------------------------------------------------------
            current_asset_accounts = self.env['account.account'].search(
                report._get_account_domain(report.ASSET_CURRENT_TYPES),
            )
            non_current_asset_accounts = self.env['account.account'].search(
                report._get_account_domain(report.ASSET_NON_CURRENT_TYPES),
            )

            current_asset_balances = report._compute_account_balance(
                current_asset_accounts, date_to=report.date_to,
            )
            non_current_asset_balances = report._compute_account_balance(
                non_current_asset_accounts, date_to=report.date_to,
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
            # Liabilities carry credit-normal balance (negative in Odoo);
            # negate to present as positive figures in the report.
            # ----------------------------------------------------------------
            current_liability_accounts = self.env['account.account'].search(
                report._get_account_domain(report.LIABILITY_CURRENT_TYPES),
            )
            non_current_liability_accounts = self.env['account.account'].search(
                report._get_account_domain(report.LIABILITY_NON_CURRENT_TYPES),
            )

            current_liability_balances = report._compute_account_balance(
                current_liability_accounts, date_to=report.date_to,
            )
            non_current_liability_balances = report._compute_account_balance(
                non_current_liability_accounts, date_to=report.date_to,
            )

            report.total_current_liabilities = -sum(
                b['balance'] for b in current_liability_balances.values()
            )
            report.total_non_current_liabilities = -sum(
                b['balance'] for b in non_current_liability_balances.values()
            )
            report.total_liabilities = (
                report.total_current_liabilities
                + report.total_non_current_liabilities
            )

            # ----------------------------------------------------------------
            # COMPUTE EQUITY BALANCES (Scenario 4)
            # Equity carries credit-normal balance (negative in Odoo).
            # Current-year earnings = Income - Expenses for the fiscal year.
            # ----------------------------------------------------------------
            equity_accounts = self.env['account.account'].search(
                report._get_account_domain(report.EQUITY_TYPES),
            )
            equity_balances = report._compute_account_balance(
                equity_accounts, date_to=report.date_to,
            )

            base_equity = -sum(
                b['balance'] for b in equity_balances.values()
            )

            # Fetch Income / Expense balances for current-year earnings
            income_accounts = self.env['account.account'].search(
                report._get_account_domain(report.INCOME_TYPES),
            )
            expense_accounts = self.env['account.account'].search(
                report._get_account_domain(report.EXPENSE_TYPES),
            )

            income_balances = report._compute_account_balance(
                income_accounts, date_from=date_from, date_to=report.date_to,
            )
            expense_balances = report._compute_account_balance(
                expense_accounts, date_from=date_from, date_to=report.date_to,
            )

            total_income = -sum(
                b['balance'] for b in income_balances.values()
            )
            total_expenses = sum(
                b['balance'] for b in expense_balances.values()
            )

            report.current_year_earnings = total_income - total_expenses

            # ----------------------------------------------------------------
            # PRIOR-YEAR RETAINED EARNINGS
            # The balance sheet equation (A = L + E) requires that all
            # income/expense from prior fiscal years is captured as
            # retained earnings in equity.  When the year-end close
            # process has not been executed, P&L account balances from
            # prior periods still exist and must be folded into equity
            # so the equation balances.
            # ----------------------------------------------------------------
            prior_income_balances = report._compute_account_balance(
                income_accounts, date_to=date_from - timedelta(days=1),
            )
            prior_expense_balances = report._compute_account_balance(
                expense_accounts, date_to=date_from - timedelta(days=1),
            )
            prior_year_income = -sum(
                b['balance'] for b in prior_income_balances.values()
            )
            prior_year_expenses = sum(
                b['balance'] for b in prior_expense_balances.values()
            )
            prior_year_earnings = prior_year_income - prior_year_expenses

            # Retained earnings = equity accounts + prior-year net income
            report.retained_earnings = base_equity + prior_year_earnings

            report.total_equity = (
                report.retained_earnings + report.current_year_earnings
            )

            # ----------------------------------------------------------------
            # VALIDATE ACCOUNTING EQUATION (Scenario 6)
            # A = L + E — enforced with rounding tolerance.
            # ----------------------------------------------------------------
            validation = report._validate_accounting_equation(
                report.total_assets,
                report.total_liabilities,
                report.total_equity,
            )
            report.is_balanced = validation['is_balanced']
            report.balance_difference = validation['difference']

            if not report.is_balanced:
                _logger.warning(
                    "Balance Sheet as of %s is NOT balanced: "
                    "Assets=%.2f, L+E=%.2f, diff=%.2f",
                    report.date_to,
                    report.total_assets,
                    report.total_liabilities + report.total_equity,
                    report.balance_difference,
                )

            # ----------------------------------------------------------------
            # COMPARATIVE PERIOD CALCULATION (Scenario 5)
            # When enabled, recompute all section balances as of the
            # comparison date and package them for line generation.
            # ----------------------------------------------------------------
            comparison = None
            if report.enable_comparison and report.comparison_date_to:
                comparison = report._compute_comparison_data(
                    current_asset_accounts=current_asset_accounts,
                    non_current_asset_accounts=non_current_asset_accounts,
                    current_liability_accounts=current_liability_accounts,
                    non_current_liability_accounts=(
                        non_current_liability_accounts
                    ),
                    equity_accounts=equity_accounts,
                    income_accounts=income_accounts,
                    expense_accounts=expense_accounts,
                )

            # ----------------------------------------------------------------
            # GENERATE REPORT LINES
            # ----------------------------------------------------------------
            report.line_ids = report._generate_report_lines(
                current_asset_accounts, current_asset_balances,
                non_current_asset_accounts, non_current_asset_balances,
                current_liability_accounts, current_liability_balances,
                non_current_liability_accounts, non_current_liability_balances,
                equity_accounts, equity_balances,
                comparison=comparison,
            )

    # -------------------------------------------------------------------------
    # FISCAL YEAR HELPERS
    # -------------------------------------------------------------------------

    def _get_fiscal_year_start(self):
        """Return the start date of the fiscal year containing ``date_to``.

        Uses the company's fiscal-year configuration.  Falls back to
        January 1st of the ``date_to`` year when the company has no
        explicit fiscal-year setup.

        Returns:
            ``datetime.date``: First day of the fiscal year.
        """
        self.ensure_one()
        fiscal_year = self.company_id.compute_fiscalyear_dates(self.date_to)
        return fiscal_year.get(
            'date_from', self.date_to.replace(month=1, day=1),
        )

    def _get_comparison_fiscal_year_start(self):
        """Return the fiscal-year start applicable to the comparison period.

        When ``comparison_date_from`` is explicitly set by the user, it
        is returned directly.  Otherwise the fiscal year containing
        ``comparison_date_to`` is derived from the company's calendar,
        falling back to January 1st of that year.

        Returns:
            ``datetime.date`` or ``False`` when comparison is not configured.
        """
        self.ensure_one()
        if self.comparison_date_from:
            return self.comparison_date_from
        if not self.comparison_date_to:
            return False
        fiscal_year = self.company_id.compute_fiscalyear_dates(
            self.comparison_date_to,
        )
        return fiscal_year.get(
            'date_from',
            self.comparison_date_to.replace(month=1, day=1),
        )

    # -------------------------------------------------------------------------
    # COMPARISON PERIOD COMPUTATION
    # -------------------------------------------------------------------------

    def _compute_comparison_data(
        self,
        current_asset_accounts,
        non_current_asset_accounts,
        current_liability_accounts,
        non_current_liability_accounts,
        equity_accounts,
        income_accounts,
        expense_accounts,
    ):
        """Compute comparison-period balances for all Balance Sheet sections.

        Mirrors the logic in ``_compute_report_data`` but targets the
        comparison date range instead of the primary reporting dates.
        The return value is a dict consumed by ``_generate_report_lines``
        to populate comparison and variance columns on every line.

        Balance Sheet accounts (Assets, Liabilities, Equity) use
        cumulative balances (no ``date_from``).  Income/Expense accounts
        for comparison current-year-earnings use the comparison fiscal
        year as the period boundary.

        Args:
            current_asset_accounts: Recordset of current-asset accounts.
            non_current_asset_accounts: Recordset of non-current-asset
                accounts.
            current_liability_accounts: Recordset of current-liability
                accounts.
            non_current_liability_accounts: Recordset of non-current-
                liability accounts.
            equity_accounts: Recordset of equity accounts.
            income_accounts: Recordset of income accounts.
            expense_accounts: Recordset of expense accounts.

        Returns:
            dict: Comparison data containing per-account balances and
            computed section totals::

                {
                    'current_asset_balances': {acct_id: {...}, ...},
                    'total_current_assets': float,
                    ...
                    'total_equity': float,
                }
        """
        self.ensure_one()
        comp_date_to = self.comparison_date_to
        comp_fiscal_start = self._get_comparison_fiscal_year_start()

        # --- Assets (cumulative, no date_from) ---
        comp_ca = self._compute_account_balance(
            current_asset_accounts, date_to=comp_date_to,
        )
        comp_nca = self._compute_account_balance(
            non_current_asset_accounts, date_to=comp_date_to,
        )
        total_ca = sum(b['balance'] for b in comp_ca.values())
        total_nca = sum(b['balance'] for b in comp_nca.values())

        # --- Liabilities (credit-normal, negated for presentation) ---
        comp_cl = self._compute_account_balance(
            current_liability_accounts, date_to=comp_date_to,
        )
        comp_ncl = self._compute_account_balance(
            non_current_liability_accounts, date_to=comp_date_to,
        )
        total_cl = -sum(b['balance'] for b in comp_cl.values())
        total_ncl = -sum(b['balance'] for b in comp_ncl.values())

        # --- Equity (credit-normal, negated for presentation) ---
        comp_eq = self._compute_account_balance(
            equity_accounts, date_to=comp_date_to,
        )
        comp_base_equity = -sum(b['balance'] for b in comp_eq.values())

        # --- P&L accounts for comparison current-year earnings ---
        comp_inc = self._compute_account_balance(
            income_accounts,
            date_from=comp_fiscal_start,
            date_to=comp_date_to,
        )
        comp_exp = self._compute_account_balance(
            expense_accounts,
            date_from=comp_fiscal_start,
            date_to=comp_date_to,
        )
        comp_total_income = -sum(b['balance'] for b in comp_inc.values())
        comp_total_expenses = sum(b['balance'] for b in comp_exp.values())
        comp_year_earnings = comp_total_income - comp_total_expenses

        # Prior-year retained earnings for comparison period
        comp_prior_inc = self._compute_account_balance(
            income_accounts,
            date_to=comp_fiscal_start - timedelta(days=1),
        )
        comp_prior_exp = self._compute_account_balance(
            expense_accounts,
            date_to=comp_fiscal_start - timedelta(days=1),
        )
        comp_prior_income = -sum(
            b['balance'] for b in comp_prior_inc.values()
        )
        comp_prior_expenses = sum(
            b['balance'] for b in comp_prior_exp.values()
        )
        comp_prior_earnings = comp_prior_income - comp_prior_expenses
        comp_retained = comp_base_equity + comp_prior_earnings

        return {
            # Per-account balance dicts (used by account-detail lines)
            'current_asset_balances': comp_ca,
            'non_current_asset_balances': comp_nca,
            'current_liability_balances': comp_cl,
            'non_current_liability_balances': comp_ncl,
            'equity_balances': comp_eq,
            # Section totals (used by section-header lines)
            'total_current_assets': total_ca,
            'total_non_current_assets': total_nca,
            'total_assets': total_ca + total_nca,
            'total_current_liabilities': total_cl,
            'total_non_current_liabilities': total_ncl,
            'total_liabilities': total_cl + total_ncl,
            'retained_earnings': comp_retained,
            'current_year_earnings': comp_year_earnings,
            'total_equity': comp_retained + comp_year_earnings,
        }

    # -------------------------------------------------------------------------
    # REPORT LINE GENERATION
    # -------------------------------------------------------------------------

    def _generate_report_lines(
        self,
        current_asset_accounts,
        current_asset_balances,
        non_current_asset_accounts,
        non_current_asset_balances,
        current_liability_accounts,
        current_liability_balances,
        non_current_liability_accounts,
        non_current_liability_balances,
        equity_accounts,
        equity_balances,
        comparison=None,
    ):
        """Generate hierarchical report-line records for display.

        Creates the following structure of virtual line records:

        * **ASSETS**

          * Current Assets → [account detail lines]
          * Non-Current Assets → [account detail lines]

        * **LIABILITIES**

          * Current Liabilities → [account detail lines]
          * Non-Current Liabilities → [account detail lines]

        * **EQUITY**

          * [equity account lines]
          * Current Year Earnings

        * **TOTAL LIABILITIES AND EQUITY**

        When *comparison* is provided, every line includes
        ``comparison_amount``, ``variance_absolute``, and
        ``variance_percentage`` computed from the comparison-period data
        via the inherited ``_compute_variance`` helper.

        Args:
            current_asset_accounts: Recordset of current-asset accounts.
            current_asset_balances: Dict mapping account ID → balance dict.
            non_current_asset_accounts: Recordset of non-current-asset
                accounts.
            non_current_asset_balances: Dict mapping account ID → balance
                dict.
            current_liability_accounts: Recordset of current-liability
                accounts.
            current_liability_balances: Dict mapping account ID → balance
                dict.
            non_current_liability_accounts: Recordset of non-current-
                liability accounts.
            non_current_liability_balances: Dict mapping account ID →
                balance dict.
            equity_accounts: Recordset of equity accounts.
            equity_balances: Dict mapping account ID → balance dict.
            comparison: Optional dict of comparison-period data returned
                by ``_compute_comparison_data``.  Pass ``None`` to disable
                comparison columns.

        Returns:
            list: ``fields.Command.create()`` tuples for assignment
            to ``line_ids``, producing persisted report-line records.
        """
        lines = []
        sequence = 0

        # -- Variance helper ---------------------------------------------------
        # Returns (comparison_amount, variance_absolute, variance_percentage)
        # for a given current amount and its comparison-period counterpart.
        def _var(current_amount, comp_amount):
            if comparison is None:
                return 0.0, 0.0, 0.0
            var = self._compute_variance(current_amount, comp_amount)
            return comp_amount, var['absolute'], var['percentage']

        # -- Account-detail line helper ----------------------------------------
        def add_account_lines(accounts, balances, level, sign=1,
                              comp_balances=None, section='asset'):
            """Create account-level detail lines for a section.

            Args:
                accounts: Recordset of ``account.account`` records.
                balances: Dict mapping account ID → balance dict.
                level: Indentation level (2 = account detail).
                sign: Balance multiplier (1 for debit-normal assets,
                    -1 for credit-normal liabilities/equity).
                comp_balances: Optional comparison balance dict.
                section: Section identifier ('asset', 'liability',
                    'equity') for template-side filtering.

            Returns:
                list: ``fields.Command.create()`` tuples for the
                    account detail lines.
            """
            nonlocal sequence
            result = []
            for account in accounts.sorted(key=lambda a: a.code):
                balance = balances.get(account.id, {})
                amount = balance.get('balance', 0.0) * sign
                if self.hide_zero_balance and not amount:
                    continue

                # Comparison data for this specific account
                comp_amount = 0.0
                if comparison and comp_balances:
                    comp_bal = comp_balances.get(account.id, {})
                    comp_amount = comp_bal.get('balance', 0.0) * sign
                c_amt, v_abs, v_pct = _var(amount, comp_amount)

                sequence += 1
                result.append(fields.Command.create({
                    'sequence': sequence,
                    'name': "%s - %s" % (account.code, account.name),
                    'level': level,
                    'amount': amount,
                    'comparison_amount': c_amt,
                    'variance_absolute': v_abs,
                    'variance_percentage': v_pct,
                    'account_ids': [fields.Command.set([account.id])],
                    'currency_id': self.currency_id.id,
                    'section': section,
                    'is_group': False,
                    'account_id': account.id,
                    'account_code': account.code,
                    'account_name': account.name,
                }))
            return result

        # =====================================================================
        # ASSETS SECTION
        # =====================================================================
        comp_ta = comparison['total_assets'] if comparison else 0.0
        ca_ta, va_ta, vp_ta = _var(self.total_assets, comp_ta)

        sequence = 100
        lines.append(fields.Command.create({
            'sequence': sequence,
            'name': _('ASSETS'),
            'level': 0,
            'is_total': True,
            'is_group': True,
            'section': 'asset',
            'amount': self.total_assets,
            'comparison_amount': ca_ta,
            'variance_absolute': va_ta,
            'variance_percentage': vp_ta,
            'currency_id': self.currency_id.id,
        }))

        # Current Assets subsection
        comp_tca = comparison['total_current_assets'] if comparison else 0.0
        ca_tca, va_tca, vp_tca = _var(self.total_current_assets, comp_tca)

        sequence = 110
        lines.append(fields.Command.create({
            'sequence': sequence,
            'name': _('Current Assets'),
            'level': 1,
            'is_total': True,
            'is_group': True,
            'section': 'asset',
            'amount': self.total_current_assets,
            'comparison_amount': ca_tca,
            'variance_absolute': va_tca,
            'variance_percentage': vp_tca,
            'currency_id': self.currency_id.id,
        }))
        lines.extend(add_account_lines(
            current_asset_accounts, current_asset_balances,
            level=2, sign=1,
            comp_balances=(
                comparison.get('current_asset_balances')
                if comparison else None
            ),
            section='asset',
        ))

        # Non-Current Assets subsection
        comp_tnca = (
            comparison['total_non_current_assets'] if comparison else 0.0
        )
        ca_tnca, va_tnca, vp_tnca = _var(
            self.total_non_current_assets, comp_tnca,
        )

        sequence = 150
        lines.append(fields.Command.create({
            'sequence': sequence,
            'name': _('Non-Current Assets'),
            'level': 1,
            'is_total': True,
            'is_group': True,
            'section': 'asset',
            'amount': self.total_non_current_assets,
            'comparison_amount': ca_tnca,
            'variance_absolute': va_tnca,
            'variance_percentage': vp_tnca,
            'currency_id': self.currency_id.id,
        }))
        lines.extend(add_account_lines(
            non_current_asset_accounts, non_current_asset_balances,
            level=2, sign=1,
            comp_balances=(
                comparison.get('non_current_asset_balances')
                if comparison else None
            ),
            section='asset',
        ))

        # =====================================================================
        # LIABILITIES SECTION
        # =====================================================================
        comp_tl = comparison['total_liabilities'] if comparison else 0.0
        ca_tl, va_tl, vp_tl = _var(self.total_liabilities, comp_tl)

        sequence = 200
        lines.append(fields.Command.create({
            'sequence': sequence,
            'name': _('LIABILITIES'),
            'level': 0,
            'is_total': True,
            'is_group': True,
            'section': 'liability',
            'amount': self.total_liabilities,
            'comparison_amount': ca_tl,
            'variance_absolute': va_tl,
            'variance_percentage': vp_tl,
            'currency_id': self.currency_id.id,
        }))

        # Current Liabilities subsection
        comp_tcl = (
            comparison['total_current_liabilities'] if comparison else 0.0
        )
        ca_tcl, va_tcl, vp_tcl = _var(
            self.total_current_liabilities, comp_tcl,
        )

        sequence = 210
        lines.append(fields.Command.create({
            'sequence': sequence,
            'name': _('Current Liabilities'),
            'level': 1,
            'is_total': True,
            'is_group': True,
            'section': 'liability',
            'amount': self.total_current_liabilities,
            'comparison_amount': ca_tcl,
            'variance_absolute': va_tcl,
            'variance_percentage': vp_tcl,
            'currency_id': self.currency_id.id,
        }))
        lines.extend(add_account_lines(
            current_liability_accounts, current_liability_balances,
            level=2, sign=-1,
            comp_balances=(
                comparison.get('current_liability_balances')
                if comparison else None
            ),
            section='liability',
        ))

        # Non-Current Liabilities subsection
        comp_tncl = (
            comparison['total_non_current_liabilities']
            if comparison else 0.0
        )
        ca_tncl, va_tncl, vp_tncl = _var(
            self.total_non_current_liabilities, comp_tncl,
        )

        sequence = 250
        lines.append(fields.Command.create({
            'sequence': sequence,
            'name': _('Non-Current Liabilities'),
            'level': 1,
            'is_total': True,
            'is_group': True,
            'section': 'liability',
            'amount': self.total_non_current_liabilities,
            'comparison_amount': ca_tncl,
            'variance_absolute': va_tncl,
            'variance_percentage': vp_tncl,
            'currency_id': self.currency_id.id,
        }))
        lines.extend(add_account_lines(
            non_current_liability_accounts, non_current_liability_balances,
            level=2, sign=-1,
            comp_balances=(
                comparison.get('non_current_liability_balances')
                if comparison else None
            ),
            section='liability',
        ))

        # =====================================================================
        # EQUITY SECTION
        # =====================================================================
        comp_te = comparison['total_equity'] if comparison else 0.0
        ca_te, va_te, vp_te = _var(self.total_equity, comp_te)

        sequence = 300
        lines.append(fields.Command.create({
            'sequence': sequence,
            'name': _('EQUITY'),
            'level': 0,
            'is_total': True,
            'is_group': True,
            'section': 'equity',
            'amount': self.total_equity,
            'comparison_amount': ca_te,
            'variance_absolute': va_te,
            'variance_percentage': vp_te,
            'currency_id': self.currency_id.id,
        }))
        lines.extend(add_account_lines(
            equity_accounts, equity_balances,
            level=1, sign=-1,
            comp_balances=(
                comparison.get('equity_balances') if comparison else None
            ),
            section='equity',
        ))

        # Current Year Earnings line
        comp_cye = (
            comparison['current_year_earnings'] if comparison else 0.0
        )
        ca_cye, va_cye, vp_cye = _var(self.current_year_earnings, comp_cye)

        sequence += 10
        lines.append(fields.Command.create({
            'sequence': sequence,
            'name': _('Current Year Earnings'),
            'level': 1,
            'section': 'equity',
            'amount': self.current_year_earnings,
            'comparison_amount': ca_cye,
            'variance_absolute': va_cye,
            'variance_percentage': vp_cye,
            'currency_id': self.currency_id.id,
        }))

        # =====================================================================
        # TOTAL LIABILITIES AND EQUITY
        # =====================================================================
        total_l_and_e = self.total_liabilities + self.total_equity
        comp_total_l_and_e = (
            (comparison['total_liabilities'] + comparison['total_equity'])
            if comparison else 0.0
        )
        ca_tle, va_tle, vp_tle = _var(total_l_and_e, comp_total_l_and_e)

        sequence = 400
        lines.append(fields.Command.create({
            'sequence': sequence,
            'name': _('TOTAL LIABILITIES AND EQUITY'),
            'level': 0,
            'is_total': True,
            'is_group': True,
            'amount': total_l_and_e,
            'comparison_amount': ca_tle,
            'variance_absolute': va_tle,
            'variance_percentage': vp_tle,
            'currency_id': self.currency_id.id,
        }))

        return lines

    # -------------------------------------------------------------------------
    # XLSX EXPORT CUSTOMISATION
    # -------------------------------------------------------------------------

    def _get_xlsx_columns(self):
        """Return Balance Sheet specific XLSX column definitions.

        Overrides the base-class columns to remove Debit/Credit (not
        applicable to the positional Balance Sheet statement) and provide
        a clean layout with Balance and optional comparison/variance
        columns.

        Returns:
            list[dict]: Column definitions for the XLSX writer.
        """
        cols = [
            {
                'header': _('Account Code'),
                'field': 'code',
                'width': 15,
                'style': 'text',
            },
            {
                'header': _('Account Name'),
                'field': 'name',
                'width': 40,
                'style': 'text',
            },
            {
                'header': _('Balance'),
                'field': 'balance',
                'width': 18,
                'style': 'monetary',
            },
        ]
        if self.enable_comparison:
            cols.extend([
                {
                    'header': _('Prior Period'),
                    'field': 'comparison_amount',
                    'width': 20,
                    'style': 'monetary',
                },
                {
                    'header': _('Change'),
                    'field': 'variance_absolute',
                    'width': 18,
                    'style': 'monetary',
                },
                {
                    'header': _('Change %'),
                    'field': 'variance_percentage',
                    'width': 14,
                    'style': 'percentage',
                },
            ])
        return cols

    # -------------------------------------------------------------------------
    # ACTION METHODS
    # -------------------------------------------------------------------------

    def action_generate_report(self):
        """Generate and display the Balance Sheet report.

        Validates required inputs, triggers report computation, and
        returns an ``ir.actions.act_window`` action that opens the
        report record in an inline form view.

        Returns:
            dict: Window action dict pointing to the computed report.

        Raises:
            UserError: When the As-of Date is not specified.
        """
        self.ensure_one()

        if not self.date_to:
            raise UserError(
                _("Please specify the As-of Date for the Balance Sheet."),
            )

        # Force recomputation and transition state
        self._compute_report_data()
        self.write({'state': 'done'})

        return {
            'name': _('Balance Sheet as of %s') % self.date_to,
            'type': 'ir.actions.act_window',
            'res_model': 'account.balance.sheet.report',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'inline',
        }

    def action_print_pdf(self):
        """Generate PDF version of the Balance Sheet.

        Delegates to the base-class ``action_print_pdf`` which resolves
        the ``ir.actions.report`` XML ID via ``_get_report_xml_id`` and
        triggers QWeb PDF rendering.

        Per FR-007: Export to PDF format.
        Performance target: <15 seconds for 100 000 transactions.

        Returns:
            dict: ``ir.actions.report`` action dict.
        """
        self.ensure_one()
        return super().action_print_pdf()

    def action_export_xlsx(self):
        """Export Balance Sheet to Excel (.xlsx) format.

        Delegates to the base-class ``action_export_xlsx`` which builds
        an in-memory ``openpyxl`` workbook using the column definitions
        from ``_get_xlsx_columns`` and the row data from
        ``_get_xlsx_data``, stores the result as an ``ir.attachment``,
        and returns a download URL action.

        Column layout (controlled by ``_get_xlsx_columns``):
        - Account Code, Account Name, Balance
        - When comparison is enabled: Prior Period, Change, Change %

        Per FR-007: Export to Excel format.
        Performance target: <10 seconds for 100 000 transactions.

        Returns:
            dict: ``ir.actions.act_url`` action pointing to the generated
            XLSX attachment download URL.
        """
        self.ensure_one()
        return super().action_export_xlsx()


class BalanceSheetReportLine(models.TransientModel):
    """Balance Sheet Report Line.

    Represents a single line in the Balance Sheet report, supporting
    hierarchical display with drill-down capability to source journal
    entries.

    Lines are organised into three indentation levels:

    * Level 0 — Section headers (ASSETS, LIABILITIES, EQUITY)
    * Level 1 — Sub-section headers (Current Assets, etc.) and
      special items (Current Year Earnings)
    * Level 2 — Individual account detail lines

    Comparison and variance columns are populated when the parent
    report has ``enable_comparison`` enabled.
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
        string='Amount',
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

    # -----------------------------------------------------------------
    # TEMPLATE-FACING FIELDS
    # QWeb ``balance_sheet_report.xml`` references these names for
    # section filtering, group-vs-detail rendering, drill-down links,
    # and monetary display.  They complement the canonical fields
    # above and are populated by ``_generate_report_lines``.
    # -----------------------------------------------------------------

    section = fields.Selection(
        selection=[
            ('asset', 'Assets'),
            ('liability', 'Liabilities'),
            ('equity', 'Equity'),
        ],
        string='Report Section',
        help="Balance Sheet section this line belongs to.",
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
        """Drill down to source transactions for this report line.

        Opens a filtered list of journal items (``account.move.line``)
        for **all** accounts associated with this line, enabling
        auditors and accountants to verify the reported amount down
        to individual journal entries.

        When the line represents a section header (no ``account_ids``),
        the action is a no-op.

        Per FR-007 Acceptance Criteria:
            "When I click on a line item amount
             Then I am navigated to a filtered view of the underlying
             journal entries"

        Returns:
            dict: ``ir.actions.act_window`` action targeting
            ``account.move.line``, or ``False`` when no accounts are
            linked to this line.
        """
        self.ensure_one()
        if not self.account_ids:
            return False

        # Pass ALL account_ids for multi-account drill-down (e.g. when
        # the line is a sub-section total covering several accounts).
        return self.report_id.action_drilldown(
            account_ids=self.account_ids.ids,
            date_to=self.report_id.date_to,
        )
