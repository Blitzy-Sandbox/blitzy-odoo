# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Reconciliation Status Report Parser

Provides data formatting for the Bank Reconciliation Status Report QWeb
template.  Follows the same AbstractModel report-parser pattern used by
``account_financial_report_ce/report/report_balance_sheet.py`` and the
other FR-module report parsers.

The parser name **must** match the ``report_name`` declared in the
``ir.actions.report`` record inside ``reconciliation_report.xml``::

    report.account_bank_reconciliation_ce.reconciliation_status

Odoo resolves the parser by prefixing ``report.`` to the ``report_name``
attribute and looking up an ``AbstractModel`` with that ``_name``.
"""

from datetime import date

from odoo import api, fields, models

import logging

_logger = logging.getLogger(__name__)


class ReportReconciliationStatus(models.AbstractModel):
    """Bank Reconciliation Status Report Parser.

    Supplies the ``_get_report_values`` dictionary consumed by the QWeb
    template ``reconciliation_status``.  The template expects the
    standard ``docs`` recordset and a handful of pre-computed helper
    variables for date calculations and aggregation.
    """

    _name = 'report.account_bank_reconciliation_ce.reconciliation_status'
    _description = 'Bank Reconciliation Status Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        """Prepare data for the Reconciliation Status QWeb report template.

        Args:
            docids: list of ``account.reconciliation.wizard`` record IDs.
            data:   optional dictionary with extra context passed from the
                    calling action (unused by the default template).

        Returns:
            dict consumed by the QWeb engine with keys:

            - ``doc_ids``   – list of record IDs
            - ``doc_model`` – model technical name
            - ``docs``      – browse recordset of wizard records
            - ``data``      – pass-through of *data*
            - ``today``     – ``datetime.date.today()`` for aging calcs
            - ``datetime``  – reference to the ``datetime`` stdlib module
                              so the template can call
                              ``datetime.datetime.now()``
        """
        docs = self.env['account.reconciliation.wizard'].browse(docids)

        # Import datetime module so the QWeb template can access
        # ``datetime.datetime.now()`` for the "Generated on" footer.
        import datetime as dt_module

        return {
            'doc_ids': docids,
            'doc_model': 'account.reconciliation.wizard',
            'docs': docs,
            'data': data,
            'today': date.today(),
            'datetime': dt_module,
        }
