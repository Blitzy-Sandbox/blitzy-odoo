# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Test Suite for BM-005: Budget Alerts

Implements comprehensive tests for the budget.alert model:
- Threshold configuration (75%/90%/100%/110%)
- Severity classification (low/medium/high/critical)
- Recipient configuration (res.users, res.groups)
- Alert history immutability (unlink / write guards)
- _cron_evaluate_thresholds scheduled-action method
- Deduplication within a budget window
- Subsequent transactions below threshold do NOT re-trigger
- Notification dispatch via chatter / activities
- BM-005 dashboard action

Target: >=80% line coverage per Rule R-04.
Enforces Rule R-08: all new fields use the alert_* prefix.
"""

from datetime import date, datetime

from freezegun import freeze_time
from psycopg2 import (
    IntegrityError,  # noqa: F401  # documents expected underlying DB error
)

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tools import float_compare, mute_logger

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestBudgetAlerts(AccountTestInvoicingCommon):
    """
    Test class for BM-005: Budget Alerts.

    Validates budget.alert model fields, _cron_evaluate_thresholds scheduled
    action, deduplication, immutability, severity mapping, and notification
    dispatch. All fields use alert_* prefix per R-08.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        AccountAccount = cls.env['account.account']

        # Chart-of-account fixtures: an expense account (the budgeted
        # account) and a cash account (the credit counterpart for balanced
        # journal entries). Codes are prefixed with XTEST to avoid
        # collisions with the generic chart-of-accounts shipped by the
        # test common.
        cls.acc_expense = AccountAccount.create({
            'code': 'XTEST.60000',
            'name': 'Test Expense',
            'account_type': 'expense',
        })
        cls.acc_cash = AccountAccount.create({
            'code': 'XTEST.10100',
            'name': 'Test Cash',
            'account_type': 'asset_cash',
        })

        # Recipient users for alert notification tests.
        # Linked to the baseline internal user group so that they can
        # read budget records via the module's ir.model.access.csv ACL
        # rows (budget.alert has user=1,0,0,0 via account.group_account_user).
        base_user_group = cls.env.ref('base.group_user')
        account_user_group = cls.env.ref('account.group_account_user')
        cls.user_ap = cls.env['res.users'].create({
            'name': 'AP Manager BM005',
            'login': 'test_ap_bm005',
            'email': 'ap.manager@bm005.test',
            'group_ids': [
                Command.link(base_user_group.id),
                Command.link(account_user_group.id),
            ],
        })
        cls.user_cfo = cls.env['res.users'].create({
            'name': 'CFO BM005',
            'login': 'test_cfo_bm005',
            'email': 'cfo@bm005.test',
            'group_ids': [
                Command.link(base_user_group.id),
                Command.link(account_user_group.id),
            ],
        })

        # Recipient group for multi-recipient escalation tests.
        cls.group_budget_owners = cls.env['res.groups'].create({
            'name': 'Budget Owners BM005',
        })

        # A confirmed FY2024 budget with a single expense line of 100,000.
        # action_confirm() is required because _cron_evaluate_thresholds
        # only scans lines whose budget.state == 'confirmed'.
        cls.budget = cls.env['budget.budget'].create({
            'name': 'FY2024 Alert Budget',
            'date_from': date(2024, 1, 1),
            'date_to': date(2024, 12, 31),
        })
        cls.line = cls.env['budget.budget.line'].create({
            'budget_id': cls.budget.id,
            'account_id': cls.acc_expense.id,
            'planned_amount': 100000.0,
        })
        cls.budget.action_confirm()

        # Reference journal used for all posted expense entries; reuses
        # the miscellaneous journal already provisioned by
        # AccountTestInvoicingCommon's ``company_data`` dict.
        cls.journal_misc = cls.company_data['default_journal_misc']

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------

    def _post_expense(self, amount, move_date=None):
        """Post a balanced expense entry to trigger alert evaluation.

        Creates an ``account.move`` of type ``entry`` with a debit to
        ``self.acc_expense`` (the budgeted account) and a credit to
        ``self.acc_cash`` for ``amount``. The move is posted so its
        balance feeds the budget line's ``variance_actual`` computed
        field which in turn drives the consumption % used by
        ``_cron_evaluate_thresholds``.

        :param float amount: debit/credit amount in the company currency.
        :param move_date: optional override for the move's ``date``;
            defaults to 2024-06-15 so moves land inside the budget window.
        :returns: the posted ``account.move`` record.
        """
        move_date = move_date or date(2024, 6, 15)
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': self.journal_misc.id,
            'date': move_date,
            'line_ids': [
                Command.create({
                    'account_id': self.acc_expense.id,
                    'name': 'Expense',
                    'debit': amount,
                    'credit': 0.0,
                }),
                Command.create({
                    'account_id': self.acc_cash.id,
                    'name': 'Cash',
                    'debit': 0.0,
                    'credit': amount,
                }),
            ],
        })
        move.action_post()
        return move

    def _create_alert(self, **overrides):
        """Create an alert with default values for the primary test line.

        Defaults correspond to a 75% threshold crossing on ``self.line``
        (planned 100,000 / actual 75,000). Individual tests override
        fields to exercise different severity mappings and type codes.

        :param overrides: ``fields.*`` values merged on top of the defaults.
        :returns: a single ``budget.alert`` record.
        """
        vals = {
            'budget_line_id': self.line.id,
            'alert_threshold_percent': '75',
            'alert_consumption_percent': 75.0,
            'alert_actual_amount': 75000.0,
            'alert_planned_amount': 100000.0,
            'alert_type': 'warning',
        }
        vals.update(overrides)
        return self.env['budget.alert'].create(vals)

    # ------------------------------------------------------------------
    # Field basics + severity mapping
    # ------------------------------------------------------------------

    def test_bm005_alert_create_with_required_fields(self):
        """An alert is created with budget_line_id and alert_threshold_percent."""
        alert = self._create_alert()
        self.assertTrue(alert, "Alert record should be created")
        self.assertEqual(alert.budget_line_id, self.line)
        self.assertEqual(alert.alert_threshold_percent, '75')
        # Monetary snapshot fields are stored on creation.
        self.assertEqual(
            float_compare(
                alert.alert_actual_amount, 75000.0, precision_digits=2,
            ),
            0,
        )
        self.assertEqual(
            float_compare(
                alert.alert_planned_amount, 100000.0, precision_digits=2,
            ),
            0,
        )

    def test_bm005_alert_severity_mapping_75_to_low(self):
        """Severity mapping: 75 → low."""
        alert = self._create_alert(
            alert_threshold_percent='75',
            alert_type='warning',
        )
        self.assertEqual(
            alert.alert_severity,
            'low',
            "75%% threshold must map to severity=low per BM-005 mapping",
        )

    def test_bm005_alert_severity_mapping_90_to_medium(self):
        """Severity mapping: 90 → medium."""
        alert = self._create_alert(
            alert_threshold_percent='90',
            alert_consumption_percent=90.0,
            alert_actual_amount=90000.0,
            alert_type='alert',
        )
        self.assertEqual(
            alert.alert_severity,
            'medium',
            "90%% threshold must map to severity=medium per BM-005 mapping",
        )

    def test_bm005_alert_severity_mapping_100_to_high(self):
        """Severity mapping: 100 → high."""
        alert = self._create_alert(
            alert_threshold_percent='100',
            alert_consumption_percent=100.0,
            alert_actual_amount=100000.0,
            alert_type='critical',
        )
        self.assertEqual(
            alert.alert_severity,
            'high',
            "100%% threshold must map to severity=high per BM-005 mapping",
        )

    def test_bm005_alert_severity_mapping_110_to_critical(self):
        """Severity mapping: 110 → critical."""
        alert = self._create_alert(
            alert_threshold_percent='110',
            alert_consumption_percent=110.0,
            alert_actual_amount=110000.0,
            alert_type='over_budget',
        )
        self.assertEqual(
            alert.alert_severity,
            'critical',
            "110%% threshold must map to severity=critical per BM-005 mapping",
        )

    def test_bm005_alert_date_defaulted_to_now(self):
        """alert_date defaults to fields.Datetime.now on creation."""
        with freeze_time('2024-06-15 10:30:00'):
            alert = self._create_alert()
        self.assertTrue(alert.alert_date, "alert_date must be populated")
        # Frozen time check (Datetime.now returns naive UTC).
        self.assertEqual(
            alert.alert_date.strftime('%Y-%m-%d'),
            '2024-06-15',
            "alert_date must default to fields.Datetime.now() at creation",
        )

    def test_bm005_alert_message_computed_and_stored(self):
        """alert_message is computed+store and contains budget name + percent."""
        alert = self._create_alert()
        self.assertTrue(
            alert.alert_message,
            "alert_message must be populated by the compute method",
        )
        # Message template substitutes account display name and threshold.
        self.assertIn(self.acc_expense.display_name, alert.alert_message)
        self.assertIn('75', alert.alert_message)
        # Compute result is persisted (store=True) so a reload preserves it.
        alert.invalidate_recordset(['alert_message'])
        self.assertTrue(alert.alert_message)

    def test_bm005_alert_related_fields_follow_line(self):
        """company_id, currency_id, budget_id are related to budget_line_id."""
        alert = self._create_alert()
        self.assertEqual(
            alert.budget_id,
            self.budget,
            "alert.budget_id must mirror budget_line_id.budget_id",
        )
        self.assertEqual(
            alert.company_id,
            self.line.company_id,
            "alert.company_id must be related to budget_line_id.company_id",
        )
        self.assertEqual(
            alert.currency_id,
            self.line.currency_id,
            "alert.currency_id must be related to budget_line_id.currency_id",
        )

    # ------------------------------------------------------------------
    # Recipient configuration
    # ------------------------------------------------------------------

    def test_bm005_alert_accepts_recipient_users(self):
        """alert_recipient_user_ids accepts a list of res.users."""
        alert = self._create_alert()
        alert.write({
            'alert_recipient_user_ids': [
                Command.link(self.user_ap.id),
                Command.link(self.user_cfo.id),
            ],
        })
        self.assertIn(self.user_ap, alert.alert_recipient_user_ids)
        self.assertIn(self.user_cfo, alert.alert_recipient_user_ids)
        self.assertEqual(len(alert.alert_recipient_user_ids), 2)

    def test_bm005_alert_accepts_recipient_groups(self):
        """alert_recipient_group_ids accepts a list of res.groups."""
        alert = self._create_alert()
        alert.write({
            'alert_recipient_group_ids': [
                Command.link(self.group_budget_owners.id),
            ],
        })
        self.assertIn(
            self.group_budget_owners,
            alert.alert_recipient_group_ids,
        )
        self.assertEqual(len(alert.alert_recipient_group_ids), 1)

    def test_bm005_alert_notification_channels_default(self):
        """alert_notification_channels defaults to a valid Selection value."""
        alert = self._create_alert()
        self.assertIn(
            alert.alert_notification_channels,
            ('email', 'activity', 'chatter', 'all'),
            "alert_notification_channels must default to a valid Selection key",
        )

    # ------------------------------------------------------------------
    # Immutability (unlink / write guards)
    # ------------------------------------------------------------------

    def test_bm005_alert_unlink_raises_for_standard_user(self):
        """Unlinking an alert raises UserError for standard users.

        BM-005 Scenario 4 mandates that alert records form an immutable
        audit trail. The ``unlink()`` override raises ``UserError`` unless
        the caller is the superuser or a member of ``base.group_system``;
        non-privileged users therefore cannot delete alerts. ``with_user``
        (not ``sudo()``) is used per Rule R-07.
        """
        alert = self._create_alert()
        with self.assertRaises(
            UserError,
            msg="unlink() must raise UserError for non-system users",
        ):
            alert.with_user(self.user_ap).unlink()
        # The alert must still exist after the failed unlink.
        self.assertTrue(alert.exists(), "Alert must survive the failed unlink")

    def test_bm005_alert_write_blocks_immutable_fields_for_standard_user(self):
        """Modifying immutable fields raises UserError for non-superuser."""
        alert = self._create_alert()
        with self.assertRaises(
            UserError,
            msg="write() on alert_threshold_percent must raise UserError",
        ):
            alert.with_user(self.user_ap).write({
                'alert_threshold_percent': '90',
            })
        # Confirm the field was NOT mutated.
        self.assertEqual(
            alert.alert_threshold_percent,
            '75',
            "alert_threshold_percent must be preserved after blocked write",
        )

    def test_bm005_alert_write_blocks_consumption_percent_mutation(self):
        """alert_consumption_percent is immutable after creation."""
        alert = self._create_alert()
        original = alert.alert_consumption_percent
        with self.assertRaises(
            UserError,
            msg="write() on alert_consumption_percent must raise UserError",
        ):
            alert.with_user(self.user_ap).write({
                'alert_consumption_percent': 99.9,
            })
        # The original snapshot value must be preserved.
        self.assertEqual(
            float_compare(
                alert.alert_consumption_percent,
                original,
                precision_digits=2,
            ),
            0,
            "alert_consumption_percent must NOT be mutated after blocked write",
        )

    def test_bm005_alert_write_allows_notification_state_update(self):
        """alert_notified is NOT in _IMMUTABLE_FIELDS; it can be updated."""
        alert = self._create_alert()
        self.assertFalse(
            alert.alert_notified,
            "alert_notified must default to False at creation",
        )
        alert.write({
            'alert_notified': True,
            'alert_notification_date': datetime(2024, 6, 15, 10, 30),
        })
        self.assertTrue(alert.alert_notified)
        self.assertEqual(
            alert.alert_notification_date,
            datetime(2024, 6, 15, 10, 30),
        )

    def test_bm005_alert_write_allows_recipient_update(self):
        """alert_recipient_* are NOT immutable; they can be updated post-creation."""
        alert = self._create_alert()
        # Initially no recipients.
        self.assertFalse(alert.alert_recipient_user_ids)
        # Adding a recipient must succeed for a standard ACL manager user
        # via the default superuser test env (no immutability guard hit).
        alert.write({
            'alert_recipient_user_ids': [Command.link(self.user_cfo.id)],
        })
        self.assertIn(self.user_cfo, alert.alert_recipient_user_ids)

    # ------------------------------------------------------------------
    # Cron threshold evaluation
    # ------------------------------------------------------------------
    # NOTE: All cron tests use ``freeze_time`` to place ``alert_date``
    # (default=Datetime.now) inside the budget fiscal window
    # (2024-01-01 .. 2024-12-31). This is critical because the
    # deduplication logic in ``_cron_evaluate_thresholds`` scopes its
    # existence search to the budget's ``date_from``..``date_to`` range:
    # alerts created outside this window would not be found by the dedup
    # query and would produce spurious duplicates.

    def test_bm005_cron_creates_alert_when_75_percent_crossed(self):
        """_cron_evaluate_thresholds creates a 75% alert when consumption >= 75%."""
        with freeze_time('2024-06-15 10:00:00'):
            self._post_expense(75000.0)
            BudgetAlert = self.env['budget.alert']
            before = BudgetAlert.search_count(
                [('budget_line_id', '=', self.line.id)],
            )
            BudgetAlert._cron_evaluate_thresholds()
            after = BudgetAlert.search_count(
                [('budget_line_id', '=', self.line.id)],
            )
        # At least one alert must have been created by the cron.
        self.assertGreaterEqual(
            after - before,
            1,
            "Cron must create at least one alert at 75%% consumption",
        )
        # The latest alert must have threshold '75' because that is the
        # lowest threshold crossed.
        latest = self.env['budget.alert'].search(
            [
                ('budget_line_id', '=', self.line.id),
                ('alert_threshold_percent', '=', '75'),
            ],
            order='id desc',
            limit=1,
        )
        self.assertTrue(
            latest,
            "A 75%% threshold alert must exist for the budget line",
        )

    def test_bm005_cron_deduplicates_within_budget_window(self):
        """Running cron twice does NOT create duplicate alerts for the same threshold."""
        with freeze_time('2024-06-15 10:00:00'):
            self._post_expense(80000.0)
            BudgetAlert = self.env['budget.alert']
            BudgetAlert._cron_evaluate_thresholds()
            count_after_first = BudgetAlert.search_count([
                ('budget_line_id', '=', self.line.id),
                ('alert_threshold_percent', '=', '75'),
            ])
            # Second invocation must be a no-op for the 75% threshold
            # because an alert already exists within the budget window.
            BudgetAlert._cron_evaluate_thresholds()
            count_after_second = BudgetAlert.search_count([
                ('budget_line_id', '=', self.line.id),
                ('alert_threshold_percent', '=', '75'),
            ])
        self.assertEqual(
            count_after_first,
            count_after_second,
            "Cron dedup must prevent duplicate 75%% alerts in the same window",
        )
        self.assertGreaterEqual(
            count_after_first,
            1,
            "At least one 75%% alert must exist after the first cron run",
        )

    def test_bm005_cron_creates_multiple_thresholds_in_sequence(self):
        """Escalating consumption triggers alerts at each threshold exactly once."""
        BudgetAlert = self.env['budget.alert']
        # 75% threshold — post 75k and run cron (consumption=75%).
        with freeze_time('2024-03-15 10:00:00'):
            self._post_expense(75000.0, move_date=date(2024, 3, 15))
            BudgetAlert._cron_evaluate_thresholds()
        # 90% threshold — add 15k (total 90k, consumption=90%).
        with freeze_time('2024-05-15 10:00:00'):
            self._post_expense(15000.0, move_date=date(2024, 5, 15))
            BudgetAlert._cron_evaluate_thresholds()
        # 100% threshold — add 10k (total 100k, consumption=100%).
        with freeze_time('2024-07-15 10:00:00'):
            self._post_expense(10000.0, move_date=date(2024, 7, 15))
            BudgetAlert._cron_evaluate_thresholds()
        # 110% threshold — add 10k (total 110k, consumption=110%).
        with freeze_time('2024-09-15 10:00:00'):
            self._post_expense(10000.0, move_date=date(2024, 9, 15))
            BudgetAlert._cron_evaluate_thresholds()

        alerts = BudgetAlert.search(
            [('budget_line_id', '=', self.line.id)],
        )
        thresholds = set(alerts.mapped('alert_threshold_percent'))
        self.assertTrue(
            {'75', '90', '100', '110'}.issubset(thresholds),
            f"All four thresholds must have fired; observed={thresholds}",
        )
        # Dedup guarantee: each threshold appears exactly once.
        for threshold in ('75', '90', '100', '110'):
            per_threshold = alerts.filtered(
                lambda a, t=threshold: a.alert_threshold_percent == t,
            )
            self.assertEqual(
                len(per_threshold),
                1,
                f"Threshold {threshold}%% must have exactly one alert",
            )

    def test_bm005_cron_no_alert_below_75_percent(self):
        """Consumption below 75% does NOT create an alert."""
        with freeze_time('2024-06-15 10:00:00'):
            # 50,000 / 100,000 = 50% consumption; below the 75% floor.
            self._post_expense(50000.0)
            BudgetAlert = self.env['budget.alert']
            BudgetAlert._cron_evaluate_thresholds()
            count = BudgetAlert.search_count(
                [('budget_line_id', '=', self.line.id)],
            )
        self.assertEqual(
            count,
            0,
            "No alert should be created when consumption is below 75%%",
        )

    def test_bm005_cron_subsequent_below_threshold_does_not_retrigger(self):
        """
        BM-005 Scenario 5: once a 75% alert has fired, a subsequent cron
        run (still at the same 75% threshold bracket) does NOT create a
        second 75% alert in the same budget window.
        """
        BudgetAlert = self.env['budget.alert']
        with freeze_time('2024-06-15 10:00:00'):
            self._post_expense(75000.0)
            BudgetAlert._cron_evaluate_thresholds()
            count1 = BudgetAlert.search_count([
                ('budget_line_id', '=', self.line.id),
                ('alert_threshold_percent', '=', '75'),
            ])
            self.assertEqual(
                count1,
                1,
                "Initial cron run must create exactly one 75%% alert",
            )
            # Re-run: the same 75% alert already exists within the budget
            # window, so the cron dedup must short-circuit and no new
            # alert can be created.
            BudgetAlert._cron_evaluate_thresholds()
            count2 = BudgetAlert.search_count([
                ('budget_line_id', '=', self.line.id),
                ('alert_threshold_percent', '=', '75'),
            ])
        self.assertEqual(
            count1,
            count2,
            "Subsequent cron run must NOT re-fire the 75%% alert",
        )

    def test_bm005_cron_skips_draft_budgets(self):
        """_cron_evaluate_thresholds only scans confirmed budgets, skipping drafts."""
        # Create a draft (unconfirmed) budget with its own expense line.
        draft = self.env['budget.budget'].create({
            'name': 'Draft-no-alerts',
            'date_from': date(2024, 1, 1),
            'date_to': date(2024, 12, 31),
        })
        draft_line = self.env['budget.budget.line'].create({
            'budget_id': draft.id,
            'account_id': self.acc_expense.id,
            'planned_amount': 10000.0,
        })
        # Confirm the draft budget is still in 'draft' state.
        self.assertEqual(
            draft.state,
            'draft',
            "New budgets must start in the 'draft' state",
        )
        with freeze_time('2024-06-15 10:00:00'):
            # Post enough to exceed 75% on the draft line (8k / 10k = 80%).
            self._post_expense(8000.0)
            self.env['budget.alert']._cron_evaluate_thresholds()
        # No alert should attach to the draft line since its parent budget
        # is not in the 'confirmed' state.
        draft_alerts = self.env['budget.alert'].search(
            [('budget_line_id', '=', draft_line.id)],
        )
        self.assertFalse(
            draft_alerts,
            "Draft budgets must NOT receive alerts from the cron",
        )

    # ------------------------------------------------------------------
    # Notification dispatch
    # ------------------------------------------------------------------

    def test_bm005_send_notification_posts_to_budget_chatter(self):
        """_send_notification posts a chatter message to the budget record."""
        alert = self._create_alert()
        # Link an internal recipient so the chatter dispatch has a target.
        alert.write({
            'alert_recipient_user_ids': [Command.link(self.user_ap.id)],
        })
        MailMessage = self.env['mail.message']
        before_count = MailMessage.search_count([
            ('res_id', '=', self.budget.id),
            ('model', '=', 'budget.budget'),
        ])
        alert._send_notification()
        after_count = MailMessage.search_count([
            ('res_id', '=', self.budget.id),
            ('model', '=', 'budget.budget'),
        ])
        self.assertGreater(
            after_count,
            before_count,
            "_send_notification must post at least one chatter message",
        )
        # The alert's stored reference to the posted mail.message must
        # be populated (relational back-reference for audit traceability).
        self.assertTrue(
            alert.alert_mail_message_id,
            "alert_mail_message_id must be populated after chatter dispatch",
        )

    def test_bm005_send_notification_marks_alert_notified(self):
        """_send_notification sets alert_notified=True and alert_notification_date."""
        alert = self._create_alert()
        alert.write({
            'alert_recipient_user_ids': [Command.link(self.user_ap.id)],
        })
        self.assertFalse(
            alert.alert_notified,
            "alert_notified must start False",
        )
        self.assertFalse(
            alert.alert_notification_date,
            "alert_notification_date must start unset",
        )
        alert._send_notification()
        self.assertTrue(
            alert.alert_notified,
            "_send_notification must set alert_notified=True",
        )
        self.assertTrue(
            alert.alert_notification_date,
            "_send_notification must stamp alert_notification_date",
        )

    def test_bm005_send_notification_schedules_activity_if_configured(self):
        """When alert_notification_channels='activity', an activity is scheduled."""
        alert = self._create_alert()
        alert.write({
            'alert_notification_channels': 'activity',
            'alert_recipient_user_ids': [Command.link(self.user_ap.id)],
        })
        MailActivity = self.env['mail.activity']
        before = MailActivity.search_count([
            ('res_model', '=', 'budget.budget'),
            ('res_id', '=', self.budget.id),
        ])
        alert._send_notification()
        after = MailActivity.search_count([
            ('res_model', '=', 'budget.budget'),
            ('res_id', '=', self.budget.id),
        ])
        self.assertGreaterEqual(
            after,
            before + 1,
            "Activity channel must schedule an activity per recipient",
        )

    # ------------------------------------------------------------------
    # Dashboard action + aggregated fields on budget.budget
    # ------------------------------------------------------------------

    def test_bm005_action_open_alerts_returns_act_window(self):
        """budget.budget.action_open_alerts returns an act_window on budget.alert."""
        self._create_alert()
        action = self.budget.action_open_alerts()
        self.assertIsInstance(
            action,
            dict,
            "action_open_alerts must return an action dict",
        )
        self.assertEqual(
            action.get('type'),
            'ir.actions.act_window',
            "action type must be ir.actions.act_window",
        )
        self.assertEqual(
            action.get('res_model'),
            'budget.alert',
            "action res_model must be budget.alert",
        )
        # The action must be scoped to this specific budget record.
        self.assertIn(
            ('budget_id', '=', self.budget.id),
            action.get('domain', []),
            "action domain must filter by the current budget record",
        )

    def test_bm005_alert_count_reflects_alert_ids(self):
        """budget.budget.alert_count = number of attached alerts."""
        # Sanity baseline: no alerts on a fresh budget.
        self.budget.invalidate_recordset(['alert_count', 'alert_ids'])
        initial_count = self.budget.alert_count
        # Create two alerts for different thresholds.
        self._create_alert()
        self._create_alert(
            alert_threshold_percent='90',
            alert_consumption_percent=90.0,
            alert_actual_amount=90000.0,
            alert_type='alert',
        )
        # Invalidate computed cache to force recompute from alert_ids.
        self.budget.invalidate_recordset(['alert_count', 'alert_ids'])
        self.assertGreaterEqual(
            self.budget.alert_count,
            initial_count + 2,
            "alert_count must reflect the two newly created alerts",
        )
        # alert_ids must contain both created records.
        created_thresholds = set(
            self.budget.alert_ids.mapped('alert_threshold_percent'),
        )
        self.assertTrue(
            {'75', '90'}.issubset(created_thresholds),
            "alert_ids must include both 75%% and 90%% alerts",
        )

    def test_bm005_alert_active_flag_reflects_recent_alerts(self):
        """budget.budget.alert_active = True when at least one alert exists."""
        # Baseline: no alerts, alert_active must be False.
        self.budget.invalidate_recordset(['alert_active'])
        self.assertFalse(
            self.budget.alert_active,
            "alert_active must start False on a fresh budget",
        )
        # After creating an alert, the flag must flip to True.
        self._create_alert()
        self.budget.invalidate_recordset(['alert_active'])
        self.assertTrue(
            self.budget.alert_active,
            "alert_active must flip to True when alerts exist",
        )

    # ------------------------------------------------------------------
    # R-08 alert_* field prefix check (BM-005's own local enforcement)
    # ------------------------------------------------------------------

    def test_bm005_r08_all_alert_fields_prefixed(self):
        """
        R-08 (BM-005 side): every field on budget.alert MUST start with
        alert_ EXCEPT the mandatory Odoo system fields and the related
        FKs (budget_line_id, budget_id, company_id, currency_id) which
        are explicitly allow-listed.
        """
        # Allow-list: Odoo system fields + module-level relational keys +
        # mail.thread mixin fields inherited from the parent mixin.
        allowed_non_prefixed = {
            # Odoo system / audit fields:
            'id',
            'create_uid',
            'create_date',
            'write_uid',
            'write_date',
            'display_name',
            '__last_update',
            # Active flag (convention on almost every model):
            'active',
            # Relational anchors — explicitly allowed non-prefixed per
            # the BM-005 ticket model design:
            'budget_line_id',
            'budget_id',
            'company_id',
            'currency_id',
            # mail.thread mixin inherited fields — allowed non-prefixed
            # because they come from the mixin, not from BM-005:
            'message_follower_ids',
            'message_ids',
            'message_main_attachment_id',
            'message_partner_ids',
            'message_unread',
            'message_unread_counter',
            'message_needaction',
            'message_needaction_counter',
            'message_has_error',
            'message_has_error_counter',
            'message_attachment_count',
            'message_is_follower',
            'message_has_sms_error',
            'has_message',
            'rating_ids',
            'website_message_ids',
        }
        IrModelFields = self.env['ir.model.fields']
        fields_on_model = IrModelFields.search([
            ('model_id.model', '=', 'budget.alert'),
        ])
        offenders = []
        for f in fields_on_model:
            if f.name in allowed_non_prefixed:
                continue
            if not f.name.startswith('alert_'):
                offenders.append(f.name)
        self.assertFalse(
            offenders,
            msg=(
                "R-08 VIOLATION: fields on budget.alert MUST use the "
                "alert_ prefix (unless explicitly allow-listed). "
                f"Offenders: {offenders}"
            ),
        )

    # ------------------------------------------------------------------
    # SQL constraint — unique threshold per window
    # ------------------------------------------------------------------

    def test_bm005_sql_constraint_unique_threshold_within_window(self):
        """unique_line_threshold_per_budget_window prevents duplicate rows.

        The database-level UNIQUE constraint on
        ``(budget_line_id, alert_threshold_percent, alert_date)`` must
        reject a second insert sharing the same tuple. The Odoo ORM may
        wrap the raw ``psycopg2.IntegrityError`` in a higher-level
        exception, so the assertion uses the permissive ``Exception``
        guard while still importing ``IntegrityError`` explicitly to
        document the underlying database error class.
        """
        alert1 = self._create_alert()
        # Attempt to create a duplicate alert with the same budget_line_id
        # + alert_threshold_percent + alert_date. The SQL constraint must
        # prevent the insert. mute_logger suppresses the expected psycopg2
        # SQL error noise in the test output.
        with self.assertRaises(
            Exception,
            msg="Duplicate alert must be rejected by the SQL constraint",
        ):
            with mute_logger('odoo.sql_db'):
                self.env['budget.alert'].create({
                    'budget_line_id': self.line.id,
                    'alert_threshold_percent': alert1.alert_threshold_percent,
                    'alert_date': alert1.alert_date,
                    'alert_consumption_percent': 76.0,
                    'alert_actual_amount': 76000.0,
                    'alert_planned_amount': 100000.0,
                    'alert_type': 'warning',
                })
                self.env.cr.flush()
