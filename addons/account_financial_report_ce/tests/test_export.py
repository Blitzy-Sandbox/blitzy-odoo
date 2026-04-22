# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Test Suite for FR-007: Multi-format Export and Drill-down Navigation

Tests the export and drill-down functionality for all 6 financial report types:
- Balance Sheet (FR-001)
- Profit & Loss (FR-002)
- Cash Flow Statement (FR-003)
- General Ledger (FR-004)
- Trial Balance (FR-005)
- Aged Partner Balance (FR-006)

FR-007 Acceptance Criteria:
- PDF generation via ir.actions.report for all report types
- Excel/XLSX export via action_export_xlsx for all report types
- Drill-down navigation returning ir.actions.act_window targeting
  account.move.line with filtered domain
- Report parser _get_report_values returning correct data structure
- Wizard dispatching to correct report model for export operations

Target: Minimum 80% test coverage per EPIC-001 requirements.
BDD alignment: Tests map to FR-007 story acceptance scenarios.
"""

from datetime import date, timedelta

from freezegun import freeze_time

from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestExport(AccountTestInvoicingCommon):
    """
    Test class for FR-007: Multi-format Export and Drill-down Navigation.

    Extends AccountTestInvoicingCommon for pre-built accounting fixtures
    including company_data with configured accounts, journals, partners,
    products, taxes, and payment terms.

    Tests cover:
    - PDF export for all 6 report types
    - Excel/XLSX export for all 6 report types
    - Drill-down navigation from report lines to journal items
    - Report parser _get_report_values data structure validation
    - Wizard-to-report dispatch for PDF and XLSX export
    """

    @classmethod
    def setUpClass(cls):
        """
        Set up test data for export and drill-down tests.

        Creates posted journal entries covering all account types needed
        by the 6 financial report types: revenue, expense, receivable,
        payable, cash, and fixed asset accounts.
        """
        super().setUpClass()

        # Grant financial report module security groups to the test user.
        # The parent AccountTestInvoicingCommon creates an 'accountman' test
        # user with only core accounting groups (group_account_manager,
        # group_account_user). Our module's ACL requires the custom groups
        # group_financial_report_user / group_financial_report_manager for
        # create/read/write/unlink access on all financial report models.
        fr_manager_group = cls.env.ref(
            'account_financial_report_ce.group_financial_report_manager',
            raise_if_not_found=False,
        )
        fr_user_group = cls.env.ref(
            'account_financial_report_ce.group_financial_report_user',
            raise_if_not_found=False,
        )
        groups_to_add = cls.env['res.groups']
        if fr_manager_group:
            groups_to_add |= fr_manager_group
        if fr_user_group:
            groups_to_add |= fr_user_group
        if groups_to_add:
            cls.env.user.group_ids += groups_to_add

        # Store commonly used references from company_data fixtures
        cls.company = cls.company_data['company']
        cls.currency = cls.company_data['currency']
        cls.journal_sale = cls.company_data['default_journal_sale']
        cls.journal_purchase = cls.company_data['default_journal_purchase']
        cls.journal_misc = cls.company_data['default_journal_misc']
        cls.journal_bank = cls.company_data['default_journal_bank']
        cls.account_revenue = cls.company_data['default_account_revenue']
        cls.account_expense = cls.company_data['default_account_expense']
        cls.account_receivable = cls.company_data['default_account_receivable']
        cls.account_payable = cls.company_data['default_account_payable']

        # Reporting date parameters for FR-007 frozen time context
        cls.date_from = date(2024, 1, 1)
        cls.date_to = date(2024, 6, 30)
        # Comparison period offset (1 year prior) used in comparative tests
        cls.comparison_date_to = cls.date_to - timedelta(days=365)

        # Create and post a customer invoice for revenue/receivable data.
        # This produces move lines on the revenue account and receivable
        # account, providing data for Balance Sheet, P&L, General Ledger,
        # Trial Balance, and Aged Receivables reports.
        cls.customer_invoice = cls.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': cls.partner_a.id,
            'invoice_date': date(2024, 3, 15),
            'date': date(2024, 3, 15),
            'invoice_line_ids': [
                (0, 0, {
                    'product_id': cls.product_a.id,
                    'quantity': 5.0,
                    'price_unit': 2000.0,
                    'tax_ids': [],
                }),
            ],
        })
        cls.customer_invoice.action_post()

        # Create and post a vendor bill for expense/payable data.
        # Produces move lines on expense and payable accounts for Balance
        # Sheet, P&L, General Ledger, Trial Balance, and Aged Payables.
        cls.vendor_bill = cls.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': cls.partner_a.id,
            'invoice_date': date(2024, 2, 1),
            'date': date(2024, 2, 1),
            'invoice_line_ids': [
                (0, 0, {
                    'product_id': cls.product_a.id,
                    'quantity': 2.0,
                    'price_unit': 1500.0,
                    'tax_ids': [],
                }),
            ],
        })
        cls.vendor_bill.action_post()

        # Create and post a bank journal entry for cash flow data.
        # Simulates a cash receipt from the customer to exercise the
        # Cash Flow Statement's operating activities section.
        bank_account = cls.env['account.account'].search([
            ('company_ids', 'in', cls.company.ids),
            ('account_type', '=', 'asset_cash'),
        ], limit=1)
        if bank_account and cls.journal_bank:
            cls.bank_entry = cls.env['account.move'].create({
                'move_type': 'entry',
                'journal_id': cls.journal_bank.id,
                'date': date(2024, 4, 1),
                'line_ids': [
                    (0, 0, {
                        'account_id': bank_account.id,
                        'partner_id': cls.partner_a.id,
                        'debit': 3000.0,
                        'credit': 0.0,
                        'name': 'Cash receipt from customer',
                    }),
                    (0, 0, {
                        'account_id': cls.account_receivable.id,
                        'partner_id': cls.partner_a.id,
                        'debit': 0.0,
                        'credit': 3000.0,
                        'name': 'Cash receipt from customer',
                    }),
                ],
            })
            cls.bank_entry.action_post()
        else:
            cls.bank_entry = cls.env['account.move']

    # -------------------------------------------------------------------------
    # HELPER METHODS — Report Creation Factories
    # -------------------------------------------------------------------------

    def _create_balance_sheet_report(self):
        """Create a Balance Sheet report record with standard parameters."""
        return self.env['account.balance.sheet.report'].create({
            'date_to': self.date_to,
            'company_id': self.company.id,
            'target_move': 'posted',
        })

    def _create_profit_loss_report(self):
        """Create a Profit & Loss report record with standard parameters."""
        return self.env['account.profit.loss.report'].create({
            'date_from': self.date_from,
            'date_to': self.date_to,
            'company_id': self.company.id,
            'target_move': 'posted',
        })

    def _create_cash_flow_report(self):
        """Create a Cash Flow Statement report with indirect method."""
        return self.env['account.cash.flow.report'].create({
            'date_from': self.date_from,
            'date_to': self.date_to,
            'company_id': self.company.id,
            'target_move': 'posted',
            'method': 'indirect',
        })

    def _create_general_ledger_report(self):
        """Create a General Ledger report with standard parameters."""
        return self.env['account.general.ledger.report'].create({
            'date_from': self.date_from,
            'date_to': self.date_to,
            'company_id': self.company.id,
            'target_move': 'posted',
        })

    def _create_trial_balance_report(self):
        """Create a Trial Balance report with standard parameters."""
        return self.env['account.trial.balance.report'].create({
            'date_to': self.date_to,
            'company_id': self.company.id,
            'target_move': 'posted',
            'show_balance_zero': True,
        })

    def _create_aged_partner_report(self, report_type='receivable'):
        """Create an Aged Partner Balance report for the given type."""
        return self.env['account.aged.partner.balance.report'].create({
            'date_to': self.date_to,
            'company_id': self.company.id,
            'target_move': 'posted',
            'report_type': report_type,
        })

    # -------------------------------------------------------------------------
    # PDF EXPORT TESTS — FR-007 Scenario: Export to PDF
    # Per FR-007 Acceptance Criteria:
    #   "Given I am viewing a financial report
    #    When I select Export to PDF
    #    Then I receive a PDF document with proper formatting"
    # -------------------------------------------------------------------------

    @freeze_time('2024-06-30')
    def test_fr007_pdf_export_balance_sheet(self):
        """
        FR-007 Scenario: PDF export for Balance Sheet.

        Given I am viewing a Balance Sheet report
        When I select Export to PDF
        Then I receive a PDF report action with type 'ir.actions.report'.
        """
        report = self._create_balance_sheet_report()
        result = report.action_print_pdf()

        self.assertIsInstance(result, dict,
                              "PDF export should return an action dict")
        self.assertEqual(
            result.get('type'), 'ir.actions.report',
            "Balance Sheet PDF action type must be 'ir.actions.report'",
        )

    @freeze_time('2024-06-30')
    def test_fr007_pdf_export_profit_loss(self):
        """
        FR-007 Scenario: PDF export for Profit & Loss.

        Given I am viewing a Profit & Loss report
        When I select Export to PDF
        Then I receive a PDF report action with type 'ir.actions.report'.
        """
        report = self._create_profit_loss_report()
        result = report.action_print_pdf()

        self.assertIsInstance(result, dict,
                              "PDF export should return an action dict")
        self.assertEqual(
            result.get('type'), 'ir.actions.report',
            "Profit & Loss PDF action type must be 'ir.actions.report'",
        )

    @freeze_time('2024-06-30')
    def test_fr007_pdf_export_cash_flow(self):
        """
        FR-007 Scenario: PDF export for Cash Flow Statement.

        Given I am viewing a Cash Flow Statement
        When I select Export to PDF
        Then I receive a PDF report action with type 'ir.actions.report'.
        """
        report = self._create_cash_flow_report()
        result = report.action_print_pdf()

        self.assertIsInstance(result, dict,
                              "PDF export should return an action dict")
        self.assertEqual(
            result.get('type'), 'ir.actions.report',
            "Cash Flow PDF action type must be 'ir.actions.report'",
        )

    @freeze_time('2024-06-30')
    def test_fr007_pdf_export_general_ledger(self):
        """
        FR-007 Scenario: PDF export for General Ledger.

        Given I am viewing a General Ledger report
        When I select Export to PDF
        Then I receive a PDF report action with type 'ir.actions.report'.
        """
        report = self._create_general_ledger_report()
        result = report.action_print_pdf()

        self.assertIsInstance(result, dict,
                              "PDF export should return an action dict")
        self.assertEqual(
            result.get('type'), 'ir.actions.report',
            "General Ledger PDF action type must be 'ir.actions.report'",
        )

    @freeze_time('2024-06-30')
    def test_fr007_pdf_export_trial_balance(self):
        """
        FR-007 Scenario: PDF export for Trial Balance.

        Given I am viewing a Trial Balance report
        When I select Export to PDF
        Then I receive a PDF report action with type 'ir.actions.report'.
        """
        report = self._create_trial_balance_report()
        result = report.action_print_pdf()

        self.assertIsInstance(result, dict,
                              "PDF export should return an action dict")
        self.assertEqual(
            result.get('type'), 'ir.actions.report',
            "Trial Balance PDF action type must be 'ir.actions.report'",
        )

    @freeze_time('2024-06-30')
    def test_fr007_pdf_export_aged_partner(self):
        """
        FR-007 Scenario: PDF export for Aged Partner Balance.

        Given I am viewing an Aged Receivables report
        When I select Export to PDF
        Then I receive a PDF report action with type 'ir.actions.report'.
        """
        report = self._create_aged_partner_report('receivable')
        result = report.action_print_pdf()

        self.assertIsInstance(result, dict,
                              "PDF export should return an action dict")
        self.assertEqual(
            result.get('type'), 'ir.actions.report',
            "Aged Partner Balance PDF action type must be 'ir.actions.report'",
        )

    # -------------------------------------------------------------------------
    # EXCEL/XLSX EXPORT TESTS — FR-007 Scenario: Export to Excel
    # Per FR-007 Acceptance Criteria:
    #   "Given I am viewing a financial report
    #    When I select Export to Excel
    #    Then I receive an XLSX file with data in tabular format"
    #
    # CP3 Finding #9 (QA/Test Integrity MAJOR) — Assertion Tightening
    # -------------------------------------------------------------------------
    # Prior revisions of this suite asserted only
    #     result.get('type') in ('ir.actions.act_url', 'ir.actions.report')
    # which was permissive enough to silently mask the broken ``act_url``
    # overrides that previously existed on ``account.profit.loss.report`` and
    # ``account.cash.flow.report``. Those overrides returned URLs pointing at
    # ``/financial_reports/<model>/xlsx/<id>`` routes that no controller
    # implemented, yielding HTTP 404 for end-users while CI remained green.
    #
    # The assertions below enforce the canonical base-class contract produced
    # by ``account.financial.report.abstract.action_export_xlsx``:
    #
    #   * ``type`` MUST equal ``ir.actions.act_url`` (exact match — not a
    #     set-membership check that accepts fallback alternatives).
    #   * ``url`` MUST begin with ``/web/content/`` and contain
    #     ``download=true`` — this is the Odoo attachment-download pattern
    #     and distinguishes correct base-class delegation from any
    #     hand-rolled custom route that might not be wired to a controller.
    #   * ``target`` MUST equal ``'new'`` so the download opens in a new tab
    #     and preserves the user's report context per FR-007 UX expectations.
    #   * An ``ir.attachment`` with matching ``res_model`` / ``res_id`` MUST
    #     exist after the call — proving the XLSX bytes were actually
    #     produced (not merely a URL fabricated without content).
    #
    # A dedicated helper ``_assert_xlsx_download_action`` centralises these
    # checks so every one of the 6 concrete report types is held to the same
    # contract. Any future model that re-introduces the ``act_url`` anti-
    # pattern with a custom controller URL will now fail at CI rather than
    # at runtime for end-users.
    # -------------------------------------------------------------------------

    def _assert_xlsx_download_action(self, report, result, label):
        """
        Assert ``result`` conforms to the base-class XLSX download contract.

        The base class ``account.financial.report.abstract.action_export_xlsx``
        serialises the workbook to bytes, stores them on ``ir.attachment``,
        and returns a ``{'type': 'ir.actions.act_url',
        'url': '/web/content/<id>?download=true', 'target': 'new'}`` action.

        :param report: the report record whose ``action_export_xlsx`` was
                       invoked (used to verify the attachment linkage).
        :param result: the dict returned by ``action_export_xlsx``.
        :param label:  human-readable report-type label for assertion
                       messages (e.g. ``"Profit & Loss"``).
        """
        # -- Envelope shape --
        self.assertIsInstance(
            result, dict,
            "%s XLSX export must return an action dict" % label,
        )

        # -- Action type MUST be exactly 'ir.actions.act_url' --
        # Strict equality (not assertIn with an or-clause) guarantees the
        # XLSX payload is delivered via the attachment-download pipeline.
        self.assertEqual(
            result.get('type'), 'ir.actions.act_url',
            "%s XLSX action 'type' must be 'ir.actions.act_url'; "
            "got %r. A mismatch indicates a custom act_url override or a "
            "report-action fallback that bypasses the base-class openpyxl "
            "pipeline." % (label, result.get('type')),
        )

        # -- URL MUST target the canonical /web/content/<id> endpoint --
        url = result.get('url') or ''
        self.assertTrue(
            url.startswith('/web/content/'),
            "%s XLSX 'url' must begin with '/web/content/' so the browser "
            "downloads from the ir.attachment endpoint; got %r. A custom "
            "route (e.g. '/financial_reports/<model>/xlsx/<id>') would "
            "return HTTP 404 unless an ir.http controller implements it, "
            "which historically has not been the case." % (label, url),
        )
        self.assertIn(
            'download=true', url,
            "%s XLSX 'url' must include 'download=true' so the browser "
            "triggers a file download instead of rendering inline; "
            "got %r." % (label, url),
        )

        # -- Target MUST open in a new browser tab --
        self.assertEqual(
            result.get('target'), 'new',
            "%s XLSX action 'target' must be 'new' so the download opens "
            "in a new browser tab and preserves the report context; "
            "got %r." % (label, result.get('target')),
        )

        # -- An ir.attachment linked to this report MUST exist --
        # Proves the openpyxl pipeline actually serialised the workbook
        # bytes and persisted them — a URL without a backing attachment
        # would 404 on click.
        xlsx_mimetype = (
            'application/vnd.openxmlformats-officedocument'
            '.spreadsheetml.sheet'
        )
        attachments = self.env['ir.attachment'].search([
            ('res_model', '=', report._name),
            ('res_id', '=', report.id),
            ('mimetype', '=', xlsx_mimetype),
        ])
        self.assertTrue(
            attachments,
            "%s XLSX export must create an ir.attachment with mimetype "
            "'application/vnd.openxmlformats-officedocument"
            ".spreadsheetml.sheet' linked to the report "
            "(res_model=%r, res_id=%r). No such attachment was found, "
            "indicating the openpyxl serialization did not complete." % (
                label, report._name, report.id,
            ),
        )

        # -- The URL's attachment id MUST match a real attachment --
        # Extract the numeric id from '/web/content/<id>?download=true' and
        # confirm it points at one of the XLSX attachments we just found.
        try:
            attachment_id = int(
                url.split('/web/content/', 1)[1].split('?', 1)[0],
            )
        except (IndexError, ValueError):
            self.fail(
                "%s XLSX 'url' %r does not contain a numeric attachment id "
                "in the expected '/web/content/<id>?download=true' "
                "position." % (label, url),
            )
        self.assertIn(
            attachment_id, attachments.ids,
            "%s XLSX 'url' references attachment id %d which is not among "
            "the XLSX attachments linked to this report (ids=%s). This "
            "indicates the action URL and the persisted workbook are out "
            "of sync." % (label, attachment_id, attachments.ids),
        )

    @freeze_time('2024-06-30')
    def test_fr007_xlsx_export_balance_sheet(self):
        """
        FR-007 Scenario: XLSX export for Balance Sheet.

        Given I am viewing a Balance Sheet report
        When I select Export to Excel
        Then I receive an ``ir.actions.act_url`` pointing at a
             ``/web/content/<id>?download=true`` attachment endpoint
             with target=='new' and a backing ir.attachment record.
        """
        report = self._create_balance_sheet_report()
        result = report.action_export_xlsx()
        self._assert_xlsx_download_action(report, result, "Balance Sheet")

    @freeze_time('2024-06-30')
    def test_fr007_xlsx_export_profit_loss(self):
        """
        FR-007 Scenario: XLSX export for Profit & Loss.

        Given I am viewing a Profit & Loss report
        When I select Export to Excel
        Then I receive the canonical base-class XLSX download action.

        Regression guard for CP3 Finding #6: prior to remediation, this
        model's ``action_export_xlsx`` returned
        ``{'type': 'ir.actions.act_url',
          'url': '/financial_reports/profit_loss/xlsx/<id>'}``
        pointing at an unimplemented controller route. The tightened
        contract below would have flagged that failure at CI time.
        """
        report = self._create_profit_loss_report()
        result = report.action_export_xlsx()
        self._assert_xlsx_download_action(report, result, "Profit & Loss")

    @freeze_time('2024-06-30')
    def test_fr007_xlsx_export_cash_flow(self):
        """
        FR-007 Scenario: XLSX export for Cash Flow Statement.

        Given I am viewing a Cash Flow Statement
        When I select Export to Excel
        Then I receive the canonical base-class XLSX download action.

        Regression guard for CP3 Finding #7: prior to remediation, this
        model's ``action_export_xlsx`` returned
        ``{'type': 'ir.actions.act_url',
          'url': '/financial_reports/cash_flow/xlsx/<id>'}``
        pointing at an unimplemented controller route. The tightened
        contract below would have flagged that failure at CI time.
        """
        report = self._create_cash_flow_report()
        result = report.action_export_xlsx()
        self._assert_xlsx_download_action(report, result, "Cash Flow")

    @freeze_time('2024-06-30')
    def test_fr007_xlsx_export_general_ledger(self):
        """
        FR-007 Scenario: XLSX export for General Ledger.

        Given I am viewing a General Ledger report
        When I select Export to Excel
        Then I receive the canonical base-class XLSX download action.
        """
        report = self._create_general_ledger_report()
        result = report.action_export_xlsx()
        self._assert_xlsx_download_action(report, result, "General Ledger")

    @freeze_time('2024-06-30')
    def test_fr007_xlsx_export_trial_balance(self):
        """
        FR-007 Scenario: XLSX export for Trial Balance.

        Given I am viewing a Trial Balance report
        When I select Export to Excel
        Then I receive the canonical base-class XLSX download action.
        """
        report = self._create_trial_balance_report()
        result = report.action_export_xlsx()
        self._assert_xlsx_download_action(report, result, "Trial Balance")

    @freeze_time('2024-06-30')
    def test_fr007_xlsx_export_aged_partner(self):
        """
        FR-007 Scenario: XLSX export for Aged Partner Balance.

        Given I am viewing an Aged Receivables report
        When I select Export to Excel
        Then I receive the canonical base-class XLSX download action.
        """
        report = self._create_aged_partner_report('receivable')
        result = report.action_export_xlsx()
        self._assert_xlsx_download_action(report, result, "Aged Partner")

    # -------------------------------------------------------------------------
    # DRILL-DOWN NAVIGATION TESTS — FR-007 Scenario: Navigate to Source
    # Per FR-007 Acceptance Criteria:
    #   "Given I am viewing a financial report
    #    When I click on a line item amount
    #    Then I am navigated to a filtered view of the underlying
    #    journal entries that comprise that amount"
    # -------------------------------------------------------------------------

    @freeze_time('2024-06-30')
    def test_fr007_drilldown_balance_sheet_line(self):
        """
        FR-007 Scenario: Drill-down from Balance Sheet line.

        Given I am viewing a Balance Sheet
        When I click on a line item amount (e.g., Accounts Receivable)
        Then I am navigated to a filtered journal items view showing
        only the entries for that account up to the report date.
        """
        report = self._create_balance_sheet_report()
        # Use the abstract base action_drilldown which targets account.move.line
        result = report.action_drilldown(
            account_id=self.account_receivable.id,
            date_to=self.date_to,
        )

        self.assertIsInstance(result, dict,
                              "Drill-down should return an action dict")
        self.assertEqual(
            result.get('type'), 'ir.actions.act_window',
            "Drill-down must return ir.actions.act_window",
        )
        self.assertEqual(
            result.get('res_model'), 'account.move.line',
            "Drill-down must target account.move.line",
        )
        self.assertIn('domain', result,
                       "Drill-down action must contain a filter domain")
        # Verify domain is a list with filter tuples
        domain = result.get('domain', [])
        self.assertIsInstance(domain, list,
                              "Domain must be a list of filter tuples")
        self.assertTrue(
            len(domain) > 0,
            "Domain must have at least one filter condition",
        )

    @freeze_time('2024-06-30')
    def test_fr007_drilldown_general_ledger_line(self):
        """
        FR-007 Scenario: Drill-down from General Ledger account section.

        Given I am viewing a General Ledger report
        When I click on an account's transaction total
        Then I see the individual journal items for that account
        filtered by the report's date range.
        """
        report = self._create_general_ledger_report()
        result = report.action_drilldown(
            account_id=self.account_revenue.id,
            date_from=self.date_from,
            date_to=self.date_to,
        )

        self.assertIsInstance(result, dict)
        self.assertEqual(result.get('type'), 'ir.actions.act_window')
        self.assertEqual(result.get('res_model'), 'account.move.line')
        # Verify domain includes date and account filters
        domain = result.get('domain', [])
        self.assertTrue(
            len(domain) > 0,
            "General Ledger drill-down domain must not be empty",
        )
        # Verify account filter is present in domain
        account_filter_found = any(
            isinstance(d, (list, tuple)) and len(d) >= 3
            and d[0] == 'account_id'
            for d in domain
        )
        self.assertTrue(
            account_filter_found,
            "Drill-down domain must filter by account_id",
        )

    @freeze_time('2024-06-30')
    def test_fr007_drilldown_aged_partner_line(self):
        """
        FR-007 Scenario: Drill-down from Aged Partner Balance partner line.

        Given I am viewing an Aged Receivables report
        When I click on a partner's total
        Then I see the partner's open items in account.move.line
        filtered for the receivable accounts.
        """
        report = self._create_aged_partner_report('receivable')
        # Use the abstract base drilldown targeting the receivable account
        result = report.action_drilldown(
            account_id=self.account_receivable.id,
            date_to=self.date_to,
        )

        self.assertIsInstance(result, dict)
        self.assertEqual(
            result.get('type'), 'ir.actions.act_window',
            "Aged partner drill-down must return act_window",
        )
        self.assertEqual(
            result.get('res_model'), 'account.move.line',
            "Aged partner drill-down must target account.move.line",
        )

    @freeze_time('2024-06-30')
    def test_fr007_drilldown_trial_balance_line(self):
        """
        FR-007 Scenario: Drill-down from Trial Balance line.

        Given I am viewing a Trial Balance
        When I click on an account balance
        Then I see the account's journal items filtered by report period.
        """
        report = self._create_trial_balance_report()
        result = report.action_drilldown(
            account_id=self.account_expense.id,
            date_to=self.date_to,
        )

        self.assertIsInstance(result, dict)
        self.assertEqual(
            result.get('type'), 'ir.actions.act_window',
            "Trial Balance drill-down must return act_window",
        )
        self.assertEqual(
            result.get('res_model'), 'account.move.line',
            "Trial Balance drill-down must target account.move.line",
        )

    @freeze_time('2024-06-30')
    def test_fr007_drilldown_action_format(self):
        """
        FR-007 Scenario: Verify drill-down action format compliance.

        Given any financial report
        When the drill-down action is generated
        Then the action dict contains all required keys for a valid
        ir.actions.act_window: type, res_model, view_mode, and domain.
        """
        report = self._create_balance_sheet_report()
        result = report.action_drilldown(
            account_id=self.account_receivable.id,
            date_to=self.date_to,
        )

        # Verify all required keys for a proper ir.actions.act_window
        required_keys = ['type', 'res_model', 'view_mode', 'domain']
        for key in required_keys:
            self.assertIn(
                key, result,
                "Drill-down action must contain key '%s'" % key,
            )

        # Validate key values
        self.assertEqual(result['type'], 'ir.actions.act_window')
        self.assertEqual(result['res_model'], 'account.move.line')
        self.assertIn(
            'list', result['view_mode'],
            "Drill-down view_mode should include 'list' for tabular display",
        )
        # Verify optional but expected keys
        self.assertIn('name', result,
                       "Drill-down action should include a display name")
        # Domain should be a non-empty list of filter conditions
        domain = result['domain']
        self.assertIsInstance(domain, list)
        self.assertGreater(len(domain), 0,
                           "Domain must contain filter conditions")

    # -------------------------------------------------------------------------
    # REPORT PARSER TESTS — FR-007 Scenario: Report Data Structure
    # Per FR-007: Verify that report parsers provide the correct data
    # structure for QWeb PDF template rendering.
    # -------------------------------------------------------------------------

    @freeze_time('2024-06-30')
    def test_fr007_report_parser_balance_sheet(self):
        """
        FR-007 Scenario: Balance Sheet parser returns valid data.

        Given a Balance Sheet report record exists
        When _get_report_values is called on the report parser
        Then the returned dict contains doc_ids, docs, doc_model, and data,
        with docs being the Balance Sheet report recordset.
        """
        report = self._create_balance_sheet_report()
        parser = self.env[
            'report.account_financial_report_ce.report_balance_sheet'
        ]
        result = parser._get_report_values(docids=report.ids)

        self.assertIsInstance(result, dict,
                              "Parser must return a dictionary")
        self.assertIn('doc_ids', result,
                       "Result must contain 'doc_ids'")
        self.assertIn('docs', result,
                       "Result must contain 'docs' recordset")
        self.assertIn('doc_model', result,
                       "Result must contain 'doc_model' string")
        self.assertIn('data', result,
                       "Result must contain 'data' key")
        self.assertEqual(
            result['doc_model'], 'account.balance.sheet.report',
            "doc_model must be 'account.balance.sheet.report'",
        )
        self.assertEqual(
            len(result['docs']), 1,
            "docs should contain exactly one report record",
        )
        self.assertEqual(result['doc_ids'], report.ids)

    @freeze_time('2024-06-30')
    def test_fr007_report_parser_profit_loss(self):
        """
        FR-007 Scenario: Profit & Loss parser returns valid data.

        Given a P&L report record exists
        When _get_report_values is called
        Then the returned dict has the correct doc_model and docs.
        """
        report = self._create_profit_loss_report()
        parser = self.env[
            'report.account_financial_report_ce.report_profit_loss'
        ]
        result = parser._get_report_values(docids=report.ids)

        self.assertIsInstance(result, dict)
        self.assertIn('doc_ids', result)
        self.assertIn('docs', result)
        self.assertIn('doc_model', result)
        self.assertEqual(
            result['doc_model'], 'account.profit.loss.report',
            "doc_model must be 'account.profit.loss.report'",
        )
        self.assertEqual(len(result['docs']), 1)

    @freeze_time('2024-06-30')
    def test_fr007_report_parser_cash_flow(self):
        """
        FR-007 Scenario: Cash Flow parser returns valid data.

        Given a Cash Flow report record exists
        When _get_report_values is called
        Then the returned dict has the correct doc_model and docs.
        """
        report = self._create_cash_flow_report()
        parser = self.env[
            'report.account_financial_report_ce.report_cash_flow'
        ]
        result = parser._get_report_values(docids=report.ids)

        self.assertIsInstance(result, dict)
        self.assertIn('doc_ids', result)
        self.assertIn('docs', result)
        self.assertIn('doc_model', result)
        self.assertEqual(
            result['doc_model'], 'account.cash.flow.report',
            "doc_model must be 'account.cash.flow.report'",
        )

    @freeze_time('2024-06-30')
    def test_fr007_report_parser_general_ledger(self):
        """
        FR-007 Scenario: General Ledger parser returns valid data.

        Given a General Ledger report record exists
        When _get_report_values is called
        Then the returned dict has the correct doc_model and docs.
        """
        report = self._create_general_ledger_report()
        parser = self.env[
            'report.account_financial_report_ce.report_general_ledger'
        ]
        result = parser._get_report_values(docids=report.ids)

        self.assertIsInstance(result, dict)
        self.assertIn('doc_ids', result)
        self.assertIn('docs', result)
        self.assertIn('doc_model', result)
        self.assertEqual(
            result['doc_model'], 'account.general.ledger.report',
            "doc_model must be 'account.general.ledger.report'",
        )

    @freeze_time('2024-06-30')
    def test_fr007_report_parser_trial_balance(self):
        """
        FR-007 Scenario: Trial Balance parser returns valid data.

        Given a Trial Balance report record exists
        When _get_report_values is called
        Then the returned dict has the correct doc_model and docs.
        """
        report = self._create_trial_balance_report()
        parser = self.env[
            'report.account_financial_report_ce.report_trial_balance'
        ]
        result = parser._get_report_values(docids=report.ids)

        self.assertIsInstance(result, dict)
        self.assertIn('doc_ids', result)
        self.assertIn('docs', result)
        self.assertIn('doc_model', result)
        self.assertEqual(
            result['doc_model'], 'account.trial.balance.report',
            "doc_model must be 'account.trial.balance.report'",
        )

    @freeze_time('2024-06-30')
    def test_fr007_report_parser_aged_partner(self):
        """
        FR-007 Scenario: Aged Partner Balance parser returns valid data.

        Given an Aged Partner Balance report record exists
        When _get_report_values is called
        Then the returned dict has the correct doc_model and docs.
        """
        report = self._create_aged_partner_report('receivable')
        parser = self.env[
            'report.account_financial_report_ce.report_aged_partner_balance'
        ]
        result = parser._get_report_values(docids=report.ids)

        self.assertIsInstance(result, dict)
        self.assertIn('doc_ids', result)
        self.assertIn('docs', result)
        self.assertIn('doc_model', result)
        self.assertEqual(
            result['doc_model'],
            'account.aged.partner.balance.report',
            "doc_model must be 'account.aged.partner.balance.report'",
        )

    # -------------------------------------------------------------------------
    # WIZARD INTEGRATION TESTS — FR-007 Scenario: Wizard Export Dispatch
    # Per FR-007: The unified financial report wizard dispatches export
    # actions to the correct underlying report model.
    # -------------------------------------------------------------------------

    @freeze_time('2024-06-30')
    def test_fr007_wizard_pdf_dispatch(self):
        """
        FR-007 Scenario: Wizard dispatches PDF export correctly.

        Given the financial report wizard with Balance Sheet selected
        When I invoke action_print_pdf from the wizard
        Then the wizard generates the Balance Sheet report record
        and returns a PDF report action with type 'ir.actions.report'.
        """
        wizard = self.env['account.financial.report.wizard'].create({
            'report_type': 'balance_sheet',
            'date_to': self.date_to,
            'company_id': self.company.id,
            'target_move': 'posted',
        })
        result = wizard.action_print_pdf()

        self.assertIsInstance(result, dict,
                              "Wizard PDF dispatch must return a dict")
        self.assertEqual(
            result.get('type'), 'ir.actions.report',
            "Wizard PDF dispatch must return 'ir.actions.report'",
        )

    @freeze_time('2024-06-30')
    def test_fr007_wizard_xlsx_dispatch(self):
        """
        FR-007 Scenario: Wizard dispatches XLSX export correctly.

        Given the financial report wizard with Trial Balance selected
        When I invoke action_export_xlsx from the wizard
        Then the wizard generates the Trial Balance report record
        and returns a valid XLSX export action.
        """
        wizard = self.env['account.financial.report.wizard'].create({
            'report_type': 'trial_balance',
            'date_to': self.date_to,
            'company_id': self.company.id,
            'target_move': 'posted',
        })
        result = wizard.action_export_xlsx()

        self.assertIsInstance(result, dict,
                              "Wizard XLSX dispatch must return a dict")
        self.assertIn(
            result.get('type'),
            ('ir.actions.act_url', 'ir.actions.report'),
            "Wizard XLSX dispatch must return a valid export action",
        )

    @freeze_time('2024-06-30')
    def test_fr007_wizard_generate_report(self):
        """
        FR-007 Scenario: Wizard generates report and returns window action.

        Given the financial report wizard with P&L selected and valid dates
        When I invoke action_generate_report
        Then the wizard creates the P&L report record and returns
        an ir.actions.act_window pointing to the report model.

        Also verifies that the wizard raises UserError when required
        parameters are missing (negative test case for robustness).
        """
        wizard = self.env['account.financial.report.wizard'].create({
            'report_type': 'profit_loss',
            'date_from': self.date_from,
            'date_to': self.date_to,
            'company_id': self.company.id,
            'target_move': 'posted',
        })
        result = wizard.action_generate_report()

        self.assertIsInstance(result, dict,
                              "Generate report must return a dict")
        self.assertEqual(
            result.get('type'), 'ir.actions.act_window',
            "Generate report must return 'ir.actions.act_window'",
        )
        self.assertEqual(
            result.get('res_model'), 'account.profit.loss.report',
            "Result must target 'account.profit.loss.report'",
        )
        self.assertTrue(
            result.get('res_id'),
            "Result must include the generated report record ID",
        )

        # Negative test: verify UserError is raised when date_from is missing
        # for a period-based report type (P&L requires date_from).
        wizard_no_date = self.env['account.financial.report.wizard'].create({
            'report_type': 'profit_loss',
            'date_to': self.date_to,
            'company_id': self.company.id,
            'target_move': 'posted',
        })
        with self.assertRaises(UserError):
            wizard_no_date.action_generate_report()
