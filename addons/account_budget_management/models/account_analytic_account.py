# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""
Analytic Account Extension — Budget Awareness (BM-001)
======================================================

This module extends the Odoo core ``account.analytic.account`` model
with budget-aware computed fields so that a user viewing an analytic
dimension (cost centre, project, department) can immediately see the
budget lines that target it, along with their planned and actual
amounts and the resulting consumption percentage.

Story Mapping
-------------
* BM-001 Scenario 3 — Analytic distribution linkage. A budget line may
  target one or more analytic accounts via a JSON ``analytic_distribution``
  dictionary (key = analytic account ID or comma-separated multi-plan
  IDs, value = percentage share). This model provides the inverse read
  path so a user viewing an analytic account can immediately see every
  budget line that references it.

* BM-003 Scenario 4 — Drill-down navigation. The
  ``budget_amount_planned`` / ``budget_amount_actual`` aggregates
  support the actual-vs-budget dashboard smart buttons and the
  analytic-account form's budget consumption widget.

* BM-005 Scenario 3 — Threshold monitoring. When the alert cron
  computes consumption percentages per budget line, the resulting
  aggregate can be displayed on the analytic-account form via the
  computed ``budget_consumption_percent`` field.

Field Structure
---------------
Five additive fields are declared; all are computed and non-stored
(re-evaluated on each form open / domain search) so there is no new
schema footprint on ``account_analytic_account`` beyond the usual
inherit-in-place table:

* ``budget_line_ids`` — Many2many reverse lookup of
  ``budget.budget.line`` records whose ``analytic_distribution`` JSON
  references this analytic account. Implemented with a compute +
  search pair so that Odoo domain builders can filter analytic
  accounts by budget-line referencing predicates such as
  ``('budget_line_ids', 'in', [budget_line_id])``.

* ``budget_line_count`` — Integer counter used by the smart-button on
  the analytic account form to show "N budget lines target this
  analytic dimension".

* ``budget_amount_planned`` — Monetary weighted sum of
  ``planned_amount * distribution_share / 100.0`` across every
  referencing budget line.

* ``budget_amount_actual`` — Monetary total of posted
  ``account.move.line.balance`` values whose account is listed on any
  referencing budget line, filtered by the budget's date range and
  the analytic distribution. Computed in a single aggregated
  ``_read_group`` per analytic account to meet the BM-003/BM-004 SLA
  of <3s for ≤1,000 budget lines.

* ``budget_consumption_percent`` — Float ratio
  ``budget_amount_actual / budget_amount_planned * 100``, rounded to
  two decimal digits. Returns ``0.0`` when the planned amount is zero
  to avoid division errors.

Rules Compliance
----------------
* R-01 — No cross-module imports. Only Odoo core symbols (``api``,
  ``fields``, ``models``, ``_``) and the in-module ``budget.budget.line``
  model are referenced.
* R-03 — Uses ``_inherit = 'account.analytic.account'`` without
  ``_name`` (the correct pattern for additive field extension of an
  existing core model).
* R-05 — No redefinition of core fields. All five added fields are
  computed (``compute=...``) — none is a plain stored column that
  would collide with an existing definition. ``currency_id``,
  ``company_id``, ``name``, ``code``, ``plan_id``, ``partner_id``,
  ``balance``, ``debit``, ``credit`` (existing on the core model) are
  reused, never redefined.
* R-07 — No ``sudo()`` calls. Record-rule access for the referenced
  ``account.move.line`` entries is controlled by standard Odoo
  accounting security; users without read access to the relevant
  journal items will see their actuals excluded from the aggregate,
  which is the expected data-permission behaviour.
* R-08 — No ``variance_*`` or ``alert_*`` prefixed fields appear on
  this model so the BM-004 / BM-005 disjoint baseline is preserved.
* R-09 — Module folder name ``account_budget_management`` matches AAP
  exactly.

Performance
-----------
Two distinct performance paths are relevant:

1. **Reverse lookup** (``_compute_budget_line_ids``) — delegates to
   ``analytic.mixin.distribution_analytic_account_ids`` which is a
   Many2many computed + searchable field backed by a PostgreSQL GIN
   index automatically created by ``analytic.mixin.init()`` over the
   ``analytic_distribution`` JSON column. The search
   ``('distribution_analytic_account_ids', 'in', analytic.id)``
   therefore executes as an efficient indexed JSONB query.

2. **Actuals aggregation** (``_compute_budget_amounts``) — performs a
   single ``_read_group`` on ``account.move.line`` per analytic
   account, grouped by ``account_id`` with ``balance:sum`` aggregate.
   This avoids per-move-line Python iteration (prohibited by R-08
   performance notes) and uses the JSONB GIN index on the ``analytic_
   distribution`` column for the distribution filter.
"""

from odoo import _, api, fields, models


class AccountAnalyticAccount(models.Model):
    """Extend ``account.analytic.account`` with budget-aware fields.

    Adds five computed fields (see module docstring) and two public
    helpers (``_search_budget_line_ids`` for inverse domain searches
    and ``action_open_budget_lines`` for the analytic-form smart
    button).

    No ``_name`` is declared — the class inherits its table from the
    core analytic account model via ``_inherit``, which is the
    canonical additive-extension pattern (R-03).
    """

    _inherit = 'account.analytic.account'

    # ==================================================================
    # Section 4.1 — Reverse-relation fields
    # ==================================================================

    budget_line_ids = fields.Many2many(
        comodel_name='budget.budget.line',
        string='Budget Lines',
        compute='_compute_budget_line_ids',
        search='_search_budget_line_ids',
        help=(
            "Budget lines referencing this analytic account via the "
            "analytic_distribution JSON field. Computed dynamically "
            "through analytic.mixin.distribution_analytic_account_ids "
            "so the search benefits from the GIN index on the JSON "
            "column."
        ),
    )
    budget_line_count = fields.Integer(
        string='Budget Line Count',
        compute='_compute_budget_line_count',
        help=(
            "Number of budget lines currently referencing this "
            "analytic account. Rendered on the analytic account form "
            "as a smart-button counter."
        ),
    )

    # ==================================================================
    # Section 4.2 — Aggregate amounts
    # ==================================================================

    budget_amount_planned = fields.Monetary(
        string='Planned Budget',
        compute='_compute_budget_amounts',
        currency_field='currency_id',
        help=(
            "Sum of planned amounts from budget lines referencing this "
            "analytic account, weighted by the distribution percentage "
            "from analytic_distribution. A line targeting this analytic "
            "at 40% contributes 40% of its planned_amount to this "
            "aggregate."
        ),
    )
    budget_amount_actual = fields.Monetary(
        string='Actual Amount',
        compute='_compute_budget_amounts',
        currency_field='currency_id',
        help=(
            "Sum of posted account.move.line balances whose account is "
            "on any budget line referencing this analytic account, "
            "within the budget line date ranges and matching the "
            "analytic distribution. Computed via a single aggregated "
            "_read_group per analytic account."
        ),
    )
    budget_consumption_percent = fields.Float(
        string='Budget Consumption (%)',
        compute='_compute_budget_amounts',
        digits=(5, 2),
        help=(
            "Ratio of actual amount to planned budget, expressed as a "
            "percentage. 100% means the actual equals the planned "
            "budget. Returns 0.0 when the planned amount is zero to "
            "avoid division-by-zero errors."
        ),
    )

    # ==================================================================
    # Section 4.3 — Compute / search methods
    # ==================================================================

    @api.depends_context('company')
    def _compute_budget_line_ids(self):
        """Populate the reverse lookup of budget lines by analytic ID.

        Uses ``analytic.mixin.distribution_analytic_account_ids`` (a
        computed + searchable Many2many of analytic account records
        flattened from the ``analytic_distribution`` JSON keys) so the
        search is routed through the JSONB GIN index auto-created by
        ``analytic.mixin.init()``.

        Scoped by company to respect multi-company security. For
        un-saved records (no numeric ID) the field is set to an empty
        recordset — standard Odoo convention for reverse-relation
        computed fields.
        """
        BudgetLine = self.env['budget.budget.line']
        for analytic in self:
            if not isinstance(analytic.id, int) or not analytic.id:
                analytic.budget_line_ids = BudgetLine
                continue
            analytic.budget_line_ids = BudgetLine.search([
                ('distribution_analytic_account_ids', 'in', analytic.id),
                ('company_id', '=', analytic.company_id.id),
            ])

    def _search_budget_line_ids(self, operator, value):
        """Domain-search helper for the computed ``budget_line_ids``.

        Supports the ``'in'``, ``'not in'``, ``'='`` and ``'!='``
        operators with a single integer or a list/tuple of integer IDs
        referring to ``budget.budget.line`` records. Returns a domain
        on the analytic account model that resolves to the set of
        analytic account IDs referenced by the supplied budget lines'
        ``analytic_distribution`` JSON.

        Uses ``analytic.mixin._get_analytic_account_ids_from_distributions``
        (inherited transitively via ``budget.budget.line._inherit=
        ['analytic.mixin']``) which handles both single-plan keys
        (``"42"``) and multi-plan comma-separated keys (``"42,7"``).

        Any operator outside the supported set is passed through on
        ``id`` unchanged so that callers using unusual operators still
        get deterministic (if broader) behaviour.
        """
        if operator not in ('in', 'not in', '=', '!='):
            return [('id', operator, value)]
        if isinstance(value, int) and not isinstance(value, bool):
            value = [value]
        BudgetLine = self.env['budget.budget.line']
        budget_lines = BudgetLine.browse(value).exists()
        account_ids = set()
        for line in budget_lines:
            account_ids.update(
                BudgetLine._get_analytic_account_ids_from_distributions(
                    [line.analytic_distribution],
                ),
            )
        if operator in ('in', '='):
            return [('id', 'in', list(account_ids))]
        return [('id', 'not in', list(account_ids))]

    @api.depends('budget_line_ids')
    def _compute_budget_line_count(self):
        """Simple counter for the smart-button on the analytic form.

        Trigger is ``budget_line_ids`` so changes in the reverse
        lookup (new / deleted budget lines, distribution edits) cause
        the smart-button label to re-render on the next cache refresh.
        """
        for analytic in self:
            analytic.budget_line_count = len(analytic.budget_line_ids)

    @api.depends('budget_line_ids', 'budget_line_ids.planned_amount')
    def _compute_budget_amounts(self):
        """Aggregate planned + actual budget amounts per analytic.

        The method has two distinct legs:

        * **Planned** — iterate each referencing budget line's
          ``analytic_distribution`` JSON, locate keys containing this
          analytic's ID (either as a single-plan key such as ``"42"``
          or as a multi-plan comma-separated key such as ``"42,7"``),
          and weight the line's ``planned_amount`` by the key's
          percentage share. Summed across all referencing lines to
          yield ``budget_amount_planned``.

        * **Actual** — issue a single ``_read_group`` over
          ``account.move.line`` filtered by the union of account IDs
          from the referencing budget lines, the minimum-to-maximum
          date window covering those lines, posted journal entries
          only (``parent_state='posted'``), and the analytic
          distribution via ``('analytic_distribution', 'in',
          analytic.id)`` which routes through
          ``analytic.mixin._search_analytic_distribution`` and the
          GIN index. Grouped by ``account_id`` with a
          ``balance:sum`` aggregate. The sum of the group results is
          the ``budget_amount_actual``.

        The consumption percentage is then
        ``budget_amount_actual / budget_amount_planned * 100`` (or
        ``0.0`` if the planned amount is zero).

        All three fields are zero-initialised up front so that the
        per-record ``continue`` branches in the no-data cases leave
        the records in a well-defined state.
        """
        # Zero-initialise all three fields to avoid orphan state on
        # analytic records that have no referencing budget lines.
        for analytic in self:
            analytic.budget_amount_planned = 0.0
            analytic.budget_amount_actual = 0.0
            analytic.budget_consumption_percent = 0.0

        if not self:
            return

        AccountMoveLine = self.env['account.move.line']

        for analytic in self:
            lines = analytic.budget_line_ids
            if not lines:
                # No referencing budget lines → planned and actual
                # remain 0.0 as zero-initialised above.
                continue

            # ------------------------------------------------------------
            # Planned: weighted sum across referencing budget lines.
            # ------------------------------------------------------------
            planned = 0.0
            for line in lines:
                for key, percentage in (line.analytic_distribution or {}).items():
                    ids_in_key = [
                        int(part)
                        for part in key.split(',')
                        if part and part.isdigit()
                    ]
                    if analytic.id in ids_in_key:
                        try:
                            pct = float(percentage)
                        except (TypeError, ValueError):
                            pct = 0.0
                        planned += (line.planned_amount or 0.0) * (pct / 100.0)
            analytic.budget_amount_planned = planned

            # ------------------------------------------------------------
            # Actual: single aggregated _read_group per analytic.
            # ------------------------------------------------------------
            account_ids = lines.mapped('account_id').ids
            dates_from = [d for d in lines.mapped('date_from') if d]
            dates_to = [d for d in lines.mapped('date_to') if d]
            if not (account_ids and dates_from and dates_to):
                # Missing filter inputs → leave actual at 0.0. This
                # matches the behaviour of the reporting wizards when
                # budget lines are in an incomplete state.
                if planned:
                    analytic.budget_consumption_percent = 0.0
                continue

            domain = [
                ('account_id', 'in', account_ids),
                ('parent_state', '=', 'posted'),
                ('date', '>=', min(dates_from)),
                ('date', '<=', max(dates_to)),
                ('analytic_distribution', 'in', analytic.id),
            ]
            groups = AccountMoveLine._read_group(
                domain=domain,
                groupby=['account_id'],
                aggregates=['balance:sum'],
            )
            # Each group is a ``(account_record, balance_sum)`` tuple.
            # Summing the balance_sum across all groups gives the
            # total posted actual for this analytic's budget window.
            total_actual = sum(
                (balance_sum or 0.0) for _account, balance_sum in groups
            )
            analytic.budget_amount_actual = total_actual

            # ------------------------------------------------------------
            # Consumption percentage.
            # ------------------------------------------------------------
            if planned:
                analytic.budget_consumption_percent = (
                    total_actual / planned * 100.0
                )
            else:
                analytic.budget_consumption_percent = 0.0

    # ==================================================================
    # Section 4.4 — Action helpers
    # ==================================================================

    def action_open_budget_lines(self):
        """Open a window showing every budget line for this analytic.

        Used by the smart-button on the analytic account form (see
        ``views/budget_views.xml``:
        ``view_account_analytic_account_form_budget_inherit``).
        Returns an ``ir.actions.act_window`` filtered by the IDs in
        the current record's ``budget_line_ids`` Many2many, with a
        default company context that aligns new budget-line creation
        with the analytic's company.
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Budget Lines'),
            'res_model': 'budget.budget.line',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.budget_line_ids.ids)],
            'context': {'default_company_id': self.company_id.id},
        }
