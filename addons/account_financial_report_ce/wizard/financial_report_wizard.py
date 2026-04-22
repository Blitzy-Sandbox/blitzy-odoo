# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Financial Report Wizard

Unified wizard for generating all financial reports:
- Balance Sheet (FR-001)
- Profit & Loss Statement (FR-002)
- Cash Flow Statement (FR-003)
- General Ledger (FR-004)
- Trial Balance (FR-005)
- Aged Partner Balance (FR-006)

This wizard provides a consistent entry point for all reports,
with common parameters and report-specific options.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class FinancialReportWizard(models.TransientModel):
    """
    Unified Financial Report Wizard.

    Provides selection of report type and common parameters,
    then delegates to specific report models.
    """
    _name = 'account.financial.report.wizard'
    _description = 'Financial Report Wizard'

    # -------------------------------------------------------------------------
    # REPORT SELECTION
    # -------------------------------------------------------------------------

    report_type = fields.Selection(
        selection=[
            ('balance_sheet', 'Balance Sheet'),
            ('profit_loss', 'Profit & Loss Statement'),
            ('cash_flow', 'Cash Flow Statement'),
            ('general_ledger', 'General Ledger'),
            ('trial_balance', 'Trial Balance'),
            ('aged_receivable', 'Aged Receivable'),
            ('aged_payable', 'Aged Payable'),
        ],
        string='Report Type',
        required=True,
        default='balance_sheet',
        help="Select the type of financial report to generate.",
    )

    # -------------------------------------------------------------------------
    # COMMON PARAMETERS
    # -------------------------------------------------------------------------

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )

    date_from = fields.Date(
        string='From Date',
        help="Start date (required for P&L, Cash Flow, General Ledger).",
    )

    date_to = fields.Date(
        string='To Date / As of Date',
        default=fields.Date.context_today,
        help="End date or as-of date for the report.",
    )

    target_move = fields.Selection(
        selection=[
            ('posted', 'All Posted Entries'),
            ('all', 'All Entries'),
        ],
        string='Target Moves',
        required=True,
        default='posted',
    )

    # -------------------------------------------------------------------------
    # COMPARISON OPTIONS
    # -------------------------------------------------------------------------

    enable_comparison = fields.Boolean(
        string='Enable Comparison',
        default=False,
        help="Enable period comparison for reports that support it.",
    )

    comparison_date_from = fields.Date(
        string='Comparison From',
        help="Start date for the comparison period.",
    )

    comparison_date_to = fields.Date(
        string='Comparison To',
        help="End date for the comparison period.",
    )

    # -------------------------------------------------------------------------
    # FILTER OPTIONS
    # -------------------------------------------------------------------------

    account_ids = fields.Many2many(
        comodel_name='account.account',
        string='Accounts',
        help="Filter by specific accounts (General Ledger, Trial Balance).",
    )

    journal_ids = fields.Many2many(
        comodel_name='account.journal',
        string='Journals',
        help="Filter by specific journals.",
    )

    partner_ids = fields.Many2many(
        comodel_name='res.partner',
        string='Partners',
        help="Filter by specific partners (Aged Balance reports).",
    )

    partner_type = fields.Selection(
        selection=[
            ('customer', 'Customer'),
            ('supplier', 'Supplier'),
        ],
        string='Partner Type',
        help="Filter partners by type for Aged Balance reports. "
             "Automatically set based on report type selection "
             "(Customer for Receivables, Supplier for Payables).",
    )

    analytic_account_ids = fields.Many2many(
        comodel_name='account.analytic.account',
        string='Analytic Accounts',
        help="Filter by specific analytic accounts.",
    )

    # -------------------------------------------------------------------------
    # DISPLAY OPTIONS
    # -------------------------------------------------------------------------

    hide_zero_balance = fields.Boolean(
        string='Hide Zero Balances',
        default=False,
        help="Hide accounts/partners with zero balance.",
    )

    show_hierarchy = fields.Boolean(
        string='Show Hierarchy',
        default=False,
        help="Show account hierarchy groupings.",
    )

    show_partner_details = fields.Boolean(
        string='Show Partner Details',
        default=False,
        help="Show partner-level detail for Trial Balance and General Ledger.",
    )

    show_details = fields.Boolean(
        string='Show Details',
        default=True,
        help="Show individual journal item details in General Ledger.",
    )

    show_move_lines = fields.Boolean(
        string='Show Move Lines',
        default=False,
        help="Show individual move lines in Aged Partner Balance.",
    )

    # -------------------------------------------------------------------------
    # AGING BUCKET THRESHOLDS (days) — Aged Receivable / Aged Payable only
    # -------------------------------------------------------------------------
    # Each bucket field represents the upper day boundary for the
    # corresponding aging tier.  Defaults match the conventional
    # 30 / 60 / 90 / 120-day industry tiers.  These values pass through to
    # the ``account.aged.partner.balance.report`` model which already
    # declares identical ``bucket_N_days`` fields, enabling per-run
    # customization of the aging thresholds without code changes.

    bucket_1_days = fields.Integer(
        string='Bucket 1 (Days)',
        default=30,
        help="Upper day boundary for the first aging tier (e.g. 1-30 days).",
    )

    bucket_2_days = fields.Integer(
        string='Bucket 2 (Days)',
        default=60,
        help="Upper day boundary for the second aging tier (e.g. 31-60 days).",
    )

    bucket_3_days = fields.Integer(
        string='Bucket 3 (Days)',
        default=90,
        help="Upper day boundary for the third aging tier (e.g. 61-90 days).",
    )

    bucket_4_days = fields.Integer(
        string='Bucket 4 (Days)',
        default=120,
        help="Upper day boundary for the fourth aging tier (e.g. 91-120 days).",
    )

    cash_flow_method = fields.Selection(
        selection=[
            ('indirect', 'Indirect Method'),
            ('direct', 'Direct Method'),
        ],
        string='Cash Flow Method',
        default='indirect',
        help="Method for cash flow statement calculation.",
    )

    include_initial_balance = fields.Boolean(
        string='Include Initial Balance',
        default=True,
    )

    sort_by = fields.Selection(
        selection=[
            ('date', 'Date'),
            ('ref', 'Reference'),
        ],
        string='Sort By',
        default='date',
    )

    # -------------------------------------------------------------------------
    # VALIDATION
    # -------------------------------------------------------------------------

    @api.onchange('report_type')
    def _onchange_report_type(self):
        """Reset and auto-configure fields based on selected report type.

        Handles:
        - Date field defaults (fiscal year start for period reports,
          cleared for structural/as-of reports).
        - Partner type auto-selection for aged balance reports
          (customer for aged_receivable, supplier for aged_payable).
        - Report-specific option resets when switching between types
          to avoid stale configuration carrying over.

        Returns:
            None. Modifies wizard fields in-place via onchange.
        """
        # --- Date handling ---
        if self.report_type in (
            'balance_sheet', 'trial_balance',
            'aged_receivable', 'aged_payable',
        ):
            # Structural and as-of-date reports do not need date_from
            self.date_from = False
        elif self.report_type in ('profit_loss', 'cash_flow', 'general_ledger'):
            if not self.date_from:
                # Default to fiscal year start for period-based reports
                today = self.date_to or fields.Date.today()
                if self.company_id:
                    fiscal_year = self.company_id.compute_fiscalyear_dates(
                        today,
                    )
                    self.date_from = fiscal_year.get('date_from')

        # --- Partner type auto-set for aged balance ---
        if self.report_type == 'aged_receivable':
            self.partner_type = 'customer'
        elif self.report_type == 'aged_payable':
            self.partner_type = 'supplier'
        else:
            # Clear partner_type when not on aged balance report
            self.partner_type = False

        # --- Reset report-specific fields when switching types ---
        if self.report_type != 'cash_flow':
            self.cash_flow_method = 'indirect'
        if self.report_type not in ('aged_receivable', 'aged_payable'):
            self.show_move_lines = False
        if self.report_type != 'general_ledger':
            self.show_details = True

    @api.constrains('date_from', 'date_to', 'comparison_date_from',
                     'comparison_date_to')
    def _check_dates(self):
        """Validate date field consistency.

        Checks:
        - Primary date range: date_from must precede date_to.
        - Comparison date range (when comparison is enabled):
          comparison_date_from must precede comparison_date_to.

        Raises:
            UserError: If any date range is inverted.
        """
        for wizard in self:
            if (wizard.date_from and wizard.date_to
                    and wizard.date_from > wizard.date_to):
                raise UserError(
                    _("From Date must be before To Date."),
                )
            if (wizard.enable_comparison
                    and wizard.comparison_date_from
                    and wizard.comparison_date_to
                    and wizard.comparison_date_from
                    > wizard.comparison_date_to):
                raise UserError(
                    _("Comparison From Date must be before "
                      "Comparison To Date."),
                )

    # -------------------------------------------------------------------------
    # ACTIONS
    # -------------------------------------------------------------------------

    def action_generate_report(self):
        """Generate the selected financial report.

        Bridges wizard parameters to the appropriate report transient model,
        creating a report record with all relevant configuration values and
        delegating to the model's ``action_generate_report`` method.

        The method performs:
        1. Report-type specific pre-validation (required fields check).
        2. Common and type-specific value assembly.
        3. Report model record creation with ORM error handling.
        4. Delegation to the report model's own generation action.

        Returns:
            dict: An ``ir.actions.act_window`` action dictionary pointing
                to the generated report form view.

        Raises:
            UserError: If required parameters are missing or the report
                model raises a validation/creation error.
        """
        self.ensure_one()

        # Map report type to ORM model name.
        # Both aged_receivable and aged_payable map to the same model;
        # the distinction is handled by the 'report_type' field on that model.
        report_models = {
            'balance_sheet': 'account.balance.sheet.report',
            'profit_loss': 'account.profit.loss.report',
            'cash_flow': 'account.cash.flow.report',
            'general_ledger': 'account.general.ledger.report',
            'trial_balance': 'account.trial.balance.report',
            'aged_receivable': 'account.aged.partner.balance.report',
            'aged_payable': 'account.aged.partner.balance.report',
        }

        model_name = report_models.get(self.report_type)
        if not model_name:
            raise UserError(_("Invalid report type selected."))

        # --- Pre-validation of report-specific required fields ---
        self._validate_report_prerequisites()

        # --- Assemble common values ---
        vals = {
            'company_id': self.company_id.id,
            'target_move': self.target_move,
            'enable_comparison': self.enable_comparison,
            'hide_zero_balance': self.hide_zero_balance,
        }

        # date_to is always the end/as-of date for all report types
        vals['date_to'] = self.date_to

        # Add date_from for period-based reports
        if self.report_type in ('profit_loss', 'cash_flow', 'general_ledger'):
            vals['date_from'] = self.date_from

        # Trial balance also accepts optional date_from for period activity
        if self.report_type == 'trial_balance' and self.date_from:
            vals['date_from'] = self.date_from

        # --- Comparison dates ---
        if self.enable_comparison:
            vals['comparison_date_from'] = self.comparison_date_from
            vals['comparison_date_to'] = self.comparison_date_to

        # --- Common filter pass-through ---
        # Only pass Many2many fields when the target model declares them;
        # Odoo 19.0 raises ValueError for unknown field names in create().
        target_model = self.env[model_name]
        if self.journal_ids and 'journal_ids' in target_model._fields:
            vals['journal_ids'] = [(6, 0, self.journal_ids.ids)]
        if (self.analytic_account_ids
                and 'analytic_account_ids' in target_model._fields):
            vals['analytic_account_ids'] = [
                (6, 0, self.analytic_account_ids.ids),
            ]

        # Display options — only pass to models that define the fields,
        # since Odoo 19.0 ORM rejects unknown field names on create().
        if 'show_hierarchy' in target_model._fields:
            vals['show_hierarchy'] = self.show_hierarchy
        if 'show_partner_details' in target_model._fields:
            vals['show_partner_details'] = self.show_partner_details

        # --- Report-specific values ---
        if self.report_type == 'general_ledger':
            vals['account_ids'] = [(6, 0, self.account_ids.ids)]
            vals['include_initial_balance'] = self.include_initial_balance
            vals['sort_by'] = self.sort_by
            vals['show_details'] = self.show_details

        if self.report_type == 'trial_balance':
            vals['show_balance_zero'] = not self.hide_zero_balance
            # Trial Balance does not currently declare ``account_ids`` on the
            # target transient model, but a future iteration may add it.
            # Mirror the defensive introspection pattern used for
            # ``journal_ids``/``analytic_account_ids``/``show_hierarchy``
            # above so the branch stays forward-compatible and never
            # attempts to write an unknown field (which Odoo 19.0 ORM
            # rejects with ``ValueError`` in ``create()``).
            if (self.account_ids
                    and 'account_ids' in target_model._fields):
                vals['account_ids'] = [(6, 0, self.account_ids.ids)]

        if self.report_type == 'cash_flow':
            vals['method'] = self.cash_flow_method

        if self.report_type in ('aged_receivable', 'aged_payable'):
            vals['report_type'] = (
                'receivable' if self.report_type == 'aged_receivable'
                else 'payable'
            )
            vals['partner_ids'] = [(6, 0, self.partner_ids.ids)]
            vals['show_move_lines'] = self.show_move_lines
            # Pass through user-configured aging bucket thresholds.  The
            # target ``account.aged.partner.balance.report`` model declares
            # matching ``bucket_N_days`` Integer fields that drive the
            # overdue-tier classification logic.  Only include these keys
            # for aged reports — other report models do not accept them.
            vals['bucket_1_days'] = self.bucket_1_days
            vals['bucket_2_days'] = self.bucket_2_days
            vals['bucket_3_days'] = self.bucket_3_days
            vals['bucket_4_days'] = self.bucket_4_days

        # --- Create report with error handling ---
        try:
            report = self.env[model_name].create(vals)
        except (ValidationError, ValueError) as exc:
            raise UserError(
                _("Could not create %(report_type)s report: %(error)s",
                  report_type=dict(
                      self._fields['report_type'].selection,
                  ).get(self.report_type, self.report_type),
                  error=str(exc)),
            ) from exc
        return report.action_generate_report()

    def _validate_report_prerequisites(self):
        """Validate report-specific required fields before generation.

        Performs pre-creation validation to give the user clear error
        messages rather than cryptic ORM constraint failures.

        Raises:
            UserError: If a required field for the selected report type
                is missing or invalid.
        """
        if self.report_type in ('profit_loss', 'cash_flow', 'general_ledger'):
            if not self.date_from:
                raise UserError(
                    _("From Date is required for %s reports.",
                      dict(self._fields['report_type'].selection).get(
                          self.report_type, self.report_type)),
                )
        if self.report_type == 'cash_flow' and not self.cash_flow_method:
            raise UserError(
                _("Cash Flow Method must be selected for "
                  "Cash Flow Statement reports."),
            )
        if (self.report_type in ('aged_receivable', 'aged_payable')
                and not self.date_to):
            raise UserError(
                _("As of Date is required for Aged Partner Balance reports."),
            )

    # Mapping of wizard report_type to ir.actions.report XML IDs
    # used as fallback when the report model lacks action_print_pdf.
    REPORT_XML_IDS = {
        'balance_sheet':
            'account_financial_report_ce.action_report_balance_sheet',
        'profit_loss':
            'account_financial_report_ce.action_report_profit_loss',
        'cash_flow':
            'account_financial_report_ce.action_report_cash_flow',
        'general_ledger':
            'account_financial_report_ce.action_report_general_ledger',
        'trial_balance':
            'account_financial_report_ce.action_report_trial_balance',
        'aged_receivable':
            'account_financial_report_ce.action_report_aged_partner_balance',
        'aged_payable':
            'account_financial_report_ce.action_report_aged_partner_balance',
    }

    def action_print_pdf(self):
        """Generate the report and export it as a PDF document.

        Chains two steps:
        1. Calls ``action_generate_report`` to create the transient
           report record and obtain its action dictionary.
        2. Delegates to the report model's ``action_print_pdf`` method
           if available; otherwise falls back to the matching
           ``ir.actions.report`` XML-ID to produce the PDF via QWeb.

        Returns:
            dict: An ``ir.actions.report`` action dictionary that
                triggers PDF generation/download in the client.

        Raises:
            UserError: If PDF export is not available or the report
                action reference cannot be resolved.
        """
        self.ensure_one()
        # Step 1 — generate the report record
        action = self.action_generate_report()
        report_id = action.get('res_id')
        model = action.get('res_model')

        if report_id and model:
            report = self.env[model].browse(report_id)
            # Preferred path: delegate to report model's own PDF method
            if hasattr(report, 'action_print_pdf'):
                return report.action_print_pdf()
            # Fallback: use the ir.actions.report XML-ID mapping
            xml_id = self.REPORT_XML_IDS.get(self.report_type)
            if xml_id:
                try:
                    return self.env.ref(xml_id).report_action(report)
                except ValueError:
                    pass  # XML-ID not found — fall through to error

        report_label = dict(
            self._fields['report_type'].selection,
        ).get(self.report_type, self.report_type)
        raise UserError(
            _("PDF export is not available for the '%s' report type.",
              report_label),
        )

    def action_export_xlsx(self):
        """Generate the report and export it as an Excel (XLSX) file.

        Chains two steps:
        1. Calls ``action_generate_report`` to create the transient
           report record and obtain its action dictionary.
        2. Delegates to the report model's ``action_export_xlsx`` method
           to produce the spreadsheet download.

        Returns:
            dict: An action dictionary that triggers XLSX file download
                in the client.

        Raises:
            UserError: If the report model does not implement Excel
                export capability.
        """
        self.ensure_one()
        # Step 1 — generate the report record
        action = self.action_generate_report()
        report_id = action.get('res_id')
        model = action.get('res_model')

        if report_id and model:
            report = self.env[model].browse(report_id)
            if hasattr(report, 'action_export_xlsx'):
                return report.action_export_xlsx()

        report_label = dict(
            self._fields['report_type'].selection,
        ).get(self.report_type, self.report_type)
        raise UserError(
            _("Excel export is not available for the '%s' report type. "
              "Please ensure the report model implements "
              "action_export_xlsx.",
              report_label),
        )

    def action_preview(self):
        """Preview the report inline in the web client.

        Convenience action bound to the *Preview* button in the wizard
        footer.  Delegates entirely to ``action_generate_report`` so
        the user sees the report form view without triggering a
        separate PDF/Excel export.

        Returns:
            dict: An ``ir.actions.act_window`` action dictionary
                identical to ``action_generate_report``.
        """
        self.ensure_one()
        return self.action_generate_report()
