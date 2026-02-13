# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Cash Flow Statement Report Parser (FR-003)

Provides data formatting and pre-computation for the Cash Flow Statement
QWeb report template (``cash_flow_report.xml``).  Extracts activity section
totals, opening/closing cash balances, net change reconciliation, indirect
method reconciliation from Net Income, cash flow verification status,
comparison period data, and company/currency context from the
``account.cash.flow.report`` transient model.

This parser bridges the ``account.cash.flow.report`` model and the
``report_cash_flow`` QWeb template, supplying both the ``docs`` recordset
(for direct ``doc.field`` access in the template) and pre-computed
convenience variables that simplify template expressions and support
alternative export formats (XLSX, programmatic consumption).

Template integration:
    The QWeb template accesses most financial data through ``doc.field``
    notation (model record fields).  The parser's top-level convenience
    keys (``total_operating``, ``beginning_cash``, etc.) are available for
    direct use in the template context or by external consumers that
    render the report data outside QWeb.
"""

from odoo import api, models


class ReportCashFlow(models.AbstractModel):
    """Cash Flow Statement Report Parser.

    Prepares all data required by the ``cash_flow_report.xml`` QWeb
    template for rendering Cash Flow Statements in PDF format.

    Pre-computes:
    - Activity section totals (Operating, Investing, Financing).
    - Opening / closing cash balances and net change in cash.
    - Net income starting point for the indirect method.
    - Cash flow verification / reconciliation status.
    - Comparison period flag.
    - Company and currency context for monetary formatting.
    """

    _name = 'report.account_financial_report_ce.report_cash_flow'
    _description = 'Cash Flow Report Parser'

    # ------------------------------------------------------------------
    # PRIVATE HELPERS
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_monetary(record, *field_names, default=0.0):
        """Retrieve the first available monetary field value from *record*.

        Iterates over *field_names* in order and returns the value of the
        first field that exists on the record.  This allows forward- and
        backward-compatible access when field names may differ between
        model revisions (e.g. ``cash_from_operating`` vs.
        ``total_operating``).

        Args:
            record: An Odoo record (may be ``None`` or an empty
                recordset).
            *field_names: One or more field names to try, in priority
                order.
            default: Value returned when *record* is falsy or none of
                the field names exist on the model.

        Returns:
            ``float`` — The monetary value from the first matching field,
            or *default* if no field is found.
        """
        if not record:
            return default
        for name in field_names:
            try:
                value = getattr(record, name, None)
            except Exception:
                # Protect against edge-case attribute access errors on
                # new-mode or partial records.
                continue
            if value is not None:
                return value
        return default

    # ------------------------------------------------------------------
    # REPORT VALUES
    # ------------------------------------------------------------------

    @api.model
    def _get_report_values(self, docids, data=None):
        """Prepare data for the Cash Flow Statement report template.

        Loads the ``account.cash.flow.report`` transient records identified
        by *docids*, extracts pre-computed activity totals, cash balances,
        net income, verification status, and comparison flags, then returns
        a dictionary consumed by the QWeb template.

        The first record in *docs* is used to populate the top-level
        convenience variables (most reports produce a single document).
        The full ``docs`` recordset is also included so the template can
        iterate when multiple reports are printed at once.

        Args:
            docids: List of ``account.cash.flow.report`` record IDs.
            data: Optional extra data dict passed from the report wizard
                or ``ir.actions.report`` action.

        Returns:
            ``dict`` with the following keys:

            ========================  =======================================
            Key                       Description
            ========================  =======================================
            ``doc_ids``               Original record IDs.
            ``doc_model``             ``'account.cash.flow.report'``.
            ``docs``                  Recordset of report records.
            ``data``                  Passthrough wizard data.
            ``company``               ``res.company`` for report header.
            ``currency_id``           ``res.currency`` for formatting.
            ``method``                ``'indirect'`` or ``'direct'``.
            ``has_comparison``        Whether a comparison period is active.
            ``net_income``            Starting point for indirect method.
            ``total_operating``       Net cash from operating activities.
            ``total_investing``       Net cash from investing activities.
            ``total_financing``       Net cash from financing activities.
            ``net_change_in_cash``    Sum of the three activity totals.
            ``beginning_cash``        Cash at period start.
            ``ending_cash``           Cash at period end.
            ``is_reconciled``         ``True`` when beginning + net change
                                      equals ending cash (within rounding).
            ========================  =======================================
        """
        docs = self.env['account.cash.flow.report'].browse(docids)

        # First document supplies the convenience variables.  When the
        # recordset is empty every value falls back to a safe default.
        doc = docs[:1]  # singleton or empty recordset
        has_doc = bool(doc)

        # -- Company & currency context (section 7) -----------------------
        company = doc.company_id if has_doc else self.env.company
        currency_id = company.currency_id

        # -- Cash flow method (section 4) ----------------------------------
        method = doc.method if has_doc else 'indirect'

        # -- Net income — indirect method starting point (section 4) -------
        net_income = doc.net_income if has_doc else 0.0

        # -- Activity section totals (section 1) ---------------------------
        # The model exposes ``cash_from_operating / investing / financing``.
        # We also probe ``total_operating`` etc. for forward compatibility
        # with possible alias fields.
        total_operating = self._safe_monetary(
            doc, 'total_operating', 'cash_from_operating',
        )
        total_investing = self._safe_monetary(
            doc, 'total_investing', 'cash_from_investing',
        )
        total_financing = self._safe_monetary(
            doc, 'total_financing', 'cash_from_financing',
        )

        # -- Net change in cash (section 3) --------------------------------
        net_change_in_cash = doc.net_change_in_cash if has_doc else 0.0

        # -- Opening / closing cash balances (section 2) -------------------
        # ``beginning_cash`` / ``ending_cash`` are related-field aliases for
        # ``opening_cash`` / ``closing_cash`` on the CashFlowReport model.
        # We try both names for robustness.
        beginning_cash = self._safe_monetary(
            doc, 'beginning_cash', 'opening_cash',
        )
        ending_cash = self._safe_monetary(
            doc, 'ending_cash', 'closing_cash',
        )

        # -- Cash flow verification (section 5) ----------------------------
        is_reconciled = doc.is_reconciled if has_doc else True

        # -- Comparison data (section 6) -----------------------------------
        # The abstract base uses ``enable_comparison``; some versions may
        # expose ``compare_period`` — try both.
        has_comparison = bool(
            has_doc
            and (
                getattr(doc, 'compare_period', False)
                or getattr(doc, 'enable_comparison', False)
            )
        )

        return {
            'doc_ids': docids,
            'doc_model': 'account.cash.flow.report',
            'docs': docs,
            'data': data,
            'company': company,
            'currency_id': currency_id,
            'method': method,
            'has_comparison': has_comparison,
            'net_income': net_income,
            'total_operating': total_operating,
            'total_investing': total_investing,
            'total_financing': total_financing,
            'net_change_in_cash': net_change_in_cash,
            'beginning_cash': beginning_cash,
            'ending_cash': ending_cash,
            'is_reconciled': is_reconciled,
        }
