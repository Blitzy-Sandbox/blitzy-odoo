# -*- coding: utf-8 -*-
# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Reconciliation Status Report Parser - Provides data formatting for the
Reconciliation Status QWeb report template.

Follows the stateless AbstractModel report-parser pattern established by
``account_financial_report_ce/report/report_balance_sheet.py`` and the
other FR-module report parsers.  The parser pre-computes derived statistics
(match counts, confidence distribution, aging, per-statement summary) and
the QWeb template handles visual rendering.

The parser name **must** match the ``report_name`` declared in the
``ir.actions.report`` record inside ``reconciliation_report.xml``::

    report.account_bank_reconciliation_ce.reconciliation_status

Odoo resolves the parser by prefixing ``report.`` to the ``report_name``
attribute and looking up an ``AbstractModel`` with that ``_name``.

Data sources (read-only access per Section 0.7.3):
    - ``account.reconciliation.wizard``: primary report documents providing
      journal_id, company_id, date_from, date_to, currency_id,
      statement_line_ids for scoping queries.
    - ``account.bank.statement.line``: statement line data with CE-extension
      fields ``reconciliation_status`` and ``matching_confidence`` added by
      ``BankStatementLineExt`` in ``partial_reconcile_ext.py``.
    - ``account.reconciliation.matching``: matching suggestion records with
      ``confidence_level``, ``confidence_score``, ``statement_line_id``,
      and ``state`` used for confidence distribution aggregation.

Multi-company isolation: every search includes an explicit
``('company_id', '=', company_id)`` domain filter.

Zero Enterprise module dependencies.
"""

import datetime as _dt_module
import logging
from datetime import date

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ReportReconciliationStatus(models.AbstractModel):
    """Bank Reconciliation Status Report Parser.

    Supplies the ``_get_report_values`` dictionary consumed by the QWeb
    template ``reconciliation_status``.  Pre-computes reconciliation
    statistics so the template receives ready-to-render data structures:

    - **reconciliation_summary**: per-statement match/unmatch counts and
      match rate, with amounts.
    - **unreconciled_lines**: detail of each unreconciled statement line
      including days-since-date aging and aging bucket classification.
    - **confidence_distribution**: count and percentage of matching
      suggestions by confidence level (High / Medium / Low / None).
    - **total_stats**: global totals across all statements — line counts,
      amounts, and overall match rate.

    Integration points:
        ``account.reconciliation.wizard``
            Browsed by *docids*; provides journal_id, company_id,
            date_from, date_to, currency_id, and statement_line_ids
            for query scoping.

        ``account.reconciliation.matching``
            Searched for confidence_level distribution via ``read_group``
            aggregation on records linked to in-scope statement lines.

        ``account.bank.statement.line`` (CE extensions)
            The ``reconciliation_status`` and ``matching_confidence``
            fields added by ``BankStatementLineExt`` drive matched vs
            unmatched classification and per-line confidence display.
    """

    _name = 'report.account_bank_reconciliation_ce.reconciliation_status'
    _description = 'Reconciliation Status Report Parser'

    # -------------------------------------------------------------------------
    # PUBLIC API
    # -------------------------------------------------------------------------

    @api.model
    def _get_report_values(self, docids, data=None):
        """Prepare data for the Reconciliation Status report template.

        Browses ``account.reconciliation.wizard`` records identified by
        *docids*, then searches and aggregates reconciliation status data
        across the bank statement lines in scope.  All queries enforce
        multi-company isolation via explicit ``company_id`` filters.

        Args:
            docids: List of ``account.reconciliation.wizard`` record IDs.
            data:   Optional dictionary with additional context from the
                    calling action (passed through to the template).

        Returns:
            Dictionary with report data for the QWeb template including:

            - ``doc_ids``                 – list of record IDs
            - ``doc_model``               – ``'account.reconciliation.wizard'``
            - ``docs``                    – browse recordset of wizard records
            - ``data``                    – pass-through of *data*
            - ``reconciliation_summary``  – per-journal/statement aggregated
                                            match statistics (list of dicts)
            - ``unreconciled_lines``      – statement lines still unreconciled
                                            with aging info (list of dicts)
            - ``confidence_distribution`` – count of matches by confidence
                                            level (dict)
            - ``total_stats``             – overall totals: total_lines,
                                            matched, unmatched, match_rate
                                            (dict)
            - ``today``                   – context-aware today date for
                                            aging calculations
            - ``datetime``                – stdlib ``datetime`` module
                                            reference for template timestamps
        """
        docs = self.env['account.reconciliation.wizard'].browse(docids)
        today_date = fields.Date.context_today(self)

        # Collect all statement lines across all wizard documents.
        # We search independently (not relying solely on the wizard's
        # computed statement_line_ids) so we can include BOTH reconciled
        # and unreconciled lines for a complete status picture.
        all_statement_lines = self.env['account.bank.statement.line']
        for doc in docs:
            lines = self._get_scoped_statement_lines(doc)
            all_statement_lines |= lines

        # Pre-compute all report sections
        reconciliation_summary = self._compute_reconciliation_summary(
            all_statement_lines, today_date,
        )
        unreconciled_lines = self._compute_unreconciled_with_aging(
            all_statement_lines, today_date,
        )
        confidence_distribution = self._compute_confidence_distribution(
            all_statement_lines,
        )
        total_stats = self._compute_total_stats(all_statement_lines)

        return {
            'doc_ids': docids,
            'doc_model': 'account.reconciliation.wizard',
            'docs': docs,
            'data': data,
            'reconciliation_summary': reconciliation_summary,
            'unreconciled_lines': unreconciled_lines,
            'confidence_distribution': confidence_distribution,
            'total_stats': total_stats,
            'today': today_date,
            # The QWeb template uses datetime.datetime.now() for the footer
            # timestamp via context_timestamp(); we pass the stdlib module.
            'datetime': _dt_module,
        }

    # -------------------------------------------------------------------------
    # PRIVATE HELPER METHODS
    # -------------------------------------------------------------------------

    @api.model
    def _get_scoped_statement_lines(self, wizard):
        """Retrieve ALL bank statement lines scoped by wizard parameters.

        Builds a domain from the wizard's ``journal_id``, ``company_id``,
        and optional ``date_from`` / ``date_to`` range, then searches
        ``account.bank.statement.line``.  Unlike the wizard's own computed
        ``statement_line_ids`` (which filters to unreconciled only), this
        method returns **all** lines so the report can compute accurate
        match rates and reconciled-vs-unreconciled breakdowns.

        Multi-company isolation is enforced by including the
        ``company_id`` filter in every query.

        Args:
            wizard: Single ``account.reconciliation.wizard`` record
                    providing ``journal_id``, ``company_id``,
                    ``date_from``, ``date_to``, and ``currency_id``.

        Returns:
            Recordset of ``account.bank.statement.line``.
        """
        if not wizard.journal_id or not wizard.company_id:
            return self.env['account.bank.statement.line']

        domain = [
            ('journal_id', '=', wizard.journal_id.id),
            ('company_id', '=', wizard.company_id.id),
        ]
        if wizard.date_from:
            domain.append(('date', '>=', wizard.date_from))
        if wizard.date_to:
            domain.append(('date', '<=', wizard.date_to))

        return self.env['account.bank.statement.line'].search(
            domain, order='date asc, id asc',
        )

    @api.model
    def _compute_reconciliation_summary(self, statement_lines, today_date):
        """Compute per-statement reconciliation summary statistics.

        Groups statement lines by their ``statement_id`` and computes
        matched / unmatched / partially-reconciled counts together with
        amounts and a per-statement match rate percentage.

        Uses Python-level grouping over the pre-fetched recordset,
        which is efficient for the typical report sizes (hundreds to
        low thousands of statement lines).

        Args:
            statement_lines: Recordset of ``account.bank.statement.line``
                             (all statuses included).
            today_date:      ``datetime.date`` for consistent calculations.

        Returns:
            list of dicts sorted by statement date (descending), each
            containing:

            - ``statement_id``: int or False
            - ``statement_name``: str
            - ``statement_date``: date or False
            - ``total_lines``: int
            - ``matched_count``: int
            - ``unmatched_count``: int
            - ``partially_count``: int
            - ``match_rate``: float (0.0 – 100.0, rounded to 1 decimal)
            - ``total_amount``: float
            - ``reconciled_amount``: float
            - ``unreconciled_amount``: float
        """
        if not statement_lines:
            return []

        # Group lines by statement_id
        stmt_groups = {}
        for line in statement_lines:
            stmt = line.statement_id
            stmt_key = stmt.id if stmt else 0
            if stmt_key not in stmt_groups:
                stmt_groups[stmt_key] = {
                    'statement': stmt,
                    'lines': self.env['account.bank.statement.line'],
                }
            stmt_groups[stmt_key]['lines'] |= line

        summary = []
        for _stmt_key, group_data in stmt_groups.items():
            stmt = group_data['statement']
            lines = group_data['lines']
            total = len(lines)

            # Classify using the CE extension field reconciliation_status
            matched = len(lines.filtered(
                lambda l: l.reconciliation_status in ('reconciled', 'manual')
            ))
            partial = len(lines.filtered(
                lambda l: l.reconciliation_status == 'partially'
            ))
            unmatched = total - matched - partial

            # Amount aggregation
            total_amount = sum(lines.mapped('amount'))
            reconciled_amount = sum(lines.filtered(
                lambda l: l.reconciliation_status in ('reconciled', 'manual')
            ).mapped('amount'))
            unreconciled_amount = total_amount - reconciled_amount

            match_rate = round(
                (matched / total * 100.0) if total > 0 else 0.0, 1,
            )

            summary.append({
                'statement_id': stmt.id if stmt else False,
                'statement_name': (
                    (stmt.name or ('Statement #%s' % stmt.id))
                    if stmt else 'No Statement'
                ),
                'statement_date': stmt.date if stmt else False,
                'total_lines': total,
                'matched_count': matched,
                'unmatched_count': unmatched,
                'partially_count': partial,
                'match_rate': match_rate,
                'total_amount': total_amount,
                'reconciled_amount': reconciled_amount,
                'unreconciled_amount': unreconciled_amount,
            })

        # Sort by statement date descending (most recent first);
        # statements without a date sort to the end.
        summary.sort(
            key=lambda s: s.get('statement_date') or date.min,
            reverse=True,
        )
        return summary

    @api.model
    def _compute_unreconciled_with_aging(self, statement_lines, today_date):
        """Compute unreconciled statement lines with aging information.

        For each unreconciled line, calculates the number of days since
        the statement line date (``today_date - line.date``) and assigns
        an aging bucket label matching the QWeb template's classification:

        - **Recent** : 0 – 30 days
        - **Aging**  : 31 – 60 days
        - **Overdue**: 61 – 90 days
        - **Critical**: 90+ days

        Args:
            statement_lines: Recordset of ``account.bank.statement.line``.
            today_date:      ``datetime.date`` from
                             ``fields.Date.context_today(self)``.

        Returns:
            list of dicts (sorted by line date ascending), each with:

            - ``line_id``: int
            - ``date``: date or False
            - ``payment_ref``: str
            - ``partner_name``: str or False
            - ``amount``: float
            - ``days_unreconciled``: int
            - ``aging_bucket``: str (``'0_30'``, ``'31_60'``, ``'61_90'``,
              ``'90_plus'``)
            - ``aging_label``: str (``'Recent'``, ``'Aging'``,
              ``'Overdue'``, ``'Critical'``)
            - ``matching_confidence``: float (0 – 100, from CE extension)
            - ``reconciliation_status``: str (selection value)
        """
        unreconciled = statement_lines.filtered(
            lambda l: l.reconciliation_status == 'unreconciled'
        )
        if not unreconciled:
            return []

        # Use date.today() as a fallback if context_today returned
        # a falsy value (should not happen, but defensive coding).
        ref_date = today_date or date.today()

        result = []
        for line in unreconciled.sorted(
            key=lambda l: l.date or date.min,
        ):
            line_date = line.date
            days = (ref_date - line_date).days if line_date else 0

            # Aging bucket classification matching the QWeb template
            if days > 90:
                aging_bucket = '90_plus'
                aging_label = 'Critical'
            elif days > 60:
                aging_bucket = '61_90'
                aging_label = 'Overdue'
            elif days > 30:
                aging_bucket = '31_60'
                aging_label = 'Aging'
            else:
                aging_bucket = '0_30'
                aging_label = 'Recent'

            result.append({
                'line_id': line.id,
                'date': line_date,
                'payment_ref': line.payment_ref or line.name or '',
                'partner_name': (
                    line.partner_id.name if line.partner_id else False
                ),
                'amount': line.amount or 0.0,
                'days_unreconciled': days,
                'aging_bucket': aging_bucket,
                'aging_label': aging_label,
                'matching_confidence': line.matching_confidence or 0.0,
                'reconciliation_status': line.reconciliation_status or 'unreconciled',
            })

        return result

    @api.model
    def _compute_confidence_distribution(self, statement_lines):
        """Compute confidence level distribution for matching suggestions.

        Searches ``account.reconciliation.matching`` records linked to
        the given statement lines (``state`` in ``proposed`` or
        ``confirmed``) and aggregates by ``confidence_level`` using
        ``read_group`` for efficient database-level grouping.

        Args:
            statement_lines: Recordset of ``account.bank.statement.line``.

        Returns:
            dict with keys:

            - ``high``: int — count of matches with confidence_level='high'
            - ``medium``: int
            - ``low``: int
            - ``none``: int — below threshold
            - ``total``: int — sum of all levels
            - ``high_pct``: float (0.0 – 100.0)
            - ``medium_pct``: float
            - ``low_pct``: float
            - ``none_pct``: float
            - ``quality_rate``: float — percentage of high + medium
        """
        distribution = {
            'high': 0,
            'medium': 0,
            'low': 0,
            'none': 0,
            'total': 0,
            'high_pct': 0.0,
            'medium_pct': 0.0,
            'low_pct': 0.0,
            'none_pct': 0.0,
            'quality_rate': 0.0,
        }

        if not statement_lines:
            return distribution

        MatchingModel = self.env['account.reconciliation.matching']

        # Use read_group for efficient DB-level aggregation by
        # confidence_level.  Only include proposed and confirmed
        # matches (rejected matches are excluded from the report).
        groups = MatchingModel.read_group(
            domain=[
                ('statement_line_id', 'in', statement_lines.ids),
                ('state', 'in', ('proposed', 'confirmed')),
            ],
            fields=['confidence_level'],
            groupby=['confidence_level'],
        )

        for group in groups:
            level = group.get('confidence_level')
            count = group.get('confidence_level_count', 0)
            if level and level in distribution:
                distribution[level] = count

        total = (
            distribution['high']
            + distribution['medium']
            + distribution['low']
            + distribution['none']
        )
        distribution['total'] = total

        if total > 0:
            distribution['high_pct'] = round(
                distribution['high'] / total * 100.0, 1,
            )
            distribution['medium_pct'] = round(
                distribution['medium'] / total * 100.0, 1,
            )
            distribution['low_pct'] = round(
                distribution['low'] / total * 100.0, 1,
            )
            distribution['none_pct'] = round(
                distribution['none'] / total * 100.0, 1,
            )
            distribution['quality_rate'] = round(
                (distribution['high'] + distribution['medium'])
                / total * 100.0,
                1,
            )

        return distribution

    @api.model
    def _compute_total_stats(self, statement_lines):
        """Compute overall reconciliation statistics across all lines.

        Aggregates matched / unmatched / partially-reconciled counts and
        monetary amounts to produce the global summary displayed in the
        ``total_stats`` section of the report.

        Args:
            statement_lines: Recordset of ``account.bank.statement.line``.

        Returns:
            dict with keys:

            - ``total_lines``: int — total number of statement lines
            - ``total_matched``: int — fully reconciled + manually matched
            - ``total_unmatched``: int — unreconciled lines
            - ``total_partial``: int — partially reconciled lines
            - ``match_rate``: float (0.0 – 100.0) — line-count based
            - ``total_amount``: float — sum of all line amounts
            - ``reconciled_amount``: float — sum of reconciled line amounts
            - ``unreconciled_amount``: float — sum of unreconciled amounts
            - ``partial_amount``: float — sum of partially reconciled amounts
            - ``amount_match_rate``: float (0.0 – 100.0) — amount-based
            - ``statement_count``: int — number of unique statements
        """
        total_lines = len(statement_lines)

        if total_lines == 0:
            return {
                'total_lines': 0,
                'total_matched': 0,
                'total_unmatched': 0,
                'total_partial': 0,
                'match_rate': 0.0,
                'total_amount': 0.0,
                'reconciled_amount': 0.0,
                'unreconciled_amount': 0.0,
                'partial_amount': 0.0,
                'amount_match_rate': 0.0,
                'statement_count': 0,
            }

        # Classify lines by reconciliation_status (CE extension field)
        matched_lines = statement_lines.filtered(
            lambda l: l.reconciliation_status in ('reconciled', 'manual')
        )
        partial_lines = statement_lines.filtered(
            lambda l: l.reconciliation_status == 'partially'
        )
        unmatched_lines = statement_lines.filtered(
            lambda l: l.reconciliation_status == 'unreconciled'
        )

        total_matched = len(matched_lines)
        total_partial = len(partial_lines)
        total_unmatched = len(unmatched_lines)

        # Amount aggregation
        total_amount = sum(statement_lines.mapped('amount'))
        reconciled_amount = sum(matched_lines.mapped('amount'))
        partial_amount = sum(partial_lines.mapped('amount'))
        unreconciled_amount = sum(unmatched_lines.mapped('amount'))

        # Match rate by line count
        match_rate = round(
            (total_matched / total_lines * 100.0), 1,
        )

        # Match rate by amount (use absolute values to handle
        # mixed debit/credit amounts correctly)
        abs_total = abs(total_amount)
        amount_match_rate = round(
            (abs(reconciled_amount) / abs_total * 100.0)
            if abs_total > 0.0 else 0.0,
            1,
        )

        # Count unique statements
        statements = statement_lines.mapped('statement_id')

        return {
            'total_lines': total_lines,
            'total_matched': total_matched,
            'total_unmatched': total_unmatched,
            'total_partial': total_partial,
            'match_rate': match_rate,
            'total_amount': total_amount,
            'reconciled_amount': reconciled_amount,
            'unreconciled_amount': unreconciled_amount,
            'partial_amount': partial_amount,
            'amount_match_rate': amount_match_rate,
            'statement_count': len(statements),
        }
