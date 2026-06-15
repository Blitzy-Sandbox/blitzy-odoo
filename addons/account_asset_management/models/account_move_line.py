# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Asset-line back-reference for account.move.line (FEATURE-004, AM-004).

This module extends ``account.move.line`` with a single additive
``fields.Many2one`` field that back-references the depreciation-schedule
line which produced the journal line. This enables drill-down from a
posted depreciation journal line to its originating schedule entry for
audit purposes and supports the AM-003 Depreciation Board's navigation
back-and-forth with the general ledger.

Context
-------
When the AM-004 depreciation cron (``account.asset._cron_post_depreciation_entries``)
posts a scheduled depreciation ``account.move``, the move contains exactly
two ``account.move.line`` rows:

    * Debit  -> depreciation expense account
    * Credit -> accumulated depreciation (contra-asset) account

Both lines carry the same ``asset_depreciation_line_id`` back-reference so
that either line's "Related Records" view or its chatter can navigate to
the originating schedule entry on ``account.asset.depreciation.line``.
The reverse relationship is defined on
``account.asset.depreciation.line.move_id`` (one ``account.move`` per
schedule line, but multiple ``account.move.line`` rows per move).

AAP Rule Compliance
-------------------
* R-01 (Module independence) -- No imports from sibling Community Edition
  modules (``account_budget_management``, ``account_deferred_revenue``,
  ``account_payment_followup``). Only the ``odoo`` framework is imported.
* R-02 (No Enterprise dependencies) -- No Odoo Enterprise module is
  referenced; the comodel ``account.asset.depreciation.line`` is defined
  locally in this Community Edition module.
* R-03 (``_inherit`` / ``_name`` correctness) -- Uses ``_inherit =
  'account.move.line'`` WITHOUT ``_name``. The core ``account.move.line``
  model registered by ``addons/account/models/account_move_line.py`` is
  extended in place; no new model is declared here.
* R-05 (No core field redefinition) -- ONLY the single additive
  relational field ``asset_depreciation_line_id`` is added. NO existing
  core field (``debit``, ``credit``, ``account_id``, ``balance``,
  ``move_id``, ``partner_id``, ``name``, ``date``, ``amount_currency``,
  ``currency_id``, ``journal_id``, ``company_id``, ``ref``, ``sequence``,
  ``tax_ids``, ``reconcile_model_id``, etc.) is redefined or
  shadowed. NO method overrides (``create``, ``write``, ``unlink``,
  ``_post``, ``_prepare_*``, ``_compute_*`` for any existing field)
  appear in this file.
* R-06 (Scheduled jobs via XML ``ir.cron``) -- Not applicable here; the
  cron that populates this back-reference is defined in
  ``data/depreciation_cron.xml`` and invokes
  ``account.asset._cron_post_depreciation_entries``.
* R-07 (No unjustified ``sudo``) -- No ``sudo()`` calls appear in this
  file.
"""

from odoo import fields, models


class AccountMoveLine(models.Model):
    """Extend ``account.move.line`` with an asset-depreciation back-reference.

    The single additive field ``asset_depreciation_line_id`` is populated
    by the AM-004 depreciation cron when it posts a journal entry for a
    depreciation-schedule line. The reverse relationship is defined on
    ``account.asset.depreciation.line.move_id`` (one ``account.move`` per
    schedule line but one ``account.move.line`` per debit/credit row).

    This class uses ``_inherit`` WITHOUT ``_name`` so the single additive
    field is added directly to the existing ``account_move_line`` table
    in place (Odoo merges the field into the core model's registry at
    ``setup_models()`` time).
    """

    _inherit = 'account.move.line'

    asset_depreciation_line_id = fields.Many2one(
        comodel_name='account.asset.depreciation.line',
        string='Asset Depreciation Line',
        ondelete='restrict',
        index=True,
        copy=False,
        help=(
            'The asset depreciation schedule line that produced this '
            'journal line. Populated automatically by the AM-004 '
            'depreciation cron when posting a scheduled depreciation '
            'entry. Enables drill-down from the general ledger back to '
            'the asset depreciation schedule (AM-003 board). '
            'ondelete="restrict" preserves the audit trail by preventing '
            'accidental deletion of the schedule line while journal '
            'lines still reference it; copy=False ensures that '
            'duplicated journal entries do not silently carry the '
            'reference forward; index=True enables efficient reverse '
            'navigation from schedule line to posted journal lines.'
        ),
    )
