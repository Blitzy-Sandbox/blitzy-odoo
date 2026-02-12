# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, models


class ReportCashFlow(models.AbstractModel):
    """Cash Flow Statement Report Parser."""
    _name = 'report.account_financial_report_ce.report_cash_flow'
    _description = 'Cash Flow Report Parser'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['account.cash.flow.report'].browse(docids)
        return {
            'doc_ids': docids,
            'doc_model': 'account.cash.flow.report',
            'docs': docs,
            'data': data,
        }
