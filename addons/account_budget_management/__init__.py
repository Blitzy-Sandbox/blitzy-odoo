# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Top-level package entry for ``account_budget_management`` (FEATURE-003).

This file is the Python package initializer required by Odoo's module
loader. Without it, the module folder cannot be imported as a Python
package and none of the model classes defined under ``models/`` are
registered with the ORM.

At this checkpoint (Checkpoint 5 — BM Foundation), only the ``models``
subpackage exists. Subsequent checkpoints will introduce ``wizard``
and ``report`` subpackages (BM-004 variance wizard, BM-003 actual-vs-
budget report); their imports will be added here at that time.

Precedent: ``addons/account_deferred_revenue/__init__.py`` — a minimal
``from . import models`` entry. We follow the same OCA convention.
"""

from . import models
