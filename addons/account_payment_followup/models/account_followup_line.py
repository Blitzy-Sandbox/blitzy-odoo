# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Account Follow-up Line — PF-005 Per-Partner Aggregate Snapshot
==============================================================

Denormalised per-partner aggregate snapshot backing the partner aging
summary, follow-up dashboard, and PF-003 report generation. Each
``account.followup.line`` record materialises a single partner's
overdue state (aging buckets, total overdue, applicable level, last
and next action dates, computed status) at a point in time, so that
batch-scale queries (thousands of partners x millions of invoices)
do not require per-record iteration of ``res.partner`` computed
fields.

One row per (``partner_id``, ``company_id``) pair; the model is
materialised lazily via the class-method helpers
``_get_or_create_for_partner`` and ``_refresh_from_partner``, and
refreshed in bulk by ``_cron_refresh_all`` (registered as a scheduled
action in subsequent checkpoints, or invoked manually by the
follow-up cron before email dispatch).

Implements:
    - FEATURE-006 PF-005: Per-partner overdue aggregate snapshot with
      aging buckets (Current/1-30/31-60/61-90/90+), total overdue,
      max days overdue, applicable follow-up level, computed status
      (``no_action_needed``, ``in_followup``, ``no_response``,
      ``done``, ``need_review``).

Integration Notes:
    - Referenced by ``security/ir.model.access.csv`` (rows 4-5) and
      ``security/followup_security.xml`` (``ir.rule`` at lines
      32-42). The model's ``_name`` auto-generates the XML ID
      ``model_account_followup_line`` that those security artifacts
      depend on.
    - Does NOT duplicate ``res.partner``'s computed fields — instead,
      it reads them from the partner and stores a point-in-time
      snapshot.
    - Enforces ``UNIQUE(partner_id, company_id)`` at the SQL level so
      that a partner has at most one snapshot per company.

Rules Compliance (AAP §0.7):
    - R-01: No cross-module imports.
    - R-02: No Enterprise references.
    - R-03: Uses ``_name`` for a net-new model (not extending an
      existing one).
    - R-07: No ``sudo()`` usage.
"""

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountFollowupLine(models.Model):
    """Per-partner overdue aggregate snapshot.

    Materialises the partner's overdue state for fast search,
    reporting, and dashboard rendering. Populated and refreshed via
    ``_refresh_from_partner``; a partner's row is uniquely keyed on
    (``partner_id``, ``company_id``).
    """

    _name = 'account.followup.line'
    _description = 'Account Follow-up Line (Per-Partner Aggregate Snapshot)'
    _order = 'max_days_overdue desc, total_overdue desc, partner_id'
    _rec_name = 'partner_id'

    # -------------------------------------------------------------------------
    # KEY FIELDS
    # -------------------------------------------------------------------------

    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Partner',
        required=True,
        ondelete='cascade',
        index=True,
        help=(
            'Customer partner this follow-up aggregate pertains to. '
            'Deletion of the partner cascades to their aggregate rows.'
        ),
    )

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        index=True,
        help=(
            'Company scope for this aggregate. A partner operating in '
            'multiple companies has one aggregate row per company so '
            'that multi-company ir.rule isolation works correctly.'
        ),
    )

    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency',
        related='company_id.currency_id',
        store=True,
        readonly=True,
        help=(
            'Currency for monetary aggregates, derived from the '
            'company.'
        ),
    )

    # -------------------------------------------------------------------------
    # AGGREGATE SNAPSHOT FIELDS
    # -------------------------------------------------------------------------

    total_overdue = fields.Monetary(
        string='Total Overdue',
        currency_field='currency_id',
        default=0.0,
        help=(
            'Snapshot of the partner\'s total overdue amount at the time '
            'of the last refresh. Mirrors '
            '``res.partner.total_overdue`` at snapshot time.'
        ),
    )

    max_days_overdue = fields.Integer(
        string='Max Days Overdue',
        default=0,
        index=True,
        help=(
            'Maximum days overdue across the partner\'s open customer '
            'invoices at snapshot time. Indexed to support fast sorting '
            'in dashboards.'
        ),
    )

    aging_bucket_current = fields.Monetary(
        string='Current (Not Due)',
        currency_field='currency_id',
        default=0.0,
    )

    aging_bucket_1_30 = fields.Monetary(
        string='1-30 Days Overdue',
        currency_field='currency_id',
        default=0.0,
    )

    aging_bucket_31_60 = fields.Monetary(
        string='31-60 Days Overdue',
        currency_field='currency_id',
        default=0.0,
    )

    aging_bucket_61_90 = fields.Monetary(
        string='61-90 Days Overdue',
        currency_field='currency_id',
        default=0.0,
    )

    aging_bucket_90_plus = fields.Monetary(
        string='90+ Days Overdue',
        currency_field='currency_id',
        default=0.0,
    )

    # -------------------------------------------------------------------------
    # FOLLOW-UP METADATA
    # -------------------------------------------------------------------------

    followup_level_id = fields.Many2one(
        comodel_name='account.followup.level',
        string='Current Level',
        index=True,
        help=(
            'Applicable follow-up level at snapshot time (mirrors '
            '``res.partner.followup_level_id`` but stored locally for '
            'dashboard efficiency).'
        ),
    )

    followup_status = fields.Selection(
        selection=[
            ('no_action_needed', 'No Action Needed'),
            ('in_followup', 'In Follow-up'),
            ('no_response', 'No Response'),
            ('done', 'Done'),
            ('need_review', 'Needs Review'),
        ],
        string='Follow-up Status',
        default='no_action_needed',
        index=True,
        help=(
            'Computed snapshot status:\n'
            ' * No Action Needed: No overdue invoices.\n'
            ' * In Follow-up: Currently being dunned at an assigned '
            'level.\n'
            ' * No Response: No partner response despite repeated '
            'contact; aging 60+ days without a matching level.\n'
            ' * Done: Previously overdue, now resolved.\n'
            ' * Needs Review: Requires manual accountant review '
            '(90+ days aging, disputed, or edge case).'
        ),
    )

    last_action_date = fields.Date(
        string='Last Action Date',
        help=(
            'Date of the most recent follow-up action recorded in '
            '``account.followup.history`` for this partner.'
        ),
    )

    next_action_date = fields.Date(
        string='Next Action Date',
        index=True,
        help=(
            'Next scheduled follow-up action date (mirrors '
            '``res.partner.followup_next_action_date``).'
        ),
    )

    last_refreshed = fields.Datetime(
        string='Last Refreshed',
        default=fields.Datetime.now,
        help='Timestamp of the last aggregate refresh.',
    )

    # -------------------------------------------------------------------------
    # SQL CONSTRAINTS
    # -------------------------------------------------------------------------
    # Odoo 19 migrated from class-level ``_sql_constraints`` list to the
    # new ``models.Constraint(...)`` declarative attribute. The attribute
    # name becomes the constraint identifier suffix (e.g.
    # ``account_followup_line_unique_partner_company``).

    _unique_partner_company = models.Constraint(
        'UNIQUE(partner_id, company_id)',
        'A follow-up line must be unique per partner and company.',
    )

    # -------------------------------------------------------------------------
    # DISPLAY HELPERS
    # -------------------------------------------------------------------------

    def name_get(self):
        """Display as 'Partner (Company) - Status'."""
        result = []
        for rec in self:
            partner_name = (
                rec.partner_id.display_name or rec.partner_id.name or _('Unknown')
            )
            company_name = rec.company_id.name or ''
            status_label = dict(
                self._fields['followup_status'].selection,
            ).get(rec.followup_status, rec.followup_status or '')
            name = _('%(partner)s (%(company)s) - %(status)s') % {
                'partner': partner_name,
                'company': company_name,
                'status': status_label,
            }
            result.append((rec.id, name))
        return result

    # -------------------------------------------------------------------------
    # CLASSMETHODS — AGGREGATE MATERIALISATION
    # -------------------------------------------------------------------------

    @api.model
    def _get_or_create_for_partner(self, partner, company=None):
        """Return (creating if necessary) the follow-up line for a partner.

        Enforces the ``UNIQUE(partner_id, company_id)`` invariant by
        performing a lookup-before-create, so callers can safely use
        this helper in loops without risking duplicate-row errors.

        :param partner: ``res.partner`` record (must be a single
            partner).
        :param company: Optional ``res.company`` record. If not
            provided, uses ``partner.company_id`` or, as fallback,
            ``self.env.company``.
        :return: Single ``account.followup.line`` record.
        """
        if not partner:
            raise UserError(
                _('Cannot create a follow-up line without a partner.'),
            )
        if len(partner) != 1:
            raise UserError(
                _('Follow-up line lookup requires exactly one partner.'),
            )

        resolved_company = (
            company
            or partner.company_id
            or self.env.company
        )

        line = self.search(
            [
                ('partner_id', '=', partner.id),
                ('company_id', '=', resolved_company.id),
            ],
            limit=1,
        )
        if not line:
            line = self.create({
                'partner_id': partner.id,
                'company_id': resolved_company.id,
            })
        return line

    @api.model
    def _refresh_from_partner(self, partner, company=None):
        """Refresh the follow-up line snapshot from the partner's live state.

        Reads the partner's computed fields (``total_overdue``,
        ``max_days_overdue``, aging buckets, ``followup_level_id``,
        ``followup_status``, ``followup_next_action_date``) and
        persists them to the line snapshot. Also records the last
        refresh timestamp and derives ``last_action_date`` from the
        most recent ``account.followup.history`` entry for the partner.

        :param partner: ``res.partner`` record (must be a single
            partner).
        :param company: Optional ``res.company`` record.
        :return: Refreshed ``account.followup.line`` record.
        """
        line = self._get_or_create_for_partner(partner, company=company)

        # Look up most recent history entry for last_action_date.
        history = self.env['account.followup.history'].search(
            [('partner_id', '=', partner.id)],
            order='action_date desc',
            limit=1,
        )
        last_action = history.action_date if history else False
        last_action_date = (
            fields.Date.to_date(last_action)
            if last_action
            else False
        )

        line.write({
            'total_overdue': partner.total_overdue or 0.0,
            'max_days_overdue': partner.max_days_overdue or 0,
            'aging_bucket_current': partner.aging_bucket_current or 0.0,
            'aging_bucket_1_30': partner.aging_bucket_1_30 or 0.0,
            'aging_bucket_31_60': partner.aging_bucket_31_60 or 0.0,
            'aging_bucket_61_90': partner.aging_bucket_61_90 or 0.0,
            'aging_bucket_90_plus': partner.aging_bucket_90_plus or 0.0,
            'followup_level_id': (
                partner.followup_level_id.id
                if partner.followup_level_id
                else False
            ),
            'followup_status': (
                partner.followup_status or 'no_action_needed'
            ),
            'next_action_date': partner.followup_next_action_date or False,
            'last_action_date': last_action_date,
            'last_refreshed': fields.Datetime.now(),
        })
        return line

    @api.model
    def _cron_refresh_all(self):
        """Batch-refresh all partner aggregates across the active company set.

        Invoked by the follow-up cron (or a dedicated refresh cron
        added in a subsequent checkpoint) to keep dashboard and
        reporting aggregates current. Iterates partners that have at
        least one posted customer invoice, delegating to
        ``_refresh_from_partner`` for each.

        Performance notes:
            - Processes partners in chunks of 500 to bound memory
              usage.
            - Logs progress via ``_logger.info`` so operators can
              track long-running refreshes in server logs.
            - Each partner is handled in its own try/except so that
              a failure on one partner does not abort the batch (PF-002
              BR-005 fault-tolerance pattern, applied analogously
              here).

        :return: Total number of partners successfully refreshed.
        """
        Partner = self.env['res.partner']
        batch_size = 500

        domain = [
            ('invoice_ids.move_type', 'in', ('out_invoice', 'out_refund')),
            ('invoice_ids.state', '=', 'posted'),
        ]
        # Deduplicate via ids since partners might have multiple invoices.
        partner_ids = Partner.search(domain).ids
        total = len(partner_ids)
        refreshed = 0
        _logger.info(
            'Follow-up aggregate refresh: %s partners to process.', total,
        )

        for offset in range(0, total, batch_size):
            chunk_ids = partner_ids[offset:offset + batch_size]
            partners = Partner.browse(chunk_ids)
            for partner in partners:
                try:
                    self._refresh_from_partner(partner)
                    refreshed += 1
                except Exception:
                    _logger.exception(
                        'Follow-up aggregate refresh failed for partner '
                        'id=%s; skipping and continuing.',
                        partner.id,
                    )
            # Flush the batch to the database to release ORM cache.
            self.env.cr.commit()  # noqa: E501 - intentional commit per batch to avoid OOM on large datasets
            _logger.info(
                'Follow-up aggregate refresh progress: %s / %s.',
                min(offset + batch_size, total),
                total,
            )

        _logger.info(
            'Follow-up aggregate refresh complete: %s / %s partners '
            'refreshed.',
            refreshed,
            total,
        )
        return refreshed
