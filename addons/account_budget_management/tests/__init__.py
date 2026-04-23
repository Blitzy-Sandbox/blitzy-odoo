# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Test package for ``account_budget_management``.

Registers per-story test modules with Odoo's test discovery machinery.
Odoo loads this package when ``--test-enable`` is passed together with
``-i`` or ``-u``; each imported module's ``@tagged`` classes are then
eligible for execution via the ``--test-tags`` filter.

Per-story tests currently registered:

* ``test_bm_003`` — BM-003: Actual vs Budget Reporting
  (``budget.vs.actual.report`` AbstractModel, ``read_group`` actuals
  aggregation, hierarchical grouping, multi-period totals).
* ``test_bm_005`` — BM-005: Budget Alerts
  (``budget.alert`` model, threshold evaluation cron, immutability
  enforcement, severity mapping, recipient configuration, notification
  dispatch, deduplication, SQL constraint).
"""
from . import test_bm_003, test_bm_005
