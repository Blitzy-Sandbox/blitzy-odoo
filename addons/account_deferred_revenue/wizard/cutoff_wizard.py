# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""DR-003 Cut-off Entry Generation Wizard.

This :class:`~odoo.models.TransientModel` implements the period-end
cut-off workflow defined by user story DR-003.  It lets an accountant
post the accumulated recognition amount of one or more deferred
schedules up to a chosen cut-off date as a single journal entry per
schedule, with optional auto-reversal in the next period and full
lock-date enforcement.

Key Design Points
-----------------
*   The wizard NEVER modifies the schedule definition itself — it only
    flips qualifying ``account.deferred.line`` records to
    ``state='posted'`` and attaches the resulting ``account.move`` via
    the ``move_id`` Many2one on each line plus the ``move_line_ids``
    Many2many for granular traceability.  The schedule's computed
    ``posted_amount`` / ``remaining_amount`` / ``completion_status``
    fields reflect the change automatically through their
    ``@api.depends`` chain.

*   Lock-date enforcement follows the pattern established by the core
    :mod:`addons.account.wizard.account_automatic_entry_wizard`
    (specifically ``_check_date`` and ``_compute_lock_date_message``).
    The non-blocking diagnostic banner uses
    :meth:`~odoo.addons.account.models.account_move.AccountMove._get_lock_date_message`
    while the blocking post-time guard uses
    :meth:`~odoo.addons.account.models.res_company.ResCompany._get_violated_lock_dates`.

*   Reversal generation leverages
    :meth:`~odoo.addons.account.models.account_move.AccountMove._reverse_moves`
    so the reversal entry is properly linked via ``reversed_entry_id``
    and ``adjusting_entry_origin_move_ids`` for the audit trail
    (DR-003 Scenario 5).  Reversals are created with
    ``auto_post='at_date'`` so they post automatically when the
    reversal date arrives via the standard
    ``ir_cron_auto_post_draft_entry`` cron job.

*   The wizard supports four operating modes selected via the ``mode``
    field:

        ``single``    — one schedule, one move.
        ``batch``     — many schedules, one consolidated move per
                        company.
        ``preview``   — compute and display only; no posting.
        ``reversal``  — post + auto-reverse (equivalent to enabling
                        ``post_reversal`` in any mode).

Rules Compliance (AAP §0.7)
---------------------------
*   **R-01** Module Independence: only imports from :mod:`odoo` core;
    no imports of sibling new modules.
*   **R-02** No Enterprise Dependencies: zero references to Enterprise
    addons.
*   **R-03** ``_inherit`` vs ``_name``: this is a NET-NEW model — uses
    ``_name`` (no ``_inherit`` on a pre-existing model name).
*   **R-05** No Core Field Redefinition: never modifies
    ``account.move`` or ``account.move.line`` field definitions; only
    creates records via ``self.env['account.move'].create(...)`` and
    invokes public API methods.
*   **R-07** No ``sudo()`` without justification: this file does not
    use ``sudo()`` at all.  Lock-date enforcement is delegated entirely
    to :meth:`res.company._get_violated_lock_dates` which performs the
    cross-user exception lookup with the appropriate elevated
    privileges encapsulated inside the core ``account`` module.
"""

import json
from collections import defaultdict
from datetime import date as date_type  # noqa: F401 - exported for type hints

from dateutil.relativedelta import relativedelta
from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import (  # noqa: F401 - groupby imported per AAP spec
    format_date,
    formatLang,
    groupby,
)

# ---------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------

#: ``account.account.account_type`` values that classify a recognition
#: account as REVENUE for cut-off direction.  When the recognition
#: account belongs to one of these types the wizard posts:
#:
#:     Debit  schedule.deferred_account_id     (clears the liability)
#:     Credit schedule.recognition_account_id  (books revenue)
_INCOME_ACCOUNT_TYPES = ('income', 'income_other')

#: ``account.account.account_type`` values that classify a recognition
#: account as EXPENSE for cut-off direction.  When the recognition
#: account belongs to one of these types the wizard posts:
#:
#:     Debit  schedule.recognition_account_id  (books expense)
#:     Credit schedule.deferred_account_id     (clears the asset)
_EXPENSE_ACCOUNT_TYPES = ('expense', 'expense_depreciation', 'expense_direct_cost')


class AccountDeferredCutoffWizard(models.TransientModel):
    """Wizard for generating DR-003 cut-off entries.

    Instantiated either from the Accounting → Deferred Revenue →
    Cut-off Entries menu (standalone invocation with empty defaults) or
    from an :class:`~odoo.addons.account_deferred_revenue.models.account_deferred_schedule.AccountDeferredSchedule`
    form/list Action (``binding_model_id`` wiring populates
    ``default_schedule_ids`` via context).

    Per :rule:`R-03` this is a **net-new model** — uses ``_name`` (no
    ``_inherit`` of a pre-existing model name).  Per :rule:`R-05` no
    field on ``account.move`` or ``account.move.line`` is redefined;
    the wizard only CREATES move records using the public ORM API.
    Per :rule:`R-07` the wizard does not use ``sudo()``; lock-exception
    handling is delegated to ``res.company._get_violated_lock_dates``.
    """

    _name = 'account.deferred.cutoff.wizard'
    _description = 'Deferred Revenue Cut-off Entry Wizard'
    # Auto-validates company consistency on every Many2one with
    # ``check_company=True`` (:attr:`journal_id`, schedule company, etc.)
    _check_company_auto = True

    # =====================================================================
    # SECTION 1 — Mode and schedule selection
    # =====================================================================
    mode = fields.Selection(
        selection=[
            ('single', 'Single Schedule'),
            ('batch', 'Batch (all pending)'),
            ('preview', 'Preview Only'),
            ('reversal', 'Generate with Reversal'),
        ],
        string='Mode',
        default='single',
        required=True,
        help=(
            "Single: generate one journal entry per schedule. "
            "Batch: process all schedules with pending recognition lines up "
            "to the cut-off date and produce one consolidated entry per "
            "company. "
            "Preview: compute and display entries without posting. "
            "Reversal: post entries and create reversal entries dated the "
            "first day of the next period (auto-post at date)."
        ),
    )

    cutoff_date = fields.Date(
        string='Cut-off Date',
        required=True,
        default=fields.Date.context_today,
        help=(
            "Recognition lines with state='draft' AND "
            "recognition_date <= cutoff_date will be included in the "
            "generated entry."
        ),
    )

    schedule_ids = fields.Many2many(
        comodel_name='account.deferred.schedule',
        string='Schedules',
        help=(
            "Schedules to process. Populated from context "
            "``default_schedule_ids`` when invoked from a schedule action; "
            "may be edited manually in batch / reversal modes."
        ),
    )

    schedule_id = fields.Many2one(
        comodel_name='account.deferred.schedule',
        string='Schedule',
        compute='_compute_schedule_id',
        store=False,
        help=(
            "Convenience reference for single mode (first schedule in "
            "schedule_ids). Populated by the ``_compute_schedule_id`` "
            "compute method."
        ),
    )

    # =====================================================================
    # SECTION 2 — Posting configuration
    # =====================================================================
    journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Journal',
        domain="[('type', '=', 'general'), ('company_id', '=', company_id)]",
        required=True,
        check_company=True,
        default=lambda self: self._default_journal_id(),
        help='General journal where cut-off entries will be posted.',
    )

    post_reversal = fields.Boolean(
        string='Generate Reversal',
        default=False,
        help=(
            "When enabled, a reversal entry is created and dated the "
            "first day of the period following ``cutoff_date``. The "
            "reversal uses ``auto_post='at_date'`` so it posts "
            "automatically when its date arrives."
        ),
    )

    reversal_date = fields.Date(
        string='Reversal Date',
        compute='_compute_reversal_date',
        store=True,
        readonly=False,
        help=(
            "Defaults to the first day of the month following "
            "``cutoff_date``. May be manually edited to any date strictly "
            "after the cut-off date."
        ),
    )

    # =====================================================================
    # SECTION 3 — Move-data buffers (computed JSON)
    # =====================================================================
    move_data = fields.Json(
        string='Move Data',
        compute='_compute_move_data',
        store=False,
        help=(
            "JSON payload of ``account.move`` value dicts that will be "
            "created on action_post. Computed from the qualifying "
            "recognition lines via :meth:`_get_move_dict_vals_change_period`."
        ),
    )

    preview_move_data = fields.Json(
        string='Preview Move Data',
        compute='_compute_preview_move_data',
        store=False,
        help=(
            "JSON payload formatted for the preview panel UI. Capped to "
            "the first 4 moves to avoid UI overload; remaining moves are "
            "summarized via the ``discarded_number`` option."
        ),
    )

    # =====================================================================
    # SECTION 4 — Company and currency
    # =====================================================================
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )

    company_currency_id = fields.Many2one(
        comodel_name='res.currency',
        related='company_id.currency_id',
        string='Company Currency',
        readonly=True,
    )

    # =====================================================================
    # SECTION 5 — Lock-date diagnostic field
    # =====================================================================
    lock_date_message = fields.Char(
        string='Lock Date Warning',
        compute='_compute_lock_date_message',
        help=(
            "Non-blocking diagnostic message shown when ``cutoff_date`` "
            "falls within a locked period. The blocking enforcement is "
            "performed at post time by ``_check_date``."
        ),
    )

    # =====================================================================
    # SECTION 6 — Default helpers
    # =====================================================================
    @api.model
    def _default_journal_id(self):
        """Pick the company's default general journal.

        Prefers ``automatic_entry_default_journal_id`` (the same journal
        used by ``account.automatic.entry.wizard``) when set; falls back
        to the first ``type='general'`` journal of the current company.
        Returns ``False`` when no general journal exists so the wizard
        renders cleanly in test environments without seed data.
        """
        company = self.env.company
        journal = company.automatic_entry_default_journal_id
        if journal and journal.type == 'general':
            return journal.id
        journal = self.env['account.journal'].search(
            [('type', '=', 'general'), ('company_id', '=', company.id)],
            limit=1,
        )
        return journal.id if journal else False

    @api.model
    def default_get(self, fields_list):
        """Pre-populate ``schedule_ids`` and ``mode`` from the context.

        When the wizard is invoked from
        :meth:`account.deferred.schedule.action_generate_cutoff` the
        context provides ``default_schedule_ids`` and ``default_mode``.
        Standard binding-action invocation provides ``active_model``
        and ``active_ids`` — those are used as a fallback so the wizard
        also works when wired via ``binding_model_id`` on the schedule
        list view.

        Also aligns ``company_id`` with the first schedule's company so
        ``_check_company_auto`` constraints pass even when the user's
        default company differs from the schedule's.
        """
        res = super().default_get(fields_list)

        # Honour explicit default_schedule_ids first; fall back to active_ids
        if 'schedule_ids' in fields_list and not res.get('schedule_ids'):
            ctx_ids = self.env.context.get('default_schedule_ids')
            if not ctx_ids and self.env.context.get('active_model') == 'account.deferred.schedule':
                ctx_ids = self.env.context.get('active_ids') or []
            if ctx_ids:
                # Normalise (6, 0, [...]) form vs plain id list
                if isinstance(ctx_ids, list) and ctx_ids and isinstance(ctx_ids[0], (list, tuple)):
                    res['schedule_ids'] = ctx_ids
                else:
                    res['schedule_ids'] = [(6, 0, list(ctx_ids))]

        # Align company with first schedule when not explicitly set
        if res.get('schedule_ids') and 'company_id' in fields_list and not res.get('company_id'):
            first_id = None
            entry = res['schedule_ids'][0]
            # ``entry`` may be (6, 0, [ids]) or a bare id
            if isinstance(entry, (list, tuple)) and len(entry) == 3:
                ids_list = entry[2] or []
                first_id = ids_list[0] if ids_list else None
            elif isinstance(entry, int):
                first_id = entry
            if first_id:
                schedule = self.env['account.deferred.schedule'].browse(first_id)
                if schedule.exists() and schedule.company_id:
                    res['company_id'] = schedule.company_id.id

        # Default mode from context if not set elsewhere
        if 'mode' in fields_list and not res.get('mode'):
            res['mode'] = self.env.context.get('default_mode', 'single')

        return res

    # =====================================================================
    # SECTION 7 — Compute methods
    # =====================================================================
    @api.depends('schedule_ids')
    def _compute_schedule_id(self):
        """Expose the first schedule as the single-row picker.

        The form view binds ``schedule_id`` for ``mode='single'`` so the
        user has a one-row picker; in ``batch`` / ``reversal`` modes
        ``schedule_ids`` is the source of truth.
        """
        for wizard in self:
            wizard.schedule_id = wizard.schedule_ids[:1] if wizard.schedule_ids else False

    @api.depends('cutoff_date')
    def _compute_reversal_date(self):
        """Default reversal date: first day of the month after cutoff_date.

        Uses :class:`dateutil.relativedelta.relativedelta` for
        calendar-aware month arithmetic so the result is correct
        regardless of ``cutoff_date``'s month length (handles February,
        30/31-day months, year rollover).  ``readonly=False`` and
        ``store=True`` allow the user to override the default in the
        form.
        """
        for wizard in self:
            if wizard.cutoff_date:
                wizard.reversal_date = (
                    wizard.cutoff_date + relativedelta(months=1)
                ).replace(day=1)
            else:
                wizard.reversal_date = False

    @api.depends('cutoff_date', 'company_id', 'journal_id')
    def _compute_lock_date_message(self):
        """Surface a non-blocking warning if cutoff_date violates a lock.

        Mirrors :meth:`account.automatic.entry.wizard._compute_lock_date_message`:
        builds a phantom move record on the wizard's journal/company so
        that :meth:`account.move._get_lock_date_message` can compute a
        consistent localized message.  When no lock is violated, sets
        the field to ``False`` so the form's ``invisible`` rule hides
        the banner.
        """
        for wizard in self:
            wizard.lock_date_message = False
            if not wizard.cutoff_date or not wizard.company_id:
                continue
            ref_move = self.env['account.move'].new({
                'journal_id': wizard.journal_id.id if wizard.journal_id else False,
                'company_id': wizard.company_id.id,
                'move_type': 'entry',
                'date': wizard.cutoff_date,
            })
            message = ref_move._get_lock_date_message(wizard.cutoff_date, has_tax=False)
            if message:
                wizard.lock_date_message = message

    @api.depends('schedule_ids', 'cutoff_date', 'journal_id', 'company_id', 'mode')
    def _compute_move_data(self):
        """Compute the move dict list for posting.

        Delegates to :meth:`_get_move_dict_vals_change_period` which
        encapsulates the single/batch branching logic.  The computation
        catches :class:`UserError` and :class:`ValidationError` so the
        UI never freezes — blocking validation lives in
        :meth:`_check_date` (called only at save/post time) and the
        diagnostic banner is updated separately by
        :meth:`_compute_lock_date_message`.
        """
        for wizard in self:
            if not wizard.schedule_ids or not wizard.cutoff_date or not wizard.journal_id:
                wizard.move_data = False
                continue
            try:
                move_vals_list = wizard._get_move_dict_vals_change_period(
                    schedules=wizard.schedule_ids,
                    cutoff_date=wizard.cutoff_date,
                )
            except (UserError, ValidationError):
                # Compute methods MUST NOT raise to the UI; surface via
                # ``lock_date_message`` (computed) and ``_check_date``
                # (constraint, evaluated at save/post time).
                wizard.move_data = False
            else:
                wizard.move_data = move_vals_list or False

    @api.depends('move_data')
    def _compute_preview_move_data(self):
        """Format ``move_data`` for the read-only preview panel.

        Mirrors :meth:`account.automatic.entry.wizard._compute_preview_move_data`:
        renders the first 4 moves via
        :meth:`account.move._move_dict_to_preview_vals` and wraps the
        result with column metadata and a discarded-count summary for
        any extra moves.
        """
        for wizard in self:
            if not wizard.move_data:
                wizard.preview_move_data = False
                continue
            # JSON field's raw value may be a Python list (typical) or a
            # serialized JSON string (edge cases in some ORM cycles).
            move_vals = (
                wizard.move_data
                if isinstance(wizard.move_data, list)
                else json.loads(wizard.move_data)
            )
            preview_columns = [
                {'field': 'account_id', 'label': _('Account')},
                {'field': 'name', 'label': _('Label')},
                {'field': 'partner_id', 'label': _('Partner')},
                {'field': 'debit', 'label': _('Debit'), 'class': 'text-end text-nowrap'},
                {'field': 'credit', 'label': _('Credit'), 'class': 'text-end text-nowrap'},
            ]
            preview_vals = []
            currency = wizard.company_id.currency_id
            for move in move_vals[:4]:
                preview_vals.append(
                    self.env['account.move']._move_dict_to_preview_vals(move, currency),
                )
            preview_discarded = max(0, len(move_vals) - len(preview_vals))
            wizard.preview_move_data = {
                'groups_vals': preview_vals,
                'options': {
                    'discarded_number': (
                        _("%d more moves", preview_discarded)
                        if preview_discarded else False
                    ),
                    'columns': preview_columns,
                },
            }

    # =====================================================================
    # SECTION 8 — Validation constraints
    # =====================================================================
    @api.constrains('cutoff_date', 'company_id', 'schedule_ids', 'journal_id')
    def _check_date(self):
        """Block posting to a locked period.

        Delegates to :meth:`res.company._get_violated_lock_dates`
        (defined in ``addons/account/models/company.py``) which itself
        invokes :meth:`_get_violated_soft_lock_date` per soft lock-date
        field.  That helper returns a violation only when the
        accounting date violates the *user-specific* lock date — the
        date computed by :meth:`_get_user_lock_date` which **already
        incorporates any active** :class:`account.lock_exception`
        records that apply to the current user.  In other words, a user
        with a valid exception covering ``cutoff_date`` will receive an
        empty ``violated`` list, while a user with a stale or
        irrelevant exception will still see the violation.

        We therefore do **not** maintain a redundant clearance loop in
        this wizard — doing so risks dismissing legitimate violations
        when an exception is present but its ``lock_date`` does not
        actually cover ``cutoff_date``.  Trusting the core helper
        guarantees consistent behaviour with the rest of the
        accounting subsystem (e.g., ``account.move.action_post``,
        ``account.automatic.entry.wizard._check_date``) and avoids
        the lock-exception-clearance bug flagged in code review CR-2
        (CP4).

        Hard lock dates are non-overridable per Odoo's lock-exception
        model (only ``fiscalyear_lock_date``, ``tax_lock_date``,
        ``sale_lock_date`` and ``purchase_lock_date`` may be
        excepted), and ``_get_violated_lock_dates`` accounts for the
        ``hard_lock_date`` independently of the exception machinery,
        so any ``hard_lock_date`` violation always triggers the error.

        :raises ValidationError: when the cut-off date violates one or
            more user-effective lock dates.
        """
        for wizard in self:
            if not wizard.cutoff_date or not wizard.company_id:
                continue
            # ``_get_violated_lock_dates`` returns ONLY violations that
            # remain after exception application; an empty result means
            # the user is authorised to post on ``cutoff_date``.
            violated = wizard.company_id._get_violated_lock_dates(
                wizard.cutoff_date,
                False,
                wizard.journal_id,
            )
            if violated:
                raise ValidationError(_(
                    "The cut-off date %(date)s is protected by: %(lock_date_info)s. "
                    "Adjust the date or request a temporary lock exception "
                    "from your accountant.",
                    date=format_date(self.env, wizard.cutoff_date),
                    lock_date_info=self.env['res.company']._format_lock_dates(violated),
                ))

    # =====================================================================
    # SECTION 9 — Helper methods (move-dict construction)
    # =====================================================================
    def _get_lock_safe_date(self, target_date):
        """Return the earliest lock-safe accounting date >= ``target_date``.

        Mirrors :meth:`account.automatic.entry.wizard._get_lock_safe_date`:
        builds a phantom :class:`account.move` on the wizard's journal
        so :meth:`~account.move._get_accounting_date` can leverage the
        journal's sequence-aware accounting-date computation.

        :raises UserError: when no safe date can be found within 60 days
            of ``target_date`` — typically indicates a malformed lock
            configuration that the user must resolve manually.
        :returns: a :class:`datetime.date` instance.
        """
        self.ensure_one()
        reference_move = self.env['account.move'].new({
            'journal_id': self.journal_id.id if self.journal_id else False,
            'company_id': self.company_id.id,
            'move_type': 'entry',
            'invoice_date': target_date,
        })
        safe_date = reference_move._get_accounting_date(target_date, False)
        if safe_date and (safe_date - target_date).days > 60:
            raise UserError(_(
                "Could not find a lock-safe date within 60 days of "
                "%(target)s for journal %(journal)s. Please review your "
                "fiscal lock dates.",
                target=format_date(self.env, target_date),
                journal=(
                    self.journal_id.display_name if self.journal_id
                    else _('[no journal]')
                ),
            ))
        return safe_date or target_date

    def _get_cut_off_label_format(self):
        """Return the translatable format string used as the move ref.

        Placeholders supported by :meth:`_format_strings`:

        * ``{schedule_name}`` — the deferred schedule's display name.
        * ``{cutoff_date}``   — the localized cut-off date.
        * ``{amount}``        — formatted monetary amount (when set).
        * ``{partner}``       — partner display name (when set).
        """
        self.ensure_one()
        return _("Deferred Revenue Cut-off: {schedule_name} - Period ending {cutoff_date}")

    def _format_strings(self, template, schedule, amount=None):
        """Substitute named placeholders in ``template`` with schedule data.

        Used to produce both the move ``ref`` and the per-line ``name``
        labels.  Uses :func:`odoo.tools.format_date` for date
        localization and :func:`odoo.tools.formatLang` for monetary
        formatting in the company currency.
        """
        self.ensure_one()
        currency = self.company_id.currency_id
        return template.format(
            schedule_name=schedule.name or _('Deferred Schedule'),
            cutoff_date=format_date(self.env, self.cutoff_date),
            amount=(
                formatLang(self.env, abs(amount), currency_obj=currency)
                if amount else ''
            ),
            partner=(
                schedule.partner_id.display_name
                if schedule.partner_id else ''
            ),
        )

    def _get_move_line_dict_vals_change_period(self, schedule, recognition_amount, label):
        """Build the (debit, credit) line tuple for one recognition tranche.

        **Accounting convention summary**

        A cut-off entry shifts the recognized portion of a deferred
        balance from the balance-sheet *deferral* account into the P&L
        *recognition* account.  The direction of the entry is driven
        by whether the recognition account is income- or expense-typed:

        * **Revenue case** (recognition account ``account_type`` in
          :data:`_INCOME_ACCOUNT_TYPES`): the schedule originated from
          a customer invoice whose proceeds were initially booked as a
          *liability* on ``deferred_account_id`` (e.g., "Unearned
          Revenue").  The cut-off entry reduces the liability and
          books revenue in the same period:

              Debit  ``schedule.deferred_account_id``     (clears liability)
              Credit ``schedule.recognition_account_id``  (books revenue)

        * **Expense case** (recognition account ``account_type`` in
          :data:`_EXPENSE_ACCOUNT_TYPES`): the schedule originated
          from a vendor bill whose payment was initially capitalised
          as an *asset* on ``deferred_account_id`` (e.g., "Prepaid
          Expense").  The cut-off entry reduces the asset and books
          the expense in the period of consumption:

              Debit  ``schedule.recognition_account_id``  (books expense)
              Credit ``schedule.deferred_account_id``     (clears asset)

        Both lines preserve ``schedule.analytic_distribution`` so any
        analytic plan attribution flows through the cut-off entry.

        Multi-currency: when ``schedule.currency_id`` differs from the
        company currency, ``amount_currency`` is populated on each
        line.  The schedule's currency drives the foreign value; the
        company currency drives the native ``debit`` / ``credit``.

        :returns: a list of two ``(0, 0, vals)`` tuples suitable for
            assignment to ``account.move.line_ids``.
        """
        self.ensure_one()
        company_currency = self.company_id.currency_id
        schedule_currency = schedule.currency_id or company_currency
        is_multi_currency = (
            schedule_currency and company_currency
            and schedule_currency != company_currency
        )

        # Round amounts in company currency for native debit/credit
        rounded_amount = company_currency.round(recognition_amount)

        # Determine direction based on recognition account type.
        # Revenue = liability clearing; Expense = asset clearing.
        recognition_type = schedule.recognition_account_id.account_type
        is_revenue = recognition_type in _INCOME_ACCOUNT_TYPES

        if is_revenue:
            debit_account = schedule.deferred_account_id
            credit_account = schedule.recognition_account_id
        else:
            # Expense (or any non-revenue type): debit recognition (book
            # expense), credit deferred (clear prepaid asset).
            debit_account = schedule.recognition_account_id
            credit_account = schedule.deferred_account_id

        base_line_vals = {
            'name': label,
            'partner_id': schedule.partner_id.id or False,
            'currency_id': schedule_currency.id if schedule_currency else False,
            'analytic_distribution': schedule.analytic_distribution or False,
        }

        # Foreign-currency amounts (signed: debit positive, credit negative)
        fcy_amount = (
            schedule_currency.round(recognition_amount)
            if is_multi_currency else 0.0
        )

        debit_line = dict(base_line_vals)
        debit_line.update({
            'debit': rounded_amount,
            'credit': 0.0,
            'account_id': debit_account.id,
        })
        if is_multi_currency:
            debit_line['amount_currency'] = fcy_amount

        credit_line = dict(base_line_vals)
        credit_line.update({
            'debit': 0.0,
            'credit': rounded_amount,
            'account_id': credit_account.id,
        })
        if is_multi_currency:
            credit_line['amount_currency'] = -fcy_amount

        return [(0, 0, debit_line), (0, 0, credit_line)]

    def _get_move_dict_vals_change_period(self, schedules, cutoff_date):
        """Build the list of ``account.move`` value dicts for posting.

        Behavior:

        * Filters each schedule's ``line_ids`` to those with
          ``state='draft'`` AND ``recognition_date <= cutoff_date``.
        * In ``single`` / ``preview`` / ``reversal`` modes: produces
          one move per schedule with that schedule's qualifying lines.
        * In ``batch`` mode: groups schedules by ``company_id`` and
          produces one consolidated move per company.
        * Each schedule contributes one debit + credit pair per
          qualifying recognition line, built by
          :meth:`_get_move_line_dict_vals_change_period`.
        * Each move's ``date`` is the lock-safe date derived from
          ``cutoff_date`` via :meth:`_get_lock_safe_date`.
        * Each move's ``ref`` is the formatted cut-off label.

        :param schedules: an :class:`account.deferred.schedule`
            recordset to process.
        :param cutoff_date: the cut-off date.
        :returns: a list of dicts suitable for
            ``self.env['account.move'].create(move_vals_list)``.
        """
        self.ensure_one()
        if not schedules:
            return []

        safe_date = self._get_lock_safe_date(cutoff_date)
        label_template = self._get_cut_off_label_format()
        move_vals_list = []

        if self.mode == 'batch':
            # Group schedules by company. The wizard's journal is shared
            # across the batch; only the company differs (multi-company
            # scenarios). One consolidated move per company.
            schedules_by_company = defaultdict(
                lambda: self.env['account.deferred.schedule'],
            )
            for schedule in schedules:
                schedules_by_company[schedule.company_id] += schedule

            for company, company_schedules in schedules_by_company.items():
                line_ids = []
                schedule_line_map = []  # (schedule, qualifying_lines) for linking
                total_amount = 0.0
                for schedule in company_schedules:
                    qualifying_lines = schedule.line_ids.filtered(
                        lambda line, c=cutoff_date: (
                            line.state == 'draft'
                            and line.recognition_date
                            and line.recognition_date <= c
                        ),
                    )
                    if not qualifying_lines:
                        continue
                    schedule_line_map.append((schedule.id, qualifying_lines.ids))
                    for rec_line in qualifying_lines:
                        label = self._format_strings(
                            label_template, schedule, rec_line.recognition_amount,
                        )
                        line_pairs = self._get_move_line_dict_vals_change_period(
                            schedule, rec_line.recognition_amount, label,
                        )
                        line_ids.extend(line_pairs)
                        total_amount += rec_line.recognition_amount

                if line_ids:
                    # Use the first schedule's label as the move ref for
                    # consolidated batches; the per-line labels carry the
                    # detailed schedule attribution.
                    first_schedule = company_schedules[:1]
                    move_vals_list.append({
                        'move_type': 'entry',
                        'journal_id': self.journal_id.id,
                        'company_id': company.id,
                        'date': fields.Date.to_string(safe_date),
                        'ref': self._format_strings(
                            label_template, first_schedule, total_amount,
                        ),
                        'line_ids': line_ids,
                        # Embedded routing table consumed by
                        # ``_link_recognition_lines`` to associate posted
                        # lines back to their schedules.
                        'deferred_cutoff_routing': schedule_line_map,
                    })
        else:
            # single / preview / reversal: one move per schedule
            for schedule in schedules:
                qualifying_lines = schedule.line_ids.filtered(
                    lambda line, c=cutoff_date: (
                        line.state == 'draft'
                        and line.recognition_date
                        and line.recognition_date <= c
                    ),
                )
                if not qualifying_lines:
                    continue
                line_ids = []
                total_amount = 0.0
                for rec_line in qualifying_lines:
                    label = self._format_strings(
                        label_template, schedule, rec_line.recognition_amount,
                    )
                    line_pairs = self._get_move_line_dict_vals_change_period(
                        schedule, rec_line.recognition_amount, label,
                    )
                    line_ids.extend(line_pairs)
                    total_amount += rec_line.recognition_amount

                move_vals_list.append({
                    'move_type': 'entry',
                    'journal_id': self.journal_id.id,
                    'company_id': schedule.company_id.id,
                    'date': fields.Date.to_string(safe_date),
                    'ref': self._format_strings(
                        label_template, schedule, total_amount,
                    ),
                    'line_ids': line_ids,
                    'deferred_cutoff_routing': [(schedule.id, qualifying_lines.ids)],
                })

        return move_vals_list

    def _link_recognition_lines(self, created_moves, routing_data):
        """Mark recognition lines as posted and link them to their moves.

        Walks the ``routing_data`` list (one entry per created move) and
        for each ``(schedule_id, recognition_line_ids)`` mapping:

        1. Sets ``state='posted'`` on the recognition lines.
        2. Sets ``move_id`` on the recognition lines to the matching
           created move (enforcing the bidirectional schedule/move
           invariant).
        3. Populates ``move_line_ids`` (Many2many) on each recognition
           line with the move's deferred / recognition account lines.
        4. Sets ``deferred_schedule_id`` and ``deferred_line_id`` on
           each created move line for traceability from the journal
           entry side.

        :param created_moves: an :class:`account.move` recordset of the
            posted cut-off entries.
        :param routing_data: a list of lists of ``(schedule_id,
            line_ids_list)`` tuples — one outer entry per created move.
        """
        self.ensure_one()
        DeferredSchedule = self.env['account.deferred.schedule']
        DeferredLine = self.env['account.deferred.line']

        # Iterate moves and routing in lock-step (same order as
        # _get_move_dict_vals_change_period produced them).
        for move, schedule_routing in zip(created_moves, routing_data):
            for schedule_id, line_ids in schedule_routing:
                schedule = DeferredSchedule.browse(schedule_id).exists()
                if not schedule:
                    continue
                rec_lines = DeferredLine.browse(line_ids).exists()
                if not rec_lines:
                    continue

                # Identify move lines belonging to this schedule by
                # matching on the schedule's deferred / recognition
                # accounts.
                schedule_accounts = (
                    schedule.deferred_account_id | schedule.recognition_account_id
                )
                schedule_move_lines = move.line_ids.filtered(
                    lambda ml, accs=schedule_accounts: ml.account_id in accs,
                )

                # Stamp the schedule back-reference on the move lines
                if schedule_move_lines:
                    schedule_move_lines.write({
                        'deferred_schedule_id': schedule.id,
                    })

                # Mark recognition lines as posted and link to the move
                rec_lines.write({
                    'state': 'posted',
                    'move_id': move.id,
                })

                # Populate the per-line many2many of move lines
                if schedule_move_lines:
                    rec_lines.write({
                        'move_line_ids': [(6, 0, schedule_move_lines.ids)],
                    })
                # Stamp the deferred_line_id back-reference on the
                # individual move lines, matching by recognition_date
                # where possible (date-aligned schedules) and falling
                # back to the first qualifying line (consolidated
                # schedules with a single-tranche cutoff).
                for ml in schedule_move_lines:
                    matching = rec_lines.filtered(
                        lambda r, d=move.date: r.recognition_date == d,
                    )[:1]
                    if not matching:
                        matching = rec_lines[:1]
                    if matching:
                        ml.deferred_line_id = matching.id

    # =====================================================================
    # SECTION 10 — Action methods (UI buttons)
    # =====================================================================
    def action_preview(self):
        """Force preview computation and re-open the wizard form.

        DR-003 Scenario 2: no journal entries are created.  Invalidates
        the JSON caches so the user always sees fresh data even if the
        underlying schedules were modified after the wizard was first
        rendered.
        """
        self.ensure_one()
        # Invalidate the computed caches so the recompute fires
        self.invalidate_recordset(['move_data', 'preview_move_data'])
        # Read the (now-fresh) value to confirm at least one move is
        # buildable; otherwise raise a user-friendly error.
        if not self.move_data:
            raise UserError(_(
                "No qualifying recognition lines were found at cut-off "
                "date %(date)s for the selected schedule(s). Verify the "
                "schedules are confirmed and have draft recognition lines "
                "on or before this date.",
                date=format_date(self.env, self.cutoff_date),
            ))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Cut-off Entry Preview'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': dict(self.env.context, deferred_cutoff_show_preview=True),
        }

    def action_post(self):
        """Create, post, and link cut-off journal entries.

        DR-003 Scenario 1 (single) and Scenario 3 (batch).  Pulls the
        precomputed ``move_data`` (built by
        :meth:`_get_move_dict_vals_change_period`), creates one
        :class:`account.move` per entry, posts them, and runs
        :meth:`_link_recognition_lines` to flip the recognition lines
        to ``state='posted'`` and stamp the move references.

        Records a chatter message on each affected schedule for the
        audit trail (DR-003 Scenario 1 fourth assertion: "each entry
        should reference the source deferral schedule").

        :returns: an ``ir.actions.act_window`` opening the posted moves.
        """
        self.ensure_one()
        if not self.schedule_ids:
            raise UserError(_(
                "No schedules selected. Please select at least one schedule "
                "to generate cut-off entries.",
            ))
        if not self.move_data:
            raise UserError(_(
                "No qualifying recognition lines were found at cut-off "
                "date %(date)s. Nothing to post.",
                date=format_date(self.env, self.cutoff_date),
            ))

        move_vals_list = (
            self.move_data
            if isinstance(self.move_data, list)
            else json.loads(self.move_data)
        )
        if not move_vals_list:
            raise UserError(_("No journal entry data was computed."))

        # Strip out the routing data before passing to ORM create.
        routing_data = []
        clean_vals_list = []
        for vals in move_vals_list:
            cleaned = dict(vals)
            routing = cleaned.pop('deferred_cutoff_routing', [])
            routing_data.append(routing)
            clean_vals_list.append(cleaned)

        created_moves = self.env['account.move'].create(clean_vals_list)
        created_moves.action_post()

        # Link recognition lines and stamp move-line back-references
        self._link_recognition_lines(created_moves, routing_data)

        # Audit-trail chatter on each affected schedule
        for move, schedule_routing in zip(created_moves, routing_data):
            for schedule_id, _line_ids in schedule_routing:
                schedule = self.env['account.deferred.schedule'].browse(schedule_id)
                if schedule.exists():
                    schedule.message_post(body=Markup(
                        _("Cut-off entry posted: %(link)s")
                        % {'link': move._get_html_link()},
                    ))

        return self._action_view_moves(created_moves, with_reversal=False)

    def action_post_with_reversal(self):
        """Post cut-off entries plus reversal entries.

        DR-003 Scenario 5.  Calls :meth:`action_post` to generate the
        cut-off moves, then immediately calls
        :meth:`account.move._reverse_moves` with
        ``default_values_list`` containing the per-move reversal date
        and ``auto_post='at_date'`` so the reversals post automatically
        on the reversal date via the standard
        ``ir_cron_auto_post_draft_entry`` cron.

        Reversals are linked back to their originals via
        ``adjusting_entry_origin_move_ids`` for full audit traceability.
        Each affected schedule receives a chatter message documenting
        the scheduled reversal.

        :returns: an ``ir.actions.act_window`` showing both the cut-off
            and the reversal moves.
        """
        self.ensure_one()
        if not self.reversal_date:
            raise UserError(_(
                "Reversal date is required. Defaults to the first day of "
                "the month following the cut-off date — adjust if needed.",
            ))
        if self.cutoff_date and self.reversal_date <= self.cutoff_date:
            raise UserError(_(
                "Reversal date %(rev)s must be strictly after the cut-off "
                "date %(cut)s.",
                rev=format_date(self.env, self.reversal_date),
                cut=format_date(self.env, self.cutoff_date),
            ))

        # Run the standard post first; if no moves get created the
        # action_post call raises a UserError that we let propagate.
        if not self.schedule_ids:
            raise UserError(_(
                "No schedules selected. Please select at least one schedule "
                "to generate cut-off entries.",
            ))
        if not self.move_data:
            raise UserError(_(
                "No qualifying recognition lines were found at cut-off "
                "date %(date)s. Nothing to post.",
                date=format_date(self.env, self.cutoff_date),
            ))

        # Replicate action_post inline so we keep a handle on the
        # created moves (rather than recovering them from an action dict).
        move_vals_list = (
            self.move_data
            if isinstance(self.move_data, list)
            else json.loads(self.move_data)
        )
        routing_data = []
        clean_vals_list = []
        for vals in move_vals_list:
            cleaned = dict(vals)
            routing = cleaned.pop('deferred_cutoff_routing', [])
            routing_data.append(routing)
            clean_vals_list.append(cleaned)

        created_moves = self.env['account.move'].create(clean_vals_list)
        created_moves.action_post()
        self._link_recognition_lines(created_moves, routing_data)

        # Audit-trail chatter for the cut-off moves
        for move, schedule_routing in zip(created_moves, routing_data):
            for schedule_id, _line_ids in schedule_routing:
                schedule = self.env['account.deferred.schedule'].browse(schedule_id)
                if schedule.exists():
                    schedule.message_post(body=Markup(
                        _("Cut-off entry posted: %(link)s")
                        % {'link': move._get_html_link()},
                    ))

        # Build per-move reversal default values
        default_values_list = [
            {
                'date': self.reversal_date,
                'auto_post': 'at_date',
                'ref': _("Reversal of %s", move.ref or move.name or ''),
            }
            for move in created_moves
        ]
        reversal_moves = created_moves._reverse_moves(
            default_values_list=default_values_list,
            cancel=False,
        )

        # Link reversals back to originals via adjusting_entry_origin_move_ids
        for original, reversal in zip(created_moves, reversal_moves):
            reversal.adjusting_entry_origin_move_ids = [(4, original.id)]

        # Audit-trail chatter for the reversal moves
        for reversal_move, schedule_routing in zip(reversal_moves, routing_data):
            for schedule_id, _line_ids in schedule_routing:
                schedule = self.env['account.deferred.schedule'].browse(schedule_id)
                if schedule.exists():
                    schedule.message_post(body=Markup(
                        _(
                            "Reversal entry scheduled for %(date)s: %(link)s",
                        ) % {
                            'date': format_date(self.env, self.reversal_date),
                            'link': reversal_move._get_html_link(),
                        },
                    ))

        all_moves = created_moves | reversal_moves
        return self._action_view_moves(all_moves, with_reversal=True)

    # =====================================================================
    # SECTION 11 — Internal action helper (kept private; not in schema)
    # =====================================================================
    def _action_view_moves(self, moves, with_reversal=False):
        """Build the ``ir.actions.act_window`` opening the created moves.

        Single move => form view; multiple moves => list+form view.
        ``with_reversal=True`` adjusts the action title.
        """
        self.ensure_one()
        title = (
            _('Cut-off Entries with Reversal') if with_reversal
            else (
                _('Cut-off Entry') if len(moves) == 1
                else _('Cut-off Entries')
            )
        )
        if len(moves) == 1 and not with_reversal:
            return {
                'type': 'ir.actions.act_window',
                'name': title,
                'res_model': 'account.move',
                'res_id': moves.id,
                'view_mode': 'form',
                'views': [(False, 'form')],
                'target': 'current',
            }
        return {
            'type': 'ir.actions.act_window',
            'name': title,
            'res_model': 'account.move',
            'domain': [('id', 'in', moves.ids)],
            'view_mode': 'list,form',
            'target': 'current',
        }
