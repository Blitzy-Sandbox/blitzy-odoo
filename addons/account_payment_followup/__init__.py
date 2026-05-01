# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Payment Follow-ups — Odoo 19.0 Community Edition.

Registers the :mod:`models`, :mod:`report`, and :mod:`wizard` sub-packages
with Odoo's module loader so that every model class
(``account.followup.level``, ``account.followup.line``,
``account.followup.history``, the ``_inherit`` extensions of
``account.move``, ``account.move.line``, and ``res.partner``,
the report parser AbstractModel
``report.account_payment_followup.followup_aged_receivables``, and the
PF-003 wizard TransientModel ``account.followup.report.wizard``) is
imported and registered with the ORM when the module is installed or
upgraded.

Subpackage Inventory:
    - ``models``: Net-new model classes plus core-model ``_inherit``
      extensions for follow-up workflows.
    - ``report``: AbstractModel parser for the PF-003 Aged Receivables
      Follow-up Report.
    - ``wizard``: TransientModel-based wizard for PF-003 — collects
      filter parameters and dispatches PDF / XLSX exports.
"""

from . import models, report, wizard
