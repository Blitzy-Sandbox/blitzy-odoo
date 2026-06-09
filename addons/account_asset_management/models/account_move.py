# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Asset back-reference for account.move (FEATURE-004, AM-001/AM-004/AM-005/AM-006).

This module extends ``account.move`` with two additive fields that link a
journal entry to the fixed asset it represents and classify which phase
of the asset lifecycle (acquisition, depreciation, modification, disposal)
produced the entry.

Lifecycle phase mapping
-----------------------

The four ``asset_entry_type`` values map 1:1 to the four AM stories that
produce journal entries against an asset:

    * ``acquisition``   -- AM-001 Asset Registration. Posted by
      ``AccountAsset.action_confirm`` -> ``_create_acquisition_move``
      when the user confirms a draft asset.
    * ``depreciation``  -- AM-004 Automatic Depreciation Entries. Posted
      by ``AccountAsset._cron_post_depreciation_entries`` (the XML
      ``ir.cron`` defined in ``data/depreciation_cron.xml``).
    * ``modification``  -- AM-005 Asset Modification. Posted by the
      ``account.asset.modification.wizard`` for revaluation, impairment,
      impairment reversal, useful life change, and salvage value change.
      The granular sub-type is preserved on the wizard record and
      mirrored into the move's ``ref`` for audit trail; the
      ``asset_entry_type`` field is intentionally coarse-grained
      (single ``modification`` bucket) to keep this Selection stable
      and minimal.
    * ``disposal``      -- AM-006 Asset Disposal. Posted by the
      ``account.asset.disposal.wizard`` for sale, scrap, and write-off
      transitions.

Drill-down and reporting
------------------------

These two fields enable:

    * Drill-down from the journal entry form (Accounting -> Journal
      Entries) back to the originating asset record via the ``asset_id``
      Many2one. The reverse navigation -- from an asset to its lifecycle
      moves -- is provided by the AM-001 / AM-004 / AM-005 / AM-006
      workflows that create those moves with ``asset_id=asset.id``.
    * Filter / group-by of journal entries by lifecycle phase via
      ``asset_entry_type`` (e.g., a search filter that returns only
      depreciation entries posted by the AM-004 cron).
    * Audit trail: every monetary movement against the asset is
      classified, ensuring complete traceability for GAAP / IFRS
      fixed-asset disclosure requirements (referenced from
      ``tickets/features/FEATURE-004-asset-management.md``).

R-05 Compliance
---------------

    * ``_inherit = 'account.move'`` WITHOUT ``_name`` -- the core model
      registered by ``addons/account/models/account_move.py`` is
      extended in place; no net-new model is declared here.
    * NO redefinition of core fields (``move_type``, ``state``, ``date``,
      ``journal_id``, ``line_ids``, ``partner_id``, ``ref``, ``name``,
      ``company_id``, ``currency_id``, ``amount_total``, ``invoice_date``,
      etc.).
    * NO override of core methods (``action_post``, ``button_draft``,
      ``_post``, ``create``, ``write``, ``unlink``, ``_prepare_*``,
      ``_compute_*``).
    * ONLY two additive fields: a relational ``Many2one`` to the new
      ``account.asset`` model and a new classification ``Selection``.

R-01 Compliance
---------------

    * NO imports from sibling new modules
      (``account_budget_management``, ``account_deferred_revenue``,
      ``account_payment_followup``).

R-03 Compliance
---------------

    * Uses ``_inherit`` for an existing core model (``account.move``);
      does NOT use ``_name`` (which would attempt to register a new
      model under the same name and break the ORM registry).

R-07 Compliance
---------------

    * No ``.sudo()`` calls -- this module is purely declarative
      (two field definitions); no business logic, no method overrides,
      no privilege escalation.
"""

from odoo import fields, models


class AccountMove(models.Model):
    """Extend ``account.move`` with asset lifecycle back-references.

    The two additive fields on ``account.move`` enable bidirectional
    navigation between an asset and its lifecycle journal entries:

        * ``asset_id``: the fixed asset this entry relates to
        * ``asset_entry_type``: lifecycle phase classification
          (acquisition, depreciation, modification, disposal)

    These fields are populated by asset-management actions and wizards
    when they create journal entries (via ``self.env['account.move']
    .create({'asset_id': ..., 'asset_entry_type': ...})``); they are
    never set by direct user input on the journal-entry form
    (``asset_entry_type`` carries ``readonly=True`` to enforce this at
    the UI layer).

    Both fields are optional (no ``required=True``): journal entries
    that originate from non-asset workflows (manual entries, customer
    invoices, vendor bills unrelated to fixed assets, payments, bank
    reconciliation entries, etc.) leave both fields ``NULL`` -- which
    is the default and preserves backward compatibility with the rest
    of the accounting module and with FEATURE-001 / FEATURE-002.
    """

    _inherit = 'account.move'

    asset_id = fields.Many2one(
        'account.asset',
        string='Asset',
        ondelete='restrict',
        index=True,
        copy=False,
        help=(
            'The fixed asset this journal entry relates to. Populated '
            'automatically by asset lifecycle operations (acquisition '
            'confirmation, depreciation cron posting, revaluation, '
            'impairment, and disposal). Enables drill-down from the '
            'general ledger back to the asset record. '
            "ondelete='restrict' preserves the audit trail by "
            'preventing deletion of an asset that has linked journal '
            'entries; deletion must instead proceed via the AM-006 '
            'disposal workflow which closes the asset while keeping '
            'the historical entries intact.'
        ),
    )

    asset_entry_type = fields.Selection(
        selection=[
            ('acquisition', 'Asset Acquisition'),
            ('depreciation', 'Asset Depreciation'),
            ('modification', 'Asset Modification'),
            ('disposal', 'Asset Disposal'),
        ],
        string='Asset Entry Type',
        readonly=True,
        copy=False,
        help=(
            'Classification of this journal entry relative to the asset '
            'lifecycle: Acquisition (AM-001) for the entry posted at '
            'asset confirmation, Depreciation (AM-004) for entries '
            'posted by the scheduled depreciation cron, Modification '
            '(AM-005) for revaluation / impairment / impairment '
            'reversal / useful-life-change / salvage-value-change '
            'entries posted by the modification wizard, or Disposal '
            '(AM-006) for entries posted by the sale / scrap / '
            'write-off disposal wizard. Set automatically by the '
            'originating action; never edited by users (readonly=True).'
        ),
    )
