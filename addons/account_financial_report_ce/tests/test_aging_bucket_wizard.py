# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Test Suite — Aging Bucket Thresholds on Financial Report Wizard
(Directive 6 / Refine PR Phase 6)

Verifies that the four configurable aging-bucket fields declared on
``account.financial.report.wizard``:

  - ``bucket_1_days`` (default 30)
  - ``bucket_2_days`` (default 60)
  - ``bucket_3_days`` (default 90)
  - ``bucket_4_days`` (default 120)

are correctly propagated to the target
``account.aged.partner.balance.report`` model *only* for aged-partner
report types (``aged_receivable`` / ``aged_payable``), and are omitted
from the ``vals`` dict for every other report type.

Two test classes are defined, one per Refine-PR acceptance assertion:

  (a) ``TestAgingBucketValsForAgedReports``:
      Bucket values appear in ``vals`` for aged_receivable and
      aged_payable report types, including both default and custom
      bucket day overrides.

  (b) ``TestAgingBucketValsForNonAgedReports``:
      Bucket keys are *absent* from ``vals`` for every other report
      type (balance_sheet, profit_loss, cash_flow, general_ledger,
      trial_balance).

Both classes use ``unittest.mock.patch.object`` to spy on the ORM
``create()`` method of each report transient model so the ``vals``
dict assembled by ``action_generate_report()`` can be captured
non-destructively without relying on database side-effects.
"""

import contextlib
from datetime import date
from unittest.mock import patch

from freezegun import freeze_time

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon

_FROZEN_TODAY = '2024-06-15'
_FROZEN_DATE = date(2024, 6, 15)


# =============================================================================
# SHARED BASE — grants security groups + deterministic company_id
# =============================================================================
@tagged('post_install', '-at_install')
class _AgingBucketWizardTestBase(AccountTestInvoicingCommon):
    """Base class providing common fixtures for bucket-field tests."""

    @classmethod
    def setUpClass(cls):
        """Grant financial report security groups to the test user so the
        wizard can create report records without AccessError."""
        super().setUpClass()

        fr_manager_group = cls.env.ref(
            'account_financial_report_ce.group_financial_report_manager',
            raise_if_not_found=False,
        )
        if fr_manager_group:
            cls.env.user.group_ids += fr_manager_group

        cls.company = cls.env.company
        cls.date_start = date(2024, 1, 1)
        cls.date_end = _FROZEN_DATE

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------
    def _create_wizard(self, report_type, **overrides):
        """Create a wizard record for the given report_type with sensible
        defaults; overrides override any default value.

        Period reports (``profit_loss``, ``cash_flow``, ``general_ledger``)
        require ``date_from``; every report type requires ``date_to``.
        Aged reports additionally require ``partner_type``.
        """
        vals = {
            'report_type': report_type,
            'date_to': self.date_end,
            'company_id': self.company.id,
            'target_move': 'posted',
        }
        if report_type in ('profit_loss', 'cash_flow', 'general_ledger'):
            vals['date_from'] = self.date_start
        if report_type == 'cash_flow':
            vals['cash_flow_method'] = 'indirect'
        if report_type in ('aged_receivable', 'aged_payable'):
            vals['partner_type'] = (
                'customer' if report_type == 'aged_receivable'
                else 'supplier'
            )
        vals.update(overrides)
        return self.env['account.financial.report.wizard'].create(vals)

    def _capture_create_vals(self, wizard, target_model_name):
        """Invoke ``wizard.action_generate_report()`` with a spy on
        ``env[target_model_name].create()`` and return the captured
        ``vals`` dict.

        Implementation:
            The target model's ``create`` method is patched to record its
            ``vals`` argument and then immediately raise ``ValidationError``.
            The wizard's own ``action_generate_report()`` method wraps the
            create call in ``try: ... except (ValidationError, ValueError)``
            and re-raises the exception as ``UserError``.  We catch the
            UserError in the test and return the captured vals.

            This approach avoids the need to pre-create a sentinel record
            with model-specific required fields (each report transient
            model declares a different ``required=True`` set, e.g.
            ``profit_loss`` requires ``date_from``, which cannot be
            satisfied from generic test data).

        Returns:
            dict: The ``vals`` dict the wizard assembled *before* calling
                ``create()`` on the target model.  If multiple create calls
                occur, the first call's vals is returned.
        """
        target_model = self.env[target_model_name]
        target_cls = type(target_model)

        captured = {}

        def fake_create(self_arg, vals_or_list):
            """Patched ``create`` method — captures vals then raises.

            Odoo 19 wraps ``create`` with ``@api.model_create_multi`` which
            normalizes a single-dict argument into a list of dicts.  We
            handle both forms defensively.
            """
            if isinstance(vals_or_list, dict):
                payload = vals_or_list
            elif isinstance(vals_or_list, (list, tuple)) and vals_or_list:
                payload = vals_or_list[0]
            else:
                payload = {}
            if 'vals' not in captured:
                captured['vals'] = dict(payload)
            # Raise ValidationError so the wizard's own try/except catches it
            # and re-raises as UserError — no actual DB write occurs.
            capture_msg = "__test_capture__"
            raise ValidationError(capture_msg)

        # Expected control flow: fake_create raises ValidationError to short-
        # circuit the real create(); the wizard may wrap that into UserError.
        # Either is an acceptable signal that vals have been captured, so we
        # suppress both.
        with patch.object(target_cls, 'create', fake_create), \
                contextlib.suppress(UserError, ValidationError):
            wizard.action_generate_report()

        return captured.get('vals', {})


# =============================================================================
# (a)  BUCKET VALS APPEAR FOR AGED REPORTS
# =============================================================================
@tagged('post_install', '-at_install')
class TestAgingBucketValsForAgedReports(_AgingBucketWizardTestBase):
    """Verify bucket_N_days keys are present in the ``vals`` dict for
    aged_receivable and aged_payable report types, and carry the exact
    values set on the wizard (both defaults and custom overrides)."""

    AGED_MODEL = 'account.aged.partner.balance.report'

    # -------------------------------------------------------------------------
    # Default bucket values
    # -------------------------------------------------------------------------
    @freeze_time(_FROZEN_TODAY)
    def test_aged_receivable_default_buckets_in_vals(self):
        """Default bucket values (30/60/90/120) are in vals for
        aged_receivable reports."""
        wizard = self._create_wizard('aged_receivable')
        # Sanity-check that defaults are applied by the ORM:
        self.assertEqual(wizard.bucket_1_days, 30,
                         "Default bucket_1_days must be 30.")
        self.assertEqual(wizard.bucket_2_days, 60,
                         "Default bucket_2_days must be 60.")
        self.assertEqual(wizard.bucket_3_days, 90,
                         "Default bucket_3_days must be 90.")
        self.assertEqual(wizard.bucket_4_days, 120,
                         "Default bucket_4_days must be 120.")

        vals = self._capture_create_vals(wizard, self.AGED_MODEL)
        self.assertIn('bucket_1_days', vals,
                      "bucket_1_days must be present in vals for "
                      "aged_receivable.")
        self.assertIn('bucket_2_days', vals,
                      "bucket_2_days must be present in vals for "
                      "aged_receivable.")
        self.assertIn('bucket_3_days', vals,
                      "bucket_3_days must be present in vals for "
                      "aged_receivable.")
        self.assertIn('bucket_4_days', vals,
                      "bucket_4_days must be present in vals for "
                      "aged_receivable.")
        self.assertEqual(vals['bucket_1_days'], 30)
        self.assertEqual(vals['bucket_2_days'], 60)
        self.assertEqual(vals['bucket_3_days'], 90)
        self.assertEqual(vals['bucket_4_days'], 120)

    @freeze_time(_FROZEN_TODAY)
    def test_aged_payable_default_buckets_in_vals(self):
        """Default bucket values are in vals for aged_payable reports."""
        wizard = self._create_wizard('aged_payable')

        vals = self._capture_create_vals(wizard, self.AGED_MODEL)
        self.assertIn('bucket_1_days', vals,
                      "bucket_1_days must be present in vals for "
                      "aged_payable.")
        self.assertIn('bucket_2_days', vals)
        self.assertIn('bucket_3_days', vals)
        self.assertIn('bucket_4_days', vals)
        self.assertEqual(vals['bucket_1_days'], 30)
        self.assertEqual(vals['bucket_2_days'], 60)
        self.assertEqual(vals['bucket_3_days'], 90)
        self.assertEqual(vals['bucket_4_days'], 120)

    # -------------------------------------------------------------------------
    # Custom (overridden) bucket values
    # -------------------------------------------------------------------------
    @freeze_time(_FROZEN_TODAY)
    def test_aged_receivable_custom_buckets_in_vals(self):
        """Custom bucket day thresholds (7/14/21/28) are passed through to
        vals for aged_receivable reports."""
        wizard = self._create_wizard(
            'aged_receivable',
            bucket_1_days=7,
            bucket_2_days=14,
            bucket_3_days=21,
            bucket_4_days=28,
        )
        self.assertEqual(wizard.bucket_1_days, 7)
        self.assertEqual(wizard.bucket_2_days, 14)
        self.assertEqual(wizard.bucket_3_days, 21)
        self.assertEqual(wizard.bucket_4_days, 28)

        vals = self._capture_create_vals(wizard, self.AGED_MODEL)
        self.assertEqual(vals['bucket_1_days'], 7,
                         "Custom bucket_1_days must be threaded to vals.")
        self.assertEqual(vals['bucket_2_days'], 14)
        self.assertEqual(vals['bucket_3_days'], 21)
        self.assertEqual(vals['bucket_4_days'], 28)

    @freeze_time(_FROZEN_TODAY)
    def test_aged_payable_custom_buckets_in_vals(self):
        """Custom bucket day thresholds (45/75/120/180) are passed through
        to vals for aged_payable reports."""
        wizard = self._create_wizard(
            'aged_payable',
            bucket_1_days=45,
            bucket_2_days=75,
            bucket_3_days=120,
            bucket_4_days=180,
        )
        vals = self._capture_create_vals(wizard, self.AGED_MODEL)
        self.assertEqual(vals['bucket_1_days'], 45)
        self.assertEqual(vals['bucket_2_days'], 75)
        self.assertEqual(vals['bucket_3_days'], 120)
        self.assertEqual(vals['bucket_4_days'], 180)

    @freeze_time(_FROZEN_TODAY)
    def test_aged_receivable_all_four_keys_present(self):
        """All four bucket keys must be simultaneously present in vals —
        not just a subset — for aged_receivable report type."""
        wizard = self._create_wizard('aged_receivable')
        vals = self._capture_create_vals(wizard, self.AGED_MODEL)
        bucket_keys_present = {
            k for k in (
                'bucket_1_days', 'bucket_2_days',
                'bucket_3_days', 'bucket_4_days',
            )
            if k in vals
        }
        self.assertEqual(
            len(bucket_keys_present), 4,
            "All four bucket_N_days keys must be present in vals "
            "for aged_receivable; got %r." % bucket_keys_present,
        )

    @freeze_time(_FROZEN_TODAY)
    def test_aged_payable_all_four_keys_present(self):
        """All four bucket keys must be simultaneously present in vals —
        not just a subset — for aged_payable report type."""
        wizard = self._create_wizard('aged_payable')
        vals = self._capture_create_vals(wizard, self.AGED_MODEL)
        bucket_keys_present = {
            k for k in (
                'bucket_1_days', 'bucket_2_days',
                'bucket_3_days', 'bucket_4_days',
            )
            if k in vals
        }
        self.assertEqual(
            len(bucket_keys_present), 4,
            "All four bucket_N_days keys must be present in vals "
            "for aged_payable; got %r." % bucket_keys_present,
        )


# =============================================================================
# (b)  BUCKET VALS ABSENT FOR NON-AGED REPORTS
# =============================================================================
@tagged('post_install', '-at_install')
class TestAgingBucketValsForNonAgedReports(_AgingBucketWizardTestBase):
    """Verify bucket_N_days keys are completely absent from the ``vals``
    dict for every non-aged report type.  Because the target report
    models (``account.balance.sheet.report``, ``account.profit.loss.report``,
    etc.) do not declare bucket fields, including them in ``vals`` would
    raise ``ValueError: Invalid field ...`` during ``create()``; this
    guard is business-critical."""

    BUCKET_KEYS = (
        'bucket_1_days',
        'bucket_2_days',
        'bucket_3_days',
        'bucket_4_days',
    )

    REPORT_TYPE_MODEL_MAP = {
        'balance_sheet': 'account.balance.sheet.report',
        'profit_loss': 'account.profit.loss.report',
        'cash_flow': 'account.cash.flow.report',
        'general_ledger': 'account.general.ledger.report',
        'trial_balance': 'account.trial.balance.report',
    }

    def _assert_no_bucket_keys(self, vals, report_type):
        """Helper: assert no bucket_N_days keys are in the vals dict."""
        for key in self.BUCKET_KEYS:
            self.assertNotIn(
                key, vals,
                "Bucket key %r must NOT appear in vals for report_type "
                "%r; got vals keys %r" % (key, report_type, list(vals)),
            )

    @freeze_time(_FROZEN_TODAY)
    def test_balance_sheet_has_no_bucket_keys(self):
        """Bucket keys MUST be absent from vals for balance_sheet reports."""
        wizard = self._create_wizard('balance_sheet')
        vals = self._capture_create_vals(
            wizard, self.REPORT_TYPE_MODEL_MAP['balance_sheet'],
        )
        self._assert_no_bucket_keys(vals, 'balance_sheet')

    @freeze_time(_FROZEN_TODAY)
    def test_profit_loss_has_no_bucket_keys(self):
        """Bucket keys MUST be absent from vals for profit_loss reports."""
        wizard = self._create_wizard('profit_loss')
        vals = self._capture_create_vals(
            wizard, self.REPORT_TYPE_MODEL_MAP['profit_loss'],
        )
        self._assert_no_bucket_keys(vals, 'profit_loss')

    @freeze_time(_FROZEN_TODAY)
    def test_cash_flow_has_no_bucket_keys(self):
        """Bucket keys MUST be absent from vals for cash_flow reports."""
        wizard = self._create_wizard('cash_flow')
        vals = self._capture_create_vals(
            wizard, self.REPORT_TYPE_MODEL_MAP['cash_flow'],
        )
        self._assert_no_bucket_keys(vals, 'cash_flow')

    @freeze_time(_FROZEN_TODAY)
    def test_general_ledger_has_no_bucket_keys(self):
        """Bucket keys MUST be absent from vals for general_ledger reports."""
        wizard = self._create_wizard('general_ledger')
        vals = self._capture_create_vals(
            wizard, self.REPORT_TYPE_MODEL_MAP['general_ledger'],
        )
        self._assert_no_bucket_keys(vals, 'general_ledger')

    @freeze_time(_FROZEN_TODAY)
    def test_trial_balance_has_no_bucket_keys(self):
        """Bucket keys MUST be absent from vals for trial_balance reports."""
        wizard = self._create_wizard('trial_balance')
        vals = self._capture_create_vals(
            wizard, self.REPORT_TYPE_MODEL_MAP['trial_balance'],
        )
        self._assert_no_bucket_keys(vals, 'trial_balance')

    @freeze_time(_FROZEN_TODAY)
    def test_non_aged_reports_ignore_wizard_bucket_overrides(self):
        """Even if the user sets bucket field values on the wizard (which
        may happen via default_* context keys), those values must not leak
        into the vals dict for non-aged report types."""
        for report_type in ('balance_sheet', 'profit_loss',
                            'cash_flow', 'general_ledger', 'trial_balance'):
            with self.subTest(report_type=report_type):
                wizard = self._create_wizard(
                    report_type,
                    bucket_1_days=99,
                    bucket_2_days=199,
                    bucket_3_days=299,
                    bucket_4_days=399,
                )
                # Confirm values were stored on the wizard:
                self.assertEqual(wizard.bucket_1_days, 99)
                self.assertEqual(wizard.bucket_4_days, 399)

                vals = self._capture_create_vals(
                    wizard, self.REPORT_TYPE_MODEL_MAP[report_type],
                )
                self._assert_no_bucket_keys(vals, report_type)
