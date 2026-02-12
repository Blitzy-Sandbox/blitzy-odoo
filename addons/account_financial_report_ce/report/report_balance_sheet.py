# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Balance Sheet Report Parser

Provides data formatting for the Balance Sheet QWeb report template.
"""

from odoo import api, models


class ReportBalanceSheet(models.AbstractModel):
    """Balance Sheet Report Parser."""
    _name = 'report.account_financial_report_ce.report_balance_sheet'
    _description = 'Balance Sheet Report Parser'

    @api.model
    def _get_report_values(self, docids, data=None):
        """
        Prepare data for the Balance Sheet report template.

        Args:
            docids: List of report record IDs
            data: Additional data passed from wizard

        Returns:
            Dictionary with report data for QWeb template
        """
        docs = self.env['account.balance.sheet.report'].browse(docids)

        return {
            'doc_ids': docids,
            'doc_model': 'account.balance.sheet.report',
            'docs': docs,
            'data': data,
        }
