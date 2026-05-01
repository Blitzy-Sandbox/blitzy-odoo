# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""ORM Model Package for FEATURE-004 Asset Management.

Imports are intentionally ordered by dependency: foundational models (with
no internal FK dependencies) first, then dependent models, then core-model
extensions (``_inherit``) last.

    1. ``account_asset_category`` -- template defaults (foundational).
    2. ``account_asset`` -- fixed-asset header (depends on category).
    3. ``account_asset_depreciation_line`` -- depreciation schedule
       (depends on asset).
    4. ``account_move`` -- ``_inherit = 'account.move'`` (references asset).
    5. ``account_move_line`` -- ``_inherit = 'account.move.line'``
       (references depreciation line).

Changing this order may cause registry-resolution errors at module install
when Odoo attempts to resolve ``fields.Many2one('account.asset', ...)``
before the target model is defined.

Rationale per the Agent Action Plan (AAP) for FEATURE-004:

* ``account_asset_category`` is a pure LEAF model with no internal FK
  dependencies on other models in this package, so it must be registered
  first. ``account_asset.category_id = fields.Many2one(
  'account.asset.category', ...)`` requires the category model to be known
  to the ORM registry before the asset class is built.
* ``account_asset`` registers ``account.asset`` (with the
  ``mail.thread`` / ``mail.activity.mixin`` mixins) and must precede
  ``account_asset_depreciation_line`` because
  ``account.asset.depreciation.line.asset_id = fields.Many2one(
  'account.asset', ondelete='cascade', ...)`` references the asset model.
* ``account_asset_depreciation_line`` must precede ``account_move_line``
  because ``account.move.line.asset_depreciation_line_id =
  fields.Many2one('account.asset.depreciation.line', ondelete='restrict',
  index=True, copy=False)`` references the schedule-line model.
* ``account_move`` (an ``_inherit = 'account.move'`` extension) adds an
  ``asset_id`` Many2one back-reference to ``account.asset`` and an
  ``asset_entry_type`` Selection field. It must follow ``account_asset``
  but is placed before ``account_move_line`` to preserve the natural
  "move before move line" conceptual order observed throughout the Odoo
  ``account`` core module.
* ``account_move_line`` (an ``_inherit = 'account.move.line'`` extension)
  adds the ``asset_depreciation_line_id`` Many2one back-reference and is
  imported LAST so that every model it references is already registered.

Compliance posture:

* R-01 (module independence): this file contains only relative
  ``from . import X`` statements; no sibling new module is imported.
* R-03 (``_inherit`` / ``_name`` correctness): each imported submodule
  uses ``_name`` for net-new models and ``_inherit`` (without ``_name``)
  for core-model extensions. This package initializer enforces the
  ordering that lets those declarations resolve cleanly.
* R-05 (no core-field redefinition): the inherited ``account_move`` /
  ``account_move_line`` extensions add only computed / relational fields
  pointing to net-new models -- they never redefine an existing core
  column. The ordering chosen here ensures those references resolve
  against models already present in the ORM registry.

Precedent: the explicit-ordering pattern is consistent with
``addons/account_financial_report_ce/models/__init__.py`` ("Import order
is critical: financial_report defines the abstract base model"). Each
``from . import X`` statement is on its own line for maximum diff
clarity and to follow the AAP's prescribed form exactly. Adding a new
model file to this package means appending one more
``from . import <new_module>`` line in the position that respects its
dependency on the models above it.
"""

from . import account_asset_category  # noqa: I001 - dependency-ordered (foundational template first)
from . import account_asset
from . import account_asset_depreciation_line
from . import account_move
from . import account_move_line
