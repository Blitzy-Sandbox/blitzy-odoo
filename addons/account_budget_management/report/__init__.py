# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Report subpackage for ``account_budget_management`` (FEATURE-003).

This module collects the BM-003 "Actual vs Budget Reporting" helpers.
The :class:`~odoo.addons.account_budget_management.report.budget_vs_actual_report.BudgetVsActualReport`
AbstractModel lives here and is loaded at module install time via the
parent package's ``from . import report`` statement.
"""

from . import budget_vs_actual_report
