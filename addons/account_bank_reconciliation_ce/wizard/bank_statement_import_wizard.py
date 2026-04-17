# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Bank Statement Import Wizard

TransientModel wizard providing the user-facing interface for importing
bank statement files.  Supports CSV, OFX, QIF, and CAMT.053 formats
with automatic format detection, CSV column mapping, preview of parsed
rows, and batch import with rollback on failure.

Implements FEATURE-002 BR-001 (Bank Statement Import) wizard acceptance
criteria.  Delegates actual file parsing, validation, and statement line
creation to ``account.bank.statement.import`` in the models package.

Performance target: import <10 seconds for 500 statement lines.
"""

import base64
import io
import logging

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

# Maximum allowed file size in bytes (10 MB).
_MAX_FILE_SIZE = 10 * 1024 * 1024


class BankStatementImportWizard(models.TransientModel):
    """Bank Statement Import Wizard — user interface for BR-001.

    Provides file upload, format detection, CSV column mapping,
    preview of parsed rows, and batch import execution.  All heavy
    parsing and validation is delegated to the
    ``account.bank.statement.import`` model.
    """

    _name = 'account.bank.statement.import.wizard'
    _description = 'Bank Statement Import Wizard'
    _check_company_auto = True

    # ------------------------------------------------------------------
    # FIELDS — Company / Journal
    # ------------------------------------------------------------------

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )

    journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Bank Journal',
        required=True,
        domain="[('type', 'in', ('bank', 'cash'))]",
        check_company=True,
        help='Select the bank or cash journal associated with this statement.',
    )

    # ------------------------------------------------------------------
    # FIELDS — File upload
    # ------------------------------------------------------------------

    data_file = fields.Binary(
        string='Bank Statement File',
        required=True,
        help='Select a bank statement file to import (CSV, OFX, QIF, or CAMT.053).',
    )

    filename = fields.Char(
        string='Filename',
    )

    auto_detect_format = fields.Boolean(
        string='Auto-detect Format',
        default=True,
        help='When enabled, the file format is automatically detected from '
             'the file extension and content signatures.',
    )

    file_format = fields.Selection(
        selection=[
            ('csv', 'CSV'),
            ('ofx', 'OFX'),
            ('qif', 'QIF'),
            ('camt053', 'CAMT.053'),
        ],
        string='File Format',
        help='Select the bank statement file format, or enable auto-detection.',
    )

    # ------------------------------------------------------------------
    # FIELDS — CSV configuration
    # ------------------------------------------------------------------

    csv_delimiter = fields.Char(
        string='CSV Delimiter',
        default=',',
        size=1,
        help='Single character used as column separator (e.g. comma, semicolon, tab).',
    )

    csv_encoding = fields.Char(
        string='File Encoding',
        default='utf-8',
        help='Character encoding of the CSV file (e.g. utf-8, latin-1, cp1252).',
    )

    csv_date_format = fields.Char(
        string='Date Format',
        default='%Y-%m-%d',
        help='Python strptime format string for parsing date values.',
    )

    csv_date_column = fields.Integer(
        string='Date Column',
        default=0,
        help='Zero-based column index for the transaction date.',
    )

    csv_label_column = fields.Integer(
        string='Label Column',
        default=1,
        help='Zero-based column index for the payment label or description.',
    )

    csv_amount_column = fields.Integer(
        string='Amount Column',
        default=2,
        help='Zero-based column index for the transaction amount.',
    )

    csv_ref_column = fields.Integer(
        string='Reference Column',
        default=-1,
        help='Column index for the payment reference.  Set to -1 to skip.',
    )

    csv_partner_column = fields.Integer(
        string='Partner Column',
        default=-1,
        help='Column index for the partner name.  Set to -1 to skip.',
    )

    csv_skip_header = fields.Boolean(
        string='Skip Header Row',
        default=True,
        help='Enable to skip the first row of the CSV file (column headers).',
    )

    # ------------------------------------------------------------------
    # FIELDS — Preview / results
    # ------------------------------------------------------------------

    preview_data = fields.Text(
        string='Preview',
        readonly=True,
        help='Preview of the first rows parsed from the uploaded file.',
    )

    preview_line_count = fields.Integer(
        string='Lines in Preview',
        readonly=True,
    )

    import_log = fields.Text(
        string='Import Log',
        readonly=True,
        help='Execution details, warnings, and errors from the import process.',
    )

    statement_ids = fields.Many2many(
        comodel_name='account.bank.statement',
        string='Created Statements',
        readonly=True,
    )

    line_count = fields.Integer(
        string='Imported Lines',
        readonly=True,
    )

    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('preview', 'Preview'),
            ('importing', 'Importing'),
            ('done', 'Done'),
            ('error', 'Error'),
        ],
        string='State',
        default='draft',
        readonly=True,
    )

    # ------------------------------------------------------------------
    # ONCHANGE HANDLERS
    # ------------------------------------------------------------------

    @api.onchange('data_file', 'filename')
    def _onchange_data_file(self):
        """Auto-detect format when a new file is uploaded."""
        if self.data_file and self.auto_detect_format:
            detected = self._detect_format()
            if detected:
                self.file_format = detected
                _logger.info(
                    'Auto-detected format %r from filename=%r',
                    detected,
                    self.filename,
                )

    @api.onchange('auto_detect_format')
    def _onchange_auto_detect_format(self):
        """Re-trigger format detection when auto-detect is toggled on."""
        if self.auto_detect_format and self.data_file:
            detected = self._detect_format()
            if detected:
                self.file_format = detected

    @api.onchange('file_format')
    def _onchange_file_format(self):
        """Reset CSV fields when format changes away from CSV."""
        if self.file_format and self.file_format != 'csv':
            # No reset needed — CSV fields are simply hidden in the view
            # via invisible="file_format != 'csv'".
            pass

    # ------------------------------------------------------------------
    # CONSTRAINT VALIDATORS
    # ------------------------------------------------------------------

    @api.constrains('data_file')
    def _check_data_file(self):
        """Ensure uploaded file is not empty and within size limits."""
        for wizard in self:
            if wizard.data_file:
                raw = base64.b64decode(wizard.data_file)
                if not raw:
                    raise ValidationError(
                        _('The uploaded file is empty. Please select a valid '
                          'bank statement file.'),
                    )
                if len(raw) > _MAX_FILE_SIZE:
                    raise ValidationError(
                        _('The uploaded file exceeds the maximum allowed size '
                          'of %d MB.') % (_MAX_FILE_SIZE // (1024 * 1024),),
                    )

    # ------------------------------------------------------------------
    # ACTION METHODS
    # ------------------------------------------------------------------

    def action_preview(self):
        """Parse the uploaded file and display a preview without importing.

        Decodes the base64 file content, delegates to the import model's
        ``_parse_file`` method to extract rows, runs
        ``_validate_imported_data`` to verify structural correctness, and
        formats the first N rows as readable text in ``preview_data``.

        Returns:
            dict: A window-action dict that re-opens this wizard to show
            the preview results.
        """
        self.ensure_one()
        self._validate_before_action()

        # Early-fail: ensure the binary payload can be decoded.
        raw_bytes = base64.b64decode(self.data_file)
        if not raw_bytes:
            raise UserError(_('The uploaded file is empty.'))

        import_rec = None
        try:
            import_model = self.env['account.bank.statement.import']
            import_rec = import_model.create(self._prepare_import_vals())

            # Delegate parsing to the import model.
            parsed_lines = import_rec._parse_file()

            # Run validation on parsed data so the preview reflects any
            # issues the user should address before the real import.
            try:
                import_rec._validate_imported_data(parsed_lines)
            except ValidationError as val_exc:
                # Validation errors during preview are non-fatal — we still
                # show the preview but include the warning in the log.
                _logger.warning(
                    'Validation warning during preview for %r: %s',
                    self.filename, val_exc,
                )
                validation_warning = str(
                    val_exc.args[0] if val_exc.args else val_exc,
                )
            else:
                validation_warning = ''

            # Build human-readable preview from first 10 rows.
            preview_limit = 10
            preview_rows = parsed_lines[:preview_limit]
            preview_parts = []
            header = '{:<12} {:<40} {:>14} {:<20} {:<20}'.format(
                'Date', 'Label', 'Amount', 'Reference', 'Partner',
            )
            preview_parts.append(header)
            preview_parts.append('-' * len(header))

            for row in preview_rows:
                date_str = str(row.get('date', ''))
                label = (row.get('payment_ref', '') or '')[:40]
                amount = row.get('amount', 0.0)
                ref = (row.get('ref', '') or '')[:20]
                partner = (row.get('partner_name', '') or '')[:20]
                preview_parts.append(
                    f'{date_str:<12} {label:<40} {amount:>14.2f} {ref:<20} {partner:<20}',
                )

            preview_parts.append('')
            preview_parts.append(
                _('Total lines in file: %d') % len(parsed_lines),
            )
            if validation_warning:
                preview_parts.append('')
                preview_parts.append(_('Validation warnings:'))
                preview_parts.append(validation_warning)

            log_msg = _('Preview generated successfully for %d lines.') % len(parsed_lines)
            if validation_warning:
                log_msg += '\n' + _('Note: validation warnings detected — see preview.')

            self.write({
                'preview_data': '\n'.join(preview_parts),
                'preview_line_count': len(parsed_lines),
                'state': 'preview',
                'import_log': log_msg,
            })

        except (UserError, ValidationError):
            raise
        except Exception as exc:
            _logger.exception('Error generating preview for file %r', self.filename)
            self.write({
                'preview_data': '',
                'preview_line_count': 0,
                'state': 'error',
                'import_log': _('Preview failed: %s') % str(exc),
            })
        finally:
            # Clean up the temporary import record if it was created.
            if import_rec:
                import_rec.unlink()

        return self._reopen_wizard()

    def action_import(self):
        """Execute the full import, creating bank statement records.

        Validates input, creates an ``account.bank.statement.import`` record
        with all wizard configuration, calls its ``action_import`` method,
        and populates result fields.  Uses a database savepoint so that
        partial records are rolled back cleanly on failure.

        Returns:
            dict: A window-action dict that re-opens this wizard to show
            import results or errors.
        """
        self.ensure_one()
        self._validate_before_action()

        self.write({'state': 'importing', 'import_log': ''})

        import_rec = None
        try:
            import_model = self.env['account.bank.statement.import']
            import_vals = self._prepare_import_vals()

            # Use a database savepoint so that any failure during import
            # (parsing, validation, or line creation) rolls back all
            # partially-created records, leaving the DB in a clean state.
            flush_uid = self.env.uid  # noqa: F841  - keep ref alive
            with self.env.cr.savepoint():
                import_rec = import_model.create(import_vals)

                # Execute import — the model handles parsing, validation,
                # duplicate detection, and batch statement line creation.
                import_rec.action_import()

                # Collect results from the import record.
                statements = import_rec.statement_ids
                total_lines = import_rec.line_count
                import_log_detail = import_rec.import_log or ''

            # If we reach here the savepoint committed successfully.
            log_parts = [
                _('Import completed successfully.'),
                _('Statements created/updated: %d') % len(statements),
                _('Total lines imported: %d') % total_lines,
            ]
            if import_log_detail:
                log_parts.append('')
                log_parts.append(import_log_detail)

            self.write({
                'statement_ids': [Command.set(statements.ids)],
                'line_count': total_lines,
                'state': 'done',
                'import_log': '\n'.join(log_parts),
            })
            _logger.info(
                'Successfully imported %d lines into %d statements for '
                'journal %r (wizard_id=%d)',
                total_lines,
                len(statements),
                self.journal_id.display_name,
                self.id,
            )

        except (UserError, ValidationError):
            # Re-raise Odoo business exceptions so users see proper messages.
            # The savepoint has already been rolled back automatically.
            raise
        except Exception as exc:
            # The savepoint context-manager rolls back all DB changes made
            # inside the ``with`` block on any unhandled exception, so
            # partially-created statement lines are cleaned up.
            _logger.exception(
                'Import failed for file %r on journal %r',
                self.filename,
                self.journal_id.display_name,
            )
            self.write({
                'state': 'error',
                'import_log': _('Import failed: %s') % str(exc),
            })

        return self._reopen_wizard()

    # ------------------------------------------------------------------
    # PRIVATE HELPER METHODS
    # ------------------------------------------------------------------

    def _detect_format(self):
        """Detect the file format from filename extension and content.

        Uses a two-tier approach:
        1. Local heuristics based on filename extension and binary content
           signatures for immediate feedback (e.g. during onchange).
        2. Delegation to ``account.bank.statement.import._detect_file_format``
           when a full import record is available, which provides more
           thorough detection including all CAMT.053 namespace versions.

        Returns:
            str or False: Detected format key (csv, ofx, qif, camt053)
            or False if detection fails.
        """
        self.ensure_one()

        # --- Attempt delegation to the import model's robust detector ---
        # Build a temporary in-memory record with enough data for detection.
        if self.data_file:
            try:
                ImportModel = self.env['account.bank.statement.import']
                # Use new() to avoid persisting a record just for detection.
                temp_rec = ImportModel.new({
                    'journal_id': self.journal_id.id or False,
                    'data_file': self.data_file,
                    'filename': self.filename or '',
                })
                detected = temp_rec._detect_file_format()
                if detected:
                    _logger.debug(
                        'Format detected via import model delegate: %r', detected,
                    )
                    return detected
            except Exception:  # noqa: BLE001  # intentional: fallback to heuristics on any delegate failure
                _logger.debug(
                    'Delegation to _detect_file_format failed; '
                    'falling back to local heuristics for %r',
                    self.filename,
                    exc_info=True,
                )

        # --- Fallback: local heuristics ---

        # 1. Extension-based detection.
        if self.filename:
            name_lower = self.filename.lower()
            if name_lower.endswith('.csv'):
                return 'csv'
            if name_lower.endswith(('.ofx', '.qfx')):
                return 'ofx'
            if name_lower.endswith('.qif'):
                return 'qif'
            if name_lower.endswith('.xml'):
                # Could be CAMT.053 — verify via content sniffing below.
                pass

        # 2. Content-based detection using in-memory streams.
        if self.data_file:
            try:
                raw = base64.b64decode(self.data_file)
                # Wrap in BytesIO for uniform stream-based inspection.
                stream = io.BytesIO(raw)
                header = stream.read(4096)

                if b'OFXHEADER' in header or b'<OFX>' in header:
                    return 'ofx'

                # Decode header to text for string-based checks.
                text_stream = io.StringIO(header.decode('utf-8', errors='replace'))
                text_header = text_stream.read()

                if text_header.lstrip().startswith('!Type:'):
                    return 'qif'

                # CAMT.053 namespace check.
                if 'urn:iso:std:iso:20022:tech:xsd:camt.053' in text_header:
                    return 'camt053'

                # If XML file by extension, default to CAMT.053.
                if self.filename and self.filename.lower().endswith('.xml'):
                    return 'camt053'

            except Exception:  # noqa: BLE001  # intentional: any decode/sniff failure returns False below
                _logger.debug(
                    'Content-based format detection failed for %r',
                    self.filename,
                    exc_info=True,
                )

        return False

    def _prepare_import_vals(self):
        """Build vals dict for ``account.bank.statement.import`` creation.

        Maps all wizard-level configuration fields onto the corresponding
        fields of the ``account.bank.statement.import`` model.

        Returns:
            dict: Field values for the import model record.
        """
        self.ensure_one()

        vals = {
            'journal_id': self.journal_id.id,
            'data_file': self.data_file,
            'filename': self.filename or '',
            'file_format': self.file_format or '',
            'auto_detect_format': self.auto_detect_format,
        }

        # Include CSV-specific settings when format is CSV or when
        # auto-detection might fall back to CSV.
        if self.file_format == 'csv' or (
            not self.file_format and self.auto_detect_format
        ):
            vals.update({
                'csv_delimiter': self.csv_delimiter or ',',
                'csv_encoding': self.csv_encoding or 'utf-8',
                'csv_date_format': self.csv_date_format or '%Y-%m-%d',
                'csv_date_column': self.csv_date_column,
                'csv_label_column': self.csv_label_column,
                'csv_amount_column': self.csv_amount_column,
                'csv_ref_column': self.csv_ref_column,
                'csv_partner_column': self.csv_partner_column,
                # Note: csv_skip_header lives only on the wizard UI; the
                # import model always skips the first row by design.
            })

        return vals

    def _validate_before_action(self):
        """Validate required inputs before preview or import.

        Raises:
            UserError: When mandatory fields are missing.
        """
        self.ensure_one()
        if not self.journal_id:
            raise UserError(
                _('Please select a bank or cash journal before proceeding.'),
            )
        if not self.data_file:
            raise UserError(
                _('Please upload a bank statement file before proceeding.'),
            )
        if not self.auto_detect_format and not self.file_format:
            raise UserError(
                _('Please select a file format or enable auto-detection.'),
            )

    def _reopen_wizard(self):
        """Return an action dict to re-display this wizard with updated data.

        Returns:
            dict: Window action dict targeting this wizard record.
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Import Bank Statement'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
