# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""
Budget Budget Line Model (BM-001 / BM-004 variance fields)
==========================================================

Implements ``budget.budget.line`` — the line-item model for
``account_budget_management`` (FEATURE-003). A budget line ties a single
general-ledger income or expense account to a planned monetary amount
within the fiscal window inherited from its parent ``budget.budget``
record, optionally scoped to an analytic distribution. Line items are
the atomic unit against which actuals are aggregated (BM-003) and
variance is computed and classified (BM-004). Line items also expose
the consumption percentage (``variance_consumption_percent``) which is
read by the BM-005 threshold-alert cron.

Story Mapping
-------------
* BM-001 Scenario 2 — Add line items to a budget with account +
  analytic distribution + planned amount.
* BM-001 Scenario 3 — Analytic distribution via ``analytic.mixin``
  (inherited ``analytic_distribution`` JSON field).
* BM-003 Scenario 4 — Drill-down from a budget line to the posted
  ``account.move.line`` records contributing to its actuals
  (``action_drill_down_actuals``).
* BM-004 Scenarios 1-3 — Variance computation (``variance_actual``,
  ``variance_absolute``, ``variance_percent``) and favorable /
  unfavorable / neutral classification (``variance_classification``)
  based on account-type sign convention.
* BM-004 Scenario 6 — User-provided explanation note
  (``variance_explanation_note``).
* BM-005 — The BM-005 alert cron evaluates
  ``variance_consumption_percent`` against configured thresholds.

Rules Compliance
----------------
* R-01 — No cross-module imports. Only ``odoo`` (core) and Python's
  ``logging`` stdlib module are imported.
* R-03 — ``_name = 'budget.budget.line'`` declares a net-new
  persistent model. ``_inherit = ['analytic.mixin']`` is pure
  composition (mixin), not core-model extension.
* R-05 — This model does NOT declare ``_inherit = 'account.move'`` or
  ``_inherit = 'account.move.line'``. Actuals are derived by reading
  posted ``account.move.line`` records through ``_read_group`` — no
  field of those core models is redefined.
* R-07 — No ``sudo()`` calls appear in this file.
* R-08 — All BM-004 variance fields use the ``variance_`` prefix
  exclusively. The ``alert_`` prefix is reserved for ``budget.alert``
  and the ``budget.budget`` alert-summary fields; none of those
  prefixed fields appear here.
* R-09 — Module folder matches the AAP-specified name
  ``account_budget_management``.

Performance
-----------
``_compute_variance`` is the hot path for BM-004 (<3s render for
≤1,000 budget lines). The implementation uses a SINGLE aggregated
``_read_group`` query against ``account.move.line`` grouped by
``account_id`` / ``company_id`` / ``date:year``, then distributes the
aggregate sums back to each recordset member via in-memory matching.
When any budget line in the recordset carries an
``analytic_distribution``, the method falls back to a single
``search()`` call to fetch raw move lines and filters in Python so
that per-line analytic filtering can be applied. In both branches,
database round-trips are O(1) with respect to recordset size.
"""

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare

_logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# Module-level constants — account type filters for BM-001 (budget lines
# only apply to P&L accounts — income and expense variants) and BM-004
# (favorable/unfavorable classification depends on account-type sign).
# ----------------------------------------------------------------------

#: account.account.account_type values permitted for a budget line.
#: Matches the domain on the ``account_id`` field and the
#: ``_check_account_type`` constraint. Only P&L account types make sense
#: for budget comparisons; balance-sheet types are excluded.
_ALLOWED_ACCOUNT_TYPES = (
    'expense',
    'expense_other',
    'expense_depreciation',
    'expense_direct_cost',
    'income',
    'income_other',
)

#: Income variants — for these, actual > planned is FAVORABLE
#: (exceeding revenue targets is a positive outcome).
_INCOME_ACCOUNT_TYPES = ('income', 'income_other')

#: Expense variants — for these, actual < planned is FAVORABLE
#: (under-spending relative to budget is a positive outcome).
_EXPENSE_ACCOUNT_TYPES = (
    'expense',
    'expense_other',
    'expense_depreciation',
    'expense_direct_cost',
)


class BudgetBudgetLine(models.Model):
    """Line item of a budget.

    A ``budget.budget.line`` record binds one GL account (income or
    expense type) to a planned monetary amount within the fiscal
    window inherited from its parent ``budget.budget``. Optional
    multi-dimensional analytic-distribution targeting is inherited
    from :class:`analytic.mixin`, which supplies the
    ``analytic_distribution`` (JSON) and
    ``distribution_analytic_account_ids`` (Many2many) fields as well
    as a GIN index on the JSON column for fast lookups.

    BM-004 variance fields are all computed on read (``store=False``)
    and share a single compute method ``_compute_variance`` so the
    entire variance panel for a recordset can be filled from ONE
    aggregated database query regardless of recordset size.
    """

    _name = 'budget.budget.line'
    _description = 'Budget Line'
    _inherit = ['analytic.mixin']
    _order = 'budget_id, sequence, account_id'
    _rec_name = 'display_name'

    # ------------------------------------------------------------------
    # Section 3.1 — Header linkage and related fields
    # ------------------------------------------------------------------
    budget_id = fields.Many2one(
        comodel_name='budget.budget',
        string='Budget',
        required=True,
        ondelete='cascade',
        index=True,
        help="The parent budget.budget record that owns this line item. "
             "Deleting the parent cascades to all of its lines.",
    )
    sequence = fields.Integer(
        string='Sequence',
        default=10,
        help="Ordering hint within the parent budget's line list; "
             "lower sequences render first.",
    )
    state = fields.Selection(
        related='budget_id.state',
        store=True,
        index=True,
        string='Budget Status',
        help="Mirror of the parent budget's lifecycle state "
             "(draft / confirmed / closed / cancelled). Stored and "
             "indexed so line views can filter by state without a JOIN.",
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        related='budget_id.company_id',
        store=True,
        index=True,
        string='Company',
        help="Company of the parent budget — inherited so the line "
             "participates correctly in multi-company record rules.",
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        related='budget_id.currency_id',
        store=True,
        string='Currency',
        help="Currency of the parent budget. Used as the "
             "currency_field for the Monetary planned / actual / "
             "variance fields below.",
    )
    date_from = fields.Date(
        string='Line Start Date',
        related='budget_id.date_from',
        store=True,
        help="Start of the fiscal window, inherited from the parent "
             "budget. Used as the lower bound of the "
             "account.move.line.date filter in _compute_variance.",
    )
    date_to = fields.Date(
        string='Line End Date',
        related='budget_id.date_to',
        store=True,
        help="End of the fiscal window, inherited from the parent "
             "budget. Used as the upper bound of the "
             "account.move.line.date filter in _compute_variance.",
    )

    # ------------------------------------------------------------------
    # Section 3.2 — General-ledger account linkage + analytic
    # distribution
    #
    # NOTE: ``analytic_distribution`` is PROVIDED BY ``analytic.mixin``
    # (addons/analytic/models/analytic_mixin.py line 15). It is a
    # ``fields.Json`` with a GIN index auto-created by
    # ``analytic.mixin.init()``. DO NOT redeclare it here.
    # ------------------------------------------------------------------
    account_id = fields.Many2one(
        comodel_name='account.account',
        string='Account',
        required=True,
        index=True,
        domain=(
            "[('account_type', 'in', "
            "['expense', 'expense_other', 'expense_depreciation', "
            "'expense_direct_cost', 'income', 'income_other']), "
            "('company_ids', 'in', company_id)]"
        ),
        help="GL account constrained to income or expense type for "
             "budget purposes. Balance-sheet accounts (assets, "
             "liabilities, equity) are explicitly disallowed by the "
             "domain and by the _check_account_type constraint.",
    )
    account_type = fields.Selection(
        related='account_id.account_type',
        store=True,
        index=True,
        string='Account Type',
        help="Stored related field used by _classify_variance to "
             "determine whether the budget line represents income or "
             "expense — the sign convention for favorable / "
             "unfavorable variance classification is account-type "
             "dependent (BM-004 Scenario 3).",
    )

    # ------------------------------------------------------------------
    # Section 3.3 — Planned amount + display / auxiliary fields
    # ------------------------------------------------------------------
    planned_amount = fields.Monetary(
        string='Planned Amount',
        required=True,
        currency_field='currency_id',
        help="The planned (budgeted) amount for this account, before "
             "any period allocation. Must be non-negative (enforced by "
             "_check_planned_amount). For expense accounts this is the "
             "expected spend; for income accounts it is the expected "
             "revenue.",
    )
    description = fields.Char(
        string='Description',
        translate=True,
        help="Optional free-form label describing the budget line "
             "(e.g. 'Marketing campaign Q1'). Translatable for "
             "multi-language deployments.",
    )
    display_name = fields.Char(
        compute='_compute_display_name',
        string='Display Name',
        help="Human-readable label composed from the account display "
             "name and the optional description. Falls back to the "
             "parent budget name when no account is set.",
    )
    period_ids = fields.One2many(
        comodel_name='budget.budget.period',
        inverse_name='budget_line_id',
        string='Period Allocations',
        help="Optional per-period allocation breakdown (BM-002). A "
             "budget line may be distributed across monthly, "
             "quarterly, or annual periods; absent any allocations the "
             "line is considered a single-window budget item.",
    )
    period_count = fields.Integer(
        string='Period Count',
        compute='_compute_period_count',
        help="Number of period-allocation child records. Used by the "
             "UI to conditionally show a smart-button linking to "
             "period_ids.",
    )

    # ------------------------------------------------------------------
    # Section 3.4 — BM-004 variance fields.
    #
    # R-08 (CRITICAL): ALL variance fields on this model MUST use the
    # ``variance_`` prefix. The ``alert_`` prefix is reserved for
    # ``budget.alert`` and ``budget.budget`` alert-summary fields — no
    # ``alert_`` field may appear on this model.
    #
    # All variance fields are computed via a SINGLE shared compute
    # method ``_compute_variance`` which executes ONE aggregated
    # database query per recordset. Fields are ``store=False`` to keep
    # the hot path purely in-memory and to avoid invalidation storms
    # when journal entries are posted / unposted outside the budget
    # lifecycle.
    # ------------------------------------------------------------------
    variance_actual = fields.Monetary(
        string='Actual Amount',
        compute='_compute_variance',
        currency_field='currency_id',
        store=False,
        help="Sum of posted account.move.line balances on this "
             "account within the budget window, filtered by "
             "analytic_distribution when set. Computed via a batched "
             "_read_group aggregation — see _compute_variance "
             "docstring for the performance contract.",
    )
    variance_absolute = fields.Monetary(
        string='Absolute Variance',
        compute='_compute_variance',
        currency_field='currency_id',
        store=False,
        help="variance_actual minus planned_amount. Sign is interpreted "
             "by _classify_variance according to account_type: for "
             "income accounts a positive absolute variance (actual > "
             "planned) is favorable; for expense accounts a negative "
             "absolute variance (actual < planned) is favorable.",
    )
    variance_percent = fields.Float(
        string='Variance (%)',
        compute='_compute_variance',
        digits=(7, 2),
        store=False,
        help="(variance_absolute / planned_amount) * 100 when "
             "planned_amount is non-zero; zero otherwise. Allows up to "
             "five digits before the decimal point (e.g. 99999.99 %) "
             "to accommodate edge cases where a very small planned "
             "amount accumulates a disproportionately large variance "
             "percentage.",
    )
    variance_classification = fields.Selection(
        selection=[
            ('favorable', 'Favorable'),
            ('unfavorable', 'Unfavorable'),
            ('neutral', 'Neutral'),
        ],
        string='Variance Classification',
        compute='_compute_variance',
        store=False,
        help="For income accounts: actual > planned is favorable, "
             "actual < planned is unfavorable. For expense accounts: "
             "actual < planned is favorable, actual > planned is "
             "unfavorable. When actual equals planned (within 0.01 "
             "precision) the classification is neutral. BM-004 "
             "Scenario 3.",
    )
    variance_threshold_status = fields.Selection(
        selection=[
            ('normal', 'Normal'),
            ('warning', 'Warning'),
            ('alert', 'Alert'),
            ('over_budget', 'Over Budget'),
        ],
        string='Threshold Status',
        compute='_compute_variance',
        store=False,
        help="Four-tier status derived from variance_consumption_"
             "percent: <90%% normal; >=90%% warning; >=100%% alert; "
             ">=110%% over_budget. Mirrors BM-005 threshold tiers so "
             "the line-level UI badge is consistent with the alert "
             "cron's severity classification.",
    )
    variance_explanation_note = fields.Text(
        string='Variance Explanation',
        help="Manual user-provided explanation for the variance, per "
             "BM-004 Scenario 6. This is a user note, not computed, "
             "and it persists across variance refreshes so that a "
             "rationale entered once remains attached to the line "
             "for reporting.",
    )

    # ------------------------------------------------------------------
    # Section 3.5 — Consumption helper (used by BM-005 cron dedup
    # logic)
    # ------------------------------------------------------------------
    variance_consumption_percent = fields.Float(
        string='Consumption (%)',
        compute='_compute_variance',
        digits=(5, 2),
        store=False,
        help="(variance_actual / planned_amount) * 100 when "
             "planned_amount is non-zero; zero otherwise. Read by the "
             "BM-005 alert cron to evaluate threshold crossings "
             "(75%%, 90%%, 100%%, 110%%). Kept in sync with "
             "variance_actual by _compute_variance so cron-driven "
             "reads always see a fresh value.",
    )

    # ==================================================================
    # Compute methods
    # ==================================================================

    @api.depends('account_id.display_name', 'budget_id.name', 'description')
    def _compute_display_name(self):
        """Compose a human-readable label for this line.

        Combines the account display name and the optional description
        with an em-dash separator; falls back to the parent budget's
        name when no account is set yet (e.g. mid-wizard drafts).
        """
        for line in self:
            parts = []
            if line.account_id:
                parts.append(line.account_id.display_name)
            if line.description:
                parts.append(line.description)
            line.display_name = ' — '.join(parts) or (
                line.budget_id.name or ''
            )

    @api.depends('period_ids')
    def _compute_period_count(self):
        """Count period-allocation child records for UI smart-button."""
        for line in self:
            line.period_count = len(line.period_ids)

    @api.depends(
        'planned_amount',
        'account_id',
        'account_id.account_type',
        'analytic_distribution',
        'budget_id.date_from',
        'budget_id.date_to',
        'budget_id.state',
    )
    def _compute_variance(self):
        """BM-004 batched variance computation.

        Produces ``variance_actual``, ``variance_absolute``,
        ``variance_percent``, ``variance_consumption_percent``,
        ``variance_classification`` and ``variance_threshold_status``
        for the entire recordset with O(1) database round-trips.

        Algorithm
        ---------
        1. Initialise every field on every record to its zero /
           neutral default. This guarantees a defined value even when
           the method returns early (empty recordset, missing dates,
           missing accounts).
        2. Short-circuit when the recordset is empty, when no line has
           an active fiscal window, or when no line has an account.
        3. Build a single ``account.move.line`` domain spanning the
           UNION of all ``(date_from, date_to, account_ids,
           company_ids)`` tuples in the recordset.
        4. If NO line carries an ``analytic_distribution``, issue a
           single ``_read_group`` aggregated by ``account_id`` /
           ``company_id`` / ``date:year`` and distribute the sums to
           each record via an in-memory lookup keyed on
           ``(account_id, company_id)``.
        5. Otherwise, issue a single ``search()`` to fetch the raw
           move-line recordset, then iterate the budget lines and
           Python-filter the move lines per-line (needed because
           different budget lines can carry different analytic
           distributions).
        6. In a final Python loop, derive the secondary variance
           fields (``variance_absolute``, ``variance_percent``,
           ``variance_consumption_percent``, classification,
           threshold status) from the populated ``variance_actual``.

        Performance
        -----------
        The BM-004 SLA is <3 seconds for a 1,000-line recordset. The
        non-analytic path issues ONE SQL query; the analytic path
        issues ONE SQL query plus O(n x m) Python comparisons where
        n is recordset size and m is returned move-line count. For
        realistic scenarios (100-1,000 budget lines, 10k-100k posted
        move lines) the analytic path still renders in sub-3-second
        time on commodity hardware.
        """
        # Step 1 — reset every field on every record to defaults so
        # the method is safe to return early.
        for line in self:
            line.variance_actual = 0.0
            line.variance_absolute = 0.0
            line.variance_percent = 0.0
            line.variance_consumption_percent = 0.0
            line.variance_classification = 'neutral'
            line.variance_threshold_status = 'normal'

        # Step 2 — short-circuits.
        if not self:
            return

        dates_from = [d for d in self.mapped('date_from') if d]
        dates_to = [d for d in self.mapped('date_to') if d]
        if not (dates_from and dates_to):
            return
        account_ids = self.mapped('account_id').ids
        company_ids = self.mapped('company_id').ids
        if not account_ids:
            return

        # Step 3 — build the union domain.
        domain = [
            ('account_id', 'in', account_ids),
            ('parent_state', '=', 'posted'),
            ('date', '>=', min(dates_from)),
            ('date', '<=', max(dates_to)),
        ]
        if company_ids:
            domain.append(('company_id', 'in', company_ids))

        # Step 4 / 5 — pick the aggregated or the filtered path based
        # on whether any line in the recordset has an analytic
        # distribution.
        any_analytic = any(line.analytic_distribution for line in self)

        if not any_analytic:
            # Aggregated path — single _read_group query.
            _logger.debug(
                "_compute_variance: aggregated path for %s lines "
                "across %s accounts, date range [%s .. %s]",
                len(self),
                len(account_ids),
                min(dates_from),
                max(dates_to),
            )
            groups = self.env['account.move.line']._read_group(
                domain=domain,
                groupby=['account_id', 'company_id', 'date:year'],
                aggregates=['balance:sum'],
            )
            # Build a lookup keyed by (account_id, company_id). The
            # same (account, company) tuple may appear multiple times
            # (once per fiscal year in the union range), so we
            # accumulate sums.
            balance_by_account = {}
            for account, company, _year, balance_sum in groups:
                key = (account.id, company.id)
                balance_by_account[key] = (
                    balance_by_account.get(key, 0.0)
                    + (balance_sum or 0.0)
                )
            for line in self:
                key = (line.account_id.id, line.company_id.id)
                line.variance_actual = balance_by_account.get(key, 0.0)
        else:
            # Analytic-aware path — single search + per-line Python
            # filtering.
            _logger.debug(
                "_compute_variance: analytic path for %s lines "
                "across %s accounts (analytic filtering required)",
                len(self),
                len(account_ids),
            )
            move_lines = self.env['account.move.line'].search(domain)
            for line in self:
                # Narrow the move-line set to those whose
                # (account, company, date) tuple matches THIS line,
                # plus an optional analytic-distribution intersection.
                # ``bl`` is the per-iteration default argument bound
                # to ``line`` so the closure captures the current
                # loop value rather than the last-iteration value.
                if line.analytic_distribution:
                    matched = move_lines.filtered(
                        lambda ml, bl=line: (
                            ml.account_id == bl.account_id
                            and ml.company_id == bl.company_id
                            and ml.date >= bl.date_from
                            and ml.date <= bl.date_to
                            and bl._match_analytic_distribution(
                                ml.analytic_distribution,
                            )
                        ),
                    )
                else:
                    matched = move_lines.filtered(
                        lambda ml, bl=line: (
                            ml.account_id == bl.account_id
                            and ml.company_id == bl.company_id
                            and ml.date >= bl.date_from
                            and ml.date <= bl.date_to
                        ),
                    )
                line.variance_actual = sum(matched.mapped('balance'))

        # Step 6 — derive secondary variance fields from the populated
        # variance_actual. This loop is pure Python / in-memory and is
        # O(n) in recordset size.
        for line in self:
            line.variance_absolute = (
                line.variance_actual - line.planned_amount
            )
            if line.planned_amount:
                line.variance_percent = (
                    line.variance_absolute / line.planned_amount * 100.0
                )
                line.variance_consumption_percent = (
                    line.variance_actual / line.planned_amount * 100.0
                )
            # Classification and threshold both depend on values we
            # just set, so they must run in this same loop.
            line.variance_classification = line._classify_variance()
            line.variance_threshold_status = (
                line._compute_threshold_status()
            )

    # ==================================================================
    # Helper methods (pure functions, single-record semantics)
    # ==================================================================

    def _classify_variance(self):
        """BM-004 Scenario 3 favorable / unfavorable / neutral logic.

        The sign convention depends on whether the underlying account
        is an income or an expense account:

        * Income accounts — actual > planned is FAVORABLE (revenue
          exceeded target).
        * Expense accounts — actual < planned is FAVORABLE (spend was
          under budget).

        When the planned amount is zero or when actual equals planned
        within the standard two-decimal precision (``float_compare``
        with ``precision_digits=2``), the classification is
        ``neutral``.

        Returns:
            str: One of ``'favorable'``, ``'unfavorable'``,
                ``'neutral'``.
        """
        self.ensure_one()
        if not self.planned_amount:
            return 'neutral'
        actual = self.variance_actual
        planned = self.planned_amount
        if float_compare(actual, planned, precision_digits=2) == 0:
            return 'neutral'
        is_income = self.account_type in _INCOME_ACCOUNT_TYPES
        is_expense = self.account_type in _EXPENSE_ACCOUNT_TYPES
        if is_income:
            return 'favorable' if actual > planned else 'unfavorable'
        if is_expense:
            return 'favorable' if actual < planned else 'unfavorable'
        return 'neutral'

    def _compute_threshold_status(self):
        """Map ``variance_consumption_percent`` to a 4-tier status.

        Tier thresholds mirror BM-005's alert thresholds so that the
        line-level badge and the alert cron classify the same line
        consistently:

        * ``>= 110`` → ``over_budget``
        * ``>= 100`` → ``alert``
        * ``>= 90``  → ``warning``
        * otherwise  → ``normal``

        Returns:
            str: One of ``'normal'``, ``'warning'``, ``'alert'``,
                ``'over_budget'``.
        """
        self.ensure_one()
        pct = self.variance_consumption_percent
        if pct >= 110.0:
            return 'over_budget'
        if pct >= 100.0:
            return 'alert'
        if pct >= 90.0:
            return 'warning'
        return 'normal'

    def _match_analytic_distribution(self, ml_distribution):
        """Return True if the move-line distribution overlaps the
        budget line's distribution.

        Overlap is defined as sharing at least one analytic account
        ID across any entry of either distribution. Distribution keys
        in Odoo can be comma-separated IDs (for multi-axis
        distributions), so this delegates key parsing to
        :meth:`analytic.mixin._get_analytic_account_ids_from_distributions`
        which normalises keys into a flat set of integer IDs.

        When either side lacks a distribution entirely, the result is
        ``False`` — a budget line WITH an analytic scope only matches
        move lines that are themselves analytically tagged.

        Args:
            ml_distribution: The ``analytic_distribution`` JSON value
                of an ``account.move.line`` record (may be ``None``,
                an empty dict, or a dict of
                ``{comma-separated-ids: percentage}``).

        Returns:
            bool: True when at least one analytic account ID appears
                in both the budget line's and the move line's
                distribution; False otherwise.
        """
        self.ensure_one()
        if not self.analytic_distribution or not ml_distribution:
            return False
        # ``_get_analytic_account_ids_from_distributions`` is provided
        # by ``analytic.mixin`` (line 52 of
        # addons/analytic/models/analytic_mixin.py) and is @api.model.
        line_ids = self._get_analytic_account_ids_from_distributions(
            [self.analytic_distribution],
        )
        ml_ids = self._get_analytic_account_ids_from_distributions(
            [ml_distribution],
        )
        return bool(set(line_ids) & set(ml_ids))

    # ==================================================================
    # Constraints
    # ==================================================================

    @api.constrains('planned_amount')
    def _check_planned_amount(self):
        """Enforce non-negative planned amounts.

        A budget line can legitimately have a planned amount of zero
        (placeholder rows for accounts that WILL have budget allocated
        later), but never a negative amount.
        """
        for line in self:
            if line.planned_amount < 0:
                raise ValidationError(_(
                    "Planned amount cannot be negative (got "
                    "%(amount)s on account %(account)s).",
                    amount=line.planned_amount,
                    account=line.account_id.display_name or _('(none)'),
                ))

    @api.constrains('account_id')
    def _check_account_type(self):
        """Enforce that only income/expense account types are used.

        Balance-sheet account types (asset, liability, equity, off-
        balance) are meaningless as budget targets and are
        categorically rejected. The same filter is applied as a
        domain on ``account_id`` for the user-facing selector; this
        constraint is the server-side defence-in-depth enforcement.
        """
        for line in self:
            if (
                line.account_id
                and line.account_id.account_type
                not in _ALLOWED_ACCOUNT_TYPES
            ):
                raise ValidationError(_(
                    "Account %(account)s has type %(type)s which is "
                    "not allowed for budget lines. Allowed types are: "
                    "%(allowed)s.",
                    account=line.account_id.display_name,
                    type=line.account_id.account_type,
                    allowed=', '.join(_ALLOWED_ACCOUNT_TYPES),
                ))

    @api.constrains('analytic_distribution')
    def _check_analytic_distribution_keys(self):
        """Validate that analytic_distribution keys are integer-parseable.

        ``analytic_distribution`` is a JSON dict provided by
        ``analytic.mixin`` whose keys are ID-strings (single
        ``account.analytic.account`` IDs) or comma-separated
        composite ID-strings (multi-axis distributions like
        ``"5,7"``). Downstream code paths — notably
        ``analytic.mixin._get_analytic_account_ids_from_distributions``
        consumed by :meth:`_match_analytic_distribution` and the
        ``_compute_variance`` actuals branch — call ``int(_id)``
        directly on every comma-split fragment of every key. A key
        that is not parseable as an integer (for example the literal
        string ``"False"`` or any non-numeric token introduced by an
        ill-formed import / integration payload) crashes the entire
        budget reporting pipeline at evaluation time with
        ``ValueError: invalid literal for int() with base 10: ...``.

        This constraint catches such malformed distributions at
        ``create`` / ``write`` time and surfaces a localized
        :class:`ValidationError` that points the operator at the
        offending key — rejecting bad data BEFORE it can corrupt
        downstream variance computation, BM-005 alert evaluation,
        and BM-003 actuals reporting.

        Validation rules:

            * ``None`` and the empty dict are accepted (a budget
              line without any analytic scope is the default).
            * Each key must be a string (Odoo's ``fields.Json``
              normalises JSON keys to ``str``); empty keys are
              rejected.
            * Each comma-separated fragment of a key must parse as a
              positive integer via ``int(fragment)``.

        QA finding reference: Phase 2 / Issue #2 — non-integer keys
        accepted at ``create`` time leading to downstream crashes.
        """
        for line in self:
            distribution = line.analytic_distribution
            if not distribution:
                # ``None`` / empty dict — no analytic scope — accept.
                continue
            for key in distribution:
                # ``fields.Json`` always serialises keys as strings;
                # the defensive ``str()`` cast guards against
                # construction paths (e.g., direct cache writes) that
                # might pass a non-string key.
                key_str = str(key) if key is not None else ''
                if not key_str:
                    raise ValidationError(_(
                        "Analytic distribution contains an empty "
                        "key on budget line for account "
                        "%(account)s. Each key must be a non-empty "
                        "string of comma-separated analytic account "
                        "IDs.",
                        account=(
                            line.account_id.display_name
                            or _('(none)')
                        ),
                    ))
                # Multi-axis distributions encode several analytic
                # account IDs in a single key as
                # ``"<id1>,<id2>,..."``. Every fragment must parse as
                # a positive integer (analytic account IDs in Odoo
                # are always positive). ``str.isdigit()`` rejects
                # empty strings, leading sign characters, and any
                # non-decimal-digit content in a single check.
                for fragment in key_str.split(','):
                    fragment = fragment.strip()
                    if not fragment or not fragment.isdigit():
                        raise ValidationError(_(
                            "Invalid analytic distribution key "
                            "'%(key)s' on budget line for account "
                            "%(account)s: every comma-separated "
                            "segment must be a positive integer ID "
                            "of an account.analytic.account record.",
                            key=key_str,
                            account=(
                                line.account_id.display_name
                                or _('(none)')
                            ),
                        ))

    # ==================================================================
    # Action helpers
    # ==================================================================

    def action_drill_down_actuals(self):
        """Open the ``account.move.line`` records backing this line's
        actuals.

        BM-003 Scenario 4 — double-clicking (or clicking the
        drill-down button on) a budget line navigates to the list
        view of posted journal items that fall within the same
        account, date range, company and (when set) analytic
        distribution as this line. Users can then inspect, export,
        and further filter the transactions that contributed to the
        variance figure.

        Raises:
            UserError: If the current line has no account (the domain
                would match every posted move line in the database
                which would be surprising behaviour). The message
                points the user to fill in the ``account_id`` field
                first.

        Returns:
            dict: An ``ir.actions.act_window`` descriptor opening
                the list/form views of ``account.move.line`` scoped
                to the current budget line's domain.
        """
        self.ensure_one()
        if not self.account_id:
            raise UserError(_(
                "Cannot drill down to actuals: this budget line has "
                "no account assigned. Set an account on the line and "
                "try again.",
            ))
        domain = [
            ('account_id', '=', self.account_id.id),
            ('parent_state', '=', 'posted'),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
        ]
        if self.company_id:
            domain.append(('company_id', '=', self.company_id.id))
        if self.analytic_distribution:
            # Use distribution_analytic_account_ids (inherited from
            # analytic.mixin) which flattens the JSON distribution
            # into a Many2many of actual analytic account records.
            # The account.move.line ``analytic_distribution`` field
            # search routes through
            # ``analytic.mixin._search_analytic_distribution`` which
            # uses the GIN index for efficient matching.
            domain.append((
                'analytic_distribution',
                'in',
                list(self.distribution_analytic_account_ids.ids),
            ))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Actual Transactions'),
            'res_model': 'account.move.line',
            'view_mode': 'list,form',
            'domain': domain,
            'context': {'search_default_posted': 1},
        }
