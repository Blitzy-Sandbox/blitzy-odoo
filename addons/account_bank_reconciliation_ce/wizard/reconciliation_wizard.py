# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Reconciliation Wizard

Manual bank reconciliation interface wizard for FEATURE-002 BR-003.
Provides the primary user interface for:
  - Loading unreconciled bank statement lines for a selected journal/date range
  - Triggering the algorithmic matching engine to propose matches
  - Displaying match suggestions with confidence badges (High/Medium/Low)
  - Supporting manual match/unmatch, partial match with write-off, batch confirm

Design follows the TransientModel pattern from
``addons/account_financial_report_ce/wizard/financial_report_wizard.py``
and the reconciliation flow from
``addons/account/wizard/account_payment_register.py``.

Multi-company isolation: all queries include company_id scoping.
Zero Enterprise dependencies.
"""

import logging

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class ReconciliationWizard(models.TransientModel):
    """Bank Reconciliation Wizard — manual reconciliation interface for BR-003.

    Loads unreconciled bank statement lines for a selected bank/cash journal,
    triggers the matching engine, displays suggestions with confidence scores,
    and provides match/unmatch/partial-match/batch-confirm operations.
    """

    _name = 'account.reconciliation.wizard'
    _description = 'Bank Reconciliation Wizard'
    _check_company_auto = True

    # -------------------------------------------------------------------------
    # Core / Hidden Fields
    # -------------------------------------------------------------------------

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )

    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency',
        related='company_id.currency_id',
        readonly=True,
    )

    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('in_progress', 'In Progress'),
            ('done', 'Done'),
        ],
        string='Status',
        default='draft',
        required=True,
        copy=False,
    )

    # -------------------------------------------------------------------------
    # Journal and Date Filters
    # -------------------------------------------------------------------------

    journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Bank Journal',
        required=True,
        domain="[('type', 'in', ('bank', 'cash'))]",
        check_company=True,
        help="Select the bank or cash journal to reconcile.",
    )

    date_from = fields.Date(
        string='From Date',
        help="Optional start date filter for statement lines.",
    )

    date_to = fields.Date(
        string='To Date',
        default=fields.Date.context_today,
        help="Optional end date filter for statement lines.",
    )

    # -------------------------------------------------------------------------
    # Statement Lines (Left Panel)
    # -------------------------------------------------------------------------

    statement_line_ids = fields.Many2many(
        comodel_name='account.bank.statement.line',
        string='Statement Lines',
        compute='_compute_statement_lines',
        readonly=True,
    )

    unreconciled_count = fields.Integer(
        string='Unreconciled Lines',
        compute='_compute_statement_lines',
    )

    selected_line_id = fields.Many2one(
        comodel_name='account.bank.statement.line',
        string='Selected Statement Line',
        help="The currently selected statement line for manual operations.",
    )

    # -------------------------------------------------------------------------
    # Matching Suggestions (Right Panel)
    # -------------------------------------------------------------------------

    match_ids = fields.Many2many(
        comodel_name='account.reconciliation.matching',
        relation='reconciliation_wizard_matching_rel',
        column1='wizard_id',
        column2='matching_id',
        string='Match Suggestions',
    )

    selected_match_ids = fields.Many2many(
        comodel_name='account.reconciliation.matching',
        string='Selected Matches',
        compute='_compute_selected_matches',
    )

    # -------------------------------------------------------------------------
    # Write-Off / Partial Match Controls
    # -------------------------------------------------------------------------

    write_off_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Write-Off Account',
        domain="[('account_type', '!=', 'off_balance')]",
        check_company=True,
        help=(
            "Account used to book the difference when performing a partial "
            "match.  Leave empty for exact matches."
        ),
    )

    write_off_label = fields.Char(
        string='Write-Off Label',
        default='Write-Off',
        help="Label applied to the write-off journal entry line.",
    )

    write_off_amount = fields.Monetary(
        string='Write-Off Amount',
        currency_field='currency_id',
        compute='_compute_write_off_amount',
        readonly=True,
        help=(
            "Computed difference amount that will be booked as a write-off "
            "entry.  This is the gap between the statement line amount and "
            "the total of the selected matching journal entries."
        ),
    )

    tolerance_percentage = fields.Float(
        string='Tolerance %',
        digits=(5, 2),
        default=0.0,
        help=(
            "Maximum acceptable percentage difference between the statement "
            "line amount and the matched journal entry amount.  Differences "
            "within this tolerance are automatically written off."
        ),
    )

    # =========================================================================
    # Compute Methods
    # =========================================================================

    @api.depends('journal_id', 'date_from', 'date_to', 'company_id')
    def _compute_statement_lines(self):
        """Load unreconciled bank statement lines for the selected journal
        and optional date range.

        Multi-company isolation: only lines belonging to the wizard's company
        are returned.
        """
        for wizard in self:
            if not wizard.journal_id:
                wizard.statement_line_ids = self.env['account.bank.statement.line']
                wizard.unreconciled_count = 0
                continue

            domain = [
                ('journal_id', '=', wizard.journal_id.id),
                ('company_id', '=', wizard.company_id.id),
                ('is_reconciled', '=', False),
            ]

            if wizard.date_from:
                domain.append(('date', '>=', wizard.date_from))
            if wizard.date_to:
                domain.append(('date', '<=', wizard.date_to))

            lines = self.env['account.bank.statement.line'].search(domain)
            wizard.statement_line_ids = lines
            wizard.unreconciled_count = len(lines)

    @api.depends('match_ids.is_selected')
    def _compute_selected_matches(self):
        """Collect matches the user has toggled as selected."""
        for wizard in self:
            wizard.selected_match_ids = wizard.match_ids.filtered('is_selected')

    @api.depends(
        'selected_line_id',
        'selected_match_ids',
        'selected_match_ids.matched_amount',
    )
    def _compute_write_off_amount(self):
        """Calculate the write-off amount as the difference between the
        selected statement line's amount and the total of selected matching
        journal entry amounts.
        """
        for wizard in self:
            if wizard.selected_line_id and wizard.selected_match_ids:
                st_amount = abs(wizard.selected_line_id.amount)
                match_total = sum(abs(m.matched_amount) for m in wizard.selected_match_ids)
                wizard.write_off_amount = st_amount - match_total
            else:
                wizard.write_off_amount = 0.0

    # =========================================================================
    # Constraint / Onchange
    # =========================================================================

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        """Ensure date_from <= date_to when both are set."""
        for wizard in self:
            if wizard.date_from and wizard.date_to and wizard.date_from > wizard.date_to:
                raise ValidationError(
                    _("The start date must be earlier than or equal to the end date."),
                )

    @api.onchange('journal_id')
    def _onchange_journal_id(self):
        """Reset dependent fields when the journal changes."""
        self.selected_line_id = False
        self.match_ids = [(5, 0, 0)]

    # =========================================================================
    # Action Methods
    # =========================================================================

    def action_find_matches(self):
        """Trigger the algorithmic matching engine for all unreconciled
        statement lines in the current wizard scope.

        Delegates to ``account.reconciliation.matching.find_matches()``
        and additionally evaluates enhanced reconciliation rules from
        ``account.reconcile.model`` in priority order.

        Updates wizard state to 'in_progress'.
        """
        self.ensure_one()
        if not self.journal_id:
            raise UserError(_("Please select a bank journal before searching for matches."))

        MatchingEngine = self.env['account.reconciliation.matching']

        # Remove previous suggestions that were not confirmed
        old_matches = self.match_ids.filtered(lambda m: m.state == 'proposed')
        if old_matches:
            old_matches.unlink()

        # Find new matches for all unreconciled statement lines
        new_matches = MatchingEngine.find_matches(
            statement_lines=self.statement_line_ids,
            journal_id=self.journal_id.id,
        )

        # Apply reconciliation rules in priority order
        self._apply_rules(self.statement_line_ids)

        # Link new matches to this wizard via Many2many
        if new_matches:
            self.match_ids = [(4, m_id) for m_id in new_matches.ids]

        self.state = 'in_progress'

        _logger.info(
            "Matching engine found %d suggestions for %d statement lines "
            "in journal '%s'.",
            len(new_matches) if new_matches else 0,
            self.unreconciled_count,
            self.journal_id.display_name,
        )

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_confirm_selected(self):
        """Confirm the selected matches and execute the reconciliation
        for the currently selected statement line.

        If the match is exact or within tolerance, a full reconciliation
        is created.  If a write-off is needed, a write-off journal entry
        line is generated.
        """
        self.ensure_one()
        if not self.selected_line_id:
            raise UserError(_("Please select a statement line first."))
        if not self.selected_match_ids:
            raise UserError(_("Please select at least one matching journal entry."))

        self._execute_reconciliation(
            st_line=self.selected_line_id,
            match_records=self.selected_match_ids,
        )

        # Reset selection
        self.selected_line_id = False

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_unmatch(self):
        """Remove existing reconciliation for the selected statement line
        and reset its status to unreconciled.
        """
        self.ensure_one()
        if not self.selected_line_id:
            raise UserError(_("Please select a statement line to unmatch."))

        st_line = self.selected_line_id
        move = st_line.move_id

        # Unreconcile all linked partial reconciliations
        if move and move.line_ids:
            partials = move.line_ids.mapped('matched_debit_ids') | \
                       move.line_ids.mapped('matched_credit_ids')
            if partials:
                partials.unlink()
                _logger.info(
                    "Unmatched statement line '%s' — removed %d partial "
                    "reconciliation(s).",
                    st_line.display_name, len(partials),
                )

        # Reset CE tracking fields
        if hasattr(st_line, 'reconciliation_status'):
            st_line.write({
                'reconciliation_status': 'unreconciled',
                'matching_confidence': 0.0,
            })

        # Update matching records
        related_matches = self.match_ids.filtered(
            lambda m: m.statement_line_id == st_line,
        )
        if related_matches:
            related_matches.write({'state': 'rejected'})

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_partial_match(self):
        """Open the partial reconciliation helper wizard pre-populated
        with the selected statement line and matching journal entries.
        """
        self.ensure_one()
        if not self.selected_line_id:
            raise UserError(_("Please select a statement line for partial matching."))

        PartialHelper = self.env['account.reconciliation.partial.helper']

        move_line_ids = self.selected_match_ids.mapped('move_line_id').ids

        helper = PartialHelper.create({
            'company_id': self.company_id.id,
            'statement_line_id': self.selected_line_id.id,
            'move_line_ids': [(6, 0, move_line_ids)],
            'write_off_account_id': self.write_off_account_id.id if self.write_off_account_id else False,
            'write_off_label': self.write_off_label or _('Write-Off'),
            'tolerance_percentage': self.tolerance_percentage,
        })

        return {
            'type': 'ir.actions.act_window',
            'name': _('Partial Reconciliation'),
            'res_model': 'account.reconciliation.partial.helper',
            'res_id': helper.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_batch_confirm(self):
        """Automatically confirm all high-confidence matches (score >= 90%)
        in a single batch operation.
        """
        self.ensure_one()

        high_confidence_matches = self.match_ids.filtered(
            lambda m: m.confidence_score >= 90.0 and m.state == 'proposed',
        )

        if not high_confidence_matches:
            raise UserError(_(
                "No high-confidence matches (score >= 90%%) found for batch "
                "confirmation.",
            ))

        confirmed_count = 0
        error_count = 0

        # Group matches by statement line for proper reconciliation
        matches_by_line = {}
        for match in high_confidence_matches:
            line = match.statement_line_id
            if line not in matches_by_line:
                matches_by_line[line] = self.env['account.reconciliation.matching']
            matches_by_line[line] |= match

        for st_line, matches in matches_by_line.items():
            try:
                self._execute_reconciliation(
                    st_line=st_line,
                    match_records=matches,
                )
                confirmed_count += 1
            except (ValueError, TypeError, KeyError) as exc:
                _logger.warning(
                    "Batch confirm failed for statement line '%s': %s",
                    st_line.display_name, exc,
                )
                error_count += 1

        self.state = 'in_progress'

        _logger.info(
            "Batch confirm completed: %d confirmed, %d errors.",
            confirmed_count, error_count,
        )

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    # =========================================================================
    # Internal Helpers
    # =========================================================================

    def _execute_reconciliation(self, st_line, match_records):
        """Perform the actual reconciliation between a bank statement line
        and the matched journal entry move lines.

        Creates ``account.partial.reconcile`` records linking the statement
        line's underlying ``account.move.line`` (via ``account.move``) with
        the matched counterpart lines.

        Follows the same pattern used by
        ``addons/account/wizard/account_payment_register.py``.

        :param st_line: ``account.bank.statement.line`` record
        :param match_records: ``account.reconciliation.matching`` recordset
        """
        move = st_line.move_id
        if not move:
            raise UserError(_(
                "Statement line '%s' has no associated journal entry.",
                st_line.display_name,
            ))

        # Identify the liquidity line(s) on the statement line's move
        liquidity_lines = move.line_ids.filtered(
            lambda ml: ml.account_id == st_line.journal_id.default_account_id,
        )

        if not liquidity_lines:
            # Fallback: use lines with matching debit/credit
            liquidity_lines = move.line_ids.filtered(
                lambda ml: ml.account_id.account_type in (
                    'asset_cash', 'liability_credit_card',
                ),
            )

        if not liquidity_lines:
            raise UserError(_(
                "Cannot find a liquidity line on the journal entry for "
                "statement line '%s'.",
                st_line.display_name,
            ))

        counterpart_lines = match_records.mapped('move_line_id')

        # Determine write-off need
        st_amount = sum(liquidity_lines.mapped('balance'))
        counterpart_amount = sum(counterpart_lines.mapped('balance'))
        difference = st_amount + counterpart_amount

        lines_to_reconcile = liquidity_lines | counterpart_lines

        # Handle write-off if needed and write-off account is set
        if abs(difference) > 0.01 and self.write_off_account_id:
            write_off_vals = {
                'name': self.write_off_label or _('Write-Off'),
                'account_id': self.write_off_account_id.id,
                'balance': -difference,
                'currency_id': self.currency_id.id,
                'partner_id': st_line.partner_id.id if st_line.partner_id else False,
            }
            # Create write-off line on the statement line's move
            move.write({
                'line_ids': [Command.create(write_off_vals)],
            })
            # Re-fetch lines after write-off creation
            wo_line = move.line_ids.filtered(
                lambda ml: ml.account_id == self.write_off_account_id
                and abs(ml.balance - (-difference)) < 0.01,
            )
            if wo_line:
                lines_to_reconcile |= wo_line[:1]

        # Trigger reconciliation via the ORM
        lines_to_reconcile.reconcile()

        # Update match records state
        match_records.write({'state': 'confirmed'})

        # Update statement line CE tracking fields
        if hasattr(st_line, 'reconciliation_status'):
            best_score = max(match_records.mapped('confidence_score'), default=0.0)
            st_line.write({
                'reconciliation_status': 'reconciled',
                'matching_confidence': best_score,
            })

        _logger.info(
            "Reconciled statement line '%s' with %d journal entr%s.",
            st_line.display_name,
            len(counterpart_lines),
            'y' if len(counterpart_lines) == 1 else 'ies',
        )

    def _apply_rules(self, statement_lines):
        """Evaluate enhanced reconciliation rules from
        ``account.reconcile.model`` (with CE extensions) against the given
        statement lines in priority order.

        :param statement_lines: ``account.bank.statement.line`` recordset
        """
        if not statement_lines:
            return

        ReconcileModel = self.env['account.reconcile.model']

        # Retrieve rules applicable to this company, ordered by priority
        domain = [
            '|',
            ('company_id', '=', self.company_id.id),
            ('company_id', '=', False),
        ]

        # Use priority ordering if the CE extension provides it
        order = 'sequence, id'
        if hasattr(ReconcileModel, 'priority'):
            order = 'priority, sequence, id'

        rules = ReconcileModel.search(domain, order=order)

        if not rules:
            _logger.debug("No reconciliation rules found for company %s.", self.company_id.name)
            return

        _logger.info(
            "Applying %d reconciliation rule(s) to %d statement lines.",
            len(rules), len(statement_lines),
        )

        for rule in rules:
            if hasattr(rule, 'evaluate_rule'):
                for st_line in statement_lines.filtered(
                    lambda ml: not ml.is_reconciled,
                ):
                    try:
                        rule.evaluate_rule(st_line)
                    except (ValueError, TypeError, KeyError) as exc:
                        _logger.warning(
                            "Rule '%s' evaluation failed for line '%s': %s",
                            rule.name, st_line.display_name, exc,
                        )
