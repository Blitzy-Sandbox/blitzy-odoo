# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""account_asset_management.wizard package.

Imports the TransientModel wizard sub-modules so their classes are
registered with the Odoo ORM at module install / upgrade time:

    * ``asset_modification_wizard`` -- AM-005 revaluation /
      impairment / impairment-reversal / useful-life / salvage
      adjustment wizard.
    * ``asset_disposal_wizard`` -- AM-006 sale / scrap / write-off
      disposal wizard.
"""

from . import asset_disposal_wizard, asset_modification_wizard
