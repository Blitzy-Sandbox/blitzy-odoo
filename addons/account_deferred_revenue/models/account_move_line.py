# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class AccountMoveLine(models.Model):
    """Extension of ``account.move.line`` adding relational links to deferred revenue schedules.

    Per rule R-05 (additive-only extension of core models), this class adds **only** relational
    fields that point to new models introduced by ``account_deferred_revenue``. No existing
    core field is redefined.

    Two back-references are exposed:

    * :attr:`deferred_schedule_id` — set on an invoice/bill line when a deferral schedule is
      created from that line (DR-001 Scenario 1). Populated by
      ``account.deferred.schedule.create`` in the sibling module model.
    * :attr:`deferred_line_id` — set on a journal-entry line when the cut-off wizard posts a
      recognition entry, linking each posted move line back to its source recognition line
      (DR-003 Scenario 1).

    Rules compliance:

    * R-01 (module independence): imports are limited to ``odoo`` only; no sibling-module
      imports.
    * R-03 (``_inherit`` vs ``_name``): uses ``_inherit`` as a string; no ``_name`` attribute.
    * R-05 (no core field redefinition): both fields are ``Many2one`` relational fields
      pointing to models that are net-new to this module. No core field on
      ``account.move.line`` is redefined.
    * R-07 (no unjustified ``sudo()``): no ``sudo()`` calls in this file.
    """

    _inherit = 'account.move.line'

    deferred_schedule_id = fields.Many2one(
        comodel_name='account.deferred.schedule',
        string='Deferred Schedule (source)',
        ondelete='set null',
        index=True,
        copy=False,
        help=(
            "If set, a deferred revenue schedule was created from this invoice line. "
            "Navigate via the schedule's 'Source Invoice Line' field (DR-001 Scenario 1)."
        ),
    )

    deferred_line_id = fields.Many2one(
        comodel_name='account.deferred.line',
        string='Recognition Line (posting)',
        ondelete='set null',
        index=True,
        copy=False,
        help=(
            "If set, this journal line was created by the cut-off wizard posting a "
            "deferred revenue recognition. Links back to the specific recognition "
            "line in the deferral schedule (DR-003 Scenario 1)."
        ),
    )
