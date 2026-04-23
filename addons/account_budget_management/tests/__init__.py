# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Test package for ``account_budget_management``.

Registers per-story test modules with Odoo's test discovery machinery.
Odoo loads this package when ``--test-enable`` is passed together with
``-i`` or ``-u``; each imported module's ``@tagged`` classes are then
eligible for execution via the ``--test-tags`` filter.

Per-story tests registered:

* ``test_bm_001`` — BM-001: Budget Definition
  (``budget.budget`` / ``budget.budget.line`` models, state machine,
  computed totals, SQL unique-per-company constraint, account-type
  validation, analytic distribution, copy semantics, and the
  ``account.analytic.account`` ``_inherit`` extension).
* ``test_bm_002`` — BM-002: Budget Period Allocation
  (``budget.budget.period`` model, equal distribution with rounding
  remainder on the final period, copy-from-previous-budget with
  year offset, date-range splitting, audit trail via ``write()``
  override, sum-matches-line and within-budget-window constraints).
* ``test_bm_003`` — BM-003: Actual vs Budget Reporting
  (``budget.vs.actual.report`` AbstractModel, ``read_group`` actuals
  aggregation, hierarchical grouping, multi-period totals).
* ``test_bm_004`` — BM-004: Variance Analysis
  (variance computation on ``budget.budget.line``,
  ``budget.variance.wizard`` ``TransientModel`` default_get, onchange,
  constraints, domain building, pure helpers, and drill-down actions).
* ``test_bm_005`` — BM-005: Budget Alerts
  (``budget.alert`` model, threshold evaluation cron, immutability
  enforcement, severity mapping, recipient configuration, notification
  dispatch, deduplication, SQL constraint, and R-08 disjoint-field
  namespace verification between ``variance_*`` and ``alert_*``).
"""
from . import (
    test_bm_001,
    test_bm_002,
    test_bm_003,
    test_bm_004,
    test_bm_005,
)
