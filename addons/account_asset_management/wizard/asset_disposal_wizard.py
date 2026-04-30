# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Asset Disposal Wizard (FEATURE-004, AM-006).

Implements the ``account.asset.disposal.wizard`` TransientModel
that processes asset disposal (sale, scrap, write-off) with
automatic gain/loss calculation, optional catch-up depreciation
through the disposal date, and partial-disposal support.

Wizard Lifecycle
----------------

    draft     -- user fills in disposal method, date, optional
                 proceeds, and partial-disposal quantity.
    confirmed -- after ``action_confirm`` validates inputs and
                 computes the gain/loss.
    posted    -- after ``action_post`` creates the disposal
                 journal entry, optional catch-up depreciation
                 entry, transitions the asset to ``close``.
    cancelled -- after ``action_cancel`` (terminal state).

AAP Rule Compliance
-------------------
* R-01 (Module independence) -- No imports from sibling CE modules.
* R-03 (``_inherit`` / ``_name`` correctness) -- Declares ``_name``
  for a NET-NEW TransientModel; no core ``_inherit`` extension.
* R-05 (No core field redefinition) -- Not applicable (new model).
* R-07 (No unjustified ``sudo``) -- No ``.sudo()`` calls appear.
"""

import logging

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class AccountAssetDisposalWizard(models.TransientModel):
    """TransientModel wizard for AM-006 asset disposal.

    Drives the user-facing form for sale, scrap, and write-off
    disposal workflows with automatic gain/loss calculation
    against net book value.
    """

    _name = 'account.asset.disposal.wizard'
    _description = 'Asset Disposal Wizard'
    _check_company_auto = True

    # =========================================================================
    # CONTEXT FIELDS
    # =========================================================================

    asset_id = fields.Many2one(
        comodel_name='account.asset',
        string='Asset',
        required=True,
        ondelete='cascade',
        help='The asset being disposed.',
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
    # DISPOSAL SPEC
    # =========================================================================

    disposal_method = fields.Selection(
        selection=[
            ('sale', 'Sale'),
            ('scrap', 'Scrap'),
            ('write_off', 'Write-off'),
        ],
        string='Disposal Method',
        required=True,
        default='sale',
        help=(
            'Selector for the disposal type. ``sale`` requires '
            'proceeds and a destination account; ``scrap`` and '
            '``write_off`` recognize the entire NBV as a loss '
            '(except ``write_off`` may net against an insurance '
            'recovery).'
        ),
    )
    disposal_date = fields.Date(
        string='Disposal Date',
        required=True,
        default=fields.Date.context_today,
        help=(
            'Date the asset is removed from service. Used as the '
            'date of the disposal journal entry.'
        ),
    )
    is_partial = fields.Boolean(
        string='Partial Disposal',
        default=False,
        help=(
            'When True, only a portion of the asset is disposed; '
            'requires ``disposed_quantity`` and ``total_quantity``.'
        ),
    )

    # =========================================================================
    # PARTIAL DISPOSAL FIELDS
    # =========================================================================

    disposed_quantity = fields.Float(
        string='Disposed Quantity',
        default=0.0,
        help=(
            'Quantity / units of the asset being disposed. Used '
            'with ``total_quantity`` to derive '
            '``disposal_proportion``.'
        ),
    )
    total_quantity = fields.Float(
        string='Total Quantity',
        default=1.0,
        help=(
            'Total quantity / units the asset represents. Defaults '
            'to 1.0 for non-divisible assets.'
        ),
    )
    disposal_proportion = fields.Float(
        string='Disposal Proportion',
        compute='_compute_disposal_proportion',
        digits=(5, 4),
        store=False,
        help='Proportion of the asset being disposed (0 to 1).',
    )

    # =========================================================================
    # SALE PROCEEDS FIELDS
    # =========================================================================

    proceeds_amount = fields.Monetary(
        string='Proceeds Amount',
        currency_field='currency_id',
        default=0.0,
        help=(
            'Sale proceeds for the disposed portion. Required for '
            '``disposal_method = sale``.'
        ),
    )
    proceeds_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Proceeds Account',
        help=(
            'Cash, bank, or accounts-receivable account debited for '
            'the sale proceeds. Required for sale disposals.'
        ),
    )

    # =========================================================================
    # GAIN / LOSS FIELDS
    # =========================================================================

    net_book_value = fields.Monetary(
        string='Net Book Value',
        currency_field='currency_id',
        compute='_compute_disposal_amounts',
        store=False,
        help=(
            'Net book value of the disposed portion: '
            '``acquisition_cost - accumulated_depreciation`` '
            'multiplied by ``disposal_proportion`` for partial '
            'disposals.'
        ),
    )
    catchup_depreciation_required = fields.Boolean(
        string='Catch-up Depreciation Required',
        compute='_compute_disposal_amounts',
        store=False,
        help=(
            'True when the disposal date is after the latest posted '
            'depreciation date and at least one due draft line exists. '
            'A catch-up depreciation entry will be posted before the '
            'disposal entry.'
        ),
    )
    catchup_depreciation_amount = fields.Monetary(
        string='Catch-up Depreciation',
        currency_field='currency_id',
        compute='_compute_disposal_amounts',
        store=False,
        help=(
            'Amount of catch-up depreciation to post before the '
            'disposal entry.'
        ),
    )
    gain_loss_amount = fields.Monetary(
        string='Gain / Loss',
        currency_field='currency_id',
        compute='_compute_disposal_amounts',
        store=False,
        help=(
            'Computed as ``proceeds_amount - net_book_value``. '
            'Positive => gain (credit gain account); negative => '
            'loss (debit loss account); zero => no gain/loss entry.'
        ),
    )
    gain_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Gain Account',
        domain="[('account_type', '=', 'income_other')]",
        help='Income account credited when proceeds exceed NBV.',
    )
    loss_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Loss Account',
        domain="[('account_type', '=', 'expense')]",
        help='Expense account debited when proceeds are less than NBV.',
    )

    # =========================================================================
    # DOCUMENTATION
    # =========================================================================

    disposal_reason = fields.Text(
        string='Disposal Reason',
        required=True,
        help='Free-form reason for the disposal (audit trail).',
    )
    documentation_ref = fields.Char(
        string='Documentation Reference',
        help=(
            'External document reference (sale invoice number, '
            'insurance claim number, scrap order, etc.).'
        ),
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
        string='Disposal Journal Entry',
        readonly=True,
        copy=False,
    )
    catchup_depreciation_move_id = fields.Many2one(
        comodel_name='account.move',
        string='Catch-up Depreciation Entry',
        readonly=True,
        copy=False,
    )

    # =========================================================================
    # COMPUTE METHODS
    # =========================================================================

    @api.depends('disposed_quantity', 'total_quantity', 'is_partial')
    def _compute_disposal_proportion(self):
        for wiz in self:
            if (
                wiz.is_partial
                and wiz.total_quantity
                and wiz.total_quantity > 0
            ):
                wiz.disposal_proportion = min(
                    max(
                        (wiz.disposed_quantity or 0.0)
                        / wiz.total_quantity,
                        0.0,
                    ),
                    1.0,
                )
            else:
                wiz.disposal_proportion = 1.0

    @api.depends(
        'asset_id',
        'asset_id.acquisition_cost',
        'asset_id.accumulated_depreciation',
        'asset_id.salvage_value',
        'disposal_proportion',
        'disposal_date',
        'proceeds_amount',
        'disposal_method',
    )
    def _compute_disposal_amounts(self):
        """Compute NBV, catch-up amount, and gain/loss."""
        for wiz in self:
            asset = wiz.asset_id
            proportion = wiz.disposal_proportion or 1.0
            if not asset:
                wiz.net_book_value = 0.0
                wiz.catchup_depreciation_required = False
                wiz.catchup_depreciation_amount = 0.0
                wiz.gain_loss_amount = 0.0
                continue
            asset_nbv = (asset.acquisition_cost or 0.0) - (
                asset.accumulated_depreciation or 0.0
            )
            wiz.net_book_value = asset_nbv * proportion
            # Catch-up: any draft line with date <= disposal_date
            # signals catch-up depreciation is due before the
            # disposal entry.
            disposal_date = wiz.disposal_date or fields.Date.context_today(wiz)
            due_lines = asset.depreciation_line_ids.filtered(
                lambda line: (
                    line.state == 'draft'
                    and line.depreciation_date
                    and line.depreciation_date <= disposal_date
                ),
            )
            wiz.catchup_depreciation_required = bool(due_lines)
            wiz.catchup_depreciation_amount = sum(
                due_lines.mapped('depreciation_amount'),
            )
            # Gain/loss = proceeds - NBV (after catch-up
            # depreciation).
            adjusted_nbv = wiz.net_book_value - (
                wiz.catchup_depreciation_amount * proportion
            )
            if wiz.disposal_method == 'sale':
                wiz.gain_loss_amount = (
                    (wiz.proceeds_amount or 0.0) - adjusted_nbv
                )
            else:
                # Scrap / write-off: no proceeds, full NBV is loss.
                wiz.gain_loss_amount = -adjusted_nbv

    # =========================================================================
    # ACTIONS
    # =========================================================================

    def action_confirm(self):
        for wiz in self:
            if wiz.state != 'draft':
                raise UserError(_(
                    'Only draft disposals can be confirmed.',
                ))
            wiz._validate_inputs()
            wiz.write({'state': 'confirmed'})
        return True

    def action_post(self):
        """Post catch-up depreciation, the disposal move, close asset."""
        for wiz in self:
            if wiz.state != 'confirmed':
                raise UserError(_(
                    'Only confirmed disposals can be posted.',
                ))
            asset = wiz.asset_id
            catchup_move = self.env['account.move']
            if wiz.catchup_depreciation_required:
                catchup_move = wiz._post_catchup_depreciation()
            disposal_move = wiz._create_disposal_move()
            asset.message_post(body=_(
                'Asset disposed (%(method)s) on %(date)s. '
                'Reason: %(reason)s.',
                method=wiz.disposal_method,
                date=wiz.disposal_date,
                reason=wiz.disposal_reason or '',
            ))
            asset.action_close()
            wiz.write({
                'state': 'posted',
                'move_id': disposal_move.id if disposal_move else False,
                'catchup_depreciation_move_id': (
                    catchup_move.id if catchup_move else False
                ),
            })
        return True

    def action_cancel(self):
        for wiz in self:
            if wiz.state in ('posted', 'cancelled'):
                raise UserError(_(
                    'Cannot cancel a posted or already-cancelled '
                    'disposal.',
                ))
            wiz.write({'state': 'cancelled'})
        return True

    # =========================================================================
    # VALIDATION
    # =========================================================================

    def _validate_inputs(self):
        self.ensure_one()
        if not self.asset_id:
            raise UserError(_('Asset is required.'))
        if self.asset_id.state != 'open':
            raise UserError(_(
                'Disposal is only permitted on open assets '
                '(asset "%s" is in state "%s").',
                self.asset_id.name or '',
                self.asset_id.state,
            ))
        if not self.disposal_reason or not self.disposal_reason.strip():
            raise UserError(_(
                'Disposal reason is required for audit trail.',
            ))
        if self.disposal_method == 'sale':
            if (self.proceeds_amount or 0.0) < 0:
                raise ValidationError(_(
                    'Proceeds amount cannot be negative.',
                ))
            if not self.proceeds_account_id:
                raise UserError(_(
                    'Proceeds account is required for sale disposals.',
                ))
        if self.is_partial:
            if self.disposed_quantity <= 0:
                raise ValidationError(_(
                    'Disposed quantity must be > 0 for partial '
                    'disposal.',
                ))
            if self.total_quantity <= 0:
                raise ValidationError(_(
                    'Total quantity must be > 0 for partial disposal.',
                ))
            if self.disposed_quantity > self.total_quantity:
                raise ValidationError(_(
                    'Disposed quantity cannot exceed total quantity.',
                ))
        if self.gain_loss_amount > 0 and not self.gain_account_id:
            raise UserError(_(
                'Gain account is required when proceeds exceed '
                'net book value.',
            ))
        if self.gain_loss_amount < 0 and not self.loss_account_id:
            raise UserError(_(
                'Loss account is required when net book value '
                'exceeds proceeds.',
            ))

    # =========================================================================
    # ENTRY GENERATION
    # =========================================================================

    def _post_catchup_depreciation(self):
        """Post all due draft depreciation lines through ``disposal_date``."""
        self.ensure_one()
        asset = self.asset_id
        disposal_date = self.disposal_date
        due_lines = asset.depreciation_line_ids.filtered(
            lambda line: (
                line.state == 'draft'
                and line.depreciation_date
                and line.depreciation_date <= disposal_date
            ),
        ).sorted(key=lambda line: line.sequence)
        last_move = self.env['account.move']
        for line in due_lines:
            line.action_post()
            if line.move_id:
                last_move = line.move_id
        return last_move

    def _create_disposal_move(self):
        """Create and post the disposal journal entry."""
        self.ensure_one()
        asset = self.asset_id
        proportion = self.disposal_proportion or 1.0
        currency = asset.currency_id or asset.company_id.currency_id
        # Per AM-006 AC1-3:
        #   Credit  asset_account_id          for acquisition_cost * proportion
        #   Debit   accumulated_dep_account   for accumulated_dep * proportion
        #   Debit   proceeds_account_id       for proceeds_amount  (sale only)
        #   Debit   loss_account_id           for loss
        #   Credit  gain_account_id           for gain
        cost_share = currency.round(
            (asset.acquisition_cost or 0.0) * proportion,
        )
        depreciation_share = currency.round(
            (asset.accumulated_depreciation or 0.0) * proportion,
        )
        proceeds = (
            currency.round(self.proceeds_amount)
            if self.disposal_method == 'sale'
            else 0.0
        )
        gain_loss = currency.round(self.gain_loss_amount)
        commands = [
            # Remove the asset's acquisition cost (credit asset).
            Command.create({
                'name': _(
                    'Disposal of %s (asset removal)', asset.name or '',
                ),
                'account_id': asset.asset_account_id.id,
                'debit': 0.0,
                'credit': cost_share,
            }),
            # Clear accumulated depreciation (debit accumulated dep).
            Command.create({
                'name': _(
                    'Disposal of %s (accumulated depreciation '
                    'clearance)', asset.name or '',
                ),
                'account_id': asset.accumulated_depreciation_account_id.id,
                'debit': depreciation_share,
                'credit': 0.0,
            }),
        ]
        if self.disposal_method == 'sale' and proceeds > 0:
            commands.append(Command.create({
                'name': _(
                    'Disposal proceeds for %s', asset.name or '',
                ),
                'account_id': self.proceeds_account_id.id,
                'partner_id': (
                    asset.vendor_id.id if asset.vendor_id else False
                ),
                'debit': proceeds,
                'credit': 0.0,
            }))
        # Gain or loss line.
        if gain_loss > 0:
            commands.append(Command.create({
                'name': _(
                    'Gain on disposal of %s', asset.name or '',
                ),
                'account_id': self.gain_account_id.id,
                'debit': 0.0,
                'credit': gain_loss,
            }))
        elif gain_loss < 0:
            commands.append(Command.create({
                'name': _(
                    'Loss on disposal of %s', asset.name or '',
                ),
                'account_id': self.loss_account_id.id,
                'debit': abs(gain_loss),
                'credit': 0.0,
            }))
        move_vals = {
            'move_type': 'entry',
            'date': self.disposal_date,
            'journal_id': asset.journal_id.id,
            'company_id': asset.company_id.id,
            'ref': _(
                'Asset disposal (%(method)s): %(name)s',
                method=self.disposal_method,
                name=asset.reference or asset.name or '',
            ),
            'asset_id': asset.id,
            'asset_entry_type': 'disposal',
            'line_ids': commands,
        }
        move = self.env['account.move'].with_company(
            asset.company_id,
        ).create(move_vals)
        move.action_post()
        _logger.info(
            'Asset %s posted disposal entry %s '
            '(method=%s, gain_loss=%s).',
            asset.display_name,
            move.name,
            self.disposal_method,
            gain_loss,
        )
        return move
