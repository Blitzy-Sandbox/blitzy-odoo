# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Aged Partner Balance Report Parser (FR-006)

Provides comprehensive data formatting for the Aged Partner Balance QWeb
report template (aged_partner_balance_report.xml).  Computes aging bucket
grand totals, percentage distributions, collection-risk summaries, and
partner statistics so the template can render the full report without
heavy in-template calculation.

Integration points
------------------
* **Model**: ``account.aged.partner.balance.report`` — transient model whose
  ``partner_line_ids`` (One2many → ``account.aged.partner.balance.report.partner``)
  carry per-partner bucket amounts (``not_due``, ``bucket_1`` … ``bucket_5``,
  ``total``).
* **Template**: ``aged_partner_balance_report.xml`` — expects context keys for
  grand totals, percentages, risk classification, partner stats, and
  date / filter metadata.
"""

from odoo import api, fields, models


class ReportAgedPartnerBalance(models.AbstractModel):
    """Aged Partner Balance Report Parser.

    Prepares the complete rendering context required by the
    ``report_aged_partner_balance`` QWeb template:

    * Per-partner aging bucket amounts (Current, 1-30, 31-60, 61-90,
      91-120, 120+ days) — passed through via the ``docs`` recordset.
    * Grand totals per aging bucket column.
    * Percentage distribution across buckets for progress-bar
      visualisation.
    * Three-tier collection-risk classification
      (Current / Aging / At Risk).
    * Partner statistics (count, average balance, open invoices).
    * Company, currency, date, and filter context.
    """

    _name = 'report.account_financial_report_ce.report_aged_partner_balance'
    _description = 'Aged Partner Balance Report Parser'

    # ------------------------------------------------------------------
    # Report value preparation
    # ------------------------------------------------------------------

    @api.model
    def _get_report_values(self, docids, data=None):
        """Prepare the full data dictionary for the QWeb template.

        The method retrieves the transient report records identified by
        *docids*, walks their ``partner_line_ids`` to aggregate bucket
        totals and percentages, derives risk-classification figures, and
        returns everything the template needs in a single dictionary.

        Args:
            docids (list[int]): IDs of
                ``account.aged.partner.balance.report`` records.
            data (dict | None): Optional wizard-provided payload.

        Returns:
            dict: Template context containing at minimum:

            * ``docs`` — report recordset
            * ``grand_not_due`` … ``grand_120_plus``, ``grand_total``
            * ``bucket_percentages`` — dict keyed by bucket label
            * ``partner_type``, ``report_title``
            * ``current_amount``, ``aging_amount``, ``at_risk_amount``
            * ``total_partners``, ``average_balance``,
              ``total_open_invoices``
            * ``company``, ``currency_id``, ``date_at``,
              ``target_move``, ``show_move_lines``
        """
        docs = self.env['account.aged.partner.balance.report'].browse(docids)

        # -- Company and currency context --------------------------------
        company = docs[0].company_id if docs else self.env.company
        currency_id = company.currency_id

        # -- Partner type and report title --------------------------------
        # The model stores 'receivable' / 'payable' / 'both' in
        # ``report_type``; expose as ``partner_type`` for template use.
        report_type_val = docs[0].report_type if docs else 'receivable'
        partner_type = report_type_val
        report_title = {
            'receivable': 'Aged Receivable Balance',
            'payable': 'Aged Payable Balance',
            'both': 'Aged Partner Balance',
        }.get(partner_type, 'Aged Partner Balance')

        # -- Aggregate grand totals from partner lines --------------------
        # ``partner_line_ids`` carries per-partner bucket amounts:
        #   not_due, bucket_1 (1-30 d), bucket_2 (31-60 d),
        #   bucket_3 (61-90 d), bucket_4 (91-120 d), bucket_5 (120+ d),
        #   total.
        PartnerLine = self.env[
            'account.aged.partner.balance.report.partner'
        ]
        partner_lines = (
            docs[0].partner_line_ids if docs else PartnerLine.browse()
        )

        grand_not_due = sum(line.not_due for line in partner_lines)
        grand_1_30 = sum(line.bucket_1 for line in partner_lines)
        grand_31_60 = sum(line.bucket_2 for line in partner_lines)
        grand_61_90 = sum(line.bucket_3 for line in partner_lines)
        grand_91_120 = sum(line.bucket_4 for line in partner_lines)
        grand_120_plus = sum(line.bucket_5 for line in partner_lines)
        grand_total = sum(line.total for line in partner_lines)

        # -- Percentage distribution per bucket (progress bar) ------------
        if grand_total:
            pct_not_due = grand_not_due / grand_total * 100.0
            pct_1_30 = grand_1_30 / grand_total * 100.0
            pct_31_60 = grand_31_60 / grand_total * 100.0
            pct_61_90 = grand_61_90 / grand_total * 100.0
            pct_91_120 = grand_91_120 / grand_total * 100.0
            pct_120_plus = grand_120_plus / grand_total * 100.0
        else:
            pct_not_due = 0.0
            pct_1_30 = 0.0
            pct_31_60 = 0.0
            pct_61_90 = 0.0
            pct_91_120 = 0.0
            pct_120_plus = 0.0

        bucket_percentages = {
            'not_due': pct_not_due,
            '1_30': pct_1_30,
            '31_60': pct_31_60,
            '61_90': pct_61_90,
            '91_120': pct_91_120,
            '120_plus': pct_120_plus,
        }

        # -- Collection risk summary (three-tier classification) ----------
        # Current: amounts not yet due
        current_amount = grand_not_due
        # Aging: overdue but not yet critical (1-90 days)
        aging_amount = grand_1_30 + grand_31_60 + grand_61_90
        # At Risk: seriously overdue (91+ days)
        at_risk_amount = grand_91_120 + grand_120_plus

        # -- Partner statistics -------------------------------------------
        total_partners = len(partner_lines)
        average_balance = (
            grand_total / total_partners if total_partners else 0.0
        )
        # Count individual open-invoice detail lines across all partners
        # (each partner line may carry ``line_ids`` with invoice-level
        # detail records).
        total_open_invoices = sum(
            len(pline.line_ids) for pline in partner_lines
        )

        # -- Date and filter context --------------------------------------
        # ``date_to`` on the model is the "as-of" date for aging;
        # expose as ``date_at`` to match template expectations.
        date_at = docs[0].date_to if docs else fields.Date.today()
        target_move = docs[0].target_move if docs else 'posted'
        # ``show_move_lines`` controls invoice-level detail rendering;
        # use getattr for forward-compatibility if the field is added
        # to the model after this parser is deployed.
        show_move_lines = (
            getattr(docs[0], 'show_move_lines', False)
            if docs
            else False
        )

        return {
            # Standard Odoo report context keys
            'doc_ids': docids,
            'doc_model': 'account.aged.partner.balance.report',
            'docs': docs,
            'data': data,
            # Company and currency
            'company': company,
            'currency_id': currency_id,
            # Report mode (AR vs AP)
            'partner_type': partner_type,
            'report_title': report_title,
            # Grand totals per aging bucket
            'grand_not_due': grand_not_due,
            'grand_1_30': grand_1_30,
            'grand_31_60': grand_31_60,
            'grand_61_90': grand_61_90,
            'grand_91_120': grand_91_120,
            'grand_120_plus': grand_120_plus,
            'grand_total': grand_total,
            # Bucket percentages for progress-bar visualisation
            'bucket_percentages': bucket_percentages,
            # Collection risk summary
            'current_amount': current_amount,
            'aging_amount': aging_amount,
            'at_risk_amount': at_risk_amount,
            # Partner statistics
            'total_partners': total_partners,
            'average_balance': average_balance,
            'total_open_invoices': total_open_invoices,
            # Date and filter context
            'date_at': date_at,
            'target_move': target_move,
            'show_move_lines': show_move_lines,
        }
