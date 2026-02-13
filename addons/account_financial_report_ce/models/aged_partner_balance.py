# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Aged Partner Balance Report Model

Implements FR-006: Aged Receivable/Payable Reports
User Story: As a Business Owner, I want to generate aged receivable and payable
reports showing amounts due in 30/60/90/120+ day buckets so that I can manage
cash flow and prioritize collection efforts.

Acceptance Criteria:
- Scenario 1: Generate Aged Receivables report
- Scenario 2: Generate Aged Payables report
- Scenario 3: Display aging buckets (Current, 1-30, 31-60, 61-90, 90+)
- Scenario 4: Show partner-level details with invoice breakdown
- Scenario 5: Sort by total amount or oldest bucket
- Scenario 6: Export to PDF/Excel with drill-down capability
"""


from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command


# Mapping between partner_type aliases and internal report_type values
_PARTNER_TYPE_TO_REPORT_TYPE = {
    'customer': 'receivable',
    'supplier': 'payable',
}
_REPORT_TYPE_TO_PARTNER_TYPE = {
    'receivable': 'customer',
    'payable': 'supplier',
    'both': 'customer',
}


def _sync_alias_vals(vals):
    """Synchronise alias field values to their canonical counterparts.

    If the caller passes *only* the alias name (``date_at``, ``partner_type``)
    the canonical field (``date_to``, ``report_type``) is populated so that
    ``required=True`` and ``default=...`` constraints on the canonical fields
    are satisfied.
    """
    # date_at -> date_to
    if 'date_at' in vals and 'date_to' not in vals:
        vals['date_to'] = vals['date_at']
    elif 'date_to' in vals and 'date_at' not in vals:
        vals['date_at'] = vals['date_to']

    # partner_type -> report_type
    if 'partner_type' in vals and 'report_type' not in vals:
        vals['report_type'] = _PARTNER_TYPE_TO_REPORT_TYPE.get(
            vals['partner_type'], 'receivable'
        )
    elif 'report_type' in vals and 'partner_type' not in vals:
        vals['partner_type'] = _REPORT_TYPE_TO_PARTNER_TYPE.get(
            vals['report_type'], 'customer'
        )


class AgedPartnerBalanceReport(models.TransientModel):
    """
    Aged Partner Balance Report.

    Shows receivables or payables grouped by partner with
    amounts categorized into aging buckets.
    """
    _name = 'account.aged.partner.balance.report'
    _description = 'Aged Partner Balance Report'
    _inherit = 'account.financial.report.abstract'

    # -------------------------------------------------------------------------
    # AGED BALANCE SPECIFIC FIELDS
    # -------------------------------------------------------------------------

    date_to = fields.Date(
        string='As of Date',
        required=True,
        default=fields.Date.context_today,
        help="Age invoices as of this date.",
    )

    # Alias stored field for backward compatibility
    date_at = fields.Date(
        string='As At Date',
        help="Alias for 'As of Date'. Kept in sync with date_to.",
    )

    report_type = fields.Selection(
        selection=[
            ('receivable', 'Receivables (Customers)'),
            ('payable', 'Payables (Vendors)'),
            ('both', 'Both'),
        ],
        string='Report Type',
        required=True,
        default='receivable',
        help="Type of partner balances to include.",
    )

    # Alias stored field for backward compatibility
    partner_type = fields.Selection(
        selection=[
            ('customer', 'Customer'),
            ('supplier', 'Supplier'),
        ],
        string='Partner Type',
        help="Alias for 'Report Type'. Maps customer->receivable, supplier->payable.",
    )

    partner_ids = fields.Many2many(
        comodel_name='res.partner',
        string='Partners',
        help="Specific partners to include. Leave empty for all.",
    )

    # Aging bucket configuration (days)
    bucket_1_days = fields.Integer(string='Bucket 1 Days', default=30)
    bucket_2_days = fields.Integer(string='Bucket 2 Days', default=60)
    bucket_3_days = fields.Integer(string='Bucket 3 Days', default=90)
    bucket_4_days = fields.Integer(string='Bucket 4 Days', default=120)

    show_only_overdue = fields.Boolean(
        string='Show Only Overdue',
        default=False,
        help="Exclude items that are not yet due.",
    )

    sort_by = fields.Selection(
        selection=[
            ('partner', 'Partner Name'),
            ('total', 'Total Amount'),
            ('oldest', 'Oldest Balance'),
        ],
        string='Sort By',
        default='partner',
    )

    # Account types for filtering
    RECEIVABLE_TYPES = ['asset_receivable']
    PAYABLE_TYPES = ['liability_payable']

    # -------------------------------------------------------------------------
    # ALIAS FIELD SYNCHRONISATION
    # -------------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to synchronise alias fields with canonical fields.

        - date_at <-> date_to
        - partner_type <-> report_type
        """
        for vals in vals_list:
            _sync_alias_vals(vals)
        records = super().create(vals_list)
        # Back-populate alias fields after creation
        for rec in records:
            if not rec.date_at and rec.date_to:
                rec.date_at = rec.date_to
            if not rec.partner_type and rec.report_type:
                rec.partner_type = _REPORT_TYPE_TO_PARTNER_TYPE.get(
                    rec.report_type, 'customer'
                )
        return records

    def write(self, vals):
        """Override write to keep alias fields in sync."""
        _sync_alias_vals(vals)
        res = super().write(vals)
        # Propagate canonical -> alias when canonical is written
        if 'date_to' in vals and 'date_at' not in vals:
            super().write({'date_at': vals['date_to']})
        if 'report_type' in vals and 'partner_type' not in vals:
            for rec in self:
                super(AgedPartnerBalanceReport, rec).write({
                    'partner_type': _REPORT_TYPE_TO_PARTNER_TYPE.get(
                        rec.report_type, 'customer'
                    ),
                })
        return res

    # -------------------------------------------------------------------------
    # COMPUTED REPORT DATA
    # -------------------------------------------------------------------------

    partner_line_ids = fields.One2many(
        comodel_name='account.aged.partner.balance.report.partner',
        inverse_name='report_id',
        string='Partner Lines',
    )

    # Alias: line_ids points to same sub-records as partner_line_ids
    # Using a plain One2many (not related) to avoid psycopg2 adaptation errors
    # that occur when 'related' tries to pass recordsets as SQL parameters.
    line_ids = fields.One2many(
        comodel_name='account.aged.partner.balance.report.partner',
        inverse_name='report_id',
        string='Lines',
    )

    # Totals
    total_not_due = fields.Monetary(string='Not Due', currency_field='currency_id')
    total_bucket_1 = fields.Monetary(string='1-30 Days', currency_field='currency_id')
    total_bucket_2 = fields.Monetary(string='31-60 Days', currency_field='currency_id')
    total_bucket_3 = fields.Monetary(string='61-90 Days', currency_field='currency_id')
    total_bucket_4 = fields.Monetary(string='91-120 Days', currency_field='currency_id')
    total_bucket_5 = fields.Monetary(string='120+ Days', currency_field='currency_id')
    total_balance = fields.Monetary(string='Total', currency_field='currency_id')

    def _compute_report_data(self):
        """
        Compute Aged Partner Balance report data.

        For each partner:
        1. Find all open receivable/payable items
        2. Calculate age based on due date vs report date
        3. Categorize into aging buckets
        4. Sum totals

        Uses ``fields.Command`` operations for ORM-safe persistence of
        One2many records on stored TransientModel records.
        """
        for report in self:
            report.currency_id = report.company_id.currency_id

            # Determine account types
            account_types = []
            if report.report_type in ('receivable', 'both'):
                account_types.extend(report.RECEIVABLE_TYPES)
            if report.report_type in ('payable', 'both'):
                account_types.extend(report.PAYABLE_TYPES)

            # Get accounts (Odoo 19.0: company_ids Many2many)
            accounts = self.env['account.account'].search([
                ('company_ids', 'in', report.company_id.ids),
                ('account_type', 'in', account_types),
            ])

            # Get open (unreconciled) move lines
            domain = [
                ('company_id', '=', report.company_id.id),
                ('account_id', 'in', accounts.ids),
                ('date', '<=', report.date_to),
                ('reconciled', '=', False),
                ('amount_residual', '!=', 0),
            ]

            if report.target_move == 'posted':
                domain.append(('parent_state', '=', 'posted'))

            if report.partner_ids:
                domain.append(('partner_id', 'in', report.partner_ids.ids))

            move_lines = self.env['account.move.line'].search(domain)

            # Group by partner
            partner_data = {}
            for ml in move_lines:
                partner = ml.partner_id or self.env['res.partner']
                if partner.id not in partner_data:
                    partner_data[partner.id] = {
                        'partner': partner,
                        'lines': [],
                        'not_due': 0.0,
                        'bucket_1': 0.0,
                        'bucket_2': 0.0,
                        'bucket_3': 0.0,
                        'bucket_4': 0.0,
                        'bucket_5': 0.0,
                        'total': 0.0,
                    }

                # Calculate age
                due_date = ml.date_maturity or ml.date
                days_overdue = (report.date_to - due_date).days

                # Get residual amount (positive for receivable, negative for payable)
                amount = ml.amount_residual
                if ml.account_id.account_type in report.PAYABLE_TYPES:
                    amount = -amount

                # Skip not-due items if option selected
                if report.show_only_overdue and days_overdue <= 0:
                    continue

                # Categorize into buckets
                if days_overdue <= 0:
                    partner_data[partner.id]['not_due'] += amount
                elif days_overdue <= report.bucket_1_days:
                    partner_data[partner.id]['bucket_1'] += amount
                elif days_overdue <= report.bucket_2_days:
                    partner_data[partner.id]['bucket_2'] += amount
                elif days_overdue <= report.bucket_3_days:
                    partner_data[partner.id]['bucket_3'] += amount
                elif days_overdue <= report.bucket_4_days:
                    partner_data[partner.id]['bucket_4'] += amount
                else:
                    partner_data[partner.id]['bucket_5'] += amount

                partner_data[partner.id]['total'] += amount
                partner_data[partner.id]['lines'].append(ml)

            # Sorting
            partners_sorted = list(partner_data.values())
            if report.sort_by == 'partner':
                partners_sorted.sort(key=lambda x: x['partner'].name or '')
            elif report.sort_by == 'total':
                partners_sorted.sort(key=lambda x: -abs(x['total']))
            elif report.sort_by == 'oldest':
                partners_sorted.sort(key=lambda x: -(x['bucket_5'] + x['bucket_4']))

            # Build partner lines using Command operations and accumulate totals
            partner_cmds = [Command.clear()]
            total_not_due = 0.0
            total_bucket_1 = 0.0
            total_bucket_2 = 0.0
            total_bucket_3 = 0.0
            total_bucket_4 = 0.0
            total_bucket_5 = 0.0
            total_balance = 0.0

            for pd in partners_sorted:
                if pd['total'] == 0:
                    continue

                # Build nested detail line commands for each partner
                detail_cmds = []
                for ml in pd['lines']:
                    due_date = ml.date_maturity or ml.date
                    days_ov = (report.date_to - due_date).days
                    # Determine bucket label
                    if days_ov <= 0:
                        bucket_label = _('Not Due')
                    elif days_ov <= report.bucket_1_days:
                        bucket_label = _('1-%d') % report.bucket_1_days
                    elif days_ov <= report.bucket_2_days:
                        bucket_label = _('%d-%d') % (
                            report.bucket_1_days + 1, report.bucket_2_days,
                        )
                    elif days_ov <= report.bucket_3_days:
                        bucket_label = _('%d-%d') % (
                            report.bucket_2_days + 1, report.bucket_3_days,
                        )
                    elif days_ov <= report.bucket_4_days:
                        bucket_label = _('%d-%d') % (
                            report.bucket_3_days + 1, report.bucket_4_days,
                        )
                    else:
                        bucket_label = _('%d+') % (report.bucket_4_days + 1)

                    residual = ml.amount_residual
                    if ml.account_id.account_type in report.PAYABLE_TYPES:
                        residual = -residual

                    detail_cmds.append(Command.create({
                        'move_line_id': ml.id,
                        'move_id': ml.move_id.id,
                        'date': ml.date,
                        'date_due': due_date,
                        'ref': ml.ref or ml.move_id.ref or '',
                        'days_overdue': max(days_ov, 0),
                        'original_amount': abs(ml.balance),
                        'residual_amount': residual,
                        'bucket': bucket_label,
                        'currency_id': report.currency_id.id,
                    }))

                partner_cmds.append(Command.create({
                    'partner_id': pd['partner'].id,
                    'name': pd['partner'].name or _('Unknown Partner'),
                    'not_due': pd['not_due'],
                    'bucket_1': pd['bucket_1'],
                    'bucket_2': pd['bucket_2'],
                    'bucket_3': pd['bucket_3'],
                    'bucket_4': pd['bucket_4'],
                    'bucket_5': pd['bucket_5'],
                    'total': pd['total'],
                    'currency_id': report.currency_id.id,
                    'line_ids': detail_cmds,
                }))

                total_not_due += pd['not_due']
                total_bucket_1 += pd['bucket_1']
                total_bucket_2 += pd['bucket_2']
                total_bucket_3 += pd['bucket_3']
                total_bucket_4 += pd['bucket_4']
                total_bucket_5 += pd['bucket_5']
                total_balance += pd['total']

            report.partner_line_ids = partner_cmds
            report.total_not_due = total_not_due
            report.total_bucket_1 = total_bucket_1
            report.total_bucket_2 = total_bucket_2
            report.total_bucket_3 = total_bucket_3
            report.total_bucket_4 = total_bucket_4
            report.total_bucket_5 = total_bucket_5
            report.total_balance = total_balance

    def action_generate_report(self):
        """Generate and display the Aged Partner Balance report."""
        self.ensure_one()
        if not self.date_to:
            raise UserError(_("Please specify the As of Date."))

        self._compute_report_data()

        report_name = {
            'receivable': _('Aged Receivables'),
            'payable': _('Aged Payables'),
            'both': _('Aged Partner Balances'),
        }.get(self.report_type)

        return {
            'name': f'{report_name} as of {self.date_to}',
            'type': 'ir.actions.act_window',
            'res_model': 'account.aged.partner.balance.report',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'inline',
        }


class AgedPartnerBalanceReportPartner(models.TransientModel):
    """Aged Partner Balance Partner Line."""
    _name = 'account.aged.partner.balance.report.partner'
    _description = 'Aged Partner Balance Report Partner'
    _order = 'name'

    report_id = fields.Many2one(
        comodel_name='account.aged.partner.balance.report',
        string='Report',
        ondelete='cascade',
    )
    partner_id = fields.Many2one('res.partner', string='Partner')
    name = fields.Char(string='Partner Name')

    # Aging buckets
    not_due = fields.Monetary(string='Not Due', currency_field='currency_id')
    bucket_1 = fields.Monetary(string='1-30', currency_field='currency_id')
    bucket_2 = fields.Monetary(string='31-60', currency_field='currency_id')
    bucket_3 = fields.Monetary(string='61-90', currency_field='currency_id')
    bucket_4 = fields.Monetary(string='91-120', currency_field='currency_id')
    bucket_5 = fields.Monetary(string='120+', currency_field='currency_id')
    total = fields.Monetary(string='Total', currency_field='currency_id')

    # Alias: amount_residual points to total for backward compatibility
    amount_residual = fields.Monetary(
        string='Residual Amount',
        currency_field='currency_id',
        related='total',
        readonly=True,
    )

    currency_id = fields.Many2one('res.currency', string='Currency')

    # Detail lines (for drill-down)
    line_ids = fields.One2many(
        comodel_name='account.aged.partner.balance.report.line',
        inverse_name='partner_line_id',
        string='Invoice Details',
    )

    def action_drilldown(self):
        """Open partner's open items."""
        self.ensure_one()

        # Determine account types based on report type
        account_types = []
        if self.report_id.report_type in ('receivable', 'both'):
            account_types.extend(self.report_id.RECEIVABLE_TYPES)
        if self.report_id.report_type in ('payable', 'both'):
            account_types.extend(self.report_id.PAYABLE_TYPES)

        accounts = self.env['account.account'].search([
            ('company_ids', 'in', self.report_id.company_id.ids),
            ('account_type', 'in', account_types),
        ])

        domain = [
            ('partner_id', '=', self.partner_id.id),
            ('account_id', 'in', accounts.ids),
            ('reconciled', '=', False),
            ('amount_residual', '!=', 0),
        ]

        return {
            'name': _('Open Items - %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'account.move.line',
            'view_mode': 'list,form',
            'domain': domain,
        }


class AgedPartnerBalanceReportLine(models.TransientModel):
    """Aged Partner Balance Detail Line (Invoice level)."""
    _name = 'account.aged.partner.balance.report.line'
    _description = 'Aged Partner Balance Report Line'
    _order = 'date_due'

    partner_line_id = fields.Many2one(
        comodel_name='account.aged.partner.balance.report.partner',
        string='Partner Line',
        ondelete='cascade',
    )
    move_line_id = fields.Many2one('account.move.line', string='Journal Item')
    move_id = fields.Many2one('account.move', string='Invoice/Bill')
    date = fields.Date(string='Date')
    date_due = fields.Date(string='Due Date')
    ref = fields.Char(string='Reference')
    days_overdue = fields.Integer(string='Days Overdue')

    original_amount = fields.Monetary(string='Original', currency_field='currency_id')
    residual_amount = fields.Monetary(string='Open Amount', currency_field='currency_id')
    bucket = fields.Char(string='Bucket')

    currency_id = fields.Many2one('res.currency', string='Currency')

    def action_open_move(self):
        """Open source invoice/bill."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.move_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
