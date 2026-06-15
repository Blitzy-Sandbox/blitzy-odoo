# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Account Move Extensions — Deferred Revenue
==========================================

Strictly-additive ``_inherit = 'account.move'`` extension that exposes the
reverse relation to :class:`account.deferred.schedule` created from invoice
lines on a given move. Also provides:

* A computed ``has_deferred_schedules`` Boolean used by the invoice form to
  conditionally display the "View Deferred Schedules" smart button.
* An action method ``action_view_deferred_schedules`` that returns a window
  action filtered to show only the schedules of the current invoice.

Integration Notes:
    - Extends ``account.move`` via ``_inherit`` — no core modifications.
    - Zero Enterprise module dependencies.
    - AGPL-3.0 licensing.
    - Reverse One2many creates no column on ``account_move`` (pure ORM metadata).
    - Computed ``has_deferred_schedules`` has ``store=False`` so it triggers
      no schema evolution or write amplification.

Rules Compliance (AAP §0.7):
    - R-01: No cross-module imports — only ``from odoo import ...``.
    - R-02: No Enterprise references.
    - R-03: Uses ``_inherit = 'account.move'`` as a string; NO ``_name``
      redefinition of the core model.
    - R-05: Fields added are (a) a reverse One2many to a NEW model
      (``account.deferred.schedule``), (b) a computed Boolean with
      ``store=False``. Zero core ``account.move`` fields are redefined.
    - R-07: No ``sudo()`` usage.
"""

from odoo import _, api, fields, models


class AccountMove(models.Model):
    """Extension of ``account.move`` exposing reverse navigation to deferred revenue schedules.

    Per rule R-05 (additive-only extension of core models), this class adds only a
    reverse One2many to :class:`account.deferred.schedule`, a computed boolean, and
    a user-invokable smart-button action. No existing core field is redefined.

    Integration Flow (DR-001 + DR-004):
        1. User creates a deferred schedule from an invoice line → the schedule's
           ``source_move_id`` is populated and this reverse ``deferred_schedule_ids``
           exposes the schedule on the invoice form.
        2. ``has_deferred_schedules`` drives the visibility of the smart button.
        3. Clicking the button invokes :meth:`action_view_deferred_schedules` which
           opens a filtered list of schedules for the current move.
    """

    _inherit = 'account.move'

    # -------------------------------------------------------------------------
    # DEFERRED REVENUE NAVIGATION FIELDS (DR-001 / DR-004)
    # -------------------------------------------------------------------------

    deferred_schedule_ids = fields.One2many(
        comodel_name='account.deferred.schedule',
        inverse_name='source_move_id',
        string='Deferred Revenue Schedules',
        copy=False,
        help=(
            "All deferred revenue schedules that were created from this invoice "
            "(or manual schedules linked to this move). Use the 'View Deferred "
            "Schedules' smart button to open the full list (DR-001 Scenario 1, "
            "DR-004 Scenario 4 drill-down)."
        ),
    )

    has_deferred_schedules = fields.Boolean(
        string='Has Deferred Schedules',
        compute='_compute_has_deferred_schedules',
        store=False,
        help=(
            "Technical field used to conditionally display the 'View Deferred "
            "Schedules' smart button in the invoice form. True when at least one "
            "``account.deferred.schedule`` references this move via "
            "``source_move_id``."
        ),
    )

    # -------------------------------------------------------------------------
    # COMPUTED FIELD METHOD
    # -------------------------------------------------------------------------

    @api.depends('deferred_schedule_ids')
    def _compute_has_deferred_schedules(self):
        """Derive ``has_deferred_schedules`` from the reverse One2many.

        Single-iteration over the recordset; the ORM prefetches
        ``deferred_schedule_ids`` efficiently so no extra query is needed.
        """
        for move in self:
            move.has_deferred_schedules = bool(move.deferred_schedule_ids)

    # -------------------------------------------------------------------------
    # SMART-BUTTON ACTION METHOD
    # -------------------------------------------------------------------------

    def action_view_deferred_schedules(self):
        """Return an ``ir.actions.act_window`` opening deferred schedules linked to this move.

        Invoked by a smart button on the ``account.move`` form view. Filters schedules
        by ``source_move_id = self.id`` so a user clicking the button on a specific
        invoice sees only that invoice's schedules. When the user clicks "Create" from
        the opened list, the ``default_*`` context keys pre-fill the new schedule with
        this move / partner / company so the DR-001 Scenario 1 flow is seamless.

        Returns:
            dict: Standard Odoo window action payload opening
                ``account.deferred.schedule`` in tree+form view, filtered to this
                move, with creation defaults for source move, partner, and company.
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Deferred Revenue Schedules'),
            'res_model': 'account.deferred.schedule',
            # Odoo 19 convention: 'list' replaces the legacy 'tree' alias.
            # Functionally identical (Odoo aliases tree -> list internally),
            # but the preferred style across this module's views is 'list'.
            'view_mode': 'list,form',
            'domain': [('source_move_id', '=', self.id)],
            'context': {
                'default_source_move_id': self.id,
                'default_partner_id': self.partner_id.id,
                'default_company_id': self.company_id.id,
            },
        }
