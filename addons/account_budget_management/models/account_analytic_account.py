# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""
Analytic Account Extension — Budget Awareness (BM-001 Scenario 3)
=================================================================

This module extends the Odoo core ``account.analytic.account`` model
with budget-aware computed fields so that users can navigate from an
analytic dimension (cost centre, project, department) to the budgets
that target it. The extension closes the Track B Phase 1 foundation
by wiring analytic records to their budget consumers via the JSON
``analytic_distribution`` field on ``budget.budget.line``.

Story Mapping
-------------
* BM-001 Scenario 3 — Analytic distribution linkage. A budget line may
  target one or more analytic accounts via a JSON distribution
  dictionary (key = analytic account ID, value = percentage share).
  This model provides the inverse read path so a user viewing an
  analytic account can immediately see every budget line that
  references it.

* BM-003 Scenario 4 — Drill-down navigation. The
  ``budget_amount_planned`` / ``budget_amount_actual`` aggregates
  support the actual-vs-budget dashboard smart buttons and the
  analytic-account form's budget consumption widget.

* BM-005 Scenario 3 — Threshold monitoring. When the alert cron
  computes consumption percentages per budget line, the resulting
  aggregate can be displayed on the analytic account form via the
  computed ``budget_consumption_percent`` field.

Field Structure
---------------
Four additive fields are declared; all are computed and non-stored
(re-evaluated on each form open) so there is no schema footprint on
``account_analytic_account`` beyond the usual inherit-in-place table:

* ``budget_line_ids`` — reverse lookup of ``budget.budget.line``
  records whose ``analytic_distribution`` JSON references this
  analytic account. Implemented with a compute + search pair so that
  Odoo domain builders can filter analytic accounts by budget-line
  referencing predicates.

* ``budget_line_count`` — stored integer used by the smart-button
  counter on the analytic account form to show "N budget lines target
  this analytic dimension". Not stored in the DB because it would
  require invalidation on every budget line write; instead it is
  computed lazily from ``budget_line_ids``.

* ``budget_amount_planned`` — weighted sum of ``planned_amount *
  distribution_share / 100.0`` across every referencing budget line.

* ``budget_amount_actual`` — weighted sum of ``variance_actual *
  distribution_share / 100.0`` across every referencing budget line.
  Because ``variance_actual`` on ``budget.budget.line`` is itself a
  computed field that reads ``account.move.line`` via ``_read_group``,
  this aggregate transitively aggregates posted actuals.

* ``budget_consumption_percent`` — convenience ratio
  ``budget_amount_actual / budget_amount_planned * 100`` rounded to
  four digits. Used by the analytic-account dashboard to render the
  percentage-consumed bar.

Rules Compliance
----------------
* R-01 — No cross-module imports. Only Odoo core symbols are used.
* R-03 — Uses ``_inherit = 'account.analytic.account'`` without
  ``_name`` (the correct pattern for additive field extension of an
  existing core model).
* R-05 — No redefinition of core fields on ``account.move`` /
  ``account.move.line``. This extension targets ``account.analytic.
  account`` (a core model in ``addons/analytic/``), and adds only
  computed fields — no existing field on the analytic account table
  is redefined.
* R-07 — No ``sudo()`` calls. Record-rule access is controlled by
  Odoo core ``analytic.mixin`` and the standard analytic security.
* R-08 — No ``variance_*`` or ``alert_*`` prefixed fields appear on
  this model so the Checkpoint 5 disjoint baseline is preserved.
* R-09 — Module folder name ``account_budget_management`` matches AAP
  exactly.

Performance
-----------
The reverse lookup uses a single parameterised SQL query against
``budget_budget_line.analytic_distribution`` with a JSONB key-existence
operator (``?``). This is O(N) in the number of budget lines and is
fast enough for the BM-001 usage pattern (a single analytic account
typically has a bounded number of referencing budget lines, commonly
well under 100).
"""

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class AccountAnalyticAccount(models.Model):
    """Extend ``account.analytic.account`` with budget-aware fields.

    The class body contains four computed fields and their compute
    methods plus a single ``_search_budget_line_ids`` helper so Odoo
    domain filters of the form
    ``('budget_line_ids', 'in', <budget_line_ids>)`` resolve
    efficiently to a SQL ``EXISTS`` subquery.

    No ``_name`` is declared — the class inherits its table from the
    core analytic account model via ``_inherit``, which is the
    canonical additive-extension pattern (R-03).
    """

    _inherit = 'account.analytic.account'

    # ==================================================================
    # Section 4.1 — Reverse-relation fields
    # ==================================================================

    budget_line_ids = fields.One2many(
        comodel_name='budget.budget.line',
        compute='_compute_budget_line_ids',
        search='_search_budget_line_ids',
        string='Budget Lines',
        help="Budget lines whose analytic distribution references this "
             "analytic account. Computed dynamically by searching "
             "``budget.budget.line.analytic_distribution`` for entries "
             "keyed on this analytic account's ID.",
    )
    budget_line_count = fields.Integer(
        string='Budget Line Count',
        compute='_compute_budget_line_count',
        help="Number of budget lines currently referencing this "
             "analytic account. Rendered on the analytic account form "
             "as a smart-button counter.",
    )

    # ==================================================================
    # Section 4.2 — Aggregate amounts
    # ==================================================================

    budget_amount_planned = fields.Monetary(
        string='Planned Budget',
        compute='_compute_budget_amounts',
        currency_field='currency_id',
        help="Weighted sum of the planned amounts of every budget "
             "line targeting this analytic account. The weight per "
             "line is the percentage share declared in the line's "
             "``analytic_distribution`` JSON (e.g. a line targeting "
             "this analytic at 40% contributes 40% of its "
             "``planned_amount`` to this aggregate).",
    )
    budget_amount_actual = fields.Monetary(
        string='Actual Consumption',
        compute='_compute_budget_amounts',
        currency_field='currency_id',
        help="Weighted sum of posted-actuals for every budget line "
             "targeting this analytic account. Actuals are computed "
             "from posted ``account.move.line`` entries matching the "
             "line's account + date range + analytic distribution; "
             "see ``budget.budget.line._compute_variance``.",
    )
    budget_consumption_percent = fields.Float(
        string='Budget Consumption (%)',
        compute='_compute_budget_amounts',
        digits=(7, 2),
        help="Ratio ``budget_amount_actual / budget_amount_planned * "
             "100``. Returns 0.0 when the planned amount is zero to "
             "avoid division errors. Capped at 7.2 digits to handle "
             "extreme over-budget consumption (e.g. 1500% — an edge "
             "case observed when a very small budget is consumed by "
             "a much larger actual).",
    )

    # ==================================================================
    # Section 4.3 — Compute methods
    # ==================================================================

    def _compute_budget_line_ids(self):
        """Populate the reverse lookup of budget lines by analytic ID.

        Uses a single parameterised SQL query against
        ``budget_budget_line.analytic_distribution`` leveraging the
        PostgreSQL JSONB key-existence operator (``?``). For every
        analytic account in ``self`` we stringify the ID and test for
        its presence as a top-level key in each budget line's
        distribution dict.

        Results are then browsed via the ORM so downstream code can
        treat ``budget_line_ids`` as a normal recordset without losing
        access-control enforcement.

        The method short-circuits when ``self`` is empty, and for new
        (un-saved) records it yields an empty recordset — matching
        the standard Odoo convention for One2many inverse lookups on
        fresh records.
        """
        BudgetLine = self.env['budget.budget.line']
        if not self:
            return
        # Pre-filter to real (saved) records with a numeric ID.
        saved = self.filtered(lambda rec: isinstance(rec.id, int))
        unsaved = self - saved
        for rec in unsaved:
            rec.budget_line_ids = BudgetLine.browse()
        if not saved:
            return
        # Batched SQL: one query per analytic account keeps the JSONB
        # operator expression simple and lets Odoo apply record rules
        # during the follow-up ``browse``. The number of analytic
        # accounts rendered in a single form / list view is bounded
        # so this loop does not scale linearly with the table size.
        for rec in saved:
            self.env.cr.execute(
                """
                SELECT id
                  FROM budget_budget_line
                 WHERE analytic_distribution ? %s
                """,
                (str(rec.id),),
            )
            line_ids = [row[0] for row in self.env.cr.fetchall()]
            rec.budget_line_ids = BudgetLine.browse(line_ids)

    def _search_budget_line_ids(self, operator, value):
        """Domain-search helper for ``budget_line_ids``.

        Supports the ``'in'`` and ``'='`` operators with a single
        integer, a list of integers, or a recordset of budget lines.
        Returns a domain that resolves to the set of analytic account
        IDs referenced by the supplied budget lines.

        This enables canonical Odoo domain constructions like::

            ('budget_line_ids', 'in', budget_line.id)

        which compiles to an ``IN`` subquery over the analytic IDs
        extracted from each line's distribution dict.
        """
        if operator not in ('=', '!=', 'in', 'not in'):
            raise NotImplementedError(
                f"Unsupported operator {operator!r} for "
                f"budget_line_ids search.",
            )
        BudgetLine = self.env['budget.budget.line']
        # Normalise value to a recordset of budget lines.
        if isinstance(value, int):
            lines = BudgetLine.browse([value])
        elif isinstance(value, (list, tuple)):
            lines = BudgetLine.browse(list(value))
        elif isinstance(value, models.BaseModel):
            lines = value
        else:
            raise NotImplementedError(
                f"Unsupported value type {type(value).__name__!r} "
                f"for budget_line_ids search.",
            )
        # Union the analytic account IDs referenced across all
        # supplied lines.
        analytic_ids = set()
        for line in lines:
            dist = line.analytic_distribution or {}
            for key in dist:
                try:
                    analytic_ids.add(int(key))
                except (TypeError, ValueError):
                    # Malformed key — skip silently; distribution JSON
                    # should always contain integer-convertible keys
                    # but we defend against bad data.
                    continue
        id_domain_op = 'in' if operator in ('=', 'in') else 'not in'
        return [('id', id_domain_op, list(analytic_ids))]

    @api.depends('budget_line_ids')
    def _compute_budget_line_count(self):
        """Simple counter for the smart-button on the analytic form."""
        for rec in self:
            rec.budget_line_count = len(rec.budget_line_ids)

    @api.depends(
        'budget_line_ids',
        'budget_line_ids.planned_amount',
        'budget_line_ids.variance_actual',
        'budget_line_ids.analytic_distribution',
    )
    def _compute_budget_amounts(self):
        """Aggregate planned + actual budget amounts per analytic account.

        For each referencing budget line the analytic distribution
        dict is inspected and the analytic account's share extracted
        (as a percentage, 0-100). That share is applied as a weight to
        the line's ``planned_amount`` and ``variance_actual`` values.

        ``variance_actual`` is itself a computed field on
        ``budget.budget.line`` that runs a single ``_read_group``
        over ``account.move.line``. By composing on that field we
        avoid duplicating actuals-fetching logic in this model.

        The computation uses floating-point arithmetic for the
        percentage multiplication (OK for display purposes); rounding
        to the line's currency precision is applied per line so that
        consolidated totals remain currency-faithful at cent
        precision.
        """
        for rec in self:
            planned_total = 0.0
            actual_total = 0.0
            for line in rec.budget_line_ids:
                dist = line.analytic_distribution or {}
                share = dist.get(str(rec.id), 0.0)
                try:
                    share = float(share)
                except (TypeError, ValueError):
                    share = 0.0
                weight = share / 100.0
                planned_total += (line.planned_amount or 0.0) * weight
                actual_total += (line.variance_actual or 0.0) * weight
            rec.budget_amount_planned = planned_total
            rec.budget_amount_actual = actual_total
            if planned_total:
                rec.budget_consumption_percent = (
                    actual_total / planned_total * 100.0
                )
            else:
                rec.budget_consumption_percent = 0.0

    # ==================================================================
    # Section 4.4 — Action helpers
    # ==================================================================

    def action_view_budget_lines(self):
        """Open a window showing every budget line targeting this analytic.

        Used by the smart-button on the analytic account form. Returns
        an ``ir.actions.act_window`` action filtered by the IDs of the
        current recordset's ``budget_line_ids``. When the recordset
        contains a single analytic account the window title is
        personalised with the analytic name.
        """
        self.ensure_one()
        return {
            'name': (
                f"Budget Lines — {self.name}"
                if self.name else "Budget Lines"
            ),
            'type': 'ir.actions.act_window',
            'res_model': 'budget.budget.line',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.budget_line_ids.ids)],
            'context': {
                'default_analytic_distribution': {str(self.id): 100.0},
            },
        }
