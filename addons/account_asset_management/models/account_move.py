# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Asset back-reference for ``account.move`` (FEATURE-004, AM-001 / AM-004).

This module extends the core ``account.move`` model with two
additive fields:

    * ``asset_id`` (``Many2one`` -> ``account.asset``) -- back-
      reference from the journal entry to the asset that originated
      it. Populated by ``_create_acquisition_move`` (AM-001) and by
      the ``action_post`` method on ``account.asset.depreciation.line``
      (AM-004) when posting the depreciation entry.
    * ``asset_entry_type`` (``Selection``) -- categorises the move\'s
      role in the asset lifecycle: ``acquisition`` (AM-001 confirmation),
      ``depreciation`` (AM-004 cron), ``revaluation`` /
      ``impairment`` / ``impairment_reversal`` (AM-005 modification
      wizard), or ``disposal`` (AM-006 disposal wizard).

Both fields are STRICTLY ADDITIVE per AAP Rule R-05: no existing
core or FEATURE-001 / FEATURE-002 field is redefined. No method on
``account.move`` is overridden.

AAP Rule Compliance
-------------------
* R-01 (Module independence) -- No imports from sibling CE modules.
* R-03 (``_inherit`` / ``_name`` correctness) -- Uses ``_inherit =
  \'account.move\'`` WITHOUT ``_name``: the core model registered
  by ``addons/account/models/account_move.py`` is extended in place.
* R-05 (No core field redefinition) -- ONLY two additive relational /
  selection fields are added; NO existing field is shadowed or
  redefined; NO method override appears.
* R-07 (No unjustified ``sudo``) -- This file contains no
  ``.sudo()`` call.
"""

from odoo import fields, models


class AccountMove(models.Model):
    """Extend ``account.move`` with asset-management back-references.

    Adds the two purely-additive fields ``asset_id`` and
    ``asset_entry_type`` so journal entries originating from the
    asset lifecycle (acquisition, depreciation, modification,
    disposal) can be drilled into from the asset record and
    classified in financial reports.
    """

    _inherit = 'account.move'

    asset_id = fields.Many2one(
        comodel_name='account.asset',
        string='Source Asset',
        ondelete='set null',
        index=True,
        copy=False,
        help=(
            'The fixed asset this journal entry was generated for '
            '(if any). Populated automatically by the asset '
            'acquisition (AM-001), depreciation (AM-004), '
            'modification (AM-005), and disposal (AM-006) workflows. '
            'NULL for entries unrelated to any asset. '
            '``ondelete=set null`` preserves journal-entry history '
            'when an asset record is unlinked (rare, since asset '
            'deletion is restricted by category and depreciation-line '
            'foreign keys).'
        ),
    )
    asset_entry_type = fields.Selection(
        selection=[
            ('acquisition', 'Acquisition'),
            ('depreciation', 'Depreciation'),
            ('revaluation', 'Revaluation'),
            ('impairment', 'Impairment'),
            ('impairment_reversal', 'Impairment Reversal'),
            ('disposal', 'Disposal'),
            ('catchup_depreciation', 'Catch-up Depreciation'),
        ],
        string='Asset Entry Type',
        copy=False,
        help=(
            'Classifies the role of this journal entry within the '
            'asset lifecycle. Set automatically by the asset '
            'workflows; useful for filtering financial reports and '
            'for audit trail navigation. NULL for entries unrelated '
            'to any asset.'
        ),
    )
