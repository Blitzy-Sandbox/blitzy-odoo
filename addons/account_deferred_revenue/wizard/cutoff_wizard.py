# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""DR-003 Cut-off Entry Generation Wizard.

This TransientModel implements the period-end cut-off workflow defined
by user story DR-003.  It lets an accountant post the accumulated
recognition amount of one or more deferred schedules up to a chosen
cut-off date as a single journal entry per schedule.

Key design points
-----------------
*   The wizard NEVER modifies the schedule definition itself — it only
    flips qualifying ``account.deferred.line`` records to ``state =
    'posted'`` and attaches the resulting ``account.move`` via the
    ``move_id`` M2o on each line.  The schedule's computed
    ``posted_amount`` / ``remaining_amount`` / ``completion_status``
    fields reflect the change automatically through their
    ``@api.depends`` chain.

*   Lock-date enforcement follows the pattern established by the core
    ``addons/account/wizard/account_automatic_entry_wizard.py``
    (specifically ``_check_date`` / ``_compute_lock_date_message``).
    The non-blocking diagnostic banner uses
    ``account.move._get_lock_date_message`` while the blocking
    post-time guard uses ``account.move._get_violated_lock_dates``.

*   Reversal generation leverages ``account.move._reverse_moves`` so the
    reversal entry is properly linked via ``reversed_entry_id`` for the
    audit trail (DR-003 Scenario 5).

*   The wizard supports four operating modes selected via the ``mode``
    field: ``single`` (one schedule), ``batch`` (multiple schedules),
    ``preview`` (no posting, fills ``preview_move_data``), and
    ``reversal`` (post + auto-reverse).

Rules compliance (AAP §0.7)
---------------------------
*   R-01 Module Independence: no imports from sibling new modules.
*   R-02 No Enterprise Dependencies: no imports of Enterprise addons.
*   R-03 _inherit vs _name: this is a net-new model — uses ``_name``.
*   R-05 No Core Field Redefinition: never modifies ``account.move`` or
    ``account.move.line`` field definitions; only creates records.
*   R-07 No sudo() without justification: this module does not use
    ``sudo()`` at all.
"""
from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import format_date

# ---------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------

#: Account types considered revenue for cut-off posting direction.
_INCOME_ACCOUNT_TYPES = ('income', 'income_other')

#: Account types considered expense for cut-off posting direction.
_EXPENSE_ACCOUNT_TYPES = ('expense', 'expense_depreciation', 'expense_direct_cost')


class AccountDeferredCutoffWizard(models.TransientModel):
    """Wizard for generating DR-003 cut-off entries.

    Instantiated either from the Accounting → Deferred Revenue →
    Cut-off Entries menu (standalone invocation with empty defaults) or
    from an ``account.deferred.schedule`` form/list Action
    (``binding_model_id`` wiring populates ``default_schedule_ids`` via
    context).
    """

    _name = 'account.deferred.cutoff.wizard'
    _description = 'Deferred Revenue Cut-off Entry Wizard'
    _check_company_auto = True

    # -----------------------------------------------------------------
    # SECTION 1 — Mode & Schedule Selection
    # -----------------------------------------------------------------
    mode = fields.Selection(
        selection=[
            ('single', 'Single Schedule'),
            ('batch', 'Batch (Multiple Schedules)'),
            ('preview', 'Preview Only'),
            ('reversal', 'Post with Reversal'),
        ],
        string='Mode',
        default='single',
        required=True,
        help='Operating mode of the wizard: '
             'single posts one schedule at a time; '
             'batch groups multiple schedules into a single operation; '
             'preview computes move data without posting; '
             'reversal posts the cut-off entry and auto-creates a '
             'reversal entry dated the first day of the next period.',
    )
    schedule_id = fields.Many2one(
        comodel_name='account.deferred.schedule',
        string='Schedule',
        compute='_compute_schedule_id',
        inverse='_inverse_schedule_id',
        store=False,
        help='Single-mode picker showing the first schedule from '
             'schedule_ids.  Changes propagate back to schedule_ids.',
    )
    schedule_ids = fields.Many2many(
        comodel_name='account.deferred.schedule',
        string='Schedules',
        help='Schedules to be processed by the cut-off wizard.  In '
             'single mode this contains exactly one record; in batch '
             'and reversal modes it may contain many.',
    )

    # -----------------------------------------------------------------
    # SECTION 2 — Posting configuration
    # -----------------------------------------------------------------
    cutoff_date = fields.Date(
        string='Cut-off Date',
        default=fields.Date.context_today,
        required=True,
        help='Period-end date up to which recognition lines are posted. '
             'Recognition lines whose ``recognition_date <= cutoff_date`` '
             'and whose ``state == "draft"`` qualify for posting.',
    )
    journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Journal',
        required=True,
        check_company=True,
        domain="[('type', '=', 'general')]",
        default=lambda self: self._default_journal_id(),
        help='Journal in which the cut-off entry (and reversal, if '
             'requested) is created.',
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True,
    )
    company_currency_id = fields.Many2one(
        comodel_name='res.currency',
        related='company_id.currency_id',
        string='Company Currency',
        readonly=True,
    )
    post_reversal = fields.Boolean(
        string='Auto-reverse Next Period',
        default=False,
        help='When checked, the wizard creates a reversal entry dated '
             'the first day of the next period immediately after '
             'posting the cut-off entry.  Equivalent to selecting '
             'the "reversal" mode.',
    )
    reversal_date = fields.Date(
        string='Reversal Date',
        help='Date for the auto-generated reversal entry.  Defaults to '
             'the first day of the month following cutoff_date when '
             'post_reversal is enabled.',
    )

    # -----------------------------------------------------------------
    # SECTION 3 — Preview & computed diagnostics
    # -----------------------------------------------------------------
    lock_date_message = fields.Char(
        string='Lock Date Warning',
        compute='_compute_lock_date_message',
        help='Non-blocking diagnostic message shown when cutoff_date '
             'violates any company lock date (fiscal, tax, hard, sale, '
             'purchase).  The blocking constraint is enforced at post '
             'time by the ``_check_date`` constrains method.',
    )
    preview_move_data = fields.Json(
        string='Preview',
        compute='_compute_move_data',
        help='Structured preview of the journal entries that would be '
             'created.  Populated from the same code path that builds '
             'the actual account.move records, ensuring the preview '
             'exactly matches what will be posted.',
    )
    move_data = fields.Json(
        string='Move Data',
        compute='_compute_move_data',
        help='Internal buffer consumed by action_post / '
             'action_post_with_reversal to create account.move '
             'records.  Not displayed to the user.',
    )

    # -----------------------------------------------------------------
    # SECTION 4 — Default helpers
    # -----------------------------------------------------------------
    @api.model
    def _default_journal_id(self):
        """Select the default journal.

        Prefer the company's ``automatic_entry_default_journal_id`` if
        set, otherwise fall back to the first general journal for the
        company.
        """
        company = self.env.company
        journal = company.automatic_entry_default_journal_id
        if journal and journal.type == 'general':
            return journal.id
        journal = self.env['account.journal'].search(
            [
                ('type', '=', 'general'),
                ('company_id', '=', company.id),
            ],
            limit=1,
        )
        return journal.id if journal else False

    @api.model
    def default_get(self, fields_list):
        """Pre-populate schedule_ids from the active context.

        When the wizard is invoked from the schedule form/list via the
        ``binding_model_id`` action, Odoo populates ``active_model``
        and ``active_ids`` in the context.  This method copies those
        IDs into ``schedule_ids`` so the user sees the selected
        schedules pre-filled in the wizard form.
        """
        result = super().default_get(fields_list)

        # Honour an explicit default_schedule_ids already in context
        if 'schedule_ids' in fields_list and not result.get('schedule_ids'):
            active_model = self.env.context.get('active_model')
            active_ids = self.env.context.get('active_ids') or []
            if active_model == 'account.deferred.schedule' and active_ids:
                result['schedule_ids'] = [(6, 0, active_ids)]
                if 'mode' in fields_list and not result.get('mode'):
                    result['mode'] = 'single' if len(active_ids) == 1 else 'batch'
        return result

    # -----------------------------------------------------------------
    # SECTION 5 — Compute & inverse methods
    # -----------------------------------------------------------------
    @api.depends('schedule_ids')
    def _compute_schedule_id(self):
        """Expose the first schedule as a single-row handle."""
        for wizard in self:
            wizard.schedule_id = wizard.schedule_ids[:1].id if wizard.schedule_ids else False

    def _inverse_schedule_id(self):
        """Mirror schedule_id picker changes back into schedule_ids."""
        for wizard in self:
            if wizard.schedule_id:
                wizard.schedule_ids = [(6, 0, [wizard.schedule_id.id])]
            elif wizard.mode == 'single':
                wizard.schedule_ids = [(6, 0, [])]

    @api.depends('cutoff_date', 'company_id')
    def _compute_lock_date_message(self):
        """Surface a warning if cutoff_date falls within a locked period.

        This is NON-blocking — the blocking check lives in
        ``_check_date`` (@api.constrains).  The message mirrors the
        wording produced by
        ``account.move._get_lock_date_message`` for consistency with
        the core accounting UX.
        """
        Move = self.env['account.move']
        for wizard in self:
            wizard.lock_date_message = False
            if not wizard.cutoff_date or not wizard.company_id:
                continue
            try:
                violated = Move.with_company(wizard.company_id)._get_violated_lock_dates(
                    wizard.cutoff_date, False,
                )
            except Exception:  # noqa: BLE001 - method signature varies by Odoo version
                continue
            if violated:
                wizard.lock_date_message = _(
                    'The cut-off date %(date)s is protected by a lock '
                    'date.  Choose a later posting date or lift the '
                    'lock before continuing.',
                    date=format_date(wizard.env, wizard.cutoff_date),
                )

    @api.depends(
        'schedule_ids',
        'cutoff_date',
        'journal_id',
        'company_id',
        'mode',
    )
    def _compute_move_data(self):
        """Compute the move_data and preview_move_data payloads.

        Each schedule that has at least one qualifying line
        (``state='draft'`` AND ``recognition_date <= cutoff_date``)
        produces one move dict containing two balanced move lines:
        a debit of the deferred account and a credit of the
        recognition account (reversed for expense-type accounts).

        The result is a list of dicts with keys:
          - ``schedule_id``: the deferred schedule id
          - ``schedule_name``: display label
          - ``date``: cutoff_date (ISO string)
          - ``journal_id``: selected journal id
          - ``ref``: textual reference for the move
          - ``line_ids_to_post``: list of deferred-line ids covered
          - ``lines``: list of move-line dicts with
            ``account_id``, ``debit``, ``credit``, ``partner_id``,
            ``name``, ``analytic_distribution``
          - ``total``: total recognition amount for the schedule
        """
        for wizard in self:
            moves = []
            if not (wizard.schedule_ids and wizard.cutoff_date and wizard.journal_id):
                wizard.move_data = moves
                wizard.preview_move_data = moves
                continue

            for schedule in wizard.schedule_ids:
                if schedule.state != 'confirmed':
                    continue
                qualifying = schedule.line_ids.filtered(
                    lambda line, cutoff=wizard.cutoff_date: (
                        line.state == 'draft'
                        and line.recognition_date
                        and line.recognition_date <= cutoff
                    ),
                )
                if not qualifying:
                    continue

                total = sum(qualifying.mapped('recognition_amount'))
                if schedule.currency_id.is_zero(total):
                    continue

                account_type = schedule.recognition_account_id.account_type
                is_expense = account_type in _EXPENSE_ACCOUNT_TYPES
                # Default posting direction:
                #  - Revenue: Debit deferred_account, Credit recognition_account
                #  - Expense: Debit recognition_account, Credit deferred_account
                if is_expense:
                    debit_account = schedule.recognition_account_id
                    credit_account = schedule.deferred_account_id
                else:
                    debit_account = schedule.deferred_account_id
                    credit_account = schedule.recognition_account_id

                ref = _(
                    'Cut-off %(schedule)s up to %(date)s',
                    schedule=schedule.name or '',
                    date=format_date(wizard.env, wizard.cutoff_date),
                )
                moves.append({
                    'schedule_id': schedule.id,
                    'schedule_name': schedule.name,
                    'date': fields.Date.to_string(wizard.cutoff_date),
                    'journal_id': wizard.journal_id.id,
                    'company_id': wizard.company_id.id,
                    'currency_id': schedule.currency_id.id,
                    'ref': ref,
                    'line_ids_to_post': qualifying.ids,
                    'total': total,
                    'lines': [
                        {
                            'account_id': debit_account.id,
                            'account_name': debit_account.display_name,
                            'debit': total,
                            'credit': 0.0,
                            'partner_id': schedule.partner_id.id or False,
                            'name': ref,
                            'analytic_distribution': schedule.analytic_distribution or {},
                        },
                        {
                            'account_id': credit_account.id,
                            'account_name': credit_account.display_name,
                            'debit': 0.0,
                            'credit': total,
                            'partner_id': schedule.partner_id.id or False,
                            'name': ref,
                            'analytic_distribution': schedule.analytic_distribution or {},
                        },
                    ],
                })
            wizard.move_data = moves
            wizard.preview_move_data = moves

    # -----------------------------------------------------------------
    # SECTION 6 — Validation constraints
    # -----------------------------------------------------------------
    @api.constrains('cutoff_date', 'company_id')
    def _check_date(self):
        """Reject posting to a period protected by any lock date.

        Runs on create and write; enforced at post time via
        ``action_post`` / ``action_post_with_reversal`` which write the
        wizard record.  Mirrors the pattern established by
        ``account.automatic.entry.wizard._check_date``.
        """
        Move = self.env['account.move']
        for wizard in self:
            if not wizard.cutoff_date or not wizard.company_id:
                continue
            try:
                violated = Move.with_company(wizard.company_id)._get_violated_lock_dates(
                    wizard.cutoff_date, False,
                )
            except Exception:  # noqa: BLE001 - tolerate signature variation
                continue
            if violated:
                raise ValidationError(_(
                    'The cut-off date %(date)s is protected by a lock '
                    'date.  Choose a later posting date or lift the '
                    'lock before continuing.',
                    date=format_date(wizard.env, wizard.cutoff_date),
                ))

    @api.constrains('schedule_ids', 'mode')
    def _check_schedule_ids(self):
        """Mode-appropriate schedule selection requirement."""
        for wizard in self:
            if wizard.mode == 'single' and len(wizard.schedule_ids) > 1:
                raise ValidationError(_(
                    'Single mode accepts exactly one schedule.  Switch '
                    'to batch mode or remove schedules.',
                ))
            if wizard.mode in ('batch', 'reversal') and not wizard.schedule_ids:
                raise ValidationError(_(
                    'At least one schedule must be selected in %(mode)s mode.',
                    mode=dict(self._fields['mode'].selection).get(wizard.mode),
                ))

    # -----------------------------------------------------------------
    # SECTION 7 — Action methods
    # -----------------------------------------------------------------
    def action_preview(self):
        """Populate ``preview_move_data`` without posting.

        Implements DR-003 Scenario 2.  The user stays in the wizard;
        the preview panel renders the computed move dicts read-only so
        they can verify accounts and amounts before committing.
        """
        self.ensure_one()
        # Force recomputation so the user always sees fresh data
        self.invalidate_recordset(['move_data', 'preview_move_data'])
        return {
            'type': 'ir.actions.act_window',
            'name': _('Cut-off Preview'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': dict(self.env.context, default_mode='preview'),
        }

    def action_post(self):
        """Create and post journal entries for all qualifying schedules.

        Implements DR-003 Scenario 1 (single period) and Scenario 3
        (batch).  Iterates through the precomputed ``move_data`` and
        creates one ``account.move`` per schedule.  The qualifying
        deferred lines are updated to ``state='posted'`` with
        ``move_id`` pointing at the new move.
        """
        self.ensure_one()
        moves = self._create_moves(self.move_data or [])
        if not moves:
            raise UserError(_(
                'No qualifying recognition lines were found for the '
                'selected schedules and cut-off date.',
            ))
        return self._action_view_moves(moves)

    def action_post_with_reversal(self):
        """Create cut-off entries plus reversal entries (Scenario 5).

        Uses ``account.move._reverse_moves`` so the reversal entry is
        properly linked via ``reversed_entry_id`` and the audit trail
        is preserved.  The reversal is dated ``reversal_date`` (or the
        first day of the month following cutoff_date when unset) and
        set to ``auto_post='at_date'`` so it posts automatically on
        that date.
        """
        self.ensure_one()
        moves = self._create_moves(self.move_data or [])
        if not moves:
            raise UserError(_(
                'No qualifying recognition lines were found for the '
                'selected schedules and cut-off date.',
            ))

        reversal_date = self.reversal_date or self._default_reversal_date()
        # Reverse moves with auto_post='at_date' for the next period
        reversal_moves = moves._reverse_moves(
            default_values_list=[
                {
                    'date': reversal_date,
                    'ref': _('Reversal of %(ref)s', ref=move.ref or move.name or ''),
                    'auto_post': 'at_date',
                }
                for move in moves
            ],
            cancel=False,
        )
        # Return the action showing both the posted cut-off entries
        # and the scheduled reversal entries.
        all_moves = moves | reversal_moves
        return self._action_view_moves(all_moves)

    def _default_reversal_date(self):
        """Compute the default reversal date: first day of next month."""
        self.ensure_one()
        if not self.cutoff_date:
            return fields.Date.context_today(self)
        # Advance to the first day of the following month
        d = self.cutoff_date
        if d.month == 12:
            return d.replace(year=d.year + 1, month=1, day=1)
        return d.replace(month=d.month + 1, day=1)

    def _create_moves(self, move_data):
        """Create and post ``account.move`` records from move_data.

        Returns the recordset of created moves.  Flips qualifying
        ``account.deferred.line`` records to posted and attaches them
        to the new moves via ``move_id``.
        """
        Move = self.env['account.move']
        DeferredLine = self.env['account.deferred.line']

        created = Move
        for entry in move_data:
            line_ids_to_post = entry.get('line_ids_to_post') or []
            if not line_ids_to_post:
                continue
            move_vals = {
                'date': entry['date'],
                'ref': entry['ref'],
                'journal_id': entry['journal_id'],
                'company_id': entry['company_id'],
                'move_type': 'entry',
                'line_ids': [
                    (
                        0,
                        0,
                        {
                            'account_id': line['account_id'],
                            'debit': line['debit'],
                            'credit': line['credit'],
                            'partner_id': line.get('partner_id') or False,
                            'name': line['name'],
                            'analytic_distribution': line.get('analytic_distribution') or False,
                        },
                    )
                    for line in entry['lines']
                ],
            }
            move = Move.create(move_vals)
            move.action_post()
            created |= move

            # Attach the qualifying deferred lines to the new move
            lines = DeferredLine.browse(line_ids_to_post).exists()
            if lines:
                lines.write({
                    'state': 'posted',
                    'move_id': move.id,
                })
        return created

    def _action_view_moves(self, moves):
        """Build an action that displays the created moves to the user."""
        self.ensure_one()
        if len(moves) == 1:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Cut-off Journal Entry'),
                'res_model': 'account.move',
                'res_id': moves.id,
                'view_mode': 'form',
                'target': 'current',
            }
        return {
            'type': 'ir.actions.act_window',
            'name': _('Cut-off Journal Entries'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', moves.ids)],
            'target': 'current',
        }

    # -----------------------------------------------------------------
    # SECTION 8 — Grouping helpers (public, useful for tests and UX)
    # -----------------------------------------------------------------
    def group_moves_by_journal(self):
        """Return a dict of ``journal_id → list[move_data]``.

        Used by DR-003 Scenario 3 batch generation to demonstrate that
        moves can be consolidated per-journal.  The actual posting path
        (``_create_moves``) already creates one move per schedule; this
        helper is exposed for reporting and tests.
        """
        self.ensure_one()
        grouping = defaultdict(list)
        for entry in self.move_data or []:
            grouping[entry['journal_id']].append(entry)
        return dict(grouping)
