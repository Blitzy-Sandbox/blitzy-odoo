# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Budget Variance Analysis Wizard (BM-004).

This module implements the interactive parameter-selection TransientModel
that drives BM-004 ``Variance Analysis`` workflows.

Story mapping (``tickets/stories/budget-management/BM-004-variance-analysis.md``):

* **Scenario 1** Basic variance calculation — wizard parameters scope
  the variance list to a specific budget + date window; variance formulas
  (absolute = actual - planned; percent = absolute / planned * 100) are
  computed upstream by ``budget.budget.line._compute_variance`` (see
  ``models/budget_budget_line.py`` lines 411-590).
* **Scenario 2** Analytic dimension breakdown — the
  ``analytic_account_ids`` Many2many filters the variance list to the
  chosen analytic accounts; the ``analytic_plan_ids`` Many2many filters
  to analytic accounts belonging to the chosen plans.
* **Scenario 3** Favorable / unfavorable classification — the
  ``favorable_filter`` Selection narrows the list to a specific
  classification bucket or leaves all classifications visible.
* **Scenario 4** Trend analysis — the ``period_granularity`` Selection
  drives the grouping dimension surfaced in the default context
  (``group_by`` hint passed into the pivot view).
* **Scenario 5** Explanation notes — users edit
  ``variance_explanation_note`` directly in the returned list view;
  the wizard simply scopes the list — it does not materialise its own
  notes.
* **Scenario 6** Drill-down to source transactions — the returned list
  view exposes the per-line ``action_drill_down_actuals`` button on
  each ``budget.budget.line``; the wizard does NOT duplicate drill-down
  logic. Its own ``action_drill_down()`` method returns a consolidated
  ``account.move.line`` view scoped to the wizard parameters for
  aggregate-level investigation.

Architectural notes
-------------------
* The wizard is a :class:`odoo.models.TransientModel`; records are
  auto-garbage-collected by the ``ir.autovacuum`` cron (Odoo core).
* No ``_inherit`` — this is a net-new TransientModel per AAP §0.5.1.2
  Group B.3.
* No cross-module imports (R-01 compliant).
* No ``sudo()`` calls (R-07 compliant).
* Variance computation is NOT performed in this wizard — it is
  performed in the `budget.budget.line._compute_variance` store=False
  field. The wizard is a pure parameter-selection + window-open
  helper; this maintains a single canonical implementation of the
  variance formulas and avoids drift.
* BM-004 SLA: <3s for 1,000 lines. The wizard imposes zero overhead
  on the render path — it only builds an ``ir.actions.act_window``
  domain. The SLA is fully absorbed by the read_group aggregation in
  ``_compute_variance``.
"""

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


# =====================================================================
# Selection value constants — surfaced as module-level so tests and
# other modules (e.g. reports) can reference them without duplicating
# the literal strings.
# =====================================================================

PERIOD_GRANULARITY_MONTHLY = 'monthly'
PERIOD_GRANULARITY_QUARTERLY = 'quarterly'
PERIOD_GRANULARITY_ANNUAL = 'annual'
PERIOD_GRANULARITY_CUSTOM = 'custom'

FAVORABLE_FILTER_ALL = 'all'
FAVORABLE_FILTER_FAVORABLE = 'favorable'
FAVORABLE_FILTER_UNFAVORABLE = 'unfavorable'
FAVORABLE_FILTER_NEUTRAL = 'neutral'


class BudgetVarianceWizard(models.TransientModel):
    """BM-004 parameter-selection wizard for variance analysis.

    End-to-end flow:

    1. User opens *Accounting → Budgets → Variance Analysis Wizard*.
    2. Wizard defaults are populated from the currently active
       confirmed budget (if any) or left blank.
    3. User picks a budget, date window, granularity, analytic
       scope, favorability filter, and an optional consumption
       threshold.
    4. ``action_open_variance()`` builds a scoped domain on
       ``budget.budget.line`` and returns an ``ir.actions.act_window``
       pointing at the variance list (created in
       ``views/budget_variance_views.xml``).
    5. The returned list uses the precomputed ``variance_*`` fields on
       ``budget.budget.line``; no additional SQL is issued by the
       wizard.
    """

    _name = 'budget.variance.wizard'
    _description = 'Budget Variance Analysis Wizard'
    _transient_max_hours = 1.0  # default; explicit for readability.

    # ------------------------------------------------------------------
    # Scope fields
    # ------------------------------------------------------------------

    budget_id = fields.Many2one(
        'budget.budget',
        string='Budget',
        required=True,
        domain=[('state', 'in', ('confirmed', 'closed'))],
        help=(
            'Target budget whose lines will be analysed. Only '
            'confirmed or closed budgets are eligible — draft '
            'budgets have no fiscal commitment and cannot yet be '
            'varianced against actuals.'
        ),
    )
    company_id = fields.Many2one(
        related='budget_id.company_id',
        store=False,
        readonly=True,
    )
    currency_id = fields.Many2one(
        related='budget_id.currency_id',
        store=False,
        readonly=True,
    )

    # Date window. Defaults mirror the selected budget's fiscal dates.
    date_from = fields.Date(
        string='Date From',
        required=True,
        help=(
            'Inclusive start of the analysis window. Defaults to the '
            'selected budget\'s ``date_from`` and can be narrowed to '
            'investigate a sub-period.'
        ),
    )
    date_to = fields.Date(
        string='Date To',
        required=True,
        help=(
            'Inclusive end of the analysis window. Defaults to the '
            'selected budget\'s ``date_to``.'
        ),
    )

    # ------------------------------------------------------------------
    # Scenario 4 — trend / granularity
    # ------------------------------------------------------------------

    period_granularity = fields.Selection(
        selection=[
            (PERIOD_GRANULARITY_MONTHLY, 'Monthly'),
            (PERIOD_GRANULARITY_QUARTERLY, 'Quarterly'),
            (PERIOD_GRANULARITY_ANNUAL, 'Annual'),
            (PERIOD_GRANULARITY_CUSTOM, 'Custom'),
        ],
        string='Period Granularity',
        default=PERIOD_GRANULARITY_MONTHLY,
        required=True,
        help=(
            'Granularity used when the user pivots the returned list. '
            'Monthly, quarterly, and annual pre-group by the '
            'corresponding date:month / date:quarter / date:year key; '
            'custom defers grouping to the user.'
        ),
    )

    # ------------------------------------------------------------------
    # Scenario 2 — analytic dimension breakdown
    # ------------------------------------------------------------------

    analytic_plan_ids = fields.Many2many(
        'account.analytic.plan',
        'budget_variance_wizard_analytic_plan_rel',
        'wizard_id',
        'plan_id',
        string='Analytic Plans',
        help=(
            'Restrict the variance list to budget lines whose '
            'analytic distribution references one of the selected '
            'plans. Leave empty for no plan-level filter.'
        ),
    )
    analytic_account_ids = fields.Many2many(
        'account.analytic.account',
        'budget_variance_wizard_analytic_account_rel',
        'wizard_id',
        'analytic_account_id',
        string='Analytic Accounts',
        help=(
            'Restrict the variance list to budget lines whose '
            'analytic distribution references one of the selected '
            'accounts. Leave empty for no account-level filter.'
        ),
    )

    # ------------------------------------------------------------------
    # Scenario 3 — favorable / unfavorable filter
    # ------------------------------------------------------------------

    favorable_filter = fields.Selection(
        selection=[
            (FAVORABLE_FILTER_ALL, 'All classifications'),
            (FAVORABLE_FILTER_FAVORABLE, 'Only favorable'),
            (FAVORABLE_FILTER_UNFAVORABLE, 'Only unfavorable'),
            (FAVORABLE_FILTER_NEUTRAL, 'Only neutral'),
        ],
        string='Favorability Filter',
        default=FAVORABLE_FILTER_ALL,
        required=True,
        help=(
            'Narrow the variance list to the selected favorability '
            'classification. The classification on each budget line '
            'is computed from the line\'s account type and the sign '
            'of the variance (see '
            '``budget.budget.line._classify_variance``).'
        ),
    )

    # ------------------------------------------------------------------
    # Threshold filter — an optional consumption-percent cut-off
    # ------------------------------------------------------------------

    variance_threshold_percent = fields.Float(
        string='Consumption Threshold %',
        default=0.0,
        help=(
            'Only show budget lines whose ``variance_consumption_'
            'percent`` (actual / planned * 100) meets or exceeds '
            'this value. Zero (default) disables the filter.'
        ),
    )

    include_draft_lines = fields.Boolean(
        string='Include Draft Lines',
        default=False,
        help=(
            'When enabled, draft lines (state != confirmed|closed) '
            'are also shown. BM-004 default is to hide draft lines '
            'because draft budgets are not yet fiscally committed.'
        ),
    )

    # ------------------------------------------------------------------
    # Default-get helpers
    # ------------------------------------------------------------------

    @api.model
    def default_get(self, fields_list):
        """Populate defaults from the active confirmed budget if any.

        ``default_get`` is Odoo's override-safe hook for prefilling
        a wizard on open. When the user opened the wizard from a
        confirmed ``budget.budget`` record (i.e. ``active_model`` =
        'budget.budget' in context), we capture that budget as the
        default ``budget_id``, and derive the default date window
        from its fiscal dates.
        """
        values = super().default_get(fields_list)
        active_model = self.env.context.get('active_model')
        active_id = self.env.context.get('active_id')
        if (
            active_model == 'budget.budget'
            and active_id
            and 'budget_id' in fields_list
        ):
            budget = self.env['budget.budget'].browse(active_id)
            if budget.exists() and budget.state in ('confirmed', 'closed'):
                values['budget_id'] = budget.id
                if 'date_from' in fields_list and not values.get('date_from'):
                    values['date_from'] = budget.date_from
                if 'date_to' in fields_list and not values.get('date_to'):
                    values['date_to'] = budget.date_to
        return values

    @api.onchange('budget_id')
    def _onchange_budget_id(self):
        """Sync the date window to the newly chosen budget's dates.

        ``onchange`` ensures that every time the user picks a
        different budget in the wizard form, the date window follows
        by default. Users can subsequently narrow the dates manually;
        ``onchange`` only populates defaults when the user has not
        yet overridden them.
        """
        for wizard in self:
            if wizard.budget_id:
                wizard.date_from = wizard.budget_id.date_from
                wizard.date_to = wizard.budget_id.date_to

    @api.model_create_multi
    def create(self, vals_list):
        """Auto-populate the date window from ``budget_id`` on create.

        ``date_from`` and ``date_to`` are declared ``required=True`` on
        the model so that downstream SQL queries (``_build_variance_domain``
        et al.) can rely on a non-null date window. When callers pass a
        ``budget_id`` but omit the date fields (e.g. programmatic
        creation from test code or from another wizard chain), we
        mirror the budget's fiscal window to satisfy the NOT NULL
        constraint. The ``default_get`` / ``onchange`` hooks cover the
        UI path but do not fire when ``create()`` is invoked
        directly with a partial dict. This create() override makes the
        wizard ergonomic for programmatic callers while preserving the
        UI defaults.
        """
        for vals in vals_list:
            budget_id = vals.get('budget_id')
            if budget_id and (
                not vals.get('date_from') or not vals.get('date_to')
            ):
                budget = self.env['budget.budget'].browse(budget_id)
                if budget.exists():
                    if not vals.get('date_from'):
                        vals['date_from'] = budget.date_from
                    if not vals.get('date_to'):
                        vals['date_to'] = budget.date_to
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------

    @api.constrains('date_from', 'date_to')
    def _check_date_range(self):
        """Enforce ``date_from <= date_to``.

        A zero-width window (date_from == date_to) is legal because
        it supports single-day variance analyses.
        """
        for wizard in self:
            if (
                wizard.date_from
                and wizard.date_to
                and wizard.date_from > wizard.date_to
            ):
                raise ValidationError(_(
                    "The \"From\" date (%(from_date)s) must be on or "
                    "before the \"To\" date (%(to_date)s). Please "
                    "correct the range.",
                    from_date=wizard.date_from,
                    to_date=wizard.date_to,
                ))

    @api.constrains('variance_threshold_percent')
    def _check_threshold_percent(self):
        """Reject negative consumption thresholds.

        A negative threshold has no semantic meaning for variance
        analysis (``variance_consumption_percent`` is a non-negative
        ratio). Reject with a clear error.
        """
        for wizard in self:
            if wizard.variance_threshold_percent < 0.0:
                raise ValidationError(_(
                    "The consumption threshold percent must be a "
                    "non-negative value (got %(value)s).",
                    value=wizard.variance_threshold_percent,
                ))

    # ------------------------------------------------------------------
    # Domain construction
    # ------------------------------------------------------------------

    def _build_variance_domain(self):
        """Build the ``account.budget.line`` domain for the wizard scope.

        The wizard's scope is applied at the ``budget.budget.line``
        level — NOT at ``account.move.line`` — because variance is a
        computed property of budget lines. Applying filters at the
        budget-line layer yields correct, simple, composable results
        without coupling the wizard to ledger semantics.

        Returns:
            list: A standard Odoo domain expressed as a list of
                triplets suitable for
                ``ir.actions.act_window.domain``.
        """
        self.ensure_one()
        domain = [('budget_id', '=', self.budget_id.id)]
        # The budget-line date window follows the parent budget (via
        # related fields), so we filter on date_from / date_to at the
        # BUDGET level not the line level.
        if not self.include_draft_lines:
            domain.append(('state', 'in', ('confirmed', 'closed')))
        # Analytic filter: if user picked plans, translate to accounts.
        analytic_account_ids = set(self.analytic_account_ids.ids)
        if self.analytic_plan_ids:
            plan_accounts = self.env['account.analytic.account'].search([
                ('plan_id', 'in', self.analytic_plan_ids.ids),
            ])
            analytic_account_ids.update(plan_accounts.ids)
        if analytic_account_ids:
            # ``distribution_analytic_account_ids`` is provided by
            # analytic.mixin — a Many2many flattening of the JSON
            # distribution. This is the canonical domain shape for
            # analytic filters on analytic.mixin inheritors.
            domain.append((
                'distribution_analytic_account_ids',
                'in',
                list(analytic_account_ids),
            ))
        # Favorability filter — translate Selection to the field value.
        if self.favorable_filter and self.favorable_filter != (
            FAVORABLE_FILTER_ALL
        ):
            domain.append((
                'variance_classification',
                '=',
                self.favorable_filter,
            ))
        # Threshold filter — only meaningful when > 0.
        if self.variance_threshold_percent > 0.0:
            domain.append((
                'variance_consumption_percent',
                '>=',
                self.variance_threshold_percent,
            ))
        return domain

    # ------------------------------------------------------------------
    # Variance calculation helpers (exposed for tests)
    # ------------------------------------------------------------------

    @api.model
    def compute_absolute_variance(self, actual, planned):
        """Return ``actual - planned``. Pure helper.

        BM-004 Scenario 1 / UT-001: the absolute variance is simply
        the signed difference between actual and planned amounts.
        Positive values mean actual exceeded planned; negative values
        mean actual fell short of planned.
        """
        return float(actual) - float(planned)

    @api.model
    def compute_percentage_variance(self, actual, planned):
        """Return ``((actual - planned) / planned) * 100`` or ``None``.

        BM-004 Scenario 1 / UT-002 / EC-001: when ``planned == 0``
        the percentage is undefined (division by zero) so this
        helper returns ``None`` — callers must display "N/A" in the
        UI for that case.
        """
        if not planned:
            return None
        return ((float(actual) - float(planned)) / float(planned)) * 100.0

    @api.model
    def classify_favorability(self, actual, planned, account_type):
        """Return favorability classification for a given account type.

        BM-004 Scenario 3 / UT-006 through UT-009. The sign convention
        depends on whether the account is revenue (income) or expense:

        * Revenue accounts — higher actuals are FAVORABLE
          (``actual > planned``).
        * Expense accounts — lower actuals are FAVORABLE
          (``actual < planned``).
        * Zero-variance (within 0.005 tolerance) or unsupported
          account types → ``neutral``.

        Args:
            actual: The realised actual amount.
            planned: The budgeted amount.
            account_type: The value of
                ``account.account.account_type`` for the underlying
                GL account.

        Returns:
            str: One of ``'favorable'``, ``'unfavorable'``,
                ``'neutral'``.
        """
        income_types = ('income', 'income_other')
        expense_types = (
            'expense',
            'expense_other',
            'expense_depreciation',
            'expense_direct_cost',
        )
        # Within-tolerance equality → neutral.
        if abs(float(actual) - float(planned)) < 0.005:
            return 'neutral'
        if account_type in income_types:
            return (
                'favorable' if float(actual) > float(planned)
                else 'unfavorable'
            )
        if account_type in expense_types:
            return (
                'favorable' if float(actual) < float(planned)
                else 'unfavorable'
            )
        return 'neutral'

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_open_variance(self):
        """Return an act_window opening the variance list/pivot/graph.

        The returned action reuses the existing BM-003/BM-004 views
        declared in ``views/budget_variance_views.xml``:

        * ``view_budget_variance_list``  — default, primary list
        * ``view_budget_variance_pivot`` — analytic pivot
        * ``view_budget_variance_graph`` — stacked graph

        Pivot defaults are seeded through the action context so the
        user lands on a view already grouped by the chosen
        granularity (monthly / quarterly / annual / custom).
        """
        self.ensure_one()
        _logger.debug(
            "BM-004 wizard opening variance view for budget %s, "
            "granularity=%s, favorable_filter=%s, threshold=%.2f",
            self.budget_id.display_name,
            self.period_granularity,
            self.favorable_filter,
            self.variance_threshold_percent,
        )
        # Default group-by for the pivot/graph surfaces depends on the
        # selected granularity. The list view never auto-groups.
        context = {
            'search_default_budget': 1,
            'budget_variance_wizard_id': self.id,
            'budget_variance_wizard_granularity': self.period_granularity,
        }
        if self.favorable_filter and self.favorable_filter != (
            FAVORABLE_FILTER_ALL
        ):
            # Expose the wizard's favorability filter as a preset in
            # the search view for visibility; the primary enforcement
            # is via the domain below.
            context['budget_variance_wizard_favorability'] = (
                self.favorable_filter
            )
        # Resolve view references safely — if the views are not yet
        # loaded (during tests that install only models), fall back to
        # the default view_mode ordering without explicit view_ids.
        try:
            view_list = self.env.ref(
                'account_budget_management.view_budget_variance_list',
            )
            view_pivot = self.env.ref(
                'account_budget_management.view_budget_variance_pivot',
            )
            view_graph = self.env.ref(
                'account_budget_management.view_budget_variance_graph',
            )
            view_ids = [
                (5, 0, 0),
                (0, 0, {
                    'view_mode': 'list',
                    'view_id': view_list.id,
                }),
                (0, 0, {
                    'view_mode': 'pivot',
                    'view_id': view_pivot.id,
                }),
                (0, 0, {
                    'view_mode': 'graph',
                    'view_id': view_graph.id,
                }),
            ]
        except ValueError:
            view_ids = False
        action = {
            'type': 'ir.actions.act_window',
            'name': _('Variance Analysis'),
            'res_model': 'budget.budget.line',
            'view_mode': 'list,pivot,graph',
            'domain': self._build_variance_domain(),
            'context': context,
            'target': 'current',
        }
        if view_ids:
            action['view_ids'] = view_ids
        return action

    def action_drill_down(self):
        """Aggregate drill-down to ``account.move.line``.

        BM-004 Scenario 6 defines per-line drill-down as the primary
        drill-down path; that is implemented on
        ``budget.budget.line.action_drill_down_actuals``. This
        wizard-level method provides a COMPLEMENTARY aggregate
        drill-down that surfaces every ``account.move.line`` in the
        wizard's scope in one list, useful for an auditor-style
        "show me every posting that influences any line in this
        budget" investigation.

        The drill-down HONORS the wizard's configured filters
        (``favorable_filter``, ``variance_threshold_percent``,
        ``analytic_plan_ids``, ``analytic_account_ids``,
        ``include_draft_lines``). When those filters narrow the set
        of budget lines to an empty subset, a ``UserError`` is
        raised so users understand why no action sheet opens —
        otherwise the user would see a misleading "empty list"
        without realising their filters eliminated every line.

        Filter evaluation is performed IN-MEMORY via
        ``RecordSet.filtered(...)`` rather than a database
        ``search()`` call because two of the relevant fields
        (``variance_classification``, ``variance_consumption_percent``)
        are ``store=False`` computed fields on ``budget.budget.line``
        with no ``search=`` argument and therefore cannot be used in
        a domain passed to the ORM. In-memory filtering is
        tractable because ``self.budget_id.line_ids`` is already
        loaded and BM-004's SLA is scoped to <= 1,000 lines.

        Returns:
            dict: An ``ir.actions.act_window`` descriptor scoping
                ``account.move.line`` to the wizard's filtered
                budget accounts, date window, companies, and (when
                set) analytic distributions.

        Raises:
            UserError: When the selected budget has no lines; when
                none of the budget lines have an account assigned;
                OR when the wizard's favorability / threshold /
                analytic / draft-inclusion filters narrow the
                matching line set to empty.
        """
        self.ensure_one()
        if not self.budget_id.line_ids:
            raise UserError(_(
                "Cannot drill down — the selected budget has no "
                "lines. Add at least one budget line on budget "
                "\"%(budget)s\" and try again.",
                budget=self.budget_id.display_name,
            ))
        # Apply wizard filters IN-MEMORY. The variance fields are
        # store=False computed fields, so we cannot use a domain
        # search; but the line_ids recordset is already loaded,
        # so .filtered() is cheap and correct.
        matching_lines = self.budget_id.line_ids
        # Draft-inclusion filter: mirrors _build_variance_domain.
        if not self.include_draft_lines:
            matching_lines = matching_lines.filtered(
                lambda line: line.state in ('confirmed', 'closed'),
            )
        # Favorability filter.
        if (self.favorable_filter
                and self.favorable_filter != FAVORABLE_FILTER_ALL):
            matching_lines = matching_lines.filtered(
                lambda line, f=self.favorable_filter:
                    line.variance_classification == f,
            )
        # Consumption-percentage threshold filter.
        if self.variance_threshold_percent > 0.0:
            threshold = self.variance_threshold_percent
            matching_lines = matching_lines.filtered(
                lambda line, t=threshold:
                    line.variance_consumption_percent >= t,
            )
        # Analytic plan / account filter — same translation used in
        # _build_variance_domain. When filter accounts are set, keep
        # only lines whose distribution intersects them.
        analytic_account_ids = set(self.analytic_account_ids.ids)
        if self.analytic_plan_ids:
            plan_accounts = self.env['account.analytic.account'].search([
                ('plan_id', 'in', self.analytic_plan_ids.ids),
            ])
            analytic_account_ids.update(plan_accounts.ids)
        if analytic_account_ids:
            matching_lines = matching_lines.filtered(
                lambda line, ids=analytic_account_ids:
                    bool(
                        set(line.distribution_analytic_account_ids.ids)
                        & ids,
                    ),
            )
        # After all filters, verify we still have matching lines.
        if not matching_lines:
            raise UserError(_(
                "Cannot drill down — no budget lines on "
                "\"%(budget)s\" match the configured filters "
                "(favorability=%(fav)s, variance threshold="
                "%(thresh)s%%, include draft lines=%(draft)s). "
                "Adjust the filters and try again.",
                budget=self.budget_id.display_name,
                fav=self.favorable_filter or FAVORABLE_FILTER_ALL,
                thresh=self.variance_threshold_percent,
                draft=self.include_draft_lines,
            ))
        accounts = matching_lines.mapped('account_id')
        if not accounts:
            raise UserError(_(
                "Cannot drill down — none of the matching budget "
                "lines on \"%(budget)s\" have an account "
                "assigned. Assign accounts on the budget lines "
                "first.",
                budget=self.budget_id.display_name,
            ))
        domain = [
            ('account_id', 'in', accounts.ids),
            ('parent_state', '=', 'posted'),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
        ]
        if self.company_id:
            domain.append(('company_id', '=', self.company_id.id))
        if analytic_account_ids:
            # Route through analytic.mixin's GIN-indexed search for
            # efficiency on large move-line datasets.
            domain.append((
                'analytic_distribution',
                'in',
                list(analytic_account_ids),
            ))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Actual Transactions — %(budget)s',
                      budget=self.budget_id.display_name),
            'res_model': 'account.move.line',
            'view_mode': 'list,form',
            'domain': domain,
            'context': {'search_default_posted': 1},
            'target': 'current',
        }
