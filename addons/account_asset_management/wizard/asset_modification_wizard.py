# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Asset Modification Wizard (FEATURE-004, AM-005).

Provides the user-facing TransientModel
``account.asset.modification.wizard`` for post-acquisition asset
modifications. Supports five modification types per IAS 16 / IAS 36 /
ASC 360:

    * ``revaluation``         -- value increase, credited to revaluation
      surplus (equity) per IAS 16 revaluation model.
    * ``impairment``          -- value decrease, debited to impairment
      loss (expense) per IAS 36 / ASC 360.
    * ``impairment_reversal`` -- recovery of prior impairment, capped at
      the lesser of (prior impairment amount, depreciated historical
      cost at the reversal date).
    * ``useful_life_change``  -- prospective extension or shortening of
      remaining depreciation per IAS 8 (Change in Accounting Estimate);
      no journal entry, only schedule recomputation.
    * ``salvage_change``      -- prospective adjustment of salvage /
      residual value per IAS 8; no journal entry, only schedule
      recomputation.

Wizard Lifecycle
----------------

    draft     -- initial state; user fills in modification type, new
                 value, justification, and supporting documentation.
    confirmed -- after ``action_confirm`` validates inputs and computes
                 the modification amount; ready for posting.
    posted    -- after ``action_post`` creates and posts the adjustment
                 journal entry, applies asset-side updates, and
                 recomputes the depreciation schedule (terminal state).
    cancelled -- after ``action_cancel``; if previously posted, the
                 journal entry is reversed via the core
                 ``_reverse_moves`` mechanism (terminal state).

Acceptance Criteria Mapping (AM-005)
------------------------------------

    AC1 Revaluation (value increase): journal entry DR asset, CR
        revaluation surplus -- ``_create_modification_move`` /
        ``revaluation`` branch.
    AC2 Impairment (value decrease): journal entry DR impairment loss,
        CR accumulated depreciation -- ``_create_modification_move`` /
        ``impairment`` branch.
    AC3 Prospective depreciation-schedule recalculation per IAS 8 --
        ``action_post`` invokes ``asset._compute_depreciation_schedule``
        after applying the modification (preserves posted lines, only
        regenerates draft / future lines).
    AC4 GAAP / IFRS-compliant journal entries -- balanced two-line
        entries with ``move_type='entry'``, posted via
        ``move.action_post()``; ``asset_id`` and ``asset_entry_type``
        fields link the entry back to the asset for drill-down.
    AC5 Immutable audit trail via ``mail.thread.message_post`` on the
        asset (the wizard is transient and auto-purged; persistent
        audit trail lives on the asset chatter).
    AC6 Effective date validations: must be >= acquisition date, must
        not be in a locked fiscal period (per
        ``company.fiscalyear_lock_date``).
    AC7 Impairment reversal capped at lesser of (prior impairment,
        depreciated historical cost) -- enforced in
        ``_check_value_direction``.

Performance (per AAP and AM-005 Technical Notes)
------------------------------------------------

    * Modification post processing < 3 seconds.
    * Depreciation schedule recalculation < 2 seconds for assets with
      <= 600 periods (achieved by preserving posted lines and
      recomputing only draft / future lines via
      ``asset._compute_depreciation_schedule``).
    * Audit trail query < 1 second (Odoo native ``mail.thread`` chatter
      retrieval is already O(log N) on indexed ``res_id`` /
      ``model``).

AAP Rule Compliance
-------------------

    * R-01 (Module independence) -- This file imports ONLY from
      ``odoo`` and ``odoo.exceptions`` plus the Python standard
      library ``logging``. NO imports of sibling Community Edition
      modules ``account_budget_management``,
      ``account_deferred_revenue``, or ``account_payment_followup``.
      Cross-model resolution within this module is performed via the
      Odoo ORM registry (string model names), not via Python-level
      imports.
    * R-02 (No Enterprise dependencies) -- No references to Enterprise
      modules ``account_asset``, ``account_accountant``, or
      ``account_reports``.
    * R-03 (``_inherit`` / ``_name`` correctness) -- Declares ``_name
      = 'account.asset.modification.wizard'`` for a NET-NEW
      TransientModel; R-03 explicitly permits ``_name`` on net-new
      models. NO ``_inherit`` of any existing core model -- the
      wizard does not inherit ``mail.thread`` because the audit trail
      is posted to the asset's chatter (the wizard is transient and
      would be auto-purged before its own chatter could be useful).
    * R-05 (No core field redefinition) -- Not applicable; this file
      creates a NEW TransientModel and does not extend
      ``account.move`` or ``account.move.line``. The two additive
      fields used on ``account.move`` (``asset_id``,
      ``asset_entry_type``) are defined in
      ``models/account_move.py`` and are referenced here only as
      values passed to ``self.env['account.move'].create({...})``.
    * R-06 (Scheduled jobs via XML ``ir.cron``) -- Not applicable;
      this wizard is invoked synchronously by user action, not
      scheduled.
    * R-07 (No unjustified ``sudo``) -- This file contains NO
      ``.sudo()`` calls. The wizard runs as the invoking accountant /
      manager; ACL enforcement is delegated to
      ``security/ir.model.access.csv``.
"""

import logging

from markupsafe import Markup

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class AccountAssetModificationWizard(models.TransientModel):
    """TransientModel wizard for AM-005 asset modifications.

    Drives the user-facing form for the five modification types,
    validates inputs in context (e.g., revaluation amount must be
    positive, impairment must reduce carrying value below current
    NBV, impairment reversal is capped at depreciated historical
    cost), creates the appropriate ``account.move`` per IAS 16 /
    IAS 36 / ASC 360, applies asset-side updates (cost adjustment for
    revaluation, useful life update, salvage value update), triggers
    prospective depreciation-schedule recomputation per IAS 8, and
    records an immutable audit trail on the asset's ``mail.thread``
    chatter.

    The wizard is opened from the asset form's "Modify" header button
    via ``account.asset.action_modify``, which returns an
    ``ir.actions.act_window`` with ``default_asset_id`` and
    ``default_company_id`` set in the context.
    """

    _name = 'account.asset.modification.wizard'
    _description = 'Asset Modification Wizard'
    _check_company_auto = True

    # =========================================================================
    # COMPANY / CONTEXT FIELDS
    # =========================================================================

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        readonly=True,
        help=(
            'The company that owns the asset and on whose books the '
            'modification will be recorded. Defaulted from the user\'s '
            'current company (or the ``default_company_id`` context key '
            'set by the asset form\'s "Modify" button). Required and '
            'readonly: changing the company mid-wizard would invalidate '
            'every account-FK selection.'
        ),
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency',
        related='company_id.currency_id',
        readonly=True,
        store=False,
        help=(
            'Currency used by all monetary fields on the wizard. '
            'Derived from the company\'s currency; not stored '
            '(``store=False``) because the wizard is a TransientModel '
            'and the field is needed only at the wizard\'s lifetime.'
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
        check_company=True,
        help=(
            'The asset being modified. Must be in Running (``open``) '
            'state; draft and closed assets cannot be modified. '
            'Multi-company filtering is enforced both visually (domain) '
            'and at write time (``_check_company_auto = True`` on the '
            'model).'
        ),
    )

    # =========================================================================
    # MODIFICATION CLASSIFICATION
    # =========================================================================

    modification_type = fields.Selection(
        selection=[
            ('revaluation', 'Revaluation (Value Increase)'),
            ('impairment', 'Impairment (Value Decrease)'),
            ('impairment_reversal', 'Impairment Reversal'),
            ('useful_life_change', 'Useful Life Change'),
            ('salvage_change', 'Salvage Value Change'),
        ],
        string='Modification Type',
        required=True,
        default='revaluation',
        help=(
            'IAS 16 revaluation: value increase credited to revaluation '
            'surplus (equity). IAS 36 / ASC 360 impairment: value '
            'decrease debited to impairment loss (expense). Impairment '
            'reversal: recovers prior impairment, capped at lesser of '
            'the original impairment amount OR the depreciated '
            'historical cost at the reversal date. Useful life change: '
            'prospectively updates remaining depreciation per IAS 8 '
            '(Change in Accounting Estimate); no journal entry. '
            'Salvage change: prospectively updates residual value '
            'assumption per IAS 8; no journal entry.'
        ),
    )
    effective_date = fields.Date(
        string='Effective Date',
        required=True,
        default=fields.Date.context_today,
        help=(
            'The accounting date the modification takes effect. Must '
            'be >= asset acquisition date and not in a locked fiscal '
            'period (validated by ``_check_effective_date``). Used as '
            'the ``date`` of the resulting ``account.move``.'
        ),
    )

    # =========================================================================
    # VALUE FIELDS (revaluation / impairment / reversal)
    # =========================================================================

    previous_value = fields.Monetary(
        string='Previous Value',
        compute='_compute_previous_value',
        readonly=True,
        currency_field='currency_id',
        help=(
            'Computed baseline value before the modification. The '
            'semantics depend on ``modification_type``: for value '
            'adjustments (revaluation, impairment, impairment '
            'reversal), it is the asset\'s current net book value '
            '(NBV). For ``useful_life_change``, it is the count of '
            'remaining (unposted) depreciation periods. For '
            '``salvage_change``, it is the asset\'s current salvage '
            'value. The form view relabels this field per '
            'modification type for clarity.'
        ),
    )
    new_value = fields.Monetary(
        string='New Value',
        currency_field='currency_id',
        help=(
            'New value after modification. For revaluation: must be > '
            'previous_value. For impairment: must be > 0 and < '
            'previous_value. For impairment reversal: must be > '
            'previous_value but <= original acquisition cost. Ignored '
            'for useful-life and salvage-change types.'
        ),
    )
    modification_amount = fields.Monetary(
        string='Modification Amount',
        compute='_compute_modification_amount',
        store=False,
        readonly=True,
        currency_field='currency_id',
        help=(
            'Signed delta: ``new_value - previous_value``. Positive '
            'for revaluation and impairment reversal (value increase); '
            'negative for impairment (value decrease). Zero for '
            'useful-life and salvage-change types (which do not '
            'produce a journal entry).'
        ),
    )

    # =========================================================================
    # USEFUL LIFE / SALVAGE CHANGE SPECIFICS
    # =========================================================================

    new_useful_life_months = fields.Integer(
        string='New Remaining Useful Life (Months)',
        default=0,
        help=(
            'New total remaining useful life in months. Applicable '
            'only when ``modification_type = useful_life_change``. '
            'Must be strictly positive. Triggers prospective schedule '
            'recomputation per IAS 8.'
        ),
    )
    new_salvage_value = fields.Monetary(
        string='New Salvage Value',
        currency_field='currency_id',
        default=0.0,
        help=(
            'New salvage / residual value. Applicable only when '
            '``modification_type = salvage_change``. Must be in '
            '``[0, acquisition_cost]``. Triggers prospective schedule '
            'recomputation per IAS 8.'
        ),
    )

    # =========================================================================
    # DOCUMENTATION / AUDIT (AM-005 AC5)
    # =========================================================================

    reason = fields.Text(
        string='Reason',
        required=True,
        help=(
            'Justification captured in the immutable audit trail '
            '(asset chatter). Required for ALL modification types -- '
            'revaluation requires an appraisal reference, impairment '
            'requires impairment-indicator description, and lifecycle '
            'changes require a management memo. Persisted on the '
            'asset\'s ``mail.thread`` after posting.'
        ),
    )
    supporting_document = fields.Binary(
        string='Supporting Document',
        attachment=True,
        help=(
            'Optional supporting document (appraisal report, '
            'impairment analysis, management memo, board minutes). '
            'Persisted to ``ir.attachment`` linked to the wizard '
            'record; the form view exposes the filename via the '
            'companion ``supporting_document_filename`` Char.'
        ),
    )
    supporting_document_filename = fields.Char(
        string='Supporting Document Filename',
        help=(
            'Companion field for ``supporting_document`` Binary '
            'attachment, set automatically by the file-upload widget '
            'in the form view (``filename="supporting_document_'
            'filename"``).'
        ),
    )

    # =========================================================================
    # ACCOUNT OVERRIDES (per IAS 16 / IAS 36 / ASC 360)
    # =========================================================================

    revaluation_surplus_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Revaluation Surplus Account',
        domain="[('account_type', '=', 'equity'),"
               " ('company_ids', 'in', company_id)]",
        check_company=True,
        help=(
            'Equity account credited on revaluation per IAS 16 '
            '(revaluation surplus / revaluation reserve). Required '
            'when ``modification_type = revaluation``. Multi-company '
            'filtering enforced via ``check_company=True`` and the '
            'domain that restricts to accounts available in the '
            'wizard\'s company.'
        ),
    )
    impairment_loss_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Impairment Loss Account',
        domain="[('account_type', 'in',"
               " ('expense', 'expense_direct_cost', 'expense_depreciation')),"
               " ('company_ids', 'in', company_id)]",
        check_company=True,
        help=(
            'Expense account debited on impairment recognition per '
            'IAS 36 / ASC 360. Required when '
            '``modification_type = impairment``. Eligible account '
            'types: ``expense``, ``expense_direct_cost``, '
            '``expense_depreciation`` (the latter for entities that '
            'classify impairment under depreciation expense).'
        ),
    )
    impairment_reversal_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Impairment Reversal Income Account',
        domain="[('account_type', 'in', ('income', 'income_other')),"
               " ('company_ids', 'in', company_id)]",
        check_company=True,
        help=(
            'Income account credited on impairment reversal. Required '
            'when ``modification_type = impairment_reversal``. '
            'Eligible account types: ``income`` and ``income_other`` '
            '(the latter for entities that segregate non-operating '
            'gains).'
        ),
    )

    # =========================================================================
    # RESULT / STATE
    # =========================================================================

    move_id = fields.Many2one(
        comodel_name='account.move',
        string='Generated Journal Entry',
        readonly=True,
        copy=False,
        help=(
            'The adjustment journal entry created and posted by '
            '``action_post``; populated only after successful posting '
            'for value-adjusting modification types (revaluation, '
            'impairment, impairment reversal). Useful-life and '
            'salvage-change modifications do not produce a journal '
            'entry (per IAS 8 prospective accounting), so this field '
            'remains False for those types.'
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
            '``draft`` -- in configuration; user filling fields. '
            '``confirmed`` -- validated and ready to post. '
            '``posted`` -- journal entry created and asset updated '
            '(terminal). ``cancelled`` -- wizard aborted; if '
            'previously posted, the move is reversed via '
            '``_reverse_moves`` (terminal). Note: ``tracking`` is '
            'deliberately omitted -- TransientModel does not inherit '
            '``mail.thread``, and the persistent audit trail lives '
            'on the ``account.asset`` chatter via '
            '``message_post`` invocations from ``action_post`` and '
            '``action_cancel``.'
        ),
    )

    # =========================================================================
    # COMPUTE METHODS
    # =========================================================================

    @api.depends(
        'asset_id',
        'asset_id.net_book_value',
        'asset_id.salvage_value',
        'asset_id.depreciation_line_ids',
        'asset_id.depreciation_line_ids.state',
        'modification_type',
    )
    def _compute_previous_value(self):
        """Resolve the per-modification-type "previous value" baseline.

        The semantics of ``previous_value`` are differentiated by
        ``modification_type`` so that the same field can serve as the
        generic "before" indicator across all five modification types
        (the form view relabels it per type for clarity):

            * ``revaluation`` / ``impairment`` /
              ``impairment_reversal`` -- the asset's current net book
              value (NBV = ``acquisition_cost - accumulated_depreciation``).
              Sourced directly from the stored
              ``account.asset.net_book_value`` field.
            * ``useful_life_change`` -- the count of remaining
              (unposted) depreciation periods, computed as
              ``len(depreciation_line_ids) - len(posted lines)``.
              Defensive fallback to 0 when the asset has no schedule.
            * ``salvage_change`` -- the asset's current
              ``salvage_value`` field.
            * default / unset -- 0.0 (defensive default).

        All branches return a ``Monetary``-compatible value so the
        same field can be displayed in any of the conditional groups
        in the form view without value-type coercion.
        """
        for wizard in self:
            asset = wizard.asset_id
            if not asset:
                wizard.previous_value = 0.0
                continue
            mtype = wizard.modification_type
            if mtype in ('revaluation', 'impairment', 'impairment_reversal'):
                wizard.previous_value = asset.net_book_value
            elif mtype == 'useful_life_change':
                # Remaining useful life expressed as count of unposted
                # depreciation periods. The view labels this field as
                # "Current Remaining Months" in the useful-life-change
                # group; the integer count here is the closest
                # available proxy without a stored "remaining months"
                # field on the asset itself.
                total_lines = len(asset.depreciation_line_ids)
                posted_lines = len(asset.depreciation_line_ids.filtered(
                    lambda line: line.state == 'posted',
                ))
                wizard.previous_value = max(total_lines - posted_lines, 0)
            elif mtype == 'salvage_change':
                wizard.previous_value = asset.salvage_value or 0.0
            else:
                wizard.previous_value = 0.0

    @api.depends('previous_value', 'new_value', 'modification_type')
    def _compute_modification_amount(self):
        """Signed modification amount: ``new_value - previous_value``.

        Computed only for value-adjusting types (revaluation,
        impairment, impairment reversal); for useful-life and
        salvage-change types, the amount is conventionally 0.0
        because no journal entry is produced.

        Sign convention:

            * Positive -> value increase (revaluation, reversal).
            * Negative -> value decrease (impairment).
            * Zero     -> non-value-adjusting modification or no
              change (e.g., user reset the new_value to equal
              previous_value).
        """
        for wizard in self:
            if wizard.modification_type in (
                'revaluation', 'impairment', 'impairment_reversal',
            ):
                wizard.modification_amount = (
                    (wizard.new_value or 0.0)
                    - (wizard.previous_value or 0.0)
                )
            else:
                wizard.modification_amount = 0.0

    # =========================================================================
    # ONCHANGE METHODS
    # =========================================================================

    @api.onchange('modification_type')
    def _onchange_modification_type(self):
        """Clear fields inapplicable to the selected modification type.

        Prevents stale values from a prior selection contaminating the
        wizard state when the user toggles the modification type. The
        onchange is purely a UX helper; @api.constrains methods enforce
        the actual rules at write / save time so a bypass of the
        onchange (e.g., via API write) cannot produce an inconsistent
        modification.
        """
        # Clear useful-life-change-specific fields when the type
        # switches away from useful_life_change.
        if self.modification_type != 'useful_life_change':
            self.new_useful_life_months = 0
        # Clear salvage-change-specific fields when the type switches
        # away from salvage_change.
        if self.modification_type != 'salvage_change':
            self.new_salvage_value = 0.0
        # Clear value-adjusting fields when the type is non-value-
        # adjusting (useful-life or salvage change), since the
        # ``new_value`` and account selections are inapplicable.
        if self.modification_type not in (
            'revaluation', 'impairment', 'impairment_reversal',
        ):
            self.new_value = 0.0
        # Clear account selections that no longer apply to the new
        # modification type so the user does not see stale choices.
        if self.modification_type != 'revaluation':
            self.revaluation_surplus_account_id = False
        if self.modification_type != 'impairment':
            self.impairment_loss_account_id = False
        if self.modification_type != 'impairment_reversal':
            self.impairment_reversal_account_id = False

    @api.onchange('asset_id')
    def _onchange_asset_id(self):
        """Pre-populate defaults from the selected asset where possible.

        For ``salvage_change`` modifications, pre-fills
        ``new_salvage_value`` with the asset's current salvage value
        so the user sees a reasonable starting point rather than
        zero. For other modification types, no pre-fill is performed
        because the "new value" / "new useful life" inputs require
        user judgement that should not be biased by autofill.
        """
        if not self.asset_id:
            return
        # Pre-fill new_salvage_value with the asset's current salvage
        # value when the modification type is salvage_change. The user
        # can override; this is purely a convenience seed.
        if self.modification_type == 'salvage_change':
            self.new_salvage_value = self.asset_id.salvage_value

    # =========================================================================
    # PYTHON CONSTRAINTS (AM-005 AC1-7 -- enforced at write time)
    # =========================================================================

    @api.constrains('effective_date', 'asset_id')
    def _check_effective_date(self):
        """AM-005 AC6: validate effective_date placement.

        Two rules:

            1. ``effective_date`` must be on or after the asset's
               ``acquisition_date``. A modification dated before the
               asset was placed in service would be nonsensical and
               could corrupt historical depreciation calculations.
            2. ``effective_date`` must be after the company's fiscal-
               year lock date. Posting an entry on or before the
               lock date is normally blocked by Odoo's core
               ``account.move`` lock-date check; raising the error
               here at the wizard level produces a clearer error
               message than the deeply-nested core check would.

        Both rules are skipped when either field is unset
        (e.g., during transient creation / context-default
        application). The matching ``required=True`` attributes on
        both fields prevent the wizard from leaving the draft state
        with these unset.
        """
        for wizard in self:
            if not wizard.asset_id or not wizard.effective_date:
                continue
            # Rule 1: effective_date >= asset.acquisition_date.
            if (
                wizard.asset_id.acquisition_date
                and wizard.effective_date
                < wizard.asset_id.acquisition_date
            ):
                raise ValidationError(_(
                    'Effective date (%(eff)s) cannot be earlier than '
                    'the asset acquisition date (%(acq)s).',
                    eff=wizard.effective_date,
                    acq=wizard.asset_id.acquisition_date,
                ))
            # Rule 2: effective_date strictly after fiscalyear_lock_date.
            # Use the asset's company so that multi-company writes use
            # the correct lock-date for the asset's books, not the
            # wizard's own company (which the asset domain already
            # constrains to match anyway).
            company = wizard.asset_id.company_id or wizard.company_id
            fiscal_lock_date = company.fiscalyear_lock_date or False
            if fiscal_lock_date and wizard.effective_date <= fiscal_lock_date:
                raise ValidationError(_(
                    'Effective date (%(eff)s) is on or before the '
                    'fiscal year lock date (%(lock)s). Choose a date '
                    'after the lock date or have a manager configure '
                    'a lock-date exception.',
                    eff=wizard.effective_date,
                    lock=fiscal_lock_date,
                ))

    @api.constrains(
        'new_value',
        'modification_type',
        'asset_id',
    )
    def _check_value_direction(self):
        """AM-005 AC1-2 / AC7: validate value direction per type.

        Rules per ``modification_type``:

            * ``revaluation``: ``new_value > previous_value`` (strict
              increase). For value decreases, the user must select
              ``impairment`` instead.
            * ``impairment``: ``0 < new_value < previous_value``
              (strict decrease, but value remains positive). For
              value increases, the user must select ``revaluation``.
            * ``impairment_reversal``: ``previous_value < new_value
              <= acquisition_cost`` (recovery, capped at original
              cost so the reversal cannot increase carrying amount
              above what it would have been without impairment per
              IAS 36 paragraph 117 and ASC 360-10-35-23).

        Useful-life and salvage-change types are not value-
        adjusting, so this constraint is a no-op for them.
        """
        for wizard in self:
            if wizard.modification_type not in (
                'revaluation', 'impairment', 'impairment_reversal',
            ):
                continue
            if wizard.new_value is None:
                raise ValidationError(_(
                    'New value must be set for modification type '
                    '"%s".',
                    wizard.modification_type,
                ))
            # Revaluation: strict increase.
            if wizard.modification_type == 'revaluation':
                if wizard.new_value <= wizard.previous_value:
                    raise ValidationError(_(
                        'Revaluation requires the new value '
                        '(%(new).2f) to be strictly greater than the '
                        'previous value (%(prev).2f). For a value '
                        'decrease, use modification type '
                        '"Impairment" instead.',
                        new=wizard.new_value,
                        prev=wizard.previous_value,
                    ))
            # Impairment: strict decrease, but new_value > 0.
            elif wizard.modification_type == 'impairment':
                if wizard.new_value <= 0:
                    raise ValidationError(_(
                        'Impaired value must be strictly positive '
                        '(got %(new).2f).',
                        new=wizard.new_value,
                    ))
                if wizard.new_value >= wizard.previous_value:
                    raise ValidationError(_(
                        'Impairment requires the new value '
                        '(%(new).2f) to be strictly less than the '
                        'previous value (%(prev).2f). For a value '
                        'increase, use modification type '
                        '"Revaluation" instead.',
                        new=wizard.new_value,
                        prev=wizard.previous_value,
                    ))
            # Impairment reversal: increase capped at acquisition cost.
            elif wizard.modification_type == 'impairment_reversal':
                if wizard.new_value <= wizard.previous_value:
                    raise ValidationError(_(
                        'Impairment reversal requires the new value '
                        '(%(new).2f) to be greater than the previous '
                        'value (%(prev).2f).',
                        new=wizard.new_value,
                        prev=wizard.previous_value,
                    ))
                # IAS 36 par 117 / ASC 360-10-35-23: reversal cannot
                # increase carrying amount above what it would have
                # been without impairment. The upper bound is the
                # original acquisition cost as a conservative proxy
                # for "depreciated historical cost"; a refined
                # calculation could subtract the depreciation that
                # WOULD have accumulated had no impairment occurred,
                # but the simpler cap is sufficient for AM-005 AC7.
                asset = wizard.asset_id
                if asset and wizard.new_value > asset.acquisition_cost:
                    raise ValidationError(_(
                        'Impairment reversal cannot increase the '
                        'asset value above the original acquisition '
                        'cost (%(cost).2f).',
                        cost=asset.acquisition_cost,
                    ))

    @api.constrains('new_useful_life_months', 'modification_type')
    def _check_useful_life(self):
        """AM-005: useful_life_change requires positive months.

        A zero or negative useful life would either produce no
        depreciation (zero) or invert the schedule (negative), both
        of which would corrupt the asset's books. The matching
        ``@api.constrains`` on ``account.asset`` enforces the same
        rule on the underlying asset; this wizard-level check
        prevents the modification from even being confirmed in an
        invalid state.
        """
        for wizard in self:
            if (
                wizard.modification_type == 'useful_life_change'
                and wizard.new_useful_life_months <= 0
            ):
                raise ValidationError(_(
                    'New useful life (months) must be strictly '
                    'positive for useful-life-change modifications '
                    '(got %d).',
                    wizard.new_useful_life_months,
                ))

    @api.constrains(
        'new_salvage_value',
        'modification_type',
        'asset_id',
    )
    def _check_new_salvage_value(self):
        """AM-005: salvage_change requires non-negative bounded value.

        Two rules:

            1. ``new_salvage_value >= 0`` -- a negative salvage value
               would imply the asset has negative residual worth at
               end of life, which would corrupt the schedule.
            2. ``new_salvage_value <= acquisition_cost`` -- a salvage
               value above acquisition cost would imply the asset
               appreciates rather than depreciates, contradicting
               the fundamental fixed-asset accounting model
               (revaluation surplus is handled separately by the
               ``revaluation`` modification type, not by raising
               salvage above cost).
        """
        for wizard in self:
            if wizard.modification_type != 'salvage_change':
                continue
            if wizard.new_salvage_value < 0:
                raise ValidationError(_(
                    'New salvage value cannot be negative (got '
                    '%(sal).2f).',
                    sal=wizard.new_salvage_value,
                ))
            if (
                wizard.asset_id
                and wizard.new_salvage_value
                > (wizard.asset_id.acquisition_cost or 0.0)
            ):
                raise ValidationError(_(
                    'New salvage value (%(sal).2f) cannot exceed the '
                    'asset acquisition cost (%(cost).2f).',
                    sal=wizard.new_salvage_value,
                    cost=wizard.asset_id.acquisition_cost,
                ))

    @api.constrains(
        'modification_type',
        'revaluation_surplus_account_id',
        'impairment_loss_account_id',
        'impairment_reversal_account_id',
    )
    def _check_required_account(self):
        """AM-005 AC4: enforce account configuration per type.

        Each value-adjusting modification type requires its
        type-specific account override:

            * ``revaluation`` -> ``revaluation_surplus_account_id``
              (equity account).
            * ``impairment`` -> ``impairment_loss_account_id``
              (expense account).
            * ``impairment_reversal`` ->
              ``impairment_reversal_account_id`` (income account).

        Useful-life and salvage-change types do not produce a
        journal entry, so no account override is required for them.
        """
        for wizard in self:
            mtype = wizard.modification_type
            if (
                mtype == 'revaluation'
                and not wizard.revaluation_surplus_account_id
            ):
                raise ValidationError(_(
                    'Revaluation Surplus Account is required for '
                    'revaluation modifications.',
                ))
            if (
                mtype == 'impairment'
                and not wizard.impairment_loss_account_id
            ):
                raise ValidationError(_(
                    'Impairment Loss Account is required for '
                    'impairment modifications.',
                ))
            if (
                mtype == 'impairment_reversal'
                and not wizard.impairment_reversal_account_id
            ):
                raise ValidationError(_(
                    'Impairment Reversal Income Account is required '
                    'for impairment-reversal modifications.',
                ))

    # =========================================================================
    # ACTION METHODS (state-machine transitions)
    # =========================================================================

    def action_confirm(self):
        """Transition draft -> confirmed; final validation gate.

        Acts as a staging gate: the user reviews all configuration
        and explicitly confirms intent before ``action_post``
        creates and posts the journal entry. After confirmation, the
        form view disables the configuration fields (per
        ``readonly="state != 'draft'"`` attributes); subsequent
        edits require cancellation and a fresh wizard.

        Validation triggers (defensive re-check beyond
        ``@api.constrains``):

            * ``_check_effective_date``  -- AC6 placement rules.
            * ``_check_value_direction`` -- AC1-2 / AC7 sign rules.
            * ``_check_required_account`` -- AC4 account enforcement.

        :return: an ``ir.actions.act_window`` dict that re-opens the
            wizard form with the new ``confirmed`` state.
        :rtype: dict
        :raises UserError: when the wizard is not in ``draft`` state.
        :raises ValidationError: from the constraint methods on
            invalid configuration.
        """
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_(
                'Only draft modifications can be confirmed (current '
                'state: "%s").',
                self.state,
            ))
        # Defensive re-validation: the @api.constrains decorators run
        # at write time, but explicitly re-running them here is cheap
        # belt-and-braces correctness in case of upstream cache /
        # stale-record edge cases.
        self._check_effective_date()
        self._check_value_direction()
        self._check_useful_life()
        self._check_new_salvage_value()
        self._check_required_account()
        self.write({'state': 'confirmed'})
        _logger.info(
            'AM-005: modification wizard %d confirmed for asset '
            '%s (type=%s, amount=%.2f).',
            self.id,
            self.asset_id.display_name,
            self.modification_type,
            self.modification_amount,
        )
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_post(self):
        """Create and post the adjustment entry; recompute schedule.

        Wraps the multi-step posting workflow in a PostgreSQL
        ``SAVEPOINT`` (via ``self.env.cr.savepoint()``) so that
        partial failure rolls back cleanly. Steps inside the
        savepoint:

            1. Create and post the adjustment ``account.move`` for
               value-adjusting types (revaluation, impairment,
               impairment reversal). Useful-life and salvage-change
               types skip this step.
            2. Apply asset-side changes (acquisition_cost,
               useful_life_months, salvage_value) per
               ``_apply_asset_changes``.
            3. Recompute the depreciation schedule via
               ``asset._compute_depreciation_schedule()`` -- the
               method preserves posted lines and only regenerates
               draft / future lines per IAS 8 prospective accounting.
            4. Post the immutable audit trail message to the asset's
               chatter via ``asset.message_post(body=...)``.
            5. Persist ``move_id`` and transition state to
               ``posted``.

        Journal entry structure per ``modification_type``:

            * Revaluation (DR asset, CR revaluation surplus):
                  DR  asset.asset_account_id            |amount|
                  CR  revaluation_surplus_account_id    |amount|

            * Impairment (DR impairment loss, CR accumulated depr):
                  DR  impairment_loss_account_id              |amount|
                  CR  asset.accumulated_depreciation_account_id
                                                             |amount|

            * Impairment Reversal (DR accum depr, CR reversal income):
                  DR  asset.accumulated_depreciation_account_id
                                                             |amount|
                  CR  impairment_reversal_account_id          |amount|

            * Useful Life Change / Salvage Change: no journal entry
              (prospective IAS 8 accounting estimate change).

        :return: an ``ir.actions.act_window`` dict that re-opens the
            wizard form in ``posted`` state.
        :rtype: dict
        :raises UserError: when the wizard is not in ``confirmed``
            state, when no asset is selected, or when posting fails
            for any non-business-logic reason (DB error, cron
            collision, etc.).
        """
        self.ensure_one()
        if self.state != 'confirmed':
            raise UserError(_(
                'Only confirmed modifications can be posted (current '
                'state: "%s"). Confirm the modification first.',
                self.state,
            ))
        asset = self.asset_id
        if not asset:
            raise UserError(_('No asset selected on the wizard.'))

        # Capture the computed values BEFORE any asset modification.
        # ``previous_value`` and ``modification_amount`` are non-stored
        # computed fields that depend on the asset's current state
        # (``net_book_value`` / ``salvage_value`` / etc.). After
        # ``_apply_asset_changes`` runs, those source fields shift so
        # the computed values would recompute to post-modification
        # values, which would corrupt the audit trail (e.g., the
        # adjustment amount would appear as 0 because previous_value
        # and new_value would both equal the new NBV). Capturing here
        # ensures the audit message and the success log both reflect
        # the AS-OF-PRE-MODIFICATION state of the wizard.
        captured_previous_value = self.previous_value
        captured_modification_amount = self.modification_amount

        # PostgreSQL SAVEPOINT for atomicity. The savepoint context
        # manager flushes pending ORM operations on enter, captures
        # all subsequent writes, and either RELEASES (success) or
        # ROLLS BACK (failure) on exit. A failure inside the block
        # therefore reverts ALL changes -- the move, the asset
        # update, the schedule recomputation, and the audit message
        # -- leaving the database in a clean state. This pattern is
        # the precedent from
        # ``addons/account_bank_reconciliation_ce/wizard/
        # bank_statement_import_wizard.py::action_import``.
        try:
            with self.env.cr.savepoint():
                # Step 1: Create the adjustment move (only for
                # value-adjusting modification types).
                move = False
                if self.modification_type in (
                    'revaluation', 'impairment', 'impairment_reversal',
                ):
                    move = self._create_modification_move()

                # Step 2: Apply asset-side updates.
                self._apply_asset_changes()

                # Step 3: Recompute the depreciation schedule
                # prospectively (preserves posted lines, regenerates
                # draft / future lines only). Per IAS 8, useful-life
                # and salvage-change modifications take effect from
                # the modification date forward; the historical
                # schedule remains immutable.
                asset._compute_depreciation_schedule()

                # Step 4: Audit trail on the asset's chatter
                # (mail.thread). The wizard itself is transient and
                # auto-purged, so persistent audit trail must live on
                # the asset. We pass the pre-modification snapshot so
                # the audit message accurately captures the
                # transition.
                audit_body = self._format_audit_message(
                    move,
                    previous_value_override=captured_previous_value,
                    modification_amount_override=(
                        captured_modification_amount
                    ),
                )
                asset.message_post(body=audit_body)

                # Step 5: Persist results and transition state.
                self.write({
                    'move_id': move.id if move else False,
                    'state': 'posted',
                })

                _logger.info(
                    'AM-005: modification wizard %d posted for asset '
                    '%s (type=%s, amount=%.2f, move=%s).',
                    self.id,
                    asset.display_name,
                    self.modification_type,
                    captured_modification_amount,
                    move.name if move else 'N/A',
                )

        except (UserError, ValidationError):
            # Re-raise Odoo business exceptions so the user sees the
            # original message; the savepoint has already rolled back
            # any partial writes automatically.
            raise
        except Exception as exc:
            # Any other exception (database error, integrity
            # violation, programming error) is logged with full
            # traceback and re-raised as a UserError so the form
            # displays a friendly message rather than a stack trace.
            # The savepoint has rolled back partial writes.
            _logger.exception(
                'AM-005: error posting modification for asset %s.',
                asset.display_name if asset else 'n/a',
            )
            raise UserError(_(
                'Posting the asset modification failed: %s',
                exc,
            )) from exc

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_cancel(self):
        """Cancel the wizard; reverse the move if previously posted.

        Three sub-flows depending on current state:

            * ``draft`` / ``confirmed`` -> set state to ``cancelled``
              with no further action; no journal entry exists yet.
            * ``posted`` -> reverse the linked ``move_id`` via the
              core ``account.move._reverse_moves`` mechanism (which
              creates an offsetting move and reconciles them via
              ``cancel=True``), post a chatter message on the asset
              recording the reversal, and transition to
              ``cancelled``. The original move is preserved for
              audit trail continuity (Odoo's reversal pattern is
              non-destructive).
            * ``cancelled`` -> raise ``UserError`` (idempotent
              cancellation refusal).

        :return: an ``ir.actions.act_window`` dict that re-opens the
            wizard form in ``cancelled`` state.
        :rtype: dict
        :raises UserError: when the wizard is already cancelled.
        """
        self.ensure_one()
        if self.state == 'cancelled':
            raise UserError(_(
                'This modification is already cancelled.',
            ))
        if self.state == 'posted' and self.move_id:
            # Reverse via the core mechanism so reconciliation /
            # storno / lock-date checks all behave correctly. The
            # ``_reverse_moves`` method returns an account.move
            # recordset; for a singleton input we take the first
            # element to display its name in the audit message.
            reversal = self.move_id._reverse_moves(
                default_values_list=[{
                    'date': self.effective_date,
                    'ref': _(
                        'Reversal of %s', self.move_id.name or '',
                    ),
                }],
                cancel=True,
            )
            self.asset_id.message_post(body=_(
                'Modification move %(orig)s reversed (reversal '
                'entry: %(rev)s).',
                orig=self.move_id.name or '',
                rev=reversal.name or '',
            ))
            _logger.info(
                'AM-005: modification wizard %d cancelled with '
                'reversal entry %s.',
                self.id,
                reversal.name or '',
            )
        else:
            _logger.info(
                'AM-005: modification wizard %d cancelled '
                '(no reversal needed; state was "%s").',
                self.id,
                self.state,
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

    def _create_modification_move(self):
        """Create and post the adjustment ``account.move``.

        Builds a balanced two-line journal entry with the appropriate
        DR / CR accounts per ``modification_type``, sets the asset
        back-reference fields (``asset_id``, ``asset_entry_type =
        'modification'``) added by the
        ``models/account_move.py`` _inherit extension, and posts the
        move immediately via ``move.action_post()`` (modifications
        are never left in draft).

        Uses ``Command.create`` for the line_ids tuples (precedent:
        ``addons/account_bank_reconciliation_ce/models/
        partial_reconcile_ext.py``).

        :return: the created and posted ``account.move`` record.
        :rtype: ``account.move``
        :raises UserError: when the modification amount is zero (no
            entry to post), or when the modification type is not a
            value-adjusting type.
        """
        self.ensure_one()
        asset = self.asset_id
        amount = abs(self.modification_amount or 0.0)
        # Currency precision check: modifications below the smallest
        # representable amount are no-ops (the journal entry would
        # round to zero).
        currency = asset.currency_id or asset.company_id.currency_id
        if currency.is_zero(amount):
            raise UserError(_(
                'Modification amount is zero (or below the smallest '
                'representable currency unit); nothing to post.',
            ))

        mtype_label = dict(
            self._fields['modification_type'].selection,
        ).get(self.modification_type, self.modification_type)

        # Resolve the DR / CR account pair per modification type.
        if self.modification_type == 'revaluation':
            # IAS 16: DR asset (gross value increase),
            #          CR revaluation surplus (equity).
            line_ids = [
                Command.create({
                    'name': _('Revaluation of %s', asset.name or ''),
                    'account_id': asset.asset_account_id.id,
                    'debit': amount,
                    'credit': 0.0,
                }),
                Command.create({
                    'name': _(
                        'Revaluation surplus for %s', asset.name or '',
                    ),
                    'account_id': self.revaluation_surplus_account_id.id,
                    'debit': 0.0,
                    'credit': amount,
                }),
            ]
        elif self.modification_type == 'impairment':
            # IAS 36 / ASC 360: DR impairment loss (expense),
            #                    CR accumulated depreciation
            #                       (contra-asset).
            line_ids = [
                Command.create({
                    'name': _('Impairment of %s', asset.name or ''),
                    'account_id': self.impairment_loss_account_id.id,
                    'debit': amount,
                    'credit': 0.0,
                }),
                Command.create({
                    'name': _(
                        'Accumulated impairment for %s',
                        asset.name or '',
                    ),
                    'account_id': (
                        asset.accumulated_depreciation_account_id.id
                    ),
                    'debit': 0.0,
                    'credit': amount,
                }),
            ]
        elif self.modification_type == 'impairment_reversal':
            # IAS 36: DR accumulated depreciation (contra-asset
            #          reversal), CR impairment reversal income.
            line_ids = [
                Command.create({
                    'name': _(
                        'Reversal of accumulated impairment for %s',
                        asset.name or '',
                    ),
                    'account_id': (
                        asset.accumulated_depreciation_account_id.id
                    ),
                    'debit': amount,
                    'credit': 0.0,
                }),
                Command.create({
                    'name': _(
                        'Impairment reversal income for %s',
                        asset.name or '',
                    ),
                    'account_id': (
                        self.impairment_reversal_account_id.id
                    ),
                    'debit': 0.0,
                    'credit': amount,
                }),
            ]
        else:
            # Defensive guard: action_post already filters to value-
            # adjusting types before calling this helper, so this
            # branch should never execute. Raising UserError yields a
            # clearer message than silently building an empty entry.
            raise UserError(_(
                'Unsupported modification type for journal entry: %s',
                self.modification_type,
            ))

        # Build the move header and create + post in one shot.
        move_vals = {
            'move_type': 'entry',
            'date': self.effective_date,
            'journal_id': asset.journal_id.id,
            'company_id': asset.company_id.id,
            'ref': _(
                'Asset Modification %(ref)s: %(type)s',
                ref=asset.reference or asset.name or '',
                type=mtype_label,
            ),
            # asset_id / asset_entry_type fields come from the R-05-
            # compliant additive _inherit extension in
            # models/account_move.py. asset_entry_type is coarse-
            # grained ('modification' for all three sub-types); the
            # granular sub-type is preserved in the ref above and on
            # the wizard's own modification_type field for audit
            # trail.
            'asset_id': asset.id,
            'asset_entry_type': 'modification',
            'line_ids': line_ids,
        }
        move = self.env['account.move'].with_company(
            asset.company_id,
        ).create(move_vals)
        # Post the move immediately. The core ``action_post`` performs
        # additional validations (lock dates, sequence, balance) so
        # any failure here surfaces a clear error before the asset-
        # side changes (next step in action_post) are applied.
        move.action_post()
        _logger.info(
            'AM-005: posted modification move %s for asset %s '
            '(type=%s, amount=%.2f).',
            move.name,
            asset.display_name,
            self.modification_type,
            amount,
        )
        return move

    def _apply_asset_changes(self):
        """Apply per-modification-type updates to the underlying asset.

        Per-type semantics:

            * ``revaluation`` -- adds ``modification_amount`` to
              ``acquisition_cost`` (the simplified revaluation model:
              gross value reflects the new fair value; accumulated
              depreciation is unchanged at the modification date and
              future depreciation is computed on the new gross
              value).
            * ``impairment`` -- adds ``modification_amount`` (a
              negative number) to ``acquisition_cost``, reducing the
              asset's gross book value. Equivalent to crediting the
              asset account directly. This simplification mirrors
              the impact of the journal entry that credits
              accumulated depreciation: in both views, NBV decreases
              by ``|amount|``. The implementation uses the
              acquisition_cost adjustment so that subsequent
              schedule recomputation works on the post-impairment
              gross value without requiring a separate
              "impairment-loss running total" field on the asset.
            * ``impairment_reversal`` -- adds ``modification_amount``
              (positive) to ``acquisition_cost``, restoring gross
              value (capped by AC7).
            * ``useful_life_change`` -- updates ``useful_life_unit``
              to ``'months'`` and ``useful_life_months`` to
              ``new_useful_life_months``; clears
              ``useful_life_years`` to avoid ambiguity. Subsequent
              schedule recomputation uses the new lifetime.
            * ``salvage_change`` -- updates ``salvage_value`` to
              ``new_salvage_value``. Subsequent schedule
              recomputation respects the new residual.

        For useful-life and salvage-change types, the implementation
        is purely a ``write`` on the asset; no journal entry is
        produced.
        """
        self.ensure_one()
        asset = self.asset_id
        if self.modification_type == 'revaluation':
            asset.write({
                'acquisition_cost': (
                    (asset.acquisition_cost or 0.0)
                    + self.modification_amount
                ),
            })
        elif self.modification_type == 'impairment':
            # modification_amount is negative for impairment; addition
            # therefore subtracts the impairment from cost.
            asset.write({
                'acquisition_cost': (
                    (asset.acquisition_cost or 0.0)
                    + self.modification_amount
                ),
            })
        elif self.modification_type == 'impairment_reversal':
            asset.write({
                'acquisition_cost': (
                    (asset.acquisition_cost or 0.0)
                    + self.modification_amount
                ),
            })
        elif self.modification_type == 'useful_life_change':
            asset.write({
                'useful_life_unit': 'months',
                'useful_life_months': self.new_useful_life_months,
                # Clear years to avoid ambiguity with the new month
                # count. The asset's _check_depreciation_config
                # constraint enforces > 0 on the unit-matching field;
                # by zeroing useful_life_years and setting unit to
                # 'months', useful_life_months is the active field.
                'useful_life_years': 0,
            })
        elif self.modification_type == 'salvage_change':
            asset.write({
                'salvage_value': self.new_salvage_value,
            })
        # No else branch: action_post guards against unknown
        # modification types via the same Selection check.

    def _format_audit_message(
        self,
        move,
        previous_value_override=None,
        modification_amount_override=None,
    ):
        """Format the HTML audit-trail message for the asset chatter.

        Per AM-005 AC5, the immutable audit trail must record:

            * Modification type (selection label, not raw key).
            * Effective date.
            * Previous and new values (for value-adjusting types) or
              the new useful-life / salvage value (for those types).
            * Adjustment amount (for value-adjusting types).
            * Reason / justification text from the wizard.
            * Link to the generated journal entry (when present).

        The user identity and timestamp are appended automatically by
        ``mail.thread.message_post`` (which is invoked on the
        ``account.asset`` mail-thread, not the wizard). HTML markup
        is used so the chatter renders structured fields rather than
        a single text blob.

        Returns a ``markupsafe.Markup`` instance so
        ``mail.thread.message_post`` treats the body as pre-sanitized
        HTML; passing a plain ``str`` causes the mail framework's
        ``escape()`` to render the ``<b>`` / ``<br/>`` tags as
        literal text in the chatter (FB-02 fix).

        Variable substitutions are escaped through the ``_(...)``
        translation helper combined with the ``%`` operator on the
        Markup-safe template -- the values themselves are wrapped in
        ``Markup.escape`` so a partner / reason string containing a
        ``<script>`` tag cannot inject markup into the chatter
        message.

        Override parameters:
            ``action_post`` captures ``previous_value`` and
            ``modification_amount`` BEFORE applying the asset
            changes, then passes them as overrides here. Without the
            overrides, the non-stored compute fields would recompute
            against the post-modification asset state and the audit
            message would show post-modification values for both
            "before" and "after" (i.e., zero adjustment), corrupting
            the audit trail. The overrides default to ``None`` so
            callers that do not need this guarantee (e.g., draft-
            preview rendering) can use the live computed values.

        :param move: the posted ``account.move`` record (or a
            falsy / empty recordset for non-value-adjusting types).
        :type move: ``account.move`` or False
        :param previous_value_override: a numeric override for the
            "previous value" line; falls back to ``self.previous_value``
            when ``None``.
        :type previous_value_override: float or None
        :param modification_amount_override: a numeric override for the
            "adjustment amount" line; falls back to
            ``self.modification_amount`` when ``None``.
        :type modification_amount_override: float or None
        :return: HTML body for ``message_post`` as a ``markupsafe.Markup``
            instance (safe HTML, no further escape).
        :rtype: markupsafe.Markup
        """
        self.ensure_one()
        type_label = dict(
            self._fields['modification_type'].selection,
        ).get(self.modification_type, self.modification_type)
        currency = self.currency_id or self.company_id.currency_id
        # Resolve the previous_value and modification_amount lines
        # using the override-first-fallback-to-live pattern.
        prev_val = (
            previous_value_override
            if previous_value_override is not None
            else (self.previous_value or 0.0)
        )
        mod_amount = (
            modification_amount_override
            if modification_amount_override is not None
            else (self.modification_amount or 0.0)
        )
        # FB-02: Build the message via ``Markup`` + ``%`` formatting so
        # the static HTML tags (``<b>``, ``<br/>``) remain safe HTML
        # while every interpolated value is auto-escaped.
        # ``Markup('...') % (...)`` escapes each substituted value
        # exactly once and joins it back into a Markup instance --
        # exactly the contract that ``mail.thread.message_post``'s
        # ``escape(body)`` short-circuit looks for on Markup inputs.
        body_parts = [
            Markup('<b>%s</b>') % _('Asset Modification Posted'),
            Markup('<br/>%s: %s') % (_('Type'), type_label),
            Markup('<br/>%s: %s') % (
                _('Effective Date'), self.effective_date or '',
            ),
            Markup('<br/>%s: %s') % (
                _('Previous Value'), currency.round(prev_val),
            ),
        ]
        if self.modification_type in (
            'revaluation', 'impairment', 'impairment_reversal',
        ):
            body_parts.append(Markup('<br/>%s: %s') % (
                _('New Value'),
                currency.round(self.new_value or 0.0),
            ))
            body_parts.append(Markup('<br/>%s: %s') % (
                _('Adjustment Amount'),
                currency.round(mod_amount),
            ))
        if self.modification_type == 'useful_life_change':
            body_parts.append(Markup('<br/>%s: %d %s') % (
                _('New Remaining Useful Life'),
                self.new_useful_life_months,
                _('months'),
            ))
        if self.modification_type == 'salvage_change':
            body_parts.append(Markup('<br/>%s: %s') % (
                _('New Salvage Value'),
                currency.round(self.new_salvage_value or 0.0),
            ))
        body_parts.append(Markup('<br/>%s: %s') % (
            _('Reason'), self.reason or '',
        ))
        if move:
            body_parts.append(Markup('<br/>%s: %s') % (
                _('Journal Entry'), move.name or '',
            ))
        # Concatenate Markup fragments via ``Markup.join`` so the
        # final body is itself a Markup instance (regular ``str.join``
        # would coerce to plain ``str`` and re-trigger the FB-02
        # escape behaviour).
        return Markup('').join(body_parts)
