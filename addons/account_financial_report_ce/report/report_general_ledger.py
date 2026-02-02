# -*- coding: utf-8 -*-
# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, models


class ReportGeneralLedger(models.AbstractModel):
    """General Ledger Report Parser."""
    _name = 'report.account_financial_report_ce.report_general_ledger'
    _description = 'General Ledger Report Parser'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['account.general.ledger.report'].browse(docids)
        return {
            'doc_ids': docids,
            'doc_model': 'account.general.ledger.report',
            'docs': docs,
            'data': data,
        }
