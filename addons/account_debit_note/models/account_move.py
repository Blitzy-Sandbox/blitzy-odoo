# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools import formatLang


class AccountMove(models.Model):
    _inherit = "account.move"

    debit_origin_id = fields.Many2one('account.move', 'Original Invoice Debited', readonly=True, copy=False, index='btree_not_null')
    debit_note_ids = fields.One2many('account.move', 'debit_origin_id', 'Debit Notes',
                                     help="The debit notes created for this invoice")
    debit_note_count = fields.Integer('Number of Debit Notes', compute='_compute_debit_count')

    @api.depends('debit_note_ids')
    def _compute_debit_count(self):
        debit_data = self.env['account.move']._read_group([('debit_origin_id', 'in', self.ids)],
                                                        ['debit_origin_id'], ['__count'])
        data_map = {debit_origin.id: count for debit_origin, count in debit_data}
        for inv in self:
            inv.debit_note_count = data_map.get(inv.id, 0.0)

    def action_view_debit_notes(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Debit Notes'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('debit_origin_id', '=', self.id)],
        }

    def action_debit_note(self):
        action = self.env.ref('account_debit_note.action_view_account_move_debit')._get_action_dict()
        return action

    def _check_vendor_credit_note_positive_total(self):
        """Refuse a credit note linked to a vendor bill whose total is not above zero.

        Only a positive total credits the bill back, so a total of zero and a total
        below zero are both refused before reaching the payable sub-ledger; every
        other document is left to the checks of account.  The refusal quotes the total
        the document actually carries, in its own currency, so that it reads accurately
        for either total and the Clerk can see the figure that was measured.
        """
        for move in self:
            if (
                move.move_type == 'in_refund'
                and move.debit_origin_id.move_type == 'in_invoice'
                and move.currency_id.compare_amounts(move.amount_total, 0.0) <= 0
            ):
                raise UserError(_(
                    "The vendor credit note %(document)s carries a total of %(total)s and cannot be posted: "
                    "that total must be greater than zero, because only a positive total credits the bill back. "
                    "State the credited quantity and the credited amount, then post it again.",
                    document=move.ref or move.display_name,
                    total=formatLang(self.env, move.amount_total, currency_obj=move.currency_id),
                ))

    def _post(self, soft=True):
        # A credit note linked to a vendor bill must carry a total above zero to have
        # anything to reverse; validating before core posts and numbers the document
        # leaves a refusal draft, unnumbered and without ledger movement.
        self._check_vendor_credit_note_positive_total()
        return super()._post(soft=soft)

    def _get_last_sequence_domain(self, relaxed=False):
        where_string, param = super()._get_last_sequence_domain(relaxed)
        # Refunds keep the single refund pool of account: its "R" prefix ignores
        # debit_origin_id, so splitting refunds by that link would hand both pools the
        # same next name.
        if self.journal_id.debit_sequence and self.move_type in ('in_invoice', 'out_invoice'):
            where_string += " AND debit_origin_id IS " + ("NOT NULL" if self.debit_origin_id else "NULL")
        return where_string, param

    def _get_starting_sequence(self):
        starting_sequence = super()._get_starting_sequence()
        if (
            self.journal_id.debit_sequence
            and self.debit_origin_id
            and self.move_type in ("in_invoice", "out_invoice")
        ):
            starting_sequence = "D" + starting_sequence
        return starting_sequence

    def _get_copy_message_content(self, default):
        """Override to handle debit note specific messages."""
        if default and default.get('debit_origin_id'):
            return _('This debit note was created from: %s', self._get_html_link())
        return super()._get_copy_message_content(default)
