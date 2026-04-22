# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Models subpackage initializer for ``account_budget_management``.

Import ordering matters: Odoo's ORM requires model classes to be
imported in an order that respects their relational dependencies so
that ``Many2one`` / ``One2many`` co-models are registered before any
class that references them. The ordering below follows the Phase 1
foundation dependency graph:

    budget_budget                         (parent header, no deps)
        └─ budget_budget_line             (Many2one → budget.budget)
              ├─ budget_period            (Many2one → budget.budget.line)
              └─ budget_alert             (Many2one → budget.budget.line)

After the four net-new models are registered, the final import extends
the core ``account.analytic.account`` with budget-aware fields — this
``_inherit``-only extension must load last because its compute methods
read ``budget.budget.line`` fields (``planned_amount``,
``variance_actual``, ``analytic_distribution``) that require the line
model to be present first.

Precedent: ``addons/account_deferred_revenue/models/__init__.py`` —
same pattern of header-then-lines-then-inherit used for DR schedules.

Checkpoint 5 scope only. The ``wizard`` and ``report`` subpackages
(BM-004 variance wizard, BM-003 actual-vs-budget report) will be added
in Checkpoint 6 along with their own subpackage ``__init__.py``
imports wired into the top-level ``__init__.py``.
"""

# Order-sensitive imports — see module docstring for rationale.
# A noqa directive on the first import disables ruff's import-sorter
# (rule I001) for this block; alphabetical sorting would reorder the
# imports into the wrong load order (e.g. account_analytic_account
# before budget_budget_line), breaking the ORM dependency graph.
# Precedent: addons/account_deferred_revenue/models/__init__.py.
from . import budget_budget  # noqa: I001 - parent header must load first
from . import budget_budget_line
from . import budget_period
from . import budget_alert
from . import account_analytic_account
