# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import re

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import formatLang

# The characters a document reference must not carry into a message: the C0 and C1
# control ranges, which include the line breaks and the carriage returns that would
# let a reference pass for a record of its own in the line-oriented server log, and
# the Unicode bidirectional marks and overrides, which reorder the text printed
# around them.  A reference of ordinary text contains none of them, so folding them
# leaves every real reference exactly as it was keyed in.
_MESSAGE_UNSAFE_CHARACTERS = re.compile(
    r'[\x00-\x1f\x7f-\x9f\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]',
)


def _message_safe(text):
    """Return ``text`` fit to be quoted in a message, on one line and in one direction.

    A document reference is free text a user keys in, and quoting it into a refusal
    carries it to two line-oriented readers: the server log, where an embedded line
    break would let the text behind it stand as a log record of its own, and the
    dialog that reads the refusal back, where an embedded bidirectional override
    would make the message read backwards.  Every such character is folded to a
    single space, which changes nothing about a reference of ordinary text and
    leaves the message otherwise as it was written -- the reference is still named
    in full, neither quoted nor cut short.

    :param text: the value to quote, or a falsy value for a document that has none
    :return: the same text with every control and bidirectional character spaced
    :rtype: str
    """
    return _MESSAGE_UNSAFE_CHARACTERS.sub(' ', text or '')


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
        # The Debit Note button is hidden from a user who has no accounting rights,
        # but a client can call the method the button names directly, so the read the
        # button stands for is required of the caller here too: the action describes a
        # window, a model and a view, and none of that is owed to a caller who may not
        # read the document the wizard would be opened from.  An empty recordset asks
        # the same question of the model itself, which is the right question when no
        # document has been selected.
        self.check_access('read')
        action = self.env.ref('account_debit_note.action_view_account_move_debit')._get_action_dict()
        return action

    def _check_vendor_credit_note_positive_total(self):
        """Refuse a credit note linked to a vendor bill whose total is not above zero.

        Only a positive total credits the bill back, so a total of zero and a total
        below zero are both refused before reaching the payable sub-ledger; every
        other document is left to the checks of account.  The refusal quotes the total
        the document actually carries, in its own currency, so that it reads accurately
        for either total and the Clerk can see the figure that was measured.

        A vendor credit note carrying a source link is what this module creates and
        nothing else does: the link is set on the copy the wizard makes and is never
        copied on, so the pair of a refund type and a source link is the module's own
        signature and is what is measured here.  The type of the document at the far
        end of that link is deliberately not part of the question.  The field is
        readonly on the form only, so a client can re-point it after creation, and
        reading the far end would let that write decide whether the total is measured
        at all -- the document under measurement would then say for itself whether the
        rule applies to it.  What the link must point at is held instead by
        :meth:`_check_debit_origin_is_vendor_bill_of_same_company`, so the two rules
        together leave no document that is a vendor credit note of this module's making
        and escapes measurement.
        """
        for move in self:
            if (
                move.move_type == 'in_refund'
                and move.debit_origin_id
                and move.currency_id.compare_amounts(move.amount_total, 0.0) <= 0
            ):
                raise UserError(_(
                    "The vendor credit note %(document)s carries a total of %(total)s and cannot be posted: "
                    "that total must be greater than zero, because only a positive total credits the bill back. "
                    "State the credited quantity and the credited amount, then post it again.",
                    document=_message_safe(move.ref or move.display_name),
                    total=formatLang(self.env, move.amount_total, currency_obj=move.currency_id),
                ))

    @api.constrains('state', 'amount_total', 'move_type', 'debit_origin_id')
    def _check_posted_vendor_credit_note_total(self):
        """Hold the positive-total rule as a property of a posted document.

        Posting through the button runs the rule in :meth:`_post`, but that is one road
        to the posted state and not the only one: a plain write of the state, a create
        that states it outright, an import or another module posting on a document's
        behalf all reach the same ledger, and a total of zero or below is as wrong on
        the ledger whichever road brought it there.  A constraint is checked on create
        and on write alike, so stating the rule here holds it against all of them, and
        it delegates to the very method :meth:`_post` calls so that a refusal reads
        the same words wherever the attempt came from.

        Only a posted document is measured.  A vendor credit note of no value is a
        perfectly ordinary draft -- the wizard produces one whenever Copy Lines is left
        off, and the Clerk keys the credited quantity in afterwards -- so what is
        refused is the attempt to post it, never its existence.
        """
        self.filtered(lambda move: move.state == 'posted')._check_vendor_credit_note_positive_total()

    @api.constrains('debit_origin_id', 'move_type', 'company_id')
    def _check_debit_origin_is_vendor_bill_of_same_company(self):
        """Hold the source of a vendor credit note to a vendor bill of its own company.

        ``debit_origin_id`` is readonly on the form and writable through the ORM, so a
        vendor credit note can be re-pointed after it is created.  The link is what
        says which bill is being credited, and the platform reads it as a document
        classification well beyond this module, so a vendor credit note is held to the
        kind of source its own creation gives it: a vendor bill, and one belonging to
        the company that carries the credit note.  Whether the source belongs to that
        company is asked of the model itself, so this rule follows whatever company
        structure account.move recognises rather than restating it.

        The source is read with the rights of the framework, not the rights of the
        writer, so a source the writer cannot read still answers the question and the
        rule cannot be turned into an access error and thereby stepped around.  For the
        same reason a refusal names only the document being written and the field being
        written: naming anything the source holds would report an attribute of a record
        the writer is not allowed to read.
        """
        for move in self:
            if move.move_type != 'in_refund' or not move.debit_origin_id:
                continue
            origin = move.debit_origin_id.sudo()
            if origin.move_type != 'in_invoice':
                raise ValidationError(_(
                    "The field 'Original Invoice Debited' of the vendor credit note %(document)s must name a "
                    "vendor bill: a vendor credit note credits a vendor bill back, so no other kind of document "
                    "can stand as its source. Leave the bill the credit note was created from in place.",
                    document=_message_safe(move.ref or move.display_name),
                ))
            if origin.filtered_domain(origin._check_company_domain(move.company_id)) != origin:
                raise ValidationError(_(
                    "The field 'Original Invoice Debited' of the vendor credit note %(document)s must name a "
                    "vendor bill of the company that carries the credit note: a credit note and the bill it "
                    "credits belong to one set of books. Leave the bill the credit note was created from in place.",
                    document=_message_safe(move.ref or move.display_name),
                ))

    def _post(self, soft=True):
        # A credit note linked to a vendor bill must carry a total above zero to have
        # anything to reverse; validating before core posts and numbers the document
        # leaves a refusal draft, unnumbered and without ledger movement.  The right to
        # post is read first, on the same terms account reads it, so a caller account is
        # about to refuse is answered by that refusal and not by a business message
        # quoting a document and the figure it carries.  Skipping the check for such a
        # caller posts nothing: account raises before any document is measured, and the
        # rule still holds for everyone else here and, whatever the road taken, in
        # _check_posted_vendor_credit_note_total.
        if self.env.su or self.env.user.has_group('account.group_account_invoice'):
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
