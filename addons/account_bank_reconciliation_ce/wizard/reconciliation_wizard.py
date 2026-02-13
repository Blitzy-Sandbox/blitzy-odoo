# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Bank reconciliation wizard for manual review and confirmation of match suggestions.

Provides the primary manual reconciliation interface for FEATURE-002 BR-003:
  - Loads unreconciled bank statement lines for a selected journal/date range.
  - Triggers the algorithmic matching engine to propose matches.
  - Displays match suggestions with confidence badges (High/Medium/Low).
  - Supports manual match/unmatch, partial match with write-off, batch confirm.

Design follows the TransientModel pattern from
``addons/account_financial_report_ce/wizard/financial_report_wizard.py``
and the reconciliation flow from
``addons/account/wizard/account_payment_register.py``.

Multi-company isolation: all queries include company_id scoping per Section 0.7.3.
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

    Integration points:
      - ``account.reconciliation.matching``: algorithmic matching engine
        (``find_matches()``, ``CONFIDENCE_HIGH``)
      - ``account.reconciliation.partial.helper``: reconciliation execution
        (``action_reconcile()``, ``action_unreconcile()``)
      - ``account.reconcile.model`` (CE extensions): enhanced rule evaluation
        (``get_ordered_rules()``, ``evaluate_rule()``)
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
        string='Match Suggestions',
        compute='_compute_matches',
        help=(
            "Matching suggestions from the algorithmic engine and rule "
            "evaluation, including proposed and confirmed entries."
        ),
    )

    selected_match_ids = fields.Many2many(
        comodel_name='account.reconciliation.matching',
        relation='reconciliation_wizard_match_sel_rel',
        column1='wizard_id',
        column2='matching_id',
        string='Selected Matches',
        help="User-selected matching records for the current statement line.",
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

    write_off_amount = fields.Float(
        string='Write-Off Amount',
        digits=(16, 2),
        compute='_compute_write_off_amount',
        readonly=True,
        help=(
            "Computed difference between the selected statement line amount "
            "and the total of the selected matching journal entry amounts."
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
        are returned.  Uses the native ``is_reconciled`` field from
        ``account.bank.statement.line`` to identify pending lines, along with
        the CE extension field ``reconciliation_status`` for display badges
        when available.
        """
        StLine = self.env['account.bank.statement.line']
        for wizard in self:
            if not wizard.journal_id:
                wizard.statement_line_ids = StLine
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

            lines = StLine.search(domain, order='date asc, id asc')
            wizard.statement_line_ids = lines
            wizard.unreconciled_count = len(lines)

            _logger.debug(
                "Loaded %d unreconciled statement lines for journal '%s' "
                "(company: %s).",
                len(lines),
                wizard.journal_id.display_name,
                wizard.company_id.name,
            )

    @api.depends('statement_line_ids')
    def _compute_matches(self):
        """Load existing ``account.reconciliation.matching`` records linked
        to the statement lines currently in the wizard scope.

        Retrieves all proposed and confirmed matching suggestions so the
        user can review pending proposals and see previously confirmed
        matches.  Rejected matches are excluded.
        """
        MatchingModel = self.env['account.reconciliation.matching']
        for wizard in self:
            if wizard.statement_line_ids:
                matches = MatchingModel.search([
                    ('statement_line_id', 'in', wizard.statement_line_ids.ids),
                    ('state', 'in', ('proposed', 'confirmed')),
                ])
                wizard.match_ids = matches
            else:
                wizard.match_ids = MatchingModel

    @api.depends(
        'selected_line_id',
        'selected_match_ids',
        'selected_match_ids.matched_amount',
    )
    def _compute_write_off_amount(self):
        """Calculate the write-off amount as the difference between the
        selected statement line's amount and the total of selected matching
        journal entry amounts.

        A positive value indicates the statement line amount exceeds the
        matched total; a negative value indicates the opposite.
        """
        for wizard in self:
            if wizard.selected_line_id and wizard.selected_match_ids:
                st_amount = abs(wizard.selected_line_id.amount)
                match_total = sum(
                    abs(m.matched_amount) for m in wizard.selected_match_ids
                )
                wizard.write_off_amount = st_amount - match_total
            else:
                wizard.write_off_amount = 0.0

    # =========================================================================
    # Constraints / Onchange
    # =========================================================================

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        """Ensure date_from <= date_to when both are set."""
        for wizard in self:
            if (wizard.date_from and wizard.date_to
                    and wizard.date_from > wizard.date_to):
                raise ValidationError(
                    _("The start date must be earlier than or equal to "
                      "the end date."),
                )

    @api.onchange('journal_id')
    def _onchange_journal_id(self):
        """Reset dependent fields when the journal changes.

        Clears the current selection and reverts the wizard state to draft
        so the user must re-run the matching engine for the new journal.
        """
        self.selected_line_id = False
        self.selected_match_ids = [Command.clear()]
        if self.state != 'draft':
            self.state = 'draft'

    # =========================================================================
    # Action Methods
    # =========================================================================

    def action_find_matches(self):
        """Trigger the algorithmic matching engine for all unreconciled
        statement lines in the current wizard scope.

        Workflow:
          1. Clear previous proposed matching suggestions from the database.
          2. Call ``account.reconciliation.matching.find_matches()`` to
             generate new match proposals with confidence scores.
          3. Evaluate enhanced reconciliation rules from
             ``account.reconcile.model`` (CE extensions) in priority order
             to boost confidence and auto-select high-quality matches.
          4. Update wizard state to ``in_progress``.

        :return: window action to refresh the wizard form.
        :raises UserError: if no journal is selected.
        """
        self.ensure_one()
        if not self.journal_id:
            raise UserError(
                _("Please select a bank journal before searching for matches."),
            )

        MatchingModel = self.env['account.reconciliation.matching']

        # 1. Clear old proposed matches that may be stale.  We search the
        #    database directly to avoid stale-cache issues with computed fields.
        old_matches = MatchingModel.search([
            ('statement_line_id', 'in', self.statement_line_ids.ids),
            ('state', '=', 'proposed'),
        ])
        if old_matches:
            _logger.debug(
                "Removing %d stale proposed matches before re-running engine.",
                len(old_matches),
            )
            old_matches.unlink()

        # Clear wizard selection state
        self.selected_match_ids = [Command.clear()]

        # 2. Run the algorithmic matching engine
        unreconciled = self.statement_line_ids.filtered(
            lambda line: not line.is_reconciled,
        )
        new_matches = MatchingModel.browse()  # empty recordset default
        if unreconciled:
            new_matches = MatchingModel.find_matches(
                unreconciled, self.journal_id.id,
            )

        # 3. Apply reconciliation rules in priority order
        if unreconciled:
            self._apply_rules(unreconciled)

        # 4. Transition state
        self.state = 'in_progress'

        _logger.info(
            "Matching engine found %d suggestion(s) for %d unreconciled "
            "line(s) in journal '%s'.",
            len(new_matches),
            len(unreconciled),
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
        """Confirm the selected matches and execute the reconciliation for
        the currently selected statement line.

        Decision logic:
          - **Exact match** (zero difference) or **within tolerance**:
            directly execute reconciliation via ``_execute_reconciliation()``.
          - **Write-off needed** (difference beyond tolerance with write-off
            account set): reconciliation includes a write-off entry via the
            ``PartialReconcileHelper``.
          - **No write-off account**: raises ``UserError`` asking user to
            set one or use partial match instead.

        :return: window action to refresh the wizard form.
        :raises UserError: if no line or no matches are selected, or if a
                           write-off is needed but no account is configured.
        """
        self.ensure_one()
        if not self.selected_line_id:
            raise UserError(_("Please select a statement line first."))
        if not self.selected_match_ids:
            raise UserError(
                _("Please select at least one matching journal entry."),
            )

        st_line = self.selected_line_id
        match_records = self.selected_match_ids

        # Determine if write-off is needed
        currency = self.currency_id or self.env.company.currency_id
        st_amount = abs(st_line.amount)
        match_total = sum(abs(m.matched_amount) for m in match_records)
        difference = st_amount - match_total

        needs_write_off = not currency.is_zero(difference)
        within_tolerance = False

        if needs_write_off and self.tolerance_percentage > 0 and st_amount > 0:
            threshold = st_amount * (self.tolerance_percentage / 100.0)
            within_tolerance = abs(difference) <= threshold

        if needs_write_off and not within_tolerance and not self.write_off_account_id:
            raise UserError(
                _("A write-off is required but no Write-Off Account is set. "
                  "Please configure a Write-Off Account or use "
                  "'Partial Match' instead."),
            )

        self._execute_reconciliation(st_line, match_records)

        # Clear selection for next statement line
        self.selected_line_id = False
        self.selected_match_ids = [Command.clear()]

        _logger.info(
            "Confirmed reconciliation for statement line '%s' with "
            "%d match(es).",
            st_line.display_name, len(match_records),
        )

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

        Delegates to ``PartialReconcileHelper.action_unreconcile()`` which
        handles:
          - Removing partial and full reconciliation records via the native
            ``action_undo_reconciliation()`` on the statement line.
          - Resetting CE tracking fields (``reconciliation_status``,
            ``matching_confidence``) to their unreconciled defaults.

        Related matching suggestions are transitioned to ``rejected`` state
        to maintain the audit trail required by BR-003.

        :return: window action to refresh the wizard form.
        :raises UserError: if no statement line is selected.
        """
        self.ensure_one()
        if not self.selected_line_id:
            raise UserError(
                _("Please select a statement line to unmatch."),
            )

        st_line = self.selected_line_id

        # Delegate unreconciliation to the PartialReconcileHelper which
        # handles native undo mechanics and CE tracking field resets.
        PartialHelper = self.env['account.reconciliation.partial.helper']
        # Satisfy the required move_line_ids field using the statement
        # line's own journal entry lines as a reference.
        ref_line_ids = (
            st_line.move_id.line_ids.ids if st_line.move_id else []
        )
        helper = PartialHelper.create({
            'company_id': self.company_id.id,
            'statement_line_id': st_line.id,
            'move_line_ids': [Command.set(ref_line_ids)],
        })
        helper.action_unreconcile()

        # Mark related matching records as rejected for audit trail
        related_matches = self.env['account.reconciliation.matching'].search([
            ('statement_line_id', '=', st_line.id),
            ('state', 'in', ('proposed', 'confirmed')),
        ])
        if related_matches:
            related_matches.write({'state': 'rejected'})

        _logger.info(
            "Unmatched statement line '%s' — %d matching record(s) "
            "rejected.",
            st_line.display_name, len(related_matches),
        )

        # Reset selection
        self.selected_line_id = False
        self.selected_match_ids = [Command.clear()]

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

        The helper wizard provides fine-grained control over:
          - Which counterpart lines to include
          - Write-off account and label configuration
          - Tolerance percentage for auto-write-off

        :return: window action opening the ``PartialReconcileHelper`` form.
        :raises UserError: if no statement line is selected.
        """
        self.ensure_one()
        if not self.selected_line_id:
            raise UserError(
                _("Please select a statement line for partial matching."),
            )

        PartialHelper = self.env['account.reconciliation.partial.helper']
        move_line_ids = self.selected_match_ids.mapped('move_line_id').ids

        helper_vals = {
            'company_id': self.company_id.id,
            'statement_line_id': self.selected_line_id.id,
            'move_line_ids': [Command.set(move_line_ids)],
            'tolerance_percentage': self.tolerance_percentage,
        }

        # Pre-populate write-off configuration if set on the wizard
        if self.write_off_account_id:
            helper_vals['write_off_account_id'] = self.write_off_account_id.id
        if self.write_off_label:
            helper_vals['write_off_label'] = self.write_off_label

        helper = PartialHelper.create(helper_vals)

        return {
            'type': 'ir.actions.act_window',
            'name': _('Partial Reconciliation'),
            'res_model': 'account.reconciliation.partial.helper',
            'res_id': helper.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_batch_confirm(self):
        """Automatically confirm all high-confidence matches in a single
        batch operation.

        Uses the ``CONFIDENCE_HIGH`` threshold (90%) from the matching
        engine to identify auto-confirmable matches.  Each confirmed match
        triggers the full reconciliation flow via
        ``_execute_reconciliation()``.

        Matches are grouped by statement line to handle one-to-many matching
        scenarios correctly.

        :return: window action refreshing the wizard form with the result
                 summary logged.
        :raises UserError: if no high-confidence matches are found.
        """
        self.ensure_one()

        MatchingModel = self.env['account.reconciliation.matching']
        # Use the CONFIDENCE_HIGH threshold from the matching engine rather
        # than a hard-coded value to stay in sync with engine constants.
        high_threshold = MatchingModel.CONFIDENCE_HIGH

        high_confidence_matches = self.match_ids.filtered(
            lambda m: (m.confidence_score >= high_threshold
                       and m.state == 'proposed'),
        )

        if not high_confidence_matches:
            raise UserError(
                _("No high-confidence matches (score >= %(threshold)s%%) "
                  "found for batch confirmation.")
                % {'threshold': int(high_threshold)},
            )

        # Group matches by statement line for proper reconciliation
        matches_by_line = {}
        for match in high_confidence_matches:
            line = match.statement_line_id
            if line not in matches_by_line:
                matches_by_line[line] = MatchingModel.browse()
            matches_by_line[line] |= match

        confirmed_count = 0
        error_count = 0

        for st_line, matches in matches_by_line.items():
            # Log per-line details including confidence_level for audit
            best_match = max(
                matches,
                key=lambda m: m.confidence_score,
                default=None,
            )
            best_score = (
                best_match.confidence_score if best_match else 0.0
            )
            best_level = (
                best_match.confidence_level if best_match else 'unknown'
            )

            _logger.debug(
                "Batch confirm: processing line '%s' with %d match(es) "
                "(best confidence: %.1f%%, level: %s).",
                st_line.display_name, len(matches),
                best_score, best_level,
            )

            try:
                self._execute_reconciliation(st_line, matches)
                confirmed_count += 1
            except (UserError, ValidationError, ValueError, TypeError) as exc:
                _logger.warning(
                    "Batch confirm failed for statement line '%s': %s",
                    st_line.display_name, exc,
                )
                error_count += 1

        # Update wizard state based on remaining work
        remaining = self.match_ids.filtered(
            lambda m: m.state == 'proposed',
        )
        self.state = 'done' if not remaining else 'in_progress'

        _logger.info(
            "Batch confirm completed: %d confirmed, %d error(s), "
            "%d remaining proposed match(es).",
            confirmed_count, error_count, len(remaining),
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

        Delegates to ``PartialReconcileHelper.action_reconcile()`` which
        handles all reconciliation mechanics including:
          - Identifying suspense/counterpart lines on the statement move
          - Creating ``account.partial.reconcile`` records
          - Handling write-off entries when difference exists
          - Multi-currency difference resolution

        Follows the reconciliation pattern established by
        ``addons/account/wizard/account_payment_register.py``.

        After reconciliation, updates matching record states to ``confirmed``
        and refreshes the statement line's ``matching_confidence`` CE tracking
        field with the best match score.

        :param st_line: ``account.bank.statement.line`` singleton
        :param match_records: ``account.reconciliation.matching`` recordset
        :raises UserError: if the statement line has no associated journal
                           entry or no counterpart lines are found.
        """
        if not st_line.move_id:
            raise UserError(
                _("Statement line '%(line)s' has no associated journal "
                  "entry.")
                % {'line': st_line.display_name},
            )

        counterpart_lines = match_records.mapped('move_line_id')
        if not counterpart_lines:
            raise UserError(
                _("No counterpart journal entry lines found in the "
                  "selected matches for statement line '%(line)s'.")
                % {'line': st_line.display_name},
            )

        # Determine write-off configuration
        currency = self.currency_id or self.env.company.currency_id
        st_amount = abs(st_line.amount)
        match_total = sum(abs(m.matched_amount) for m in match_records)
        difference = st_amount - match_total

        helper_vals = {
            'company_id': self.company_id.id,
            'statement_line_id': st_line.id,
            'move_line_ids': [Command.set(counterpart_lines.ids)],
            'tolerance_percentage': self.tolerance_percentage,
        }

        # Configure write-off when there is a meaningful difference beyond
        # the tolerance threshold and a write-off account is available.
        if not currency.is_zero(difference):
            within_tolerance = False
            if self.tolerance_percentage > 0 and st_amount > 0:
                threshold = st_amount * (self.tolerance_percentage / 100.0)
                within_tolerance = abs(difference) <= threshold

            if not within_tolerance and self.write_off_account_id:
                helper_vals['write_off_account_id'] = (
                    self.write_off_account_id.id
                )
                helper_vals['write_off_label'] = (
                    self.write_off_label or _('Write-Off')
                )

        # Delegate to PartialReconcileHelper for consistent reconciliation
        # across both manual confirm and batch confirm flows.
        PartialHelper = self.env['account.reconciliation.partial.helper']
        helper = PartialHelper.create(helper_vals)
        helper.action_reconcile()

        # Transition matching record states to confirmed
        match_records.write({'state': 'confirmed'})

        # Update the statement line's CE confidence tracking field with the
        # actual matching engine score rather than the default from the helper.
        best_match = max(
            match_records,
            key=lambda m: m.confidence_score,
            default=None,
        )
        best_score = best_match.confidence_score if best_match else 0.0
        best_level = best_match.confidence_level if best_match else 'n/a'

        if best_score > 0 and hasattr(st_line, 'matching_confidence'):
            st_line.write({'matching_confidence': best_score})

        _logger.info(
            "Reconciled statement line '%s' with %d counterpart entr%s "
            "(best confidence: %.1f%%, level: %s).",
            st_line.display_name,
            len(counterpart_lines),
            'y' if len(counterpart_lines) == 1 else 'ies',
            best_score,
            best_level,
        )

    def _apply_rules(self, statement_lines):
        """Evaluate enhanced reconciliation rules from
        ``account.reconcile.model`` (with CE extensions) against the given
        statement lines in priority order.

        Rules are retrieved via ``get_ordered_rules()`` and evaluated per
        statement line using ``evaluate_rule(st_line, candidates)``.
        Matching confidence scores are adjusted based on rule evaluation
        results.  Matches whose scores exceed a rule's
        ``auto_reconcile_threshold`` are automatically marked as selected
        via the ``is_selected`` field for batch confirmation.

        :param statement_lines: ``account.bank.statement.line`` recordset
        """
        if not statement_lines:
            return

        ReconcileModel = self.env['account.reconcile.model']
        rules = ReconcileModel.get_ordered_rules(self.company_id.id)

        if not rules:
            _logger.debug(
                "No CE reconciliation rules found for company '%s'.",
                self.company_id.name,
            )
            return

        _logger.info(
            "Applying %d reconciliation rule(s) (ordered by priority) to "
            "%d statement line(s).",
            len(rules), len(statement_lines),
        )

        MatchingModel = self.env['account.reconciliation.matching']

        for st_line in statement_lines.filtered(lambda line: not line.is_reconciled):
            # Retrieve existing match suggestions for this line
            existing_matches = MatchingModel.search([
                ('statement_line_id', '=', st_line.id),
                ('state', '=', 'proposed'),
            ])
            if not existing_matches:
                continue

            candidate_move_lines = existing_matches.mapped('move_line_id')

            for rule in rules:
                # Gate on rule's confidence_threshold: skip this rule if
                # the best existing match score is below the threshold
                if rule.confidence_threshold > 0:
                    best_current = max(
                        existing_matches.mapped('confidence_score'),
                        default=0.0,
                    )
                    if best_current < rule.confidence_threshold:
                        continue

                try:
                    result = rule.evaluate_rule(st_line, candidate_move_lines)
                except (ValueError, TypeError, KeyError) as exc:
                    _logger.warning(
                        "Rule '%s' (priority %s) evaluation failed for "
                        "line '%s': %s",
                        rule.name, rule.priority,
                        st_line.display_name, exc,
                    )
                    continue

                if not result.get('rule_matched'):
                    continue

                # Apply confidence adjustments to matching records
                matched_candidates = result.get(
                    'candidates', self.env['account.move.line'],
                )
                adjustment = result.get('confidence_adjustment', 0.0)

                if adjustment and matched_candidates:
                    for match in existing_matches:
                        if match.move_line_id in matched_candidates:
                            new_score = min(
                                100.0,
                                match.confidence_score + adjustment,
                            )
                            match.write({'confidence_score': new_score})
                            _logger.debug(
                                "Rule '%s' boosted match confidence to "
                                "%.1f%% for line '%s' -> entry '%s'.",
                                rule.name, new_score,
                                st_line.display_name,
                                match.move_line_id.display_name,
                            )

                # Auto-select matches that exceed the rule's
                # auto_reconcile_threshold for batch confirmation
                if rule.auto_reconcile_threshold > 0 and matched_candidates:
                    for match in existing_matches:
                        if (match.move_line_id in matched_candidates
                                and match.confidence_score
                                >= rule.auto_reconcile_threshold):
                            match.write({'is_selected': True})
                            _logger.debug(
                                "Auto-selected match for line '%s' "
                                "(score %.1f%% >= threshold %.1f%%).",
                                st_line.display_name,
                                match.confidence_score,
                                rule.auto_reconcile_threshold,
                            )
