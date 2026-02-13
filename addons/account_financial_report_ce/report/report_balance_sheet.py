# -*- coding: utf-8 -*-
# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Balance Sheet Report Parser

Provides comprehensive data formatting and context preparation for the
Balance Sheet QWeb report template (balance_sheet_report.xml).

Per FR-001 (Balance Sheet Report) and the Agent Action Plan:
- Supplies pre-grouped line collections by section (Assets, Liabilities, Equity)
- Provides company currency context for monetary formatting
- Passes comparison period metadata for conditional template rendering
- Includes accounting equation validation status (Assets = Liabilities + Equity)
- Delivers section totals and report parameter context for header display
"""

from odoo import api, fields, models


class ReportBalanceSheet(models.AbstractModel):
    """Balance Sheet Report Parser."""
    _name = 'report.account_financial_report_ce.report_balance_sheet'
    _description = 'Balance Sheet Report Parser'

    @api.model
    def _get_report_values(self, docids, data=None):
        """
        Prepare comprehensive data for the Balance Sheet report template.

        Enhances the minimal stub context with a rich data dictionary that
        the QWeb template ``balance_sheet_report.xml`` can consume for
        rendering a GAAP/IFRS-compliant Balance Sheet.

        The returned context includes:

        1. **Core report references** — ``doc_ids``, ``doc_model``, ``docs``,
           and the original ``data`` dict from the wizard.
        2. **Pre-grouped line collections** — ``asset_lines``,
           ``liability_lines``, ``equity_lines`` filtered from
           ``doc.line_ids`` by section field, enabling the parser to supply
           pre-computed summaries alongside template-side filtering.
        3. **Company currency context** — ``company`` and ``currency_id`` for
           ``format_amount`` helpers and report header rendering.
        4. **Comparison period metadata** — ``has_comparison``,
           ``compare_date_from``, ``compare_date_to`` derived from the
           report model's comparison fields, controlling conditional column
           rendering in the template.
        5. **Equation validation** — ``is_balanced`` and
           ``balance_difference`` from the BalanceSheetReport model's
           ``_validate_accounting_equation`` computation, powering the
           verification badge in the template footer.
        6. **Section totals** — ``total_assets``, ``total_liabilities``,
           ``total_equity`` directly from the computed model fields.
        7. **Report parameter helpers** — ``report_date`` (with
           ``fields.Date.today()`` fallback), ``date_from``, and
           ``target_move`` for the report header "As of" label and
           parameter display.

        Args:
            docids: List of ``account.balance.sheet.report`` record IDs
                to render.
            data: Optional additional data dict passed from the report
                wizard action.

        Returns:
            dict: Template context consumed by ``balance_sheet_report.xml``.
        """
        docs = self.env['account.balance.sheet.report'].browse(docids)

        # ---------------------------------------------------------------------
        # Company and currency context for number formatting and header
        # ---------------------------------------------------------------------
        company = docs[0].company_id if docs else self.env.company
        currency_id = company.currency_id

        # ---------------------------------------------------------------------
        # Pre-group line_ids by section (Assets / Liabilities / Equity)
        # The QWeb template performs its own filtering on doc.line_ids, but
        # pre-grouped collections allow the parser to provide optimised
        # access and enable additional server-side summary computation.
        # ---------------------------------------------------------------------
        ReportLine = self.env['account.balance.sheet.report.line']
        if docs:
            first_doc = docs[0]
            asset_lines = first_doc.line_ids.filtered(
                lambda l: l.section == 'asset'
            )
            liability_lines = first_doc.line_ids.filtered(
                lambda l: l.section == 'liability'
            )
            equity_lines = first_doc.line_ids.filtered(
                lambda l: l.section == 'equity'
            )
        else:
            asset_lines = ReportLine
            liability_lines = ReportLine
            equity_lines = ReportLine

        # ---------------------------------------------------------------------
        # Comparison period metadata for conditional column rendering
        # The report model may expose the comparison flag as either
        # 'compare_period' (updated naming) or 'enable_comparison'
        # (abstract base naming).  Resolve both for forward-compatibility.
        # ---------------------------------------------------------------------
        has_comparison = False
        compare_date_from = False
        compare_date_to = False
        if docs:
            has_comparison = bool(
                getattr(docs[0], 'compare_period', False)
                or getattr(docs[0], 'enable_comparison', False)
            )
            if has_comparison:
                # Comparison date range — resolve updated or abstract names
                compare_date_from = getattr(
                    docs[0], 'compare_date_from',
                    getattr(docs[0], 'comparison_date_from', False),
                )
                compare_date_to = getattr(
                    docs[0], 'compare_date_to',
                    getattr(docs[0], 'comparison_date_to', False),
                )

        # ---------------------------------------------------------------------
        # Equation validation status (Assets = Liabilities + Equity)
        # Sourced from the BalanceSheetReport model's
        # _validate_accounting_equation computation.
        # ---------------------------------------------------------------------
        is_balanced = docs[0].is_balanced if docs else True
        balance_difference = docs[0].balance_difference if docs else 0.0

        # ---------------------------------------------------------------------
        # Section totals from the computed report model fields
        # ---------------------------------------------------------------------
        total_assets = docs[0].total_assets if docs else 0.0
        total_liabilities = docs[0].total_liabilities if docs else 0.0
        total_equity = docs[0].total_equity if docs else 0.0

        # ---------------------------------------------------------------------
        # Report parameter helpers for header / "As of" display
        # fields.Date.today() provides a safe fallback when docs is empty,
        # ensuring the template always has a valid date for rendering.
        # ---------------------------------------------------------------------
        report_date = docs[0].date_to if docs else fields.Date.today()
        date_from = docs[0].date_from if docs else False
        target_move = docs[0].target_move if docs else 'posted'

        return {
            # Core report references
            'doc_ids': docids,
            'doc_model': 'account.balance.sheet.report',
            'docs': docs,
            'data': data,
            # Company and currency context
            'company': company,
            'currency_id': currency_id,
            # Pre-grouped line collections
            'asset_lines': asset_lines,
            'liability_lines': liability_lines,
            'equity_lines': equity_lines,
            # Comparison period metadata
            'has_comparison': has_comparison,
            'compare_date_from': compare_date_from,
            'compare_date_to': compare_date_to,
            # Equation validation
            'is_balanced': is_balanced,
            'balance_difference': balance_difference,
            # Section totals
            'total_assets': total_assets,
            'total_liabilities': total_liabilities,
            'total_equity': total_equity,
            # Report parameters
            'report_date': report_date,
            'date_from': date_from,
            'target_move': target_move,
        }
