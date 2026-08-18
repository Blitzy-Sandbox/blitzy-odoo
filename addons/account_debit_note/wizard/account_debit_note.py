# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.tools.translate import _
from odoo.exceptions import UserError


class AccountDebitNote(models.TransientModel):
    """
    Add Debit Note wizard: raises a document linked to the invoice or bill it corrects.
    A debit note corrects with a positive amount; a vendor bill can instead be credited
    back as a vendor credit note by setting Create Vendor Credit Note.
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
                                help="In case you need to do corrections for every line, it can be in handy to copy them. ")
    create_vendor_credit_note = fields.Boolean("Create Vendor Credit Note", default=False,
                                               help="Only for a posted vendor bill: create a vendor credit note, which gives back the "
                                                    "charge and reduces what you still owe the vendor, instead of a debit note, which "
                                                    "increases it.  The credit note stays linked to the bill it credits, and is "
                                                    "recorded in that bill's own journal, so no specific journal can be used for it.  "
                                                    "Leave this off to keep creating debit notes from vendor bills. ")
    move_type = fields.Char(compute="_compute_from_moves")
    journal_type = fields.Char(compute="_compute_journal_type")
    country_code = fields.Char(related='move_ids.company_id.country_id.code')
    vendor_credit_note_eligible = fields.Boolean(compute="_compute_vendor_credit_note_eligible")

    @api.model
    def default_get(self, fields):
        res = super(AccountDebitNote, self).default_get(fields)
        move_ids = self.env['account.move'].browse(self.env.context['active_ids']) if self.env.context.get('active_model') == 'account.move' else self.env['account.move']
        if any(move.state != "posted" for move in move_ids):
            raise UserError(_('You can only debit posted moves.'))
        elif any(move.debit_origin_id for move in move_ids):
            raise UserError(_("You can't make a debit note for an invoice that is already linked to a debit note."))
        elif any(move.move_type not in ['out_invoice', 'in_invoice', 'out_refund', 'in_refund'] for move in move_ids):
            raise UserError(_("You can make a debit note only for a Customer Invoice, a Customer Credit Note, a Vendor Bill or a Vendor Credit Note."))
        res['move_ids'] = [(6, 0, move_ids.ids)]
        return res

    @api.depends('move_ids')
    def _compute_from_moves(self):
        for record in self:
            move_ids = record.move_ids
            record.move_type = move_ids[0].move_type if len(move_ids) == 1 or not any(m.move_type != move_ids[0].move_type for m in move_ids) else False

    @api.depends('move_type')
    def _compute_journal_type(self):
        for record in self:
            record.journal_type = record.move_type in ['in_refund', 'in_invoice'] and 'purchase' or 'sale'

    @api.depends('move_ids', 'move_ids.state', 'move_ids.move_type', 'move_ids.debit_origin_id')
    def _compute_vendor_credit_note_eligible(self):
        for record in self:
            record.vendor_credit_note_eligible = not record._vendor_credit_note_source_refusal()

    @api.onchange('create_vendor_credit_note')
    def _onchange_create_vendor_credit_note(self):
        if self.create_vendor_credit_note:
            self.journal_id = False

    def _prepare_default_values(self, move):
        # Opt-in maps a vendor bill to a linked vendor credit note; default=False preserves the existing debit-note path.
        vendor_credit_note = self.create_vendor_credit_note and move.move_type == 'in_invoice'
        if vendor_credit_note:
            type = 'in_refund'
        elif move.move_type in ('in_refund', 'out_refund'):
            type = 'in_invoice' if move.move_type == 'in_refund' else 'out_invoice'
        else:
            type = move.move_type
        default_values = {
                'ref': '%s, %s' % (move.name, self.reason) if self.reason else move.name,
                'date': self.date or move.date,
                'invoice_date': move.is_invoice(include_receipts=True) and (self.date or move.date) or False,
                'journal_id': self.journal_id and self.journal_id.id or move.journal_id.id,
                'invoice_payment_term_id': None,
                'debit_origin_id': move.id,
                'move_type': type,
            }
        if vendor_credit_note:
            default_values['name'] = '/'
        if not self.copy_lines or move.move_type in [('in_refund', 'out_refund')]:
            default_values['line_ids'] = [(5, 0, 0)]
        return default_values

    def _vendor_credit_note_source_refusal(self):
        """State why this selection cannot be credited as one vendor credit note, or return ``''``.

        The reason is returned rather than raised because the form reads whether
        there is one, through ``vendor_credit_note_eligible``, while
        ``_check_vendor_credit_note_request`` raises it for a request that
        reached the wizard by another route.
        """
        self.ensure_one()
        move = self.move_ids
        if len(move) != 1:
            return _(
                "A vendor credit note gives back the charge of exactly one vendor bill, but %(count)s documents are selected.  "
                "Select the single bill to credit, or leave Create Vendor Credit Note unticked to raise a debit note for each of them.",
                count=len(move),
            )
        if move.state != 'posted':
            return _(
                "A vendor credit note can only give back the charge of a posted vendor bill, and %(document)s is not posted.  "
                "Post that bill first, or leave Create Vendor Credit Note unticked.",
                document=move.display_name,
            )
        if move.move_type != 'in_invoice':
            return _(
                "Only a vendor bill can be credited with a vendor credit note, and %(document)s is not one.  "
                "Leave Create Vendor Credit Note unticked to raise a debit note from it instead.",
                document=move.display_name,
            )
        if move.debit_origin_id:
            return _(
                "A vendor credit note gives back the charge of the vendor bill that carries it, and %(document)s does not: it is itself a correction of a bill, raised from %(source)s.  "
                "Credit %(source)s instead, or leave Create Vendor Credit Note unticked to raise a debit note from %(document)s.",
                document=move.display_name,
                source=move.debit_origin_id.display_name,
            )
        return ''

    def _check_vendor_credit_note_request(self):
        self.ensure_one()
        source_refusal = self._vendor_credit_note_source_refusal()
        if source_refusal:
            raise UserError(source_refusal)
        move = self.move_ids
        if self.journal_id and self.journal_id != move.journal_id:
            raise UserError(_(
                "A vendor credit note is recorded in the journal of the bill it credits, %(bill_journal)s, so it cannot be recorded in %(other_journal)s.  "
                "Leave Use Specific Journal empty, or select %(bill_journal)s.",
                bill_journal=move.journal_id.display_name,
                other_journal=self.journal_id.display_name,
            ))

    def create_debit(self):
        self.ensure_one()
        if self.create_vendor_credit_note:
            self._check_vendor_credit_note_request()
        new_moves = self.env['account.move']
        for move in self.move_ids.with_context(include_business_fields=True):  # Copy sale/purchase links.
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
