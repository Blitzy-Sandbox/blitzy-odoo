# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Top-level package entry for ``account_budget_management`` (FEATURE-003).

This file is the Python package initializer required by Odoo's module
loader. Without it, the module folder cannot be imported as a Python
package and none of the model classes defined under ``models/`` are
registered with the ORM.

Subpackages loaded here:

* ``models`` — persistent and inherit-based models
  (:class:`BudgetBudget`, :class:`BudgetBudgetLine`,
  :class:`BudgetBudgetPeriod`, :class:`BudgetAlert`, and the
  ``account.analytic.account`` inherit extension).
* ``report`` — BM-003 Actual-vs-Budget AbstractModel helper
  (:class:`BudgetVsActualReport`). The subpackage is loaded at module
  install time so the helper is available to tests and any future
  QWeb / pivot consumer without requiring a dedicated action.
* ``wizard`` — BM-004 Variance Analysis interactive parameter
  wizard (:class:`BudgetVarianceWizard`). The subpackage hosts
  :class:`odoo.models.TransientModel` classes that collect user
  parameters and return ``ir.actions.act_window`` descriptors
  opening the appropriate reporting surfaces.

Precedent: ``addons/account_financial_report_ce/__init__.py`` uses the
same ``from . import models, report, wizard`` pattern. We follow the
OCA convention verbatim.
"""

from . import models, report, wizard
