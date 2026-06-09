# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Asset Category Template Model (FEATURE-004, AM-001 AC3).

Implements ``account.asset.category`` — a template model that holds default
depreciation configuration and account assignments. Assets created in a
category inherit these defaults via the ``category_id`` onchange defined on
``account.asset`` (see ``account_asset.py`` in the same models package).

Per AM-001 Scenario 3 ("Assignment of asset to category with inherited default
settings"), values inherited from the category onto an asset CAN be overridden
on the individual asset instance. This model is therefore a passive TEMPLATE:
once the onchange/create copies values into the asset, the asset's own copy is
authoritative.

Per AM-002 Scenario 6 ("Configure asset category templates with default
depreciation settings"), the category carries default depreciation method,
useful life, salvage percentage, start-date option, and declining factor so
that assets of a similar type (e.g., "IT Equipment", "Vehicles", "Buildings")
share consistent policies without per-asset re-entry.

Per AM-004 Scenario 3 ("Draft versus auto-post configuration options"), the
category exposes an ``auto_post_depreciation`` toggle that the AM-004 cron
(``ir.cron`` XML record) inspects when deciding whether to post generated
entries immediately or leave them in draft for manual review.

Architectural posture:
- This is a pure LEAF model: no internal foreign keys to other models in the
  ``account_asset_management`` module. Importing this module file before
  ``account_asset.py`` in ``models/__init__.py`` is therefore SAFE — the
  forward One2many reference to ``account.asset`` is resolved lazily by the
  Odoo ORM registry at class-build time.
- Categories do NOT use ``mail.thread`` / ``mail.activity.mixin`` because
  chatter is required on individual assets (AM-001 Scenario 6) but not on
  template records. Keeping the category form lean avoids unnecessary UI
  noise for configuration screens.

Compliance with Agent Action Plan (AAP) Rules:
- R-01 (Module independence): NO ``import`` of ``account_budget_management``,
  ``account_deferred_revenue``, or ``account_payment_followup``. This file
  imports only from ``odoo`` and ``odoo.exceptions``.
- R-03 (``_inherit`` / ``_name`` correctness): Declares ``_name =
  'account.asset.category'`` for a NET-NEW model; no ``_inherit`` on any
  core Odoo model in this file.
- R-05 (No core-field redefinition): NOT APPLICABLE — this is a net-new
  standalone model, not an extension of ``account.move`` or
  ``account.move.line``.
- R-07 (No ``sudo()`` without justification): This file contains no
  ``.sudo()`` call; verified by grep.

Constraints enforced at the Python level (four ``@api.constrains`` guards):
1. ``_check_useful_life`` — useful life must be non-negative when method is
   straight-line or declining-balance (AM-002 Scenario 7).
2. ``_check_declining_factor`` — declining factor must be strictly positive
   when method is declining-balance (AM-002 Scenario 3 / 7).
3. ``_check_salvage_percent`` — salvage percent must be within [0, 100]
   (AM-002 Scenario 7; also enforced on the asset for salvage_value ≤ cost).
4. ``_check_units_total`` — expected total units must be non-negative when
   method is units-of-production (AM-002 Scenario 4 / 7).

Database-level uniqueness is enforced by a ``models.UniqueIndex`` on
``(code, company_id)``. The index uses PostgreSQL's native ``NULL != NULL``
semantics so categories with a NULL ``code`` are not constrained, matching
the AAP Key Insight for optional category codes.
"""

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AccountAssetCategory(models.Model):
    """Asset Category — template for default depreciation configuration.

    An asset category groups assets of similar type (e.g., "IT Equipment",
    "Vehicles", "Buildings") and provides the default depreciation method,
    useful life, salvage percentage, start-date option, and account
    assignments that individual assets inherit at creation time.

    The category is a LEAF model in ``account_asset_management``'s dependency
    graph: no fields on this model reference any other model defined in the
    same addon. This property makes the category safe to import first in the
    module's ``__init__.py``.

    Per AM-001 Scenario 3, values copied from the category onto an asset are
    overridable on the asset instance. The category itself is never the
    live source of per-asset values after record creation.
    """

    _name = 'account.asset.category'
    _description = 'Asset Category'
    _order = 'sequence, name'
    _check_company_auto = True

    # -------------------------------------------------------------------------
    # IDENTIFICATION
    # -------------------------------------------------------------------------

    name = fields.Char(
        string='Category Name',
        required=True,
        translate=True,
        help=(
            'Descriptive name of the asset category, e.g., "IT Equipment", '
            '"Vehicles", "Buildings". Displayed in asset lookup widgets and '
            'reports. Translatable for multi-locale deployments.'
        ),
    )

    code = fields.Char(
        string='Short Code',
        help=(
            'Optional short code for reporting and quick identification, '
            'e.g., "IT" for IT Equipment or "VEH" for Vehicles. When set, '
            'the code must be unique within the company (NULL values are '
            'not constrained — PostgreSQL NULL != NULL semantics).'
        ),
    )

    sequence = fields.Integer(
        default=10,
        help=(
            'Display ordering: categories with lower sequence values appear '
            'first in list views and category selection drop-downs.'
        ),
    )

    active = fields.Boolean(
        default=True,
        help=(
            'When unchecked, the category is archived and hidden from '
            'selection widgets on new assets. Existing assets tied to an '
            'archived category are unaffected (category is a template, not '
            'a live link).'
        ),
    )

    description = fields.Text(
        help=(
            'Optional free-form description, e.g., depreciation policy '
            'rationale, retention guidelines, or categorization notes. '
            'Not exposed in the depreciation calculation but useful for '
            'audit trails and onboarding new Accountants.'
        ),
    )

    # -------------------------------------------------------------------------
    # SCOPE
    # -------------------------------------------------------------------------

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        default=lambda self: self.env.company,
        index=True,
        help=(
            'Company to which the category applies. Leave empty to make the '
            'category available to all companies in a multi-company '
            'deployment (assets will still inherit their own company_id '
            'from the creation context, so cross-company linkage is not '
            'produced).'
        ),
    )

    # -------------------------------------------------------------------------
    # DEFAULT DEPRECIATION METHOD (AM-002 AC1-4, AC6)
    # -------------------------------------------------------------------------

    depreciation_method = fields.Selection(
        selection=[
            ('straight_line', 'Straight-Line'),
            ('declining_balance', 'Declining Balance'),
            ('units_of_production', 'Units of Production'),
        ],
        string='Default Method',
        default='straight_line',
        required=True,
        help=(
            'Default depreciation method copied onto new assets created in '
            'this category. Straight-line spreads cost evenly across useful '
            'life (AM-002 Scenario 1/2). Declining balance accelerates early '
            'periods using ``declining_factor`` (AM-002 Scenario 3). Units '
            'of production depreciates per unit produced (AM-002 Scenario 4).'
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
            'Unit in which the useful life is expressed. Years (annual '
            'schedule, AM-002 Scenario 1), months (monthly schedule, '
            'AM-002 Scenario 2), or units (production-based, AM-002 '
            'Scenario 4).'
        ),
    )

    useful_life_years = fields.Integer(
        string='Default Useful Life (Years)',
        default=0,
        help=(
            'Default useful life in years for assets created in this '
            'category. Used when ``useful_life_unit`` is "years"; ignored '
            'otherwise. Must be non-negative.'
        ),
    )

    useful_life_months = fields.Integer(
        string='Default Useful Life (Months)',
        default=0,
        help=(
            'Default useful life in months for assets created in this '
            'category. Used when ``useful_life_unit`` is "months"; ignored '
            'otherwise. Must be non-negative.'
        ),
    )

    declining_factor = fields.Float(
        string='Default Declining Factor',
        default=2.0,
        digits=(5, 2),
        help=(
            'Default multiplier applied to the straight-line rate when '
            '``depreciation_method`` is declining balance. A value of 2.0 '
            'yields double-declining-balance depreciation (the most '
            'common). Must be strictly positive when the declining-balance '
            'method is used.'
        ),
    )

    switch_to_straight_line = fields.Boolean(
        string='Switch to Straight-Line',
        default=False,
        help=(
            'When enabled in combination with the declining-balance method, '
            'the asset switches to straight-line once the remaining '
            'straight-line expense exceeds the declining-balance expense '
            '(AM-002 Scenario 3, optimal crossover point). Ignored for '
            'other depreciation methods.'
        ),
    )

    salvage_percent = fields.Float(
        string='Default Salvage Value (%)',
        default=0.0,
        digits=(5, 2),
        help=(
            'Default salvage (residual) value expressed as a percentage of '
            'acquisition cost (range 0.0 to 100.0). The asset onchange '
            'converts this percentage to an absolute ``salvage_value`` '
            'using the formula ``salvage_value = (salvage_percent / 100.0) '
            '* acquisition_cost``.'
        ),
    )

    units_production_total = fields.Float(
        string='Default Expected Units',
        default=0.0,
        help=(
            'Default total expected production units for the units-of-'
            'production method (AM-002 Scenario 4). Per-period depreciation '
            'is computed as ``actual_units * (acquisition_cost - salvage) / '
            'units_production_total``. Must be non-negative when the '
            'units-of-production method is used.'
        ),
    )

    start_date_option = fields.Selection(
        selection=[
            ('acquisition_date', 'Acquisition Date'),
            ('first_day_next_month', 'First Day of Next Month'),
            ('first_day_current_month', 'First Day of Current Month'),
            ('manual', 'Manual Date'),
        ],
        string='Default Start Date',
        default='acquisition_date',
        required=True,
        help=(
            'Default rule for deriving the depreciation start date on '
            'assets in this category (AM-002 Scenario 5). "Acquisition '
            'date" prorates from the acquisition. "First day of next/'
            'current month" aligns with month-end fiscal calendars. '
            '"Manual" lets the Accountant specify the date per asset.'
        ),
    )

    # -------------------------------------------------------------------------
    # DEFAULT ACCOUNT ASSIGNMENTS (AM-001 AC6)
    # -------------------------------------------------------------------------

    asset_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Default Asset Account',
        domain="[('account_type', '=', 'asset_fixed')]",
        check_company=True,
        help=(
            'Fixed-asset account (type ``asset_fixed``) inherited by assets '
            'in this category at creation. The ``check_company`` flag '
            'enforces multi-company isolation: ``account.account`` in '
            'Odoo 19.0 uses ``company_ids`` (Many2many) which is '
            'transparently checked by Odoo via the model-level '
            '``_check_company_auto = True`` setting.'
        ),
    )

    expense_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Default Depreciation Expense Account',
        domain="[('account_type', '=', 'expense_depreciation')]",
        check_company=True,
        help=(
            'Depreciation expense account (type ``expense_depreciation``) '
            'inherited by assets in this category. Debited by each AM-004 '
            'depreciation journal entry.'
        ),
    )

    accumulated_depreciation_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Default Accumulated Depreciation Account',
        domain="[('account_type', '=', 'asset_non_current')]",
        check_company=True,
        help=(
            'Accumulated depreciation (contra-asset) account inherited by '
            'assets in this category. Credited by each AM-004 depreciation '
            'journal entry. Typically a balance-sheet asset account that '
            'nets against ``asset_account_id`` for net book value.'
        ),
    )

    journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Default Depreciation Journal',
        domain="[('type', '=', 'general'), ('company_id', '=', company_id)]",
        check_company=True,
        help=(
            'Default general journal to which AM-004 depreciation entries '
            'for assets in this category are posted. Only journals of type '
            '"general" are eligible (miscellaneous / adjustment journal).'
        ),
    )

    # -------------------------------------------------------------------------
    # AM-004 AUTOMATION CONTROL
    # -------------------------------------------------------------------------

    auto_post_depreciation = fields.Boolean(
        string='Auto-Post Depreciation',
        default=False,
        help=(
            'Controls AM-004 cron behaviour for assets in this category. '
            'When TRUE, the scheduled action posts generated depreciation '
            'entries immediately (status "posted"). When FALSE (default — '
            'the safer choice per AM-004 Scenario 3), entries are created '
            'in "draft" status for manual review by an Accountant before '
            'they affect financial statements.'
        ),
    )

    # -------------------------------------------------------------------------
    # RELATED RECORDS
    # -------------------------------------------------------------------------

    asset_ids = fields.One2many(
        comodel_name='account.asset',
        inverse_name='category_id',
        string='Assets',
        help=(
            'All ``account.asset`` records currently assigned to this '
            'category. Populated through the ``category_id`` M2o on '
            'account.asset. Useful for reporting aggregate asset counts '
            'and for navigating from a category form to the list of '
            'assets that inherit its defaults.'
        ),
    )

    asset_count = fields.Integer(
        string='# Assets',
        compute='_compute_asset_count',
        help=(
            'Total number of assets currently assigned to this category. '
            'Used as a badge on list/kanban views and as a smart-button '
            'counter on the category form.'
        ),
    )

    # -------------------------------------------------------------------------
    # SQL CONSTRAINTS
    # -------------------------------------------------------------------------

    # Odoo 19 native uniqueness enforcement. The ``models.UniqueIndex`` is the
    # supported Odoo 19 mechanism that actually creates the PostgreSQL unique
    # index (see ``odoo/orm/table_objects.py::UniqueIndex``). The generated
    # database object is named ``account_asset_category_unique_code_per_company``.
    # PostgreSQL NULL != NULL semantics mean NULL ``code`` values are NOT
    # constrained — multiple categories without a code can coexist in the same
    # company, which matches the AAP Key Insight that ``code`` is OPTIONAL.
    _unique_code_per_company = models.UniqueIndex(
        '(code, company_id)',
        'Asset category code must be unique per company.',
    )

    # NOTE: The legacy ``_sql_constraints`` attribute has been removed in
    # favor of the Odoo 19 canonical ``models.UniqueIndex`` declaration
    # above (``_unique_code_per_company``). Keeping both produced a
    # deprecation warning at module load time; the canonical
    # ``UniqueIndex`` already creates the same PostgreSQL UNIQUE index
    # so removing the legacy attribute is safe and eliminates the
    # warning. See addons/account_asset_management code review feedback
    # (Checkpoint 8) for the rationale.

    # -------------------------------------------------------------------------
    # COMPUTE METHODS
    # -------------------------------------------------------------------------

    @api.depends('asset_ids')
    def _compute_asset_count(self):
        """Compute the number of assets assigned to each category.

        Trivially counts the reverse One2many ``asset_ids``. Recomputed
        whenever an asset's ``category_id`` changes or when a new asset is
        created/deleted, via the standard Odoo dependency-inversion
        mechanism on the ``asset_ids`` recordset.
        """
        for category in self:
            category.asset_count = len(category.asset_ids)

    # -------------------------------------------------------------------------
    # PYTHON CONSTRAINTS (AM-002 AC7)
    # -------------------------------------------------------------------------

    @api.constrains(
        'useful_life_years',
        'useful_life_months',
        'depreciation_method',
        'useful_life_unit',
    )
    def _check_useful_life(self):
        """Validate useful life is non-negative and coherent with the method.

        Per AM-002 Scenario 7, for straight-line and declining-balance
        methods the useful life must be non-negative; a zero useful life is
        permitted on the category template (asset-level validation will
        enforce a strictly-positive useful life at confirmation time when
        the method requires periodic computation). The units-of-production
        method is validated separately in ``_check_units_total``.
        """
        for category in self:
            if category.depreciation_method in ('straight_line', 'declining_balance'):
                if category.useful_life_unit == 'years' and category.useful_life_years < 0:
                    raise ValidationError(
                        _(
                            'Useful life in years cannot be negative '
                            'for category "%s".',
                            category.name,
                        ),
                    )
                if category.useful_life_unit == 'months' and category.useful_life_months < 0:
                    raise ValidationError(
                        _(
                            'Useful life in months cannot be negative '
                            'for category "%s".',
                            category.name,
                        ),
                    )

    @api.constrains('declining_factor', 'depreciation_method')
    def _check_declining_factor(self):
        """Ensure declining factor is strictly positive for declining-balance.

        Per AM-002 Scenario 3 and Scenario 7, the declining-balance method
        requires a strictly-positive factor (e.g., 1.5x, 2.0x, 2.5x). A
        zero or negative factor would produce no depreciation or negative
        depreciation, both nonsensical. For straight-line and units-of-
        production methods, the field is ignored and this check is a no-op.
        """
        for category in self:
            if (
                category.depreciation_method == 'declining_balance'
                and category.declining_factor <= 0
            ):
                raise ValidationError(
                    _(
                        'Declining factor must be > 0 for category "%s" '
                        '(declining balance method).',
                        category.name,
                    ),
                )

    @api.constrains('salvage_percent')
    def _check_salvage_percent(self):
        """Clamp salvage percent within the closed interval [0, 100].

        Per AM-002 Scenario 7, salvage value cannot exceed acquisition
        cost (which translates to 100% at the template level) and cannot
        be negative. Enforced for all methods because the template applies
        uniformly regardless of the downstream depreciation calculation.
        """
        for category in self:
            if category.salvage_percent < 0 or category.salvage_percent > 100:
                raise ValidationError(
                    _(
                        'Salvage percent must be between 0 and 100 for '
                        'category "%s" (got %.2f).',
                        category.name,
                        category.salvage_percent,
                    ),
                )

    @api.constrains('units_production_total', 'depreciation_method')
    def _check_units_total(self):
        """Validate total expected units is non-negative for units-of-production.

        Per AM-002 Scenario 4 and Scenario 7, the units-of-production
        method requires a non-negative total expected units figure. A zero
        total is allowed at the template level (the asset-level validation
        will enforce a strictly-positive total at confirmation time).
        Ignored for other methods.
        """
        for category in self:
            if (
                category.depreciation_method == 'units_of_production'
                and category.units_production_total < 0
            ):
                raise ValidationError(
                    _(
                        'Total expected units must be >= 0 for category '
                        '"%s".',
                        category.name,
                    ),
                )
