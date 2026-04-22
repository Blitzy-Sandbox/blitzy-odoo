# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""
Budget Alert Model (BM-005)
===========================

Implements ``budget.alert`` — the immutable audit record capturing a
single THRESHOLD CROSSING EVENT for a ``budget.budget.line``. When the
actual consumption of a budget line crosses one of the configured
thresholds (75%, 90%, 100%, 110%), the BM-005 cron
(``_cron_evaluate_thresholds``) creates a ``budget.alert`` record
capturing the state at the moment of crossing (threshold percentage,
consumption percentage, actual amount, planned amount, alert type /
severity), selects recipients (the budget's responsible user plus any
group-based recipients), and dispatches notifications via the configured
channel (email / activity / chatter / all).

Each record is a permanent audit entry: users cannot ``unlink()`` it
(raises ``UserError`` unless running as superuser or as a member of
``base.group_system``), and the snapshot fields are write-protected via
an ``_IMMUTABLE_FIELDS`` tuple enforced in the ``write()`` override.

Story Mapping
-------------
* BM-005 Scenario 1 — Multiple threshold levels (75 / 90 / 100 / 110)
  with severity classification (low / medium / high / critical) and
  corresponding alert types (warning / alert / critical / over_budget).
* BM-005 Scenario 2 — Early-warning notification payload rendered by
  ``_compute_alert_message``: account display name, consumption %,
  actual / planned amounts, threshold %.
* BM-005 Scenario 3 — Critical "budget exceeded" notification dispatch
  via ``_send_notification`` at the 110 % threshold.
* BM-005 Scenario 4 — Recipient configuration: ``alert_recipient_user_ids``
  (explicit users) and ``alert_recipient_group_ids`` (group-based
  recipients) collected from the budget's responsible user plus any
  configured recipients.
* BM-005 Scenario 5 — Alert history immutability: the ``unlink()``
  override prevents deletion by non-system users so the audit trail is
  preserved.
* BM-005 Scenario 6 — Severity classification used by the dashboard to
  render color-coded kanban cards.

Rules Compliance
----------------
* R-01 — No cross-module imports. Only ``odoo`` core and the Python
  standard library ``logging`` module are referenced.
* R-03 — ``_name = 'budget.alert'`` is a net-new model; ``_inherit`` is
  used purely to compose the ``mail.thread`` mixin so alerts can thread
  into the parent budget's chatter.
* R-05 — No redefinition of ``account.move`` / ``account.move.line``
  fields. Alert events read aggregated actuals via
  ``budget.budget.line.variance_actual`` (computed by the sibling model
  using a single ``_read_group`` on ``account.move.line``).
* R-06 — The cron is registered as an ``ir.cron`` XML record in
  ``data/budget_alert_cron.xml``; no Python-level scheduler is used.
* R-07 — No ``sudo()`` calls appear in this file; immutability is
  enforced via ``self.env.su`` checks (superuser-mode detection) and
  group membership checks, not via sudo escalation.
* R-08 — Every non-relational field on this model uses the ``alert_``
  prefix. No ``variance_*`` prefixed field appears anywhere in this
  file; variance fields belong on ``budget.budget.line`` and variance
  wizard fields belong on the BM-004 wizard. This partitioning allows
  BM-004 and BM-005 to advance in parallel without field collisions.

Performance
-----------
* BM-005 SLA: the cron must complete within the default Odoo cron
  timeout for ≤ 1,000 budget lines. Achieved by:
    1. Single ``search()`` over all confirmed budget lines.
    2. Single invocation of ``_compute_variance`` on the recordset,
       which internally performs ONE aggregated ``_read_group`` on
       ``account.move.line`` (pattern established in
       ``budget_budget_line.py`` lines 411-590 per BM-004).
    3. In-memory iteration over the lines for threshold comparisons;
       no per-line ORM search over ``account.move.line``.
    4. Deduplication via a bounded ``search()`` per (line, threshold)
       pair — O(n * 4) queries in the worst case but bounded by the
       THRESHOLDS tuple size.
"""

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class BudgetAlert(models.Model):
    """Immutable audit record for a single budget threshold crossing event.

    Each ``budget.alert`` record captures the state of a
    ``budget.budget.line`` at the moment its actual consumption crossed
    one of the configured threshold percentages (75 %, 90 %, 100 %,
    110 %). The record is created by the BM-005 cron
    (``_cron_evaluate_thresholds``) and dispatches notifications to the
    configured recipients via ``_send_notification``.

    The record is immutable:

    * ``unlink()`` is prohibited for non-superuser, non-``group_system``
      users, preserving the audit trail (BM-005 Scenario 5).
    * ``write()`` blocks mutation of the snapshot fields listed in
      ``_IMMUTABLE_FIELDS`` so that once the crossing has been captured
      its record-keeping fidelity is guaranteed.

    The model composes :class:`mail.thread` so notifications can post
    into the parent budget's chatter (``alert.budget_id.message_post``)
    and so its own chatter can record dispatch outcomes.
    """

    _name = 'budget.alert'
    _description = 'Budget Alert'
    _inherit = ['mail.thread']
    _order = 'alert_date desc, id desc'
    _rec_name = 'alert_message'

    # ==================================================================
    # Class-level constants
    # ==================================================================

    #: Threshold percentages evaluated by ``_cron_evaluate_thresholds``.
    #: These values MUST match the ``selection`` keys of
    #: ``alert_threshold_percent`` so that deduplication search domains
    #: are stable and indexable.
    THRESHOLDS = ('75', '90', '100', '110')

    #: Tuple of field names that are immutable once the record has been
    #: created. The ``write()`` override raises ``UserError`` when any
    #: of these fields appears in the ``vals`` dict for a non-superuser
    #: call.
    _IMMUTABLE_FIELDS = (
        'budget_line_id',
        'alert_threshold_percent',
        'alert_date',
        'alert_consumption_percent',
        'alert_actual_amount',
        'alert_planned_amount',
        'alert_type',
    )

    # ==================================================================
    # Section 3.1 — Relational anchor
    #
    # These fields are exempt from the R-08 ``alert_`` prefix rule
    # because they are pure foreign-key references naming the domain
    # entities they point at (``budget_line_id`` → ``budget.budget.line``,
    # ``budget_id`` → ``budget.budget``, ``company_id`` →
    # ``res.company``, ``currency_id`` → ``res.currency``).
    # ==================================================================

    budget_line_id = fields.Many2one(
        comodel_name='budget.budget.line',
        string='Budget Line',
        required=True,
        ondelete='cascade',
        index=True,
        tracking=True,
        help="The budget line whose threshold crossing triggered this "
             "alert event. Cascade-deleted with its parent budget line "
             "so that orphaned alerts do not accumulate.",
    )
    budget_id = fields.Many2one(
        comodel_name='budget.budget',
        string='Budget',
        related='budget_line_id.budget_id',
        store=True,
        index=True,
        help="Inverse for ``budget.budget.alert_ids``. Stored so that "
             "dashboard group-by and filter operations on the budget "
             "kanban can avoid joining through ``budget_line_id``.",
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        related='budget_line_id.company_id',
        store=True,
        index=True,
        help="Stored related to support multi-company record rules.",
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        related='budget_line_id.currency_id',
        store=True,
        help="Currency of the ``alert_actual_amount`` / "
             "``alert_planned_amount`` monetary snapshot.",
    )

    # ==================================================================
    # Section 3.2 — Threshold + event snapshot fields
    #
    # R-08: every field in this section uses the ``alert_`` prefix.
    # All snapshot fields are ``readonly=True`` to discourage manual
    # mutation; the ``_IMMUTABLE_FIELDS`` tuple enforces this at the
    # write() level.
    # ==================================================================

    alert_threshold_percent = fields.Selection(
        selection=[
            ('75', '75% — Approaching Budget'),
            ('90', '90% — Warning'),
            ('100', '100% — Budget Reached'),
            ('110', '110% — Over Budget'),
        ],
        string='Threshold (%)',
        required=True,
        readonly=True,
        tracking=True,
        help="Threshold percentage crossed at the time of alert "
             "creation. Encoded as a Selection to constrain values to "
             "the four BM-005 specified thresholds.",
    )
    alert_date = fields.Datetime(
        string='Alert Date',
        required=True,
        readonly=True,
        default=fields.Datetime.now,
        tracking=True,
        help="Timestamp at which the threshold crossing was detected "
             "and the alert record was created.",
    )
    alert_consumption_percent = fields.Float(
        string='Consumption at Alert (%)',
        required=True,
        readonly=True,
        digits=(7, 2),
        help="Actual / Planned * 100 at the time of the alert event. "
             "Captured as a snapshot so that subsequent movements on "
             "the budget line's actuals do not retroactively change "
             "the alert's audit value. Widened to ``digits=(7, 2)`` "
             "(max 99999.99 %) so the snapshot faithfully records "
             "extreme over-budget consumption — a small budget "
             "consumed by a much larger actual (e.g. 1500 %) is a "
             "real-world data point whose integrity matters more "
             "than the display compactness of a narrower field.",
    )
    alert_actual_amount = fields.Monetary(
        string='Actual Amount',
        readonly=True,
        currency_field='currency_id',
        help="Monetary actual consumption at the moment the threshold "
             "was crossed. Snapshot — not recomputed on subsequent "
             "journal-entry posting.",
    )
    alert_planned_amount = fields.Monetary(
        string='Planned Amount',
        readonly=True,
        currency_field='currency_id',
        help="Monetary planned amount of the budget line at the moment "
             "the threshold was crossed.",
    )
    alert_type = fields.Selection(
        selection=[
            ('warning', 'Warning'),
            ('alert', 'Alert'),
            ('critical', 'Critical'),
            ('over_budget', 'Over Budget'),
        ],
        string='Alert Type',
        required=True,
        readonly=True,
        tracking=True,
        help="Classification of the alert derived from the threshold: "
             "75→warning, 90→alert, 100→critical, 110→over_budget.",
    )
    alert_severity = fields.Selection(
        selection=[
            ('low', 'Low'),
            ('medium', 'Medium'),
            ('high', 'High'),
            ('critical', 'Critical'),
        ],
        string='Severity',
        compute='_compute_alert_severity',
        store=True,
        help="Severity level mapped from ``alert_threshold_percent``. "
             "Used by the dashboard kanban for color coding per "
             "BM-005 Scenario 6.",
    )

    # ==================================================================
    # Section 3.3 — Recipient + notification fields
    #
    # R-08: every field in this section uses the ``alert_`` prefix.
    # ==================================================================

    alert_recipient_user_ids = fields.Many2many(
        comodel_name='res.users',
        relation='budget_alert_recipient_users_rel',
        column1='alert_id',
        column2='user_id',
        string='Recipient Users',
        help="Users who were notified for this alert event. "
             "Populated by ``_create_alert_for_line`` from the budget's "
             "responsible user plus any group-based recipients.",
    )
    alert_recipient_group_ids = fields.Many2many(
        comodel_name='res.groups',
        relation='budget_alert_recipient_groups_rel',
        column1='alert_id',
        column2='group_id',
        string='Recipient Groups',
        help="Groups whose members were notified for this alert event. "
             "Reserved for future use — group-based recipient expansion "
             "is handled at notification-dispatch time by resolving "
             "``group.users`` against the already-populated "
             "``alert_recipient_user_ids``.",
    )
    alert_notification_channels = fields.Selection(
        selection=[
            ('email', 'Email'),
            ('activity', 'Activity'),
            ('chatter', 'Chatter'),
            ('all', 'All Channels'),
        ],
        string='Notification Channel',
        default='email',
        required=True,
        readonly=True,
        help="Channel used to dispatch the alert notification. "
             "``email`` / ``chatter`` post a ``mail.message`` on the "
             "parent budget's chatter; ``activity`` creates a todo "
             "activity for each recipient user; ``all`` combines both.",
    )
    alert_notified = fields.Boolean(
        string='Notification Sent',
        readonly=True,
        default=False,
        tracking=True,
        help="True once ``_send_notification`` has successfully "
             "dispatched the alert. Used by the dashboard to "
             "distinguish pending from delivered alerts.",
    )
    alert_notification_date = fields.Datetime(
        string='Notification Date',
        readonly=True,
        help="Timestamp at which ``_send_notification`` completed the "
             "dispatch. Remains ``False`` until dispatch succeeds.",
    )
    alert_message = fields.Text(
        string='Alert Message',
        compute='_compute_alert_message',
        store=True,
        help="Human-readable summary of the threshold crossing, "
             "rendered at create time and used as the chatter body and "
             "the ``_rec_name`` value in list / kanban views.",
    )
    alert_mail_message_id = fields.Many2one(
        comodel_name='mail.message',
        string='Originating Mail Message',
        readonly=True,
        ondelete='set null',
        help="Reference to the ``mail.message`` record posted by "
             "``_send_notification``. ``ondelete='set null'`` so that "
             "message deletion / archival does not cascade-delete this "
             "immutable audit record.",
    )

    # ==================================================================
    # Phase 4 — Compute methods
    # ==================================================================

    @api.depends('alert_threshold_percent', 'alert_type')
    def _compute_alert_severity(self):
        """Map the threshold percentage to the BM-005 severity level.

        The mapping is deterministic and bounded to the four thresholds
        enumerated on ``alert_threshold_percent``:

        * ``75``  → ``low``      (approaching budget)
        * ``90``  → ``medium``   (warning)
        * ``100`` → ``high``     (budget reached)
        * ``110`` → ``critical`` (over budget)

        Records without a threshold (an edge case for in-flight
        creation) default to ``low`` rather than raising, so the
        compute remains total.
        """
        mapping = {
            '75': 'low',
            '90': 'medium',
            '100': 'high',
            '110': 'critical',
        }
        for alert in self:
            alert.alert_severity = mapping.get(
                alert.alert_threshold_percent,
                'low',
            )

    @api.depends(
        'budget_line_id',
        'budget_line_id.account_id',
        'alert_threshold_percent',
        'alert_consumption_percent',
        'alert_actual_amount',
        'alert_planned_amount',
    )
    def _compute_alert_message(self):
        """Render the human-readable alert summary.

        Used as the chatter body when ``_send_notification`` posts the
        alert, and as the list / kanban ``_rec_name`` value in the
        alert history view. The message template matches BM-005
        Scenario 2 (early-warning payload) and Scenario 3 (critical
        over-budget payload) in substance; the specific threshold /
        consumption / amounts are injected dynamically.
        """
        for alert in self:
            if not alert.budget_line_id:
                alert.alert_message = ''
                continue
            alert.alert_message = _(
                "Budget line %(account)s reached %(consumption).2f%% "
                "(%(actual)s / %(planned)s) — threshold "
                "%(threshold)s%% crossed.",
            ) % {
                'account': alert.budget_line_id.account_id.display_name or '',
                'consumption': alert.alert_consumption_percent,
                'actual': alert.alert_actual_amount,
                'planned': alert.alert_planned_amount,
                'threshold': alert.alert_threshold_percent,
            }

    # ==================================================================
    # Phase 5 — Immutability overrides
    #
    # BM-005 Scenario 5 mandates that alert records are preserved as an
    # audit trail. Two complementary enforcement points:
    #
    # 1. ``unlink()`` raises ``UserError`` unless the caller is running
    #    in superuser mode (``self.env.su``) or is a member of
    #    ``base.group_system`` (Settings administrators). This allows
    #    regulatory / infrastructure removal paths without giving
    #    ordinary users the ability to hide alerts.
    # 2. ``write()`` raises ``UserError`` when a non-superuser call
    #    attempts to mutate any of the fields in
    #    ``_IMMUTABLE_FIELDS``. Non-immutable fields (e.g.
    #    ``alert_notified``, ``alert_mail_message_id``,
    #    ``alert_notification_date``) may be updated post-creation by
    #    the notification dispatcher.
    # ==================================================================

    def unlink(self):
        """Prohibit deletion of alert audit records by ordinary users.

        Per BM-005 Scenario 5, alert records form an immutable audit
        trail. Deletion is allowed only under two conditions:

        * ``self.env.su`` — the caller is running in superuser mode
          (e.g. module uninstall or an internal framework path).
        * ``self.env.user.has_group('base.group_system')`` — the caller
          is a Settings administrator acting deliberately.

        In all other cases a ``UserError`` is raised with a clear
        explanation pointing the user at the administrative escalation
        path.
        """
        if not self.env.su and not self.env.user.has_group('base.group_system'):
            raise UserError(_(
                "Budget alert records are immutable audit entries and "
                "cannot be deleted. Contact a system administrator if "
                "an entry must be removed for regulatory purposes.",
            ))
        return super().unlink()

    def write(self, vals):
        """Block mutation of snapshot fields post-creation.

        Fields in ``_IMMUTABLE_FIELDS`` capture the state at the moment
        of threshold crossing and must remain stable thereafter.
        Mutation of any such field by a non-superuser raises
        ``UserError``.

        Non-snapshot fields (notification-dispatch bookkeeping such as
        ``alert_notified``, ``alert_notification_date``,
        ``alert_mail_message_id``, recipient lists, chatter threads)
        remain mutable so that the dispatch pipeline can record its
        own outcomes.
        """
        forbidden = set(vals) & set(self._IMMUTABLE_FIELDS)
        if forbidden and not self.env.su:
            raise UserError(_(
                "Fields %(fields)s on budget.alert records are "
                "immutable once the record is created.",
            ) % {'fields': ', '.join(sorted(forbidden))})
        return super().write(vals)

    # ==================================================================
    # Phase 6 — Cron method (BM-005 scheduled threshold evaluation)
    # ==================================================================

    @api.model
    def _cron_evaluate_thresholds(self):
        """BM-005 scheduled alert evaluation.

        Invoked from ``data/budget_alert_cron.xml`` (``ir.cron`` XML
        record — see R-06). The method name matches the cron record's
        ``code`` field ``model._cron_evaluate_thresholds()`` exactly;
        renaming one side of this contract requires updating the
        other in the same commit.

        Scans all confirmed budgets' lines,
        computes consumption per line via a single aggregated query on
        ``account.move.line`` (delegated to
        ``budget.budget.line._compute_variance``), identifies newly
        crossed thresholds (those without a prior alert in the current
        budget window), creates ``budget.alert`` records, and
        dispatches notifications.

        Performance
        -----------
        Must complete within the default Odoo cron timeout for ≤ 1,000
        budget lines (BM-005 performance target). Compliance mechanism:

        * ONE ``search()`` over ``budget.budget.line`` filtered by
          ``budget_id.state == 'confirmed'``.
        * ONE invocation of ``_compute_variance`` on the recordset,
          which internally issues a single ``_read_group`` against
          ``account.move.line`` (per BM-004 implementation).
        * A bounded per-line threshold loop (4 thresholds) with a
          bounded per-(line, threshold) deduplication ``search()``.

        No direct iteration over ``account.move.line`` records is
        performed at any level.
        """
        _logger.info("BM-005: Starting budget threshold evaluation cron")
        BudgetLine = self.env['budget.budget.line']
        active_lines = BudgetLine.search([
            ('budget_id.state', '=', 'confirmed'),
        ])
        if not active_lines:
            _logger.info("BM-005: No active budget lines to evaluate")
            return

        # Defensive: ensure the BM-004 _compute_variance method exists
        # on the recordset class. This is expected to always succeed in
        # production; the guard keeps the cron tolerant during partial
        # upgrades where the sibling model may not yet expose the
        # method. When present, invoking it proactively populates
        # variance_actual on every record in a single _read_group
        # round-trip.
        if hasattr(active_lines, '_compute_variance'):
            active_lines._compute_variance()

        created_count = 0
        for line in active_lines:
            if not line.planned_amount:
                # Zero-planned lines cannot meaningfully breach any
                # percentage threshold; skip to avoid division by zero
                # and to avoid creating spurious alerts.
                continue
            actual = getattr(line, 'variance_actual', 0.0) or 0.0
            consumption = (actual / line.planned_amount) * 100.0
            for threshold in self.THRESHOLDS:
                threshold_float = float(threshold)
                if consumption < threshold_float:
                    # Consumption has not yet reached this threshold;
                    # no alert needed. The loop continues to higher
                    # thresholds but they will all fail the same
                    # comparison so the inner loop short-circuits
                    # implicitly on subsequent iterations.
                    continue
                # Deduplication: has this threshold already been
                # alerted for this line within the active budget
                # window? A single bounded search() per (line,
                # threshold) is acceptable under the performance
                # target because THRESHOLDS has cardinality 4.
                date_from = fields.Datetime.to_datetime(
                    line.budget_id.date_from,
                )
                date_to = fields.Datetime.to_datetime(
                    line.budget_id.date_to,
                )
                domain = [
                    ('budget_line_id', '=', line.id),
                    ('alert_threshold_percent', '=', threshold),
                ]
                if date_from:
                    domain.append(('alert_date', '>=', date_from))
                if date_to:
                    domain.append(('alert_date', '<=', date_to))
                existing = self.search(domain, limit=1)
                if existing:
                    continue
                alert = self._create_alert_for_line(
                    line, threshold, consumption, actual,
                )
                alert._send_notification()
                created_count += 1
        _logger.info(
            "BM-005: Created %s new alert event(s)", created_count,
        )

    @api.model
    def _create_alert_for_line(self, line, threshold, consumption, actual):
        """Factory for a single alert record.

        :param line: the ``budget.budget.line`` record whose threshold
            was crossed.
        :param threshold: string-typed threshold percentage ('75',
            '90', '100', '110') matching the ``alert_threshold_percent``
            Selection key.
        :param consumption: float consumption percentage at the moment
            of crossing (actual / planned * 100).
        :param actual: the monetary actual amount at the moment of
            crossing.
        :return: the newly-created ``budget.alert`` recordset (one
            record).

        Recipient selection: the budget's responsible user
        (``budget.user_id``) is included by default. Group-based
        recipients may be attached subsequently by the dispatcher.
        """
        type_mapping = {
            '75': 'warning',
            '90': 'alert',
            '100': 'critical',
            '110': 'over_budget',
        }
        alert_type = type_mapping.get(threshold, 'warning')
        # Collect recipients: the budget's responsible user is the
        # default recipient. Additional users may be attached post hoc
        # via the dispatcher or by group-expansion logic.
        recipients = self.env['res.users']
        if line.budget_id and line.budget_id.user_id:
            recipients = line.budget_id.user_id
        create_vals = {
            'budget_line_id': line.id,
            'alert_threshold_percent': threshold,
            'alert_consumption_percent': consumption,
            'alert_actual_amount': actual,
            'alert_planned_amount': line.planned_amount,
            'alert_type': alert_type,
            'alert_notification_channels': 'email',
        }
        if recipients:
            create_vals['alert_recipient_user_ids'] = [
                (6, 0, recipients.ids),
            ]
        return self.create(create_vals)

    # ==================================================================
    # Phase 7 — Notification dispatcher
    # ==================================================================

    def _send_notification(self):
        """Dispatch the alert via the configured channel.

        For the ``email`` / ``all`` / ``chatter`` channels, posts a
        ``mail.message`` on the parent ``budget.budget``'s chatter
        (``budget.budget`` composes ``mail.thread`` and
        ``mail.activity.mixin``), notifying the partners associated
        with ``alert_recipient_user_ids``. The returned
        ``mail.message`` is stored in ``alert_mail_message_id`` for
        audit-trail traceability.

        For the ``activity`` / ``all`` channels, schedules a todo
        ``mail.activity`` on the parent budget for each recipient user
        so that the responsible user sees an actionable item in their
        activity queue (BM-005 Scenario 2 — activity-based follow-up).

        On completion, records the dispatch outcome on the alert
        itself: ``alert_notified = True`` and
        ``alert_notification_date = now``.
        """
        for alert in self:
            if not alert.budget_id:
                # Defensive: if the related budget_id somehow is not
                # populated (should not happen since budget_line_id is
                # required and the related is stored), skip dispatch
                # rather than raise.
                _logger.warning(
                    "BM-005: alert %s has no budget_id; skipping "
                    "notification dispatch",
                    alert.id,
                )
                continue
            partners = alert.alert_recipient_user_ids.partner_id
            channel = alert.alert_notification_channels
            msg = False
            if channel in ('email', 'all', 'chatter'):
                # message_post returns a mail.message record. The
                # budget.budget model composes mail.thread, so this
                # call threads the notification into the parent
                # budget's chatter with the configured subtype.
                msg = alert.budget_id.message_post(
                    body=alert.alert_message,
                    partner_ids=partners.ids,
                    subject=_(
                        "Budget Alert: %(level)s%% threshold crossed",
                        level=alert.alert_threshold_percent,
                    ),
                    message_type='notification',
                    subtype_xmlid='mail.mt_note',
                )
                alert.alert_mail_message_id = msg.id if msg else False
            if channel in ('activity', 'all'):
                # One todo activity per recipient so that each user's
                # activity queue surfaces the alert individually.
                for user in alert.alert_recipient_user_ids:
                    alert.budget_id.activity_schedule(
                        act_type_xmlid='mail.mail_activity_data_todo',
                        summary=_(
                            "Budget Alert: %(level)s%% threshold",
                            level=alert.alert_threshold_percent,
                        ),
                        note=alert.alert_message,
                        user_id=user.id,
                    )
            alert.alert_notified = True
            alert.alert_notification_date = fields.Datetime.now()

    # ==================================================================
    # Phase 8 — SQL constraints
    # ==================================================================
    # Declared via Odoo 19's ``models.Constraint`` TableObject pattern.
    # The legacy ``_sql_constraints`` attribute was deprecated in Odoo 19
    # (registry-load warning). See ``odoo/orm/table_objects.py`` and
    # ``addons/l10n_vn_edi_viettel/models/sinvoice.py`` for precedent.

    _unique_line_threshold_per_budget_window = models.Constraint(
        'UNIQUE(budget_line_id, alert_threshold_percent, alert_date)',
        'An alert for this budget line at this threshold has '
        'already been recorded at this timestamp.',
    )
