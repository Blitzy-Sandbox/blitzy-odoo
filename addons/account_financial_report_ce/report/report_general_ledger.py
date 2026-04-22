# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
General Ledger Report Parser (FR-004)

Provides data formatting and aggregation for the General Ledger QWeb
report template.  Transforms transient model data from
``account.general.ledger.report`` into the structure required by the
``general_ledger_report.xml`` QWeb template, including:

* Per-account transaction data with opening/closing balances split
  into debit and credit columns.
* Pre-sorted transaction lines respecting the user-selected sort order.
* Grand totals aggregated across all accounts in the report.
* Company and currency context for monetary formatting.
* Filter context values for the template parameter header.

Integration points:
    - Reads from ``account.general.ledger.report`` TransientModel
      (``account_line_ids`` → ``account.general.ledger.report.account``
      → ``line_ids`` → ``account.general.ledger.report.line``).
    - Supplies data to QWeb template ``report_general_ledger``.
    - Supports both PDF (QWeb → wkhtmltopdf) and XLSX export pathways.
"""

from odoo import api, models


class ReportGeneralLedger(models.AbstractModel):
    """General Ledger Report Parser.

    Transforms the computed report data stored in the
    ``account.general.ledger.report`` transient model into a
    complete template context dictionary for QWeb rendering.

    The heavy lifting (balance computation, transaction retrieval,
    running-balance calculation) is performed by the transient model's
    ``_compute_report_data`` method.  This parser focuses on:

    1. Re-structuring the ORM records into a list of plain dicts
       (``accounts_data``) for easy template iteration and XLSX export.
    2. Splitting net opening / closing balances into separate debit and
       credit columns for columnar presentation.
    3. Computing grand totals across all included accounts.
    4. Extracting filter-context values for the report header display.
    """

    _name = 'report.account_financial_report_ce.report_general_ledger'
    _description = 'General Ledger Report Parser'

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_sort_key(sort_by):
        """Return a sort-key function for transaction lines.

        The ``sort_by`` selection on the report model controls how
        individual journal-item lines are ordered within each account
        section.

        Args:
            sort_by (str): One of ``'date'``, ``'ref'``, or ``'name'``.

        Returns:
            callable: A key function suitable for ``recordset.sorted()``.
        """
        if sort_by == 'ref':
            return lambda line: (line.ref or '', line.date, line.id)
        if sort_by == 'name':
            return lambda line: (line.name or '', line.date, line.id)
        # Default: chronological order with stable tie-breaking by id
        return lambda line: (line.date, line.id)

    @staticmethod
    def _split_balance(balance):
        """Split a net balance into debit and credit column values.

        In General Ledger columnar presentation the opening and closing
        balances are shown in the debit column when positive (natural
        debit balance) and in the credit column when negative (natural
        credit balance).

        Args:
            balance (float): Net balance amount (debit minus credit).

        Returns:
            tuple[float, float]: ``(debit_amount, credit_amount)``
                where exactly one value is non-zero.
        """
        if balance >= 0:
            return balance, 0.0
        return 0.0, abs(balance)

    # ------------------------------------------------------------------
    # Data-building pipeline
    # ------------------------------------------------------------------

    def _build_accounts_data(self, docs):
        """Build a pre-structured list of per-account data dicts.

        Iterates every ``account_line_id`` across all *docs* records,
        producing an ordered list that the QWeb template (or an XLSX
        exporter) can iterate without further ORM calls.

        Each dict in the returned list contains:

        * ``account`` - the ``account.account`` record.
        * ``account_line`` - the ``account.general.ledger.report.account``
          record (gives direct ORM access if needed).
        * ``opening_debit``, ``opening_credit``, ``opening_balance`` -
          opening figures with the net balance split into columns.
        * ``period_lines`` - a *sorted* recordset of
          ``account.general.ledger.report.line`` transaction records.
        * ``period_debit``, ``period_credit`` - period movement totals.
        * ``closing_debit``, ``closing_credit``, ``closing_balance`` -
          closing figures with the net balance split into columns.

        Args:
            docs: Recordset of ``account.general.ledger.report``.

        Returns:
            list[dict]: One entry per account section, ordered by
            account code (via the account-line ``name`` field which is
            formatted as ``"<code> - <name>"``).
        """
        accounts_data = []

        for doc in docs:
            # Resolve user-selected sort order for transaction lines
            sort_by = getattr(doc, 'sort_by', 'date') or 'date'
            sort_key = self._get_sort_key(sort_by)

            # Account lines are stored sorted by name (<code> - <name>)
            for account_line in doc.account_line_ids.sorted('name'):
                opening_debit, opening_credit = self._split_balance(
                    account_line.opening_balance,
                )
                closing_debit, closing_credit = self._split_balance(
                    account_line.closing_balance,
                )

                # Re-sort transaction lines per user preference
                period_lines = account_line.line_ids.sorted(key=sort_key)

                accounts_data.append({
                    'account': account_line.account_id,
                    'account_line': account_line,
                    'opening_debit': opening_debit,
                    'opening_credit': opening_credit,
                    'opening_balance': account_line.opening_balance,
                    'period_lines': period_lines,
                    'period_debit': account_line.total_debit,
                    'period_credit': account_line.total_credit,
                    'closing_debit': closing_debit,
                    'closing_credit': closing_credit,
                    'closing_balance': account_line.closing_balance,
                })

        return accounts_data

    @staticmethod
    def _compute_grand_totals(accounts_data):
        """Aggregate grand totals from the per-account data list.

        Sums opening, period-movement, and closing figures across every
        account section to produce the report-level grand-total row.

        Args:
            accounts_data (list[dict]): Output of
                :meth:`_build_accounts_data`.

        Returns:
            dict: Keys prefixed with ``grand_`` matching the values
            expected by the QWeb grand-totals table and XLSX export.
        """
        grand_opening_debit = 0.0
        grand_opening_credit = 0.0
        grand_opening_balance = 0.0
        grand_period_debit = 0.0
        grand_period_credit = 0.0
        grand_closing_debit = 0.0
        grand_closing_credit = 0.0
        grand_closing_balance = 0.0

        for acct in accounts_data:
            grand_opening_debit += acct['opening_debit']
            grand_opening_credit += acct['opening_credit']
            grand_opening_balance += acct['opening_balance']
            grand_period_debit += acct['period_debit']
            grand_period_credit += acct['period_credit']
            grand_closing_debit += acct['closing_debit']
            grand_closing_credit += acct['closing_credit']
            grand_closing_balance += acct['closing_balance']

        return {
            'grand_opening_debit': grand_opening_debit,
            'grand_opening_credit': grand_opening_credit,
            'grand_opening_balance': grand_opening_balance,
            'grand_period_debit': grand_period_debit,
            'grand_period_credit': grand_period_credit,
            'grand_closing_debit': grand_closing_debit,
            'grand_closing_credit': grand_closing_credit,
            'grand_closing_balance': grand_closing_balance,
        }

    def _get_filter_context(self, docs):
        """Extract filter / display-option context from the first doc.

        Safely reads report configuration fields, falling back to
        sensible defaults when a field does not (yet) exist on the
        model.  This provides forward-compatibility so the parser
        continues to work as new display-option fields are added to the
        transient model by parallel development efforts.

        Args:
            docs: Recordset of ``account.general.ledger.report``.

        Returns:
            dict: Filter-context keys consumed by the QWeb template
            header section (date range, target move, visibility flags,
            active filters).
        """
        if not docs:
            return {
                'date_from': False,
                'date_to': False,
                'target_move': 'posted',
                'hide_account_at_0': False,
                'show_details': True,
                'filter_accounts': self.env['account.account'],
                'filter_partners': self.env['res.partner'],
            }

        first_doc = docs[0]

        # ``hide_account_at_0`` may be exposed under the name
        # ``hide_zero_balance`` on the abstract base model.
        hide_account_at_0 = getattr(
            first_doc, 'hide_account_at_0',
            getattr(first_doc, 'hide_zero_balance', False),
        )

        # ``show_details`` controls transaction-line visibility; the
        # field may not yet be present on the model.
        show_details = getattr(first_doc, 'show_details', True)

        # ``partner_ids`` is only relevant when the General Ledger is
        # filtered by partner; not all model versions expose it.
        filter_partners = getattr(
            first_doc, 'partner_ids', self.env['res.partner'],
        )

        # ``account_ids`` is the Many2many filter field on the GL model.
        filter_accounts = first_doc.account_ids

        return {
            'date_from': first_doc.date_from,
            'date_to': first_doc.date_to,
            'target_move': first_doc.target_move,
            'hide_account_at_0': hide_account_at_0,
            'show_details': show_details,
            'filter_accounts': filter_accounts,
            'filter_partners': filter_partners,
        }

    # ------------------------------------------------------------------
    # Public API - called by the Odoo report engine
    # ------------------------------------------------------------------

    @api.model
    def _get_report_values(self, docids, data=None):
        """Prepare the complete data context for the General Ledger report.

        This is the entry point invoked by the Odoo report rendering
        engine when generating the General Ledger PDF or when the
        template is rendered in the browser.

        The method orchestrates the data-building pipeline:

        1. Browse the transient report records.
        2. Resolve company and currency context.
        3. Build the per-account structured data list
           (``accounts_data``).
        4. Compute grand totals from the structured data.
        5. Extract filter context for the template header.
        6. Assemble and return the unified template context dict.

        Args:
            docids (list[int]): IDs of
                ``account.general.ledger.report`` records to render.
            data (dict | None): Additional context passed from the
                report wizard action.

        Returns:
            dict: Complete template context containing:

            - ``doc_ids``, ``doc_model``, ``docs``, ``data`` -
              standard Odoo report values.
            - ``company``, ``currency_id`` - company and currency
              context for monetary formatting.
            - ``accounts_data`` - pre-built per-account data list for
              template iteration and XLSX export.
            - ``grand_opening_debit`` … ``grand_closing_balance`` -
              aggregated grand totals.
            - ``date_from``, ``date_to``, ``target_move``,
              ``hide_account_at_0``, ``show_details``,
              ``filter_accounts``, ``filter_partners`` -
              filter context for the report header.
        """
        docs = self.env['account.general.ledger.report'].browse(docids)

        # ---- Company & currency context ----
        company = docs[0].company_id if docs else self.env.company
        currency_id = company.currency_id

        # ---- Per-account structured data ----
        accounts_data = self._build_accounts_data(docs)

        # ---- Grand totals ----
        grand_totals = self._compute_grand_totals(accounts_data)

        # ---- Filter context for template header ----
        filter_context = self._get_filter_context(docs)

        # ---- Assemble result ----
        result = {
            'doc_ids': docids,
            'doc_model': 'account.general.ledger.report',
            'docs': docs,
            'data': data,
            'company': company,
            'currency_id': currency_id,
            'accounts_data': accounts_data,
        }
        result.update(grand_totals)
        result.update(filter_context)

        return result
