# -*- coding: utf-8 -*-
# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, models


class ReportAgedPartnerBalance(models.AbstractModel):
    """Aged Partner Balance Report Parser."""
    _name = 'report.account_financial_report_ce.report_aged_partner_balance'
    _description = 'Aged Partner Balance Report Parser'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['account.aged.partner.balance.report'].browse(docids)
        return {
            'doc_ids': docids,
            'doc_model': 'account.aged.partner.balance.report',
            'docs': docs,
            'data': data,
        }
