# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Account Move Line Extensions — Payment Follow-ups

Extends Odoo's core ``account.move.line`` with computed aging fields for
customer receivable lines. Used for fine-grained aging analysis when a
single invoice has multiple due-date lines (e.g., payment terms splitting
an invoice into 30/60/90-day tranches).

Implements:
    - FEATURE-006 PF-005: Overdue Calculation (receivable-line days-overdue,
      aging bucket)

Integration Notes:
    - Extends ``account.move.line`` via ``_inherit`` (no core modifications).
    - Zero Enterprise module dependencies.
    - AGPL-3.0 licensing.
    - Only receivable lines (``account_type == 'asset_receivable'``) that are
      unreconciled and on posted moves are tracked. All other lines default
      to ``days_overdue=0`` and ``aging_bucket='current'``.
    - Fields are stored and indexed to support fast aggregation in partner
      aging summaries and follow-up report generation. Line-level granularity
      (distinct from the move-level classification on ``account.move``)
      enables per-installment aging when payment terms split a single
      invoice into multiple receivable lines with different maturity dates.

Rules Compliance (AAP §0.7):
    - R-01: No cross-module imports (imports only from ``odoo``).
    - R-02: No Enterprise references.
    - R-03: Uses ``_inherit`` only, no ``_name``.
    - R-05: All new fields are computed; no core field redefinition.
    - R-07: No ``sudo()`` usage.
"""

from odoo import api, fields, models


class AccountMoveLine(models.Model):
    """Customer receivable-line extensions for payment follow-up workflows.

    Adds computed days-overdue and aging-bucket classification to receivable
    lines (``account_type == 'asset_receivable'``). The ``aging_bucket``
    Selection is indexed to enable fast aggregation in follow-up reports
    and the partner-level aging compute.

    The line-level classification is distinct from the move-level
    classification (on ``account.move``) because payment terms can split a
    single invoice into multiple receivable lines with different maturity
    dates. A 2/10 net 30 payment term, for example, generates two
    receivable lines with different ``date_maturity`` values; each is
    classified independently.
    """

    _inherit = 'account.move.line'

    # -------------------------------------------------------------------------
    # FOLLOW-UP TRACKING FIELDS (PF-005)
    # -------------------------------------------------------------------------

    days_overdue = fields.Integer(
        string='Days Overdue',
        compute='_compute_line_days_overdue',
        store=True,
        help=(
            'Number of days past the line maturity date. Zero if the line is '
            'not a receivable, is reconciled (paid), is on an unposted move, '
            'or has no maturity date set.'
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
        compute='_compute_line_days_overdue',
        store=True,
        index=True,
        default='current',
        help=(
            'Aging classification of this receivable line based on days '
            'overdue. Indexed to support fast grouping in partner aging '
            'summaries and follow-up report generation.'
        ),
    )

    # -------------------------------------------------------------------------
    # COMPUTE METHODS
    # -------------------------------------------------------------------------

    @api.depends(
        'date_maturity',
        'reconciled',
        'parent_state',
        'account_id.account_type',
        'amount_residual',
    )
    def _compute_line_days_overdue(self):
        """Compute days overdue and aging bucket for receivable lines.

        Business Rules (PF-005):
            - Only receivable lines (``account_type == 'asset_receivable'``)
              are classified; all other account types get
              ``days_overdue=0`` / ``aging_bucket='current'``.
            - Reconciled (paid/cleared) lines are not overdue.
            - Lines on unposted moves (draft/cancel) are not overdue.
            - Missing ``date_maturity`` defaults to ``'current'`` (no
              overdue math).
            - Future maturity (``date_maturity > today``) resolves to
              ``'current'`` with ``days_overdue=0`` (inclusive: a line due
              exactly today is considered not yet overdue).

        Bucket thresholds (matching PF-005 Scenario 3):
            - ``current``: not yet due (delta <= 0)
            - ``bucket_1_30``: 1-30 days past due
            - ``bucket_31_60``: 31-60 days past due
            - ``bucket_61_90``: 61-90 days past due
            - ``bucket_90_plus``: more than 90 days past due

        Dependency notes:
            - ``amount_residual`` is included in ``@api.depends`` to ensure
              recomputation when partial payments change the residual
              (payments may mark a line as reconciled, updating classification).
              It is not read directly in the method body because
              classification is based on time, not amount.
            - ``account_id.account_type`` uses the dotted path so that, in
              the rare case an account's type is changed (e.g., during a
              chart-of-accounts migration), dependent lines recompute.
            - ``parent_state`` is a stored related field on
              ``account.move.line`` (``related='move_id.state', store=True``);
              depending on it triggers recomputation when the move posts or
              cancels, without forcing a JOIN at recompute time.
        """
        today = fields.Date.context_today(self)
        for line in self:
            # Default to not-overdue (applied first so every early continue
            # leaves the line in a deterministic state).
            line.days_overdue = 0
            line.aging_bucket = 'current'

            # Short-circuit: only receivable lines on posted moves with
            # unreconciled residual and a set maturity date are evaluated.
            if not line.account_id or line.account_id.account_type != 'asset_receivable':
                continue
            if line.reconciled:
                continue
            if line.parent_state != 'posted':
                continue
            if not line.date_maturity:
                continue

            delta = (today - line.date_maturity).days
            if delta <= 0:
                # Not yet due (future or exactly today).
                continue

            line.days_overdue = delta
            if delta <= 30:
                line.aging_bucket = 'bucket_1_30'
            elif delta <= 60:
                line.aging_bucket = 'bucket_31_60'
            elif delta <= 90:
                line.aging_bucket = 'bucket_61_90'
            else:
                line.aging_bucket = 'bucket_90_plus'
