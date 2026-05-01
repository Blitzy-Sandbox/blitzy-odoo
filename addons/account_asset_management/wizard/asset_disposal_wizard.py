# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Asset Disposal Wizard (FEATURE-004, AM-006).

Implements the ``account.asset.disposal.wizard`` TransientModel that
processes end-of-life asset removal via three methods:

    * **Sale** -- asset sold to an external party; proceeds recorded
      against a cash, bank, or receivable account; gain/loss recognized
      against the difference between proceeds and net book value.
    * **Scrap** -- asset removed with zero proceeds; the entire
      remaining net book value is written off as a loss on disposal.
    * **Write-off** -- asset removed with optional insurance recovery
      treated as proceeds equivalent (e.g., theft / fire / total loss).

After posting, the wizard transitions the asset to ``state='close'``
(full disposal) or proportionally reduces ``acquisition_cost`` while
keeping the asset open (partial disposal), records an immutable audit
trail message on the asset's chatter, and -- when needed -- posts a
pre-disposal catch-up depreciation entry covering the period between
the last posted depreciation and the disposal date.

Wizard Lifecycle
----------------

::

    draft     -- user fills in disposal method, date, optional
                 proceeds, and partial-disposal quantity.
    confirmed -- after ``action_confirm`` validates inputs and
                 computes the gain/loss preview.
    posted    -- after ``action_post`` creates the catch-up
                 depreciation entry (if required), the disposal
                 journal entry, and transitions the asset state.
    cancelled -- after ``action_cancel``; if previously posted, the
                 disposal and catch-up moves are reversed via Odoo's
                 standard ``_reverse_moves`` mechanism.

Acceptance Criteria Mapping (per AM-006 ticket)
-----------------------------------------------

* AC1 -- Three disposal methods: ``sale`` / ``scrap`` / ``write_off``.
* AC2 -- Catch-up depreciation through the disposal date for any
  unposted draft schedule lines on or before that date.
* AC3 -- Required documentation (``disposal_reason``,
  ``documentation_ref``) captured in the audit trail.
* AC4 -- Disposal date validation: ``>= acquisition_date`` and not in
  a locked fiscal period.
* AC5 -- Partial disposal support with proportional acquisition cost
  and accumulated depreciation calculations.
* AC6 -- GAAP / IFRS compliant journal entries with correct gain
  (credit income) / loss (debit expense) recognition.

Performance Budgets (per AAP section 0.1.2 / FEATURE-004)
---------------------------------------------------------

* Disposal journal entry creation: < 3 seconds per disposal.
* Catch-up depreciation calculation: < 5 seconds.
* Partial disposal calculation: < 3 seconds.

AAP Rule Compliance
-------------------

* R-01 (Module independence) -- No imports from sibling Community
  Edition modules (``account_budget_management``,
  ``account_deferred_revenue``, ``account_payment_followup``).
* R-02 (No Enterprise dependencies) -- No imports of any Odoo
  Enterprise module (``account_asset``, ``account_accountant``,
  ``account_reports``, etc.).
* R-03 (``_inherit`` / ``_name`` correctness) -- Declares ``_name``
  for a NET-NEW TransientModel. R-03 permits ``_name`` on net-new
  models. No ``_inherit`` extension of any core Odoo model is
  attempted.
* R-05 (No core field redefinition) -- Not applicable here: this
  file creates a NEW TransientModel; it does not extend
  ``account.move`` or ``account.move.line``.
* R-07 (No unjustified ``sudo``) -- This file contains NO
  ``.sudo()`` calls; all ORM operations execute under the wizard
  invoker's privileges as authorized by ``ir.model.access.csv``.
"""

import logging

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class AccountAssetDisposalWizard(models.TransientModel):
    """TransientModel wizard for AM-006 asset disposal workflows.

    Drives the user-facing form for sale, scrap, and write-off
    disposal types with automatic gain / loss calculation against
    net book value, optional pre-disposal catch-up depreciation,
    and partial-disposal support with proportional accounting.

    Each disposal produces up to two ``account.move`` records:

        1. ``catchup_depreciation_move_id`` -- catch-up depreciation
           covering the gap between the last posted depreciation and
           the disposal date (created only when required).
        2. ``move_id`` -- the main disposal entry: removes the
           asset's acquisition cost (credit asset account), clears
           the accumulated depreciation (debit accumulated account),
           records proceeds (debit cash / receivable), and balances
           with a gain (credit income) or loss (debit expense) line.

    The wizard runs under a single PostgreSQL savepoint so that any
    failure during posting rolls back both moves atomically; either
    everything posts cleanly or nothing persists.
    """

    _name = 'account.asset.disposal.wizard'
    _description = 'Asset Disposal Wizard'
    _check_company_auto = True

    # =========================================================================
    # CORE / COMPANY CONTEXT
    # =========================================================================

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        readonly=True,
        help=(
            'Company that owns the asset and under whose chart of '
            'accounts this disposal posts. Defaulted from the active '
            'company at wizard creation; readonly to enforce '
            'multi-company isolation in combination with '
            '``_check_company_auto = True``.'
        ),
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency',
        related='company_id.currency_id',
        readonly=True,
        store=False,
        help=(
            'Currency used for every Monetary field on this wizard. '
            'Derived from ``company_id.currency_id``; not stored to '
            'avoid duplication and to track company changes.'
        ),
    )

    # =========================================================================
    # ASSET SELECTION
    # =========================================================================

    asset_id = fields.Many2one(
        comodel_name='account.asset',
        string='Asset',
        required=True,
        ondelete='cascade',
        domain="[('state', '=', 'open'), ('company_id', '=', company_id)]",
        help=(
            'The asset being disposed. Must be in Running (``open``) '
            'state. The domain restricts selection to open assets in '
            'the current company; closed assets cannot be re-disposed '
            'and draft assets must first be confirmed.'
        ),
    )

    # =========================================================================
    # DISPOSAL CLASSIFICATION
    # =========================================================================

    disposal_method = fields.Selection(
        selection=[
            ('sale', 'Sale'),
            ('scrap', 'Scrap'),
            ('write_off', 'Write-Off'),
        ],
        string='Disposal Method',
        required=True,
        default='sale',
        help=(
            'AM-006 AC1 selector. ``sale`` -- proceeds flow to a '
            'receivable / cash account; gain/loss recognized on the '
            'difference vs. NBV. ``scrap`` -- zero proceeds; full NBV '
            'is a loss. ``write_off`` -- optional insurance recovery '
            'treated as proceeds equivalent (theft, fire, total loss).'
        ),
    )
    disposal_date = fields.Date(
        string='Disposal Date',
        required=True,
        default=fields.Date.context_today,
        help=(
            'The accounting date the disposal takes effect. Must be '
            '>= ``asset.acquisition_date`` and not fall on or before '
            'the company fiscal-year lock date (AM-006 AC4). The '
            'disposal journal entry is dated on this value.'
        ),
    )

    # =========================================================================
    # PROCEEDS
    # =========================================================================

    proceeds_amount = fields.Monetary(
        string='Proceeds Amount',
        currency_field='currency_id',
        default=0.0,
        help=(
            'Amount received (cash, bank, or receivable). Required '
            'and must be > 0 when ``disposal_method = sale``. Must '
            'be 0 when ``disposal_method = scrap`` (use ``write_off`` '
            'for insurance recoveries). May be 0 or positive for '
            '``write_off``; negative values are rejected.'
        ),
    )
    proceeds_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Proceeds Account',
        domain=(
            "[('account_type', 'in', "
            "('asset_receivable', 'asset_cash', 'asset_current'))]"
        ),
        check_company=True,
        help=(
            'Cash, bank, or accounts-receivable account debited by '
            'the proceeds amount. Required when '
            '``disposal_method = sale`` or any time '
            '``proceeds_amount > 0``. Filtered by account type to '
            'liquidity / receivable / current-asset accounts. '
            'Multi-company isolation is enforced by '
            '``check_company=True`` plus the model-level '
            '``_check_company_auto = True``.'
        ),
    )

    # =========================================================================
    # GAIN / LOSS
    # =========================================================================

    net_book_value = fields.Monetary(
        string='Net Book Value (at disposal date)',
        compute='_compute_net_book_value',
        store=False,
        readonly=True,
        currency_field='currency_id',
        help=(
            'Asset NBV at the disposal date. For a full disposal: '
            'the asset\'s current ``net_book_value``. For partial '
            'disposal: NBV multiplied by ``disposal_proportion``. '
            'After ``action_post`` runs, the gain/loss line uses the '
            'NBV recomputed AFTER the catch-up entry posts (the '
            'preview here is pre-catch-up).'
        ),
    )
    gain_loss_amount = fields.Monetary(
        string='Gain / Loss Amount',
        compute='_compute_gain_loss_amount',
        store=False,
        readonly=True,
        currency_field='currency_id',
        help=(
            'AM-006 formula: ``gain_loss_amount = proceeds_amount - '
            'net_book_value``. Positive = gain (credit income); '
            'negative = loss (debit expense); zero = breakeven '
            '(no gain/loss line).'
        ),
    )
    gain_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Gain Account',
        domain="[('account_type', 'in', ('income', 'income_other'))]",
        check_company=True,
        help=(
            'Income account credited when the disposal generates a '
            'gain (proceeds > NBV). Required when '
            '``gain_loss_amount > 0``. Multi-company isolation via '
            '``check_company=True``.'
        ),
    )
    loss_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Loss Account',
        domain=(
            "[('account_type', 'in', "
            "('expense', 'expense_direct_cost', 'expense_depreciation'))]"
        ),
        check_company=True,
        help=(
            'Expense account debited when the disposal generates a '
            'loss (proceeds < NBV). Required when '
            '``gain_loss_amount < 0`` OR when '
            '``disposal_method = scrap`` and NBV > 0. Multi-company '
            'isolation via ``check_company=True``.'
        ),
    )

    # =========================================================================
    # DOCUMENTATION (AM-006 AC3)
    # =========================================================================

    disposal_reason = fields.Text(
        string='Disposal Reason',
        required=True,
        help=(
            'AM-006 AC3 audit-trail justification (e.g., "End of '
            'useful life", "Damaged in transit", "Replaced by '
            'newer model"). Captured in the chatter audit message '
            'posted to the asset.'
        ),
    )
    documentation_ref = fields.Char(
        string='Documentation Reference',
        help=(
            'External reference number for the supporting document: '
            'sale contract, scrap certificate, insurance claim ID, '
            'police report number, etc. Persisted in the audit trail '
            'for compliance traceability.'
        ),
    )

    # =========================================================================
    # PARTIAL DISPOSAL (AM-006 AC5)
    # =========================================================================

    is_partial = fields.Boolean(
        string='Partial Disposal',
        default=False,
        help=(
            'Tick to dispose only a portion of the asset (e.g., 30 '
            'of 100 units). Requires ``disposed_quantity``. The '
            'asset remains in ``open`` state with reduced '
            '``acquisition_cost``; future depreciation continues on '
            'the retained portion.'
        ),
    )
    disposed_quantity = fields.Float(
        string='Disposed Quantity',
        default=0.0,
        digits='Product Unit of Measure',
        help=(
            'Quantity / units disposed (relevant for '
            'units-of-production assets and for divisible assets '
            'with explicit unit tracking). Must be > 0 and <= '
            '``total_quantity`` for partial disposals.'
        ),
    )
    total_quantity = fields.Float(
        string='Total Asset Quantity',
        compute='_compute_total_quantity',
        readonly=True,
        digits='Product Unit of Measure',
        help=(
            'The asset\'s total quantity. For units-of-production '
            'assets: ``asset.units_production_total``. For other '
            'assets: 1.0 (treated as a single divisible unit).'
        ),
    )
    disposal_proportion = fields.Float(
        string='Disposal Proportion',
        compute='_compute_disposal_proportion',
        readonly=True,
        digits=(12, 4),
        help=(
            'Fraction of the asset being disposed: '
            '``disposed_quantity / total_quantity``. Equals 1.0 for '
            'full disposal. Used to prorate ``acquisition_cost`` '
            'and ``accumulated_depreciation`` in the disposal '
            'journal entry.'
        ),
    )

    # =========================================================================
    # CATCH-UP DEPRECIATION (AM-006 AC2)
    # =========================================================================

    catchup_depreciation_required = fields.Boolean(
        string='Catch-up Depreciation Required',
        compute='_compute_catchup_required',
        store=False,
        readonly=True,
        help=(
            'True when the asset has unposted draft depreciation '
            'lines with ``depreciation_date <= disposal_date``. A '
            'catch-up depreciation entry will be posted before the '
            'main disposal entry to bring accumulated depreciation '
            'current through the disposal date (AM-006 AC2).'
        ),
    )
    catchup_depreciation_amount = fields.Monetary(
        string='Catch-up Depreciation Amount',
        compute='_compute_catchup_amount',
        store=False,
        readonly=True,
        currency_field='currency_id',
        help=(
            'Sum of the eligible draft depreciation-line amounts '
            '(those with ``depreciation_date <= disposal_date``), '
            'prorated by ``disposal_proportion`` for partial '
            'disposals. Posted as a single catch-up journal entry '
            'before the disposal entry.'
        ),
    )

    # =========================================================================
    # RESULT / STATE
    # =========================================================================

    move_id = fields.Many2one(
        comodel_name='account.move',
        string='Disposal Journal Entry',
        readonly=True,
        copy=False,
        help=(
            'The main disposal ``account.move`` created by '
            '``action_post()``. Tagged with '
            '``asset_entry_type=\'disposal\'`` for lifecycle '
            'reporting. Cleared on cancellation by '
            '``_reverse_moves``.'
        ),
    )
    catchup_depreciation_move_id = fields.Many2one(
        comodel_name='account.move',
        string='Catch-up Depreciation Entry',
        readonly=True,
        copy=False,
        help=(
            'The catch-up depreciation ``account.move`` created by '
            '``action_post()`` when '
            '``catchup_depreciation_required = True``. Tagged with '
            '``asset_entry_type=\'depreciation\'``. Posted BEFORE '
            'the main disposal entry so the gain/loss calculation '
            'uses the up-to-date NBV.'
        ),
    )
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
        copy=False,
        help=(
            'Wizard state machine: ``draft`` (initial input) -> '
            '``confirmed`` (validated, gain/loss previewed) -> '
            '``posted`` (journal entries posted, asset transitioned). '
            '``cancelled`` is reachable from any non-terminal state '
            'and (when posted) reverses the journal entries via '
            '``_reverse_moves``.'
        ),
    )

    # =========================================================================
    # COMPUTE METHODS
    # =========================================================================

    @api.depends(
        'asset_id',
        'asset_id.net_book_value',
        'is_partial',
        'disposal_proportion',
    )
    def _compute_net_book_value(self):
        """Compute the disposable NBV at the disposal date.

        For a full disposal, returns the asset's current
        ``net_book_value`` (a stored compute on ``account.asset``
        backed by the sum of posted depreciation lines).

        For a partial disposal, multiplies the asset NBV by the
        ``disposal_proportion`` so that only the disposed portion is
        recognized in the gain/loss calculation.

        This pre-catch-up preview drives the form's gain/loss display
        before posting; ``action_post`` recomputes the actual NBV
        after the catch-up entry posts to ensure the disposal entry
        is balanced against the correct carrying amount.
        """
        for wizard in self:
            asset_nbv = (
                wizard.asset_id.net_book_value
                if wizard.asset_id
                else 0.0
            )
            if wizard.is_partial and wizard.disposal_proportion:
                wizard.net_book_value = asset_nbv * wizard.disposal_proportion
            else:
                wizard.net_book_value = asset_nbv

    @api.depends('proceeds_amount', 'net_book_value')
    def _compute_gain_loss_amount(self):
        """Compute gain or loss using the AM-006 verbatim formula.

        ``gain_loss_amount = proceeds_amount - net_book_value``

        Positive => gain (credit gain account on the disposal entry).
        Negative => loss (debit loss account on the disposal entry).
        Zero     => breakeven (no gain/loss line; entry still
                    balances because debits and credits net out).
        """
        for wizard in self:
            wizard.gain_loss_amount = (
                (wizard.proceeds_amount or 0.0)
                - (wizard.net_book_value or 0.0)
            )

    @api.depends(
        'asset_id',
        'asset_id.depreciation_method',
        'asset_id.units_production_total',
    )
    def _compute_total_quantity(self):
        """Compute the asset's total disposable quantity.

        For units-of-production assets, the total quantity is the
        ``units_production_total`` configured at registration. For
        all other depreciation methods (straight-line, declining
        balance), the asset is treated as a single divisible unit
        (``total_quantity = 1.0``).
        """
        for wizard in self:
            if (
                wizard.asset_id
                and wizard.asset_id.depreciation_method
                == 'units_of_production'
            ):
                wizard.total_quantity = (
                    wizard.asset_id.units_production_total or 1.0
                )
            else:
                wizard.total_quantity = 1.0

    @api.depends('disposed_quantity', 'total_quantity', 'is_partial')
    def _compute_disposal_proportion(self):
        """Compute the disposal proportion (0.0 to 1.0).

        Always 1.0 for full disposals. For partial disposals,
        equals ``disposed_quantity / total_quantity`` clamped to
        the valid range. Returns 0.0 if ``total_quantity`` is zero
        to avoid division-by-zero (the constraint validator will
        reject the wizard before posting in that case).
        """
        for wizard in self:
            if not wizard.is_partial:
                wizard.disposal_proportion = 1.0
            elif wizard.total_quantity:
                wizard.disposal_proportion = (
                    (wizard.disposed_quantity or 0.0)
                    / wizard.total_quantity
                )
            else:
                wizard.disposal_proportion = 0.0

    @api.depends(
        'asset_id',
        'asset_id.depreciation_line_ids',
        'asset_id.depreciation_line_ids.state',
        'asset_id.depreciation_line_ids.depreciation_date',
        'disposal_date',
    )
    def _compute_catchup_required(self):
        """Detect unposted depreciation through the disposal date.

        Filters ``asset.depreciation_line_ids`` to lines in
        ``state='draft'`` whose ``depreciation_date <=
        disposal_date``. If at least one such line exists, the
        catch-up entry is required and ``action_post()`` will post
        it before the main disposal entry (AM-006 AC2 / Scenario 6).
        """
        for wizard in self:
            if not wizard.asset_id or not wizard.disposal_date:
                wizard.catchup_depreciation_required = False
                continue
            disposal_date = wizard.disposal_date
            pending = wizard.asset_id.depreciation_line_ids.filtered(
                lambda line: (
                    line.state == 'draft'
                    and line.depreciation_date
                    and line.depreciation_date <= disposal_date
                ),
            )
            wizard.catchup_depreciation_required = bool(pending)

    @api.depends(
        'asset_id',
        'asset_id.depreciation_line_ids.state',
        'asset_id.depreciation_line_ids.depreciation_date',
        'asset_id.depreciation_line_ids.depreciation_amount',
        'disposal_date',
        'is_partial',
        'disposal_proportion',
    )
    def _compute_catchup_amount(self):
        """Sum the eligible draft depreciation-line amounts.

        Aggregates ``depreciation_amount`` across all draft lines
        with ``depreciation_date <= disposal_date``, then prorates
        by ``disposal_proportion`` for partial disposals. The
        resulting amount becomes the debit/credit on the catch-up
        depreciation entry created by ``_create_catchup_move``.
        """
        for wizard in self:
            if not wizard.asset_id or not wizard.disposal_date:
                wizard.catchup_depreciation_amount = 0.0
                continue
            disposal_date = wizard.disposal_date
            pending = wizard.asset_id.depreciation_line_ids.filtered(
                lambda line: (
                    line.state == 'draft'
                    and line.depreciation_date
                    and line.depreciation_date <= disposal_date
                ),
            )
            total = sum(pending.mapped('depreciation_amount'))
            if wizard.is_partial and wizard.disposal_proportion:
                total *= wizard.disposal_proportion
            wizard.catchup_depreciation_amount = total

    # =========================================================================
    # ONCHANGE METHODS
    # =========================================================================

    @api.onchange('disposal_method')
    def _onchange_disposal_method(self):
        """Clear inapplicable fields when the disposal method changes.

        For ``scrap`` disposals, force ``proceeds_amount`` to zero
        and clear ``proceeds_account_id`` (scrap recognizes the full
        NBV as a loss; insurance recoveries belong on ``write_off``).

        For ``write_off``, proceeds remain optional (the user may
        enter an insurance recovery amount or leave at zero).

        For ``sale``, no automatic clearing -- the user supplies
        proceeds and account explicitly.
        """
        if self.disposal_method == 'scrap':
            self.proceeds_amount = 0.0
            self.proceeds_account_id = False

    @api.onchange('is_partial')
    def _onchange_is_partial(self):
        """Reset ``disposed_quantity`` when toggling the partial flag.

        Switching from partial to full disposal clears any leftover
        ``disposed_quantity`` value so that the proportion correctly
        defaults to 1.0 (computed by ``_compute_disposal_proportion``).
        """
        if not self.is_partial:
            self.disposed_quantity = 0.0

    @api.onchange('asset_id')
    def _onchange_asset_id(self):
        """Inherit company context from the selected asset.

        When the user selects an asset, propagate its ``company_id``
        to the wizard's ``company_id``. This keeps the multi-company
        domains on ``proceeds_account_id``, ``gain_account_id``, and
        ``loss_account_id`` consistent with the asset's company.
        Account fields themselves remain user-chosen (no automatic
        defaults to avoid leaking inappropriate accounts for
        specific disposal scenarios).
        """
        if self.asset_id and self.asset_id.company_id:
            # Force the wizard's company_id to follow the asset's
            # company so that account-domain filters and
            # ``check_company`` behave correctly for the picked
            # asset, even when the user opened the wizard from a
            # different default company context.
            self.company_id = self.asset_id.company_id

    # =========================================================================
    # PYTHON CONSTRAINTS
    # =========================================================================

    @api.constrains('disposal_date', 'asset_id')
    def _check_disposal_date(self):
        """AM-006 AC4: validate the disposal date.

        Two rules are enforced:

            1. ``disposal_date >= asset.acquisition_date`` -- it is
               accounting-impossible to dispose an asset before it
               was acquired.
            2. ``disposal_date > company.fiscalyear_lock_date`` --
               posting into a locked period is forbidden; an admin
               must clear or extend the lock first.
        """
        for wizard in self:
            if not wizard.asset_id or not wizard.disposal_date:
                continue
            asset = wizard.asset_id
            if (
                asset.acquisition_date
                and wizard.disposal_date < asset.acquisition_date
            ):
                raise ValidationError(_(
                    'Disposal date (%(disp)s) cannot be earlier than '
                    'the asset acquisition date (%(acq)s).',
                    disp=wizard.disposal_date,
                    acq=asset.acquisition_date,
                ))
            company = asset.company_id or wizard.company_id
            fiscal_lock_date = (
                company.fiscalyear_lock_date if company else False
            )
            if (
                fiscal_lock_date
                and wizard.disposal_date <= fiscal_lock_date
            ):
                raise ValidationError(_(
                    'Disposal date (%(disp)s) is in a locked fiscal '
                    'period (lock date: %(lock)s). Choose a date '
                    'after the lock date or have a manager clear '
                    'the lock exception.',
                    disp=wizard.disposal_date,
                    lock=fiscal_lock_date,
                ))

    @api.constrains(
        'disposal_method',
        'proceeds_amount',
        'proceeds_account_id',
    )
    def _check_proceeds_configuration(self):
        """Validate proceeds-amount / proceeds-account combinations.

        Method-specific rules:

            * ``sale``       -- proceeds_account required;
                                proceeds_amount must be > 0.
            * ``scrap``      -- proceeds_amount must be exactly 0
                                (use ``write_off`` for insurance
                                recoveries).
            * ``write_off``  -- proceeds_amount must be >= 0.

        Cross-method rule: any time ``proceeds_amount > 0``,
        ``proceeds_account_id`` is required (the entry can't be
        posted without a destination account for the cash/AR debit).
        """
        for wizard in self:
            if wizard.disposal_method == 'sale':
                if not wizard.proceeds_account_id:
                    raise ValidationError(_(
                        'Proceeds Account is required for a sale.',
                    ))
                if wizard.proceeds_amount <= 0:
                    raise ValidationError(_(
                        'Proceeds Amount must be positive for a sale.',
                    ))
            elif (
                wizard.disposal_method == 'scrap'
                and wizard.proceeds_amount != 0
            ):
                raise ValidationError(_(
                    'Scrap disposal must have zero proceeds; use '
                    'Write-Off for insurance recoveries.',
                ))
            elif (
                wizard.disposal_method == 'write_off'
                and wizard.proceeds_amount < 0
            ):
                raise ValidationError(_(
                    'Proceeds Amount cannot be negative.',
                ))
            # Cross-method: proceeds without account is invalid.
            if (
                wizard.proceeds_amount > 0
                and not wizard.proceeds_account_id
            ):
                raise ValidationError(_(
                    'Proceeds Account is required when Proceeds '
                    'Amount is greater than zero.',
                ))

    @api.constrains(
        'proceeds_amount',
        'asset_id',
        'is_partial',
        'disposed_quantity',
        'gain_account_id',
        'loss_account_id',
        'disposal_method',
    )
    def _check_gain_loss_accounts(self):
        """Validate gain / loss account selection.

        Three rules:

            1. If ``gain_loss_amount > 0`` (gain), require
               ``gain_account_id``.
            2. If ``gain_loss_amount < 0`` (loss), require
               ``loss_account_id``.
            3. If ``disposal_method = scrap`` and the asset has
               positive NBV, require ``loss_account_id`` -- scrap
               always recognizes a loss equal to the NBV.
        """
        for wizard in self:
            if (
                wizard.gain_loss_amount > 0
                and not wizard.gain_account_id
            ):
                raise ValidationError(_(
                    'Gain Account is required when the disposal '
                    'produces a gain (proceeds > NBV).',
                ))
            if (
                wizard.gain_loss_amount < 0
                and not wizard.loss_account_id
            ):
                raise ValidationError(_(
                    'Loss Account is required when the disposal '
                    'produces a loss (proceeds < NBV).',
                ))
            if (
                wizard.disposal_method == 'scrap'
                and (wizard.net_book_value or 0.0) > 0
                and not wizard.loss_account_id
            ):
                raise ValidationError(_(
                    'Loss Account is required for scrap disposal '
                    'to absorb the net book value.',
                ))

    @api.constrains('is_partial', 'disposed_quantity', 'asset_id')
    def _check_partial_quantity(self):
        """Validate partial-disposal quantities.

        For ``is_partial = True``:

            * ``disposed_quantity > 0``
            * ``disposed_quantity <= total_quantity``

        Full disposals (``is_partial = False``) skip these checks
        because ``disposal_proportion`` is forced to 1.0.
        """
        for wizard in self:
            if not wizard.is_partial:
                continue
            if wizard.disposed_quantity <= 0:
                raise ValidationError(_(
                    'Disposed Quantity must be greater than zero '
                    'for a partial disposal.',
                ))
            if wizard.disposed_quantity > wizard.total_quantity:
                raise ValidationError(_(
                    'Disposed Quantity (%(disp).4f) cannot exceed '
                    'total asset quantity (%(tot).4f).',
                    disp=wizard.disposed_quantity,
                    tot=wizard.total_quantity,
                ))

    # =========================================================================
    # ACTION METHODS
    # =========================================================================

    def action_confirm(self):
        """Transition draft -> confirmed.

        Re-runs every ``@api.constrains`` validator to provide
        belt-and-braces protection against in-memory state changes
        that haven't yet been persisted (constrains fires on write,
        not on transient-only mutations). On success, sets
        ``state = 'confirmed'`` and re-opens the wizard form so the
        user sees the gain/loss preview before clicking Post.

        Returns:
            dict: ``ir.actions.act_window`` re-displaying the
            wizard form so the user can review and post.

        Raises:
            UserError: when the wizard is not in ``draft`` state.
            ValidationError: when any constraint fails.
        """
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_(
                'Only draft disposals can be confirmed.',
            ))
        if self.asset_id.state != 'open':
            raise UserError(_(
                'Disposal is only permitted on open assets '
                '(asset "%(name)s" is in state "%(state)s").',
                name=self.asset_id.name or '',
                state=self.asset_id.state,
            ))
        # Force constraint re-check -- belt-and-braces validation
        # for in-memory state that may not yet have triggered the
        # @api.constrains decorators on write.
        self._check_disposal_date()
        self._check_proceeds_configuration()
        self._check_gain_loss_accounts()
        self._check_partial_quantity()
        self.write({'state': 'confirmed'})
        _logger.info(
            'AM-006: disposal wizard %d confirmed for asset %s '
            '(method=%s, disposal_date=%s, partial=%s).',
            self.id,
            self.asset_id.display_name,
            self.disposal_method,
            self.disposal_date,
            self.is_partial,
        )
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_post(self):
        """Post catch-up depreciation (if required) and the disposal.

        The operation is wrapped in a single PostgreSQL savepoint:
        either both entries post successfully and the asset
        transitions to ``close`` (full) or its acquisition cost is
        reduced (partial), or nothing persists (rollback on any
        unhandled exception).

        Journal entry structure per disposal_method (AM-006 AC1-3):

        * **Sale** (proceeds > 0)::

              DR  proceeds_account_id            proceeds_amount
              DR  accumulated_depreciation_acct  accum_depr
              CR  asset_account_id               acquisition_cost
              DR  loss_account_id                |loss|  (if loss)
              CR  gain_account_id                gain    (if gain)

        * **Scrap** (proceeds = 0)::

              DR  accumulated_depreciation_acct  accum_depr
              DR  loss_account_id                NBV (full loss)
              CR  asset_account_id               acquisition_cost

        * **Write-off** (proceeds >= 0): structurally identical to
          sale when ``proceeds > 0``, identical to scrap otherwise.

        Partial disposal: the asset-side amounts are multiplied by
        ``disposal_proportion``; the asset's ``acquisition_cost``
        is reduced by the same proportion and the asset stays open
        with a recomputed depreciation schedule.

        Returns:
            dict: ``ir.actions.act_window`` refreshing the wizard
            form so the user sees the linked journal entries and
            posted state.

        Raises:
            UserError: when the wizard is not in ``confirmed`` state
                or when posting fails (savepoint already rolled back).
        """
        self.ensure_one()
        if self.state != 'confirmed':
            raise UserError(_(
                'Only confirmed disposals can be posted. '
                'Confirm first.',
            ))
        asset = self.asset_id
        if not asset:
            raise UserError(_('No asset selected.'))

        catchup_move = self.env['account.move']
        disposal_move = self.env['account.move']

        try:
            # Single savepoint wraps the multi-move pipeline so
            # partial failures roll back atomically.
            with self.env.cr.savepoint():
                # 1. Post catch-up depreciation FIRST so the main
                #    disposal entry uses the up-to-date NBV.
                if (
                    self.catchup_depreciation_required
                    and not asset.currency_id.is_zero(
                        self.catchup_depreciation_amount,
                    )
                ):
                    catchup_move = self._create_catchup_move()

                # 2. Force asset cache refresh so the disposal-move
                #    builder reads the post-catch-up
                #    accumulated_depreciation and net_book_value.
                asset.invalidate_recordset(
                    ['accumulated_depreciation', 'net_book_value'],
                )

                # 3. Create and post the main disposal entry.
                disposal_move = self._create_disposal_move()

                # 4. Transition the asset state.
                if self.is_partial:
                    # Partial: reduce acquisition_cost
                    # proportionally; recompute the schedule on the
                    # retained portion. Asset stays in 'open' state.
                    new_cost = asset.acquisition_cost * (
                        1.0 - self.disposal_proportion
                    )
                    asset.write({'acquisition_cost': new_cost})
                    # Recompute the schedule for the reduced cost
                    # so future depreciation aligns with the
                    # remaining carrying amount.
                    asset._compute_depreciation_schedule()
                else:
                    # Full disposal: transition asset to 'close'.
                    asset.action_close()

                # 5. Audit trail on the asset's chatter.
                audit_body = self._format_audit_message(
                    disposal_move,
                    catchup_move,
                )
                asset.message_post(body=audit_body)

                # 6. Persist references and transition wizard state.
                self.write({
                    'move_id': (
                        disposal_move.id if disposal_move else False
                    ),
                    'catchup_depreciation_move_id': (
                        catchup_move.id if catchup_move else False
                    ),
                    'state': 'posted',
                })

                _logger.info(
                    'AM-006: disposal wizard %d posted for asset %s '
                    '(method=%s, proceeds=%.2f, gain_loss=%.2f, '
                    'move=%s, catchup=%s).',
                    self.id,
                    asset.display_name,
                    self.disposal_method,
                    self.proceeds_amount or 0.0,
                    self.gain_loss_amount or 0.0,
                    disposal_move.name if disposal_move else 'N/A',
                    catchup_move.name if catchup_move else 'N/A',
                )

        except (UserError, ValidationError):
            # Re-raise Odoo business exceptions verbatim so users
            # see their proper messages; the savepoint context
            # manager has already rolled back the partial state.
            raise
        except Exception as exc:
            # Any other exception: log full traceback and re-raise
            # as a UserError with a friendly message. The savepoint
            # has already rolled back all changes.
            _logger.exception(
                'AM-006: error posting disposal for asset %s',
                asset.display_name if asset else 'n/a',
            )
            raise UserError(_(
                'Posting failed: %s', exc,
            )) from exc

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_cancel(self):
        """Cancel the wizard.

        From any non-terminal state, transitions to ``cancelled``.
        If the wizard was previously posted, reverses both the
        disposal and catch-up moves via Odoo's standard
        ``_reverse_moves`` mechanism (which preserves analytic /
        reconciliation / audit trail continuity) and re-opens the
        asset by calling ``action_set_draft`` (admin must
        re-confirm to bring the asset back to 'open' state).

        Returns:
            dict: ``ir.actions.act_window`` refreshing the wizard
            form so the user sees the cancelled state and any
            reversal entry references.
        """
        self.ensure_one()
        if self.state == 'cancelled':
            raise UserError(_(
                'This disposal is already cancelled.',
            ))
        reversal_names = []
        if self.state == 'posted':
            # Reverse the disposal move first, then the catch-up
            # move (LIFO order to mirror posting sequence).
            if self.move_id:
                disposal_reversal = self.move_id._reverse_moves(
                    default_values_list=[{
                        'date': fields.Date.context_today(self),
                        'ref': _(
                            'Reversal of disposal %s',
                            self.move_id.name or '',
                        ),
                    }],
                    cancel=True,
                )
                if disposal_reversal:
                    reversal_names.append(
                        disposal_reversal.name or '',
                    )
            if self.catchup_depreciation_move_id:
                catchup_reversal = (
                    self.catchup_depreciation_move_id._reverse_moves(
                        default_values_list=[{
                            'date': fields.Date.context_today(self),
                            'ref': _(
                                'Reversal of catch-up %s',
                                self.catchup_depreciation_move_id.name
                                or '',
                            ),
                        }],
                        cancel=True,
                    )
                )
                if catchup_reversal:
                    reversal_names.append(
                        catchup_reversal.name or '',
                    )
            # Re-open the asset if it was fully disposed (partial
            # disposals only adjusted acquisition_cost; the asset
            # stayed open).
            if (
                not self.is_partial
                and self.asset_id
                and self.asset_id.state == 'close'
            ):
                # Transition the asset back to 'open' directly via
                # write. action_set_draft only accepts assets in
                # 'open' state and would also wipe the schedule;
                # since we have already reversed the disposal moves,
                # the asset's schedule and acquisition entry remain
                # intact and the asset should resume in 'open'.
                # The chatter ``tracking=True`` on ``state`` records
                # the close -> open transition for audit purposes.
                self.asset_id.write({'state': 'open'})
            # Audit trail on the asset chatter.
            if self.asset_id:
                self.asset_id.message_post(body=_(
                    'Disposal cancelled; reversal entries posted: '
                    '%s',
                    ', '.join(filter(None, reversal_names))
                    or _('(none needed)'),
                ))
            _logger.info(
                'AM-006: disposal wizard %d cancelled (reversals=%s).',
                self.id,
                reversal_names,
            )
        self.write({'state': 'cancelled'})
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    # =========================================================================
    # PRIVATE HELPERS
    # =========================================================================

    def _create_catchup_move(self):
        """Create and post the catch-up depreciation move.

        Standard depreciation entry::

            DR  asset.expense_account_id              catchup_amount
            CR  asset.accumulated_depreciation_account catchup_amount

        Tagged with ``asset_entry_type='depreciation'`` for proper
        classification in the asset-entry timeline. The move is
        immediately posted via ``action_post()``.

        Returns:
            recordset: The freshly-posted ``account.move`` singleton,
                or an empty ``account.move`` if the catch-up amount
                rounds to zero in the asset's currency.
        """
        self.ensure_one()
        asset = self.asset_id
        amount = self.catchup_depreciation_amount or 0.0
        currency = asset.currency_id or asset.company_id.currency_id
        if currency.is_zero(amount):
            return self.env['account.move']

        rounded_amount = currency.round(amount)
        move_vals = {
            'move_type': 'entry',
            'date': self.disposal_date,
            'journal_id': asset.journal_id.id,
            'company_id': asset.company_id.id,
            'ref': _(
                'Catch-up depreciation for %s',
                asset.reference or asset.name or '',
            ),
            'asset_id': asset.id,
            'asset_entry_type': 'depreciation',
            'line_ids': [
                Command.create({
                    'name': _(
                        'Catch-up depreciation %s',
                        asset.name or '',
                    ),
                    'account_id': asset.expense_account_id.id,
                    'debit': rounded_amount,
                    'credit': 0.0,
                }),
                Command.create({
                    'name': _(
                        'Accumulated depreciation %s',
                        asset.name or '',
                    ),
                    'account_id': (
                        asset.accumulated_depreciation_account_id.id
                    ),
                    'debit': 0.0,
                    'credit': rounded_amount,
                }),
            ],
        }
        move = self.env['account.move'].with_company(
            asset.company_id,
        ).create(move_vals)
        move.action_post()
        # Mark the underlying draft schedule lines as 'posted' so
        # the cron does not re-post them. The covered lines are
        # those whose depreciation_date is on or before the
        # disposal_date.
        covered_lines = asset.depreciation_line_ids.filtered(
            lambda line: (
                line.state == 'draft'
                and line.depreciation_date
                and line.depreciation_date <= self.disposal_date
            ),
        )
        if covered_lines:
            covered_lines.write({
                'state': 'posted',
                'move_id': move.id,
            })
        _logger.info(
            'AM-006: catch-up depreciation move %s posted for '
            'asset %s (amount=%.2f, lines_covered=%d).',
            move.name,
            asset.display_name,
            rounded_amount,
            len(covered_lines),
        )
        return move

    def _create_disposal_move(self):
        """Create and post the main disposal move.

        Line composition (all entries balanced; line order does not
        affect Odoo balancing):

            * Remove the asset from books: CR ``asset_account_id``
              for ``acquisition_cost`` (prorated for partial).
            * Remove accumulated depreciation: DR
              ``accumulated_depreciation_account_id`` for
              ``accumulated_depreciation`` (prorated for partial).
            * Record proceeds: DR ``proceeds_account_id`` for
              ``proceeds_amount`` (when > 0).
            * Record gain or loss:
                - Gain (proceeds > NBV): CR ``gain_account_id``.
                - Loss (proceeds < NBV): DR ``loss_account_id``.
                - Breakeven (proceeds == NBV): no gain/loss line.

        Tagged with ``asset_entry_type='disposal'`` for proper
        classification in the asset-entry timeline. Posted via
        ``action_post()``.

        Returns:
            recordset: The freshly-posted ``account.move`` singleton.
        """
        self.ensure_one()
        asset = self.asset_id
        proportion = (
            self.disposal_proportion if self.is_partial else 1.0
        )
        currency = asset.currency_id or asset.company_id.currency_id

        # Prorate asset-side amounts for partial disposals.
        disposal_cost = currency.round(
            (asset.acquisition_cost or 0.0) * proportion,
        )
        disposal_accum = currency.round(
            (asset.accumulated_depreciation or 0.0) * proportion,
        )
        # Recompute the prorated NBV directly from cost and accum
        # (post-catch-up). This is the basis for the gain/loss
        # actually posted, which may differ slightly from the
        # pre-catch-up preview shown on the form.
        disposal_nbv = disposal_cost - disposal_accum
        proceeds = currency.round(self.proceeds_amount or 0.0)
        gain_loss = proceeds - disposal_nbv

        line_vals = []

        # 1. Remove the asset (credit asset account).
        if not currency.is_zero(disposal_cost):
            line_vals.append(Command.create({
                'name': _(
                    'Disposal of %s (asset removal)',
                    asset.name or '',
                ),
                'account_id': asset.asset_account_id.id,
                'debit': 0.0,
                'credit': disposal_cost,
            }))

        # 2. Remove accumulated depreciation (debit contra-asset).
        if not currency.is_zero(disposal_accum):
            line_vals.append(Command.create({
                'name': _(
                    'Disposal of %s (accumulated depreciation '
                    'clearance)',
                    asset.name or '',
                ),
                'account_id': (
                    asset.accumulated_depreciation_account_id.id
                ),
                'debit': disposal_accum,
                'credit': 0.0,
            }))

        # 3. Record proceeds (debit cash / receivable).
        if not currency.is_zero(proceeds):
            partner_id = (
                asset.vendor_id.id
                if asset.vendor_id
                else False
            )
            line_vals.append(Command.create({
                'name': _(
                    'Proceeds from disposal of %s',
                    asset.name or '',
                ),
                'account_id': self.proceeds_account_id.id,
                'partner_id': partner_id,
                'debit': proceeds,
                'credit': 0.0,
            }))

        # 4. Record gain or loss.
        if currency.compare_amounts(gain_loss, 0.0) > 0:
            # Gain: credit income account.
            line_vals.append(Command.create({
                'name': _(
                    'Gain on disposal of %s',
                    asset.name or '',
                ),
                'account_id': self.gain_account_id.id,
                'debit': 0.0,
                'credit': gain_loss,
            }))
        elif currency.compare_amounts(gain_loss, 0.0) < 0:
            # Loss: debit expense account.
            line_vals.append(Command.create({
                'name': _(
                    'Loss on disposal of %s',
                    asset.name or '',
                ),
                'account_id': self.loss_account_id.id,
                'debit': abs(gain_loss),
                'credit': 0.0,
            }))
        # Breakeven (gain_loss == 0): no gain/loss line; entry is
        # already balanced by debits and credits cancelling out.

        method_label = dict(
            self._fields['disposal_method'].selection,
        ).get(self.disposal_method, self.disposal_method or '')
        move_vals = {
            'move_type': 'entry',
            'date': self.disposal_date,
            'journal_id': asset.journal_id.id,
            'company_id': asset.company_id.id,
            'ref': _(
                'Asset disposal (%(method)s): %(ref)s',
                method=method_label,
                ref=asset.reference or asset.name or '',
            ),
            'asset_id': asset.id,
            'asset_entry_type': 'disposal',
            'line_ids': line_vals,
        }
        move = self.env['account.move'].with_company(
            asset.company_id,
        ).create(move_vals)
        move.action_post()
        _logger.info(
            'AM-006: disposal move %s posted for asset %s '
            '(method=%s, proportion=%.4f, cost=%.2f, accum=%.2f, '
            'proceeds=%.2f, gain_loss=%.2f).',
            move.name,
            asset.display_name,
            self.disposal_method,
            proportion,
            disposal_cost,
            disposal_accum,
            proceeds,
            gain_loss,
        )
        return move

    def _format_audit_message(self, disposal_move, catchup_move):
        """Format the chatter message posted to the asset's mail.thread.

        Captures every audit-relevant attribute of the disposal in
        a single HTML-formatted message for the chatter timeline:

            * disposal method
            * disposal date
            * proceeds (formatted in the asset's currency)
            * net book value (post-catch-up)
            * gain / loss
            * documentation reference (if provided)
            * partial disposal quantity (if applicable)
            * disposal and catch-up entry references

        Returns:
            str: HTML-formatted audit-trail message ready for
            ``asset.message_post(body=...)``.
        """
        self.ensure_one()
        method_label = dict(
            self._fields['disposal_method'].selection,
        ).get(self.disposal_method, self.disposal_method or '')
        currency = (
            self.currency_id
            or (self.asset_id and self.asset_id.currency_id)
            or self.env.company.currency_id
        )
        body_parts = [
            _('<b>Asset Disposal Posted</b>'),
            '<br/>',
            _('Method: %s', method_label),
            '<br/>',
            _('Disposal Date: %s', self.disposal_date),
            '<br/>',
            _(
                'Proceeds: %s',
                currency.round(self.proceeds_amount or 0.0),
            ),
            '<br/>',
            _(
                'Net Book Value: %s',
                currency.round(self.net_book_value or 0.0),
            ),
            '<br/>',
            _(
                'Gain/Loss: %s',
                currency.round(self.gain_loss_amount or 0.0),
            ),
            '<br/>',
            _('Reason: %s', self.disposal_reason or ''),
        ]
        if self.documentation_ref:
            body_parts.append('<br/>')
            body_parts.append(_(
                'Documentation Ref: %s',
                self.documentation_ref,
            ))
        if self.is_partial:
            body_parts.append('<br/>')
            body_parts.append(_(
                'Partial Disposal: %(disp).4f of %(tot).4f units',
                disp=self.disposed_quantity or 0.0,
                tot=self.total_quantity or 0.0,
            ))
        if disposal_move:
            body_parts.append('<br/>')
            body_parts.append(_(
                'Disposal Entry: %s',
                disposal_move.name or '',
            ))
        if catchup_move:
            body_parts.append('<br/>')
            body_parts.append(_(
                'Catch-up Depreciation Entry: %s',
                catchup_move.name or '',
            ))
        return ''.join(body_parts)
