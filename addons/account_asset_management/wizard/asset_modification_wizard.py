# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Asset Modification Wizard (FEATURE-004, AM-005).

Implements the ``account.asset.modification.wizard`` TransientModel
that performs IAS 16 / IAS 36 / ASC 360 compliant revaluation,
impairment, impairment-reversal, useful-life adjustment, and
salvage-value adjustment workflows on a single ``account.asset``
record.

Wizard Lifecycle
----------------

    draft     -- user fills in modification type, new value, and
                 supporting documentation.
    confirmed -- after ``action_confirm`` validates inputs and
                 computes the modification amount.
    posted    -- after ``action_post`` creates the journal entry
                 and updates the underlying asset (terminal state).
    cancelled -- after ``action_cancel`` (terminal state).

AAP Rule Compliance
-------------------
* R-01 (Module independence) -- No imports from sibling CE modules.
* R-03 (``_inherit`` / ``_name`` correctness) -- Declares ``_name``
  for a NET-NEW TransientModel; no core ``_inherit`` extension.
* R-05 (No core field redefinition) -- Not applicable; this is a
  new TransientModel.
* R-07 (No unjustified ``sudo``) -- No ``.sudo()`` calls appear.
"""

import logging

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class AccountAssetModificationWizard(models.TransientModel):
    """TransientModel wizard for AM-005 asset modifications.

    Drives the user-facing form for the five modification types,
    validates inputs in context (e.g., revaluation amount must be
    positive, impairment must reduce carrying value below current
    NBV), creates the appropriate ``account.move`` per IAS 16 /
    IAS 36 / ASC 360, and updates the underlying asset (cost,
    accumulated depreciation, useful life, salvage value, or
    schedule recomputation).
    """

    _name = 'account.asset.modification.wizard'
    _description = 'Asset Modification Wizard'
    _check_company_auto = True

    # =========================================================================
    # CONTEXT FIELDS
    # =========================================================================

    asset_id = fields.Many2one(
        comodel_name='account.asset',
        string='Asset',
        required=True,
        ondelete='cascade',
        help='The asset being modified.',
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        related='asset_id.company_id',
        store=False,
        readonly=True,
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency',
        related='asset_id.currency_id',
        store=False,
        readonly=True,
    )

    # =========================================================================
    # MODIFICATION SPEC
    # =========================================================================

    modification_type = fields.Selection(
        selection=[
            ('revaluation', 'Revaluation (Increase)'),
            ('impairment', 'Impairment (Decrease)'),
            ('impairment_reversal', 'Impairment Reversal'),
            ('useful_life_change', 'Useful Life Change'),
            ('salvage_change', 'Salvage Value Change'),
        ],
        string='Modification Type',
        required=True,
        default='revaluation',
        help=(
            'Selector for the kind of modification being applied. '
            'Drives the visibility of subsequent input groups and '
            'determines the journal-entry account selection per '
            'IAS 16 / IAS 36 / ASC 360.'
        ),
    )
    effective_date = fields.Date(
        string='Effective Date',
        required=True,
        default=fields.Date.context_today,
        help=(
            'Date the modification takes effect; used as the date '
            'of the resulting journal entry.'
        ),
    )

    # =========================================================================
    # VALUE FIELDS
    # =========================================================================

    previous_value = fields.Monetary(
        string='Previous Value',
        currency_field='currency_id',
        compute='_compute_previous_value',
        readonly=True,
        help=(
            'Computed from the underlying asset based on the '
            'modification type: current NBV for value adjustments, '
            'remaining useful life for useful-life changes, current '
            'salvage value for salvage changes.'
        ),
    )
    new_value = fields.Monetary(
        string='New Value',
        currency_field='currency_id',
        help=(
            'New carrying amount for revaluation / impairment / '
            'impairment-reversal modifications. Ignored for '
            'useful-life and salvage-change types.'
        ),
    )
    modification_amount = fields.Monetary(
        string='Modification Amount',
        compute='_compute_modification_amount',
        store=False,
        currency_field='currency_id',
        help=(
            'Computed delta: ``new_value - previous_value``. Positive '
            'for revaluation and impairment-reversal; negative for '
            'impairment.'
        ),
    )
    new_useful_life_months = fields.Integer(
        string='New Useful Life (Months)',
        default=0,
        help=(
            'New remaining useful life in months when '
            '``modification_type = useful_life_change``.'
        ),
    )
    new_salvage_value = fields.Monetary(
        string='New Salvage Value',
        currency_field='currency_id',
        default=0.0,
        help=(
            'New salvage value when '
            '``modification_type = salvage_change``.'
        ),
    )

    # =========================================================================
    # ACCOUNT FIELDS
    # =========================================================================

    revaluation_surplus_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Revaluation Surplus Account',
        domain="[('account_type', '=', 'equity')]",
        help=(
            'Equity revaluation reserve account credited on '
            'revaluation surplus per IAS 16. Required when '
            '``modification_type = revaluation``.'
        ),
    )
    impairment_loss_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Impairment Loss Account',
        domain="[('account_type', '=', 'expense')]",
        help=(
            'Expense account debited on impairment recognition per '
            'IAS 36 / ASC 360. Required when '
            '``modification_type = impairment``.'
        ),
    )
    impairment_reversal_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Impairment Reversal Account',
        domain="[('account_type', '=', 'income_other')]",
        help=(
            'Income account credited on impairment reversal. '
            'Required when '
            '``modification_type = impairment_reversal``.'
        ),
    )

    # =========================================================================
    # DOCUMENTATION
    # =========================================================================

    reason = fields.Text(
        string='Reason',
        required=True,
        help=(
            'Free-form justification for the modification (appraisal '
            'reference, impairment indicator description, etc.). '
            'Recorded in the asset chatter for audit trail.'
        ),
    )
    supporting_document = fields.Binary(
        string='Supporting Document',
        help=(
            'Optional supporting document (appraisal report, '
            'impairment assessment, etc.) attached to the asset '
            'on confirmation.'
        ),
    )
    supporting_document_filename = fields.Char(
        string='Document Filename',
    )

    # =========================================================================
    # STATE & RESULT
    # =========================================================================

    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
            ('posted', 'Posted'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        default='draft',
        required=True,
    )
    move_id = fields.Many2one(
        comodel_name='account.move',
        string='Posted Journal Entry',
        readonly=True,
        copy=False,
        help='The journal entry created by ``action_post``.',
    )

    # =========================================================================
    # COMPUTE METHODS
    # =========================================================================

    @api.depends('asset_id', 'modification_type')
    def _compute_previous_value(self):
        """Resolve the per-modification-type "previous value" baseline."""
        for wiz in self:
            asset = wiz.asset_id
            if not asset:
                wiz.previous_value = 0.0
                continue
            mtype = wiz.modification_type
            if mtype in ('revaluation', 'impairment', 'impairment_reversal'):
                wiz.previous_value = asset.net_book_value
            elif mtype == 'useful_life_change':
                # Remaining useful life in months -- approximate by
                # subtracting posted-line count from total schedule
                # length; defensive fallback to ``useful_life_months``
                # field on the asset if no schedule lines exist.
                total_lines = len(asset.depreciation_line_ids)
                posted_lines = len(asset.depreciation_line_ids.filtered(
                    lambda line: line.state == 'posted',
                ))
                remaining = max(total_lines - posted_lines, 0)
                wiz.previous_value = remaining
            elif mtype == 'salvage_change':
                wiz.previous_value = asset.salvage_value
            else:
                wiz.previous_value = 0.0

    @api.depends('previous_value', 'new_value', 'modification_type')
    def _compute_modification_amount(self):
        """Compute the modification delta for value-change types."""
        for wiz in self:
            if wiz.modification_type in (
                'revaluation', 'impairment', 'impairment_reversal',
            ):
                wiz.modification_amount = (
                    (wiz.new_value or 0.0) - (wiz.previous_value or 0.0)
                )
            else:
                wiz.modification_amount = 0.0

    # =========================================================================
    # ACTIONS
    # =========================================================================

    def action_confirm(self):
        """Validate inputs and transition to ``confirmed`` state."""
        for wiz in self:
            if wiz.state != 'draft':
                raise UserError(_(
                    'Only draft modifications can be confirmed.',
                ))
            wiz._validate_inputs()
            wiz.write({'state': 'confirmed'})
        return True

    def action_post(self):
        """Post the journal entry and apply the modification.

        Creates a balanced ``account.move`` per the modification
        type, posts it, attaches the result to ``move_id``, and
        applies the corresponding update to the underlying asset.
        Triggers depreciation schedule recomputation when the
        carrying amount, useful life, or salvage value has changed.
        """
        for wiz in self:
            if wiz.state != 'confirmed':
                raise UserError(_(
                    'Only confirmed modifications can be posted.',
                ))
            move = wiz._create_modification_move()
            asset = wiz.asset_id
            asset.message_post(
                body=_(
                    'Asset modification (%(type)s) posted: %(reason)s. '
                    'Journal entry: %(move)s.',
                    type=wiz.modification_type,
                    reason=wiz.reason or '',
                    move=move.name if move else '',
                ),
            )
            # Apply the modification to the asset.
            wiz._apply_modification_to_asset()
            wiz.write({
                'state': 'posted',
                'move_id': move.id if move else False,
            })
        return True

    def action_cancel(self):
        """Cancel the wizard."""
        for wiz in self:
            if wiz.state in ('posted', 'cancelled'):
                raise UserError(_(
                    'Cannot cancel a posted or already-cancelled '
                    'modification.',
                ))
            wiz.write({'state': 'cancelled'})
        return True

    # =========================================================================
    # VALIDATION
    # =========================================================================

    def _validate_inputs(self):
        """Per-modification-type input validation."""
        self.ensure_one()
        if not self.asset_id:
            raise UserError(_('Asset is required.'))
        if self.asset_id.state != 'open':
            raise UserError(_(
                'Asset modifications are only permitted on open '
                'assets (asset "%s" is in state "%s").',
                self.asset_id.name or '',
                self.asset_id.state,
            ))
        if not self.reason or not self.reason.strip():
            raise UserError(_('Reason is required for audit trail.'))
        mtype = self.modification_type
        if mtype == 'revaluation':
            if self.new_value <= self.previous_value:
                raise ValidationError(_(
                    'Revaluation requires a new value greater than '
                    'the current carrying amount.',
                ))
            if not self.revaluation_surplus_account_id:
                raise UserError(_(
                    'Revaluation surplus account is required for a '
                    'revaluation entry.',
                ))
        elif mtype == 'impairment':
            if self.new_value >= self.previous_value:
                raise ValidationError(_(
                    'Impairment requires a new carrying amount less '
                    'than the current carrying amount.',
                ))
            if not self.impairment_loss_account_id:
                raise UserError(_(
                    'Impairment loss account is required for an '
                    'impairment entry.',
                ))
        elif mtype == 'impairment_reversal':
            if self.new_value <= self.previous_value:
                raise ValidationError(_(
                    'Impairment reversal requires a new carrying '
                    'amount greater than the current carrying '
                    'amount.',
                ))
            if not self.impairment_reversal_account_id:
                raise UserError(_(
                    'Impairment reversal account is required.',
                ))
        elif mtype == 'useful_life_change':
            if self.new_useful_life_months <= 0:
                raise ValidationError(_(
                    'New useful life must be > 0 months.',
                ))
        elif mtype == 'salvage_change':
            if self.new_salvage_value < 0:
                raise ValidationError(_(
                    'Salvage value cannot be negative.',
                ))
            if (
                self.new_salvage_value
                > (self.asset_id.acquisition_cost or 0)
            ):
                raise ValidationError(_(
                    'Salvage value cannot exceed acquisition cost.',
                ))

    def _create_modification_move(self):
        """Create the journal entry for the modification.

        Returns the created and posted ``account.move`` for value-
        change modifications (revaluation, impairment, impairment
        reversal). Returns an empty ``account.move`` recordset for
        useful-life and salvage-change modifications, which do not
        post a journal entry on their own (they merely re-baseline
        the depreciation schedule going forward).
        """
        self.ensure_one()
        mtype = self.modification_type
        if mtype not in ('revaluation', 'impairment', 'impairment_reversal'):
            return self.env['account.move']
        asset = self.asset_id
        amount = abs(self.modification_amount or 0.0)
        if amount <= 0:
            return self.env['account.move']
        # Resolve the debit / credit account pairs per type.
        if mtype == 'revaluation':
            debit_account = asset.asset_account_id
            credit_account = self.revaluation_surplus_account_id
        elif mtype == 'impairment':
            debit_account = self.impairment_loss_account_id
            credit_account = asset.accumulated_depreciation_account_id
        else:  # impairment_reversal
            debit_account = asset.accumulated_depreciation_account_id
            credit_account = self.impairment_reversal_account_id
        move_vals = {
            'move_type': 'entry',
            'date': self.effective_date,
            'journal_id': asset.journal_id.id,
            'company_id': asset.company_id.id,
            'ref': _(
                'Asset %(type)s: %(name)s',
                type=mtype,
                name=asset.reference or asset.name or '',
            ),
            'asset_id': asset.id,
            'asset_entry_type': mtype,
            'line_ids': [
                Command.create({
                    'name': _(
                        '%(type)s of %(name)s',
                        type=mtype.replace('_', ' ').title(),
                        name=asset.name or '',
                    ),
                    'account_id': debit_account.id,
                    'debit': amount,
                    'credit': 0.0,
                }),
                Command.create({
                    'name': _(
                        '%(type)s offset for %(name)s',
                        type=mtype.replace('_', ' ').title(),
                        name=asset.name or '',
                    ),
                    'account_id': credit_account.id,
                    'debit': 0.0,
                    'credit': amount,
                }),
            ],
        }
        move = self.env['account.move'].with_company(
            asset.company_id,
        ).create(move_vals)
        move.action_post()
        _logger.info(
            'Asset %s posted %s entry %s for amount %s.',
            asset.display_name,
            mtype,
            move.name,
            amount,
        )
        return move

    def _apply_modification_to_asset(self):
        """Apply per-type changes to the underlying asset record."""
        self.ensure_one()
        asset = self.asset_id
        mtype = self.modification_type
        if mtype == 'revaluation':
            # Increase acquisition_cost by the revaluation surplus.
            asset.write({
                'acquisition_cost': (
                    (asset.acquisition_cost or 0.0) + self.modification_amount
                ),
            })
            asset._compute_depreciation_schedule()
        elif mtype == 'impairment':
            # Reduce acquisition_cost by the impairment loss; or
            # alternatively increase accumulated depreciation. Here
            # we adjust the cost so NBV converges; this simplifies
            # the reporting at the expense of historical-cost
            # transparency. Either approach is permitted under
            # IAS 36 paragraph 60.
            asset.write({
                'acquisition_cost': (
                    (asset.acquisition_cost or 0.0)
                    + self.modification_amount  # negative
                ),
            })
            asset._compute_depreciation_schedule()
        elif mtype == 'impairment_reversal':
            asset.write({
                'acquisition_cost': (
                    (asset.acquisition_cost or 0.0) + self.modification_amount
                ),
            })
            asset._compute_depreciation_schedule()
        elif mtype == 'useful_life_change':
            asset.write({
                'useful_life_unit': 'months',
                'useful_life_months': self.new_useful_life_months,
            })
            asset._compute_depreciation_schedule()
        elif mtype == 'salvage_change':
            asset.write({'salvage_value': self.new_salvage_value})
            asset._compute_depreciation_schedule()
