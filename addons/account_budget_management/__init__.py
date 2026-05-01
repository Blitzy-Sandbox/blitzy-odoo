# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Top-level package entry for the FEATURE-003 budget management addon.

This file is the Python package initializer required by Odoo's module
loader. Without it, the addon folder cannot be imported as a Python
package and none of the model classes defined in its subpackages are
registered with the ORM.

Subpackages loaded here (order-sensitive):

* ``models`` — persistent ORM classes (``budget.budget``,
  ``budget.budget.line``, ``budget.budget.period``, ``budget.alert``)
  plus the ``_inherit`` extension of ``account.analytic.account``.
  Loaded first so dependent classes can resolve every relational and
  ``self.env[...]`` reference at registration time.
* ``report`` — BM-003 actual-vs-budget :class:`AbstractModel` helper
  (``budget.vs.actual.report``). Loaded after ``models`` because the
  helper consumes persistent budget records.
* ``wizard`` — BM-004 variance analysis :class:`TransientModel`
  (``budget.variance.wizard``). Loaded after ``models`` because the
  wizard issues ``self.env['budget.budget.line']`` lookups when the
  user requests a variance run.

Comma order in the import statement below follows ruff's alphabetical
``I001`` convention; the only ordering that materially affects ORM
registration is that ``models`` must be one of the items in this
module-level import statement, which it is. Both ``report`` and
``wizard`` perform their cross-references at runtime via
``self.env[]`` lookups, so their relative position is irrelevant.
"""

from . import models, report, wizard
