# BR-001 Statement Import

| Attribute       | Value                                                    |
|-----------------|----------------------------------------------------------|
| **Story ID**    | BR-001                                                   |
| **Title**       | Statement Import                                         |
| **Parent Feature** | [FEATURE-002: Bank Reconciliation](../../features/FEATURE-002-bank-reconciliation.md) |
| **Status**      | Draft                                                    |
| **Priority**    | Critical                                                 |
| **Estimate**    | L (Large)                                                |

---

## User Story

**As an** Accountant / Bookkeeper

**I want** to import bank statements in multiple electronic formats (CSV, OFX, QIF, CAMT.053)

**So that** I can efficiently load bank transaction data from any financial institution into the system for reconciliation without manual data entry

---

## Acceptance Criteria

### Scenario 1: Import CSV Bank Statement

- **Given** a CSV file containing bank transactions with date, description, and amount columns
- **When** I upload the file and configure column mapping for the bank journal
- **Then** all transactions are parsed and created as bank statement lines with correct dates, descriptions, and amounts

### Scenario 2: Import OFX Format Statement

- **Given** an OFX (Open Financial Exchange) file downloaded from a US bank
- **When** I import the file for the corresponding bank journal
- **Then** the OFX transaction data is parsed, including FITID transaction references, and statement lines are created with partner name and memo fields populated

### Scenario 3: Import QIF Legacy Format

- **Given** a QIF (Quicken Interchange Format) file exported from legacy banking software
- **When** I import the file for the bank journal
- **Then** transactions are converted to statement lines with dates, payee names, and amounts correctly mapped

### Scenario 4: Import CAMT.053 ISO 20022 Statement

- **Given** a CAMT.053 XML file compliant with ISO 20022 European banking standard
- **When** I import the file for a Euro-denominated bank journal
- **Then** all transaction entries (Ntry elements) are parsed including booking date, value date, amount, currency, and remittance information

### Scenario 5: Duplicate Transaction Detection

- **Given** a bank statement file containing transactions some of which were previously imported
- **When** I import the file
- **Then** duplicate transactions are identified based on date, amount, and reference, and I am warned before creating duplicates with option to skip

### Scenario 6: Import Error Handling

- **Given** a malformed or incomplete bank statement file
- **When** I attempt to import the file
- **Then** specific validation errors are reported (missing required fields, invalid date formats, parsing failures) without creating partial imports

---

## Constraints

### License and Compliance

- [x] **AGPL-3.0 Compatibility**: Module/feature must be distributed under AGPL-3.0 compatible license
- [x] **No Enterprise Dependencies**: No imports or dependencies on Odoo Enterprise edition modules (specifically `account_accountant`, `account_bank_statement_import` Enterprise variants)
- [x] **OCA Coding Standards**: Implementation must follow Odoo and OCA (Odoo Community Association) coding standards

### Version Compatibility

- [x] **Target Version**: Odoo 18.0 compatibility required
- [x] **Repository Note**: Current repository is Odoo 19.0; implementation should be version-agnostic where possible

---

## Technical Discovery Notes

### Codebase Analysis Areas

| Area | Files/Modules to Examine | Analysis Focus |
|------|-------------------------|----------------|
| Bank Statement Model | `addons/account/models/account_bank_statement.py` | Statement structure, required fields (`name`, `reference`, `date`, `balance_start`, `balance_end_real`, `line_ids`), journal association pattern |
| Statement Line Model | `addons/account/models/account_bank_statement_line.py` | Line fields (`payment_ref`, `amount`, `partner_name`, `account_number`, `transaction_type`), move inherits pattern |
| Document Import Pipeline | `addons/account/models/account_document_import_mixin.py` | Attachment handling, file parsing patterns, error handling approach (`_create_records_from_attachments`, `_to_files_data`, `_extend_with_attachments`) |
| Bank Journal Configuration | `addons/account/models/account_journal.py` | Bank journal type settings, suspense account handling, currency configuration |
| Existing Import Patterns | `addons/account/wizard/` | Wizard-based import workflow patterns, user interaction design |

### Relevant Existing Modules

- `addons/account/` - Core accounting module containing `account.bank.statement` and `account.bank.statement.line` models that statement import must integrate with
- `addons/account/models/account_document_import_mixin.py` - Abstract mixin providing document import pipeline with attachment handling and transaction-safe record creation
- `addons/account/models/account_journal.py` - Bank journal configuration including `__get_bank_statements_available_sources()` method for import source registration
- `addons/base/models/ir_attachment.py` - Attachment handling for uploaded statement files

### OCA Module Compatibility

| OCA Repository | Module | Compatibility Consideration |
|----------------|--------|----------------------------|
| OCA/account-reconcile | `account_statement_import` | Base import framework with wizard interface; evaluate integration vs. reimplementation |
| OCA/account-reconcile | `account_statement_import_ofx` | OFX parser implementation; analyze parsing approach for compatibility |
| OCA/account-reconcile | `account_statement_import_qif` | QIF parser implementation; analyze for legacy format handling patterns |
| OCA/account-reconcile | `account_statement_import_camt` | CAMT.053 XML parser; analyze ISO 20022 namespace handling and Ntry element extraction |
| OCA/account-reconcile | `account_statement_import_file` | Generic file import base; consider extension vs. standalone approach |

### Format-Specific Considerations

| Format | Standard Reference | Key Parsing Elements |
|--------|-------------------|---------------------|
| CSV | Generic/Custom | Column mapping wizard, delimiter detection, date format configuration, encoding handling (UTF-8, Latin-1) |
| OFX | Open Financial Exchange 2.x | SGML-based parsing, FITID unique identifiers, BANKACCTFROM/STMTTRN elements |
| QIF | Quicken Interchange Format | Line-prefix parsing (D=date, T=amount, P=payee, M=memo), transaction type codes |
| CAMT.053 | ISO 20022 | XML namespaces (urn:iso:std:iso:20022:tech:xsd:camt.053), Ntry/NtryDtls/TxDtls hierarchy, BkToCstmrStmt root |

---

## Dependencies

### Story Dependencies

| Dependency Type | Story ID | Story Title | Relationship |
|-----------------|----------|-------------|--------------|
| Parent Feature | FEATURE-002 | Bank Reconciliation | This story is part of the Bank Reconciliation feature |
| Blocks | BR-002 | Algorithmic Matching | Statement import must complete before matching can process statement lines |
| Blocks | BR-003 | Manual Reconciliation | Statement import provides the statement lines for manual reconciliation |
| Related | None | N/A | This is the foundational story with no blockers |

### External Dependencies

| Dependency | Type | Notes |
|------------|------|-------|
| OFX Specification | Standard | Open Financial Exchange format specification for US bank compatibility |
| QIF Specification | Standard | Quicken Interchange Format for legacy system imports |
| ISO 20022 CAMT.053 | Standard | European banking standard for bank-to-customer statements |
| Python `lxml` | Library | XML parsing library for CAMT.053 (already in Odoo dependencies) |

### Integration Points

| Odoo Model/Module | Integration Type | Purpose |
|-------------------|------------------|---------|
| `account.bank.statement` | Write | Create statement records from imported files |
| `account.bank.statement.line` | Write | Create individual transaction lines from parsed data |
| `account.journal` | Read | Identify target bank journal for statement association |
| `res.currency` | Read | Currency validation for multi-currency statements |
| `ir.attachment` | Read/Write | Store original imported file as attachment |
| `account.document.import.mixin` | Inherit | Leverage existing document import pipeline patterns |

---

## Test Requirements

### Coverage Requirement

| Metric | Requirement | Notes |
|--------|-------------|-------|
| **Minimum Test Coverage** | **80%** | Mandatory for all statement import functionality |
| Unit Test Coverage | 80%+ | Format parsers, validation logic, duplicate detection |
| Integration Test Coverage | 80%+ | Full import workflow, journal association, line creation |

### Unit Test Scenarios

| Acceptance Scenario | Unit Test Focus | Key Assertions |
|---------------------|-----------------|----------------|
| Scenario 1: CSV Import | CSV parser, column mapping | Dates parsed correctly, amounts with correct sign, descriptions preserved |
| Scenario 2: OFX Import | OFX parser, FITID extraction | Transaction references stored, partner names extracted, memo fields populated |
| Scenario 3: QIF Import | QIF parser, line-prefix handling | Date format conversion, payee extraction, amount sign handling |
| Scenario 4: CAMT.053 Import | XML parser, namespace handling | Ntry elements extracted, booking/value dates separated, currency validated |
| Scenario 5: Duplicate Detection | Fingerprint algorithm, comparison logic | Duplicates identified by date+amount+reference hash, warning generated |
| Scenario 6: Error Handling | Validation routines, exception handling | Specific error messages, no partial imports, file integrity preserved |

### Integration Test Considerations

- [ ] Test complete import workflow from file upload to statement line creation
- [ ] Test integration with `account.bank.statement` model for statement creation
- [ ] Test integration with `account.bank.statement.line` model for line creation
- [ ] Test journal association and currency validation
- [ ] Test attachment creation for source file preservation
- [ ] Test multi-currency statement handling
- [ ] Test import with various date formats and regional settings
- [ ] Test large file handling (500+ transactions per statement)

### Acceptance Test Mapping

| BDD Scenario | Test Method Name | Test Type |
|--------------|------------------|-----------|
| Scenario 1: Import CSV Bank Statement | `test_import_csv_statement` | Acceptance |
| Scenario 2: Import OFX Format Statement | `test_import_ofx_statement` | Acceptance |
| Scenario 3: Import QIF Legacy Format | `test_import_qif_statement` | Acceptance |
| Scenario 4: Import CAMT.053 ISO 20022 Statement | `test_import_camt053_statement` | Acceptance |
| Scenario 5: Duplicate Transaction Detection | `test_duplicate_transaction_detection` | Acceptance |
| Scenario 6: Import Error Handling | `test_import_error_handling` | Acceptance |

### Sample Test Data Requirements

| Format | Test File Description | Key Test Cases |
|--------|----------------------|----------------|
| CSV | Standard bank export with date/desc/amount columns | Multi-row, varying date formats, negative amounts |
| OFX | Sample OFX 2.x file from US bank template | Multiple STMTTRN entries, FITID uniqueness |
| QIF | Legacy Quicken export file | Various transaction types, memo fields |
| CAMT.053 | ISO 20022 compliant XML sample | Multiple Ntry elements, namespaced XML |
| Malformed | Invalid/corrupted files for each format | Missing fields, invalid dates, encoding errors |

---

## Definition of Done

### Implementation Checklist

- [ ] All 6 acceptance criteria scenarios pass
- [ ] 80% minimum test coverage achieved for import functionality
- [ ] Unit tests written and passing for each format parser
- [ ] Integration tests written and passing for import workflow
- [ ] Sample test files created for each format (CSV, OFX, QIF, CAMT.053)

### Compliance Checklist

- [ ] No Enterprise module dependencies introduced
- [ ] AGPL-3.0 license compliance verified
- [ ] Code follows OCA coding standards (pre-commit, pylint-odoo)
- [ ] Code reviewed and approved

### Documentation Checklist

- [ ] Code documentation (docstrings) complete for all public methods
- [ ] Column mapping configuration documented for CSV import
- [ ] Supported format specifications documented
- [ ] Error message catalog documented

### Quality Checklist

- [ ] No critical or high-severity bugs
- [ ] Import performance acceptable (<10 seconds for 500 lines)
- [ ] Security considerations addressed (file validation, size limits)
- [ ] Error messages are user-friendly and actionable

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2024 | Enterprise Accounting Team | Initial story creation |

---

## Notes

### Business Context

Bank statement import is the **foundational capability** for the entire bank reconciliation feature. Without reliable statement import supporting multiple formats, organizations cannot begin the reconciliation process. This story addresses the critical pain point of manual data entry and format incompatibility with various financial institutions.

### Format Priority

Based on market analysis:
1. **CSV** - Universal format supported by virtually all banks
2. **CAMT.053** - European standard increasingly adopted globally
3. **OFX** - Primary format for US banks
4. **QIF** - Legacy format for backward compatibility

### Edge Cases to Consider

- **Multi-currency statements**: Statements with transactions in multiple currencies
- **Negative balance statements**: Opening/closing balances that are negative
- **Unicode in descriptions**: International characters in transaction descriptions
- **Large statements**: Performance with 1000+ transactions
- **Partial imports**: Handling of imports that partially succeed (should rollback)

### Security Considerations

- File size limits to prevent denial of service
- File type validation to prevent malicious uploads
- Sanitization of imported text fields
- Audit trail of import actions

---

<!--
================================================================================
INVEST VALIDATION CHECKLIST
================================================================================
✓ Independent - Can be developed standalone; no story dependencies
✓ Negotiable - Describes import outcomes, not specific implementation
✓ Valuable - Business value clear: eliminates manual data entry, supports multiple banks
✓ Estimable - Scope well-defined: 4 formats, 6 scenarios
✓ Small - Fits within 1-2 sprints for experienced team
✓ Testable - Each scenario has clear pass/fail criteria

BDD COMPLIANCE:
✓ 6 scenarios (within 3-6 guideline)
✓ All scenarios use Given/When/Then format
✓ No UI element references in acceptance criteria
✓ No implementation details prescribed
✓ Observable outcomes specified
================================================================================
-->
