# -*- coding: utf-8 -*-
import re

from odoo import models, fields, api
from odoo.tools.translate import _
from odoo.exceptions import UserError

# Characters that must never reach the reference of a document: the C0 and C1 control
# ranges, a line break among them, which can forge a line of their own wherever the
# reference is written or exported line by line, and the Unicode bidirectional marks
# and overrides, which reorder the glyphs around them so that a reference reads on
# screen as text other than the text that is stored.  They are folded to a space
# rather than dropped, so that the words they sit between stay separate words.
_UNSAFE_REFERENCE_CHARACTERS = re.compile(r'[\x00-\x1f\x7f-\x9f\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]')


class AccountDebitNote(models.TransientModel):
    """
    Add Debit Note wizard: when you want to correct an invoice with a positive amount.
    Opposite of a Credit Note, but different from a regular invoice as you need the link to the original invoice.
    In some cases, also used to cancel Credit Notes
    A posted vendor bill can instead be credited back as a vendor credit note, by setting Create Vendor Credit Note.
    """
    _name = 'account.debit.note'
    _description = 'Add Debit Note wizard'

    move_ids = fields.Many2many('account.move', 'account_move_debit_move', 'debit_id', 'move_id',
                                domain=[('state', '=', 'posted')])
    date = fields.Date(string='Debit Note Date', default=fields.Date.context_today, required=True)
    reason = fields.Char(string='Reason')
    journal_id = fields.Many2one('account.journal', string='Use Specific Journal',
                                 help='If empty, uses the journal of the journal entry to be debited.')
    copy_lines = fields.Boolean("Copy Lines",
                                help="In case you need to do corrections for every line, it can be in handy to copy them.  "
                                     "We won't copy them for debit notes from credit notes. ")
    create_vendor_credit_note = fields.Boolean("Create Vendor Credit Note", default=False,
                                               help="For a posted vendor bill, create a vendor credit note giving the charge back, "
                                                    "instead of a debit note. Leave it off to keep creating debit notes.")
    # computed fields
    move_type = fields.Char(compute="_compute_from_moves")
    journal_type = fields.Char(compute="_compute_journal_type")
    country_code = fields.Char(related='move_ids.company_id.country_id.code')

    @api.model
    def default_get(self, fields):
        res = super(AccountDebitNote, self).default_get(fields)
        # A list action states the documents it was run on in active_ids; the client also
        # reaches this method through onchange, where it states none.  Reading the key
        # instead of subscripting it leaves that second call with an empty selection, the
        # wizard opening on nothing to debit, which is what it already answered when the
        # action was run on an empty selection.
        move_ids = self.env['account.move'].browse(self.env.context.get('active_ids') or []) if self.env.context.get('active_model') == 'account.move' else self.env['account.move']
        # The preconditions of create_debit, applied here as well so that a selection no
        # debit note can be made for is refused while the wizard is being opened, on
        # screen, rather than when the Clerk confirms it.
        self._check_source_moves(move_ids)
        res['move_ids'] = [(6, 0, move_ids.ids)]
        # The document-type list actions of account seed their own type in the context
        # (Bills sends default_move_type='in_invoice'), and default_get hands such a
        # default to a computed field as readily as to a keyed one, so the fields below
        # would describe the list the wizard was opened from instead of the documents
        # selected in it. Dropping them leaves the source type, its journal type and
        # its country to be computed from move_ids, which is what every consumer of
        # them - the field modifiers of the form and the journal domain - must read.
        for computed_name in ('move_type', 'journal_type', 'country_code'):
            res.pop(computed_name, None)
        return res

    @api.model
    def _check_source_moves(self, moves):
        """Refuse the documents that no debit note can be made from.

        Both ends of the wizard hold their caller to these preconditions: default_get,
        so that the refusal reaches the Clerk as the wizard opens, and create_debit,
        because a caller that creates the wizard record itself - a script, or a client
        calling the ORM directly - never passes through default_get, and create_debit is
        the method that copies the document and carries the source link into the ledger.
        One implementation keeps both ends refusing the same documents in the same words.

        :param moves: the ``account.move`` records the debit notes would be made from.
        """
        if any(move.state != "posted" for move in moves):
            raise UserError(_('You can only debit posted moves.'))
        elif any(move.debit_origin_id for move in moves):
            # What is read is the selected document's own source link, so what is refused
            # is a document that is itself the note of another one - not a document that
            # already has notes of its own, which stays perfectly debitable.
            raise UserError(_("You can't make a debit note for a document that is itself linked to the document it was made from."))
        elif any(move.move_type not in ['out_invoice', 'in_invoice', 'out_refund', 'in_refund'] for move in moves):
            raise UserError(_("You can make a debit note only for a Customer Invoice, a Customer Credit Note, a Vendor Bill or a Vendor Credit Note."))

    @api.depends('move_ids')
    def _compute_from_moves(self):
        for record in self:
            move_ids = record.move_ids
            record.move_type = move_ids[0].move_type if len(move_ids) == 1 or not any(m.move_type != move_ids[0].move_type for m in move_ids) else False

    @api.depends('move_type')
    def _compute_journal_type(self):
        for record in self:
            record.journal_type = record.move_type in ['in_refund', 'in_invoice'] and 'purchase' or 'sale'

    @api.model_create_multi
    def create(self, vals_list):
        # The documents asked for are resolved before the row that links them is written:
        # an id naming no document would otherwise be refused by the database, and what
        # comes back from there speaks of the link and its own constraints instead of the
        # selection that was made.
        for vals in vals_list:
            self._check_requested_moves(vals.get('move_ids'))
        return super().create(vals_list)

    def write(self, vals):
        # A selection changed after the wizard exists reaches the same relation row by the
        # same route, so it is resolved the same way: the database is left with nothing to
        # refuse, and the caller is answered about the selection instead.
        self._check_requested_moves(vals.get('move_ids'))
        return super().write(vals)

    @api.model
    def _check_requested_moves(self, move_ids_value):
        """Refuse a ``move_ids`` value asking for an id that names no document.

        The shapes read are the ones a caller states a selection of existing documents by
        id in: a plain list of ids, the LINK command and the SET command.  Every other
        command, a value stated as a recordset - which a request made of JSON cannot be -
        and a value asking for a document to be created along with the link are all left
        to the ORM, and so is the whole value when the caller may not read documents at
        all: whether a given id names one is not something this wizard answers to such a
        caller, and the access check of the ORM is what refuses the write to them.

        Existence is all that is established, and deliberately: a document that exists
        but which the caller may not reach is left to the access check of the ORM, which
        is what has to refuse it and what says so.  Neither is any part of the value
        quoted back other than the ids, because the rest is the caller's own text and a
        refusal is written to the log, where text of that kind could forge a line.

        :param move_ids_value: the value given for ``move_ids``, in any of the shapes the
            ORM accepts for a many-to-many field.
        """
        if isinstance(move_ids_value, models.BaseModel):
            return
        candidates = []
        for item in move_ids_value or ():
            if isinstance(item, (list, tuple)) and len(item) > 1:
                if item[0] == 4:
                    candidates.append(item[1])          # LINK one document
                elif item[0] == 6 and len(item) > 2:
                    candidates.extend(item[2] or ())    # SET the whole selection
            elif not isinstance(item, dict):
                candidates.append(item)                 # a plain list of ids
        if not candidates or not self.env['account.move'].has_access('read'):
            return
        # A boolean is not read as the id 1 it would otherwise pass for, and nothing else
        # that is not a whole number names a row this relation can hold either: the
        # documents to debit have to be posted already, so there is nothing to link that
        # is still being created.
        requested = [item for item in candidates if isinstance(item, int) and not isinstance(item, bool)]
        missing = sorted(set(requested) - set(self.env['account.move'].browse(requested).exists().ids))
        if missing:
            raise UserError(_(
                "No document to debit was found for %(references)s. "
                "Open the Debit Note action from the invoices or bills you want to debit and try again.",
                references=', '.join(str(move_id) for move_id in missing),
            ))
        if len(requested) != len(candidates):
            raise UserError(_("The selection given to the Debit Note wizard does not name documents. Open the Debit Note action from the invoices or bills you want to debit and try again."))

    @api.model
    def _sanitize_reference_text(self, text):
        """Return ``text`` with everything that could misrepresent it folded to a space.

        The Reason is copied into the reference of the document this wizard creates, and
        that reference is then read back in list cells, on printed documents and in the
        message of the posting refusal.  A bidirectional override in it makes the
        reference read as text other than the text that is stored, and a line break in it
        can forge a line wherever the reference is written line by line, so both are
        folded out here, where the Reason enters the document, leaving everything that
        reads the reference afterwards reading text that means what it shows.

        Text carrying none of those characters is returned exactly as it was keyed, so
        that an ordinary Reason still produces the reference it has always produced.

        :param text: the free text keyed by the user, or a false value.
        :return: the text to interpolate, empty when nothing legible is left of it.
        """
        source = text or ''
        folded = _UNSAFE_REFERENCE_CHARACTERS.sub(' ', source)
        if folded == source:
            return source
        # The fold leaves a space wherever a character was taken out; collapsing those
        # runs keeps the words of the Reason legible and leaves nothing at all of a Reason
        # made of nothing else, which the caller then reads as false and interpolates no
        # separator for.
        return ' '.join(folded.split())

    def _prepare_default_values(self, move):
        # Opt-in maps a vendor bill to a linked vendor credit note; default=False preserves the existing debit-note path.
        vendor_credit_note = self.create_vendor_credit_note and move.move_type == 'in_invoice'
        if vendor_credit_note:
            type = 'in_refund'
        elif move.move_type in ('in_refund', 'out_refund'):
            type = 'in_invoice' if move.move_type == 'in_refund' else 'out_invoice'
        else:
            type = move.move_type
        # The Reason reaches the reference as text and nothing else: a Reason left with
        # nothing legible by the fold leaves the reference as the source name alone.
        reason = self._sanitize_reference_text(self.reason)
        default_values = {
                'ref': '%s, %s' % (move.name, reason) if reason else move.name,
                'date': self.date or move.date,
                'invoice_date': move.is_invoice(include_receipts=True) and (self.date or move.date) or False,
                'journal_id': self.journal_id and self.journal_id.id or move.journal_id.id,
                'invoice_payment_term_id': None,
                'debit_origin_id': move.id,
                'move_type': type,
            }
        if not self.copy_lines or move.move_type in [('in_refund', 'out_refund')]:
            default_values['line_ids'] = [(5, 0, 0)]
        return default_values

    def create_debit(self):
        self.ensure_one()
        if not self.move_ids:
            # Nothing to copy, so nothing to name the new document after: refusing here
            # keeps the answer a sentence about the selection.
            raise UserError(_("Select at least one posted invoice or bill to make a debit note for."))
        # Applied to what the wizard record actually holds, and not only to what
        # default_get was opened on, so that every caller of the copy is held to the
        # preconditions the wizard states.
        self._check_source_moves(self.move_ids)
        new_moves = self.env['account.move']
        for move in self.move_ids.with_context(include_business_fields=True): #copy sale/purchase links
            default_values = self._prepare_default_values(move)
            new_move = move.copy(default=default_values)
            new_moves |= new_move

        action = {
            'name': _('Debit Notes'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'context': {'default_move_type': default_values['move_type']},
        }
        if len(new_moves) == 1:
            action.update({
                'view_mode': 'form',
                'res_id': new_moves.id,
            })
        else:
            action.update({
                'view_mode': 'list,form',
                'domain': [('id', 'in', new_moves.ids)],
            })
        return action
