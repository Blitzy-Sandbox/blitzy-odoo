# -*- coding: utf-8 -*-
# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, models


class ReportProfitLoss(models.AbstractModel):
    """Profit & Loss Report Parser."""
    _name = 'report.account_financial_report_ce.report_profit_loss'
    _description = 'Profit & Loss Report Parser'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['account.profit.loss.report'].browse(docids)
        return {
            'doc_ids': docids,
            'doc_model': 'account.profit.loss.report',
            'docs': docs,
            'data': data,
        }
