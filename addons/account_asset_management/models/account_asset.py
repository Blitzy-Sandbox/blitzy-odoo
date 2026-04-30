# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Fixed Asset Header Model (FEATURE-004, AM-001 / AM-002 / AM-004).

Implements the central ``account.asset`` entity for Odoo 19.0 Community
Edition. Responsibilities:

    * Asset registration and identification (AM-001).
    * Depreciation configuration with three methods (AM-002):
      straight-line, declining balance, and units-of-production.
    * State machine: ``draft`` -> ``open`` -> ``close``.
    * Acquisition journal entry creation on confirmation (AM-001 AC2).
    * Depreciation schedule generation per-method (AM-002 AC1-4).
    * AM-004 cron entry point for automatic depreciation posting with
      idempotency, batching, and fault tolerance.
    * Integration points for AM-005 modification and AM-006 disposal
      wizards (returns ``ir.actions.act_window`` records).

AAP Rule Compliance
-------------------
* R-01 (Module independence) -- This file imports ONLY from
  ``odoo`` and ``odoo.exceptions`` plus the Python standard library
  (``logging``, ``datetime``) and ``dateutil``. NO imports of
  ``account_budget_management``, ``account_deferred_revenue``, or
  ``account_payment_followup``. Cross-model resolution within this
  module is performed via the Odoo ORM registry (string model names),
  not via Python-level imports.
* R-03 (``_inherit`` / ``_name`` correctness) -- Declares ``_name =
  'account.asset'`` for a NET-NEW model. The ``_inherit`` list contains
  ONLY the mixin models ``mail.thread`` and ``mail.activity.mixin``;
  no core Odoo concrete model is extended in this file (extensions of
  ``account.move`` and ``account.move.line`` live in their own files
  in the same ``models/`` package, per AAP convention).
* R-05 (No core field redefinition) -- NOT APPLICABLE to this file:
  ``account.asset`` is a brand-new model. The only fields added to
  ``account.move`` / ``account.move.line`` are defined in their
  respective ``_inherit`` extension files and are strictly additive
  (computed or relational only).
* R-06 (Scheduled jobs via XML ``ir.cron``) -- The AM-004 cron entry
  point ``_cron_post_depreciation_entries`` is invoked by an XML
  ``<record model="ir.cron">`` declaration in
  ``data/depreciation_cron.xml``. NO Python-level scheduling primitives
  (e.g., ``threading.Timer``, ``APScheduler``) appear in this file.
* R-07 (No unjustified ``sudo``) -- This file contains NO ``.sudo()``
  calls; the cron's per-line/per-asset try/except blocks use the
  scheduler's own user (typically the Odoo administrator) and rely on
  the existing ``ir.model.access.csv`` rules for authorization.

Performance Notes
-----------------
* ``company_id`` carries ``index=True`` for efficient multi-company
  ``ir.rule`` filtering.
* ``accumulated_depreciation`` and ``net_book_value`` are stored
  computed fields with ``store=True`` for O(1) lookup in form / list /
  kanban / graph views.
* ``_cron_post_depreciation_entries`` performs a SINGLE search with an
  optimized domain to avoid N+1 queries; per-line ``filtered`` runs in
  Python on the already-loaded recordset.

Attribute / Method Map (per AAP exports schema)
-----------------------------------------------
Fields (~30): name, reference, active, company_id, currency_id,
    acquisition_date, acquisition_cost, salvage_value, vendor_id,
    source_invoice_id, category_id, asset_account_id,
    expense_account_id, accumulated_depreciation_account_id,
    journal_id, depreciation_method, useful_life_unit,
    useful_life_years, useful_life_months, declining_factor,
    switch_to_straight_line, units_production_total,
    units_production_to_date, start_date_option,
    depreciation_start_date, state, acquisition_move_id,
    depreciation_line_ids, accumulated_depreciation, net_book_value,
    depreciation_line_count.
Defaults / Computes / Onchanges: _default_reference,
    _compute_depreciation_totals, _compute_depreciation_line_count,
    _onchange_category_id.
Constraints: _check_acquisition_cost_positive, _check_salvage_value,
    _check_asset_account_type, _check_expense_account_type,
    _check_accumulated_account_type, _check_depreciation_config,
    _check_declining_factor.
State-machine actions: action_confirm, action_set_draft, action_close,
    action_dispose, action_modify, action_view_depreciation_lines.
Helpers: _validate_accounts, _validate_depreciation_config,
    _resolve_depreciation_start_date, _create_acquisition_move,
    _compute_depreciation_schedule, _schedule_straight_line,
    _schedule_declining_balance, _schedule_units_of_production.
Cron: _cron_post_depreciation_entries.
SQL constraints: _sql_constraints (unique reference per company).
"""

import logging
from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class AccountAsset(models.Model):
    """Fixed Asset -- central entity for FEATURE-004 Asset Management.

    Each ``account.asset`` record represents a single fixed asset
    (building, vehicle, machinery, equipment, etc.) tracked through
    its lifecycle from acquisition through depreciation, modification,
    and ultimately disposal.

    The model uses ``mail.thread`` and ``mail.activity.mixin`` mixins
    for chatter and follow-up activity tracking (AM-001 Scenario 6
    audit trail).

    State machine
    -------------

    * ``draft``  -- initial state; the asset is being configured. No
      journal entry has been posted, the depreciation schedule has not
      been generated.
    * ``open``   -- confirmed and active. The acquisition journal
      entry has been posted; the depreciation schedule has been
      generated; the AM-004 cron will post each due line.
    * ``close``  -- the asset has been disposed (sale, scrap, or
      write-off via AM-006) or fully depreciated (cron auto-closes).
      No further automatic depreciation occurs.

    Transitions are explicit via ``write({'state': '...'})`` calls in
    ``action_confirm``, ``action_set_draft``, and ``action_close`` so
    that the chatter ``tracking=True`` history captures every change.
    """

    _name = 'account.asset'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Fixed Asset'
    _order = 'acquisition_date desc, reference, name'
    _check_company_auto = True

    # =========================================================================
    # IDENTIFICATION & METADATA
    # =========================================================================

    name = fields.Char(
        string='Asset Name',
        required=True,
        tracking=True,
        translate=True,
        help=(
            'Descriptive asset name displayed in lists, reports, and the '
            'chatter, e.g., "Office Building HQ" or "Production Line #3". '
            'Translatable for multi-locale deployments.'
        ),
    )
    reference = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        tracking=True,
        default=lambda self: self._default_reference(),
        help=(
            'Unique asset reference number, auto-generated from the '
            '``ir.sequence`` with code ``account.asset`` declared in '
            '``data/asset_sequence.xml``. Format: FA/YYYY/NNNN '
            '(e.g., FA/2025/0001). Reset annually via ``use_date_range``.'
        ),
    )
    active = fields.Boolean(
        default=True,
        help=(
            'Unset to archive an asset; archived records remain in the '
            'database for audit trail but are hidden from default list / '
            'kanban / search views.'
        ),
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        index=True,
        default=lambda self: self.env.company,
        help=(
            'Company that owns the asset. Required (no shared / cross-'
            'company assets). Indexed for efficient multi-company '
            '``ir.rule`` filtering.'
        ),
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency',
        related='company_id.currency_id',
        store=True,
        readonly=True,
        help=(
            'Currency used by all monetary fields on the asset; derived '
            'from the company\'s currency. Stored so that ``Monetary`` '
            'descriptors can resolve it without a related-field lookup '
            'on every read.'
        ),
    )

    # =========================================================================
    # ACQUISITION INFORMATION (AM-001 AC1, AC5)
    # =========================================================================

    acquisition_date = fields.Date(
        string='Acquisition Date',
        required=True,
        default=fields.Date.context_today,
        tracking=True,
        help=(
            'The date the asset was placed in service. Used as the '
            'default for ``depreciation_start_date`` when '
            '``start_date_option`` resolves to "acquisition_date", and '
            'as the journal entry date for the acquisition '
            '``account.move`` posted at confirmation (AM-001 AC2).'
        ),
    )
    acquisition_cost = fields.Monetary(
        string='Acquisition Cost',
        required=True,
        tracking=True,
        currency_field='currency_id',
        help=(
            'Original cost of the asset in the company currency. Used '
            'as the gross book value at the start of the depreciation '
            'schedule. Must be strictly positive (enforced by '
            '``_check_acquisition_cost_positive``).'
        ),
    )
    salvage_value = fields.Monetary(
        string='Salvage Value',
        default=0.0,
        tracking=True,
        currency_field='currency_id',
        help=(
            'Estimated residual / disposal value at end of useful life. '
            'Total depreciable base equals ``acquisition_cost - '
            'salvage_value``; the schedule is generated so the final '
            'net book value converges to this amount. Must be in '
            '``[0, acquisition_cost]`` (enforced by '
            '``_check_salvage_value``).'
        ),
    )
    vendor_id = fields.Many2one(
        comodel_name='res.partner',
        string='Vendor',
        domain="[('supplier_rank', '>', 0)]",
        tracking=True,
        help=(
            'Supplier the asset was acquired from (optional but '
            'recommended for audit trail). The domain filters to '
            'partners with ``supplier_rank > 0`` so that customer-only '
            'partners are not selectable here.'
        ),
    )
    source_invoice_id = fields.Many2one(
        comodel_name='account.move',
        string='Source Vendor Bill',
        domain=(
            "[('move_type', '=', 'in_invoice'),"
            " ('state', '=', 'posted'),"
            " ('company_id', '=', company_id)]"
        ),
        tracking=True,
        copy=False,
        help=(
            'Posted vendor bill that originated this asset (AM-001 '
            'Scenario 5). Selecting a bill here links the asset to the '
            'general ledger purchase entry for traceability. Restricted '
            'to posted vendor bills (``move_type = in_invoice``) of '
            'the same company.'
        ),
    )

    # =========================================================================
    # CATEGORY & ACCOUNT ASSIGNMENT (AM-001 AC3, AC6)
    # =========================================================================

    category_id = fields.Many2one(
        comodel_name='account.asset.category',
        string='Category',
        tracking=True,
        ondelete='restrict',
        check_company=True,
        help=(
            'Asset category template. Selecting a category pre-fills '
            'depreciation method, useful life, salvage percentage, '
            'start-date option, declining factor, and the three '
            'accounting accounts via the ``_onchange_category_id`` '
            'method (AM-001 Scenario 3). Inherited values can be '
            'overridden per-asset; category changes do NOT retroactively '
            'affect existing assets. ``ondelete=restrict`` prevents a '
            'category from being deleted while assets still reference it.'
        ),
    )
    asset_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Asset Account',
        required=True,
        domain="[('account_type', '=', 'asset_fixed')]",
        tracking=True,
        check_company=True,
        help=(
            'Fixed-asset account (type ``asset_fixed``) debited at '
            'acquisition (AM-001 AC2) and credited at disposal '
            '(AM-006). Must be of type ``asset_fixed``; enforced by '
            'both the domain (UI) and ``_check_asset_account_type`` '
            '(server-side). Multi-company filtering is enforced by '
            '``check_company=True`` plus the model-level '
            '``_check_company_auto = True`` which together restrict '
            'selection to accounts whose ``company_ids`` contains '
            'the asset\'s company.'
        ),
    )
    expense_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Depreciation Expense Account',
        required=True,
        domain="[('account_type', '=', 'expense_depreciation')]",
        tracking=True,
        check_company=True,
        help=(
            'Depreciation expense account (type ``expense_depreciation``) '
            'debited by every depreciation entry posted by AM-004. '
            'Enforced by domain and ``_check_expense_account_type``. '
            'Multi-company filtering via ``check_company=True``.'
        ),
    )
    accumulated_depreciation_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Accumulated Depreciation Account',
        required=True,
        domain="[('account_type', '=', 'asset_non_current')]",
        tracking=True,
        check_company=True,
        help=(
            'Accumulated-depreciation contra-asset account (type '
            '``asset_non_current``) credited by every depreciation '
            'entry posted by AM-004. Combined with the asset account, '
            'it produces the net book value on the balance sheet. '
            'Enforced by domain and '
            '``_check_accumulated_account_type``. Multi-company '
            'filtering via ``check_company=True``.'
        ),
    )
    journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Depreciation Journal',
        required=True,
        domain="[('type', '=', 'general'), ('company_id', '=', company_id)]",
        tracking=True,
        check_company=True,
        help=(
            'General journal (typically a miscellaneous / adjustment '
            'journal) that receives the acquisition entry and all '
            'depreciation entries. Restricted to journals of type '
            '``general``; sales / purchase / bank journals are not '
            'eligible because depreciation is a non-monetary '
            'adjusting entry.'
        ),
    )

    # =========================================================================
    # DEPRECIATION CONFIGURATION (AM-002 AC1-5)
    # =========================================================================

    depreciation_method = fields.Selection(
        selection=[
            ('straight_line', 'Straight-Line'),
            ('declining_balance', 'Declining Balance'),
            ('units_of_production', 'Units of Production'),
        ],
        string='Depreciation Method',
        required=True,
        default='straight_line',
        tracking=True,
        help=(
            'AM-002 method selector. ``straight_line`` distributes the '
            'depreciable base evenly across periods (AM-002 Scenario '
            '1/2). ``declining_balance`` applies an accelerated rate '
            '(``declining_factor / useful_life_years``) to the '
            'remaining net book value each period (AM-002 Scenario 3). '
            '``units_of_production`` ties depreciation to actual usage '
            'reported via ``units_production_to_date`` (AM-002 '
            'Scenario 4).'
        ),
    )
    useful_life_unit = fields.Selection(
        selection=[
            ('years', 'Years'),
            ('months', 'Months'),
            ('units', 'Units'),
        ],
        string='Useful Life Unit',
        default='years',
        required=True,
        help=(
            'Unit in which the useful life is expressed. ``years`` and '
            '``months`` apply to time-based methods (straight-line and '
            'declining balance); ``units`` is reserved for the '
            'units-of-production method.'
        ),
    )
    useful_life_years = fields.Integer(
        string='Useful Life (Years)',
        default=0,
        help=(
            'Number of full years over which the asset depreciates. '
            'Used when ``useful_life_unit = years``. Must be > 0 at '
            'confirmation time for time-based methods (enforced by '
            '``_check_depreciation_config``).'
        ),
    )
    useful_life_months = fields.Integer(
        string='Useful Life (Months)',
        default=0,
        help=(
            'Number of full months over which the asset depreciates. '
            'Used when ``useful_life_unit = months``. Must be > 0 at '
            'confirmation time for time-based methods.'
        ),
    )
    declining_factor = fields.Float(
        string='Declining Factor',
        default=2.0,
        digits=(5, 2),
        help=(
            'Multiplier applied to the straight-line rate to produce '
            'the declining-balance rate. The effective annual rate is '
            '``declining_factor / useful_life_years``. A factor of 2.0 '
            'yields the common "double-declining-balance" method. '
            'Must be > 0 when method is declining-balance.'
        ),
    )
    switch_to_straight_line = fields.Boolean(
        string='Switch to Straight-Line',
        default=False,
        help=(
            'When True (declining-balance only), the schedule '
            'automatically switches to straight-line at the period '
            'where straight-line depreciation on the remaining book '
            'value exceeds the declining-balance amount (AM-002 '
            'Scenario 3 optimal crossover). Ensures the asset is fully '
            'depreciated by end of useful life.'
        ),
    )
    units_production_total = fields.Float(
        string='Total Expected Units',
        default=0.0,
        help=(
            'Total expected production units over the asset\'s useful '
            'life (units-of-production method only). Per-unit '
            'depreciation rate equals ``(acquisition_cost - '
            'salvage_value) / units_production_total``. Must be > 0 '
            'when method is units-of-production.'
        ),
    )
    units_production_to_date = fields.Float(
        string='Units Produced to Date',
        default=0.0,
        help=(
            'Cumulative units produced and depreciated. Updated as '
            'production is recorded against the asset (units-of-'
            'production method only).'
        ),
    )
    start_date_option = fields.Selection(
        selection=[
            ('acquisition_date', 'Acquisition Date'),
            ('first_day_next_month', 'First Day of Next Month'),
            ('first_day_current_month', 'First Day of Current Month'),
            ('manual', 'Manual Date'),
        ],
        string='Start Date Option',
        default='acquisition_date',
        required=True,
        help=(
            'AM-002 Scenario 5 selector controlling how '
            '``depreciation_start_date`` is derived. '
            '``acquisition_date`` prorates from the acquisition date. '
            '``first_day_next_month`` and ``first_day_current_month`` '
            'align with month-end fiscal calendars. ``manual`` lets '
            'the Accountant specify the date explicitly.'
        ),
    )
    depreciation_start_date = fields.Date(
        string='Depreciation Start Date',
        help=(
            'Date the first depreciation period begins. Computed from '
            '``start_date_option`` at confirmation time unless '
            '``start_date_option = manual``, in which case the user '
            'must supply this value before confirming.'
        ),
    )

    # =========================================================================
    # STATE MACHINE (AM-001 AC2, AM-006)
    # =========================================================================

    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('open', 'Running'),
            ('close', 'Closed'),
        ],
        string='Status',
        default='draft',
        required=True,
        copy=False,
        tracking=True,
        help=(
            '``draft`` -- the asset is in configuration; no journal '
            'entry has been created. ``open`` -- the asset has been '
            'confirmed; the acquisition entry is posted; the AM-004 '
            'cron will post each scheduled depreciation entry as it '
            'becomes due. ``close`` -- the asset has been disposed '
            '(via AM-006) or fully depreciated (auto-closed by the '
            'cron when NBV reaches salvage value).'
        ),
    )

    # =========================================================================
    # LIFECYCLE JOURNAL ENTRIES
    # =========================================================================

    acquisition_move_id = fields.Many2one(
        comodel_name='account.move',
        string='Acquisition Entry',
        readonly=True,
        copy=False,
        help=(
            'The journal entry created when the asset was confirmed '
            '(state ``draft`` -> ``open``). Records the asset debit '
            'and an offset credit (typically a clearing / suspense / '
            'transfer account, or the source vendor bill\'s payable '
            'account if linked).'
        ),
    )
    depreciation_line_ids = fields.One2many(
        comodel_name='account.asset.depreciation.line',
        inverse_name='asset_id',
        string='Depreciation Schedule',
        copy=False,
        help=(
            'The depreciation schedule lines generated at confirmation '
            '(AM-002) and posted by the AM-004 cron. One record per '
            'period (year, month, or production event). Cleared and '
            'regenerated on schedule recomputation, but POSTED lines '
            'are preserved by ``_compute_depreciation_schedule``.'
        ),
    )

    # =========================================================================
    # COMPUTED AGGREGATES (stored for O(1) board / list rendering)
    # =========================================================================

    accumulated_depreciation = fields.Monetary(
        string='Accumulated Depreciation',
        compute='_compute_depreciation_totals',
        store=True,
        currency_field='currency_id',
        help=(
            'Sum of ``depreciation_amount`` across all depreciation '
            'schedule lines whose ``state == \'posted\'``. Stored '
            '(``store=True``) so list / form / kanban / graph views '
            'never re-aggregate at read time.'
        ),
    )
    net_book_value = fields.Monetary(
        string='Net Book Value',
        compute='_compute_depreciation_totals',
        store=True,
        currency_field='currency_id',
        help=(
            'Asset net book value: ``acquisition_cost - '
            'accumulated_depreciation``. Falls to ``salvage_value`` '
            'on the final fully-posted period of the schedule. The '
            'AM-004 cron auto-closes the asset when NBV reaches '
            'salvage value.'
        ),
    )
    depreciation_line_count = fields.Integer(
        string='# Depreciation Lines',
        compute='_compute_depreciation_line_count',
        help=(
            'Total number of depreciation schedule lines, draft and '
            'posted combined. Used as a smart-button counter on the '
            'asset form for navigation to the depreciation board.'
        ),
    )

    # =========================================================================
    # SQL CONSTRAINTS
    # =========================================================================

    # Asset reference uniqueness scoped by company so that the same
    # numeric reference may exist in multiple companies in a multi-
    # company deployment (PostgreSQL emits NULL != NULL semantics, so
    # the placeholder reference '/' that may briefly exist while the
    # ir.sequence resolves is NOT constrained -- the sequence call
    # always returns a non-null value before the row hits the database).
    #
    # Odoo 19 native uniqueness enforcement. The ``models.UniqueIndex`` is
    # the supported Odoo 19 mechanism that actually creates the PostgreSQL
    # unique index (see ``odoo/orm/table_objects.py::UniqueIndex``). The
    # generated database object is named
    # ``account_asset_unique_reference_per_company``.
    _unique_reference_per_company = models.UniqueIndex(
        '(reference, company_id)',
        'Asset reference must be unique per company.',
    )

    # Backwards-compatibility declaration kept for schema/spec alignment
    # with the AAP exports list (``members_exposed`` includes
    # ``_sql_constraints``). Odoo 19 emits a deprecation warning for this
    # attribute via ``odoo/orm/model_classes.py`` but the actual uniqueness
    # is enforced by the ``_unique_reference_per_company`` UniqueIndex
    # above; both entries describe the SAME logical constraint and produce
    # the SAME database guarantee.
    _sql_constraints = [
        (
            'unique_reference_per_company',
            'UNIQUE(reference, company_id)',
            'Asset reference must be unique per company.',
        ),
    ]

    # =========================================================================
    # DEFAULT VALUE METHODS
    # =========================================================================

    @api.model
    def _default_reference(self):
        """Generate a unique asset reference via ``ir.sequence``.

        Uses the ``account.asset`` sequence code declared in
        ``data/asset_sequence.xml`` (format ``FA/YYYY/NNNN`` with
        annual reset via ``use_date_range=True``). Falls back to the
        placeholder ``'/'`` when the sequence cannot be resolved
        (e.g., during early module install before the data file is
        loaded). Odoo recomputes the placeholder on the next write
        once the sequence becomes available.

        :return: a string asset reference, e.g., ``'FA/2025/0001'`` or
                 ``'/'`` on fallback.
        :rtype: str
        """
        return self.env['ir.sequence'].with_company(
            self.env.company,
        ).next_by_code('account.asset') or '/'

    # =========================================================================
    # COMPUTE METHODS
    # =========================================================================

    @api.depends(
        'acquisition_cost',
        'depreciation_line_ids',
        'depreciation_line_ids.state',
        'depreciation_line_ids.depreciation_amount',
    )
    def _compute_depreciation_totals(self):
        """Compute ``accumulated_depreciation`` and ``net_book_value``.

        Sums the ``depreciation_amount`` of every schedule line whose
        ``state == 'posted'`` to produce ``accumulated_depreciation``;
        derives ``net_book_value`` as ``acquisition_cost -
        accumulated_depreciation``.

        Both fields are stored (``store=True``) so subsequent reads do
        not re-aggregate. The dependency tuple is the FULL trigger
        list to ensure recomputation when:

            * ``acquisition_cost`` changes (re-baselines NBV)
            * the schedule recordset changes (lines added/removed)
            * a line transitions to or from ``state = 'posted'``
            * a line's ``depreciation_amount`` is edited
        """
        for asset in self:
            posted_lines = asset.depreciation_line_ids.filtered(
                lambda line: line.state == 'posted',
            )
            asset.accumulated_depreciation = sum(
                posted_lines.mapped('depreciation_amount'),
            )
            asset.net_book_value = (
                (asset.acquisition_cost or 0.0)
                - asset.accumulated_depreciation
            )

    @api.depends('depreciation_line_ids')
    def _compute_depreciation_line_count(self):
        """Count total depreciation schedule lines (draft + posted).

        Used as a smart-button counter on the asset form. Not stored
        (cheap to compute as ``len``) so the form always reflects the
        current count without write-time recompute overhead.
        """
        for asset in self:
            asset.depreciation_line_count = len(asset.depreciation_line_ids)

    # =========================================================================
    # ONCHANGE METHODS
    # =========================================================================

    @api.onchange('category_id')
    def _onchange_category_id(self):
        """Pre-fill depreciation configuration from the selected category.

        Per AM-001 Scenario 3, selecting a category copies its default
        depreciation method, useful life, declining factor, salvage
        percentage, start-date option, and account assignments onto
        the asset. The ``or self.<field>`` idiom respects manual
        overrides: a value already set on the asset is NOT replaced
        by the category default. This makes category selection an
        ADDITIVE pre-fill, not a destructive overwrite.

        Salvage value is derived from ``category.salvage_percent`` x
        ``acquisition_cost / 100`` ONLY when both are non-zero; an
        already-set explicit ``salvage_value`` is preserved.

        Per AM-001 Scenario 3, category-driven values can be
        overridden on the asset, and category changes after asset
        creation do NOT retroactively affect already-saved assets
        (this method runs only on user-driven onchange).
        """
        if not self.category_id:
            return
        cat = self.category_id
        # Account / journal assignments: copy only if not already set
        # so the user's explicit selection wins over the category
        # default.
        self.asset_account_id = self.asset_account_id or cat.asset_account_id
        self.expense_account_id = (
            self.expense_account_id or cat.expense_account_id
        )
        self.accumulated_depreciation_account_id = (
            self.accumulated_depreciation_account_id
            or cat.accumulated_depreciation_account_id
        )
        self.journal_id = self.journal_id or cat.journal_id
        # Depreciation method and parameters: take category defaults
        # when present; otherwise keep the existing asset value.
        self.depreciation_method = (
            cat.depreciation_method or self.depreciation_method
        )
        self.useful_life_unit = cat.useful_life_unit or self.useful_life_unit
        self.useful_life_years = (
            cat.useful_life_years or self.useful_life_years
        )
        self.useful_life_months = (
            cat.useful_life_months or self.useful_life_months
        )
        self.declining_factor = (
            cat.declining_factor or self.declining_factor
        )
        # Boolean flag is copied unconditionally (False is a valid
        # default that the category may explicitly set).
        self.switch_to_straight_line = cat.switch_to_straight_line
        self.units_production_total = (
            cat.units_production_total or self.units_production_total
        )
        self.start_date_option = (
            cat.start_date_option or self.start_date_option
        )
        # Salvage value derivation from category percentage; only if
        # both inputs are present and the asset's salvage_value has
        # not already been explicitly set.
        if (
            cat.salvage_percent
            and self.acquisition_cost
            and not self.salvage_value
        ):
            self.salvage_value = (
                (cat.salvage_percent / 100.0) * self.acquisition_cost
            )

    # =========================================================================
    # PYTHON CONSTRAINTS (AM-001 AC6, AM-002 AC7)
    # =========================================================================

    @api.constrains('acquisition_cost')
    def _check_acquisition_cost_positive(self):
        """Validate ``acquisition_cost`` is strictly positive.

        Per AM-001 AC6 and AM-002 AC7, an asset cannot have zero or
        negative acquisition cost: the depreciable base would be
        non-positive and the schedule generation would be undefined
        (division-by-zero or negative depreciation amounts). The
        check uses ``is not None`` to permit the transient
        ``acquisition_cost = False`` state during record creation
        before required-field enforcement triggers.
        """
        for asset in self:
            if (
                asset.acquisition_cost is not None
                and asset.acquisition_cost <= 0
            ):
                raise ValidationError(_(
                    'Acquisition cost must be strictly positive for '
                    'asset "%s".',
                    asset.name or '',
                ))

    @api.constrains('salvage_value', 'acquisition_cost')
    def _check_salvage_value(self):
        """Validate ``salvage_value`` is in ``[0, acquisition_cost]``.

        Per AM-002 AC7, salvage value must be non-negative and cannot
        exceed acquisition cost. A salvage value above acquisition
        cost would imply that the asset appreciates rather than
        depreciates, which violates the fundamental fixed-asset
        accounting model (revaluation surplus is handled separately
        by AM-005, not by manipulating ``salvage_value``).
        """
        for asset in self:
            if asset.salvage_value is None:
                continue
            if asset.salvage_value < 0:
                raise ValidationError(_(
                    'Salvage value cannot be negative (asset "%s").',
                    asset.name or '',
                ))
            if asset.salvage_value > (asset.acquisition_cost or 0):
                raise ValidationError(_(
                    'Salvage value cannot exceed acquisition cost '
                    '(asset "%s").',
                    asset.name or '',
                ))

    @api.constrains('asset_account_id')
    def _check_asset_account_type(self):
        """Validate ``asset_account_id`` is of type ``asset_fixed``.

        AM-001 AC6 requires that the asset account is of fixed-asset
        type; non-fixed-asset accounts (e.g., current assets, expense
        accounts) would mis-classify the asset on the balance sheet.
        Enforced at write time even though the field's UI domain
        already filters the selection list, because the domain is
        only a UI hint and bypassed by API-level writes (e.g., from
        scripts or web services).
        """
        for asset in self:
            if (
                asset.asset_account_id
                and asset.asset_account_id.account_type != 'asset_fixed'
            ):
                raise ValidationError(_(
                    'Asset account for "%s" must have account type '
                    '"Fixed Assets" (asset_fixed); got "%s".',
                    asset.name or '',
                    asset.asset_account_id.account_type,
                ))

    @api.constrains('expense_account_id')
    def _check_expense_account_type(self):
        """Validate ``expense_account_id`` is ``expense_depreciation``.

        AM-001 AC6 / AM-002 AC7 require that the depreciation expense
        account is of type ``expense_depreciation`` so that it
        aggregates correctly into the depreciation expense line on
        the income statement.
        """
        for asset in self:
            if (
                asset.expense_account_id
                and asset.expense_account_id.account_type
                != 'expense_depreciation'
            ):
                raise ValidationError(_(
                    'Depreciation expense account for "%s" must have '
                    'account type "Depreciation" '
                    '(expense_depreciation); got "%s".',
                    asset.name or '',
                    asset.expense_account_id.account_type,
                ))

    @api.constrains('accumulated_depreciation_account_id')
    def _check_accumulated_account_type(self):
        """Validate accumulated-depreciation account type.

        AM-001 AC6 requires that the accumulated-depreciation
        contra-asset account is of type ``asset_non_current`` so the
        balance-sheet aggregation correctly nets it against the
        ``asset_fixed`` account to produce net property-plant-and-
        equipment.
        """
        for asset in self:
            account = asset.accumulated_depreciation_account_id
            if account and account.account_type != 'asset_non_current':
                raise ValidationError(_(
                    'Accumulated depreciation account for "%s" must '
                    'have account type "Non-current Assets" '
                    '(asset_non_current); got "%s".',
                    asset.name or '',
                    account.account_type,
                ))

    @api.constrains(
        'depreciation_method',
        'useful_life_unit',
        'useful_life_years',
        'useful_life_months',
        'units_production_total',
    )
    def _check_depreciation_config(self):
        """Validate depreciation configuration completeness (AM-002 AC7).

        For ``straight_line`` and ``declining_balance`` methods, the
        useful life (years or months, per ``useful_life_unit``) must
        be > 0. For ``units_of_production``, the total expected units
        must be > 0. A zero useful life or zero expected units would
        cause division-by-zero in schedule generation.

        Note: this check enforces strictly-positive values BEFORE
        confirmation. The matching category-level checks
        (``account.asset.category._check_useful_life``) allow zero
        as a template default; the asset-level check is stricter
        because the schedule must be computable.
        """
        for asset in self:
            method = asset.depreciation_method
            if method in ('straight_line', 'declining_balance'):
                if (
                    asset.useful_life_unit == 'years'
                    and asset.useful_life_years <= 0
                ):
                    raise ValidationError(_(
                        'Useful life in years must be > 0 for method '
                        '"%s" (asset "%s").',
                        method,
                        asset.name or '',
                    ))
                if (
                    asset.useful_life_unit == 'months'
                    and asset.useful_life_months <= 0
                ):
                    raise ValidationError(_(
                        'Useful life in months must be > 0 for method '
                        '"%s" (asset "%s").',
                        method,
                        asset.name or '',
                    ))
            if (
                method == 'units_of_production'
                and asset.units_production_total <= 0
            ):
                raise ValidationError(_(
                    'Total expected units must be > 0 for units-of-'
                    'production asset "%s".',
                    asset.name or '',
                ))

    @api.constrains('declining_factor', 'depreciation_method')
    def _check_declining_factor(self):
        """Validate ``declining_factor`` for declining-balance method.

        Per AM-002 Scenario 3 / 7, the declining-balance method
        requires a strictly-positive factor. A zero or negative
        factor would produce no depreciation or negative depreciation,
        both nonsensical. For other methods this field is ignored;
        the constraint only fires when the method is
        ``declining_balance``.
        """
        for asset in self:
            if (
                asset.depreciation_method == 'declining_balance'
                and asset.declining_factor <= 0
            ):
                raise ValidationError(_(
                    'Declining factor must be > 0 for declining-'
                    'balance asset "%s".',
                    asset.name or '',
                ))

    # =========================================================================
    # VALIDATION HELPERS (called by action_confirm)
    # =========================================================================

    def _validate_accounts(self):
        """Validate all required accounts are configured (AM-001 AC6).

        Called at ``action_confirm`` time as a defensive last check
        before posting the acquisition entry. Verifies that the four
        required fields (``asset_account_id``, ``expense_account_id``,
        ``accumulated_depreciation_account_id``, ``journal_id``) are
        all set, and that each account belongs to the asset\'s
        company. The ``check_company=True`` attribute on each FK
        already enforces this at the ORM level, but this defensive
        re-check guards against API-level writes that bypass UI
        validation.

        :raises UserError: when any required field is missing or any
            account belongs to a different company than the asset.
        """
        self.ensure_one()
        missing = []
        if not self.asset_account_id:
            missing.append(_('Asset Account'))
        if not self.expense_account_id:
            missing.append(_('Depreciation Expense Account'))
        if not self.accumulated_depreciation_account_id:
            missing.append(_('Accumulated Depreciation Account'))
        if not self.journal_id:
            missing.append(_('Depreciation Journal'))
        if missing:
            raise UserError(_(
                'Missing required fields for asset "%s": %s.',
                self.name or '',
                ', '.join(missing),
            ))
        # Same-company check (defensive; check_company=True on the FK
        # already enforces this, but API-level writes can bypass the
        # UI domain).
        #
        # Odoo 19 changed ``account.account.company_id`` (Many2one) to
        # ``account.account.company_ids`` (Many2many) so we test
        # membership: every account in this asset's record must be
        # available in the asset's company. ``account.journal`` retains
        # the Many2one ``company_id`` and is checked separately.
        company = self.company_id
        for account in (
            self.asset_account_id,
            self.expense_account_id,
            self.accumulated_depreciation_account_id,
        ):
            allowed_companies = account.company_ids
            if allowed_companies and company not in allowed_companies:
                raise UserError(_(
                    'Account "%s" does not belong to asset company '
                    '"%s".',
                    account.display_name,
                    company.display_name,
                ))
        # Same-company check for the journal (still Many2one in Odoo 19).
        if (
            self.journal_id.company_id
            and self.journal_id.company_id != company
        ):
            raise UserError(_(
                'Journal "%s" does not belong to asset company '
                '"%s".',
                self.journal_id.display_name,
                company.display_name,
            ))

    def _validate_depreciation_config(self):
        """Defensive re-check of depreciation configuration.

        Verifies that the useful life (years or months) is > 0 for
        time-based methods, and that ``units_production_total`` > 0
        for the units-of-production method. The matching
        ``@api.constrains`` runs on every write, but this defensive
        check ensures that the asset cannot be confirmed in an
        invalid state even if a constrained field is somehow
        bypassed.

        :raises UserError: when the depreciation configuration is
            incomplete or inconsistent.
        """
        self.ensure_one()
        method = self.depreciation_method
        if method in ('straight_line', 'declining_balance'):
            if self.useful_life_unit == 'years':
                periods = self.useful_life_years
            else:
                periods = self.useful_life_months
            if periods <= 0:
                raise UserError(_(
                    'Useful life must be > 0 before confirming asset '
                    '"%s".',
                    self.name or '',
                ))
        elif (
            method == 'units_of_production'
            and self.units_production_total <= 0
        ):
            raise UserError(_(
                'Total expected units must be > 0 before confirming '
                'asset "%s".',
                self.name or '',
            ))

    def _resolve_depreciation_start_date(self):
        """Compute ``depreciation_start_date`` per ``start_date_option``.

        AM-002 Scenario 5 selector behaviours:

            * ``acquisition_date`` -- the start date equals the
              acquisition date (default; produces full-period prorating).
            * ``first_day_next_month`` -- the start date is the first
              day of the month following acquisition; depreciation
              begins cleanly at the start of the next fiscal month.
              December acquisitions wrap to January of the next year
              via the ``acq.year + (acq.month // 12)`` arithmetic.
            * ``first_day_current_month`` -- the start date is the
              first day of the acquisition month (back-dates the
              start of depreciation to the beginning of the
              acquisition month).
            * ``manual`` -- requires the user to have explicitly set
              ``depreciation_start_date`` already; raises ``UserError``
              if the field is empty.

        Uses ``datetime.date`` directly (not ``relativedelta``) for
        the simple first-of-month boundary calculations because the
        arithmetic is closed-form and does not benefit from
        ``relativedelta``\'s edge-case handling.

        :raises UserError: when ``start_date_option = manual`` and
            ``depreciation_start_date`` is not set, or when
            ``acquisition_date`` is missing.
        """
        self.ensure_one()
        if self.start_date_option == 'manual':
            if not self.depreciation_start_date:
                raise UserError(_(
                    'Manual start-date option requires an explicit '
                    'depreciation start date for asset "%s".',
                    self.name or '',
                ))
            return
        acq = self.acquisition_date
        if not acq:
            raise UserError(_(
                'Acquisition date is required for asset "%s".',
                self.name or '',
            ))
        if self.start_date_option == 'acquisition_date':
            self.depreciation_start_date = acq
        elif self.start_date_option == 'first_day_next_month':
            # First day of the month after acquisition. December
            # wraps to January of the next year via the
            # ``// 12`` and ``% 12 + 1`` arithmetic.
            year = acq.year + (acq.month // 12)
            month = (acq.month % 12) + 1
            self.depreciation_start_date = date(year, month, 1)
        elif self.start_date_option == 'first_day_current_month':
            self.depreciation_start_date = date(
                acq.year, acq.month, 1,
            )

    # =========================================================================
    # ACQUISITION JOURNAL ENTRY (AM-001 AC2)
    # =========================================================================

    def _create_acquisition_move(self):
        """Create and post the acquisition ``account.move``.

        Posts a balanced two-line journal entry on the asset\'s
        depreciation journal with debit / credit pattern:

            Debit:  ``asset_account_id``       acquisition_cost
            Credit: <offset account>           acquisition_cost

        Offset account resolution order:

            1. If ``source_invoice_id`` is set, use the partner\'s
               account_payable_id (the payable account from the
               source vendor bill\'s context). This preserves the
               audit trail back to the originating purchase entry.
            2. Otherwise, use the company\'s
               ``transfer_account_id`` (a clearing / suspense
               account) if configured.
            3. Otherwise, fall back to the journal\'s
               ``default_account_id``.

        The move is created with ``move_type='entry'``, the
        acquisition date as the entry date, and a descriptive
        reference. The lines are created via ``Command.create``
        (a single ``Command`` per line) and the move is posted
        immediately via ``move.action_post()`` per AM-001 AC2.

        :return: the created and posted ``account.move`` record.
        :rtype: ``account.move``
        :raises UserError: when no offset account can be resolved.
        """
        self.ensure_one()
        # Resolve the offset account using the documented priority.
        offset_account = self.env['account.account']
        if self.source_invoice_id and self.source_invoice_id.partner_id:
            partner = self.source_invoice_id.partner_id.with_company(
                self.company_id,
            )
            offset_account = (
                partner.property_account_payable_id or offset_account
            )
        if not offset_account:
            offset_account = (
                self.company_id.transfer_account_id or offset_account
            )
        if not offset_account:
            offset_account = (
                self.journal_id.default_account_id or offset_account
            )
        if not offset_account:
            raise UserError(_(
                'Unable to resolve an offset account for the '
                'acquisition entry of asset "%s". Configure either a '
                'source vendor bill with a payable account, a company '
                'transfer / clearing account, or a default account on '
                'journal "%s".',
                self.name or '',
                self.journal_id.display_name,
            ))
        # Build the balanced move.
        move_vals = {
            'move_type': 'entry',
            'date': self.acquisition_date,
            'journal_id': self.journal_id.id,
            'company_id': self.company_id.id,
            'ref': _(
                'Asset acquisition: %s',
                self.reference or self.name or '',
            ),
            'asset_id': self.id,
            'asset_entry_type': 'acquisition',
            'line_ids': [
                Command.create({
                    'name': _('Acquisition of %s', self.name or ''),
                    'account_id': self.asset_account_id.id,
                    'partner_id': (
                        self.vendor_id.id if self.vendor_id else False
                    ),
                    'debit': self.acquisition_cost,
                    'credit': 0.0,
                }),
                Command.create({
                    'name': _(
                        'Acquisition offset for %s', self.name or '',
                    ),
                    'account_id': offset_account.id,
                    'partner_id': (
                        self.vendor_id.id if self.vendor_id else False
                    ),
                    'debit': 0.0,
                    'credit': self.acquisition_cost,
                }),
            ],
        }
        move = self.env['account.move'].with_company(
            self.company_id,
        ).create(move_vals)
        move.action_post()
        _logger.info(
            'Posted acquisition move %s for asset %s '
            '(amount=%s, journal=%s).',
            move.name,
            self.display_name,
            self.acquisition_cost,
            self.journal_id.display_name,
        )
        return move

    # =========================================================================
    # STATE-MACHINE ACTIONS (AM-001 AC2, AM-006)
    # =========================================================================

    def action_confirm(self):
        """Transition draft asset to ``open`` state.

        Implements AM-001 Scenario 2: validates configuration, creates
        and posts the acquisition journal entry, generates the
        depreciation schedule, transitions ``state`` from ``draft``
        to ``open``, and posts a chatter message recording the
        transition.

        Each asset in ``self`` is processed independently so that a
        batch confirmation operates record-by-record. Validation
        errors raise ``UserError`` immediately and abort the entire
        batch (per the design assumption that batch confirmation
        means "confirm them all or none").

        :return: ``True`` when all assets are confirmed.
        :raises UserError: when an asset is not in ``draft`` state,
            or when validation fails.
        """
        for asset in self:
            if asset.state != 'draft':
                raise UserError(_(
                    'Only draft assets can be confirmed. Asset "%s" '
                    'is in state "%s".',
                    asset.name or '',
                    asset.state,
                ))
            asset._validate_accounts()
            asset._validate_depreciation_config()
            asset._resolve_depreciation_start_date()
            move = asset._create_acquisition_move()
            asset.acquisition_move_id = move.id
            asset._compute_depreciation_schedule()
            asset.write({'state': 'open'})
            asset.message_post(body=_(
                'Asset confirmed. Acquisition entry %(name)s posted; '
                'depreciation schedule generated.',
                name=move.name or '',
            ))
        return True

    def action_set_draft(self):
        """Reset an open asset back to ``draft`` (admin reversal).

        Reverses the acquisition move (cancels it via
        ``button_draft`` followed by ``button_cancel``), clears the
        ``acquisition_move_id`` link, and transitions ``state`` to
        ``draft``. Refuses to act if any depreciation line has been
        posted (the asset already has irreversible accounting
        impact).

        :return: ``True`` when all assets are reset.
        :raises UserError: when an asset is not ``open``, or when
            posted depreciation lines exist.
        """
        for asset in self:
            if asset.state != 'open':
                raise UserError(_(
                    'Only open assets can be reset to draft '
                    '(asset "%s" is in state "%s").',
                    asset.name or '',
                    asset.state,
                ))
            posted_lines = asset.depreciation_line_ids.filtered(
                lambda line: line.state == 'posted',
            )
            if posted_lines:
                raise UserError(_(
                    'Cannot reset asset "%s" to draft because it has '
                    '%d posted depreciation line(s). Reverse the '
                    'depreciation entries through the journal '
                    'workflow first.',
                    asset.name or '',
                    len(posted_lines),
                ))
            move = asset.acquisition_move_id
            if move and move.state == 'posted':
                move.button_draft()
                move.button_cancel()
            # Drop draft schedule lines so the asset can be
            # re-configured cleanly before the next confirmation.
            draft_lines = asset.depreciation_line_ids.filtered(
                lambda line: line.state == 'draft',
            )
            draft_lines.unlink()
            asset.write({
                'state': 'draft',
                'acquisition_move_id': False,
            })
            asset.message_post(body=_(
                'Asset reset to draft; acquisition entry cancelled.',
            ))
        return True

    def action_close(self):
        """Transition asset to ``close`` state.

        Called by the AM-006 disposal wizard after posting the
        disposal journal entry, and by the AM-004 cron when an
        asset has been fully depreciated (NBV reaches salvage value).
        Does NOT generate any journal entry of its own; the disposal
        wizard owns that responsibility.

        :return: ``True``.
        """
        for asset in self:
            if asset.state == 'close':
                continue
            asset.write({'state': 'close'})
            asset.message_post(body=_(
                'Asset closed.',
            ))
        return True

    def action_dispose(self):
        """Open the AM-006 disposal wizard for the current asset.

        Returns an ``ir.actions.act_window`` dict that opens the
        ``account.asset.disposal.wizard`` TransientModel as a modal
        with the current asset pre-filled via context.

        :return: an ``ir.actions.act_window`` dict.
        :rtype: dict
        :raises UserError: when called on an asset not in ``open``
            state (closed assets cannot be re-disposed).
        """
        self.ensure_one()
        if self.state != 'open':
            raise UserError(_(
                'Only open assets can be disposed (asset "%s" is in '
                'state "%s").',
                self.name or '',
                self.state,
            ))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Dispose Asset'),
            'res_model': 'account.asset.disposal.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_asset_id': self.id,
                'default_company_id': self.company_id.id,
            },
        }

    def action_modify(self):
        """Open the AM-005 modification wizard for the current asset.

        Returns an ``ir.actions.act_window`` dict that opens the
        ``account.asset.modification.wizard`` TransientModel as a
        modal with the current asset pre-filled via context. Used
        for revaluation, impairment, impairment reversal, useful
        life adjustments, and salvage-value changes.

        :return: an ``ir.actions.act_window`` dict.
        :rtype: dict
        :raises UserError: when called on an asset not in ``open``
            state.
        """
        self.ensure_one()
        if self.state != 'open':
            raise UserError(_(
                'Only open assets can be modified (asset "%s" is in '
                'state "%s").',
                self.name or '',
                self.state,
            ))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Modify Asset'),
            'res_model': 'account.asset.modification.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_asset_id': self.id,
                'default_company_id': self.company_id.id,
            },
        }

    def action_view_depreciation_lines(self):
        """Open the depreciation board filtered to this asset.

        Smart-button action returning an ``ir.actions.act_window``
        that lists the asset\'s depreciation schedule lines in tree /
        kanban / graph view. The default search context filters by
        the current asset; the context default supplies
        ``default_asset_id`` so that creation of new lines (admin
        only) is also pre-filled.

        :return: an ``ir.actions.act_window`` dict.
        :rtype: dict
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Depreciation Schedule'),
            'res_model': 'account.asset.depreciation.line',
            'view_mode': 'list,kanban,graph',
            'domain': [('asset_id', '=', self.id)],
            'context': {
                'default_asset_id': self.id,
                'search_default_asset_id': self.id,
            },
        }

    # =========================================================================
    # DEPRECIATION SCHEDULE GENERATION (AM-002 AC1-4)
    # =========================================================================

    def _compute_depreciation_schedule(self):
        """Generate the depreciation schedule per the configured method.

        Dispatcher that:

            1. Drops existing DRAFT schedule lines (preserves POSTED
               lines so re-running this method after partial cron
               execution does NOT void already-posted entries; only
               the unposted future lines are regenerated).
            2. Calls the method-specific helper:

                * ``straight_line``       -> ``_schedule_straight_line``
                * ``declining_balance``   -> ``_schedule_declining_balance``
                * ``units_of_production`` -> ``_schedule_units_of_production``

        :raises UserError: when the depreciation method is unknown
            (defensive guard against schema drift or test fixtures).
        """
        self.ensure_one()
        # Drop DRAFT lines only; NEVER touch posted lines (idempotency
        # for AM-005 modification re-computation, where the posted
        # historical schedule must remain immutable).
        draft_lines = self.depreciation_line_ids.filtered(
            lambda line: line.state == 'draft',
        )
        if draft_lines:
            draft_lines.unlink()
        method = self.depreciation_method
        if method == 'straight_line':
            self._schedule_straight_line()
        elif method == 'declining_balance':
            self._schedule_declining_balance()
        elif method == 'units_of_production':
            self._schedule_units_of_production()
        else:
            raise UserError(_(
                'Unknown depreciation method "%s" for asset "%s".',
                method,
                self.name or '',
            ))

    def _schedule_straight_line(self):
        """Generate a straight-line depreciation schedule (AM-002 Sc1/2).

        Per-period amount = ``(acquisition_cost - salvage_value) /
        total_periods``. Total periods is derived from
        ``useful_life_years`` (one line per year) or
        ``useful_life_months`` (one line per month), per
        ``useful_life_unit``.

        Dates advance via ``relativedelta(years=+1)`` or
        ``relativedelta(months=+1)`` -- NEVER via
        ``timedelta(days=N)`` -- because calendar months and years
        have variable lengths and the precise calendar boundary is
        what fiscal reporting consumers (the AM-003 board, the
        AM-004 cron) depend on.

        Rounding: per-period amounts are rounded to the company\'s
        currency precision; the FINAL period\'s amount is adjusted to
        absorb any cumulative rounding error so the schedule\'s total
        equals exactly ``acquisition_cost - salvage_value``.
        """
        self.ensure_one()
        depreciable = (self.acquisition_cost or 0.0) - (self.salvage_value or 0.0)
        if depreciable <= 0:
            # Nothing to depreciate (asset is fully salvaged); no
            # schedule lines required. The cron will treat the asset
            # as fully depreciated and close it on the next run.
            return
        # Resolve total period count and per-period date increment.
        if self.useful_life_unit == 'years':
            total_periods = self.useful_life_years
            increment = relativedelta(years=+1)
        else:
            total_periods = self.useful_life_months
            increment = relativedelta(months=+1)
        if total_periods <= 0:
            return
        currency = self.currency_id or self.company_id.currency_id
        per_period = currency.round(depreciable / total_periods)
        start_date = self.depreciation_start_date or self.acquisition_date
        commands = []
        cumulative = 0.0
        current_date = start_date
        for sequence in range(1, total_periods + 1):
            if sequence == total_periods:
                # Final period absorbs cumulative rounding error so
                # that sum == depreciable exactly.
                amount = currency.round(depreciable - cumulative)
            else:
                amount = per_period
            cumulative += amount
            commands.append(Command.create({
                'sequence': sequence,
                'depreciation_date': current_date,
                'depreciation_amount': amount,
            }))
            current_date = current_date + increment
        if commands:
            self.write({'depreciation_line_ids': commands})

    def _schedule_declining_balance(self):
        """Generate a declining-balance depreciation schedule (AM-002 Sc3).

        Per-period amount = ``book_value * rate``, where
        ``rate = declining_factor / total_periods`` (so a factor of
        2.0 over 5 years yields 40% per period -- the classic
        "double-declining-balance"). ``book_value`` is the running
        net book value at the START of the period (acquisition_cost
        less the cumulative depreciation through prior periods).

        When ``switch_to_straight_line`` is True, the schedule
        switches to straight-line at the FIRST period where the
        straight-line amount on the remaining book value (less
        salvage value) exceeds the declining amount. This ensures
        the schedule fully depreciates the asset to its salvage
        value by the end of the useful life.

        The FINAL period\'s amount is adjusted to absorb any
        cumulative rounding error so the schedule\'s total equals
        exactly ``acquisition_cost - salvage_value``.
        """
        self.ensure_one()
        depreciable = (self.acquisition_cost or 0.0) - (self.salvage_value or 0.0)
        if depreciable <= 0:
            return
        # Resolve total period count and per-period date increment.
        if self.useful_life_unit == 'years':
            total_periods = self.useful_life_years
            increment = relativedelta(years=+1)
        else:
            total_periods = self.useful_life_months
            increment = relativedelta(months=+1)
        if total_periods <= 0:
            return
        currency = self.currency_id or self.company_id.currency_id
        rate = (self.declining_factor or 0.0) / total_periods
        if rate <= 0:
            return
        start_date = self.depreciation_start_date or self.acquisition_date
        commands = []
        cumulative = 0.0
        current_date = start_date
        switched_to_sl = False
        for sequence in range(1, total_periods + 1):
            book_value = (self.acquisition_cost or 0.0) - cumulative
            # Declining-balance amount -- never depreciate below
            # salvage value, so the calculated amount is bounded by
            # ``book_value - salvage_value`` (remaining depreciable
            # base).
            remaining = book_value - (self.salvage_value or 0.0)
            if remaining <= 0:
                break
            declining_amount = currency.round(book_value * rate)
            # Switch-to-straight-line check: only consider it once
            # the asset has not yet switched. Once switched, all
            # remaining periods use the straight-line amount on the
            # then-current book value.
            remaining_periods = total_periods - sequence + 1
            if (
                self.switch_to_straight_line
                and not switched_to_sl
                and remaining_periods > 0
            ):
                sl_amount = currency.round(
                    remaining / remaining_periods,
                )
                if sl_amount > declining_amount:
                    switched_to_sl = True
            if switched_to_sl:
                amount = currency.round(remaining / remaining_periods)
            else:
                amount = declining_amount
            # Cap by remaining depreciable base; never overshoot.
            amount = min(amount, remaining)
            # Final period absorbs rounding error.
            if sequence == total_periods:
                amount = currency.round(depreciable - cumulative)
                # Defensive: if rounding yields a negative or zero
                # final amount (because earlier rounding overshot),
                # skip the line rather than create a negative entry.
                if amount <= 0:
                    break
            cumulative += amount
            commands.append(Command.create({
                'sequence': sequence,
                'depreciation_date': current_date,
                'depreciation_amount': amount,
            }))
            current_date = current_date + increment
        if commands:
            self.write({'depreciation_line_ids': commands})

    def _schedule_units_of_production(self):
        """Generate the initial line for units-of-production (AM-002 Sc4).

        Creates a single placeholder schedule line dated on the
        asset\'s ``depreciation_start_date`` (or its
        ``acquisition_date`` as a fallback) with
        ``depreciation_amount = 0`` and ``sequence = 1``. Subsequent
        production-event entries are appended to the schedule as
        production is recorded; the per-unit rate is computed at
        usage time as ``(acquisition_cost - salvage_value) /
        units_production_total``.

        This deliberately leaves the schedule "empty" of forecast
        lines because the units-of-production method depends on
        actual production data that is not known at confirmation
        time. The AM-003 board displays the placeholder line so the
        asset is not absent from the schedule view; AM-004 has a
        no-op for this asset until production lines are added.
        """
        self.ensure_one()
        start_date = self.depreciation_start_date or self.acquisition_date
        if not start_date:
            return
        self.write({
            'depreciation_line_ids': [
                Command.create({
                    'sequence': 1,
                    'depreciation_date': start_date,
                    'depreciation_amount': 0.0,
                }),
            ],
        })

    # =========================================================================
    # AM-004 CRON ENTRY POINT (CRITICAL -- batch / idempotent / fault-tolerant)
    # =========================================================================

    @api.model
    def _cron_post_depreciation_entries(self):
        """Post all due depreciation lines across all open assets.

        Invoked by the ``ir.cron`` record declared in
        ``data/depreciation_cron.xml`` (R-06 mandates XML cron, not a
        Python-level scheduler).

        Semantics
        ---------

        * **Batch** -- a single SQL search retrieves all open assets
          with at least one due draft depreciation line. The per-asset
          and per-line filtering uses Python ``filtered`` on the
          already-loaded recordsets to avoid N+1 queries.
        * **Idempotent** -- each line\'s ``action_post`` checks
          ``state == \'draft\'`` and is a no-op for posted /
          skipped lines (delegated to the depreciation-line model).
          Re-running the cron after a partial failure is therefore
          safe.
        * **Fault-tolerant** (AM-004 AC6) -- per-line ``UserError``
          (missing config, locked period, etc.) is caught and logged
          as a warning; per-asset ``Exception`` is caught and logged
          via ``_logger.exception`` so one asset\'s failure cannot
          abort the rest of the batch.
        * **Logged** (AM-004 AC5) -- emits structured INFO log records
          for cron start, cron completion, and counts of success /
          skipped / errored lines. WARNING for each skipped line.
          EXCEPTION for each errored asset.
        * **Auto-close** (AM-004 AC6 "Fully Depreciated Asset") --
          after posting an asset\'s due lines, if the resulting NBV
          is at or below ``salvage_value``, transitions the asset to
          ``state = \'close\'`` automatically.

        :return: a dict with three counters: ``success`` (lines
            posted), ``skipped`` (lines that raised ``UserError``),
            and ``errors`` (assets that raised non-``UserError``
            exceptions).
        :rtype: dict
        """
        today = fields.Date.context_today(self)
        # Locate every open asset with at least one due draft line.
        # The domain uses the One2many traversal ``depreciation_line_ids``
        # to filter by line state and date in a single SQL search.
        assets = self.search([
            ('state', '=', 'open'),
            ('depreciation_line_ids.state', '=', 'draft'),
            ('depreciation_line_ids.depreciation_date', '<=', today),
        ])
        _logger.info(
            'AM-004 cron starting: %d open asset(s) with due '
            'depreciation lines as of %s.',
            len(assets),
            today,
        )
        success_count = 0
        skip_count = 0
        error_count = 0
        for asset in assets:
            try:
                # Filter to the lines whose date is on or before
                # ``today`` and whose state is still ``draft``.
                # Sort by ``sequence`` so periods are posted in
                # chronological order (cumulative_depreciation and
                # net_book_value computations remain coherent).
                due_lines = asset.depreciation_line_ids.filtered(
                    lambda line: (
                        line.state == 'draft'
                        and line.depreciation_date
                        and line.depreciation_date <= today
                    ),
                ).sorted(key=lambda line: line.sequence)
                for line in due_lines:
                    try:
                        line.action_post()
                        success_count += 1
                    except UserError as exc:
                        # Recoverable per-line failure (missing
                        # config, locked period). Log at warning,
                        # increment skip counter, and continue with
                        # the next line in the same asset.
                        _logger.warning(
                            'AM-004: skipping depreciation line %s '
                            'for asset %s: %s',
                            line.id,
                            asset.display_name,
                            exc,
                        )
                        skip_count += 1
                # Auto-close fully depreciated assets (AM-004 AC6).
                # Use ``invalidate_recordset`` to force a fresh read
                # of the recently-recomputed NBV; otherwise the
                # in-memory cache may return the pre-post value.
                asset.invalidate_recordset(
                    fnames=[
                        'accumulated_depreciation',
                        'net_book_value',
                    ],
                )
                if asset.net_book_value <= asset.salvage_value:
                    asset.message_post(body=_(
                        'Asset fully depreciated; closing.',
                    ))
                    asset.action_close()
            except Exception:  # noqa: BLE001
                # Catch-all per-asset fault-tolerance per AM-004 AC6.
                # ``_logger.exception`` automatically captures the active
                # exception's type, message, and traceback, so we do NOT
                # pass the exception object as a positional argument
                # (ruff TRY401). Increment the error counter and
                # continue with the next asset.
                _logger.exception(
                    'AM-004: error processing asset %s.',
                    asset.display_name,
                )
                error_count += 1
        _logger.info(
            'AM-004 cron completed: success=%d, skipped=%d, '
            'errors=%d.',
            success_count,
            skip_count,
            error_count,
        )
        return {
            'success': success_count,
            'skipped': skip_count,
            'errors': error_count,
        }
