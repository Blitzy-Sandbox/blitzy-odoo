# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Models sub-package for ``account_payment_followup``.

Import order matters here because Odoo builds the ``_name -> model class``
registry in the order classes are defined. Models that are referenced by
later models (via ``Many2one`` / ``One2many`` / ``Many2many`` fields with
string model names) should be registered first to ensure their
``ir.model.data`` entries exist before any XML records or CSV ACLs try to
resolve ``model_<name>`` external IDs.

Registration order (from least to most dependent):

1. ``account.followup.level`` (PF-001) — configuration model with no
   references to other new models; referenced by ``res.partner``,
   ``account.followup.line``, and ``account.followup.history`` below.
2. ``account.followup.line`` (PF-005) — denormalised per-partner aggregate
   that references ``res.partner`` and ``account.followup.level``.
3. ``account.followup.history`` (PF-004) — immutable audit-trail records
   that reference ``res.partner``, ``account.followup.level``, and
   ``account.move`` (M2M).
4. ``account.move`` — ``_inherit`` extension that adds computed
   ``days_overdue`` and ``is_disputed`` fields per PF-005.
5. ``account.move.line`` — ``_inherit`` extension that adds computed
   ``days_overdue`` and ``aging_bucket`` fields per PF-005 (already
   implemented at foundation).
6. ``res.partner`` — ``_inherit`` extension that adds PF-001 level
   assignment and PF-005 aging-bucket aggregation fields, plus the
   ``_get_overdue_invoices()`` helper used by ``account.followup.level``
   and the four mail templates.

All model files are imported at this checkpoint; the sibling
``wizard/`` and ``report/`` sub-packages are NOT imported by the module
``__init__.py`` because those folders are empty at the foundation
checkpoint (they will be populated by subsequent checkpoints for PF-003
report generation).
"""

from . import (
    account_followup_history,
    account_followup_level,
    account_followup_line,
    account_move,
    account_move_line,
    res_partner,
)
