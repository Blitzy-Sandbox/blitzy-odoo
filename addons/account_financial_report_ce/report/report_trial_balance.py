# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Trial Balance Report Parser (FR-005)

Provides the full rendering context for the Trial Balance QWeb report
template (``trial_balance_report.xml``).  This parser bridges the
``account.trial.balance.report`` TransientModel data with the QWeb
engine, supplying:

- Pre-computed grand totals for opening, period, and closing column pairs
- Debit/credit equality validation flags with tolerance-aware checks
- Account type hierarchy grouping with subtotals (when ``show_hierarchy``
  is enabled)
- Company / currency context and filter parameter pass-through
- Summary statistics (total accounts, accounts with balance, net position)

All totals leverage the model's pre-computed fields
(``total_opening_debit``, ``total_period_debit``, ``total_debit``, etc.)
to avoid redundant aggregation; only hierarchy grouping and summary
statistics are computed in the parser itself.
"""

from collections import OrderedDict

from odoo import api, models

# Canonical account types as defined in the Odoo 19.0 ``account.account``
# model.  Used for hierarchy grouping in the report output.  The ordering
# follows the standard financial statement presentation sequence.
ACCOUNT_TYPES = [
    'asset_receivable',
    'asset_cash',
    'asset_current',
    'asset_non_current',
    'asset_prepayments',
    'asset_fixed',
    'liability_payable',
    'liability_credit_card',
    'liability_current',
    'liability_non_current',
    'equity',
    'equity_unaffected',
    'income',
    'income_other',
    'expense',
    'expense_depreciation',
    'expense_direct_cost',
    'off_balance',
]

# Tolerance for floating-point balance equality checks (currency units).
# Values within this threshold are treated as balanced.
BALANCE_TOLERANCE = 0.01


class ReportTrialBalance(models.AbstractModel):
    """Trial Balance Report Parser.

    AbstractModel QWeb report parser for
    ``report.account_financial_report_ce.report_trial_balance``.  Prepares
    the full rendering context consumed by the QWeb template, including
    column totals, validation indicators, hierarchy grouping data, and
    summary statistics.
    """

    _name = 'report.account_financial_report_ce.report_trial_balance'
    _description = 'Trial Balance Report Parser'

    # ------------------------------------------------------------------
    # PUBLIC API
    # ------------------------------------------------------------------

    @api.model
    def _get_report_values(self, docids, data=None):
        """Prepare the full data context for the Trial Balance QWeb template.

        Fetches the trial balance report records, reads pre-computed
        column totals, validates debit/credit equality across all column
        pairs, builds optional hierarchy grouping data, and assembles
        summary statistics for the template footer.

        Args:
            docids (list[int]): IDs of ``account.trial.balance.report``
                records to render.  Typically a single-element list from
                the wizard's ``action_print_pdf`` or report action.
            data (dict | None): Extra data dictionary passed from the
                report wizard or ``ir.actions.report`` action.  May
                contain overrides or supplementary context; forwarded
                as-is to the template.

        Returns:
            dict: QWeb rendering context with the following keys:

            **Core keys** (always present):
                ``doc_ids``, ``doc_model``, ``docs``, ``data``

            **Company / currency**:
                ``company`` (``res.company``), ``currency_id``
                (``res.currency``)

            **Column totals** (floats):
                ``total_opening_debit``, ``total_opening_credit``,
                ``total_period_debit``, ``total_period_credit``,
                ``total_closing_debit``, ``total_closing_credit``

            **Validation** (booleans / floats):
                ``is_balanced``, ``opening_difference``,
                ``period_difference``, ``closing_difference``

            **Hierarchy grouping**:
                ``account_types_data`` (``OrderedDict``)

            **Filter / parameter context**:
                ``date_from``, ``date_to``, ``target_move``,
                ``hide_account_at_0``, ``show_hierarchy``,
                ``show_partner_details``

            **Summary statistics** (ints / floats):
                ``total_accounts``, ``accounts_with_balance``,
                ``net_position``
        """
        docs = self.env['account.trial.balance.report'].browse(docids)

        # -- Company and currency context ---------------------------------
        company = docs[0].company_id if docs else self.env.company
        currency_id = company.currency_id

        # -- Grand totals from pre-computed model fields ------------------
        # The model's ``_compute_column_totals`` already aggregates these
        # from the line recordset.  We read them directly from the report
        # record to avoid re-iterating Python-side.
        total_opening_debit = 0.0
        total_opening_credit = 0.0
        total_period_debit = 0.0
        total_period_credit = 0.0
        total_closing_debit = 0.0
        total_closing_credit = 0.0

        if docs:
            doc = docs[0]
            total_opening_debit = doc.total_opening_debit or 0.0
            total_opening_credit = doc.total_opening_credit or 0.0
            total_period_debit = doc.total_period_debit or 0.0
            total_period_credit = doc.total_period_credit or 0.0
            # The model stores closing column totals as ``total_debit``
            # and ``total_credit`` (i.e. the primary "Total Debit" and
            # "Total Credit" fields on the report).
            total_closing_debit = doc.total_debit or 0.0
            total_closing_credit = doc.total_credit or 0.0

        # -- Per-column balance differences --------------------------------
        opening_difference = abs(total_opening_debit - total_opening_credit)
        period_difference = abs(total_period_debit - total_period_credit)
        closing_difference = abs(total_closing_debit - total_closing_credit)

        # Balanced when ALL three column pairs are within tolerance.
        # The model exposes individual ``is_*_balanced`` flags; here we
        # provide a single composite flag for template convenience.
        is_balanced = (
            opening_difference < BALANCE_TOLERANCE
            and period_difference < BALANCE_TOLERANCE
            and closing_difference < BALANCE_TOLERANCE
        )

        # -- Hierarchy grouping data --------------------------------------
        account_types_data = self._build_account_types_data(docs)

        # -- Filter / parameter context -----------------------------------
        date_from = docs[0].date_from if docs else False
        date_to = docs[0].date_to if docs else False
        target_move = docs[0].target_move if docs else 'posted'
        show_hierarchy = docs[0].show_hierarchy if docs else False

        # ``hide_account_at_0`` is derived from the model's
        # ``show_balance_zero`` (inverted logic) and the abstract parent's
        # ``hide_zero_balance`` flag.  When either indicates zero-balance
        # accounts should be excluded, the template receives ``True``.
        hide_account_at_0 = False
        if docs:
            hide_account_at_0 = (
                not docs[0].show_balance_zero
                or getattr(docs[0], 'hide_zero_balance', False)
            )

        # ``show_partner_details`` may not exist on the model yet; use a
        # safe attribute lookup with a ``False`` default so the parser
        # remains forward-compatible when the field is introduced.
        show_partner_details = (
            getattr(docs[0], 'show_partner_details', False)
            if docs else False
        )

        # -- Summary statistics -------------------------------------------
        total_accounts = 0
        accounts_with_balance = 0

        if docs:
            # Exclude group header lines from account counts — they are
            # subtotal rows, not real accounts.
            detail_lines = docs[0].line_ids.filtered(
                lambda line: not line.is_group_line,
            )
            total_accounts = len(detail_lines)
            # An account "has balance" when its closing net position
            # (debit_balance - credit_balance) is non-zero.
            accounts_with_balance = len(detail_lines.filtered(
                lambda line: not currency_id.is_zero(
                    line.debit_balance - line.credit_balance,
                ),
            ))

        net_position = total_closing_debit - total_closing_credit

        return {
            # Core report keys
            'doc_ids': docids,
            'doc_model': 'account.trial.balance.report',
            'docs': docs,
            'data': data,
            # Company / currency
            'company': company,
            'currency_id': currency_id,
            # Column totals
            'total_opening_debit': total_opening_debit,
            'total_opening_credit': total_opening_credit,
            'total_period_debit': total_period_debit,
            'total_period_credit': total_period_credit,
            'total_closing_debit': total_closing_debit,
            'total_closing_credit': total_closing_credit,
            # Validation
            'is_balanced': is_balanced,
            'opening_difference': opening_difference,
            'period_difference': period_difference,
            'closing_difference': closing_difference,
            # Hierarchy grouping
            'account_types_data': account_types_data,
            # Filter / parameter context
            'date_from': date_from,
            'date_to': date_to,
            'target_move': target_move,
            'hide_account_at_0': hide_account_at_0,
            'show_hierarchy': show_hierarchy,
            'show_partner_details': show_partner_details,
            # Summary statistics
            'total_accounts': total_accounts,
            'accounts_with_balance': accounts_with_balance,
            'net_position': net_position,
        }

    # ------------------------------------------------------------------
    # HIERARCHY GROUPING HELPERS
    # ------------------------------------------------------------------

    @api.model
    def _build_account_types_data(self, docs):
        """Build hierarchy grouping data keyed by account type.

        When ``show_hierarchy`` is enabled on the report, this method
        pre-groups detail lines (non-group lines) by their
        ``account_type`` field and computes column subtotals for each
        group.  The result is an :class:`OrderedDict` that preserves the
        canonical account type ordering defined in ``ACCOUNT_TYPES``.

        Each entry contains:

        - ``lines`` — list of line records belonging to this account type
        - ``subtotal_opening_debit`` — sum of ``opening_debit``
        - ``subtotal_opening_credit`` — sum of ``opening_credit``
        - ``subtotal_period_debit`` — sum of period debit (field ``debit``)
        - ``subtotal_period_credit`` — sum of period credit (field ``credit``)
        - ``subtotal_closing_debit`` — sum of closing debit (field
          ``debit_balance``)
        - ``subtotal_closing_credit`` — sum of closing credit (field
          ``credit_balance``)
        - ``label`` — human-readable header label

        Args:
            docs: Browsed ``account.trial.balance.report`` recordset.

        Returns:
            OrderedDict: Mapping *account_type* → group data dict.
                Empty ``OrderedDict`` when *docs* is empty or
                ``show_hierarchy`` is disabled.
        """
        account_types_data = OrderedDict()

        if not docs:
            return account_types_data

        doc = docs[0]
        if not doc.show_hierarchy:
            return account_types_data

        # Filter to detail lines only (exclude group subtotal headers
        # that were already created by the model's hierarchy builder).
        detail_lines = doc.line_ids.filtered(
            lambda line: not line.is_group_line,
        )

        # Partition lines by account_type.
        type_lines_map = {}
        for line in detail_lines:
            acc_type = line.account_type or 'off_balance'
            type_lines_map.setdefault(acc_type, []).append(line)

        # Iterate over canonical type order so the output dict follows
        # the standard financial statement presentation sequence.
        for acc_type in ACCOUNT_TYPES:
            lines_for_type = type_lines_map.get(acc_type)
            if not lines_for_type:
                continue

            subtotal_opening_debit = sum(
                ln.opening_debit for ln in lines_for_type
            )
            subtotal_opening_credit = sum(
                ln.opening_credit for ln in lines_for_type
            )
            subtotal_period_debit = sum(
                ln.debit for ln in lines_for_type
            )
            subtotal_period_credit = sum(
                ln.credit for ln in lines_for_type
            )
            subtotal_closing_debit = sum(
                ln.debit_balance for ln in lines_for_type
            )
            subtotal_closing_credit = sum(
                ln.credit_balance for ln in lines_for_type
            )

            account_types_data[acc_type] = {
                'lines': lines_for_type,
                'subtotal_opening_debit': subtotal_opening_debit,
                'subtotal_opening_credit': subtotal_opening_credit,
                'subtotal_period_debit': subtotal_period_debit,
                'subtotal_period_credit': subtotal_period_credit,
                'subtotal_closing_debit': subtotal_closing_debit,
                'subtotal_closing_credit': subtotal_closing_credit,
                'label': acc_type.replace('_', ' ').title(),
            }

        # Append any non-canonical types that appear in the data but are
        # not listed in ACCOUNT_TYPES (future-proofing).
        for acc_type, lines_for_type in type_lines_map.items():
            if acc_type in account_types_data:
                continue
            account_types_data[acc_type] = {
                'lines': lines_for_type,
                'subtotal_opening_debit': sum(
                    ln.opening_debit for ln in lines_for_type
                ),
                'subtotal_opening_credit': sum(
                    ln.opening_credit for ln in lines_for_type
                ),
                'subtotal_period_debit': sum(
                    ln.debit for ln in lines_for_type
                ),
                'subtotal_period_credit': sum(
                    ln.credit for ln in lines_for_type
                ),
                'subtotal_closing_debit': sum(
                    ln.debit_balance for ln in lines_for_type
                ),
                'subtotal_closing_credit': sum(
                    ln.credit_balance for ln in lines_for_type
                ),
                'label': acc_type.replace('_', ' ').title(),
            }

        return account_types_data
