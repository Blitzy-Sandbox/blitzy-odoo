# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Account Move Extensions — Payment Follow-ups
============================================

Extends Odoo's core ``account.move`` with computed overdue tracking fields
for customer invoices and adds a navigation relation to
``account.followup.history`` records that reference each invoice via the
primary invoice link.

Implements
----------
- FEATURE-006 PF-005: Overdue Calculation (invoice-level days-overdue,
  is-overdue flag, aging-bucket classification, dispute flag).
- FEATURE-006 PF-004: Action History Tracking (reverse One2many relation
  from invoice to history records — single-invoice contexts only;
  bulk-action history records use the ``invoice_ids`` Many2many on the
  history model and are intentionally not duplicated here).

Integration Notes
-----------------
- Extends ``account.move`` via ``_inherit`` (no core modifications).
- Zero Enterprise module dependencies.
- AGPL-3.0 licensing.
- Only customer invoices and refunds (``move_type in ('out_invoice',
  'out_refund')``) that are posted and not fully paid (``payment_state in
  ('not_paid', 'partial')``) are classified as overdue. Vendor bills,
  journal entries, draft invoices, paid invoices, and reversed invoices
  all default to ``days_overdue=0``, ``is_overdue=False``,
  ``aging_bucket='current'``.
- Supplier bills (``in_invoice``, ``in_refund``) are NEVER classified
  as overdue at this level; this module strictly handles customer-side
  receivables follow-up per PF-005 BR-003.

Rules Compliance (AAP §0.7)
---------------------------
- R-01: No cross-module imports (imports only from ``odoo``).
- R-02: No Enterprise references — pure Community/AGPL-3 stack.
- R-03: Uses ``_inherit`` only, no ``_name`` redefinition. The class
  declares ``_inherit = 'account.move'`` so all new fields are added
  to the existing ``account_move`` PostgreSQL table without registering
  a new model.
- R-05: All new fields are computed (``days_overdue``, ``is_overdue``,
  ``aging_bucket``) or relational (``followup_history_ids`` One2many to
  the new module model ``account.followup.history``) or net-new
  additive Boolean (``is_disputed``). No existing core, FEATURE-001, or
  FEATURE-002 field is redefined. Verified via grep against
  ``addons/account/models/account_move.py``,
  ``addons/account_financial_report_ce/`` and
  ``addons/account_bank_reconciliation_ce/`` — no field of any of these
  names exists on persistent ``account.move`` records (the only hit is
  on a TransientModel report line in ``account_financial_report_ce``,
  which is not the same model).
- R-07: No ``sudo()`` usage.
"""

from odoo import api, fields, models


class AccountMove(models.Model):
    """Customer invoice/refund extensions for payment follow-up workflows.

    Adds computed days-overdue, is-overdue, and aging-bucket classification
    to customer invoices (``out_invoice``) and credit notes (``out_refund``).
    Also adds a manually-set ``is_disputed`` flag used by PF-005 BR-005 to
    exclude disputed invoices from per-partner overdue aggregates while
    retaining them in aging reports for visibility, and a reverse
    ``followup_history_ids`` One2many relation to navigate from an invoice
    to its single-invoice follow-up history records (PF-004 Scenario 4).

    These fields are stored and indexed where appropriate to enable fast
    filtering in follow-up reports (e.g., "show all invoices in the
    31-60 bucket"). All fields are additive and compute only from existing
    core fields (``invoice_date_due``, ``payment_state``, ``state``,
    ``move_type``, ``amount_residual``); no core field is redefined per
    R-05.

    Field summary:
        - ``days_overdue``: Integer, computed, stored. Number of days past
          ``invoice_date_due``; zero for non-tracked moves.
        - ``is_overdue``: Boolean, computed, stored, indexed. True for
          posted customer invoices/refunds past their due date with
          outstanding residual.
        - ``aging_bucket``: Selection, computed, stored, indexed,
          default='current'. One of ``current`` / ``bucket_1_30`` /
          ``bucket_31_60`` / ``bucket_61_90`` / ``bucket_90_plus``.
        - ``is_disputed``: Boolean, manually set, indexed. PF-005 BR-005
          exclusion flag for disputed invoices.
        - ``followup_history_ids``: One2many to ``account.followup.history``
          via ``inverse_name='invoice_id'``. Single-invoice context only.
    """

    _inherit = 'account.move'

    # -------------------------------------------------------------------------
    # FOLLOW-UP TRACKING FIELDS (PF-005)
    # -------------------------------------------------------------------------
    # All three computed fields share the same compute method
    # ``_compute_days_overdue`` so a single iteration of the recordset
    # populates all three values. ``store=True`` is used for all three
    # so search domains (e.g., ``[('is_overdue', '=', True)]``,
    # ``[('aging_bucket', '=', 'bucket_31_60')]``) are efficient SQL
    # comparisons against the indexed column rather than per-row Python
    # recomputations.
    # -------------------------------------------------------------------------

    days_overdue = fields.Integer(
        string='Days Overdue',
        compute='_compute_days_overdue',
        store=True,
        help=(
            'Number of days past the invoice due date. Zero when the invoice '
            'is not a customer invoice/refund, is unposted, is fully paid or '
            'reversed, has no due date, or is not yet due. Used by PF-002 '
            'follow-up mail templates and PF-005 partner aging aggregation.'
        ),
    )

    is_overdue = fields.Boolean(
        string='Is Overdue',
        compute='_compute_days_overdue',
        store=True,
        index=True,
        help=(
            'True when the invoice is a posted customer invoice/refund, is '
            'not fully paid, has a due date in the past, and therefore '
            'should be considered for follow-up correspondence. Indexed for '
            'fast filtering by PF-002 cron and PF-005 partner aggregation.'
        ),
    )

    aging_bucket = fields.Selection(
        selection=[
            ('current', 'Current'),
            ('bucket_1_30', '1-30 Days'),
            ('bucket_31_60', '31-60 Days'),
            ('bucket_61_90', '61-90 Days'),
            ('bucket_90_plus', '90+ Days'),
        ],
        string='Aging Bucket',
        compute='_compute_days_overdue',
        store=True,
        index=True,
        default='current',
        help=(
            'Aging classification of the invoice based on days overdue. '
            'One of: ``current`` (not yet due or paid), ``bucket_1_30`` '
            '(1-30 days past due), ``bucket_31_60`` (31-60 days past due), '
            '``bucket_61_90`` (61-90 days past due), ``bucket_90_plus`` '
            '(more than 90 days past due). Indexed to support fast filtering '
            'in follow-up reports and dashboard aggregations. Default is '
            "'current' so newly created invoices have a valid value before "
            'the compute method runs.'
        ),
    )

    is_disputed = fields.Boolean(
        string='Is Disputed',
        default=False,
        index=True,
        copy=False,
        tracking=True,
        help=(
            'Flag set manually by accountants when the customer has formally '
            'disputed an invoice (e.g., delivery complaints, pricing '
            'disagreements, credit note pending). Disputed invoices are '
            'excluded from the per-partner overdue aggregation used by '
            'PF-005 and the PF-002 follow-up email cron, so that customers '
            'are not dunned for amounts under review. Per PF-005 BR-005. '
            'Added by account_payment_followup; does NOT exist in Odoo 19.0 '
            'core account.move (verified — additive field only, R-05 '
            'compliant).'
        ),
    )

    # -------------------------------------------------------------------------
    # RELATIONS TO FOLLOW-UP MODELS (PF-004)
    # -------------------------------------------------------------------------
    # ``followup_history_ids`` is the reverse One2many side of the Many2one
    # ``invoice_id`` field on ``account.followup.history`` (which uses
    # ``ondelete='set null'`` per PF-004 BR-004 so that history records
    # are preserved when an invoice is deleted — the FK is nulled but the
    # history row remains).
    #
    # Note on single-vs-many invoice links: ``account.followup.history``
    # has BOTH:
    #   - ``invoice_id`` (Many2one): primary invoice for single-invoice
    #     contexts (e.g., a phone call about one specific overdue bill;
    #     PF-004 Scenario 4).
    #   - ``invoice_ids`` (Many2many): multiple invoices for bulk actions
    #     (e.g., the PF-002 email cron lists all overdue invoices for a
    #     customer in one email).
    #
    # This ``followup_history_ids`` field uses ``inverse_name='invoice_id'``
    # to deliberately surface only single-invoice history records. Bulk-
    # action history records that reference an invoice solely through the
    # Many2many ``invoice_ids`` are intentionally NOT included in this
    # reverse relation — including them would cause a single bulk email
    # mentioning an invoice in a list of 20 overdue invoices to count as
    # "20 individual history records pointing to this invoice", which is
    # both confusing in the form view and incorrect per PF-004's
    # single-record-per-action semantics. Consumers needing bulk-action
    # listings should query ``account.followup.history`` directly with a
    # domain on ``invoice_ids`` (e.g.,
    # ``self.env['account.followup.history'].search([('invoice_ids', 'in', invoice.ids)])``).
    # -------------------------------------------------------------------------

    followup_history_ids = fields.One2many(
        comodel_name='account.followup.history',
        inverse_name='invoice_id',
        string='Follow-up History',
        help=(
            'Follow-up actions (emails, calls, letters, meetings, payment '
            'promises, status changes, internal notes, SMS) that specifically '
            'reference this invoice via the primary single-invoice link. '
            'Does NOT include history records that reference this invoice '
            'only through the Many2many bulk-action relation '
            '(``invoice_ids``); query ``account.followup.history`` directly '
            'for bulk listings. Records preserved when this invoice is '
            "deleted via ``ondelete='set null'`` on the inverse side per "
            'PF-004 BR-004.'
        ),
    )

    # -------------------------------------------------------------------------
    # COMPUTE METHODS
    # -------------------------------------------------------------------------

    @api.depends(
        'invoice_date_due',
        'payment_state',
        'state',
        'move_type',
        'amount_residual',
    )
    def _compute_days_overdue(self):
        """Compute days-overdue, is-overdue, and aging-bucket for invoices.

        Single compute method populating three correlated fields
        (``days_overdue``, ``is_overdue``, ``aging_bucket``) so the bucket
        classification is always consistent with the underlying day count.

        Business Rules (PF-005):
            - Only customer invoices (``out_invoice``) and credit notes
              (``out_refund``) are tracked. All other move types
              (``in_invoice``, ``in_refund``, ``entry``, ``out_receipt``,
              ``in_receipt``) default to ``days_overdue=0``,
              ``is_overdue=False``, ``aging_bucket='current'``.
            - Posted moves only (``state == 'posted'``). Draft and cancelled
              moves are not legally binding receivables (PF-005 BR-002)
              and are excluded.
            - Unpaid or partially-paid moves only (``payment_state in
              ('not_paid', 'partial')``). Fully-paid (``paid``) and
              reversed (``reversed``) moves have no outstanding balance
              and are excluded. ``in_payment`` (payment initiated but not
              cleared), ``blocked`` (manually marked), and
              ``invoicing_legacy`` (imported historical data) states are
              also excluded so the aging classification matches the
              partner-level aggregation in ``res.partner._compute_overdue_aggregates``
              for cross-model consistency.
            - Missing ``invoice_date_due`` resolves to ``'current'`` with
              ``days_overdue=0`` (defensive fallback; core Odoo computes
              ``invoice_date_due`` from payment terms so this branch is
              rarely reached for normal invoices).
            - Future-due invoices (``invoice_date_due > today``) are
              ``'current'`` with ``days_overdue=0``.
            - Invoices due exactly today (``invoice_date_due == today``)
              are NOT yet overdue (``delta == 0`` check), aligning with
              standard finance convention that the due date is the last
              day on which payment is timely.

        Bucket Thresholds (matching PF-005 Scenario 3):
            - ``current``: not yet due (delta <= 0) or non-tracked move.
            - ``bucket_1_30``: 1-30 days past due (1 <= delta <= 30).
            - ``bucket_31_60``: 31-60 days past due (31 <= delta <= 60).
            - ``bucket_61_90``: 61-90 days past due (61 <= delta <= 90).
            - ``bucket_90_plus``: more than 90 days past due (delta > 90).

        Dependency Notes (``@api.depends`` chain):
            - ``invoice_date_due`` — primary input; recompute when due date
              changes (PF-005 Scenario 6: invoice modified).
            - ``payment_state`` — recompute when payment state transitions
              (e.g., ``not_paid`` -> ``partial`` -> ``paid``) on payment
              registration (PF-005 Scenario 6: payment recorded).
            - ``state`` — recompute when move is posted or cancelled;
              draft/cancelled moves must reset to ``'current'``.
            - ``move_type`` — recompute on type changes during manual
              corrections (rare but supported).
            - ``amount_residual`` — included so that partial-payment-driven
              residual updates also force recomputation. The bucket
              classification itself is time-based (not amount-based), but
              including ``amount_residual`` in the dependency chain ensures
              the compute fires whenever a payment changes the residual,
              even if ``payment_state`` is briefly stale during
              transactional updates. This protects against edge cases
              where a payment marks the move as partial before
              ``payment_state`` is recomputed.
        """
        today = fields.Date.context_today(self)
        for move in self:
            # Default to not-overdue / current bucket. Applied first so that
            # every early ``continue`` below leaves the move in a fully
            # deterministic, cleared state — no field can carry over a stale
            # value from a previous compute pass.
            move.days_overdue = 0
            move.is_overdue = False
            move.aging_bucket = 'current'

            # Only customer invoices and refunds are candidates for follow-up.
            # Vendor bills, journal entries, and receipts are not in scope
            # for the customer payment follow-up workflow per PF-005 BR-003
            # (this module strictly handles customer-side receivables).
            if move.move_type not in ('out_invoice', 'out_refund'):
                continue

            # Only posted (legally binding) moves are evaluated. Draft moves
            # may be edited/cancelled; cancelled moves have no receivable
            # impact. PF-005 BR-002.
            if move.state != 'posted':
                continue

            # Only unpaid or partially-paid moves can be overdue. The
            # `not_paid` state covers fresh invoices with no payment;
            # `partial` covers invoices with payments that don't fully
            # settle the residual. All other states (`paid`, `reversed`,
            # `in_payment`, `blocked`, `invoicing_legacy`) are excluded
            # for consistency with the partner-level aggregation in
            # res.partner._compute_overdue_aggregates.
            if move.payment_state not in ('not_paid', 'partial'):
                continue

            # Cannot classify aging without a due date. Missing
            # invoice_date_due is a defensive fallback; core Odoo computes
            # it from payment terms so this branch is rarely hit for
            # well-formed invoices, but handling it gracefully prevents
            # exceptions on corrupted or partially-entered data.
            if not move.invoice_date_due:
                continue

            # Compute days past due. Negative or zero deltas indicate
            # the invoice is not yet overdue (due in the future or due
            # exactly today). Standard finance convention: the due date
            # is the last timely day; an invoice due today is not yet
            # overdue, becoming overdue on the following calendar day.
            delta = (today - move.invoice_date_due).days
            if delta <= 0:
                # Not yet due (future or exactly today). Stay in 'current'.
                continue

            # Past due: populate days_overdue and is_overdue, then bucket.
            # Bucket classification uses inclusive upper bounds matching
            # PF-005 Scenario 3 thresholds (1-30, 31-60, 61-90, 90+).
            move.days_overdue = delta
            move.is_overdue = True
            if delta <= 30:
                move.aging_bucket = 'bucket_1_30'
            elif delta <= 60:
                move.aging_bucket = 'bucket_31_60'
            elif delta <= 90:
                move.aging_bucket = 'bucket_61_90'
            else:
                move.aging_bucket = 'bucket_90_plus'
