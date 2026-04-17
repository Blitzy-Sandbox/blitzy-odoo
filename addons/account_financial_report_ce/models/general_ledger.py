# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
General Ledger Report Model

Implements FR-004: General Ledger Report
User Story: As an Accountant, I want to generate a general ledger showing all
transactions by account so that I can verify account activity and trace
individual transactions.

Acceptance Criteria:
- Scenario 1: Generate General Ledger for date range
- Scenario 2: Filter by specific accounts or account ranges
- Scenario 3: Show opening balance, transactions, closing balance per account
- Scenario 4: Transaction detail with date, reference, description, debit, credit
- Scenario 5: Sort by date or document reference
- Scenario 6: Drill-down to source journal entries
"""

from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command


class GeneralLedgerReport(models.TransientModel):
    """
    General Ledger Report.

    Shows all transactions for each account within a date range,
    with opening balance, transaction details, and closing balance.
    """
    _name = 'account.general.ledger.report'
    _description = 'General Ledger Report'
    _inherit = 'account.financial.report.abstract'

    # -------------------------------------------------------------------------
    # GENERAL LEDGER SPECIFIC FIELDS
    # -------------------------------------------------------------------------

    date_from = fields.Date(
        string='From Date',
        required=True,
        help="Start date for transactions to include.",
    )

    date_to = fields.Date(
        string='To Date',
        required=True,
        default=fields.Date.context_today,
        help="End date for transactions to include.",
    )

    account_ids = fields.Many2many(
        comodel_name='account.account',
        string='Accounts',
        help="Specific accounts to include. Leave empty for all accounts.",
    )

    account_from = fields.Char(
        string='From Account Code',
        help="Starting account code for range filter.",
    )

    account_to = fields.Char(
        string='To Account Code',
        help="Ending account code for range filter.",
    )

    include_initial_balance = fields.Boolean(
        string='Include Initial Balance',
        default=True,
        help="Show opening balance for each account.",
    )

    sort_by = fields.Selection(
        selection=[
            ('date', 'Date'),
            ('ref', 'Reference'),
            ('name', 'Description'),
        ],
        string='Sort By',
        default='date',
        help="Sort transactions within each account by this field.",
    )

    centralize = fields.Boolean(
        string='Centralize Partners',
        default=False,
        help="Group transactions by partner within each account.",
    )

    partner_ids = fields.Many2many(
        comodel_name='res.partner',
        string='Partners',
        help="Specific partners to include. Leave empty for all partners.",
    )

    show_details = fields.Boolean(
        string='Show Transaction Details',
        default=True,
        help="When enabled, individual journal entry lines are "
             "displayed under each account. When disabled, only "
             "account-level summaries are shown.",
    )

    # -----------------------------------------------------------------
    # TEMPLATE-FACING ALIAS FIELDS
    # QWeb ``general_ledger_report.xml`` references ``doc.hide_account_at_0``
    # as an alias of the abstract ``hide_zero_balance`` flag.
    # -----------------------------------------------------------------

    hide_account_at_0 = fields.Boolean(
        related='hide_zero_balance',
        string='Hide Empty Accounts',
        readonly=True,
        help="Alias of 'hide_zero_balance' for QWeb template "
             "compatibility.",
    )

    # -------------------------------------------------------------------------
    # COMPUTED REPORT DATA
    # -------------------------------------------------------------------------

    account_line_ids = fields.One2many(
        comodel_name='account.general.ledger.report.account',
        inverse_name='report_id',
        string='Account Lines',
    )

    # Alias: line_ids points to same sub-records as account_line_ids
    # Using a plain One2many (not related) to avoid psycopg2 adaptation errors
    # that occur when 'related' tries to pass recordsets as SQL parameters.
    line_ids = fields.One2many(
        comodel_name='account.general.ledger.report.account',
        inverse_name='report_id',
        string='Lines',
    )

    def _compute_report_data(self):
        """Compute General Ledger report data.

        Builds the full General Ledger by iterating over the selected
        accounts and populating :attr:`account_line_ids` with one
        ``account.general.ledger.report.account`` per account, each
        containing nested ``account.general.ledger.report.line`` records
        for the individual transactions.

        Algorithm per account:

        1. Compute **opening balance** from all posted entries before
           ``date_from`` via ``_compute_account_balance``.
        2. Retrieve every ``account.move.line`` within ``[date_from,
           date_to]``, honouring partner and target-move filters.
        3. Accumulate a **running balance** starting from the opening
           balance.
        4. When *centralize* is enabled, group transactions by partner
           and append partner-level subtotal lines for drill-down
           convenience.
        5. Store **closing balance** = opening + total_debit - total_credit.

        The method writes via ORM ``Command`` operations so the data is
        persisted in the transient table and survives a page reload
        within the same session.
        """
        for report in self:
            report.currency_id = report.company_id.currency_id

            # Determine which accounts to include (Odoo 19.0: company_ids)
            domain = [('company_ids', 'in', report.company_id.ids)]

            if report.account_ids:
                domain.append(('id', 'in', report.account_ids.ids))

            if report.account_from:
                domain.append(('code', '>=', report.account_from))

            if report.account_to:
                domain.append(('code', '<=', report.account_to))

            accounts = self.env['account.account'].search(domain, order='code')

            # Build account lines using Command operations for ORM persistence
            account_cmds = [Command.clear()]

            for account in accounts:
                # Opening balance
                if report.include_initial_balance:
                    opening_balance = report._compute_account_balance(
                        account,
                        date_to=fields.Date.subtract(report.date_from, days=1),
                    ).get(account.id, {}).get('balance', 0.0)
                else:
                    opening_balance = 0.0

                # Build move line domain for this account
                move_line_domain = report._get_move_line_domain(
                    date_from=report.date_from,
                    date_to=report.date_to,
                    account_ids=[account.id],
                )

                # Apply partner filtering when specific partners are selected
                if report.partner_ids:
                    move_line_domain.append(
                        ('partner_id', 'in', report.partner_ids.ids),
                    )

                # Determine sort order based on user selection
                order_field = {
                    'date': 'date, id',
                    'ref': 'ref, date, id',
                    'name': 'name, date, id',
                }.get(report.sort_by, 'date, id')

                # When centralizing by partner, prepend partner sort to
                # group all transactions for the same partner together
                if report.centralize:
                    order_field = 'partner_id, ' + order_field

                move_lines = self.env['account.move.line'].search(
                    move_line_domain, order=order_field,
                )

                # Skip accounts with no activity if hiding zero balance
                if report.hide_zero_balance and not move_lines and opening_balance == 0:
                    continue

                # Aggregate totals
                total_debit = sum(move_lines.mapped('debit'))
                total_credit = sum(move_lines.mapped('credit'))
                closing_balance = opening_balance + total_debit - total_credit

                # Build nested transaction line Command.create() entries
                transaction_cmds = []
                running_balance = opening_balance

                if report.centralize and move_lines:
                    # Group transactions by partner with subtotals
                    transaction_cmds = report._build_centralized_lines(
                        move_lines, running_balance,
                    )
                else:
                    # Standard chronological transaction listing
                    for ml in move_lines:
                        running_balance += ml.debit - ml.credit
                        transaction_cmds.append(Command.create({
                            'move_line_id': ml.id,
                            'date': ml.date,
                            'journal_id': ml.journal_id.id,
                            'move_id': ml.move_id.id,
                            'ref': ml.ref or ml.move_id.ref,
                            'name': ml.name,
                            'partner_id': ml.partner_id.id,
                            'debit': ml.debit,
                            'credit': ml.credit,
                            'balance': running_balance,
                            'currency_id': report.currency_id.id,
                        }))

                # Create account line with embedded transaction lines
                account_cmds.append(Command.create({
                    'account_id': account.id,
                    'name': f"{account.code} - {account.name}",
                    'opening_balance': opening_balance,
                    'total_debit': total_debit,
                    'total_credit': total_credit,
                    'closing_balance': closing_balance,
                    'currency_id': report.currency_id.id,
                    'line_ids': transaction_cmds,
                }))

            report.account_line_ids = account_cmds

    def _build_centralized_lines(self, move_lines, running_balance):
        """Build transaction lines grouped by partner with subtotals.

        When the *centralize* option is active, transactions within an
        account are organised into partner groups.  Each group ends with
        a subtotal line whose :attr:`is_partner_subtotal` flag is
        ``True``, making it easy for the QWeb template to render
        distinct formatting.

        The *move_lines* recordset **must** already be sorted with
        ``partner_id`` as the primary key (handled by the caller which
        prepends ``partner_id`` to the ORDER BY clause).

        :param move_lines: ``account.move.line`` recordset sorted by
            ``partner_id`` first, then by the user-chosen sort field.
        :param running_balance: Opening balance carried forward into the
            first transaction line.
        :returns: list of ORM ``Command.create()`` dicts suitable for
            assignment to ``line_ids`` on an account section record.
        """
        self.ensure_one()
        transaction_cmds = []
        current_partner_id = None
        partner_debit = 0.0
        partner_credit = 0.0
        first_line = True

        for ml in move_lines:
            partner_id = ml.partner_id.id or False

            # Detect partner change — emit subtotal for previous group
            if not first_line and partner_id != current_partner_id:
                partner_name = (
                    self.env['res.partner'].browse(
                        current_partner_id,
                    ).display_name
                    if current_partner_id
                    else _('No Partner')
                )
                transaction_cmds.append(Command.create({
                    'date': False,
                    'name': _('Partner Subtotal: %s') % partner_name,
                    'partner_id': current_partner_id or False,
                    'debit': partner_debit,
                    'credit': partner_credit,
                    'balance': running_balance,
                    'currency_id': self.currency_id.id,
                    'is_partner_subtotal': True,
                }))
                partner_debit = 0.0
                partner_credit = 0.0

            first_line = False
            current_partner_id = partner_id
            running_balance += ml.debit - ml.credit
            partner_debit += ml.debit
            partner_credit += ml.credit

            transaction_cmds.append(Command.create({
                'move_line_id': ml.id,
                'date': ml.date,
                'journal_id': ml.journal_id.id,
                'move_id': ml.move_id.id,
                'ref': ml.ref or ml.move_id.ref,
                'name': ml.name,
                'partner_id': ml.partner_id.id,
                'debit': ml.debit,
                'credit': ml.credit,
                'balance': running_balance,
                'currency_id': self.currency_id.id,
            }))

        # Emit subtotal for the last partner group
        if not first_line:
            partner_name = (
                self.env['res.partner'].browse(
                    current_partner_id,
                ).display_name
                if current_partner_id
                else _('No Partner')
            )
            transaction_cmds.append(Command.create({
                'date': False,
                'name': _('Partner Subtotal: %s') % partner_name,
                'partner_id': current_partner_id or False,
                'debit': partner_debit,
                'credit': partner_credit,
                'balance': running_balance,
                'currency_id': self.currency_id.id,
                'is_partner_subtotal': True,
            }))

        return transaction_cmds

    def action_generate_report(self):
        """Generate and display the General Ledger report.

        Validates the mandatory date range, triggers the data
        computation pipeline, and returns an ``ir.actions.act_window``
        action that opens the populated report record in an inline form.

        :raises UserError: When ``date_from`` or ``date_to`` is missing.
        :returns: Window action dictionary.
        :rtype: dict
        """
        self.ensure_one()
        if not self.date_from or not self.date_to:
            raise UserError(_("Please specify the date range."))

        self._compute_report_data()

        return {
            'name': _('General Ledger: %s to %s') % (self.date_from, self.date_to),
            'type': 'ir.actions.act_window',
            'res_model': 'account.general.ledger.report',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'inline',
        }

    # -------------------------------------------------------------------------
    # XLSX EXPORT OVERRIDES
    # -------------------------------------------------------------------------

    def _get_xlsx_columns(self):
        """Return General Ledger specific column definitions for XLSX export.

        Overrides the base implementation to provide columns appropriate for
        the GL report structure: date, journal, reference, description,
        partner, debit, credit, and running balance.

        :returns: List of column definition dicts with ``header``, ``field``,
            ``width``, and ``style`` keys.
        :rtype: list[dict]
        """
        return [
            {'header': _('Date'), 'field': 'date', 'width': 12,
             'style': 'text'},
            {'header': _('Journal'), 'field': 'journal', 'width': 10,
             'style': 'text'},
            {'header': _('Reference'), 'field': 'ref', 'width': 20,
             'style': 'text'},
            {'header': _('Description'), 'field': 'name', 'width': 35,
             'style': 'text'},
            {'header': _('Partner'), 'field': 'partner', 'width': 25,
             'style': 'text'},
            {'header': _('Debit'), 'field': 'debit', 'width': 18,
             'style': 'monetary'},
            {'header': _('Credit'), 'field': 'credit', 'width': 18,
             'style': 'monetary'},
            {'header': _('Balance'), 'field': 'balance', 'width': 18,
             'style': 'monetary'},
        ]

    def _get_xlsx_data(self):
        """Return General Ledger data rows for XLSX export.

        Overrides the base implementation to produce a flat list of rows
        that interleave account-section headers (with opening/closing
        balances) and individual transaction lines.

        Account header rows have ``level=0`` and ``is_total=True``.
        Transaction rows have ``level=1`` and ``is_total=False``.
        Partner subtotal rows (when centralizing) have ``level=1`` and
        ``is_total=True``.

        :returns: List of row dicts keyed by the column ``field`` values
            from :meth:`_get_xlsx_columns`.
        :rtype: list[dict]
        """
        self.ensure_one()
        rows = []
        for acct_line in self.account_line_ids:
            # Account header row with opening balance
            rows.append({
                'date': '',
                'journal': '',
                'ref': '',
                'name': acct_line.name or '',
                'partner': '',
                'debit': acct_line.total_debit,
                'credit': acct_line.total_credit,
                'balance': acct_line.opening_balance,
                'level': 0,
                'is_total': True,
            })

            # Individual transaction lines
            for txn in acct_line.line_ids:
                rows.append({
                    'date': str(txn.date) if txn.date else '',
                    'journal': (
                        txn.journal_id.code if txn.journal_id else ''
                    ),
                    'ref': txn.ref or '',
                    'name': txn.name or '',
                    'partner': (
                        txn.partner_id.display_name
                        if txn.partner_id else ''
                    ),
                    'debit': txn.debit,
                    'credit': txn.credit,
                    'balance': txn.balance,
                    'level': 1,
                    'is_total': bool(txn.is_partner_subtotal),
                })

            # Closing balance row
            rows.append({
                'date': '',
                'journal': '',
                'ref': '',
                'name': _('Closing Balance'),
                'partner': '',
                'debit': acct_line.total_debit,
                'credit': acct_line.total_credit,
                'balance': acct_line.closing_balance,
                'level': 0,
                'is_total': True,
            })

        return rows


class GeneralLedgerReportAccount(models.TransientModel):
    """General Ledger account-level section record.

    Each record represents one account in the ledger and holds the
    aggregated opening balance, total debits/credits, closing balance,
    and a one-to-many collection of individual transaction lines
    (``account.general.ledger.report.line``).
    """

    _name = 'account.general.ledger.report.account'
    _description = 'General Ledger Report Account'
    _order = 'name'

    report_id = fields.Many2one(
        comodel_name='account.general.ledger.report',
        string='Report',
        ondelete='cascade',
    )
    account_id = fields.Many2one('account.account', string='Account')
    name = fields.Char(string='Account Name')
    opening_balance = fields.Monetary(string='Opening Balance', currency_field='currency_id')
    total_debit = fields.Monetary(string='Total Debit', currency_field='currency_id')
    total_credit = fields.Monetary(string='Total Credit', currency_field='currency_id')
    closing_balance = fields.Monetary(string='Closing Balance', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', string='Currency')
    line_ids = fields.One2many(
        comodel_name='account.general.ledger.report.line',
        inverse_name='account_line_id',
        string='Transactions',
    )

    def action_drilldown(self):
        """Open the underlying journal items for this account section.

        Delegates to the parent report's ``action_drilldown`` method,
        passing both ``date_from`` and ``date_to`` so the resulting
        list view is filtered to the exact reporting period.

        :returns: ``ir.actions.act_window`` action dictionary filtered
            to ``account.move.line`` records for this account.
        :rtype: dict
        """
        self.ensure_one()
        return self.report_id.action_drilldown(
            account_id=self.account_id.id,
            date_from=self.report_id.date_from,
            date_to=self.report_id.date_to,
        )


class GeneralLedgerReportLine(models.TransientModel):
    """General Ledger individual transaction line.

    Each record corresponds to a single ``account.move.line`` within
    the reporting period for the parent account section.  The
    ``balance`` field carries a **running balance** accumulated from
    the account's opening balance through the current line.

    When the *centralize* option is enabled on the parent report,
    additional partner-subtotal rows are generated with
    ``is_partner_subtotal = True`` and without a linked
    ``move_line_id``.
    """

    _name = 'account.general.ledger.report.line'
    _description = 'General Ledger Report Transaction'
    # Order by id to preserve the creation sequence set by
    # _compute_report_data, which already sorts lines according to
    # the user's sort_by preference (date/ref/name).  Using 'date, id'
    # would override non-date sort choices.
    _order = 'id'

    account_line_id = fields.Many2one(
        comodel_name='account.general.ledger.report.account',
        string='Account Line',
        ondelete='cascade',
    )
    move_line_id = fields.Many2one('account.move.line', string='Journal Item')
    date = fields.Date(string='Date')
    journal_id = fields.Many2one('account.journal', string='Journal')
    move_id = fields.Many2one('account.move', string='Journal Entry')
    ref = fields.Char(string='Reference')
    name = fields.Char(string='Description')
    partner_id = fields.Many2one('res.partner', string='Partner')
    debit = fields.Monetary(string='Debit', currency_field='currency_id')
    credit = fields.Monetary(string='Credit', currency_field='currency_id')
    balance = fields.Monetary(string='Running Balance', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', string='Currency')
    is_partner_subtotal = fields.Boolean(
        string='Is Partner Subtotal',
        default=False,
        help="Marks this line as a partner-group subtotal generated "
             "by the centralize option.  These lines have no linked "
             "move_line_id and carry the sum of debit/credit for the "
             "partner within the account.",
    )

    def action_open_move(self):
        """Open the source journal entry in a form view.

        Per FR-007 acceptance criteria:
            *"When I click on a line item amount, then I am navigated
            to a filtered view of the underlying journal entries."*

        :returns: ``ir.actions.act_window`` action pointing at the
            ``account.move`` record that originated this line.
        :rtype: dict
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.move_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
