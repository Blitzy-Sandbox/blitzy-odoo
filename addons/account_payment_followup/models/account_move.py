# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Account Move Extensions — Payment Follow-ups
============================================

Extends Odoo's core ``account.move`` with computed overdue classification
at the invoice level. The move-level (invoice-level) classification
complements the line-level classification added by
``account_move_line.py`` so that reports and mail templates can render
invoice-scoped information (e.g., ``inv.days_overdue`` inside a mail
template iterating overdue invoices) without needing to traverse
``line_ids``.

Implements:
    - FEATURE-006 PF-005: Overdue Calculation (invoice-level days-overdue,
      is-overdue flag, dispute flag)
    - Support for mail templates in ``data/mail_template_data.xml`` which
      render ``inv.days_overdue`` on line 82/143/201/262.

Integration Notes:
    - Extends ``account.move`` via ``_inherit`` (no core modifications).
    - Zero Enterprise module dependencies.
    - AGPL-3.0 licensing.
    - Only customer invoices and refunds (``move_type in
      ('out_invoice', 'out_refund')``) that are posted and unpaid
      (``payment_state in ('not_paid', 'partial')``) are classified as
      overdue.
    - Supplier bills (``in_invoice``, ``in_refund``) are NEVER classified
      as overdue at this level; this module strictly handles customer-side
      receivables follow-up per PF-005 BR-003.

Rules Compliance (AAP §0.7):
    - R-01: No cross-module imports (imports only from ``odoo``).
    - R-02: No Enterprise references.
    - R-03: Uses ``_inherit`` only, no ``_name`` redefinition.
    - R-05: All new fields are computed (``days_overdue``) or simple
      additive Boolean (``is_overdue`` computed, ``is_disputed``
      additive user-set flag). No existing core field is redefined.
      ``is_disputed`` is NET-NEW to the Odoo 19.0 core ``account.move``
      model (verified via ``addons/account/models/account_move.py`` —
      no core field of that name exists), justifying its addition as
      a plain ``fields.Boolean`` rather than a computed field.
    - R-07: No ``sudo()`` usage.
"""

from odoo import api, fields, models


class AccountMove(models.Model):
    """Customer invoice/refund extensions for payment follow-up workflows.

    Adds computed ``days_overdue`` (Integer) and ``is_overdue`` (Boolean)
    fields at the invoice level, plus a user-settable ``is_disputed``
    flag used by PF-005 BR-005 to exclude disputed invoices from
    overdue aggregates on ``res.partner``.

    Business Rules (PF-005):
        - Non-customer invoices (``move_type not in ('out_invoice',
          'out_refund')``) are treated as not-overdue (``days_overdue=0``,
          ``is_overdue=False``).
        - Unposted moves (``state != 'posted'``) are not overdue.
        - Fully-paid moves (``payment_state == 'paid'``) are not overdue.
        - Reversed moves (``payment_state == 'reversed'``) are not overdue.
        - Moves without ``invoice_date_due`` are not overdue (defensive
          fallback; core Odoo computes ``invoice_date_due`` from payment
          terms so this branch is rarely hit).
        - Moves due in the future (``invoice_date_due > today``) are not
          overdue (``days_overdue=0``).
        - Moves due today (``invoice_date_due == today``) are NOT overdue
          (inclusive of the due date grace period).
        - Disputed moves (``is_disputed=True``) are still classified as
          overdue at this model level; the exclusion from partner
          aggregates is performed in ``res.partner._get_overdue_invoices()``
          so that users viewing the invoice list still see accurate
          aging information.
    """

    _inherit = 'account.move'

    # -------------------------------------------------------------------------
    # FOLLOW-UP TRACKING FIELDS (PF-005)
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

    is_disputed = fields.Boolean(
        string='Is Disputed',
        default=False,
        index=True,
        copy=False,
        tracking=True,
        help=(
            'Flag set manually by accountants when the customer has formally '
            "disputed an invoice (e.g., delivery complaints, pricing "
            'disagreements, credit note pending). Disputed invoices are '
            'excluded from the per-partner overdue aggregation used by '
            'PF-005 and the PF-002 follow-up email cron, so that customers '
            'are not dunned for amounts under review. Per PF-005 BR-005. '
            'Added by account_payment_followup; does NOT exist in Odoo 19.0 '
            'core account.move (verified).'
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
        """Compute invoice-level days-overdue and is-overdue flag.

        Business Rules (PF-005 invoice-level):
            - Customer invoices/refunds only (``move_type`` in
              ``('out_invoice', 'out_refund')``).
            - Posted moves only (``state == 'posted'``).
            - Unpaid / partially paid moves only (``payment_state`` in
              ``('not_paid', 'partial')``).
            - Requires ``invoice_date_due``; defaults to zero otherwise.
            - Exactly-today due dates resolve to zero overdue (grace).

        Dependency notes:
            - ``amount_residual`` is included so the computation is
              re-evaluated when partial payments reduce the residual
              (because partial payments may flip ``payment_state`` from
              ``not_paid`` to ``partial`` or ``paid``).
            - ``state`` ensures recomputation when moves are posted or
              cancelled; unposted moves must never appear in aging.
            - ``move_type`` is static after creation for customer
              invoices/refunds, but including it here future-proofs the
              computation against type changes during manual corrections.
        """
        today = fields.Date.context_today(self)
        for move in self:
            # Default to not-overdue (applied first so every early continue
            # leaves the move in a deterministic state).
            move.days_overdue = 0
            move.is_overdue = False

            # Only customer invoices and refunds are candidates.
            if move.move_type not in ('out_invoice', 'out_refund'):
                continue
            # Posted moves only.
            if move.state != 'posted':
                continue
            # Unpaid or partially-paid moves only.
            if move.payment_state not in ('not_paid', 'partial'):
                continue
            # Requires a due date to classify.
            if not move.invoice_date_due:
                continue

            delta = (today - move.invoice_date_due).days
            if delta <= 0:
                # Not yet due (future or exactly today).
                continue

            move.days_overdue = delta
            move.is_overdue = True
