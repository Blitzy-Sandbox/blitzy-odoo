# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Partial Reconciliation Extensions for Bank Reconciliation

This module extends `account.bank.statement.line` with reconciliation tracking
fields and provides a `PartialReconcileHelper` transient model for managing
partial reconciliation workflows including:

- Split transaction support with write-off entries
- Tolerance-based automatic write-off application
- Multi-currency difference handling
- Manual reconciliation match/unmatch actions with audit trail

Implements:
    - FEATURE-002 BR-005: Partial Reconciliation with Write-offs
    - FEATURE-002 BR-003: Manual Reconciliation Workflows

Integration Notes:
    - Extends account.bank.statement.line via _inherit (no core modifications)
    - Creates account.partial.reconcile records following the same pattern as
      addons/account/models/account_partial_reconcile.py
    - Write access for reconciliation follows addons/account/wizard/account_payment_register.py
    - Zero Enterprise module dependencies

Constraints:
    - AGPL-3.0 licensing
    - Multi-company isolation via check_company and company-scoped queries
    - Python 3.10-3.13 compatibility
"""

import logging

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class BankStatementLineExt(models.Model):
    """Extension of account.bank.statement.line for reconciliation tracking.

    Adds fields to track the reconciliation status and matching confidence
    produced by the reconciliation matching engine, as well as import
    provenance metadata (hash, source file, format) used for duplicate
    detection during bank statement imports.

    This class uses ``_inherit`` without ``_name`` so all fields are added
    directly to the existing ``account_bank_statement_line`` table.
    """

    _inherit = 'account.bank.statement.line'

    # -------------------------------------------------------------------------
    # RECONCILIATION TRACKING FIELDS
    # -------------------------------------------------------------------------

    matching_confidence = fields.Float(
        string='Matching Confidence',
        digits=(5, 2),
        readonly=True,
        copy=False,
        help=(
            'Best matching confidence score (0-100) assigned by the '
            'reconciliation engine.  Values ≥90 are "High", 70-89 are '
            '"Medium", and 50-69 are "Low" confidence.'
        ),
    )

    reconciliation_status = fields.Selection(
        selection=[
            ('unreconciled', 'Unreconciled'),
            ('partially', 'Partially Reconciled'),
            ('reconciled', 'Fully Reconciled'),
            ('manual', 'Manually Reconciled'),
        ],
        string='Reconciliation Status',
        default='unreconciled',
        copy=False,
        help=(
            'Tracks the current reconciliation state of this statement line.  '
            'Updated automatically when partial or full reconciliation records '
            'are created or removed.'
        ),
    )

    # -------------------------------------------------------------------------
    # IMPORT PROVENANCE FIELDS
    # -------------------------------------------------------------------------

    import_hash = fields.Char(
        string='Import Hash',
        index=True,
        readonly=True,
        copy=False,
        help=(
            'SHA-256 hash computed over the canonical line data (date, amount, '
            'reference, partner).  Used to detect and reject duplicate imports.'
        ),
    )

    import_source = fields.Char(
        string='Import Source',
        readonly=True,
        copy=False,
        help='Original file name from which this statement line was imported.',
    )

    import_format = fields.Selection(
        selection=[
            ('csv', 'CSV'),
            ('ofx', 'OFX'),
            ('qif', 'QIF'),
            ('camt053', 'CAMT.053'),
            ('manual', 'Manual'),
        ],
        string='Import Format',
        readonly=True,
        copy=False,
        help='The electronic format used to import this statement line.',
    )


class PartialReconcileHelper(models.TransientModel):
    """Wizard for managing partial reconciliation of bank statement lines.

    Provides a guided workflow for reconciling a single bank statement line
    against one or more open journal items (``account.move.line``).  The
    wizard computes the difference between the statement amount and the
    total residual of the selected journal items, determines whether the
    difference falls within a configurable tolerance, and—when needed—creates
    a write-off journal entry to absorb the difference.

    The reconciliation creates standard ``account.partial.reconcile`` and
    ``account.full.reconcile`` records so that all operations are fully
    auditable through Odoo's native reconciliation trail.

    Implements:
        - BR-005: Split transaction support, write-off generation, tolerance
        - BR-003: Manual match / unmatch actions
    """

    _name = 'account.reconciliation.partial.helper'
    _description = 'Partial Reconciliation Helper'
    _check_company_auto = True

    # -------------------------------------------------------------------------
    # FIELDS
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

    statement_line_id = fields.Many2one(
        comodel_name='account.bank.statement.line',
        string='Statement Line',
        required=True,
        check_company=True,
    )

    move_line_ids = fields.Many2many(
        comodel_name='account.move.line',
        string='Journal Items to Reconcile',
        check_company=True,
    )

    write_off_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Write-Off Account',
        domain="[('account_type', '!=', 'off_balance')]",
        check_company=True,
        help=(
            'Account to use for the write-off journal entry when the '
            'reconciliation difference cannot be absorbed by tolerance alone.'
        ),
    )

    write_off_label = fields.Char(
        string='Write-Off Label',
        default='Write-Off',
    )

    write_off_amount = fields.Monetary(
        string='Write-Off Amount',
        currency_field='currency_id',
        compute='_compute_write_off_amount',
        help='Absolute value of the difference that will be posted as a write-off.',
    )

    tolerance_percentage = fields.Float(
        string='Tolerance %',
        default=0.0,
        digits=(5, 2),
        help=(
            'Maximum acceptable percentage difference between the statement '
            'amount and the matched journal items total to automatically apply '
            'a write-off.  Set to 0 to require exact matches.'
        ),
    )

    total_statement_amount = fields.Monetary(
        string='Statement Amount',
        currency_field='currency_id',
        compute='_compute_amounts',
    )

    total_move_line_amount = fields.Monetary(
        string='Journal Items Total',
        currency_field='currency_id',
        compute='_compute_amounts',
    )

    difference_amount = fields.Monetary(
        string='Difference',
        currency_field='currency_id',
        compute='_compute_amounts',
    )

    is_within_tolerance = fields.Boolean(
        string='Within Tolerance',
        compute='_compute_amounts',
    )

    # -------------------------------------------------------------------------
    # COMPUTE METHODS
    # -------------------------------------------------------------------------

    @api.depends(
        'statement_line_id',
        'statement_line_id.amount',
        'move_line_ids',
        'move_line_ids.amount_residual',
        'tolerance_percentage',
    )
    def _compute_amounts(self):
        """Compute reconciliation summary amounts and tolerance check.

        * ``total_statement_amount`` - the absolute bank statement line amount.
        * ``total_move_line_amount`` - sum of the selected journal items'
          residual amounts (absolute values for comparison purposes).
        * ``difference_amount`` - signed difference (statement - journal items).
        * ``is_within_tolerance`` - True when the absolute difference as a
          percentage of the statement amount does not exceed
          ``tolerance_percentage``.
        """
        for wizard in self:
            st_amount = wizard.statement_line_id.amount if wizard.statement_line_id else 0.0
            ml_amount = sum(
                wizard.move_line_ids.mapped('amount_residual'),
            ) if wizard.move_line_ids else 0.0

            wizard.total_statement_amount = st_amount
            wizard.total_move_line_amount = ml_amount

            # Difference: positive means the statement has more than the
            # journal items; negative means journal items exceed the statement.
            difference = st_amount - ml_amount
            wizard.difference_amount = difference

            # Tolerance evaluation: compare the absolute difference against
            # the tolerance percentage of the statement amount.
            if wizard.tolerance_percentage > 0.0 and st_amount:
                threshold = abs(st_amount) * (wizard.tolerance_percentage / 100.0)
                wizard.is_within_tolerance = abs(difference) <= threshold
            else:
                # When tolerance is 0 or the statement amount is 0, only an
                # exact match is considered "within tolerance".
                currency = wizard.currency_id or self.env.company.currency_id
                wizard.is_within_tolerance = currency.is_zero(difference)

    @api.depends('difference_amount', 'write_off_account_id')
    def _compute_write_off_amount(self):
        """Compute the write-off amount that will be posted.

        The write-off amount equals the absolute value of the difference
        when a write-off account is selected.  If no write-off account is
        configured the amount is 0.
        """
        for wizard in self:
            if wizard.write_off_account_id:
                wizard.write_off_amount = abs(wizard.difference_amount)
            else:
                wizard.write_off_amount = 0.0

    # -------------------------------------------------------------------------
    # ACTION METHODS
    # -------------------------------------------------------------------------

    def action_reconcile(self):
        """Execute partial or full reconciliation for the statement line.

        Workflow:
        1. Validate that a statement line and at least one journal item are
           selected.
        2. Handle multi-currency scenarios when the statement line and the
           journal items use different currencies.
        3. If the amounts match exactly (or the difference is within the
           configured tolerance and no write-off account is set), reconcile
           the statement line's suspense move lines directly against the
           selected journal items via ``account.partial.reconcile``.
        4. If a write-off account is specified, create an additional journal
           entry to absorb the difference, post it, and then reconcile.
        5. Update the statement line's ``reconciliation_status``.
        6. Return an action that closes the wizard.
        """
        self.ensure_one()

        # --- Validation ---------------------------------------------------
        if not self.statement_line_id:
            raise UserError(_(
                "Please select a bank statement line to reconcile.",
            ))
        if not self.move_line_ids:
            raise UserError(_(
                "Please select at least one journal item to reconcile against.",
            ))

        _logger.info(
            "Starting reconciliation for statement line %s (amount=%s) "
            "against %d journal item(s).",
            self.statement_line_id.id,
            self.statement_line_id.amount,
            len(self.move_line_ids),
        )

        st_line = self.statement_line_id
        move_lines = self.move_line_ids

        # --- Multi-currency handling --------------------------------------
        converted_amounts = self._handle_multi_currency(st_line, move_lines)

        # --- Determine the suspense / counterpart lines on the statement --
        # Following the standard Odoo pattern from
        # addons/account/tests/common.py  pay_with_statement_line():
        #   1. Get suspense lines from the statement move
        #   2. Change their account to the counterpart account (receivable /
        #      payable) so both sides share the same reconcilable account
        #   3. Call reconcile() on the combined set
        _liquidity_lines, suspense_lines, other_lines = st_line._seek_for_lines()
        counterpart_lines = suspense_lines | other_lines

        if not counterpart_lines:
            raise UserError(_(
                "The statement line journal entry has no counterpart lines. "
                "Please verify the journal configuration.",
            ))

        # Determine the target reconcilable account from the journal items
        # we are matching against.  Prefer a receivable/payable account if
        # available; otherwise fall back to the first reconcilable account.
        target_account = False
        for ml in move_lines:
            if ml.account_id.account_type in ('asset_receivable', 'liability_payable'):
                target_account = ml.account_id
                break
        if not target_account:
            for ml in move_lines:
                if ml.account_id.reconcile:
                    target_account = ml.account_id
                    break

        if not target_account:
            raise UserError(_(
                "None of the selected journal items have a reconcilable "
                "account.  Please verify the journal entries.",
            ))

        # Re-assign the counterpart (suspense) lines' account to match the
        # target account.  This is the standard Odoo reconciliation pattern
        # that makes both sides share the same reconcilable account.
        counterpart_lines.with_context(
            skip_account_move_synchronization=True,
        ).write({'account_id': target_account.id})

        # After the account switch the lines are now reconcilable.
        reconcilable_lines = counterpart_lines

        # --- Exact / tolerance match path ---------------------------------
        currency = self.currency_id or self.env.company.currency_id
        difference = self.difference_amount

        if currency.is_zero(difference) or (
            self.is_within_tolerance and not self.write_off_account_id
        ):
            # Direct reconciliation -- use ORM reconcile() on the combined
            # set of statement counterpart + matching journal items.
            self._reconcile_lines(reconcilable_lines, move_lines, converted_amounts)
            new_status = 'reconciled'
            _logger.info(
                "Statement line %s reconciled (exact/tolerance match).",
                st_line.id,
            )
        elif self.write_off_account_id:
            # Write-off path -- create a journal entry for the difference,
            # then reconcile everything together.
            write_off_move = self._create_write_off_entry(difference)
            wo_lines = write_off_move.line_ids.filtered(
                lambda line: line.account_id == target_account,
            )
            self._reconcile_lines(
                reconcilable_lines, move_lines | wo_lines, converted_amounts,
            )
            new_status = 'reconciled'
            _logger.info(
                "Statement line %s reconciled with write-off entry %s "
                "(difference=%s).",
                st_line.id,
                write_off_move.name,
                difference,
            )
        else:
            # Partial reconciliation -- the amounts don't match and no
            # write-off was requested.
            self._reconcile_lines(reconcilable_lines, move_lines, converted_amounts)
            new_status = 'partially'
            _logger.info(
                "Statement line %s partially reconciled (difference=%s).",
                st_line.id,
                difference,
            )

        # --- Update status on the statement line --------------------------
        st_line.write({'reconciliation_status': new_status})

        return {'type': 'ir.actions.act_window_close'}

    def _reconcile_lines(self, st_move_lines, counterpart_lines, converted_amounts):
        """Reconcile statement move lines against the provided counterpart lines.

        Uses Odoo's standard ORM ``reconcile()`` method which internally creates
        ``account.partial.reconcile`` and ``account.full.reconcile`` records as
        appropriate.  At this point the statement's counterpart lines already
        share the same reconcilable account as the matching journal items (the
        account was reassigned in ``action_reconcile``).

        :param st_move_lines: recordset of ``account.move.line`` from the
            statement line's journal entry (the former suspense lines whose
            account has been changed to the target reconcilable account).
        :param counterpart_lines: recordset of ``account.move.line`` from the
            open invoices / bills / other journal entries (and optionally
            write-off entries).
        :param converted_amounts: dict returned by ``_handle_multi_currency``
            containing currency conversion context, or empty dict.
        """
        all_lines = st_move_lines | counterpart_lines

        # Filter to only lines that are not yet reconciled and whose account
        # allows reconciliation.
        to_reconcile = all_lines.filtered(
            lambda line: line.account_id.reconcile and not line.reconciled,
        )
        if not to_reconcile:
            _logger.debug(
                "No reconcilable unreconciled lines found; nothing to do.",
            )
            return

        # Use Odoo's standard reconcile() which handles:
        # - account.partial.reconcile creation
        # - account.full.reconcile detection when residuals are cleared
        # - Multi-currency exchange difference entries
        # - Cash-basis tax entries
        try:
            to_reconcile.reconcile()
        except Exception:  # noqa: BLE001  # intentional: fall back gracefully on any reconcile failure
            # If the ORM reconcile() fails (e.g. due to account mismatch
            # or residual rounding), fall back to manual partial reconcile
            # creation so the user can complete reconciliation later.
            _logger.warning(
                "Standard ORM reconcile() failed; falling back to manual "
                "partial reconcile creation.",
                exc_info=True,
            )
            self._create_partial_reconcile_fallback(st_move_lines, counterpart_lines)

    def action_unreconcile(self):
        """Reverse reconciliation for the current statement line.

        Removes all partial reconcile records linked to the statement line's
        journal entry and resets the reconciliation status to ``unreconciled``.

        This method leverages the existing ``action_undo_reconciliation``
        on ``account.bank.statement.line`` which already handles:
        - Removing ``account.partial.reconcile`` records
        - Reversing cash-basis and exchange-difference entries
        - Resetting journal items to their original state
        """
        self.ensure_one()

        if not self.statement_line_id:
            raise UserError(_(
                "No statement line selected for un-reconciliation.",
            ))

        st_line = self.statement_line_id
        _logger.info(
            "Reversing reconciliation for statement line %s.",
            st_line.id,
        )

        # Delegate to the native undo mechanism which is already production-
        # tested and handles all edge cases (CABA, exchange diffs, payments).
        st_line.action_undo_reconciliation()

        # Reset the extended reconciliation status.
        st_line.write({
            'reconciliation_status': 'unreconciled',
            'matching_confidence': 0.0,
        })

        _logger.info(
            "Reconciliation reversed for statement line %s.",
            st_line.id,
        )

        return {'type': 'ir.actions.act_window_close'}

    # -------------------------------------------------------------------------
    # HELPER METHODS
    # -------------------------------------------------------------------------

    def _create_write_off_entry(self, difference):
        """Create and post a journal entry for the write-off difference.

        The entry consists of two lines:
        1. A line on the **write-off account** absorbing the difference.
        2. A balancing line on the **bank suspense account** (or the
           statement line's counterpart account) so the move is balanced.

        :param difference: Signed monetary difference.  Positive means the
            statement exceeds journal items; negative means journal items
            exceed the statement.
        :returns: The posted ``account.move`` record.
        :raises UserError: If the write-off account is not configured.
        """
        self.ensure_one()

        if not self.write_off_account_id:
            raise UserError(_(
                "A write-off account must be selected to create a write-off entry.",
            ))

        st_line = self.statement_line_id
        journal = st_line.journal_id
        company = st_line.company_id
        currency = self.currency_id or company.currency_id

        label = self.write_off_label or _('Write-Off')

        # Determine debit/credit from the sign of the difference.
        # A positive difference means the bank has *more* than the invoices,
        # so the write-off account absorbs the surplus as a debit (expense).
        abs_diff = abs(difference)

        write_off_debit = abs_diff if difference > 0 else 0.0
        write_off_credit = abs_diff if difference < 0 else 0.0
        counter_debit = write_off_credit  # mirror
        counter_credit = write_off_debit  # mirror

        # The counterpart account is the journal's suspense account (same
        # account used by the bank statement line's counterpart move line)
        # so that the resulting move line can be reconciled with the
        # statement's suspense line.
        counterpart_account = journal.suspense_account_id
        if not counterpart_account:
            raise UserError(_(
                "The journal '%s' does not have a suspense account configured.",
                journal.display_name,
            ))

        move_vals = {
            'move_type': 'entry',
            'journal_id': journal.id,
            'date': st_line.date or fields.Date.context_today(self),
            'ref': _("Write-off: %s", st_line.payment_ref or st_line.display_name),
            'company_id': company.id,
            'line_ids': [
                Command.create({
                    'name': label,
                    'account_id': self.write_off_account_id.id,
                    'partner_id': st_line.partner_id.id,
                    'currency_id': currency.id,
                    'debit': write_off_debit,
                    'credit': write_off_credit,
                    'amount_currency': difference,
                }),
                Command.create({
                    'name': label,
                    'account_id': counterpart_account.id,
                    'partner_id': st_line.partner_id.id,
                    'currency_id': currency.id,
                    'debit': counter_debit,
                    'credit': counter_credit,
                    'amount_currency': -difference,
                }),
            ],
        }

        write_off_move = self.env['account.move'].with_company(company).create(move_vals)
        write_off_move.action_post()

        _logger.info(
            "Write-off entry %s created for statement line %s "
            "(amount=%s, account=%s).",
            write_off_move.name,
            st_line.id,
            abs_diff,
            self.write_off_account_id.display_name,
        )

        return write_off_move

    def _create_partial_reconcile(self, debit_line, credit_line, amount):
        """Create a single ``account.partial.reconcile`` record.

        Follows the creation pattern observed in
        ``addons/account/models/account_partial_reconcile.py`` where
        ``debit_move_id`` and ``credit_move_id`` reference journal items
        with positive and negative balances respectively, and the ``amount``
        is always positive in company currency.

        :param debit_line: ``account.move.line`` with positive balance.
        :param credit_line: ``account.move.line`` with negative balance.
        :param amount: Positive reconciliation amount in company currency.
        :returns: The created ``account.partial.reconcile`` record.
        :raises ValidationError: If either line has no currency set.
        """
        self.ensure_one()

        if not debit_line.currency_id or not credit_line.currency_id:
            raise ValidationError(_(
                "Cannot create a partial reconciliation: both journal items "
                "must have a currency set.",
            ))

        company_currency = debit_line.company_currency_id

        # Compute the foreign-currency amounts for each side.
        debit_amount_currency = abs(debit_line.amount_currency) if (
            debit_line.currency_id != company_currency
        ) else amount

        credit_amount_currency = abs(credit_line.amount_currency) if (
            credit_line.currency_id != company_currency
        ) else amount

        # Cap to the actual residuals to avoid over-reconciliation.
        debit_amount_currency = min(
            debit_amount_currency,
            abs(debit_line.amount_residual_currency),
        )
        credit_amount_currency = min(
            credit_amount_currency,
            abs(credit_line.amount_residual_currency),
        )
        amount = min(amount, abs(debit_line.amount_residual), abs(credit_line.amount_residual))

        if amount <= 0:
            _logger.debug(
                "Skipping partial reconcile creation: zero or negative amount "
                "(debit_line=%s, credit_line=%s).",
                debit_line.id,
                credit_line.id,
            )
            return self.env['account.partial.reconcile']

        partial_vals = {
            'debit_move_id': debit_line.id,
            'credit_move_id': credit_line.id,
            'amount': amount,
            'debit_amount_currency': debit_amount_currency,
            'credit_amount_currency': credit_amount_currency,
        }

        partial = self.env['account.partial.reconcile'].create(partial_vals)

        _logger.debug(
            "Created account.partial.reconcile id=%s "
            "(debit=%s, credit=%s, amount=%s).",
            partial.id,
            debit_line.id,
            credit_line.id,
            amount,
        )

        return partial

    def _create_partial_reconcile_fallback(self, st_move_lines, counterpart_lines):
        """Fallback reconciliation when ORM ``reconcile()`` cannot be used.

        Iterates over the statement move lines and counterpart lines to create
        ``account.partial.reconcile`` records manually.  This is only invoked
        when the standard ORM reconcile raises an unexpected error.

        :param st_move_lines: recordset of ``account.move.line`` from the
            statement's journal entry.
        :param counterpart_lines: recordset of ``account.move.line`` from
            matching journal entries.
        """
        for line in st_move_lines:
            if not line.account_id.reconcile:
                continue
            for cp_line in counterpart_lines:
                if not cp_line.account_id.reconcile or cp_line.reconciled:
                    continue
                line_residual = abs(line.amount_residual)
                cp_residual = abs(cp_line.amount_residual)
                amount = min(line_residual, cp_residual)
                if amount <= 0:
                    continue
                if line.balance >= 0 and cp_line.balance < 0:
                    debit_line, credit_line = line, cp_line
                elif line.balance < 0 and cp_line.balance >= 0:
                    debit_line, credit_line = cp_line, line
                elif line.amount_residual > 0:
                    debit_line, credit_line = line, cp_line
                else:
                    debit_line, credit_line = cp_line, line
                self._create_partial_reconcile(debit_line, credit_line, amount)

    def _handle_multi_currency(self, st_line, move_lines):
        """Handle currency conversion when statement and journal items differ.

        When the statement line is denominated in a different currency from the
        journal items, this method computes the conversion context needed for
        reconciliation.  It leverages the statement line's existing
        ``_get_accounting_amounts_and_currencies`` helper and the Odoo
        ``res.currency._convert`` method.

        :param st_line: ``account.bank.statement.line`` record.
        :param move_lines: ``account.move.line`` recordset being reconciled.
        :returns: Dictionary with currency conversion metadata.  Empty dict
            when no conversion is needed.
        """
        self.ensure_one()
        result = {}

        if not st_line or not move_lines:
            return result

        st_currency = st_line.currency_id or st_line.company_id.currency_id
        company_currency = st_line.company_id.currency_id

        # Collect distinct currencies from the move lines.
        ml_currencies = move_lines.mapped('currency_id')

        # If all items share the same currency as the statement, no special
        # handling is required.
        if all(c == st_currency for c in ml_currencies):
            return result

        conversion_date = st_line.date or fields.Date.context_today(self)

        for ml in move_lines:
            ml_currency = ml.currency_id
            if ml_currency == st_currency:
                continue

            # Convert the statement amount into the move line's currency for
            # comparison and tolerance evaluation.
            converted = st_currency._convert(
                from_amount=st_line.amount,
                to_currency=ml_currency,
                company=st_line.company_id,
                date=conversion_date,
            )
            result.setdefault('conversions', {})[ml.id] = {
                'original_currency': st_currency.id,
                'target_currency': ml_currency.id,
                'converted_amount': converted,
                'conversion_date': conversion_date,
            }

            _logger.debug(
                "Multi-currency conversion for move line %s: %s %s → %s %s "
                "(date=%s).",
                ml.id,
                st_line.amount,
                st_currency.name,
                converted,
                ml_currency.name,
                conversion_date,
            )

        if result:
            # Store the exchange rate applied for auditing purposes.
            result['statement_currency_id'] = st_currency.id
            result['company_currency_id'] = company_currency.id

        return result
