# -*- coding: utf-8 -*-
# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""
Bank Statement Import Model

Implements FEATURE-002 BR-001: Multi-format bank statement import logic.
Supports CSV (configurable column mapping), OFX (via ofxparse), QIF (text
parsing), and CAMT.053 (ISO 20022 XML via lxml.etree). Provides duplicate
detection by computing SHA256 hashes of statement line data, file type
auto-detection from content signatures and filename extensions, validation
of imported data, and batch line creation with company-scoped isolation.

Performance target: Statement import completes in <10 seconds for 500 lines.

Constraints:
- AGPL-3.0 license
- Zero dependencies on Odoo Enterprise modules
- OCA coding standards compliance
- Multi-company isolation on all queries
"""

import base64
import csv
import hashlib
import io
import logging
import re
from datetime import datetime, date

from odoo import api, fields, models, _, Command
from odoo.exceptions import UserError, ValidationError

# Conditional import for CAMT.053 XML parsing
try:
    from lxml import etree
except ImportError:
    etree = None

# Conditional import for OFX parsing
try:
    from ofxparse import OfxParser
except ImportError:
    OfxParser = None

_logger = logging.getLogger(__name__)

# CAMT.053 ISO 20022 namespace constants
CAMT_053_NS = 'urn:iso:std:iso:20022:tech:xsd:camt.053.001'
CAMT_053_VERSIONS = [
    'urn:iso:std:iso:20022:tech:xsd:camt.053.001.02',
    'urn:iso:std:iso:20022:tech:xsd:camt.053.001.03',
    'urn:iso:std:iso:20022:tech:xsd:camt.053.001.04',
    'urn:iso:std:iso:20022:tech:xsd:camt.053.001.06',
    'urn:iso:std:iso:20022:tech:xsd:camt.053.001.08',
]

# QIF date format patterns commonly used by financial institutions
QIF_DATE_FORMATS = [
    '%m/%d/%Y',
    '%d/%m/%Y',
    '%m-%d-%Y',
    '%d-%m-%Y',
    '%m/%d\'%y',
    '%Y-%m-%d',
    '%Y%m%d',
]


class BankStatementImport(models.TransientModel):
    """Bank Statement Import model for multi-format file parsing.

    This TransientModel provides the core import logic for BR-001,
    supporting CSV, OFX, QIF, and CAMT.053 bank statement formats.
    It handles file format auto-detection, parsing, validation,
    duplicate detection via SHA256 hashing, and batch creation of
    account.bank.statement.line records.

    Usage:
        wizard = self.env['account.bank.statement.import'].create({
            'journal_id': bank_journal.id,
            'data_file': base64_encoded_file,
            'filename': 'statement.csv',
        })
        wizard.action_import()
    """
    _name = 'account.bank.statement.import'
    _description = 'Bank Statement Import'

    # -------------------------------------------------------------------------
    # CORE FIELDS
    # -------------------------------------------------------------------------

    journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Bank Journal',
        required=True,
        domain=[('type', 'in', ('bank', 'cash'))],
        help="The bank or cash journal to import the statement into.",
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        related='journal_id.company_id',
        store=True,
        help="Company derived from the selected journal.",
    )
    data_file = fields.Binary(
        string='Bank Statement File',
        required=True,
        help="Upload the bank statement file in CSV, OFX, QIF, or CAMT.053 format.",
    )
    filename = fields.Char(
        string='Filename',
        help="Original filename of the uploaded bank statement.",
    )
    file_format = fields.Selection(
        selection=[
            ('csv', 'CSV'),
            ('ofx', 'OFX'),
            ('qif', 'QIF'),
            ('camt053', 'CAMT.053'),
        ],
        string='File Format',
        help="Format of the bank statement file. Leave empty for auto-detection.",
    )
    auto_detect_format = fields.Boolean(
        string='Auto-detect Format',
        default=True,
        help="Automatically detect the file format from content and extension.",
    )

    # -------------------------------------------------------------------------
    # CSV CONFIGURATION FIELDS
    # -------------------------------------------------------------------------

    csv_delimiter = fields.Char(
        string='CSV Delimiter',
        default=',',
        help="Column delimiter used in the CSV file (e.g., ',' or ';' or '\\t').",
    )
    csv_date_format = fields.Char(
        string='CSV Date Format',
        default='%Y-%m-%d',
        help="Python strftime format for date parsing (e.g., '%%Y-%%m-%%d' or '%%m/%%d/%%Y').",
    )
    csv_encoding = fields.Char(
        string='CSV Encoding',
        default='utf-8',
        help="Character encoding of the CSV file (e.g., 'utf-8', 'latin-1', 'cp1252').",
    )
    csv_date_column = fields.Integer(
        string='Date Column Index',
        default=0,
        help="Zero-based column index for the transaction date.",
    )
    csv_label_column = fields.Integer(
        string='Label Column Index',
        default=1,
        help="Zero-based column index for the transaction label/description.",
    )
    csv_amount_column = fields.Integer(
        string='Amount Column Index',
        default=2,
        help="Zero-based column index for the transaction amount.",
    )
    csv_ref_column = fields.Integer(
        string='Reference Column Index',
        default=-1,
        help="Zero-based column index for the transaction reference. Set -1 to skip.",
    )
    csv_partner_column = fields.Integer(
        string='Partner Column Index',
        default=-1,
        help="Zero-based column index for the partner name. Set -1 to skip.",
    )

    # -------------------------------------------------------------------------
    # RESULT FIELDS
    # -------------------------------------------------------------------------

    import_log = fields.Text(
        string='Import Log',
        readonly=True,
        help="Detailed log of the import process including warnings and errors.",
    )
    statement_ids = fields.Many2many(
        comodel_name='account.bank.statement',
        string='Created Statements',
        help="Bank statements created or updated during this import.",
    )
    line_count = fields.Integer(
        string='Imported Lines',
        compute='_compute_line_count',
        help="Total number of statement lines imported.",
    )

    # -------------------------------------------------------------------------
    # COMPUTE METHODS
    # -------------------------------------------------------------------------

    @api.depends('statement_ids', 'statement_ids.line_ids')
    def _compute_line_count(self):
        """Compute the total number of lines across all created statements."""
        for record in self:
            if record.statement_ids:
                record.line_count = sum(
                    len(stmt.line_ids) for stmt in record.statement_ids
                )
            else:
                record.line_count = 0

    # -------------------------------------------------------------------------
    # FORMAT DETECTION
    # -------------------------------------------------------------------------

    def _detect_file_format(self):
        """Auto-detect file format from filename extension and content signatures.

        Detection priority:
        1. Filename extension (.ofx/.qfx, .qif, .xml, .csv)
        2. Content signature analysis (OFX headers, QIF type markers,
           CAMT.053 XML namespaces)
        3. Default to CSV if no match found

        Returns:
            str: Detected format ('csv', 'ofx', 'qif', 'camt053')
        """
        self.ensure_one()

        if not self.data_file:
            raise UserError(_("No file uploaded for format detection."))

        raw_data = base64.b64decode(self.data_file)

        # Step 1: Check filename extension
        if self.filename:
            filename_lower = self.filename.lower().strip()
            if filename_lower.endswith(('.ofx', '.qfx')):
                _logger.info(
                    "Format detected from extension: OFX (file: %s)",
                    self.filename,
                )
                return 'ofx'
            if filename_lower.endswith('.qif'):
                _logger.info(
                    "Format detected from extension: QIF (file: %s)",
                    self.filename,
                )
                return 'qif'
            if filename_lower.endswith('.xml'):
                # XML could be CAMT.053 - verify content below
                pass
            if filename_lower.endswith('.csv'):
                _logger.info(
                    "Format detected from extension: CSV (file: %s)",
                    self.filename,
                )
                return 'csv'

        # Step 2: Content signature analysis
        # Try decoding as text for signature matching
        try:
            text_content = raw_data[:4096].decode('utf-8', errors='replace')
        except Exception:
            text_content = raw_data[:4096].decode('latin-1', errors='replace')

        # Check for OFX signatures
        if re.search(r'OFXHEADER', text_content) or re.search(r'<\?OFX', text_content):
            _logger.info(
                "Format detected from content signature: OFX (file: %s)",
                self.filename or 'unknown',
            )
            return 'ofx'

        # Check for QIF signature
        if re.match(r'^!Type:', text_content, re.MULTILINE):
            _logger.info(
                "Format detected from content signature: QIF (file: %s)",
                self.filename or 'unknown',
            )
            return 'qif'

        # Check for CAMT.053 XML namespace
        for ns_version in CAMT_053_VERSIONS:
            if re.search(re.escape(ns_version), text_content):
                _logger.info(
                    "Format detected from content signature: CAMT.053 (file: %s)",
                    self.filename or 'unknown',
                )
                return 'camt053'

        # Check for generic CAMT namespace
        if re.search(r'urn:iso:std:iso:20022:tech:xsd:camt\.053', text_content):
            _logger.info(
                "Format detected from content signature: CAMT.053 (file: %s)",
                self.filename or 'unknown',
            )
            return 'camt053'

        # Step 3: Default to CSV
        _logger.info(
            "No specific format detected, defaulting to CSV (file: %s)",
            self.filename or 'unknown',
        )
        return 'csv'

    # -------------------------------------------------------------------------
    # DUPLICATE DETECTION
    # -------------------------------------------------------------------------

    @api.model
    def _compute_import_hash(self, values):
        """Compute a SHA256 hash from statement line data for duplicate detection.

        The hash is computed from the combination of date, amount, and reference
        to uniquely identify a transaction. This prevents re-importing the same
        bank transactions when a statement file is uploaded multiple times.

        Args:
            values (dict): Parsed line data containing 'date', 'amount',
                           and optionally 'ref' or 'payment_ref'.

        Returns:
            str: Hex digest of the SHA256 hash.
        """
        hash_data = '{date}|{amount}|{ref}'.format(
            date=str(values.get('date', '')),
            amount=str(values.get('amount', 0.0)),
            ref=str(values.get('ref', values.get('payment_ref', ''))),
        )
        return hashlib.sha256(hash_data.encode('utf-8')).hexdigest()

    def _check_duplicate(self, hash_val):
        """Check if a statement line with the given import hash already exists.

        Searches for existing statement lines in the same journal and company
        that have a matching import hash value stored in transaction_details.

        Args:
            hash_val (str): SHA256 hex digest to search for.

        Returns:
            bool: True if a duplicate exists, False otherwise.
        """
        self.ensure_one()
        # Search in transaction_details JSON field for matching import_hash
        existing = self.env['account.bank.statement.line'].search([
            ('journal_id', '=', self.journal_id.id),
            ('company_id', '=', self.company_id.id),
            ('transaction_details', 'like', hash_val),
        ], limit=1)
        if existing:
            _logger.warning(
                "Duplicate statement line detected (hash: %s) in journal %s",
                hash_val[:16],
                self.journal_id.display_name,
            )
            return True
        return False

    # -------------------------------------------------------------------------
    # MAIN IMPORT ACTION
    # -------------------------------------------------------------------------

    def action_import(self):
        """Main import action: detect format, parse file, validate, and create lines.

        This is the primary entry point called from the import wizard. It orchestrates
        the complete import workflow:
        1. Detect or validate file format
        2. Decode and parse the file
        3. Validate parsed data
        4. Create statement lines with duplicate checking

        Returns:
            dict: Action dictionary to display import results or stay on wizard.

        Raises:
            UserError: If no file is uploaded, format is unsupported, or
                       import validation fails.
        """
        self.ensure_one()
        log_lines = []

        if not self.data_file:
            raise UserError(_("Please upload a bank statement file."))

        # Step 1: Detect file format
        if self.auto_detect_format or not self.file_format:
            detected_format = self._detect_file_format()
            self.file_format = detected_format
            log_lines.append(_("Auto-detected format: %s") % detected_format.upper())
        else:
            log_lines.append(_("Using specified format: %s") % self.file_format.upper())

        _logger.info(
            "Starting bank statement import: journal=%s, format=%s, file=%s",
            self.journal_id.display_name,
            self.file_format,
            self.filename or 'unknown',
        )

        # Step 2: Parse file
        try:
            parsed_lines = self._parse_file()
        except Exception as exc:
            _logger.error(
                "Failed to parse bank statement file: %s", str(exc),
            )
            raise UserError(
                _("Failed to parse the bank statement file.\n\nError: %s") % str(exc)
            ) from exc

        log_lines.append(_("Parsed %d transaction lines.") % len(parsed_lines))

        # Step 3: Validate parsed data
        try:
            self._validate_imported_data(parsed_lines)
        except ValidationError as exc:
            log_lines.append(_("Validation failed: %s") % str(exc.args[0] if exc.args else exc))
            self.import_log = '\n'.join(log_lines)
            raise

        log_lines.append(_("Data validation passed."))

        # Step 4: Create statement lines
        created_lines, duplicate_count = self._create_statement_lines(
            self.journal_id, parsed_lines
        )

        if duplicate_count > 0:
            log_lines.append(
                _("Skipped %d duplicate lines.") % duplicate_count
            )

        log_lines.append(
            _("Successfully imported %d lines.") % len(created_lines)
        )

        self.import_log = '\n'.join(log_lines)

        _logger.info(
            "Bank statement import completed: %d lines imported, %d duplicates skipped",
            len(created_lines),
            duplicate_count,
        )

        # Return action to show results
        if self.statement_ids:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Imported Statements'),
                'res_model': 'account.bank.statement',
                'view_mode': 'list,form',
                'domain': [('id', 'in', self.statement_ids.ids)],
                'target': 'current',
            }

        return {
            'type': 'ir.actions.act_window',
            'name': _('Import Result'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    # -------------------------------------------------------------------------
    # FILE PARSING DISPATCH
    # -------------------------------------------------------------------------

    def _parse_file(self):
        """Route to the correct parser based on the detected/selected file_format.

        Decodes the base64-encoded data_file and dispatches to the appropriate
        format-specific parser method.

        Returns:
            list[dict]: List of parsed line dictionaries, each containing:
                - date (str or date): Transaction date
                - payment_ref (str): Transaction label/description
                - amount (float): Transaction amount (positive for credit, negative for debit)
                - ref (str): Transaction reference (optional)
                - partner_name (str): Counterparty name (optional)

        Raises:
            UserError: If file format is not set or unsupported.
        """
        self.ensure_one()

        if not self.file_format:
            raise UserError(_("File format is not set. Please select or auto-detect the format."))

        raw_data = base64.b64decode(self.data_file)

        parser_map = {
            'csv': self._parse_csv,
            'ofx': self._parse_ofx,
            'qif': self._parse_qif,
            'camt053': self._parse_camt053,
        }

        parser = parser_map.get(self.file_format)
        if not parser:
            raise UserError(
                _("Unsupported file format: %s") % self.file_format
            )

        return parser(raw_data)

    # -------------------------------------------------------------------------
    # CSV PARSER
    # -------------------------------------------------------------------------

    def _parse_csv(self, data_file):
        """Parse a CSV bank statement file with configurable column mapping.

        Reads the CSV file using the configured delimiter, encoding, and column
        mapping fields (csv_date_column, csv_label_column, csv_amount_column,
        csv_ref_column, csv_partner_column). The first row is treated as a
        header and skipped.

        Args:
            data_file (bytes): Raw CSV file content.

        Returns:
            list[dict]: Parsed transaction lines with keys:
                date, payment_ref, amount, ref, partner_name

        Raises:
            UserError: If the CSV file cannot be decoded or parsed.
        """
        self.ensure_one()
        lines = []
        encoding = self.csv_encoding or 'utf-8'
        delimiter = self.csv_delimiter or ','

        # Handle tab delimiter notation
        if delimiter in ('\\t', 'tab', 'TAB'):
            delimiter = '\t'

        try:
            text_data = data_file.decode(encoding)
        except (UnicodeDecodeError, LookupError) as exc:
            raise UserError(
                _("Cannot decode the CSV file with encoding '%s'. "
                  "Please verify the encoding setting.\n\nError: %s")
                % (encoding, str(exc))
            ) from exc

        reader = csv.reader(io.StringIO(text_data), delimiter=delimiter)

        # Skip header row
        try:
            header = next(reader)
            _logger.debug("CSV header: %s", header)
        except StopIteration:
            raise UserError(_("The CSV file is empty."))

        date_format = self.csv_date_format or '%Y-%m-%d'
        row_number = 1  # 1-based (header is row 0)

        for row in reader:
            row_number += 1
            if not row or all(cell.strip() == '' for cell in row):
                continue  # skip empty rows

            try:
                max_col = max(
                    self.csv_date_column,
                    self.csv_label_column,
                    self.csv_amount_column,
                )
                if self.csv_ref_column >= 0:
                    max_col = max(max_col, self.csv_ref_column)
                if self.csv_partner_column >= 0:
                    max_col = max(max_col, self.csv_partner_column)

                if len(row) <= max_col:
                    _logger.warning(
                        "CSV row %d has %d columns, expected at least %d. Skipping.",
                        row_number, len(row), max_col + 1,
                    )
                    continue

                # Parse date
                date_str = row[self.csv_date_column].strip()
                try:
                    parsed_date = datetime.strptime(date_str, date_format).date()
                except ValueError:
                    _logger.warning(
                        "CSV row %d: invalid date '%s' for format '%s'. Skipping.",
                        row_number, date_str, date_format,
                    )
                    continue

                # Parse amount
                amount_str = row[self.csv_amount_column].strip()
                amount_str = re.sub(r'[^\d.\-+,]', '', amount_str)
                # Handle European number format (comma as decimal separator)
                if ',' in amount_str and '.' not in amount_str:
                    amount_str = amount_str.replace(',', '.')
                elif ',' in amount_str and '.' in amount_str:
                    # e.g., "1,234.56" or "1.234,56"
                    if amount_str.rfind(',') > amount_str.rfind('.'):
                        # European: "1.234,56"
                        amount_str = amount_str.replace('.', '').replace(',', '.')
                    else:
                        # US/UK: "1,234.56"
                        amount_str = amount_str.replace(',', '')

                try:
                    amount = float(amount_str)
                except (ValueError, TypeError):
                    _logger.warning(
                        "CSV row %d: invalid amount '%s'. Skipping.",
                        row_number, row[self.csv_amount_column].strip(),
                    )
                    continue

                # Parse label
                payment_ref = row[self.csv_label_column].strip()

                # Parse optional reference
                ref = ''
                if self.csv_ref_column >= 0 and self.csv_ref_column < len(row):
                    ref = row[self.csv_ref_column].strip()

                # Parse optional partner name
                partner_name = ''
                if self.csv_partner_column >= 0 and self.csv_partner_column < len(row):
                    partner_name = row[self.csv_partner_column].strip()

                lines.append({
                    'date': parsed_date,
                    'payment_ref': payment_ref,
                    'amount': amount,
                    'ref': ref,
                    'partner_name': partner_name,
                })

            except (IndexError, ValueError) as exc:
                _logger.warning(
                    "CSV row %d: parsing error: %s. Skipping.",
                    row_number, str(exc),
                )
                continue

        _logger.info("CSV parsing complete: %d lines parsed from %s", len(lines), self.filename or 'unknown')
        return lines

    # -------------------------------------------------------------------------
    # OFX PARSER
    # -------------------------------------------------------------------------

    def _parse_ofx(self, data_file):
        """Parse an OFX/QFX bank statement file using ofxparse.

        Uses the ofxparse library to extract account information and transaction
        details from OFX (Open Financial Exchange) format files. The OFX format
        is commonly used by US and Canadian banks.

        Args:
            data_file (bytes): Raw OFX file content.

        Returns:
            list[dict]: Parsed transaction lines with keys:
                date, payment_ref, amount, ref, partner_name

        Raises:
            UserError: If ofxparse library is not installed or parsing fails.
        """
        self.ensure_one()

        if OfxParser is None:
            raise UserError(
                _("The 'ofxparse' Python library is required to import OFX files. "
                  "Please install it with: pip install ofxparse")
            )

        lines = []
        try:
            ofx = OfxParser.parse(io.BytesIO(data_file))
        except Exception as exc:
            raise UserError(
                _("Failed to parse the OFX file.\n\nError: %s") % str(exc)
            ) from exc

        if not ofx.account:
            raise UserError(
                _("The OFX file does not contain any account information.")
            )

        account = ofx.account
        _logger.info(
            "OFX account found: account_id=%s, routing=%s, institution=%s",
            getattr(account, 'account_id', 'N/A'),
            getattr(account, 'routing_number', 'N/A'),
            getattr(account, 'institution', 'N/A'),
        )

        statement = getattr(account, 'statement', None)
        if not statement:
            raise UserError(
                _("The OFX file does not contain any statement data.")
            )

        transactions = getattr(statement, 'transactions', [])
        if not transactions:
            _logger.warning("OFX file contains no transactions.")
            return lines

        for txn in transactions:
            # Extract transaction date
            txn_date = getattr(txn, 'date', None)
            if txn_date:
                if isinstance(txn_date, datetime):
                    txn_date = txn_date.date()
                elif not isinstance(txn_date, date):
                    try:
                        txn_date = datetime.strptime(str(txn_date), '%Y-%m-%d').date()
                    except (ValueError, TypeError):
                        txn_date = date.today()
            else:
                txn_date = date.today()

            # Extract amount
            txn_amount = float(getattr(txn, 'amount', 0.0))

            # Build the label from memo and payee
            memo = str(getattr(txn, 'memo', '') or '')
            payee = str(getattr(txn, 'payee', '') or '')
            payment_ref = memo or payee or _('OFX Transaction')

            # Extract unique transaction ID as reference
            fitid = str(getattr(txn, 'id', '') or '')

            # Extract transaction type
            txn_type = str(getattr(txn, 'type', '') or '')

            lines.append({
                'date': txn_date,
                'payment_ref': payment_ref,
                'amount': txn_amount,
                'ref': fitid,
                'partner_name': payee,
                'transaction_type': txn_type,
            })

        _logger.info("OFX parsing complete: %d transactions parsed", len(lines))
        return lines

    # -------------------------------------------------------------------------
    # QIF PARSER
    # -------------------------------------------------------------------------

    def _parse_qif(self, data_file):
        """Parse a QIF (Quicken Interchange Format) bank statement file.

        QIF is a plain text format where each transaction is a block of lines
        prefixed by field type codes:
          D = Date
          T = Amount
          P = Payee
          N = Reference/Check number
          M = Memo
          ^  = End of transaction record

        Args:
            data_file (bytes): Raw QIF file content.

        Returns:
            list[dict]: Parsed transaction lines with keys:
                date, payment_ref, amount, ref, partner_name

        Raises:
            UserError: If the QIF file cannot be decoded or contains no data.
        """
        self.ensure_one()
        lines = []

        # Try decoding with common encodings
        text_data = None
        for encoding in ('utf-8', 'latin-1', 'cp1252'):
            try:
                text_data = data_file.decode(encoding)
                break
            except (UnicodeDecodeError, LookupError):
                continue

        if text_data is None:
            raise UserError(
                _("Cannot decode the QIF file. Please verify the file encoding.")
            )

        # Initialize current transaction accumulator
        current_txn = {}
        in_transactions = False

        for line in text_data.splitlines():
            line = line.strip()
            if not line:
                continue

            # Detect the transaction type header
            if line.startswith('!Type:'):
                in_transactions = True
                continue

            if not in_transactions:
                continue

            # Parse field codes
            if line.startswith('D'):
                # Date field
                date_str = line[1:].strip()
                current_txn['date_str'] = date_str
            elif line.startswith('T') or line.startswith('U'):
                # Amount field (T = total amount, U = amount in split)
                amount_str = line[1:].strip()
                amount_str = re.sub(r'[^\d.\-+,]', '', amount_str)
                if ',' in amount_str and '.' not in amount_str:
                    amount_str = amount_str.replace(',', '.')
                elif ',' in amount_str:
                    amount_str = amount_str.replace(',', '')
                try:
                    current_txn['amount'] = float(amount_str)
                except (ValueError, TypeError):
                    current_txn['amount'] = 0.0
            elif line.startswith('P'):
                # Payee field
                current_txn['payee'] = line[1:].strip()
            elif line.startswith('N'):
                # Reference/check number
                current_txn['ref'] = line[1:].strip()
            elif line.startswith('M'):
                # Memo field
                current_txn['memo'] = line[1:].strip()
            elif line.startswith('^'):
                # End of transaction record
                if current_txn:
                    parsed_line = self._finalize_qif_transaction(current_txn)
                    if parsed_line:
                        lines.append(parsed_line)
                current_txn = {}

        # Handle last transaction if file doesn't end with ^
        if current_txn:
            parsed_line = self._finalize_qif_transaction(current_txn)
            if parsed_line:
                lines.append(parsed_line)

        _logger.info("QIF parsing complete: %d transactions parsed", len(lines))
        return lines

    def _finalize_qif_transaction(self, txn_data):
        """Convert raw QIF transaction data into a standardized line dict.

        Handles QIF date format parsing by trying multiple common date formats
        used by various financial institutions.

        Args:
            txn_data (dict): Raw QIF field data with keys like 'date_str',
                             'amount', 'payee', 'ref', 'memo'.

        Returns:
            dict or None: Parsed transaction line, or None if date is invalid.
        """
        # Parse QIF date (various formats: M/D/Y, D/M/Y, M/D'Y, etc.)
        date_str = txn_data.get('date_str', '')
        parsed_date = None

        for fmt in QIF_DATE_FORMATS:
            try:
                parsed_date = datetime.strptime(date_str, fmt).date()
                break
            except (ValueError, TypeError):
                continue

        if parsed_date is None:
            _logger.warning(
                "QIF: could not parse date '%s'. Skipping transaction.", date_str,
            )
            return None

        amount = txn_data.get('amount', 0.0)
        payee = txn_data.get('payee', '')
        memo = txn_data.get('memo', '')
        ref = txn_data.get('ref', '')
        payment_ref = payee or memo or _('QIF Transaction')

        return {
            'date': parsed_date,
            'payment_ref': payment_ref,
            'amount': amount,
            'ref': ref,
            'partner_name': payee,
        }

    # -------------------------------------------------------------------------
    # CAMT.053 PARSER
    # -------------------------------------------------------------------------

    def _parse_camt053(self, data_file):
        """Parse a CAMT.053 (ISO 20022) bank-to-customer statement XML file.

        Navigates the XML element hierarchy:
        Document > BkToCstmrStmt > Stmt > Ntry (entries)

        Each Ntry element contains:
        - Amt: Transaction amount with Ccy attribute
        - CdtDbtInd: Credit/Debit indicator (CRDT/DBIT)
        - BookgDt/Dt or ValDt/Dt: Booking or value date
        - NtryRef: Entry reference
        - NtryDtls/TxDtls: Detailed transaction information
        - NtryDtls/TxDtls/Refs/EndToEndId: End-to-end reference
        - NtryDtls/TxDtls/RltdPties/Dbtr/Nm or Cdtr/Nm: Counterparty name
        - AddtlNtryInf: Additional entry information (used as label)

        Args:
            data_file (bytes): Raw CAMT.053 XML file content.

        Returns:
            list[dict]: Parsed transaction lines with keys:
                date, payment_ref, amount, ref, partner_name

        Raises:
            UserError: If lxml is not installed or XML parsing fails.
        """
        self.ensure_one()

        if etree is None:
            raise UserError(
                _("The 'lxml' Python library is required to import CAMT.053 files. "
                  "Please install it with: pip install lxml")
            )

        lines = []

        try:
            root = etree.fromstring(data_file)
        except Exception as exc:
            raise UserError(
                _("Failed to parse the CAMT.053 XML file.\n\nError: %s") % str(exc)
            ) from exc

        # Detect the namespace from the root element
        ns = self._detect_camt_namespace(root)
        if not ns:
            raise UserError(
                _("The XML file does not appear to be a valid CAMT.053 statement. "
                  "No recognized ISO 20022 CAMT.053 namespace found.")
            )

        ns_map = {'ns': ns}

        # Navigate: Document > BkToCstmrStmt > Stmt
        statements = root.findall('.//ns:Stmt', ns_map)
        if not statements:
            raise UserError(
                _("No statement (Stmt) elements found in the CAMT.053 file.")
            )

        for stmt_elem in statements:
            entries = stmt_elem.findall('ns:Ntry', ns_map)
            _logger.info(
                "CAMT.053: processing statement with %d entries", len(entries),
            )

            for entry in entries:
                parsed_line = self._parse_camt053_entry(entry, ns_map)
                if parsed_line:
                    lines.append(parsed_line)

        _logger.info("CAMT.053 parsing complete: %d transactions parsed", len(lines))
        return lines

    def _detect_camt_namespace(self, root):
        """Detect the CAMT.053 XML namespace from the root element.

        Checks the root tag against known CAMT.053 namespace versions
        (v02 through v08).

        Args:
            root: lxml Element for the document root.

        Returns:
            str or None: The detected namespace URI, or None if not recognized.
        """
        # Extract namespace from the root tag using QName
        try:
            qname = etree.QName(root.tag)
            root_ns = qname.namespace
        except (ValueError, TypeError):
            root_ns = None

        if root_ns:
            for ns_version in CAMT_053_VERSIONS:
                if root_ns == ns_version:
                    return ns_version
            # Check if it's a generic CAMT.053 namespace
            if 'camt.053' in root_ns:
                return root_ns

        # Fallback: scan nsmap for known CAMT.053 namespaces
        nsmap = getattr(root, 'nsmap', {})
        for prefix, uri in nsmap.items():
            for ns_version in CAMT_053_VERSIONS:
                if uri == ns_version:
                    return ns_version
            if uri and 'camt.053' in uri:
                return uri

        return None

    def _parse_camt053_entry(self, entry, ns_map):
        """Parse a single CAMT.053 Ntry (entry) element into a line dict.

        Args:
            entry: lxml Element representing an Ntry node.
            ns_map (dict): Namespace mapping for XPath queries.

        Returns:
            dict or None: Parsed transaction line, or None if parsing fails.
        """
        try:
            # Extract amount
            amt_elem = entry.find('ns:Amt', ns_map)
            if amt_elem is not None and amt_elem.text:
                amount = float(amt_elem.text.strip())
            else:
                amount = 0.0

            # Apply credit/debit indicator
            cdi_elem = entry.find('ns:CdtDbtInd', ns_map)
            if cdi_elem is not None and cdi_elem.text:
                if cdi_elem.text.strip().upper() == 'DBIT':
                    amount = -abs(amount)
                else:
                    amount = abs(amount)

            # Extract date (BookgDt > ValDt fallback)
            parsed_date = None
            for date_path in ('ns:BookgDt/ns:Dt', 'ns:ValDt/ns:Dt'):
                dt_elem = entry.find(date_path, ns_map)
                if dt_elem is not None and dt_elem.text:
                    try:
                        parsed_date = datetime.strptime(
                            dt_elem.text.strip(), '%Y-%m-%d'
                        ).date()
                        break
                    except ValueError:
                        continue

            if parsed_date is None:
                parsed_date = date.today()

            # Extract reference
            ref = ''
            # Try NtryRef first
            ntry_ref = entry.find('ns:NtryRef', ns_map)
            if ntry_ref is not None and ntry_ref.text:
                ref = ntry_ref.text.strip()

            # Try EndToEndId from transaction details
            e2e_path = 'ns:NtryDtls/ns:TxDtls/ns:Refs/ns:EndToEndId'
            e2e_elem = entry.find(e2e_path, ns_map)
            if e2e_elem is not None and e2e_elem.text:
                e2e_ref = e2e_elem.text.strip()
                if e2e_ref and e2e_ref != 'NOTPROVIDED':
                    ref = ref or e2e_ref

            # Extract payment reference / label
            payment_ref = ''
            # Try AddtlNtryInf (additional entry information)
            addtl_elem = entry.find('ns:AddtlNtryInf', ns_map)
            if addtl_elem is not None and addtl_elem.text:
                payment_ref = addtl_elem.text.strip()

            # Try RmtInf/Ustrd (unstructured remittance information)
            if not payment_ref:
                ustrd_path = 'ns:NtryDtls/ns:TxDtls/ns:RmtInf/ns:Ustrd'
                ustrd_elem = entry.find(ustrd_path, ns_map)
                if ustrd_elem is not None and ustrd_elem.text:
                    payment_ref = ustrd_elem.text.strip()

            if not payment_ref:
                payment_ref = ref or _('CAMT.053 Transaction')

            # Extract partner name from counterparty
            partner_name = ''
            # For credits, look at debtor; for debits, look at creditor
            for party_path in (
                'ns:NtryDtls/ns:TxDtls/ns:RltdPties/ns:Dbtr/ns:Nm',
                'ns:NtryDtls/ns:TxDtls/ns:RltdPties/ns:Cdtr/ns:Nm',
            ):
                party_elem = entry.find(party_path, ns_map)
                if party_elem is not None and party_elem.text:
                    partner_name = party_elem.text.strip()
                    break

            return {
                'date': parsed_date,
                'payment_ref': payment_ref,
                'amount': amount,
                'ref': ref,
                'partner_name': partner_name,
            }

        except Exception as exc:
            _logger.warning(
                "CAMT.053: failed to parse entry: %s", str(exc),
            )
            return None

    # -------------------------------------------------------------------------
    # DATA VALIDATION
    # -------------------------------------------------------------------------

    def _validate_imported_data(self, parsed_data):
        """Validate parsed statement line data before creating records.

        Checks:
        1. Data is not empty
        2. Required fields (date, amount) are present and valid
        3. Date values are proper date objects or parseable strings
        4. Amount values are numeric (int or float)

        Args:
            parsed_data (list[dict]): List of parsed line dictionaries.

        Raises:
            ValidationError: If validation fails with a descriptive message.
        """
        self.ensure_one()

        if not parsed_data:
            raise ValidationError(
                _("The file does not contain any valid transaction data. "
                  "Please check the file format and content.")
            )

        errors = []

        for idx, line_data in enumerate(parsed_data, start=1):
            # Check required fields
            if 'date' not in line_data or not line_data['date']:
                errors.append(
                    _("Line %d: missing or empty date field.") % idx
                )
            elif not isinstance(line_data['date'], date):
                # Try to parse as string
                if isinstance(line_data['date'], str):
                    try:
                        datetime.strptime(line_data['date'], '%Y-%m-%d')
                    except ValueError:
                        errors.append(
                            _("Line %d: invalid date format '%s'. Expected YYYY-MM-DD.")
                            % (idx, line_data['date'])
                        )
                else:
                    errors.append(
                        _("Line %d: date must be a date object or string, got %s.")
                        % (idx, type(line_data['date']).__name__)
                    )

            if 'amount' not in line_data:
                errors.append(
                    _("Line %d: missing amount field.") % idx
                )
            elif not isinstance(line_data['amount'], (int, float)):
                errors.append(
                    _("Line %d: amount must be numeric, got '%s'.")
                    % (idx, line_data['amount'])
                )

            if not line_data.get('payment_ref'):
                _logger.debug(
                    "Line %d: no payment_ref provided, will use default label.",
                    idx,
                )

        if errors:
            # Limit displayed errors to prevent overwhelming the user
            max_display = 20
            error_msg = '\n'.join(errors[:max_display])
            if len(errors) > max_display:
                error_msg += _("\n... and %d more errors.") % (len(errors) - max_display)
            raise ValidationError(error_msg)

        _logger.info("Validation passed for %d parsed lines.", len(parsed_data))

    # -------------------------------------------------------------------------
    # STATEMENT LINE CREATION
    # -------------------------------------------------------------------------

    def _create_statement_lines(self, journal, parsed_lines):
        """Create account.bank.statement.line records from parsed data.

        For each parsed line:
        1. Compute import hash for duplicate detection
        2. Skip if duplicate exists
        3. Attempt partner matching by name
        4. Create the statement line record

        Statement lines are created directly (without an enclosing statement),
        as Odoo's account.bank.statement model manages grouping automatically
        through computed fields.

        Args:
            journal (recordset): account.journal record for the bank journal.
            parsed_lines (list[dict]): Validated parsed line dictionaries.

        Returns:
            tuple: (created_lines recordset, duplicate_count int)
        """
        self.ensure_one()

        StLine = self.env['account.bank.statement.line']
        created_lines = StLine
        duplicate_count = 0
        batch_vals = []

        for line_data in parsed_lines:
            # Compute import hash for duplicate detection
            import_hash = self._compute_import_hash(line_data)

            # Check for duplicate
            if self._check_duplicate(import_hash):
                duplicate_count += 1
                continue

            # Ensure date is a proper date object
            line_date = line_data.get('date')
            if isinstance(line_date, str):
                try:
                    line_date = datetime.strptime(line_date, '%Y-%m-%d').date()
                except ValueError:
                    line_date = date.today()

            # Attempt partner matching
            partner_name = line_data.get('partner_name', '')
            partner = self.env['res.partner']
            if partner_name:
                partner = self._get_partner_from_name(partner_name)

            # Build statement line values
            line_vals = {
                'journal_id': journal.id,
                'date': line_date,
                'payment_ref': line_data.get('payment_ref', '') or _('Imported Transaction'),
                'amount': line_data.get('amount', 0.0),
                'partner_id': partner.id if partner else False,
                'partner_name': partner_name,
                'transaction_details': {
                    'import_hash': import_hash,
                    'import_source': self.filename or '',
                    'import_format': self.file_format or '',
                    'original_ref': line_data.get('ref', ''),
                },
            }

            # Set the reference if available
            if line_data.get('ref'):
                line_vals['payment_ref'] = '%s - %s' % (
                    line_data.get('payment_ref', ''),
                    line_data['ref'],
                ) if line_data.get('payment_ref') else line_data['ref']

            # Set transaction_type if available (from OFX parser)
            if line_data.get('transaction_type'):
                line_vals['transaction_type'] = line_data['transaction_type']

            batch_vals.append(line_vals)

        # Batch create statement lines for performance
        if batch_vals:
            _logger.info(
                "Creating %d statement lines in journal '%s'",
                len(batch_vals),
                journal.display_name,
            )
            try:
                created_lines = StLine.with_context(
                    is_statement_line=True,
                ).create(batch_vals)
            except Exception as exc:
                _logger.error(
                    "Failed to create statement lines: %s", str(exc),
                )
                raise UserError(
                    _("Failed to create statement lines.\n\nError: %s") % str(exc)
                ) from exc

            # Collect associated statements for the result
            statement_ids = created_lines.mapped('statement_id')
            if statement_ids:
                self.statement_ids = [(6, 0, statement_ids.ids)]

        _logger.info(
            "Statement line creation complete: %d created, %d duplicates",
            len(created_lines),
            duplicate_count,
        )
        return created_lines, duplicate_count

    # -------------------------------------------------------------------------
    # PARTNER MATCHING
    # -------------------------------------------------------------------------

    def _get_partner_from_name(self, partner_name):
        """Fuzzy match a partner by name using ilike search.

        Searches res.partner for records matching the given name with
        case-insensitive partial matching. The search is scoped to the
        current company to maintain multi-company isolation.

        Args:
            partner_name (str): Partner name to search for.

        Returns:
            recordset: Matching res.partner record, or empty recordset if
                       no match found.
        """
        if not partner_name or not partner_name.strip():
            return self.env['res.partner']

        partner_name = partner_name.strip()

        # Try exact match first (case-insensitive)
        partner = self.env['res.partner'].search([
            ('name', '=ilike', partner_name),
            '|',
            ('company_id', '=', self.company_id.id),
            ('company_id', '=', False),
        ], limit=1)

        if partner:
            return partner

        # Try partial match with ilike
        partner = self.env['res.partner'].search([
            ('name', 'ilike', partner_name),
            '|',
            ('company_id', '=', self.company_id.id),
            ('company_id', '=', False),
        ], limit=1)

        if partner:
            _logger.debug(
                "Partner fuzzy match: '%s' -> '%s' (id=%d)",
                partner_name,
                partner.name,
                partner.id,
            )
            return partner

        # Try matching against commercial partner name
        partner = self.env['res.partner'].search([
            ('commercial_company_name', 'ilike', partner_name),
            '|',
            ('company_id', '=', self.company_id.id),
            ('company_id', '=', False),
        ], limit=1)

        if partner:
            _logger.debug(
                "Partner commercial name match: '%s' -> '%s' (id=%d)",
                partner_name,
                partner.name,
                partner.id,
            )
            return partner

        _logger.debug(
            "No partner match found for: '%s'", partner_name,
        )
        return self.env['res.partner']
