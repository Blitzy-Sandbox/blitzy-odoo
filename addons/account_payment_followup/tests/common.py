# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Shared Test Common Base — Payment Follow-up Module
===================================================

Provides a base test class :class:`AccountPaymentFollowupTestCommon` that
extends Odoo's :class:`~odoo.addons.account.tests.common.AccountTestInvoicingCommon`
fixture with all assets required by the PF-001 through PF-005 test modules:

  - Deterministic frozen date (2024-06-30) for aging calculations
  - Multiple partners spanning all aging buckets:
      * ``partner_current``        — due date in future, not overdue
      * ``partner_overdue_7d``     — 7 days past due → Level 1 (First Reminder)
      * ``partner_overdue_14d``    — 14 days past due → Level 2 (Second Reminder)
      * ``partner_overdue_21d``    — 21 days past due → Level 3 (Warning)
      * ``partner_overdue_30d``    — 30 days past due → Level 4 (Final Notice)
      * ``partner_overdue_45d``    — 45 days past due → Level 4 (Final Notice)
      * ``partner_overdue_95d``    — 95 days past due → Level 4 (Final Notice)
      * ``partner_mixed_aging``    — multiple invoices spanning all buckets
  - Posted customer invoices (out_invoice) with controlled ``invoice_date_due``
  - Immediate payment term so ``date_maturity == invoice_date``
  - Helper methods for invoice creation, history recording, partner setup

All subclasses should use ``@freeze_time(cls.FROZEN_DATE)`` around assertions
that depend on today's date, to ensure deterministic aging-bucket placement.

The common.py module is foundational: it is imported first by ``__init__.py``
and provides fixtures consumed by every ``test_pf_*.py`` module in this
package.

Rules Compliance (AAP §0.7)
---------------------------
- **R-01** (Module Independence): no imports from sibling new modules
  (``account_asset_management``, ``account_budget_management``,
  ``account_deferred_revenue``).
- **R-02** (No Enterprise Dependencies): no imports from Enterprise addons
  (``account_followup``, ``account_accountant``, ``account_reports``).
- **R-04** (Per-Story Coverage Gate): this base class is consumed by all
  five PF-00X test modules to attain ≥80% coverage per story.
- **R-07** (No ``sudo()`` without justification): no ``sudo()`` calls
  appear in this file.
- **R-09** (Exact Folder Name): file resides at
  ``addons/account_payment_followup/tests/common.py``.
"""

from datetime import date, timedelta

from freezegun import freeze_time

from odoo import Command, fields
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class AccountPaymentFollowupTestCommon(AccountTestInvoicingCommon):
    """Shared fixture base for all PF-00X test modules.

    Inherits from :class:`AccountTestInvoicingCommon` which provides:

      - ``cls.company_data`` dict with pre-configured company, journals,
        accounts (``default_journal_bank``, ``default_journal_sale``,
        ``default_journal_purchase``, ``default_account_revenue``,
        ``default_account_expense``, ``default_account_receivable``,
        ``default_account_payable``)
      - ``cls.partner_a``, ``cls.partner_b`` — generic test partners
      - ``cls.product_a``, ``cls.product_b`` — test products
      - ``cls.pay_terms_a`` — Immediate Payment term
        (``date_maturity == invoice_date``)
      - ``cls.tax_sale_a`` — default sale tax
      - ``cls.env.user`` — ``accountman`` user with account manager group

    Extends these with follow-up-specific test data (see class docstring
    above) so that subclasses can immediately exercise PF-001 through
    PF-005 behaviour against a deterministic, fully-populated database.

    Naming Conventions
    ------------------
    - Partner fixtures use the prefix ``partner_`` followed by an aging
      qualifier (``current``, ``overdue_7d``, ``mixed_aging``, etc.).
    - Invoice fixtures use the prefix ``inv_`` followed by the days-overdue
      magnitude (``inv_current``, ``inv_7d``, ``inv_mixed_15d``, etc.).
    - Helper methods use the underscore prefix ``_`` to signal they are
      for-test-use only and not part of any public API.

    Performance Notes
    -----------------
    All fixtures are built once per test class via :meth:`setUpClass` rather
    than per-test in :meth:`setUp`. The :func:`freeze_time` context manager
    wraps fixture creation so that ``invoice_date_due`` and ORM-derived
    ``date_maturity`` values resolve against the fixed reference date,
    making aging calculations stable across CI runs and developer
    environments.
    """

    # -------------------------------------------------------------------------
    # CLASS CONSTANTS
    # -------------------------------------------------------------------------
    # FROZEN_DATE is the deterministic reference date used by all aging
    # calculations. Choosing a mid-year non-month-boundary date (June 30)
    # avoids edge-case behaviour at fiscal-year and month boundaries.
    # Exposed at class level so subclasses can reference it without
    # duplicating the constant or re-importing ``datetime.date``.
    # -------------------------------------------------------------------------

    FROZEN_DATE = date(2024, 6, 30)

    @classmethod
    def setUpClass(cls):
        """Create all follow-up-specific test fixtures.

        Inherits the rich Odoo accounting fixtures from
        :meth:`AccountTestInvoicingCommon.setUpClass` (chart of accounts,
        journals, products, taxes, payment terms, the ``accountman`` user,
        ``partner_a`` / ``partner_b``), then layers on the follow-up-
        specific partner and invoice fixtures inside a
        :func:`freeze_time` context so all date-dependent fields are
        deterministic.

        Multi-company alignment
        -----------------------
        The seed ``account.followup.level`` records (loaded from
        ``data/followup_data.xml``) and the PF-002 ``ir.cron`` are
        anchored to whichever company was active when the module was
        installed (typically ``base.main_company``).
        :class:`AccountTestInvoicingCommon` creates an isolated test
        company and assigns the ``accountman`` user solely to it, which
        means the global multi-company ``ir.rule`` defined in
        ``security/followup_security.xml`` would otherwise block the
        property accessors below from reading those seed records.

        Granting the test user membership in **all** companies — a
        permission they already hold via the ``base.group_system`` group
        added by :meth:`AccountTestInvoicingCommon.get_default_groups` —
        aligns the test user's ``company_ids`` with the seed-record
        scope so subclasses can resolve the levels via :func:`env.ref`
        without further configuration. No ``sudo()`` is used: the
        ``base.group_system`` membership is sufficient ACL for the
        ``res.users.company_ids`` write below.

        Subclasses that need additional fixtures should override this
        method, call ``super().setUpClass()`` first, and then add their
        own fixtures (also wrapped in ``freeze_time(cls.FROZEN_DATE)``
        if they require deterministic dates).
        """
        super().setUpClass()

        # Align the test user's company access with the seed-record
        # company scope. ``base.group_system`` (granted by the parent
        # ``get_default_groups()``) authorises this write — no
        # privilege escalation required.
        all_companies = cls.env['res.company'].search([])
        cls.env.user.company_ids = [Command.set(all_companies.ids)]

        # Marker attribute used by introspection in tests verifying that
        # the freeze-time-protected fixture build executed successfully.
        cls._freeze_time_setup_started = True

        # Use ``freeze_time`` for all fixture-creation dates so that
        # aging-bucket placement is deterministic. This freezes both
        # ``datetime.now()`` and ``date.today()`` to ``cls.FROZEN_DATE``
        # for the duration of the ``with`` block, which means Odoo's
        # ORM-driven ``date_maturity`` computation (which falls back to
        # ``fields.Date.today()`` when payment terms don't specify a
        # delay) produces stable, reproducible values.
        with freeze_time(cls.FROZEN_DATE):
            cls._setup_overdue_partners()
            cls._setup_overdue_invoices()

    # -------------------------------------------------------------------------
    # FIXTURE BUILDERS — PARTNERS
    # -------------------------------------------------------------------------

    @classmethod
    def _setup_overdue_partners(cls):
        """Create partner fixtures spanning all aging buckets.

        Eight partners total:

        - One non-overdue partner (``partner_current``) — due date in the
          future, no aging.
        - Six single-aging-bucket partners (``partner_overdue_7d``,
          ``partner_overdue_14d``, ``partner_overdue_21d``,
          ``partner_overdue_30d``, ``partner_overdue_45d``,
          ``partner_overdue_95d``) — each has exactly one overdue invoice
          placing them squarely in one bucket.
        - One mixed-aging partner (``partner_mixed_aging``) — multiple
          invoices spanning all five buckets, used for tests that exercise
          aggregate aging calculations.

        All partners use the Immediate Payment term (``cls.pay_terms_a``)
        so ``date_maturity == invoice_date``. The ``customer_rank=1``
        flag makes them visible in customer-only views and lookups, and
        ``email`` is required for PF-002 automated email generation.

        ``company_id=False`` makes the partners visible to all companies,
        which avoids multi-company isolation surprises in tests where the
        test runner may switch companies mid-run.
        """
        # Common partner attributes used as a baseline for all eight
        # partners. Each partner overrides ``name`` and ``email`` so they
        # are individually identifiable in test assertions and in the
        # follow-up email log. The ``placeholder@example.com`` email in
        # the template is a defensive default; every concrete partner
        # below overrides it with a unique address.
        partner_vals_template = {
            'customer_rank': 1,
            'property_payment_term_id': cls.pay_terms_a.id,
            'email': 'placeholder@example.com',
            # ``company_id=False`` makes partners visible to all companies
            # — avoids multi-company isolation surprises in tests.
            'company_id': False,
        }

        cls.partner_current = cls.env['res.partner'].create({
            **partner_vals_template,
            'name': 'Test Partner — Current (no overdue)',
            'email': 'current@test.com',
        })
        cls.partner_overdue_7d = cls.env['res.partner'].create({
            **partner_vals_template,
            'name': 'Test Partner — 7 days overdue',
            'email': 'overdue7@test.com',
        })
        cls.partner_overdue_14d = cls.env['res.partner'].create({
            **partner_vals_template,
            'name': 'Test Partner — 14 days overdue',
            'email': 'overdue14@test.com',
        })
        cls.partner_overdue_21d = cls.env['res.partner'].create({
            **partner_vals_template,
            'name': 'Test Partner — 21 days overdue',
            'email': 'overdue21@test.com',
        })
        cls.partner_overdue_30d = cls.env['res.partner'].create({
            **partner_vals_template,
            'name': 'Test Partner — 30 days overdue',
            'email': 'overdue30@test.com',
        })
        cls.partner_overdue_45d = cls.env['res.partner'].create({
            **partner_vals_template,
            'name': 'Test Partner — 45 days overdue',
            'email': 'overdue45@test.com',
        })
        cls.partner_overdue_95d = cls.env['res.partner'].create({
            **partner_vals_template,
            'name': 'Test Partner — 95 days overdue',
            'email': 'overdue95@test.com',
        })
        cls.partner_mixed_aging = cls.env['res.partner'].create({
            **partner_vals_template,
            'name': 'Test Partner — Mixed aging',
            'email': 'mixed@test.com',
        })

    # -------------------------------------------------------------------------
    # FIXTURE BUILDERS — INVOICES
    # -------------------------------------------------------------------------

    @classmethod
    def _setup_overdue_invoices(cls):
        """Create posted customer invoices with controlled due dates.

        Twelve invoices total:

        Single-bucket invoices (one per ``partner_overdue_*``):

        - ``inv_current``      — 0 days overdue (due today, not yet overdue)
        - ``inv_7d``           — 7 days overdue → Level 1 (First Reminder)
        - ``inv_14d``          — 14 days overdue → Level 2 (Second Reminder)
        - ``inv_21d``          — 21 days overdue → Level 3 (Warning)
        - ``inv_30d``          — 30 days overdue → Level 4 (Final Notice)
        - ``inv_45d``          — 45 days overdue → bucket 31-60
        - ``inv_95d``          — 95 days overdue → bucket 90+

        Mixed-aging invoices (all on ``partner_mixed_aging``):

        - ``inv_mixed_current`` — future-due (not yet overdue)
        - ``inv_mixed_15d``     — 15 days overdue → bucket 1-30
        - ``inv_mixed_45d``     — 45 days overdue → bucket 31-60
        - ``inv_mixed_75d``     — 75 days overdue → bucket 61-90
        - ``inv_mixed_100d``    — 100 days overdue → bucket 90+

        All invoices use ``move_type='out_invoice'`` (customer invoice),
        the Immediate Payment term so ``date_maturity == invoice_date``,
        no taxes (so invoice total == ``price_unit``), and are posted
        (``state='posted'``, ``payment_state='not_paid'``).
        """
        today = cls.FROZEN_DATE

        # ------------------------------------------------------------------
        # Single-bucket invoices: one invoice per partner, placing each
        # partner cleanly into one aging bucket.
        # ------------------------------------------------------------------

        # Current (not overdue): due date == today (delta == 0; standard
        # finance convention treats the due date as the last timely day,
        # so an invoice due today is NOT yet overdue).
        cls.inv_current = cls._create_overdue_invoice(
            partner=cls.partner_current,
            invoice_date=today,
            amount=1000.00,
        )

        # 7 days overdue → Level 1 (First Reminder)
        cls.inv_7d = cls._create_overdue_invoice(
            partner=cls.partner_overdue_7d,
            invoice_date=today - timedelta(days=7),
            amount=1500.00,
        )

        # 14 days overdue → Level 2 (Second Reminder)
        cls.inv_14d = cls._create_overdue_invoice(
            partner=cls.partner_overdue_14d,
            invoice_date=today - timedelta(days=14),
            amount=2000.00,
        )

        # 21 days overdue → Level 3 (Warning)
        cls.inv_21d = cls._create_overdue_invoice(
            partner=cls.partner_overdue_21d,
            invoice_date=today - timedelta(days=21),
            amount=2500.00,
        )

        # 30 days overdue → Level 4 (Final Notice), bucket 1-30
        cls.inv_30d = cls._create_overdue_invoice(
            partner=cls.partner_overdue_30d,
            invoice_date=today - timedelta(days=30),
            amount=3000.00,
        )

        # 45 days overdue → Level 4 (Final Notice), bucket 31-60
        cls.inv_45d = cls._create_overdue_invoice(
            partner=cls.partner_overdue_45d,
            invoice_date=today - timedelta(days=45),
            amount=4500.00,
        )

        # 95 days overdue → Level 4 (Final Notice), bucket 90+
        cls.inv_95d = cls._create_overdue_invoice(
            partner=cls.partner_overdue_95d,
            invoice_date=today - timedelta(days=95),
            amount=9500.00,
        )

        # ------------------------------------------------------------------
        # Mixed-aging invoices: all on ``partner_mixed_aging``, one per
        # bucket, used to exercise aggregate aging calculations.
        # ------------------------------------------------------------------

        # Future-due (5 days from now) → 'current' bucket
        cls.inv_mixed_current = cls._create_overdue_invoice(
            partner=cls.partner_mixed_aging,
            invoice_date=today + timedelta(days=5),
            amount=100.00,
        )

        # 15 days overdue → bucket 1-30
        cls.inv_mixed_15d = cls._create_overdue_invoice(
            partner=cls.partner_mixed_aging,
            invoice_date=today - timedelta(days=15),
            amount=200.00,
        )

        # 45 days overdue → bucket 31-60
        cls.inv_mixed_45d = cls._create_overdue_invoice(
            partner=cls.partner_mixed_aging,
            invoice_date=today - timedelta(days=45),
            amount=300.00,
        )

        # 75 days overdue → bucket 61-90
        cls.inv_mixed_75d = cls._create_overdue_invoice(
            partner=cls.partner_mixed_aging,
            invoice_date=today - timedelta(days=75),
            amount=400.00,
        )

        # 100 days overdue → bucket 90+
        cls.inv_mixed_100d = cls._create_overdue_invoice(
            partner=cls.partner_mixed_aging,
            invoice_date=today - timedelta(days=100),
            amount=500.00,
        )

    # -------------------------------------------------------------------------
    # HELPER METHODS — INVOICES
    # -------------------------------------------------------------------------

    @classmethod
    def _create_overdue_invoice(cls, partner, invoice_date, amount,
                                move_type='out_invoice', post=True,
                                tax_ids=None):
        """Create a minimal customer invoice with the Immediate payment term.

        The Immediate payment term (:attr:`cls.pay_terms_a`) causes
        ``date_maturity`` to equal ``invoice_date``, giving deterministic
        ``days_overdue`` calculations when frozen-time is set to a known
        reference date.

        Mirrors the pattern from
        ``addons/account_financial_report_ce/tests/test_aged_partner.py``
        :meth:`_create_aged_invoice`, adapted for the follow-up domain
        (no analytic distribution, no ``account_id`` override on the line
        — Odoo derives the receivable account from the partner's
        ``property_account_receivable_id`` via product / journal defaults).

        :param partner: ``res.partner`` record (required).
        :param invoice_date: ``datetime.date`` — invoice date AND, via the
            Immediate Payment term, the line's ``date_maturity``.
        :param amount: line ``price_unit`` (positive ``float``); the
            invoice total equals this value because the line carries no
            taxes (see ``tax_ids`` parameter).
        :param move_type: ``'out_invoice'`` (customer invoice) or
            ``'out_refund'`` (customer credit note). Default ``'out_invoice'``.
        :param post: If ``True`` (default), call :meth:`action_post` on
            the move before returning. Set to ``False`` to obtain a
            draft move (useful for tests that exercise draft-state
            behaviour).
        :param tax_ids: Optional list/tuple of ``Command`` operations to
            apply to the line's ``tax_ids``. ``None`` (default) and
            ``False`` both expand to ``[Command.clear()]`` so the line
            carries no taxes; pass an explicit list (e.g.,
            ``[Command.set([cls.tax_sale_a.id])]``) to override.

        :return: The created ``account.move`` record (posted if
            ``post=True``, draft otherwise).
        """
        # Default tax behaviour: clear all taxes so invoice total ==
        # price_unit, simplifying amount assertions in tests.
        # ``tax_ids in (None, False)`` covers both the default unset
        # case and explicit ``False`` (which a caller might use to make
        # the no-taxes intent explicit at the call site).
        tax_spec = [Command.clear()] if tax_ids in (None, False) else tax_ids
        move = cls.env['account.move'].create({
            'move_type': move_type,
            'partner_id': partner.id,
            'invoice_date': invoice_date,
            # ``date`` (the move date / accounting date) is set equal to
            # ``invoice_date`` so journal entries are dated consistently
            # with the invoice itself; otherwise Odoo defaults to
            # ``fields.Date.today()`` which under freeze_time is also
            # ``cls.FROZEN_DATE`` but is explicit here for clarity.
            'date': invoice_date,
            # The Immediate Payment term forces ``date_maturity ==
            # invoice_date`` on the receivable line, which is essential
            # for deterministic days-overdue calculations.
            'invoice_payment_term_id': cls.pay_terms_a.id,
            'invoice_line_ids': [
                Command.create({
                    'name': 'Follow-up test line',
                    'price_unit': amount,
                    'quantity': 1.0,
                    'tax_ids': tax_spec,
                }),
            ],
        })
        if post:
            move.action_post()
        return move

    @classmethod
    def _create_overdue_credit_note(cls, partner, invoice_date, amount,
                                    post=True):
        """Create a customer credit note (``out_refund``).

        Convenience wrapper around :meth:`_create_overdue_invoice` that
        sets ``move_type='out_refund'``. Used by tests that exercise
        credit-note behaviour (e.g., PF-005 BR-006: credit notes reduce
        the partner's total overdue via signed ``amount_residual``).

        :param partner: ``res.partner`` record (required).
        :param invoice_date: ``datetime.date`` — credit note date and
            ``date_maturity``.
        :param amount: line ``price_unit`` (positive ``float``); the
            credit note total equals this amount and reduces the
            partner's outstanding receivables when applied.
        :param post: If ``True`` (default), post the move; ``False``
            yields a draft credit note.

        :return: The created ``account.move`` record with
            ``move_type='out_refund'``.
        """
        return cls._create_overdue_invoice(
            partner=partner,
            invoice_date=invoice_date,
            amount=amount,
            move_type='out_refund',
            post=post,
        )

    # -------------------------------------------------------------------------
    # HELPER METHODS — HISTORY RECORDS (PF-004)
    # -------------------------------------------------------------------------

    @classmethod
    def _create_history_record(cls, partner, action_type='email',
                               summary='Test follow-up action', level=None,
                               invoice=None, **kwargs):
        """Create an ``account.followup.history`` record with sensible defaults.

        Used by PF-004 action-history-tracking tests to seed audit-trail
        records without manually populating every required field.

        Required fields populated automatically:

        - ``partner_id`` — from the ``partner`` argument
        - ``action_type`` — from the ``action_type`` argument
        - ``action_date`` — defaults to ``fields.Datetime.now()`` (which
          under ``freeze_time`` is the frozen reference datetime)
        - ``user_id`` — defaults to ``cls.env.user`` (the ``accountman``
          user with account manager permissions)
        - ``summary`` — from the ``summary`` argument

        Optional fields:

        - ``followup_level_id`` — populated only if a ``level`` is supplied
        - ``invoice_id`` (single-invoice link) and ``invoice_ids``
          (Many2many) — both populated if an ``invoice`` is supplied,
          providing both single- and bulk-context links

        Any additional keyword arguments are passed through verbatim to
        the ``create()`` call, so callers can override defaults or supply
        fields not handled explicitly here (e.g., ``promised_date``,
        ``promised_amount``, ``notes``, ``outcome``).

        :param partner: ``res.partner`` record (required).
        :param action_type: One of ``'email'``, ``'phone'``, ``'letter'``,
            ``'meeting'``, ``'promise'``, ``'status'``, ``'note'``,
            ``'sms'``. Default: ``'email'``.
        :param summary: Short description shown in list/kanban views.
        :param level: Optional ``account.followup.level`` record to link.
        :param invoice: Optional ``account.move`` record to link as the
            primary invoice; also populates the Many2many ``invoice_ids``.
        :param kwargs: Any additional ``account.followup.history`` field
            values to set at creation.

        :return: The created ``account.followup.history`` record.
        """
        vals = {
            'partner_id': partner.id,
            'action_type': action_type,
            # ``fields.Datetime.now()`` honours ``freeze_time`` if the
            # caller is inside a frozen-time context, otherwise it
            # returns the real current datetime. Either way the test
            # gets a well-defined value rather than relying on the
            # model-level default at creation time.
            'action_date': fields.Datetime.now(),
            'user_id': cls.env.user.id,
            'summary': summary,
            **kwargs,
        }
        if level:
            vals['followup_level_id'] = level.id
        if invoice:
            vals['invoice_id'] = invoice.id
            # Populating ``invoice_ids`` ensures the Many2many bulk-context
            # smart-button on the partner form, and downstream queries on
            # ``invoice_ids``, see this history record. The ``Command.set``
            # operation atomically replaces the M2M to contain exactly the
            # supplied invoice.
            vals['invoice_ids'] = [Command.set([invoice.id])]
        return cls.env['account.followup.history'].create(vals)

    # -------------------------------------------------------------------------
    # HELPER METHODS — PAYMENT REGISTRATION
    # -------------------------------------------------------------------------

    @classmethod
    def _register_payment(cls, invoice, amount, payment_date=None):
        """Register a payment on an invoice using ``account.payment.register``.

        Used by tests that exercise residual-amount behaviour (partial
        payments reduce ``amount_residual`` and may transition
        ``payment_state`` from ``'not_paid'`` → ``'partial'`` → ``'paid'``).

        Internally invokes Odoo's standard payment-registration wizard
        ``account.payment.register`` with the invoice in active context,
        populates ``amount`` / ``payment_date`` / ``journal_id``, then
        calls ``_create_payments()`` which is the wizard's primary
        action method (returns the created payment record(s)).

        :param invoice: ``account.move`` record (single posted invoice).
        :param amount: Payment amount (``float``); may be less than
            ``invoice.amount_residual`` for a partial payment.
        :param payment_date: Optional ``datetime.date`` for the payment.
            Default: ``cls.FROZEN_DATE`` so payments align with the
            deterministic test reference date.

        :return: The created ``account.payment`` recordset (one record
            per invoice processed).
        """
        # Default to the frozen reference date so payments are
        # deterministically dated relative to the test fixtures. Callers
        # who need an explicit different date may override.
        payment_date = payment_date or cls.FROZEN_DATE
        wizard = cls.env['account.payment.register'].with_context(
            active_model='account.move',
            active_ids=invoice.ids,
        ).create({
            'amount': amount,
            'payment_date': payment_date,
            # Use the bank journal from the parent fixture for
            # consistency with other receivable-payment tests.
            'journal_id': cls.company_data['default_journal_bank'].id,
        })
        # ``_create_payments()`` is the wizard's primary action method
        # (returns the created ``account.payment`` records). The
        # leading-underscore is Odoo's internal-API convention; the
        # method is stable and used widely throughout core test suites.
        return wizard._create_payments()

    # -------------------------------------------------------------------------
    # PROPERTY ACCESSORS — SEED RECORD LOOKUPS
    # -------------------------------------------------------------------------
    # Lazy property accessors that resolve the four default follow-up
    # levels and the PF-002 cron seeded by data XML. Implemented as
    # ``@property`` (instance methods) rather than ``@classmethod``
    # because subclass tests typically call them in instance context
    # (``self.first_reminder_level``) and the underlying
    # ``self.env.ref()`` lookup is inexpensive (cached after first call
    # within an env).
    #
    # External-ID format note
    # -----------------------
    # The external IDs below match the actual ``id="..."`` attributes on
    # the seeded records in ``data/followup_data.xml`` and
    # ``data/followup_cron.xml``. Each XID is qualified with the module
    # name ``account_payment_followup`` per Odoo's external-ID
    # conventions (``module_name.local_id``).
    # -------------------------------------------------------------------------

    @property
    def first_reminder_level(self):
        """Return the First Reminder level (sequence=10, delay=7).

        Resolved via Odoo's external-ID lookup. Raises
        :class:`ValueError` (with message "External ID not found") if
        ``data/followup_data.xml`` failed to load — typically a sign
        that ``data/mail_template_data.xml`` failed to load first
        (the level XML references the email templates by XID, so the
        templates must exist before the levels can be parsed).

        :return: ``account.followup.level`` record (singleton).
        """
        return self.env.ref(
            'account_payment_followup.followup_level_first_reminder',
        )

    @property
    def second_reminder_level(self):
        """Return the Second Reminder level (sequence=20, delay=14).

        :return: ``account.followup.level`` record (singleton).
        """
        return self.env.ref(
            'account_payment_followup.followup_level_second_reminder',
        )

    @property
    def warning_level(self):
        """Return the Warning level (sequence=30, delay=21).

        :return: ``account.followup.level`` record (singleton).
        """
        return self.env.ref(
            'account_payment_followup.followup_level_warning',
        )

    @property
    def final_notice_level(self):
        """Return the Final Notice level (sequence=40, delay=30).

        :return: ``account.followup.level`` record (singleton).
        """
        return self.env.ref(
            'account_payment_followup.followup_level_final_notice',
        )

    @property
    def followup_cron(self):
        """Return the PF-002 ``ir.cron`` scheduled action record.

        Used by ``test_pf_002.py`` to verify Gate 13 (cron reachability)
        — that is, the cron is registered, visible in
        Settings → Technical → Automation → Scheduled Actions, and
        manually invokable via ``method_direct_trigger()``.

        :return: ``ir.cron`` record (singleton).
        """
        return self.env.ref(
            'account_payment_followup.ir_cron_payment_followup',
        )
