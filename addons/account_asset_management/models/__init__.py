# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""account_asset_management.models package.

The Odoo ORM resolves Many2one / One2many cross-references at
``setup_models()`` time (after every model class has been imported
and registered in the registry), so the relative order of these
imports does not affect runtime behaviour. We therefore use
alphabetical order, which is the convention adopted by FEATURE-002
(``account_bank_reconciliation_ce``) and matches the ``ruff`` import
sorter (``I001``) configuration in ``ruff.toml``.

Models registered (in alphabetical order):

    * ``account.asset`` (net-new) -- central asset model
    * ``account.asset.category`` (net-new) -- category template
    * ``account.asset.depreciation.line`` (net-new) -- schedule lines
    * ``account.move`` (``_inherit``) -- adds ``asset_id`` /
      ``asset_entry_type`` for asset-driven journal entries
    * ``account.move.line`` (``_inherit``) -- adds
      ``asset_depreciation_line_id`` back-reference (already present
      in the existing extension file).
"""

from . import (
    account_asset,
    account_asset_category,
    account_asset_depreciation_line,
    account_move,
    account_move_line,
)
