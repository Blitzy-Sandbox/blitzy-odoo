# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""account_asset_management package entry point.

Imports the ``models`` and ``wizard`` sub-packages so their
``models.Model`` / ``models.TransientModel`` subclasses are
registered with the Odoo ORM at module install / upgrade time.

Per AAP Rule R-01 (Module Independence), this package never
imports from any sibling Community Edition module
(``account_budget_management``, ``account_deferred_revenue``,
``account_payment_followup``).
"""

from . import models, wizard
