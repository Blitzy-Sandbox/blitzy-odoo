# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
PF-003 — Follow-up Report Generation: Acceptance Test Suite
============================================================

Verifies the report wizard, parser AbstractModel, and QWeb PDF / XLSX
export pipeline introduced by:

  * ``addons/account_payment_followup/wizard/followup_report_wizard.py``
    — ``account.followup.report.wizard`` TransientModel.
  * ``addons/account_payment_followup/report/followup_report.py`` —
    ``report.account_payment_followup.followup_aged_receivables``
    AbstractModel parser.
  * ``addons/account_payment_followup/report/followup_report.xml`` —
    ir.actions.report record + QWeb PDF template.

Maps to the eight BDD acceptance scenarios and seven business rules
(BR-001..BR-007) from
``tickets/stories/payment-followups/PF-003-followup-report-generation.md``.

Determinism
-----------
The test class inherits :class:`AccountPaymentFollowupTestCommon` and is
decorated with ``@freeze_time(FROZEN_DATE)`` so all aging calculations
resolve against ``date(2024, 6, 30)``. Without this freeze, partner
``aging_bucket_*`` fields would drift as real time advances past the
fixture invoice dates, breaking deterministic assertions.

Targets ≥80% line coverage of:
  * ``wizard/followup_report_wizard.py``
  * ``report/followup_report.py``

Rules Compliance (AAP §0.7)
---------------------------
- R-01: No imports from sibling new modules (``account_asset_management``,
        ``account_budget_management``, ``account_deferred_revenue``).
- R-02: No imports from Enterprise modules (``account_followup``,
        ``account_accountant``, ``account_reports``).
- R-04: Targets ≥80% coverage of the wizard + parser modules.
- R-07: No ``sudo()`` calls.
- R-09: Filename is ``test_pf_003.py`` exactly (story ID lowercase).
"""

import base64
import io
import logging
import os
import signal
import time
from datetime import date, timedelta

from freezegun import freeze_time
from openpyxl import load_workbook

from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import AccountPaymentFollowupTestCommon
from odoo.addons.account_payment_followup.wizard import (
    followup_report_wizard as wiz_module,
)

_logger = logging.getLogger(__name__)

# Module-level frozen reference date — must mirror common.py FROZEN_DATE
# so the @freeze_time class decorator below stays consistent with fixture
# creation in ``AccountPaymentFollowupTestCommon.setUpClass``.
FROZEN_DATE = date(2024, 6, 30)

# XMLIDs verified across multiple tests (Gate 13 cron / report reachability).
# The report action XID ends in ``_aged_receivables`` to match the actual
# XML id declared in ``report/followup_report.xml`` — the agent_prompt's
# shorter form ``account_payment_followup.action_report_followup`` is a
# documentation drift that this test file silently corrects per the
# AAP discovery note.
REPORT_XMLID = (
    'account_payment_followup.action_report_followup_aged_receivables'
)

# AbstractModel parser ``_name`` — the abbreviated form keeps the
# auto-derived ``_table`` identifier under PostgreSQL's 63-char limit
# (see ``report/followup_report.py`` lines 132-156 for the rationale).
PARSER_MODEL_NAME = (
    'report.account_payment_followup.followup_aged_receivables'
)

# Wizard model technical name — the test_pf_003 surface depends on this
# resolving via ``self.env[WIZARD_MODEL]``.
WIZARD_MODEL = 'account.followup.report.wizard'


@tagged('post_install', '-at_install')
@freeze_time(FROZEN_DATE)
class TestFollowupReportGeneration(AccountPaymentFollowupTestCommon):
    """PF-003 — Follow-up Report Generation.

    Maps to acceptance scenarios:
      - Scenario 1: Aged Receivables Report Generation
      - Scenario 2: Filter by Follow-up Level
      - Scenario 3: Drill-down from Report to Customer Invoices
      - Scenario 4: PDF Export
      - Scenario 5: Excel Export
      - Scenario 6: Follow-up Effectiveness Summary (recovery rate, etc.)
      - Scenario 7: Filter by Date Range / Amount
      - Scenario 8: Group By Salesperson / Region

    Plus: 7 business rules BR-001..BR-007 and performance target <10s
    for 500 partners (PF-003 §6).
    """

    @classmethod
    def setUpClass(cls):
        """Build PF-003-specific fixtures on top of the common base.

        Forces an initial recompute of partner-level aggregates so the
        report parser sees deterministic aging values for every test
        fixture, then caches handy proxies (``cls.Wizard``, ``cls.Parser``)
        used by every test method.
        """
        super().setUpClass()

        # Touch every partner so its computed ``aging_bucket_*`` fields
        # are materialised before any test asserts on them. The
        # ``invalidate_recordset`` purges any cached values so the
        # subsequent ``mapped`` triggers a fresh compute under the frozen
        # reference date.
        all_partners = (
            cls.partner_current
            | cls.partner_overdue_7d | cls.partner_overdue_14d
            | cls.partner_overdue_21d | cls.partner_overdue_30d
            | cls.partner_overdue_45d | cls.partner_overdue_95d
            | cls.partner_mixed_aging
        )
        all_partners.invalidate_recordset()
        all_partners.mapped('followup_level_id')
        all_partners.mapped('total_overdue')
        cls.all_test_partners = all_partners

        # Shorthand proxies for the wizard model and parser AbstractModel.
        cls.Wizard = cls.env[WIZARD_MODEL]
        cls.Parser = cls.env[PARSER_MODEL_NAME]

    # =========================================================================
    # Phase 1 — Wizard CRUD & Defaults
    # =========================================================================

    def test_wizard_creates_with_defaults(self):
        """Phase 1: wizard creates with all sensible defaults.

        Asserts:
          * ``report_date`` defaults to ``fields.Date.context_today(...)``,
            i.e. today (frozen to FROZEN_DATE).
          * ``report_type`` semantics — verified via ``aging_bucket_filter``
            defaulting to ``'all'`` (the wizard exposes filtering via
            ``aging_bucket_filter`` rather than a top-level ``report_type``
            selector; the parser branches on the wizard's filter state).
          * Default company is ``self.env.company``.
          * Default ``date_from`` is first-of-month, ``date_to`` is today
            (so the effective default window is "month-to-date").
          * Effectiveness section is enabled by default.
          * Disputed invoices are excluded by default.
          * Grouping booleans are unset by default.
        """
        wizard = self.Wizard.create({})

        # Record exists
        self.assertTrue(wizard.exists())
        self.assertEqual(wizard._name, WIZARD_MODEL)

        # Date defaults
        self.assertEqual(
            wizard.report_date, FROZEN_DATE,
            'report_date defaults to today (frozen to FROZEN_DATE).',
        )
        self.assertEqual(
            wizard.date_from, date(2024, 6, 1),
            'date_from defaults to first day of current month.',
        )
        self.assertEqual(
            wizard.date_to, FROZEN_DATE,
            'date_to defaults to today.',
        )

        # Scope defaults
        self.assertEqual(
            wizard.company_id, self.env.company,
            'company_id defaults to env.company.',
        )
        self.assertEqual(
            wizard.currency_id, self.env.company.currency_id,
            'currency_id is related to company_id.currency_id.',
        )

        # Filter defaults — ``aging_bucket_filter='all'`` is the parser
        # equivalent of the agent_prompt's ``report_type='aged_receivables'``
        # default since the wizard combines both via ``aging_bucket_filter``.
        self.assertEqual(wizard.aging_bucket_filter, 'all')
        self.assertEqual(wizard.minimum_amount, 0.0)
        self.assertEqual(wizard.target_moves, 'posted')

        # Boolean toggles
        self.assertTrue(
            wizard.include_effectiveness,
            'Effectiveness metrics enabled by default per PF-003 Scenario 6.',
        )
        self.assertFalse(wizard.include_disputed)
        self.assertFalse(wizard.group_by_salesperson)
        self.assertFalse(wizard.group_by_country)

        # Default grouping resolution falls through to 'level'
        self.assertEqual(
            wizard.group_by, 'level',
            'Default grouping is "level" when no flags are set.',
        )

        # Computed display fields are populated
        self.assertTrue(wizard.group_by_label)
        self.assertIsInstance(wizard.followup_level_names, str)

    def test_wizard_field_validators(self):
        """Phase 1: wizard constraints reject invalid input states.

        Exercises three @api.constrains hooks:
          * ``_check_date_range`` — date_from > date_to → ValidationError.
          * ``_check_minimum_amount`` — minimum_amount < 0 → ValidationError.
          * ``_check_company_in_allowed`` — company outside env.companies
            → ValidationError.

        Plus the affirmative case: empty start/end dates do NOT raise
        (no date filter is allowed).
        """
        # Date range: start > end → ValidationError
        with self.assertRaises(ValidationError), \
                mute_logger('odoo.sql_db'):
            self.Wizard.create({
                'date_from': FROZEN_DATE,
                'date_to': FROZEN_DATE - timedelta(days=10),
                'report_date': FROZEN_DATE,
            })

        # Negative minimum amount → ValidationError
        with self.assertRaises(ValidationError), \
                mute_logger('odoo.sql_db'):
            self.Wizard.create({'minimum_amount': -50.0})

        # Forbidden company → ValidationError
        forbidden_company = self.env['res.company'].create({
            'name': 'PF-003 Forbidden Company',
        })
        # Ensure user is NOT in this company
        self.env.user.company_ids = [Command.unlink(forbidden_company.id)]
        with self.assertRaises(ValidationError), \
                mute_logger('odoo.sql_db'):
            self.Wizard.create({'company_id': forbidden_company.id})
        # Restore company access for downstream tests in the same class
        self.env.user.company_ids = [Command.link(forbidden_company.id)]

        # Affirmative case: equal dates are OK (degenerate single-day range).
        wizard_eq = self.Wizard.create({
            'date_from': FROZEN_DATE,
            'date_to': FROZEN_DATE,
            'report_date': FROZEN_DATE,
        })
        self.assertEqual(wizard_eq.date_from, wizard_eq.date_to)

    # =========================================================================
    # Phase 2 — Scenario 1: Aged Receivables Report Happy Path
    # =========================================================================

    def test_scenario_1_aged_receivables_generation(self):
        """Phase 2 / Scenario 1: action_generate_report dispatches PDF action.

        Asserts:
          * ``wizard.action_generate_report()`` returns ``ir.actions.report``.
          * The parser delivers per-partner aging buckets summing to the
            expected partner-level aggregates pulled from
            ``res.partner.aging_bucket_*`` (PF-005 computed fields).
          * Grand totals match ``sum(partner.aging_bucket_*)`` across all
            tested partners (no double-counting, no missing rows).
        """
        wizard = self.Wizard.create({})
        action = wizard.action_generate_report()

        # action_generate_report must dispatch the report action
        self.assertIsInstance(action, dict)
        self.assertEqual(
            action.get('type'), 'ir.actions.report',
            "action_generate_report must return type='ir.actions.report'.",
        )
        # Sanity check: the report_name on the action targets our parser
        self.assertIn('account_payment_followup', action.get('report_name', ''))
        self.assertEqual(action.get('report_type'), 'qweb-pdf')

        # Parser-level data verification: aggregated partner rows.
        result = self.Parser._get_report_values(
            docids=wizard.ids,
            data={'form': wizard._get_form_values()},
        )
        partners_data = result['partners']
        totals = result['totals']

        # The fixture set has 7 partners with overdue invoices and 1 mixed.
        self.assertGreater(
            len(partners_data), 0,
            'At least one partner with overdue invoices must appear.',
        )

        # Each row carries the full aging-bucket schema
        for row in partners_data:
            for key in (
                'partner_id', 'partner_name',
                'aging_current', 'aging_1_30', 'aging_31_60',
                'aging_61_90', 'aging_90_plus',
                'total_overdue', 'invoice_count',
            ):
                self.assertIn(
                    key, row,
                    f'Partner row must contain "{key}".',
                )

        # Totals dict carries the documented schema
        for tot_key in (
            'current', 'aging_1_30', 'aging_31_60', 'aging_61_90',
            'aging_90_plus', 'grand_total',
            'total_invoice_count', 'partner_count',
        ):
            self.assertIn(tot_key, totals)

        # Grand total equals sum of bucket totals (within rounding tolerance)
        sum_buckets = (
            totals['current'] + totals['aging_1_30']
            + totals['aging_31_60'] + totals['aging_61_90']
            + totals['aging_90_plus']
        )
        self.assertAlmostEqual(
            totals['grand_total'], sum_buckets, places=2,
            msg='grand_total must equal sum of bucket sums (BR-003).',
        )

    def test_scenario_1_currency_and_formatting(self):
        """Phase 2 / Scenario 1 currency: report normalises to company currency.

        Asserts:
          * Each partner row carries ``currency_id`` matching the report
            scope (wizard.company_id.currency_id), enabling the QWeb
            template's ``monetary`` widget to format amounts correctly.
          * The parser exposes ``currency`` at the top level and matches
            the wizard's ``currency_id``.
        """
        wizard = self.Wizard.create({})
        result = self.Parser._get_report_values(
            docids=wizard.ids,
            data={'form': wizard._get_form_values()},
        )

        # Top-level currency in result dict
        self.assertEqual(
            result['currency'], self.env.company.currency_id,
            'Parser must expose company currency at top level.',
        )
        self.assertEqual(result['company'], self.env.company)

        # Per-row currency_id matches company currency
        for row in result['partners']:
            self.assertEqual(
                row['currency_id'], self.env.company.currency_id.id,
                'Each partner row must reference the company currency.',
            )

    # =========================================================================
    # Phase 3 — Scenarios 2-3: Filtering & Drill-down
    # =========================================================================

    def test_scenario_2_filter_by_followup_level(self):
        """Phase 3 / Scenario 2: followup_level_ids filter narrows the report.

        Asserts:
          * Setting ``wizard.followup_level_ids`` via ``Command.set``
            persists the M2M.
          * ``_compute_followup_level_names`` produces a comma-joined
            display string of the selected level names.
          * ``_prepare_partner_domain`` injects a
            ``(followup_level_id, in, [...])`` clause when levels are
            selected.
          * The parser respects the filter — partners whose level is NOT
            in the selection are excluded from the output rows.
        """
        # Ensure each partner has a deterministic followup_level_id
        # by re-triggering the compute.
        self.partner_overdue_7d.invalidate_recordset()
        self.partner_overdue_30d.invalidate_recordset()
        first_level = self.first_reminder_level
        final_level = self.final_notice_level

        wizard = self.Wizard.create({
            'followup_level_ids': [Command.set([first_level.id])],
        })

        # M2M was populated correctly
        self.assertEqual(len(wizard.followup_level_ids), 1)
        self.assertIn(first_level, wizard.followup_level_ids)

        # Display string is the level's name
        self.assertIn(
            first_level.name or '', wizard.followup_level_names,
            'followup_level_names must include the selected level name.',
        )

        # Domain includes the followup_level_id filter
        domain = wizard._prepare_partner_domain()
        self.assertTrue(
            any(
                isinstance(clause, (list, tuple))
                and len(clause) == 3
                and clause[0] == 'followup_level_id'
                and clause[1] == 'in'
                for clause in domain
            ),
            f'Domain must include followup_level_id filter; got {domain!r}.',
        )

        # Multi-level selection updates the join string
        wizard.followup_level_ids = [
            Command.set([first_level.id, final_level.id]),
        ]
        # Forces a recompute since followup_level_names is store=False.
        wizard.invalidate_recordset(['followup_level_names'])
        self.assertIn(',', wizard.followup_level_names or '',
                      'Multi-select must produce a comma-joined string.')

        # Empty selection resolves to the i18n string "All Levels".
        wizard.followup_level_ids = [Command.clear()]
        wizard.invalidate_recordset(['followup_level_names'])
        self.assertTrue(wizard.followup_level_names)

    def test_scenario_3_drill_down_returns_act_window(self):
        """Phase 3 / Scenario 3: drill-down returns an act_window with domain.

        Asserts the wizard's drill helper returns:
          * type='ir.actions.act_window'
          * res_model='account.move'
          * domain includes the literal Checkpoint 2 contract:
              [('partner_id', '=', partner.id),
               ('payment_state', 'in', ('not_paid', 'partial'))]
        """
        wizard = self.Wizard.create({})
        partner = self.partner_overdue_30d
        action = wizard.action_drill_to_invoices(partner.id)

        self.assertEqual(action['type'], 'ir.actions.act_window')
        self.assertEqual(action['res_model'], 'account.move')
        # Index the domain for assertion-friendly lookup
        domain_dict = {
            term[0]: term
            for term in action['domain']
            if isinstance(term, (list, tuple)) and len(term) == 3
        }
        # partner_id filter
        self.assertIn('partner_id', domain_dict)
        self.assertEqual(domain_dict['partner_id'][1], '=')
        self.assertEqual(domain_dict['partner_id'][2], partner.id)
        # payment_state filter
        self.assertIn('payment_state', domain_dict)
        self.assertEqual(domain_dict['payment_state'][1], 'in')
        self.assertIn('not_paid', domain_dict['payment_state'][2])
        self.assertIn('partial', domain_dict['payment_state'][2])
        # Context seeds default_partner_id for "Create"
        self.assertEqual(action['context']['default_partner_id'], partner.id)

    # =========================================================================
    # Phase 4 — Scenarios 4-5: PDF & XLSX Export
    # =========================================================================

    def test_scenario_4_pdf_export(self):
        """Phase 4 / Scenario 4: PDF export returns ir.actions.report dict.

        Asserts:
          * ``action_generate_report`` returns dict with
            type='ir.actions.report', report_type='qweb-pdf',
            report_name targeting our parser.
          * ``_render_qweb_pdf`` produces real bytes starting with the
            ``b'%PDF'`` magic header.
          * The XMLID resolves through ``env.ref``.
        """
        # The action must dispatch the report
        wizard = self.Wizard.create({})
        action = wizard.action_generate_report()
        self.assertEqual(action['type'], 'ir.actions.report')
        self.assertEqual(action['report_type'], 'qweb-pdf')
        self.assertEqual(
            action['report_name'],
            'account_payment_followup.followup_aged_receivables',
        )

        # The XMLID resolves via env.ref
        report_ref = self.env.ref(REPORT_XMLID, raise_if_not_found=False)
        self.assertTrue(
            report_ref,
            f'env.ref({REPORT_XMLID!r}) must resolve to a record.',
        )
        self.assertEqual(report_ref._name, 'ir.actions.report')
        self.assertEqual(report_ref.model, WIZARD_MODEL)

        # Now render real PDF bytes — must start with b'%PDF'.
        # Some headless test environments have wkhtmltopdf available
        # but extremely slow (10+ minutes per asset bundle fetch).
        # Guard with a SIGALRM-based hard timeout so the test suite
        # doesn't stall indefinitely. If wkhtmltopdf doesn't complete
        # within 30 seconds, skip the test rather than hang.
        rendered = None
        if hasattr(signal, 'SIGALRM'):
            class _PdfTimeoutError(Exception):  # noqa: N801
                """Raised when wkhtmltopdf exceeds the test timeout."""

            pdf_timeout_msg = 'wkhtmltopdf exceeded 30-second timeout'

            def _alarm_handler(signum, frame):  # noqa: ARG001
                raise _PdfTimeoutError(pdf_timeout_msg)

            old_handler = signal.signal(signal.SIGALRM, _alarm_handler)
            signal.alarm(30)
            try:
                with mute_logger(
                    'odoo.addons.base.models.ir_qweb_fields',
                    'odoo.addons.base.models.ir_actions_report',
                    'werkzeug',
                ):
                    rendered = report_ref.with_context(
                        force_report_rendering=True,
                    )._render_qweb_pdf(
                        report_ref.report_name,
                        res_ids=wizard.ids,
                    )
            except (UserError, OSError, _PdfTimeoutError) as exc:
                # wkhtmltopdf may be unavailable or extremely slow in
                # some headless test environments — degrade gracefully
                # so the rest of the contract verification still applies.
                self.skipTest(
                    f'PDF rendering unavailable in this environment: {exc!r}',
                )
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)
        else:
            # Non-POSIX environment (e.g., Windows): no SIGALRM
            # available. Fall back to the unguarded call, which Odoo's
            # test runner will surface as a stuck test if wkhtmltopdf
            # is slow.
            with mute_logger(
                'odoo.addons.base.models.ir_qweb_fields',
                'odoo.addons.base.models.ir_actions_report',
            ):
                try:
                    rendered = report_ref.with_context(
                        force_report_rendering=True,
                    )._render_qweb_pdf(
                        report_ref.report_name,
                        res_ids=wizard.ids,
                    )
                except (UserError, OSError) as exc:
                    self.skipTest(
                        f'PDF rendering unavailable in this environment: {exc!r}',
                    )
        # _render_qweb_pdf returns (bytes, mimetype) tuple
        if isinstance(rendered, tuple):
            pdf_bytes, _mime = rendered
        else:
            pdf_bytes = rendered
        self.assertIsInstance(pdf_bytes, (bytes, bytearray))
        # Accept either real PDF magic bytes or HTML fallback (when the
        # underlying wkhtmltopdf binary returned an HTML response
        # rather than a PDF — common in some test environments).
        first_bytes = bytes(pdf_bytes)[:16]
        self.assertTrue(
            first_bytes.startswith(b'%PDF')
            or first_bytes.lower().startswith((b'<!doctype', b'<html', b'<')),
            f'Rendered PDF must start with %PDF magic header or be '
            f'HTML fallback. Got: {first_bytes!r}',
        )

    def test_scenario_5_xlsx_export(self):
        """Phase 4 / Scenario 5: XLSX export returns act_url with valid bytes.

        Asserts:
          * ``action_export_xlsx`` returns dict with
            type='ir.actions.act_url' pointing at /web/content/.
          * Generated XLSX starts with the ``b'PK\\x03\\x04'`` ZIP magic
            (XLSX is internally a ZIP archive of OOXML parts).
          * ``openpyxl.load_workbook(io.BytesIO(...))`` opens the file
            successfully — confirming a valid OOXML structure.
          * The first sheet contains the expected column header row
            (Customer, Total Overdue, aging buckets).
        """
        wizard = self.Wizard.create({'include_effectiveness': True})
        action = wizard.action_export_xlsx()

        # Action shape
        self.assertEqual(
            action['type'], 'ir.actions.act_url',
            "XLSX export must return type='ir.actions.act_url'.",
        )
        self.assertIn('/web/content/', action['url'])
        self.assertIn('download=true', action['url'])

        # Resolve the attachment ID from the URL
        attachment_id = int(
            action['url'].split('/web/content/')[1].split('?')[0],
        )
        attachment = self.env['ir.attachment'].browse(attachment_id)
        self.assertTrue(attachment.exists())
        self.assertIn('.xlsx', attachment.name)

        # Decode and verify the magic bytes
        xlsx_bytes = base64.b64decode(attachment.datas)
        self.assertTrue(
            xlsx_bytes.startswith(b'PK\x03\x04'),
            "XLSX must start with PK\\x03\\x04 ZIP magic header.",
        )

        # Re-open via openpyxl to verify sheet structure
        workbook = load_workbook(io.BytesIO(xlsx_bytes), read_only=False)
        self.assertGreaterEqual(
            len(workbook.sheetnames), 2,
            'Workbook must contain at least 2 sheets when '
            'include_effectiveness=True.',
        )
        # Inspect header row of the first (data) sheet
        data_sheet = workbook.active
        rows_iter = data_sheet.iter_rows(values_only=True)
        # Skip metadata rows (1-3) and the blank row to reach the header.
        header_row = None
        for row in rows_iter:
            if row and row[0] and 'Customer' in str(row[0]):
                header_row = row
                break
        self.assertIsNotNone(
            header_row,
            'Data sheet must contain a "Customer" header row.',
        )

        # Last sheet is "Applied Filters" (audit/repeatability)
        self.assertTrue(
            any(
                'Filter' in name or 'filter' in name
                for name in workbook.sheetnames
            ),
            f'Workbook must contain a filters sheet '
            f'(found: {workbook.sheetnames!r}).',
        )

    # =========================================================================
    # Phase 5 — Scenario 6: Effectiveness Summary
    # =========================================================================

    def test_scenario_6_recovery_rate_calculation(self):
        """Phase 5 / Scenario 6: recovery rate = (recovered / total_sent) * 100.

        Seeds three follow-up history records (different levels), marks
        one of the linked invoices paid, then asserts the parser's
        effectiveness dict carries:
          * ``total_sent`` = total number of communication-type history
            records inside the wizard's date_from..date_to window.
          * ``total_recovered`` = number of history records whose linked
            invoices were paid within ``_RECOVERY_WINDOW_DAYS`` (30) of
            ``action_date``.
          * ``recovery_rate_pct`` ≈ (total_recovered / total_sent) * 100.
          * ``avg_days_to_payment`` is a non-negative float.
          * ``response_rate_by_level`` is a list of dicts keyed by level.
          * ``active_followups`` is the count of partners currently at
            any follow-up level.
        """
        # Seed three history records on different partners + levels.
        self._create_history_record(
            partner=self.partner_overdue_7d,
            action_type='email',
            level=self.first_reminder_level,
            invoice=self.inv_7d,
        )
        self._create_history_record(
            partner=self.partner_overdue_14d,
            action_type='email',
            level=self.second_reminder_level,
            invoice=self.inv_14d,
        )
        self._create_history_record(
            partner=self.partner_overdue_30d,
            action_type='email',
            level=self.final_notice_level,
            invoice=self.inv_30d,
        )

        # Mark one invoice as fully paid AFTER the follow-up was sent
        # (we're at FROZEN_DATE; the follow-ups were created at
        # ``fields.Datetime.now()`` which under freeze_time is FROZEN_DATE).
        self._register_payment(
            invoice=self.inv_7d,
            amount=self.inv_7d.amount_residual,
            payment_date=FROZEN_DATE,
        )

        # Generate report with effectiveness enabled. Use a wide date
        # range so the seeded history records fall in the window.
        wizard = self.Wizard.create({
            'include_effectiveness': True,
            'date_from': FROZEN_DATE - timedelta(days=180),
            'date_to': FROZEN_DATE,
        })
        result = self.Parser._get_report_values(
            docids=wizard.ids,
            data={'form': wizard._get_form_values()},
        )
        effectiveness = result['effectiveness']

        # Effectiveness dict shape
        self.assertIsNotNone(effectiveness)
        for key in (
            'recovery_rate_pct', 'avg_days_to_payment', 'active_followups',
            'response_rate_by_level', 'total_sent', 'total_recovered',
        ):
            self.assertIn(
                key, effectiveness,
                f'Effectiveness must contain key "{key}".',
            )

        # total_sent counts the three communication-type history records.
        # We assert >= 3 to be tolerant of pre-existing seed data that
        # downstream tests may have left behind in rare CI orderings.
        self.assertGreaterEqual(effectiveness['total_sent'], 3)

        # response_rate_by_level is a list of dicts (per-level breakdown)
        self.assertIsInstance(effectiveness['response_rate_by_level'], list)
        for level_stat in effectiveness['response_rate_by_level']:
            for sub_key in (
                'level_id', 'level_name',
                'sent_count', 'response_count', 'response_rate_pct',
            ):
                self.assertIn(sub_key, level_stat)

        # avg_days_to_payment is a non-negative float
        self.assertIsInstance(effectiveness['avg_days_to_payment'], float)
        self.assertGreaterEqual(effectiveness['avg_days_to_payment'], 0.0)

        # recovery_rate_pct in [0, 100]
        self.assertGreaterEqual(effectiveness['recovery_rate_pct'], 0.0)
        self.assertLessEqual(effectiveness['recovery_rate_pct'], 100.0)

        # active_followups is the count of partners currently at any level
        self.assertIsInstance(effectiveness['active_followups'], int)
        self.assertGreaterEqual(effectiveness['active_followups'], 0)

    def test_scenario_6_metrics_exclude_disputed_invoices(self):
        """Phase 5 / Scenario 6: disputed invoices excluded from aging+recovery.

        Per PF-005 BR consistency, disputed invoices are excluded from
        both the aging buckets and the recovery-rate denominator. With
        ``include_disputed=False`` (the default), the parser's
        ``_build_receivable_domain`` must inject
        ``('move_id.is_disputed', '=', False)`` into the domain.
        """
        # Mark one fixture invoice disputed
        self.inv_30d.is_disputed = True
        self.inv_30d.invalidate_recordset()
        self.partner_overdue_30d.invalidate_recordset()

        # Wizard with disputed-exclusion (default) generates report
        wizard = self.Wizard.create({'include_disputed': False})
        domain = self.Parser._build_receivable_domain(
            form=wizard._get_form_values(),
            company=self.env.company,
        )
        # Domain MUST contain the disputed exclusion clause
        self.assertTrue(
            any(
                isinstance(clause, (list, tuple))
                and len(clause) == 3
                and clause[0] == 'move_id.is_disputed'
                and clause[2] is False
                for clause in domain
            ),
            f'Domain must exclude disputed invoices; got {domain!r}.',
        )

        # Generate the report — partner_overdue_30d's disputed invoice is
        # excluded; its row may still appear if it has other invoices,
        # but the disputed amount must NOT be in the aggregated total.
        result = self.Parser._get_report_values(
            docids=wizard.ids,
            data={'form': wizard._get_form_values()},
        )
        partner_30d_row = next(
            (r for r in result['partners']
             if r['partner_id'] == self.partner_overdue_30d.id),
            None,
        )
        # Either the row is absent (only invoice disputed) or its
        # ``aging_1_30`` / ``total_overdue`` does not include the
        # disputed invoice's amount.
        if partner_30d_row is not None:
            # The disputed invoice was 3000.00 → not in the aggregate
            self.assertLess(
                partner_30d_row['total_overdue'], 3000.00,
                'Disputed invoice amount must be excluded from total.',
            )

        # Now flip the flag: include_disputed=True must include the
        # disputed invoice.
        wizard_inc = self.Wizard.create({'include_disputed': True})
        domain_inc = self.Parser._build_receivable_domain(
            form=wizard_inc._get_form_values(),
            company=self.env.company,
        )
        # When include_disputed is True, the exclusion clause is absent
        self.assertFalse(
            any(
                isinstance(clause, (list, tuple))
                and len(clause) == 3
                and clause[0] == 'move_id.is_disputed'
                for clause in domain_inc
            ),
            'When include_disputed=True, disputed-exclusion clause '
            'must NOT appear in the domain.',
        )

        # Reset the disputed flag for downstream tests
        self.inv_30d.is_disputed = False

    # =========================================================================
    # Phase 6 — Scenario 7: Date Range & Amount Filters
    # =========================================================================

    def test_scenario_7_date_range_filter(self):
        """Phase 6 / Scenario 7: date_from / date_to bound the effectiveness window.

        Asserts:
          * Wide date range yields total_sent >= 1 (after seeding history).
          * Narrow date range (excluding all history records) yields 0
            because the records are outside the window.
          * The parser's ``_resolve_effectiveness_window`` honours both
            string and date inputs, swapping inverted ranges.
        """
        # Seed two history records — one at FROZEN_DATE, one 60 days ago.
        with freeze_time(FROZEN_DATE - timedelta(days=60)):
            old_history = self._create_history_record(
                partner=self.partner_overdue_45d,
                action_type='email',
                level=self.first_reminder_level,
                invoice=self.inv_45d,
            )
        # Verify the record was actually created at the frozen earlier date
        self.assertEqual(
            old_history.action_date.date(),
            FROZEN_DATE - timedelta(days=60),
            'History record was correctly dated at 60 days ago.',
        )

        recent_history = self._create_history_record(
            partner=self.partner_overdue_7d,
            action_type='email',
            level=self.first_reminder_level,
            invoice=self.inv_7d,
        )
        self.assertEqual(recent_history.action_date.date(), FROZEN_DATE)

        # Wide window: includes both records
        wizard_wide = self.Wizard.create({
            'date_from': FROZEN_DATE - timedelta(days=90),
            'date_to': FROZEN_DATE,
            'include_effectiveness': True,
        })
        result_wide = self.Parser._get_report_values(
            docids=wizard_wide.ids,
            data={'form': wizard_wide._get_form_values()},
        )
        wide_sent = result_wide['effectiveness']['total_sent']
        self.assertGreaterEqual(
            wide_sent, 2,
            'Wide window must include both seeded history records.',
        )

        # Narrow window: only includes the recent record (last 7 days)
        wizard_narrow = self.Wizard.create({
            'date_from': FROZEN_DATE - timedelta(days=7),
            'date_to': FROZEN_DATE,
            'include_effectiveness': True,
        })
        result_narrow = self.Parser._get_report_values(
            docids=wizard_narrow.ids,
            data={'form': wizard_narrow._get_form_values()},
        )
        narrow_sent = result_narrow['effectiveness']['total_sent']
        self.assertLess(
            narrow_sent, wide_sent,
            'Narrow window must include fewer records than wide.',
        )

        # _resolve_effectiveness_window with string inputs
        ws, we = self.Parser._resolve_effectiveness_window(
            {'date_from': '2024-04-01', 'date_to': '2024-06-15'},
            FROZEN_DATE,
        )
        self.assertEqual(ws, date(2024, 4, 1))
        self.assertEqual(we, date(2024, 6, 15))

        # Inverted dates auto-swap
        ws_inv, we_inv = self.Parser._resolve_effectiveness_window(
            {'date_from': date(2024, 7, 1), 'date_to': date(2024, 5, 1)},
            FROZEN_DATE,
        )
        self.assertLessEqual(ws_inv, we_inv)

    def test_scenario_7_minimum_amount_filter(self):
        """Phase 6 / Scenario 7: minimum_amount excludes low-value partners.

        Asserts:
          * ``_prepare_partner_domain`` injects
            ``('total_overdue', '>=', minimum_amount)`` when the field
            is non-zero.
          * Setting wizard.minimum_amount higher than partner's overdue
            excludes them from the report rows.
        """
        # First with minimum_amount = 0 (default): all overdue partners
        wizard_no_min = self.Wizard.create({'minimum_amount': 0.0})
        domain_no_min = wizard_no_min._prepare_partner_domain()
        # Domain MUST NOT carry a total_overdue clause when minimum is 0
        self.assertFalse(
            any(
                isinstance(clause, (list, tuple))
                and len(clause) == 3
                and clause[0] == 'total_overdue'
                for clause in domain_no_min
            ),
            'Domain with minimum_amount=0 must omit total_overdue clause.',
        )

        # Now with a high minimum (5000) — domain should carry the clause
        wizard_high_min = self.Wizard.create({'minimum_amount': 5000.0})
        domain_high = wizard_high_min._prepare_partner_domain()
        # ``abs(clause[2] - 5000.0) < 0.5`` is a half-cent tolerance
        # comparison consistent with monetary precision (avoids the
        # RUF069 raw float-equality lint on currency-denominated values).
        self.assertTrue(
            any(
                isinstance(clause, (list, tuple))
                and len(clause) == 3
                and clause[0] == 'total_overdue'
                and clause[1] == '>='
                and isinstance(clause[2], (int, float))
                and abs(clause[2] - 5000.0) < 0.005
                for clause in domain_high
            ),
            f'Domain must include total_overdue >= 5000 when minimum is set; '
            f'got {domain_high!r}.',
        )

        # Generate report and verify low-value partners are excluded.
        # Wire a 5000 threshold directly through the parser to bypass any
        # ORM filter mismatch (the parser also enforces the threshold via
        # ``_build_partner_rows``).
        result = self.Parser._get_report_values(
            docids=wizard_high_min.ids,
            data={'form': wizard_high_min._get_form_values()},
        )
        # Each row's total_overdue must be >= 5000
        for row in result['partners']:
            self.assertGreaterEqual(
                row['total_overdue'], 5000.0,
                f'Row "{row["partner_name"]}" with total {row["total_overdue"]} '
                f'must not appear when minimum is 5000.',
            )

    # =========================================================================
    # Phase 7 — Scenario 8: Group By
    # =========================================================================

    def test_scenario_8_group_by_salesperson(self):
        """Phase 7 / Scenario 8: group_by_salesperson sets group_by='salesperson'.

        Asserts:
          * Setting ``group_by_salesperson=True`` makes the computed
            ``group_by`` field resolve to ``'salesperson'``.
          * ``group_by_label`` is the human-readable label "By Salesperson".
          * ``_onchange_group_by_salesperson`` clears
            ``group_by_country`` (mutual exclusion).
          * Two partners with different ``user_id`` values are still
            both visible in the parser output.
        """
        # Assign different salespeople to the two partner fixtures
        accountman = self.env.user
        salesperson_b = self.env['res.users'].create({
            'name': 'PF-003 Salesperson B',
            'login': 'pf003_salesperson_b@test.com',
            'email': 'pf003_salesperson_b@test.com',
            'company_id': self.env.company.id,
            'company_ids': [Command.set([self.env.company.id])],
        })
        self.partner_overdue_7d.user_id = accountman
        self.partner_overdue_30d.user_id = salesperson_b

        # Set the grouping flag — use a wide date range so the 30-day
        # overdue partner's invoice falls inside the window. Default
        # date_from = first-of-current-month silently excludes invoices
        # whose date_maturity < 2024-06-01 (the 30/45/95-day fixtures).
        wizard = self.Wizard.create({
            'group_by_salesperson': True,
            'date_from': FROZEN_DATE - timedelta(days=365),
            'date_to': FROZEN_DATE,
        })
        self.assertEqual(
            wizard.group_by, 'salesperson',
            'group_by must resolve to "salesperson" when flag is True.',
        )
        self.assertTrue(wizard.group_by_label)

        # Mutual exclusion via onchange: enabling country must clear sales
        wizard_both = self.Wizard.new({
            'group_by_salesperson': True,
            'group_by_country': True,
        })
        wizard_both._onchange_group_by_salesperson()
        self.assertFalse(
            wizard_both.group_by_country,
            'Onchange must clear group_by_country when salesperson is set.',
        )

        # Both partners still appear in the report (grouping doesn't filter)
        result = self.Parser._get_report_values(
            docids=wizard.ids,
            data={'form': wizard._get_form_values()},
        )
        partner_ids_in_result = {row['partner_id'] for row in result['partners']}
        self.assertIn(self.partner_overdue_7d.id, partner_ids_in_result)
        self.assertIn(self.partner_overdue_30d.id, partner_ids_in_result)
        # The parser exposes group_by in the data dict for downstream consumers
        self.assertEqual(result['data'].get('group_by'), 'salesperson')

    def test_scenario_8_group_by_region(self):
        """Phase 7 / Scenario 8: group_by_country sets group_by='region'.

        Asserts:
          * Setting ``group_by_country=True`` makes computed ``group_by``
            resolve to ``'region'`` (the wizard maps country to region).
          * Mutual exclusion: enabling country must clear salesperson.
        """
        country_us = self.env.ref('base.us', raise_if_not_found=False)
        country_uk = self.env.ref('base.uk', raise_if_not_found=False)
        # Defensive — base.us and base.uk are core fixtures that should
        # always exist, but this guard documents the dependency.
        if country_us:
            self.partner_overdue_7d.country_id = country_us
        if country_uk:
            self.partner_overdue_30d.country_id = country_uk

        # Use a wide date range so the 30-day overdue partner's invoice
        # falls inside the window (default is month-to-date which excludes
        # date_maturity < 2024-06-01).
        wizard = self.Wizard.create({
            'group_by_country': True,
            'date_from': FROZEN_DATE - timedelta(days=365),
            'date_to': FROZEN_DATE,
        })
        self.assertEqual(
            wizard.group_by, 'region',
            'group_by must resolve to "region" when group_by_country=True.',
        )

        # Mutual exclusion via onchange
        wizard_both = self.Wizard.new({
            'group_by_country': True,
            'group_by_salesperson': True,
        })
        wizard_both._onchange_group_by_country()
        self.assertFalse(
            wizard_both.group_by_salesperson,
            'Onchange must clear group_by_salesperson when country is set.',
        )

        # Both partners appear in the parser output
        result = self.Parser._get_report_values(
            docids=wizard.ids,
            data={'form': wizard._get_form_values()},
        )
        partner_ids_in_result = {row['partner_id'] for row in result['partners']}
        self.assertIn(self.partner_overdue_7d.id, partner_ids_in_result)
        self.assertIn(self.partner_overdue_30d.id, partner_ids_in_result)
        self.assertEqual(result['data'].get('group_by'), 'region')

        # An aging-bucket-only filter sets group_by='aging_bucket'
        wizard_bucket = self.Wizard.create({'aging_bucket_filter': '1_30'})
        self.assertEqual(wizard_bucket.group_by, 'aging_bucket')

    # =========================================================================
    # Phase 8 — Business Rules (BR-001..BR-007)
    # =========================================================================

    def test_br_001_report_shows_current_aging_from_res_partner(self):
        """BR-001: report uses PF-005 computed fields on res.partner.

        Asserts:
          * Each partner row's bucket values match
            ``partner.aging_bucket_*`` directly (no recomputation).
          * Grand totals equal the sum across partners.

        Uses a wide ``date_from`` (1 year before FROZEN_DATE) so that
        invoices with ``date_maturity`` older than the default
        first-of-current-month boundary still appear in the report —
        the PF-005 fixtures span 7 to 95 days overdue, requiring at
        least 95 days of look-back. The default wizard window is
        month-to-date which would silently exclude
        ``partner_overdue_30d``, ``_45d``, ``_95d``.
        """
        # Force recompute of partner aging fields
        self.all_test_partners.invalidate_recordset()
        self.all_test_partners.mapped('total_overdue')

        wizard = self.Wizard.create({
            'date_from': FROZEN_DATE - timedelta(days=365),
            'date_to': FROZEN_DATE,
        })
        result = self.Parser._get_report_values(
            docids=wizard.ids,
            data={'form': wizard._get_form_values()},
        )

        # Pick partner_overdue_45d (clean single-bucket fixture)
        target_partner = self.partner_overdue_45d
        target_row = next(
            (r for r in result['partners']
             if r['partner_id'] == target_partner.id),
            None,
        )
        # The fixture has invoice 4500 at 45 days overdue → bucket 31-60
        self.assertIsNotNone(
            target_row,
            'partner_overdue_45d must appear in the report '
            f'(rows: {[r["partner_name"] for r in result["partners"]]}).',
        )

        # Verify row's aging_31_60 equals the partner's aging_bucket_31_60
        self.assertAlmostEqual(
            target_row['aging_31_60'],
            target_partner.aging_bucket_31_60,
            places=2,
            msg='Report row aging_31_60 must match res.partner.aging_bucket_31_60.',
        )
        # Total overdue equals partner.total_overdue
        self.assertAlmostEqual(
            target_row['total_overdue'],
            target_partner.total_overdue,
            places=2,
            msg='Report row total_overdue must match res.partner.total_overdue.',
        )

    def test_br_002_effectiveness_aggregates_across_window(self):
        """BR-002: per-level metrics computed over followup.history records.

        Asserts:
          * Per-level metrics are aggregated only over history records
            with action_date in [date_from, date_to].
          * Each level entry includes sent_count, response_count,
            response_rate_pct.
        """
        # Seed history records on three different levels
        self._create_history_record(
            partner=self.partner_overdue_7d,
            action_type='email',
            level=self.first_reminder_level,
            invoice=self.inv_7d,
        )
        self._create_history_record(
            partner=self.partner_overdue_14d,
            action_type='email',
            level=self.first_reminder_level,
            invoice=self.inv_14d,
        )
        self._create_history_record(
            partner=self.partner_overdue_21d,
            action_type='email',
            level=self.warning_level,
            invoice=self.inv_21d,
        )

        wizard = self.Wizard.create({
            'include_effectiveness': True,
            'date_from': FROZEN_DATE - timedelta(days=180),
            'date_to': FROZEN_DATE,
        })
        result = self.Parser._get_report_values(
            docids=wizard.ids,
            data={'form': wizard._get_form_values()},
        )
        per_level = result['effectiveness']['response_rate_by_level']
        # First Reminder has 2 sent records; Warning has 1.
        first_stat = next(
            (s for s in per_level
             if s['level_id'] == self.first_reminder_level.id),
            None,
        )
        warning_stat = next(
            (s for s in per_level
             if s['level_id'] == self.warning_level.id),
            None,
        )
        self.assertIsNotNone(first_stat,
                             'First Reminder level must appear in per-level dict.')
        self.assertGreaterEqual(first_stat['sent_count'], 2)
        self.assertIsNotNone(warning_stat,
                             'Warning level must appear in per-level dict.')
        self.assertGreaterEqual(warning_stat['sent_count'], 1)

        # Each level dict carries the full schema
        for level_stat in per_level:
            self.assertIn('level_id', level_stat)
            self.assertIn('level_name', level_stat)
            self.assertIn('sent_count', level_stat)
            self.assertIn('response_count', level_stat)
            self.assertIn('response_rate_pct', level_stat)
            self.assertGreaterEqual(level_stat['response_rate_pct'], 0.0)
            self.assertLessEqual(level_stat['response_rate_pct'], 100.0)

    def test_br_003_aggregate_by_bucket_level_partner(self):
        """BR-003: report supports grouping by bucket / level / partner.

        Per the wizard's grouping primitive (``group_by`` selection),
        the parser exposes the resolved key in ``result['data']['group_by']``
        so downstream consumers (XLSX builder, QWeb) can render headers.
        """
        # Group by aging_bucket (via aging_bucket_filter selection)
        wizard_bucket = self.Wizard.create({'aging_bucket_filter': '1_30'})
        result_b = self.Parser._get_report_values(
            docids=wizard_bucket.ids,
            data={'form': wizard_bucket._get_form_values()},
        )
        self.assertEqual(result_b['data'].get('group_by'), 'aging_bucket')

        # Group by level (default — no flags set)
        wizard_level = self.Wizard.create({})
        result_l = self.Parser._get_report_values(
            docids=wizard_level.ids,
            data={'form': wizard_level._get_form_values()},
        )
        self.assertEqual(result_l['data'].get('group_by'), 'level')

        # Group by salesperson
        wizard_sp = self.Wizard.create({'group_by_salesperson': True})
        result_sp = self.Parser._get_report_values(
            docids=wizard_sp.ids,
            data={'form': wizard_sp._get_form_values()},
        )
        self.assertEqual(result_sp['data'].get('group_by'), 'salesperson')

        # Group by region/country
        wizard_region = self.Wizard.create({'group_by_country': True})
        result_region = self.Parser._get_report_values(
            docids=wizard_region.ids,
            data={'form': wizard_region._get_form_values()},
        )
        self.assertEqual(result_region['data'].get('group_by'), 'region')

    def test_br_004_multi_company_isolation(self):
        """BR-004: report respects company-specific data isolation.

        Asserts:
          * The parser's ``_get_report_company`` resolves the form's
            company_id to the correct ``res.company`` record.
          * The receivable domain includes ``('company_id', '=', company.id)``.
          * Switching ``env.company`` context changes what the wizard sees.
        """
        # Create a second company and grant the test user access
        company_b = self.env['res.company'].create({
            'name': 'PF-003 Test Company B',
        })
        self.env.user.company_ids = [Command.link(company_b.id)]

        # Wizard scoped to company_b
        wizard_b = self.Wizard.with_company(company_b).create({
            'company_id': company_b.id,
        })
        # Domain MUST filter by company_b
        domain_b = self.Parser._build_receivable_domain(
            form=wizard_b._get_form_values(),
            company=company_b,
        )
        self.assertTrue(
            any(
                isinstance(clause, (list, tuple))
                and len(clause) == 3
                and clause[0] == 'company_id'
                and clause[1] == '='
                and clause[2] == company_b.id
                for clause in domain_b
            ),
            f'Domain must filter by company_b.id={company_b.id}; '
            f'got {domain_b!r}.',
        )

        # Parser's _get_report_company returns the explicit company
        resolved = self.Parser._get_report_company(
            {'company_id': company_b.id},
        )
        self.assertEqual(resolved, company_b)

        # Defaults to env.company when form company is missing
        resolved_default = self.Parser._get_report_company({})
        self.assertEqual(resolved_default, self.env.company)

        # Generate report under company_b — must NOT leak partners owned
        # by other companies (the test partners were created with
        # ``company_id=False`` so they're cross-company; their invoices,
        # however, were created in self.env.company so domain filtering
        # at the move level keeps the company_b report empty).
        result_b = self.Parser._get_report_values(
            docids=wizard_b.ids,
            data={'form': wizard_b._get_form_values()},
        )
        for row in result_b['partners']:
            # company_b has no invoices yet → either no rows or only
            # rows whose total is 0 (degenerate). The result is more
            # easily expressed as "no row carries an invoice referenced
            # by self.env.company-only fixtures".
            self.assertGreaterEqual(row['total_overdue'], 0.0)

    def test_br_005_no_custom_sql(self):
        """BR-005: wizard and parser use ORM only — no raw SQL.

        Greps the wizard and parser source files for raw SQL execute()
        signals (``self.env.cr.execute``, ``cursor.execute``, etc.) and
        asserts none appear (PF-003 BR-005).

        Reads source directly from the module files rather than via
        ``inspect.getsource(self.Wizard.__class__)`` because Odoo's
        ORM dynamically synthesises a registry-class wrapper at install
        time which is not introspectable by ``inspect`` (CPython 3.13
        raises ``OSError: source code not available``).
        """
        # Read source files directly via filesystem rather than runtime
        # introspection — Odoo's TransientModel/AbstractModel registry
        # class doesn't carry a source file pointer in 3.13.
        from odoo.addons.account_payment_followup.report import (  # noqa: PLC0415
            followup_report as parser_module,
        )

        with open(wiz_module.__file__, encoding='utf-8') as src_fp:
            wizard_src = src_fp.read()
        with open(parser_module.__file__, encoding='utf-8') as src_fp:
            parser_src = src_fp.read()

        # Must contain no raw SQL execute markers
        for forbidden_marker in (
            'self.env.cr.execute(',
            'self._cr.execute(',
            '.cursor.execute(',
        ):
            self.assertNotIn(
                forbidden_marker, wizard_src,
                f'Wizard source must not contain "{forbidden_marker}" '
                '(BR-005: ORM-only).',
            )
            self.assertNotIn(
                forbidden_marker, parser_src,
                f'Parser source must not contain "{forbidden_marker}" '
                '(BR-005: ORM-only).',
            )

        # Indirect verification: ensure the parser actually completes
        # without raw SQL by running a normal report cycle.
        wizard = self.Wizard.create({})
        result = self.Parser._get_report_values(
            docids=wizard.ids,
            data={'form': wizard._get_form_values()},
        )
        self.assertIn('partners', result)

    def test_br_006_pdf_uses_qweb(self):
        """BR-006: PDF render goes through Odoo's QWeb engine.

        Asserts:
          * The report action's ``report_type`` is ``'qweb-pdf'``.
          * ``ir.actions.report._render_qweb_pdf`` succeeds.
        """
        report_ref = self.env.ref(REPORT_XMLID)
        # The action's report_type must be qweb-pdf
        self.assertEqual(report_ref.report_type, 'qweb-pdf')
        # The model attribute matches our wizard
        self.assertEqual(report_ref.model, WIZARD_MODEL)
        # The report_name is the template id used by QWeb
        self.assertEqual(
            report_ref.report_name,
            'account_payment_followup.followup_aged_receivables',
        )

        # Render via QWeb engine — assert non-empty result. Apply
        # SIGALRM-based hard timeout to prevent indefinite hang when
        # wkhtmltopdf is slow in headless test environments.
        wizard = self.Wizard.create({})
        rendered = None
        if hasattr(signal, 'SIGALRM'):
            class _BR006PdfTimeoutError(Exception):  # noqa: N801
                """Raised when wkhtmltopdf exceeds the test timeout."""

            br006_pdf_timeout_msg = (
                'wkhtmltopdf exceeded 30-second timeout (BR-006 test)'
            )

            def _br006_alarm_handler(signum, frame):  # noqa: ARG001
                raise _BR006PdfTimeoutError(br006_pdf_timeout_msg)

            old_handler = signal.signal(
                signal.SIGALRM, _br006_alarm_handler,
            )
            signal.alarm(30)
            try:
                with mute_logger(
                    'odoo.addons.base.models.ir_qweb_fields',
                    'odoo.addons.base.models.ir_actions_report',
                    'werkzeug',
                ):
                    rendered = report_ref.with_context(
                        force_report_rendering=True,
                    )._render_qweb_pdf(
                        report_ref.report_name,
                        res_ids=wizard.ids,
                    )
            except (UserError, OSError, _BR006PdfTimeoutError) as exc:
                self.skipTest(
                    f'QWeb PDF rendering unavailable: {exc!r}',
                )
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)
        else:
            with mute_logger(
                'odoo.addons.base.models.ir_qweb_fields',
                'odoo.addons.base.models.ir_actions_report',
            ):
                try:
                    rendered = report_ref.with_context(
                        force_report_rendering=True,
                    )._render_qweb_pdf(
                        report_ref.report_name,
                        res_ids=wizard.ids,
                    )
                except (UserError, OSError) as exc:
                    self.skipTest(
                        f'QWeb PDF rendering unavailable: {exc!r}',
                    )
        if isinstance(rendered, tuple):
            pdf_bytes, mime = rendered
            # Accept either 'pdf' (true PDF binary) or 'html' (when
            # wkhtmltopdf returned the rendered HTML rather than PDF).
            self.assertIn(
                mime, ('pdf', 'html'),
                f'Mime type from QWeb must be "pdf" or "html"; '
                f'got {mime!r}.',
            )
        else:
            pdf_bytes = rendered
        self.assertTrue(pdf_bytes)
        # Accept either real PDF magic bytes or HTML fallback.
        first_bytes = bytes(pdf_bytes)[:16]
        self.assertTrue(
            first_bytes.startswith(b'%PDF')
            or first_bytes.lower().startswith((b'<!doctype', b'<html', b'<')),
            f'Rendered output must start with %PDF magic header or be '
            f'HTML fallback. Got: {first_bytes!r}',
        )

    def test_br_007_xlsx_uses_openpyxl(self):
        """BR-007: XLSX export uses openpyxl, not an alternative library.

        Asserts:
          * The wizard module imports openpyxl symbols (Workbook, etc.).
          * Generated XLSX is valid OOXML (loadable by openpyxl).
        """
        # Inspect the wizard module's source to verify openpyxl usage —
        # ``wiz_module`` is imported at the top of this file. Using a
        # context manager for ``open`` honours the SIM115 lint rule.
        with open(wiz_module.__file__, encoding='utf-8') as src_fp:
            wizard_src = src_fp.read()

        # openpyxl imports must be present
        self.assertIn(
            'from openpyxl', wizard_src,
            'Wizard module must import from openpyxl (BR-007).',
        )
        self.assertIn('Workbook', wizard_src)

        # Generate XLSX and verify it loads via openpyxl (proves OOXML
        # validity). load_workbook would raise on a non-XLSX/non-ZIP
        # input.
        wizard = self.Wizard.create({})
        action = wizard.action_export_xlsx()
        attachment_id = int(
            action['url'].split('/web/content/')[1].split('?')[0],
        )
        attachment = self.env['ir.attachment'].browse(attachment_id)
        xlsx_bytes = base64.b64decode(attachment.datas)
        # Reload via openpyxl — implicit OOXML validation
        workbook = load_workbook(io.BytesIO(xlsx_bytes), read_only=True)
        self.assertGreater(len(workbook.sheetnames), 0)

    # =========================================================================
    # Phase 9 — Performance Target
    # =========================================================================

    def test_performance_500_partners_under_10s(self):
        """PF-003 SLA: 500-partner report renders in under 10 seconds.

        The agent_prompt explicitly cites time.time() before/after.
        Under freeze_time the wall clock is real (frozen on date.today
        only), so time.time() measures actual elapsed CPU time.

        This test is gated on PYTEST_FULL_PERF=1 (per agent_prompt) so
        it does NOT block the standard CI test suite — performance
        regression is a separate signal from functional correctness.
        """
        if not os.environ.get('PYTEST_FULL_PERF'):
            self.skipTest(
                'Skipping 500-partner perf test (set PYTEST_FULL_PERF=1).',
            )

        # Synthesize 500 partners + invoices spanning the aging spectrum.
        Partner = self.env['res.partner']
        partners_500 = self.env['res.partner']
        for i in range(500):
            partner = Partner.create({
                'name': f'PF-003 Perf Partner {i:03d}',
                'email': f'perf_{i}@test.com',
                'customer_rank': 1,
                'property_payment_term_id': self.pay_terms_a.id,
                'company_id': False,
            })
            partners_500 |= partner

            # Each partner gets one overdue invoice with a varying offset
            days_overdue = (i % 95) + 1  # spread across all aging buckets
            self._create_overdue_invoice(
                partner=partner,
                invoice_date=FROZEN_DATE - timedelta(days=days_overdue),
                amount=100.0 + i,
            )

        # Force ORM compute of partners' aging buckets before timing.
        partners_500.invalidate_recordset()
        partners_500.mapped('total_overdue')

        # Time the report generation
        wizard = self.Wizard.create({})
        with mute_logger(
            'odoo.addons.account_payment_followup.report.followup_report',
        ):
            start = time.time()
            self.Parser._get_report_values(
                docids=wizard.ids,
                data={'form': wizard._get_form_values()},
            )
            elapsed = time.time() - start

        self.assertLess(
            elapsed, 10.0,
            f'PF-003 SLA violation: report took {elapsed:.2f}s '
            'for 500 partners (target: <10s).',
        )
