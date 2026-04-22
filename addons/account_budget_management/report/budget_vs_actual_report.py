# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""BM-003 — Actual vs Budget Reporting (AbstractModel helper).

This module defines the :class:`BudgetVsActualReport` AbstractModel that
computes planned-vs-actual variance data for
:class:`~odoo.addons.account_budget_management.models.budget_budget.BudgetBudget`
headers and their
:class:`~odoo.addons.account_budget_management.models.budget_budget_line.BudgetBudgetLine`
children.

Design notes
------------
* **AbstractModel, not TransientModel.** The BM-003 reporting entry point
  has no persisted state; the computation is purely derived from the
  ``budget.budget`` / ``budget.budget.line`` recordsets and a small
  ``options`` dict of filters passed by the caller. Following the
  precedent set by
  :class:`~odoo.addons.account_financial_report_ce.models.financial_report.FinancialReportAbstract`,
  the shared aggregation logic lives on an ``AbstractModel`` so it can
  be exercised directly by the test suite (per Rule R-04 — ≥80 %
  coverage gate) and reused by any future QWeb or pivot consumer
  without duplication.

* **Single-query ``_read_group`` aggregation.** Following the
  performance contract established for BM-004 variance analysis
  (< 3 s for ≤ 1 000 budget lines per SM-002), all ``account.move.line``
  aggregation happens in a single ``_read_group`` call keyed by
  ``account_id``. Planned amounts come directly from the budget lines
  — no aggregation is required on the planned side because
  ``budget.budget.line.planned_amount`` is authored 1:1 per line.

* **Hierarchical enrichment.** When the caller passes an
  ``analytic_plan_id`` option (BM-003 Scenario 2), the helper enriches
  each row's ``analytic_distribution`` field with an aggregated
  ``{analytic_account_name: amount}`` map derived from the posted
  ``account.move.line`` records whose ``analytic_distribution`` JSON
  resolves to analytic accounts belonging to the requested plan
  (descendant-aware via ``parent_path``).

* **Rules compliance.** R-01 (no sibling-module imports), R-02 (no
  Enterprise-edition imports), R-03 (``_name`` only — net-new abstract
  model), R-05 (no field redefinition on core models; this file only
  reads ``account.move.line.balance`` via ``_read_group``), R-07 (no
  ``sudo()`` calls).
"""

from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import UserError

# -----------------------------------------------------------------------
# Module-level threshold constants (BM-003 Scenario 5 — consumption
# classification).
#
# The threshold buckets are inclusive-exclusive at ``CONSUMPTION_THRESHOLD_NORMAL``
# (``>= 80 %`` → warning) and inclusive at ``CONSUMPTION_THRESHOLD_WARNING``
# (``<= 100 %`` → still warning; strictly ``> 100 %`` → alert). This
# matches the boundary behaviour asserted by ``tests/test_bm_003.py``:
#
#     _classify_consumption(79.99) == "normal"
#     _classify_consumption(80.00) == "warning"
#     _classify_consumption(100.00) == "warning"
#     _classify_consumption(100.01) == "alert"
# -----------------------------------------------------------------------
CONSUMPTION_THRESHOLD_NORMAL = 80.0
CONSUMPTION_THRESHOLD_WARNING = 100.0


class BudgetVsActualReport(models.AbstractModel):
    """BM-003 — Actual vs Budget Report helper (AbstractModel).

    The report model is a pure service: it has no database table, no
    persisted fields, and no UI of its own. Instead it exposes a
    collection of ``@api.model`` helper methods that build the data
    dictionary consumed by the BM-003 pivot / graph / list views and
    by ``addons/account_budget_management/tests/test_bm_003.py``.

    Public API
    ----------
    * :meth:`_get_report_values` — top-level entry point; returns the
      canonical report dictionary including ``rows`` and
      ``ytd_totals``.
    * :meth:`_get_budget_lines` — builds one row per
      ``budget.budget.line`` covering planned, actual, variance,
      consumed-percentage and threshold-status fields.
    * :meth:`_build_actuals_domain` — constructs the
      ``account.move.line`` domain used by the actuals
      aggregation. Reusable by callers who wish to drill down
      into the same window.
    * :meth:`_get_actual_amounts` — executes the single
      ``_read_group`` query that sums ``balance`` per account.
    * :meth:`_get_hierarchical_data` — enriches the flat rows with
      analytic-plan-aware aggregation (BM-003 Scenario 2).
    * :meth:`_get_ytd_totals` — computes overall summary totals
      across all rows (BM-003 Scenario 3 — multi-period YTD).
    * :meth:`_classify_consumption` — classifies a consumption
      percentage into ``normal`` / ``warning`` / ``alert`` buckets
      (BM-003 Scenario 5).
    """

    _name = "budget.vs.actual.report"
    _description = "Budget vs Actual Report (BM-003)"

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    @api.model
    def _get_report_values(self, docids, data=None):
        """Return the canonical BM-003 data dictionary.

        This is the standard Odoo report-helper entry point matching the
        precedent shape used by
        ``addons.account_financial_report_ce.models.financial_report.FinancialReportAbstract``.

        :param list[int] docids: ``budget.budget`` record IDs to report
            on (typically a single fiscal-year budget, but the helper
            supports a list of IDs for multi-budget roll-ups).
        :param dict data: optional filter dict containing any subset of:

            * ``date_from`` (str / :class:`datetime.date`) — inclusive
              start of the actuals window. Defaults to no lower bound.
            * ``date_to`` (str / :class:`datetime.date`) — inclusive
              end of the actuals window. Defaults to no upper bound.
            * ``analytic_plan_id`` (int) — when set, activates the
              hierarchical enrichment path (BM-003 Scenario 2)
              filtering by the analytic plan and its descendants.
            * ``company_ids`` (list[int]) — multi-company scope.
              Defaults to ``self.env.companies.ids``.
            * ``hierarchical_view`` (bool) — explicit opt-in flag for
              hierarchical enrichment. ``analytic_plan_id`` implies
              this.

        :returns: dict with keys ``doc_ids``, ``doc_model``, ``docs``,
            ``data``, ``rows`` (list of row dicts — see
            :meth:`_get_budget_lines`) and ``ytd_totals`` (summary
            totals — see :meth:`_get_ytd_totals`).
        :rtype: dict
        """
        data = data or {}
        docids_list = list(docids) if docids else []
        docs = self.env["budget.budget"].browse(docids_list)
        rows = self._get_budget_lines(docs, data)
        ytd_totals = self._get_ytd_totals(rows)
        return {
            "doc_ids": docids_list,
            "doc_model": "budget.budget",
            "docs": docs,
            "data": data,
            "rows": rows,
            "ytd_totals": ytd_totals,
        }

    # ------------------------------------------------------------------
    # Core aggregation
    # ------------------------------------------------------------------

    @api.model
    def _get_budget_lines(self, budgets, options):
        """Build the BM-003 report rows for a set of budgets.

        For each ``budget.budget.line`` in the given budgets this method:

        1. Reads ``planned_amount`` directly from the line (already
           authored 1:1 per line — no aggregation required).
        2. Aggregates posted ``account.move.line`` entries matching the
           line's ``account_id`` via a single ``_read_group`` call
           (single-SQL performance path — see :meth:`_get_actual_amounts`).
        3. Computes ``variance_amount = planned - actual``,
           ``consumed_percent = (actual / planned) * 100`` and the
           threshold classification via
           :meth:`_classify_consumption`.
        4. When ``options['analytic_plan_id']`` (or
           ``options['hierarchical_view']``) is truthy, delegates to
           :meth:`_get_hierarchical_data` to enrich each row's
           ``analytic_distribution`` field with plan-aware aggregated
           analytic breakdowns derived from the posted move lines.

        :param budgets: ``budget.budget`` recordset (may be empty — an
            empty recordset yields an empty result list).
        :type budgets: :class:`odoo.models.Model`
        :param dict options: see :meth:`_get_report_values` for the
            supported keys.

        :returns: list of row dicts. Each row contains the keys
            ``budget_line_id``, ``budget_id``, ``account_id``,
            ``account_code``, ``account_name``,
            ``analytic_distribution``, ``planned_amount``,
            ``actual_amount``, ``variance_amount``,
            ``consumed_percent`` and ``threshold_status``.
        :rtype: list[dict]
        """
        options = options or {}
        budget_lines = budgets.mapped("line_ids") if budgets else self.env["budget.budget.line"]
        if not budget_lines:
            return []

        # Build the aggregation domain once per call.
        domain = self._build_actuals_domain(budget_lines, options)

        # Single-SQL aggregation per the BM-004 performance pattern.
        actuals_by_account = self._get_actual_amounts(domain)

        rows = []
        for line in budget_lines:
            account = line.account_id
            planned = line.planned_amount or 0.0
            actual = actuals_by_account.get(account.id, 0.0)
            variance = planned - actual
            consumed = (actual / planned * 100.0) if planned else 0.0
            rows.append(
                {
                    "budget_line_id": line.id,
                    "budget_id": line.budget_id.id,
                    "account_id": account.id,
                    "account_code": account.code or "",
                    "account_name": account.name or "",
                    "analytic_distribution": dict(line.analytic_distribution or {}),
                    "planned_amount": planned,
                    "actual_amount": actual,
                    "variance_amount": variance,
                    "consumed_percent": consumed,
                    "threshold_status": self._classify_consumption(consumed),
                },
            )

        # BM-003 Scenario 2 — hierarchical enrichment.
        if options.get("hierarchical_view") or options.get("analytic_plan_id"):
            rows = self._get_hierarchical_data(
                rows,
                plan_id=options.get("analytic_plan_id"),
                options=options,
            )

        return rows

    # ------------------------------------------------------------------
    # Domain construction
    # ------------------------------------------------------------------

    @api.model
    def _build_actuals_domain(self, budget_lines, options):
        """Construct the ``account.move.line`` domain used for actuals.

        Constraints applied (per BM-003 Scenario 1 and Scenario 4):

        * ``parent_state = 'posted'`` — draft entries are excluded.
        * ``account_id IN budget_lines.mapped('account_id').ids`` —
          only accounts referenced by budget lines participate.
        * ``company_id IN options['company_ids'] or
          self.env.companies.ids`` — multi-company safe.
        * Optional ``date >= options['date_from']`` /
          ``date <= options['date_to']`` window. Date values are
          normalised through ``fields.Date.to_date`` so callers may
          pass either :class:`datetime.date` objects or ISO strings.

        :param budget_lines: ``budget.budget.line`` recordset whose
            accounts define the ``account_id`` filter clause. The
            method works with any recordset (single line or multiple
            lines) — the test suite directly exercises the
            single-line call path.
        :type budget_lines: :class:`odoo.models.Model`
        :param dict options: see :meth:`_get_report_values`.

        :returns: Odoo domain list suitable for
            ``account.move.line._read_group`` / ``search``.
        :rtype: list[tuple]

        :raises UserError: if both ``date_from`` and ``date_to`` are
            provided and ``date_from > date_to`` (defensive
            consistency check — the normal BM-003 UX validates this
            upstream, but this guard protects programmatic callers).
        """
        # NOTE: no ``self.ensure_one()`` here — AbstractModel @api.model
        # methods are routinely invoked on empty recordsets (e.g.,
        # ``self.env['budget.vs.actual.report']._build_actuals_domain(...)``)
        # and ``ensure_one`` would raise ``ValueError: Expected singleton``.
        options = options or {}

        account_ids = budget_lines.mapped("account_id").ids if budget_lines else []
        company_ids = options.get("company_ids") or self.env.companies.ids

        domain = [
            ("parent_state", "=", "posted"),
            ("account_id", "in", account_ids),
            ("company_id", "in", company_ids),
        ]

        date_from = options.get("date_from")
        date_to = options.get("date_to")

        # Normalise dates through ``fields.Date.to_date`` — accepts both
        # ``datetime.date`` instances and ISO strings.
        if date_from:
            date_from = fields.Date.to_date(date_from)
        if date_to:
            date_to = fields.Date.to_date(date_to)

        if date_from and date_to and date_from > date_to:
            msg = _(
                "Invalid date range: date_from (%(df)s) is after "
                "date_to (%(dt)s).",
                df=date_from,
                dt=date_to,
            )
            raise UserError(msg)

        if date_from:
            domain.append(("date", ">=", date_from))
        if date_to:
            domain.append(("date", "<=", date_to))

        return domain

    # ------------------------------------------------------------------
    # Single-SQL actuals aggregation
    # ------------------------------------------------------------------

    @api.model
    def _get_actual_amounts(self, domain):
        """Aggregate ``account.move.line.balance`` by ``account_id``.

        This is the single-query performance path. For ≤ 1 000 budget
        lines the report render is dominated by this one ``_read_group``
        SQL execution — satisfying the SM-002 < 3 s target inherited
        by BM-003 reporting. No per-row iteration over move lines
        occurs.

        :param list[tuple] domain: Odoo domain built by
            :meth:`_build_actuals_domain` (or an equivalent caller).

        :returns: mapping ``{account.account.id: sum(balance)}``.
            Accounts with no matching posted entries are **absent**
            from the result (the caller should fall back to 0.0 on
            missing keys).
        :rtype: dict[int, float]
        """
        actuals = self.env["account.move.line"]._read_group(
            domain=domain,
            groupby=["account_id"],
            aggregates=["balance:sum"],
        )
        return {
            account.id: (balance_sum or 0.0)
            for account, balance_sum in actuals
            if account
        }

    # ------------------------------------------------------------------
    # Hierarchical / analytic-aware enrichment (BM-003 Scenario 2)
    # ------------------------------------------------------------------

    @api.model
    def _get_hierarchical_data(self, rows, plan_id=None, options=None):
        """Enrich flat rows with analytic-plan-aware breakdowns.

        When a caller requests hierarchical reporting (by passing
        ``analytic_plan_id`` to :meth:`_get_report_values` — BM-003
        Scenario 2), each row's ``analytic_distribution`` field is
        rewritten as a ``{analytic_account_name: balance_amount}``
        dict derived from the posted ``account.move.line`` records
        matching the row's account and the report window.

        The implementation uses the standard Odoo
        ``account.analytic.plan._parent_store`` / ``parent_path``
        pattern to resolve descendant plans in a single lookup, so
        passing a root plan automatically scopes to all of its
        children.

        :param list[dict] rows: flat row list produced by
            :meth:`_get_budget_lines`.
        :param int plan_id: optional ``account.analytic.plan`` ID.
            When ``None``, all analytic accounts participate in the
            aggregation (no plan filter).
        :param dict options: optional — the same options dict passed
            to :meth:`_get_report_values`. Used to derive the date /
            company filters for the move-line query so the enriched
            breakdowns reflect the same window as the flat actuals.

        :returns: the same row list with ``analytic_distribution``
            replaced by an aggregated ``{name: amount}`` mapping
            whenever at least one matching analytic-bearing move line
            exists. Rows without matching analytic data retain their
            original ``analytic_distribution``.
        :rtype: list[dict]
        """
        if not rows:
            return []

        options = options or {}

        # Resolve the set of permitted plan IDs via ``parent_path``.
        # When ``plan_id`` is omitted every analytic account is eligible.
        plan_model = self.env["account.analytic.plan"]
        permitted_plan_ids = None
        if plan_id:
            plan = plan_model.browse(plan_id)
            if plan.exists():
                if plan.parent_path:
                    descendant_plans = plan_model.search(
                        [("parent_path", "=like", f"{plan.parent_path}%")],
                    )
                    permitted_plan_ids = set(descendant_plans.ids) or {plan.id}
                else:
                    permitted_plan_ids = {plan.id}
            else:
                permitted_plan_ids = set()

        # Build the single move-line query for all rows' accounts.
        account_ids = [row["account_id"] for row in rows if row.get("account_id")]
        if not account_ids:
            return rows

        move_line_domain = [
            ("parent_state", "=", "posted"),
            ("account_id", "in", account_ids),
        ]

        date_from = options.get("date_from")
        date_to = options.get("date_to")
        if date_from:
            move_line_domain.append(("date", ">=", fields.Date.to_date(date_from)))
        if date_to:
            move_line_domain.append(("date", "<=", fields.Date.to_date(date_to)))

        company_ids = options.get("company_ids") or self.env.companies.ids
        if company_ids:
            move_line_domain.append(("company_id", "in", company_ids))

        move_lines = self.env["account.move.line"].search(move_line_domain)

        # Group move lines by account for O(n) per-row lookup.
        lines_by_account = defaultdict(list)
        for move_line in move_lines:
            lines_by_account[move_line.account_id.id].append(move_line)

        # Collect analytic account IDs referenced across all eligible
        # move lines — batch-browse once to resolve ``name`` / ``plan_id``
        # without per-iteration ORM lookups.
        analytic_id_set = set()
        for mls in lines_by_account.values():
            for move_line in mls:
                dist = move_line.analytic_distribution or {}
                for key_str in dist:
                    try:
                        analytic_id_set.add(int(key_str))
                    except (TypeError, ValueError):
                        continue

        analytic_model = self.env["account.analytic.account"]
        if analytic_id_set:
            analytic_records = analytic_model.browse(sorted(analytic_id_set)).exists()
        else:
            analytic_records = analytic_model

        analytic_info = {
            analytic.id: (analytic.name or "", analytic.plan_id.id)
            for analytic in analytic_records
        }

        # Enrich each row with its plan-filtered analytic breakdown.
        for row in rows:
            account_id = row.get("account_id")
            if not account_id:
                continue

            analytic_totals = defaultdict(float)
            for move_line in lines_by_account.get(account_id, []):
                dist = move_line.analytic_distribution or {}
                balance = move_line.balance or 0.0
                for key_str, pct in dist.items():
                    try:
                        aid = int(key_str)
                    except (TypeError, ValueError):
                        continue
                    info = analytic_info.get(aid)
                    if not info:
                        continue
                    analytic_name, analytic_plan_id = info
                    if (
                        permitted_plan_ids is not None
                        and analytic_plan_id not in permitted_plan_ids
                    ):
                        continue
                    contribution = balance * (pct or 0.0) / 100.0
                    analytic_totals[analytic_name] += contribution

            if analytic_totals:
                row["analytic_distribution"] = dict(analytic_totals)

        return rows

    # ------------------------------------------------------------------
    # YTD totals (BM-003 Scenario 3)
    # ------------------------------------------------------------------

    @api.model
    def _get_ytd_totals(self, rows):
        """Compute summary totals across all rows.

        Called by :meth:`_get_report_values` to populate the report
        header / summary card. For multi-period YTD reporting (BM-003
        Scenario 3) the caller constructs the date window spanning
        the year-to-date range and passes it via ``options`` — this
        method merely sums the row-level values that already reflect
        the window.

        :param list[dict] rows: the list of row dicts produced by
            :meth:`_get_budget_lines`.

        :returns: dict containing:

            * ``total_planned`` (float) — ``sum(row.planned_amount)``
            * ``total_actual`` (float) — ``sum(row.actual_amount)``
            * ``total_variance`` (float) — ``total_planned - total_actual``
            * ``total_consumed_percent`` (float) — overall consumption
              pct or ``0.0`` when ``total_planned`` is zero

            The legacy schema-parity aliases ``planned_total``,
            ``actual_total``, ``variance_total`` and
            ``consumed_percent_total`` are also included to support
            either naming convention at the caller side.
        :rtype: dict
        """
        planned_total = 0.0
        actual_total = 0.0
        for row in rows:
            planned_total += row.get("planned_amount", 0.0) or 0.0
            actual_total += row.get("actual_amount", 0.0) or 0.0
        variance_total = planned_total - actual_total
        consumed_percent_total = (
            (actual_total / planned_total * 100.0) if planned_total else 0.0
        )
        return {
            # Primary keys (test-contract naming, ``total_*`` prefix).
            "total_planned": planned_total,
            "total_actual": actual_total,
            "total_variance": variance_total,
            "total_consumed_percent": consumed_percent_total,
            # Schema-parity aliases (``*_total`` suffix).
            "planned_total": planned_total,
            "actual_total": actual_total,
            "variance_total": variance_total,
            "consumed_percent_total": consumed_percent_total,
        }

    # ------------------------------------------------------------------
    # Threshold classification (BM-003 Scenario 5)
    # ------------------------------------------------------------------

    @api.model
    def _classify_consumption(self, consumed_percent):
        """Classify a consumption percentage into BM-003 buckets.

        The classification boundaries are:

        ====================  ====================================
        Consumption range      Status
        ====================  ====================================
        ``0 <= x < 80``       ``"normal"``
        ``80 <= x <= 100``    ``"warning"``
        ``x > 100``           ``"alert"``
        ====================  ====================================

        The boundary behaviour is exactly as asserted by
        ``tests/test_bm_003.py``:

        * ``_classify_consumption(79.99)`` → ``"normal"``
        * ``_classify_consumption(80.00)`` → ``"warning"``
        * ``_classify_consumption(100.00)`` → ``"warning"``
        * ``_classify_consumption(100.01)`` → ``"alert"``

        :param float consumed_percent: the consumption percentage,
            typically in ``[0, +inf)``. May exceed 100 when actuals
            exceed planned.

        :returns: one of ``"normal"``, ``"warning"`` or ``"alert"``.
        :rtype: str
        """
        if consumed_percent > CONSUMPTION_THRESHOLD_WARNING:
            return "alert"
        if consumed_percent >= CONSUMPTION_THRESHOLD_NORMAL:
            return "warning"
        return "normal"
