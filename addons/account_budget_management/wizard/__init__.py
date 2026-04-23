# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Wizard package for ``account_budget_management`` (FEATURE-003).

This subpackage hosts ``TransientModel`` wizards — interactive,
short-lived records used to collect user parameters before launching
a view, report, or action.

Modules registered here:

* ``budget_variance_wizard`` — BM-004 Variance Analysis wizard.
  Provides the parameter-selection UI that drives the variance list /
  pivot / graph views on ``budget.budget.line``. Users select a
  target budget, a date range, a period granularity, optional
  analytic-plan / analytic-account filters, a favorability filter,
  and an optional consumption-threshold filter; the wizard's
  ``action_open_variance()`` returns an ``ir.actions.act_window``
  that opens the filtered variance list.

Precedent: ``addons/account_financial_report_ce/wizard/__init__.py``
follows the same single-statement ``from . import <wizard_module>``
pattern. We adopt the convention verbatim.
"""

from . import budget_variance_wizard
