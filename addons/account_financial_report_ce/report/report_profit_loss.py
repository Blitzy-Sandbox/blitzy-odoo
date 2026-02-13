# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Profit & Loss Report Parser (FR-002)

Provides data formatting and context enrichment for the Profit & Loss
QWeb report template (profit_loss_report.xml). Extracts section subtotals,
date-range context, comparison period metadata, company/currency details,
and margin percentages from the ProfitLossReport transient model so that
the QWeb template receives a complete, pre-computed rendering context.
"""

from odoo import api, models


class ReportProfitLoss(models.AbstractModel):
    """Profit & Loss Report Parser.

    Bridges the ``account.profit.loss.report`` transient model to its
    QWeb report template by constructing a rich rendering context that
    includes:

    * Income / expense breakdown with section subtotals
    * Gross profit, operating income, and net income figures
    * Date-range and target-move metadata for the report header
    * Comparison-period flag and dates
    * Company and currency references
    * Pre-computed margin percentages (gross, operating, net)
    """

    _name = 'report.account_financial_report_ce.report_profit_loss'
    _description = 'Profit & Loss Report Parser'

    # ------------------------------------------------------------------
    # Report value preparation
    # ------------------------------------------------------------------

    @api.model
    def _get_report_values(self, docids, data=None):
        """Prepare the full data structure for the P&L QWeb template.

        The method reads computed fields that the
        ``ProfitLossReport._compute_report_data`` method has already
        populated (total_revenue, total_cogs, gross_profit, etc.) and
        exposes them as top-level template context keys.  This avoids
        duplicating aggregation logic inside the QWeb template and
        guarantees consistency between model-computed values and what
        the template renders.

        Args:
            docids: List of ``account.profit.loss.report`` record IDs
                to include in the report output.
            data: Optional dictionary of additional data passed from the
                report wizard or action context.

        Returns:
            Dictionary consumed by the QWeb template with the following
            notable keys beyond the standard ``doc_ids`` / ``docs``:

            * ``company`` / ``currency_id`` – reporting entity context
            * ``has_comparison`` – boolean flag for comparative columns
            * ``total_revenue`` … ``net_income`` – section subtotals
            * ``gross_margin`` … ``net_margin`` – percentage margins
        """
        docs = self.env['account.profit.loss.report'].browse(docids)

        # ----- Reference document (first record) for scalar values ----
        doc = docs[0] if docs else None

        # ----- Company and currency context (point 5) -----------------
        company = doc.company_id if doc else self.env.company
        currency_id = company.currency_id

        # ----- Date range context (point 3) ---------------------------
        date_from = doc.date_from if doc else False
        date_to = doc.date_to if doc else False
        target_move = doc.target_move if doc else 'posted'

        # ----- Comparison data (point 4) ------------------------------
        # The abstract base model stores the comparison flag as
        # ``enable_comparison`` and the dates as ``comparison_date_from``
        # / ``comparison_date_to``.  We expose them under both the model
        # field names and the shorter aliases expected by the template.
        has_comparison = bool(doc and doc.enable_comparison)
        compare_date_from = doc.comparison_date_from if doc else False
        compare_date_to = doc.comparison_date_to if doc else False

        # ----- Income / expense section subtotals (point 1) -----------
        # These values originate from the transient model's
        # ``_compute_report_data`` method which performs read_group
        # aggregation against account.move.line.
        total_revenue = doc.total_revenue if doc else 0.0
        total_cogs = doc.total_cogs if doc else 0.0
        gross_profit = doc.gross_profit if doc else 0.0
        total_operating_expenses = doc.total_operating_expenses if doc else 0.0
        operating_income = doc.operating_income if doc else 0.0

        # ``total_other`` is the net of other income minus other
        # expenses.  The model stores these as two separate computed
        # fields; we combine them for the template's convenience.
        total_other_income = doc.total_other_income if doc else 0.0
        total_other_expenses = doc.total_other_expenses if doc else 0.0
        total_other = total_other_income - total_other_expenses

        net_income = doc.net_income if doc else 0.0

        # ----- Margin percentages (point 6) ---------------------------
        # Pre-computed here so the template does not need to guard
        # against division-by-zero independently.
        if total_revenue:
            gross_margin = (gross_profit / total_revenue) * 100.0
            operating_margin = (operating_income / total_revenue) * 100.0
            net_margin = (net_income / total_revenue) * 100.0
        else:
            gross_margin = 0.0
            operating_margin = 0.0
            net_margin = 0.0

        # ----- Assemble the template rendering context ----------------
        return {
            # Standard report keys
            'doc_ids': docids,
            'doc_model': 'account.profit.loss.report',
            'docs': docs,
            'data': data,
            # Company and currency context
            'company': company,
            'currency_id': currency_id,
            # Date range metadata for report header
            'date_from': date_from,
            'date_to': date_to,
            'target_move': target_move,
            # Comparison period support
            'has_comparison': has_comparison,
            'compare_date_from': compare_date_from,
            'compare_date_to': compare_date_to,
            # Section subtotals (pre-computed by model)
            'total_revenue': total_revenue,
            'total_cogs': total_cogs,
            'gross_profit': gross_profit,
            'total_operating_expenses': total_operating_expenses,
            'operating_income': operating_income,
            'total_other': total_other,
            'net_income': net_income,
            # Margin analysis percentages
            'gross_margin': gross_margin,
            'operating_margin': operating_margin,
            'net_margin': net_margin,
        }
