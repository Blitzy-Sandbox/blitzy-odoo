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

Six-Column Layout:
  Opening Debit | Opening Credit | Period Debit | Period Credit |
  Closing Debit | Closing Credit
Each column pair must balance (sum debits == sum credits).
"""

import logging
from collections import defaultdict

from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command

_logger = logging.getLogger(__name__)

# Display labels for internal account groups used in hierarchy mode.
# Keys correspond to ``account.account.internal_group`` computed values.
INTERNAL_GROUP_LABELS = {
    'asset': 'Assets',
    'liability': 'Liabilities',
    'equity': 'Equity',
    'income': 'Income',
    'expense': 'Expenses',
    'off_balance': 'Off-Balance Sheet',
}

# Sequence offsets that control display ordering of hierarchy groups.
INTERNAL_GROUP_SEQUENCE = {
    'asset': 1000,
    'liability': 2000,
    'equity': 3000,
    'income': 4000,
    'expense': 5000,
    'off_balance': 6000,
}


class TrialBalanceReport(models.TransientModel):
    """Trial Balance Report.

    Generates a trial balance showing all account balances with opening,
    period, and closing debit/credit columns.  Validates the fundamental
    double-entry rule: total debits must equal total credits at every
    column level (opening, period, closing).

    Supports:
    - Optional date range (from/to) for period activity isolation
    - Account group hierarchy with subtotal lines
    - Comparative period analysis with variance computation
    - Display type selection (balance-only, debit/credit, or both)
    - Zero-balance filtering via ``show_balance_zero`` and the parent
      class's ``hide_zero_balance``

    Performance:
        Uses ``read_group`` via ``_compute_account_balance`` for SQL-level
        aggregation, targeting <30 seconds for 100 000 move lines per the
        FR-005 performance requirement.
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
        help="Optional start date to show only period activity.  When "
             "provided, opening balances are computed as of the day "
             "before this date and period columns reflect activity "
             "within [date_from, date_to].",
    )

    show_balance_zero = fields.Boolean(
        string='Show Zero Balances',
        default=False,
        help="Include accounts with zero balance in all column pairs.",
    )

    show_hierarchy = fields.Boolean(
        string='Show Account Groups',
        default=False,
        help="Display accounts grouped by internal group (Assets, "
             "Liabilities, Equity, Income, Expenses) with subtotal lines.",
    )

    show_analytic = fields.Boolean(
        string='Include Analytic',
        default=False,
        help="Show analytic account breakdown.",
    )

    show_partner_details = fields.Boolean(
        string='Show Partner Details',
        default=False,
        help="When enabled, display partner-level breakdown for "
             "receivable and payable accounts.",
    )

    # -----------------------------------------------------------------
    # TEMPLATE-FACING ALIAS FIELDS
    # QWeb ``trial_balance_report.xml`` references ``doc.hide_account_at_0``
    # as an alias of the abstract ``hide_zero_balance`` flag.
    # -----------------------------------------------------------------

    hide_account_at_0 = fields.Boolean(
        related='hide_zero_balance',
        string='Hide Accounts at 0',
        readonly=True,
        help="Alias of 'hide_zero_balance' for QWeb template "
             "compatibility.",
    )

    display_type = fields.Selection(
        selection=[
            ('balance', 'Balance Only'),
            ('debit_credit', 'Debit/Credit Columns'),
            ('both', 'Both'),
        ],
        string='Display Type',
        default='both',
        help="Controls which column sets are visible in the report:\n"
             "- Balance Only: closing debit/credit balance columns\n"
             "- Debit/Credit: period gross debit and credit columns\n"
             "- Both: all column pairs (opening, period, closing)",
    )

    # -------------------------------------------------------------------------
    # COMPUTED REPORT DATA — PRIMARY LINE CONTAINER
    # -------------------------------------------------------------------------

    line_ids = fields.One2many(
        comodel_name='account.trial.balance.report.line',
        inverse_name='report_id',
        string='Account Lines',
    )

    # --- Closing column totals (primary totals) ---

    total_debit = fields.Monetary(
        string='Total Debit',
        currency_field='currency_id',
        help="Sum of closing debit balances across all accounts.",
    )

    total_credit = fields.Monetary(
        string='Total Credit',
        currency_field='currency_id',
        help="Sum of closing credit balances across all accounts.",
    )

    is_balanced = fields.Boolean(
        string='Is Balanced',
        help="True if closing total debits equal closing total credits.",
    )

    difference = fields.Monetary(
        string='Difference',
        currency_field='currency_id',
        help="Difference between closing total debits and credits "
             "(should be 0).",
    )

    # --- Opening column totals ---

    total_opening_debit = fields.Monetary(
        string='Total Opening Debit',
        currency_field='currency_id',
        help="Sum of opening debit balances across all accounts.",
    )

    total_opening_credit = fields.Monetary(
        string='Total Opening Credit',
        currency_field='currency_id',
        help="Sum of opening credit balances across all accounts.",
    )

    is_opening_balanced = fields.Boolean(
        string='Opening Balanced',
        help="True if opening total debits equal opening total credits.",
    )

    # --- Period column totals ---

    total_period_debit = fields.Monetary(
        string='Total Period Debit',
        currency_field='currency_id',
        help="Sum of gross period debits across all accounts.",
    )

    total_period_credit = fields.Monetary(
        string='Total Period Credit',
        currency_field='currency_id',
        help="Sum of gross period credits across all accounts.",
    )

    is_period_balanced = fields.Boolean(
        string='Period Balanced',
        help="True if total period debits equal total period credits.",
    )

    # --- Closing column validation (alias/complement) ---

    is_closing_balanced = fields.Boolean(
        string='Closing Balanced',
        help="Alias for is_balanced; True when closing columns balance.",
    )

    # --- Display helpers ---

    warning_message = fields.Char(
        string='Balance Warning',
        help="Displays a warning when any column pair is out of balance.",
    )

    show_debit_credit_columns = fields.Boolean(
        string='Show Debit/Credit',
        help="True when display_type includes gross debit/credit columns.",
    )

    show_balance_column = fields.Boolean(
        string='Show Balance',
        help="True when display_type includes closing balance columns.",
    )

    # -------------------------------------------------------------------------
    # REPORT COMPUTATION
    # -------------------------------------------------------------------------

    def _compute_report_data(self):
        """Compute full Trial Balance report data with six-column layout.

        For each account, this method computes:

        1. **Opening balances** — net debit/credit positions before
           ``date_from`` (zero when ``date_from`` is not set).
        2. **Period activity** — gross debit and credit totals within
           ``[date_from, date_to]`` (or cumulative to ``date_to``).
        3. **Closing balances** — opening + period net positions.
        4. **Comparison data** — optional prior-period balances with
           variance analysis (FR-005 Scenario 6).
        5. **Hierarchy grouping** — optional internal-group subtotals.

        Column-level validation ensures:

        - Total opening debits == Total opening credits
        - Total period debits == Total period credits
        - Total closing debits == Total closing credits

        Any imbalance triggers a descriptive ``warning_message``.
        """
        for report in self:
            report.currency_id = report.company_id.currency_id

            # Display type flags for view-level column toggling
            report.show_debit_credit_columns = report.display_type in (
                'debit_credit', 'both',
            )
            report.show_balance_column = report.display_type in (
                'balance', 'both',
            )

            # --- Fetch all accounts for this company (Odoo 19.0 Many2many) ---
            accounts = self.env['account.account'].search([
                ('company_ids', 'in', report.company_id.ids),
            ], order='code')

            # --- Compute opening, period, and closing balances ---
            opening_balances, period_balances = (
                report._compute_column_balances(accounts)
            )

            # --- Comparison period (FR-005 Scenario 6) ---
            comparison_balances = {}
            if report.enable_comparison and report.comparison_date_to:
                comparison_balances = report._prepare_comparison_data(
                    accounts,
                )

            # --- Build report lines (flat or hierarchical) ---
            if report.show_hierarchy:
                line_vals_list = report._build_hierarchy_lines(
                    accounts, opening_balances, period_balances,
                    comparison_balances,
                )
            else:
                line_vals_list = report._build_flat_lines(
                    accounts, opening_balances, period_balances,
                    comparison_balances,
                )

            # Persist lines via Command.create for DB persistence
            line_commands = [Command.clear()]
            for vals in line_vals_list:
                line_commands.append(Command.create(vals))
            report.line_ids = line_commands

            # --- Compute column totals from non-group account lines ---
            report._compute_column_totals(line_vals_list)

            # --- Per-column balance validation ---
            report._validate_column_balance()

    # -------------------------------------------------------------------------
    # BALANCE COMPUTATION HELPERS
    # -------------------------------------------------------------------------

    def _compute_column_balances(self, accounts):
        """Compute opening and period balances for every account.

        When ``date_from`` is set, opening balances represent the
        cumulative position up to the day before ``date_from``, and
        period balances represent activity within ``[date_from,
        date_to]``.

        When ``date_from`` is *not* set, opening balances are zero and
        period balances represent the cumulative position up to
        ``date_to``.

        Args:
            accounts: ``account.account`` recordset to aggregate.

        Returns:
            tuple: ``(opening_balances, period_balances)`` — each a dict
            mapping ``account_id`` (int) to
            ``{'debit': float, 'credit': float, 'balance': float}``.
        """
        self.ensure_one()
        if self.date_from:
            # Opening = cumulative up to the day before the period start
            opening_date_to = fields.Date.subtract(self.date_from, days=1)
            opening_balances = self._compute_account_balance(
                accounts, date_to=opening_date_to,
            )
            # Period = activity within [date_from, date_to]
            period_balances = self._compute_account_balance(
                accounts,
                date_from=self.date_from,
                date_to=self.date_to,
            )
        else:
            # No opening period — everything is cumulative to date_to
            opening_balances = {
                acc.id: {'debit': 0.0, 'credit': 0.0, 'balance': 0.0}
                for acc in accounts
            }
            period_balances = self._compute_account_balance(
                accounts, date_to=self.date_to,
            )
        return opening_balances, period_balances

    def _prepare_line_values(self, account, opening_bal, period_bal,
                             comparison_bal=None, level=1,
                             is_group_line=False, sequence=10):
        """Build a single report line values dict from balance data.

        Computes the six-column layout (opening debit/credit, period
        debit/credit, closing debit/credit) and optional comparison /
        variance columns.

        Args:
            account: ``account.account`` record, or ``False`` for group
                header lines.
            opening_bal: Dict with ``debit``, ``credit``, ``balance``.
            period_bal: Dict with ``debit``, ``credit``, ``balance``.
            comparison_bal: Optional comparison period balance dict.
            level: Hierarchy indentation level (0 = group, 1 = detail).
            is_group_line: ``True`` for group subtotal header lines.
            sequence: Sort sequence within the report.

        Returns:
            dict: Field values suitable for ``Command.create()``.
        """
        opening_balance = opening_bal.get('balance', 0.0)
        period_debit = period_bal.get('debit', 0.0)
        period_credit = period_bal.get('credit', 0.0)
        period_balance = period_bal.get('balance', 0.0)
        closing_balance = opening_balance + period_balance

        # Net debit/credit positions for opening column
        opening_debit = opening_balance if opening_balance > 0 else 0.0
        opening_credit = -opening_balance if opening_balance < 0 else 0.0

        # Net debit/credit positions for closing column
        debit_balance = closing_balance if closing_balance > 0 else 0.0
        credit_balance = -closing_balance if closing_balance < 0 else 0.0

        # Core line values (always populated regardless of display_type)
        is_real_account = account and not is_group_line
        acct_code = account.code if is_real_account else ''
        acct_name = (
            account.name if is_real_account
            else (account if isinstance(account, str) else '')
        )
        vals = {
            'account_id': account.id if is_real_account else False,
            'code': acct_code,
            'name': acct_name,
            'account_type': (
                account.account_type if is_real_account else ''
            ),
            'opening_debit': opening_debit,
            'opening_credit': opening_credit,
            'debit': period_debit,
            'credit': period_credit,
            'balance': period_balance,
            'debit_balance': debit_balance,
            'credit_balance': credit_balance,
            'level': level,
            'is_group_line': is_group_line,
            'sequence': sequence,
            'currency_id': self.currency_id.id,
            # Template-facing alias fields
            'account_code': acct_code,
            'account_name': acct_name,
            'period_debit': period_debit,
            'period_credit': period_credit,
            'closing_balance': closing_balance,
        }

        # Comparison and variance (FR-005 Scenario 6)
        if comparison_bal:
            comp_balance = comparison_bal.get('balance', 0.0)
            comp_debit = comp_balance if comp_balance > 0 else 0.0
            comp_credit = -comp_balance if comp_balance < 0 else 0.0
            variance_data = self._compute_variance(
                closing_balance, comp_balance,
            )
            vals.update({
                'comparison_debit': comp_debit,
                'comparison_credit': comp_credit,
                'variance': variance_data['absolute'],
            })

        return vals

    # -------------------------------------------------------------------------
    # LINE BUILDERS
    # -------------------------------------------------------------------------

    def _is_zero_line(self, opening_bal, period_bal):
        """Check whether an account has zero activity across all columns.

        An account is considered "zero" when its opening balance, period
        debits, period credits, and derived closing balance are all zero.

        Args:
            opening_bal: Opening balance dict.
            period_bal: Period balance dict.

        Returns:
            bool: ``True`` if the line would display as all-zeros.
        """
        currency = self.env.company.currency_id
        opening_balance = opening_bal.get('balance', 0.0)
        return (
            currency.is_zero(opening_balance)
            and currency.is_zero(period_bal.get('debit', 0.0))
            and currency.is_zero(period_bal.get('credit', 0.0))
            and currency.is_zero(period_bal.get('balance', 0.0))
        )

    def _should_skip_zero(self, opening_bal, period_bal):
        """Determine whether a zero-balance account should be excluded.

        Accounts are excluded when the line has zero activity *and* either
        the local ``show_balance_zero`` is ``False`` or the parent's
        ``hide_zero_balance`` is ``True``.

        Args:
            opening_bal: Opening balance dict.
            period_bal: Period balance dict.

        Returns:
            bool: ``True`` if the line should be excluded.
        """
        if not self._is_zero_line(opening_bal, period_bal):
            return False
        # Exclude when user explicitly hides zeros via either flag
        if not self.show_balance_zero:
            return True
        return bool(self.hide_zero_balance)

    def _build_flat_lines(self, accounts, opening_balances, period_balances,
                          comparison_balances):
        """Build a flat (non-hierarchical) list of trial balance lines.

        Each account becomes a single line sorted by account code.

        Args:
            accounts: ``account.account`` recordset (pre-sorted by code).
            opening_balances: Dict mapping account_id → opening balance dict.
            period_balances: Dict mapping account_id → period balance dict.
            comparison_balances: Dict mapping account_id → comparison balance
                dict (empty when comparison is disabled).

        Returns:
            list[dict]: Line value dicts suitable for ``Command.create()``.
        """
        lines = []
        sequence = 0
        zero_bal = {'debit': 0.0, 'credit': 0.0, 'balance': 0.0}

        for account in accounts:
            opening_bal = opening_balances.get(account.id, zero_bal)
            period_bal = period_balances.get(account.id, zero_bal)

            if self._should_skip_zero(opening_bal, period_bal):
                continue

            sequence += 10
            comp_bal = comparison_balances.get(account.id)
            lines.append(self._prepare_line_values(
                account, opening_bal, period_bal,
                comparison_bal=comp_bal,
                level=1, sequence=sequence,
            ))
        return lines

    def _build_hierarchy_lines(self, accounts, opening_balances,
                               period_balances, comparison_balances):
        """Build hierarchical trial balance lines grouped by internal group.

        Accounts are grouped by their ``internal_group`` classification
        (asset, liability, equity, income, expense, off_balance).  Each
        group receives a header/subtotal line at level 0, with individual
        account lines nested at level 1.

        Args:
            accounts: ``account.account`` recordset (pre-sorted by code).
            opening_balances: Dict mapping account_id → opening balance dict.
            period_balances: Dict mapping account_id → period balance dict.
            comparison_balances: Dict mapping account_id → comparison balance
                dict (empty when comparison is disabled).

        Returns:
            list[dict]: Line value dicts ordered by group sequence then
            account code, suitable for ``Command.create()``.
        """
        zero_bal = {'debit': 0.0, 'credit': 0.0, 'balance': 0.0}

        # Partition accounts by internal_group
        groups = defaultdict(lambda: self.env['account.account'])
        for account in accounts:
            group_key = account.internal_group or 'off_balance'
            groups[group_key] |= account

        lines = []
        sorted_groups = sorted(
            groups.keys(),
            key=lambda g: INTERNAL_GROUP_SEQUENCE.get(g, 9999),
        )

        for group_key in sorted_groups:
            group_accounts = groups[group_key]
            group_sequence = INTERNAL_GROUP_SEQUENCE.get(group_key, 9999)
            group_label = INTERNAL_GROUP_LABELS.get(
                group_key, group_key.replace('_', ' ').title(),
            )

            # Accumulate group subtotals
            group_opening = {'debit': 0.0, 'credit': 0.0, 'balance': 0.0}
            group_period = {'debit': 0.0, 'credit': 0.0, 'balance': 0.0}
            group_comparison = {'debit': 0.0, 'credit': 0.0, 'balance': 0.0}
            account_lines = []
            seq = group_sequence

            for account in group_accounts.sorted(key=lambda a: a.code):
                opening_bal = opening_balances.get(account.id, zero_bal)
                period_bal = period_balances.get(account.id, zero_bal)

                if self._should_skip_zero(opening_bal, period_bal):
                    continue

                seq += 1
                comp_bal = comparison_balances.get(account.id)

                account_lines.append(self._prepare_line_values(
                    account, opening_bal, period_bal,
                    comparison_bal=comp_bal,
                    level=1, sequence=seq,
                ))

                # Accumulate group totals
                for key in ('debit', 'credit', 'balance'):
                    group_opening[key] += opening_bal.get(key, 0.0)
                    group_period[key] += period_bal.get(key, 0.0)
                    if comp_bal:
                        group_comparison[key] += comp_bal.get(key, 0.0)

            # Skip group entirely if no visible accounts
            if not account_lines:
                continue

            # Group header line (level 0, subtotal)
            group_comp = group_comparison if comparison_balances else None
            header_vals = self._prepare_line_values(
                group_label,  # passed as name string
                group_opening, group_period,
                comparison_bal=group_comp,
                level=0, is_group_line=True, sequence=group_sequence,
            )
            lines.append(header_vals)
            lines.extend(account_lines)

        return lines

    # -------------------------------------------------------------------------
    # TOTALS AND VALIDATION
    # -------------------------------------------------------------------------

    def _compute_column_totals(self, line_vals_list):
        """Compute per-column totals from account lines.

        Group header lines (``is_group_line=True``) are excluded from
        totals to prevent double-counting.

        Args:
            line_vals_list: List of line value dicts produced by
                ``_build_flat_lines`` or ``_build_hierarchy_lines``.
        """
        self.ensure_one()
        totals = {
            'opening_debit': 0.0,
            'opening_credit': 0.0,
            'period_debit': 0.0,
            'period_credit': 0.0,
            'closing_debit': 0.0,
            'closing_credit': 0.0,
        }
        for vals in line_vals_list:
            if vals.get('is_group_line'):
                continue
            totals['opening_debit'] += vals.get('opening_debit', 0.0)
            totals['opening_credit'] += vals.get('opening_credit', 0.0)
            totals['period_debit'] += vals.get('debit', 0.0)
            totals['period_credit'] += vals.get('credit', 0.0)
            totals['closing_debit'] += vals.get('debit_balance', 0.0)
            totals['closing_credit'] += vals.get('credit_balance', 0.0)

        self.total_opening_debit = totals['opening_debit']
        self.total_opening_credit = totals['opening_credit']
        self.total_period_debit = totals['period_debit']
        self.total_period_credit = totals['period_credit']
        self.total_debit = totals['closing_debit']
        self.total_credit = totals['closing_credit']
        self.difference = round(self.total_debit - self.total_credit, 2)
        self.is_balanced = self.difference == 0

    def _validate_column_balance(self):
        """Validate that each column pair balances and build warning text.

        Checks three column pairs independently:

        1. Opening debits vs. opening credits
        2. Period debits vs. period credits
        3. Closing debits vs. closing credits

        Sets per-column ``is_*_balanced`` flags and a human-readable
        ``warning_message`` when any imbalance is detected.
        """
        self.ensure_one()
        opening_diff = round(
            self.total_opening_debit - self.total_opening_credit, 2,
        )
        period_diff = round(
            self.total_period_debit - self.total_period_credit, 2,
        )
        closing_diff = round(
            self.total_debit - self.total_credit, 2,
        )

        self.is_opening_balanced = opening_diff == 0
        self.is_period_balanced = period_diff == 0
        self.is_closing_balanced = closing_diff == 0

        warnings = []
        if not self.is_opening_balanced:
            warnings.append(
                _("Opening columns out of balance by %(diff)s",
                  diff=opening_diff),
            )
        if not self.is_period_balanced:
            warnings.append(
                _("Period columns out of balance by %(diff)s",
                  diff=period_diff),
            )
        if not self.is_closing_balanced:
            warnings.append(
                _("Closing columns out of balance by %(diff)s",
                  diff=closing_diff),
            )

        self.warning_message = '; '.join(warnings) if warnings else False

        if warnings:
            _logger.warning(
                "Trial Balance %s: %s", self.id, self.warning_message,
            )

    # -------------------------------------------------------------------------
    # XLSX EXPORT OVERRIDES
    # -------------------------------------------------------------------------

    def _get_xlsx_columns(self):
        """Return column definitions for Trial Balance XLSX export.

        Provides the six-column layout (opening, period, closing) plus
        optional comparison/variance columns.  Column visibility follows
        the ``display_type`` selection.

        Returns:
            list[dict]: Column definitions with ``header``, ``field``,
            ``width``, and ``style`` keys.
        """
        cols = [
            {'header': _('Code'), 'field': 'code', 'width': 12,
             'style': 'text'},
            {'header': _('Account Name'), 'field': 'name', 'width': 40,
             'style': 'text'},
        ]

        if self.display_type in ('both',):
            cols.extend([
                {'header': _('Opening Debit'), 'field': 'opening_debit',
                 'width': 18, 'style': 'monetary'},
                {'header': _('Opening Credit'), 'field': 'opening_credit',
                 'width': 18, 'style': 'monetary'},
            ])

        if self.display_type in ('debit_credit', 'both'):
            cols.extend([
                {'header': _('Period Debit'), 'field': 'debit',
                 'width': 18, 'style': 'monetary'},
                {'header': _('Period Credit'), 'field': 'credit',
                 'width': 18, 'style': 'monetary'},
            ])

        if self.display_type in ('balance', 'both'):
            cols.extend([
                {'header': _('Closing Debit'), 'field': 'debit_balance',
                 'width': 18, 'style': 'monetary'},
                {'header': _('Closing Credit'), 'field': 'credit_balance',
                 'width': 18, 'style': 'monetary'},
            ])

        if self.enable_comparison:
            cols.extend([
                {'header': _('Comp. Debit'), 'field': 'comparison_debit',
                 'width': 18, 'style': 'monetary'},
                {'header': _('Comp. Credit'), 'field': 'comparison_credit',
                 'width': 18, 'style': 'monetary'},
                {'header': _('Variance'), 'field': 'variance',
                 'width': 18, 'style': 'monetary'},
            ])

        return cols

    def _get_xlsx_data(self):
        """Return data rows for Trial Balance XLSX export.

        Iterates over ``line_ids`` and maps each line to a dict whose
        keys match the ``field`` values returned by
        :meth:`_get_xlsx_columns`.

        Returns:
            list[dict]: Data rows for the spreadsheet.
        """
        rows = []
        for line in self.line_ids:
            row = {
                'code': line.code or '',
                'name': line.name or '',
                'opening_debit': line.opening_debit or 0.0,
                'opening_credit': line.opening_credit or 0.0,
                'debit': line.debit or 0.0,
                'credit': line.credit or 0.0,
                'debit_balance': line.debit_balance or 0.0,
                'credit_balance': line.credit_balance or 0.0,
                'level': line.level or 0,
                'is_total': line.is_group_line,
            }
            if self.enable_comparison:
                row.update({
                    'comparison_debit': line.comparison_debit or 0.0,
                    'comparison_credit': line.comparison_credit or 0.0,
                    'variance': line.variance or 0.0,
                })
            rows.append(row)
        return rows

    # -------------------------------------------------------------------------
    # ACTIONS
    # -------------------------------------------------------------------------

    def action_generate_report(self):
        """Generate and display the Trial Balance report.

        Validates the required ``date_to`` field, triggers the report
        computation, and returns a window action displaying the generated
        report inline.

        Returns:
            dict: ``ir.actions.act_window`` action pointing to this
            report record in form view.

        Raises:
            UserError: When ``date_to`` is not specified.
            UserError: When ``date_from`` is set but is after ``date_to``.
        """
        self.ensure_one()
        if not self.date_to:
            raise UserError(_("Please specify the As of Date."))
        if self.date_from and self.date_from > self.date_to:
            raise UserError(
                _("The From Date must be before the As of Date."),
            )

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
    """Trial Balance Report Line.

    Represents a single row in the trial balance, which may be either a
    concrete account line (``is_group_line=False``) or a group subtotal
    header (``is_group_line=True``).

    The six-column layout fields are:

    - ``opening_debit`` / ``opening_credit`` — net position before the
      reporting period.
    - ``debit`` / ``credit`` — gross period activity.
    - ``debit_balance`` / ``credit_balance`` — net closing position
      (opening + period).

    Optional comparison columns:

    - ``comparison_debit`` / ``comparison_credit`` — prior period net
      position.
    - ``variance`` — absolute difference between current closing and
      comparison closing balances.
    """
    _name = 'account.trial.balance.report.line'
    _description = 'Trial Balance Report Line'
    _order = 'sequence, code'

    report_id = fields.Many2one(
        comodel_name='account.trial.balance.report',
        string='Report',
        ondelete='cascade',
    )
    account_id = fields.Many2one('account.account', string='Account')
    code = fields.Char(string='Code')
    name = fields.Char(string='Account Name')
    account_type = fields.Char(string='Type')

    # --- Opening column (net debit/credit positions before date_from) ---
    opening_debit = fields.Monetary(
        string='Opening Debit',
        currency_field='currency_id',
        help="Debit balance as of the day before the period start.  "
             "Positive when the account has a net debit position.",
    )
    opening_credit = fields.Monetary(
        string='Opening Credit',
        currency_field='currency_id',
        help="Credit balance as of the day before the period start.  "
             "Positive when the account has a net credit position.",
    )

    # --- Period column (gross debit/credit totals) ---
    debit = fields.Monetary(
        string='Period Debit',
        currency_field='currency_id',
        help="Sum of all debit entries posted within the reporting period.",
    )
    credit = fields.Monetary(
        string='Period Credit',
        currency_field='currency_id',
        help="Sum of all credit entries posted within the reporting period.",
    )
    balance = fields.Monetary(
        string='Net Balance',
        currency_field='currency_id',
        help="Period net balance (debit − credit).",
    )

    # --- Closing column (net debit/credit balance = opening + period) ---
    debit_balance = fields.Monetary(
        string='Closing Debit',
        currency_field='currency_id',
        help="Closing debit balance (opening + period).  Positive when "
             "the account closes with a net debit position.",
    )
    credit_balance = fields.Monetary(
        string='Closing Credit',
        currency_field='currency_id',
        help="Closing credit balance (opening + period).  Positive when "
             "the account closes with a net credit position.",
    )

    # --- Comparison columns ---
    comparison_debit = fields.Monetary(
        string='Prior Debit',
        currency_field='currency_id',
        help="Comparison period net debit balance.",
    )
    comparison_credit = fields.Monetary(
        string='Prior Credit',
        currency_field='currency_id',
        help="Comparison period net credit balance.",
    )
    variance = fields.Monetary(
        string='Variance',
        currency_field='currency_id',
        help="Absolute variance: current closing − comparison closing.",
    )

    # --- Hierarchy / display fields ---
    level = fields.Integer(
        string='Level',
        default=1,
        help="Hierarchy indentation level (0 = group header, 1 = detail).",
    )
    is_group_line = fields.Boolean(
        string='Is Group Line',
        default=False,
        help="True for group subtotal header lines.",
    )
    sequence = fields.Integer(
        string='Sequence',
        default=10,
        help="Sort order within the report.",
    )

    currency_id = fields.Many2one('res.currency', string='Currency')

    # -----------------------------------------------------------------
    # TEMPLATE-FACING FIELDS
    # QWeb ``trial_balance_report.xml`` references these names.
    # They are aliases / computed values populated by
    # ``_prepare_line_values``.
    # -----------------------------------------------------------------

    account_code = fields.Char(
        string='Account Code',
        help="Alias of 'code' for QWeb template compatibility.",
    )

    account_name = fields.Char(
        string='Account Name (Template)',
        help="Alias of 'name' for QWeb template compatibility.",
    )

    period_debit = fields.Monetary(
        string='Period Debit (Template)',
        currency_field='currency_id',
        help="Alias of 'debit' for QWeb template compatibility.",
    )

    period_credit = fields.Monetary(
        string='Period Credit (Template)',
        currency_field='currency_id',
        help="Alias of 'credit' for QWeb template compatibility.",
    )

    closing_balance = fields.Monetary(
        string='Closing Balance',
        currency_field='currency_id',
        help="Net closing balance (opening + period). Positive = net "
             "debit, negative = net credit.",
    )

    def action_drilldown(self):
        """Drill down to journal items underlying this trial balance line.

        Opens a filtered list view of ``account.move.line`` records for
        the account in this line, scoped to the report's date range.
        Group header lines (``is_group_line=True``) are not drillable.

        Returns:
            dict: ``ir.actions.act_window`` action, or ``False`` when
            the line is a group header with no specific account.
        """
        self.ensure_one()
        if not self.account_id:
            return False
        return self.report_id.action_drilldown(
            account_id=self.account_id.id,
            date_from=self.report_id.date_from,
            date_to=self.report_id.date_to,
        )
