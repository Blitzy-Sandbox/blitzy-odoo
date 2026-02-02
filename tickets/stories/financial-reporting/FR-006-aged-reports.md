# FR-006: Aged Receivable/Payable Reports

| Attribute          | Value                                                                 |
|--------------------|-----------------------------------------------------------------------|
| **Story ID**       | FR-006                                                                |
| **Title**          | Aged Receivable/Payable Reports                                       |
| **Parent Feature** | [FEATURE-001: Financial Reporting](../../features/FEATURE-001-financial-reporting.md) |
| **Status**         | Draft                                                                 |
| **Priority**       | High                                                                  |
| **Estimate**       | M (Medium)                                                            |

---

## User Story

**As a** Business Owner

**I want** to generate aged receivable and aged payable reports showing outstanding balances by aging periods

**So that** I can manage cash flow, prioritize collection efforts, and monitor vendor payment obligations

---

## Acceptance Criteria

### Scenario 1: Generate Aged Receivables Report

- **Given** I am on the financial reports menu
- **When** I select Aged Receivables report and specify an as-of date
- **Then** I see a report listing all customers with outstanding balances organized by aging buckets (Current, 1-30 days, 31-60 days, 61-90 days, 91-120 days, Over 120 days)

### Scenario 2: Generate Aged Payables Report

- **Given** I am on the financial reports menu
- **When** I select Aged Payables report and specify an as-of date
- **Then** I see a report listing all vendors with outstanding balances organized by aging buckets (Current, 1-30 days, 31-60 days, 61-90 days, 91-120 days, Over 120 days)

### Scenario 3: Aging bucket customization

- **Given** I am configuring the aged report parameters
- **When** I specify custom aging periods (e.g., 0-15, 16-30, 31-45, 46-60, Over 60 days)
- **Then** the report generates with my custom aging buckets instead of standard periods

### Scenario 4: Partner-level detail expansion

- **Given** an Aged Receivables report is displayed
- **When** I expand a customer's row
- **Then** I see the individual open invoices contributing to each aging bucket with invoice numbers, invoice dates, due dates, and amounts

### Scenario 5: Multi-currency handling

- **Given** customers have outstanding invoices in multiple currencies
- **When** I generate the Aged Receivables report
- **Then** amounts are converted to company currency using appropriate exchange rates with original currency amounts displayed alongside

### Scenario 6: Filter by partner type or category

- **Given** I have partners categorized by type (key accounts, standard, etc.)
- **When** I filter the aged report by partner category
- **Then** only partners matching the selected category are included in the report

---

## Constraints

### License and Compliance

- [x] **AGPL-3.0 Compatibility**: Module/feature must be distributed under AGPL-3.0 compatible license
- [x] **No Enterprise Dependencies**: No imports or dependencies on Odoo Enterprise edition modules (specifically `account_reports` or `account_followup`)
- [x] **OCA Coding Standards**: Implementation must follow Odoo and OCA (Odoo Community Association) coding standards

### Version Compatibility

- [x] **Target Version**: Odoo 18.0 compatibility required
- [x] **Repository Note**: Current repository is Odoo 19.0; implementation should be version-agnostic where possible

### GAAP/IFRS Compliance

- [x] **Standard Aging Buckets**: Support industry-standard aging periods (Current, 30, 60, 90, 120+ days)
- [x] **Currency Presentation**: Multi-currency amounts properly converted and disclosed per financial reporting standards

---

## Technical Discovery Notes

### Codebase Analysis Areas

| Area | Files/Modules to Examine | Analysis Focus |
|------|-------------------------|----------------|
| Partner Credit Data | `addons/account/models/partner.py` | Examine `credit`, `debit`, `total_invoiced`, `days_sales_outstanding` fields and `_credit_debit_get` computation method |
| Invoice/Move Data | `addons/account/models/account_move.py` | Analyze `amount_residual`, `payment_state`, `invoice_date_due` fields for aging calculation |
| Move Line Data | `addons/account/models/account_move_line.py` | Review `amount_residual`, `date_maturity`, `reconciled` fields for determining outstanding amounts |
| Invoice Report Patterns | `addons/account/report/account_invoice_report.py` | Study SQL-view patterns for aggregation and multi-currency handling |
| Partner Model | `addons/base/models/res_partner.py` | Review partner category and classification fields |

### Relevant Existing Modules

- `addons/account/` - Core accounting module containing partner credit/debit computation, account move and move line models, invoice report patterns
- `addons/account/models/partner.py` - Contains `_credit_debit_get()` method showing pattern for aggregating outstanding receivables/payables by account type
- `addons/account/report/account_invoice_report.py` - SQL-view based report providing patterns for currency conversion and partner-based aggregation

### OCA Module Compatibility

| OCA Repository | Module | Compatibility Consideration |
|----------------|--------|----------------------------|
| OCA/account-financial-reporting | `account_financial_report` | Reference Aged Partner Balance report implementation for patterns; evaluate integration vs. independent development |
| OCA/account-financial-reporting | `account_financial_report_qweb` | Study QWeb report generation patterns for PDF output |

### Key Data Model Insights

Based on source file analysis:

1. **Partner Credit/Debit Calculation**: The `_credit_debit_get` method in `partner.py` queries `account.move.line` joining with `account.account` to aggregate residual amounts by `account_type` ('asset_receivable' for receivables, 'liability_payable' for payables)

2. **Outstanding Amount Detection**: Uses `amount_residual` field where `reconciled IS NOT TRUE` to identify unpaid amounts

3. **Multi-Currency Pattern**: The `account_invoice_report.py` shows patterns for handling `currency_id` and company currency conversion using `company_currency_id`

4. **Aging Calculation Basis**: Use `invoice_date_due` (due date) from `account.move` or `date_maturity` from `account.move.line` as the basis for aging bucket assignment relative to the as-of date

---

## Dependencies

### Story Dependencies

| Dependency Type | Story ID | Story Title | Relationship |
|-----------------|----------|-------------|--------------|
| Parent Feature | FEATURE-001 | Financial Reporting | This story is part of this feature |
| Related | FR-007 | Report Export & Drill-down | Export functionality and drill-down to source invoices |
| Related | PF-005 | Overdue Calculation | Payment Follow-ups feature uses similar aging logic |

### External Dependencies

| Dependency | Type | Notes |
|------------|------|-------|
| GAAP/IFRS Standards | Standard | Aging bucket definitions follow generally accepted practices |
| ISO 4217 | Standard | Currency codes for multi-currency presentation |

### Integration Points

| Odoo Model/Module | Integration Type | Purpose |
|-------------------|------------------|---------|
| `account.move` | Read | Source of invoice data including due dates, amounts, and payment states |
| `account.move.line` | Read | Source of detailed line items with residual amounts and maturity dates |
| `res.partner` | Read | Customer and vendor information including categories |
| `res.currency` | Read | Currency conversion rates for multi-currency handling |
| `account.account` | Read | Account type classification (asset_receivable, liability_payable) |

---

## Test Requirements

### Coverage Requirement

| Metric | Requirement | Notes |
|--------|-------------|-------|
| **Minimum Test Coverage** | **80%** | Mandatory for all new functionality |
| Unit Test Coverage | 80%+ | Aging calculation logic, bucket assignment, currency conversion |
| Integration Test Coverage | 80%+ | Report generation, data aggregation, filter application |

### Unit Test Scenarios

| Acceptance Scenario | Unit Test Focus | Key Assertions |
|---------------------|-----------------|----------------|
| Scenario 1: Aged Receivables | Aging bucket calculation for receivables | Verify correct bucket assignment based on days past due |
| Scenario 2: Aged Payables | Aging bucket calculation for payables | Verify correct bucket assignment for vendor invoices |
| Scenario 3: Custom buckets | Custom aging period configuration | Verify buckets respect user-defined ranges |
| Scenario 4: Partner detail | Invoice aggregation by partner | Verify individual invoice amounts sum to partner total |
| Scenario 5: Multi-currency | Currency conversion accuracy | Verify amounts converted at correct exchange rates |
| Scenario 6: Partner filtering | Filter application | Verify only matching partners included in results |

### Integration Test Considerations

- [ ] Test integration with `account.move` model for invoice data retrieval
- [ ] Test integration with `account.move.line` model for residual amounts
- [ ] Test integration with `res.partner` model for partner categorization
- [ ] Test integration with `res.currency` for exchange rate application
- [ ] Test cross-module functionality with existing account reports

### Acceptance Test Mapping

| BDD Scenario | Test Method Name | Test Type |
|--------------|------------------|-----------|
| Scenario 1: Generate Aged Receivables Report | `test_generate_aged_receivables_report` | Acceptance |
| Scenario 2: Generate Aged Payables Report | `test_generate_aged_payables_report` | Acceptance |
| Scenario 3: Aging bucket customization | `test_custom_aging_buckets` | Acceptance |
| Scenario 4: Partner-level detail expansion | `test_partner_detail_expansion` | Acceptance |
| Scenario 5: Multi-currency handling | `test_multi_currency_conversion` | Acceptance |
| Scenario 6: Filter by partner type or category | `test_partner_category_filter` | Acceptance |

### Specific Test Cases

1. **Aging Bucket Boundary Tests**:
   - Invoice due today → Current bucket
   - Invoice due 1 day ago → 1-30 days bucket
   - Invoice due 30 days ago → 1-30 days bucket
   - Invoice due 31 days ago → 31-60 days bucket
   - Invoice due 121 days ago → Over 120 days bucket

2. **Multi-Currency Scenarios**:
   - EUR invoice for USD company
   - Multiple currencies for same partner
   - Exchange rate dated at as-of date vs. invoice date

3. **Edge Cases**:
   - Partner with zero outstanding balance (excluded from report)
   - Partially paid invoice (residual amount only)
   - Credit notes affecting aging

---

## Definition of Done

### Implementation Checklist

- [ ] All acceptance criteria scenarios pass
- [ ] 80% minimum test coverage achieved
- [ ] Unit tests written and passing
- [ ] Integration tests written and passing

### Compliance Checklist

- [ ] No Enterprise module dependencies introduced
- [ ] AGPL-3.0 license compliance verified
- [ ] Code follows OCA coding standards
- [ ] Code reviewed and approved

### Documentation Checklist

- [ ] Code documentation (docstrings, comments) complete
- [ ] User-facing documentation updated (if applicable)
- [ ] Technical documentation updated (if applicable)

### Quality Checklist

- [ ] No critical or high-severity bugs
- [ ] Performance acceptable for datasets up to 100,000 transactions
- [ ] Security considerations addressed (access rights for Accountant/Manager roles)

---

## INVEST Principles Validation

| Principle | Assessment | Status |
|-----------|------------|--------|
| **Independent** | Can be developed after core account module exists; minimal dependency on other FR stories | ✅ Pass |
| **Negotiable** | Describes aging report outcomes without prescribing implementation approach | ✅ Pass |
| **Valuable** | Clear business value: cash flow management, collection prioritization, vendor payment monitoring | ✅ Pass |
| **Estimable** | Well-defined scope with 6 clear scenarios; comparable to other FR stories | ✅ Pass |
| **Small** | Focused on two related reports (AR/AP aging); completable within one sprint | ✅ Pass |
| **Testable** | BDD scenarios provide objective pass/fail criteria; aging bucket calculations are verifiable | ✅ Pass |

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2024-01-XX | Enterprise Accounting Team | Initial story creation |

---

## Notes

### Business Context

Aged receivable and payable reports are essential working capital management tools:

- **Accounts Receivable Aging**: Identifies overdue customer invoices to prioritize collection efforts, calculate bad debt reserves, and assess credit risk
- **Accounts Payable Aging**: Monitors vendor payment obligations to manage cash flow, maintain supplier relationships, and identify available early payment discounts

### Persona Usage Patterns

| Persona | Primary Use Case | Frequency |
|---------|------------------|-----------|
| Business Owner | Review AR aging for cash flow planning | Weekly |
| CFO | Analyze aging trends for financial forecasting | Monthly |
| Accountant | Generate detailed aging for collection actions | Daily |
| Credit Controller | Prioritize collection calls based on aging | Daily |

### Relationship to Payment Follow-ups (PF-005)

The aging calculation logic developed for this story should be designed for reuse by the Payment Follow-ups feature (PF-005 Overdue Calculation). The same underlying data (overdue invoices by partner) drives both:
- This story: Reporting and visibility
- PF-005: Automated collection actions

Consider implementing shared utility methods or services that can be leveraged by both features.

### Standard Aging Bucket Definitions

| Bucket | Days Past Due | Description |
|--------|---------------|-------------|
| Current | 0 | Not yet due |
| 1-30 days | 1-30 | Slightly past due |
| 31-60 days | 31-60 | Moderately past due |
| 61-90 days | 61-90 | Significantly past due |
| 91-120 days | 91-120 | Severely past due |
| Over 120 days | 121+ | Extremely past due; bad debt risk |
