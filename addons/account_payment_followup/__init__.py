# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Payment Follow-ups — Odoo 19.0 Community Edition.

Registers the :mod:`models` sub-package with Odoo's module loader so that
every model class (``account.followup.level``, ``account.followup.line``,
``account.followup.history``, and the ``_inherit`` extensions of
``account.move``, ``account.move.line``, and ``res.partner``) is imported
and registered with the ORM when the module is installed or upgraded.

Downstream sub-packages (``report`` for PF-003 and ``wizard`` for
PF-003 follow-up report wizard) will be appended to the import list in
subsequent checkpoints once those folders are populated. At the current
foundation checkpoint, only the ``models`` package exists on disk, so
importing non-existent sub-packages would raise ImportError at module
installation time.
"""

from . import models
