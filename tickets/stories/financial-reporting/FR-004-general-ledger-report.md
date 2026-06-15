# FR-004: General Ledger Report

| Attribute       | Value                                                    |
|-----------------|----------------------------------------------------------|
| **Story ID**    | FR-004                                                   |
| **Title**       | General Ledger Report                                    |
| **Parent Feature** | [FEATURE-001: Financial Reporting](../../features/FEATURE-001-financial-reporting.md) |
| **Status**      | Draft                                                    |
| **Priority**    | High                                                     |
| **Estimate**    | M (Medium)                                               |

---

## User Story

**As an** Accountant

**I want** to generate a general ledger report showing all transactions for each account with running balances

**So that** I can review the complete transaction history, verify postings, and support audit inquiries

---

## Acceptance Criteria

### Scenario 1: Generate General Ledger for date range

- **Given** I am on the financial reports menu
- **When** I select General Ledger report and specify a date range
- **Then** I see all journal entries grouped by account showing date, reference, description, debit, credit, and running balance

### Scenario 2: Filter by specific accounts

- **Given** I want to review only cash and bank accounts
- **When** I filter the General Ledger by account codes or account types
- **Then** only the selected accounts and their transactions are displayed

### Scenario 3: Opening balance presentation

- **Given** I am generating a General Ledger starting mid-fiscal year
- **When** the report is generated for balance-forward accounts
- **Then** an opening balance line is shown before the first transaction in the period

### Scenario 4: Partner information display

- **Given** transactions are posted with partner references
- **When** I view the General Ledger
- **Then** partner names are displayed alongside relevant transactions for receivables and payables

### Scenario 5: Journal entry reference linking

- **Given** a General Ledger is displayed with transactions
- **When** I click on a journal entry reference number
- **Then** I am navigated to the source journal entry document

### Scenario 6: Centralized journal consolidation

- **Given** some accounts have transactions in centralized journals
- **When** I generate the General Ledger with centralized journal option
- **Then** centralized journal transactions are properly grouped and totaled

---

## Constraints

### License and Compliance

- [ ] **AGPL-3.0 Compatibility**: Module/feature must be distributed under AGPL-3.0 compatible license
- [ ] **No Enterprise Dependencies**: No imports or dependencies on Odoo Enterprise edition modules
- [ ] **OCA Coding Standards**: Implementation must follow Odoo and OCA (Odoo Community Association) coding standards

### Version Compatibility

- [ ] **Target Version**: Odoo 18.0 compatibility required
- [ ] **Repository Note**: Current repository is Odoo 19.0; implementation should be version-agnostic where possible

---

## Technical Discovery Notes

### Codebase Analysis Areas

| Area | Files/Modules to Examine | Analysis Focus |
|------|-------------------------|----------------|
| Transaction Data Model | `addons/account/models/account_move_line.py` | Examine fields: `debit`, `credit`, `balance`, `cumulated_balance`, `date`, `ref`, `name`, `partner_id`, `account_id`, `move_id` for transaction data retrieval |
| Account Structure | `addons/account/models/account_account.py` | Review `include_initial_balance` field for balance-forward account identification; analyze `account_type` and `internal_group` for filtering |
| Existing Report Patterns | `addons/account/report/account_invoice_report.py` | Study SQL-view based reporting patterns, `_table_query` approach, and field aggregation methods |
| Balance Computation | `addons/account/models/account_move_line.py` | Analyze `_compute_cumulated_balance` method for running balance calculation patterns |

### Relevant Existing Modules

- `addons/account/` - Core accounting module containing:
  - `account.move.line` model with transaction data (date, debit, credit, balance, partner_id, account_id)
  - `account.account` model with `include_initial_balance` field for balance-forward logic
  - `account.move` model for journal entry navigation and drill-down references
  - Existing report infrastructure in `addons/account/report/` directory

- `addons/analytic/` - Analytic accounting integration:
  - Potential analytic dimension filtering for departmental/project general ledgers
  - `analytic.mixin` inherited by `account.move.line`

### OCA Module Compatibility

| OCA Repository | Module | Compatibility Consideration |
|----------------|--------|----------------------------|
| OCA/account-financial-reporting | `account_financial_report` | Primary reference for General Ledger implementation patterns; evaluate for integration vs. standalone approach |
| OCA/account-financial-reporting | `account_financial_report_qweb` | QWeb template patterns for PDF report generation |

### Key Technical Considerations

1. **Running Balance Calculation**: The `cumulated_balance` computed field in `account.move.line` provides pattern for running balance; may need custom implementation for report-specific ordering

2. **Opening Balance Logic**: Accounts with `include_initial_balance=True` (asset, liability, equity types) require aggregation of all historical transactions before the report start date

3. **Multi-Currency Display**: Consider `amount_currency` and `currency_id` fields for transactions in non-company currencies

4. **Performance**: Large transaction volumes require efficient SQL queries; consider pagination or lazy loading for interactive reports

5. **Centralized Journals**: Analyze journal configuration for centralized journal handling across multi-company setups

---

## Dependencies

### Story Dependencies

| Dependency Type | Story ID | Story Title | Relationship |
|-----------------|----------|-------------|--------------|
| Parent Feature | FEATURE-001 | Financial Reporting | This story is part of the Financial Reporting feature |
| Blocks | FR-005 | Trial Balance Report | General Ledger provides transaction detail behind Trial Balance summary |
| Related | FR-007 | Report Export & Drill-down | Export and drill-down functionality applies to General Ledger |
| Related | FR-001 | Balance Sheet Report | GL transactions support Balance Sheet account verification |
| Related | FR-002 | Profit & Loss Statement | GL transactions support P&L account verification |

### External Dependencies

| Dependency | Type | Notes |
|------------|------|-------|
| GAAP/IFRS Standards | Standard | General Ledger format should support standard accounting presentation requirements |
| ISO 8601 | Standard | Date formatting for international compatibility |

### Integration Points

| Odoo Model/Module | Integration Type | Purpose |
|-------------------|------------------|---------|
| `account.move` | Read | Retrieve journal entry data for transaction display and drill-down navigation |
| `account.move.line` | Read | Primary data source for transaction details including debit, credit, balance, date, reference |
| `account.account` | Read | Account master data for grouping, filtering, and balance-forward identification |
| `res.partner` | Read | Partner information display for receivable/payable transactions |
| `account.journal` | Read | Journal information for centralized journal consolidation feature |

---

## Test Requirements

### Coverage Requirement

| Metric | Requirement | Notes |
|--------|-------------|-------|
| **Minimum Test Coverage** | **80%** | Mandatory for all new functionality |
| Unit Test Coverage | 80%+ | Running balance calculations, opening balance logic |
| Integration Test Coverage | 80%+ | Report generation with journal entry data |

### Unit Test Scenarios

| Acceptance Scenario | Unit Test Focus | Key Assertions |
|---------------------|-----------------|----------------|
| Scenario 1: Generate GL for date range | Date range filtering logic | Transactions within range included; transactions outside range excluded |
| Scenario 2: Filter by specific accounts | Account filtering logic | Only selected accounts appear; correct transaction counts per account |
| Scenario 3: Opening balance presentation | Opening balance computation | Balance-forward accounts show correct opening balance; P&L accounts show zero opening |
| Scenario 4: Partner information display | Partner data retrieval | Partner names displayed for receivable/payable transactions |
| Scenario 5: Journal entry reference linking | Navigation URL generation | Correct action URL generated for journal entry navigation |
| Scenario 6: Centralized journal consolidation | Journal grouping logic | Centralized transactions properly aggregated |

### Integration Test Considerations

- [ ] Test integration with `account.move` model for journal entry data retrieval
- [ ] Test integration with `account.move.line` model for transaction line details
- [ ] Test integration with `account.account` model for account hierarchy and filtering
- [ ] Test running balance calculations across multiple transactions
- [ ] Test opening balance computation for balance-forward accounts (assets, liabilities, equity)
- [ ] Test multi-company scenarios with centralized journals
- [ ] Test performance with large transaction volumes (10,000+ lines)

### Acceptance Test Mapping

| BDD Scenario | Test Method Name | Test Type |
|--------------|------------------|-----------|
| Scenario 1: Generate GL for date range | `test_general_ledger_date_range_filter` | Acceptance |
| Scenario 2: Filter by specific accounts | `test_general_ledger_account_filter` | Acceptance |
| Scenario 3: Opening balance presentation | `test_general_ledger_opening_balance` | Acceptance |
| Scenario 4: Partner information display | `test_general_ledger_partner_display` | Acceptance |
| Scenario 5: Journal entry reference linking | `test_general_ledger_entry_navigation` | Acceptance |
| Scenario 6: Centralized journal consolidation | `test_general_ledger_centralized_journals` | Acceptance |

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
- [ ] Performance acceptable (report generates in <30 seconds for typical datasets)
- [ ] Security considerations addressed (access rights for Accountant and Manager roles)

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2024 | Enterprise Accounting Team | Initial story creation |

---

## Notes

### Auditor Use Case

While the primary persona is the Accountant, Auditors are a key secondary user of the General Ledger report. They use it to:
- Verify the accuracy of financial statement figures by tracing back to source transactions
- Review transaction patterns for anomalies or unusual entries
- Confirm that all transactions are properly documented with references
- Test internal controls by examining the completeness and accuracy of the accounting records

### Running Balance Calculation Note

The running balance should be calculated in chronological order within each account, starting from the opening balance (if applicable) and accumulating through each transaction. The formula is:

```
Running Balance = Opening Balance + Sum of (Debit - Credit) for all prior transactions
```

For accounts that use credits as positive (e.g., revenue, liabilities), the presentation may show the balance as a positive number even when the calculated balance is negative.

### Multi-Currency Consideration

When transactions exist in multiple currencies:
- Primary display should be in company currency for consistency
- Original currency amount should be available for reference where applicable
- Exchange rate differences should be transparent to support reconciliation

### Performance Benchmark

For optimal user experience, the General Ledger report should:
- Generate within 10 seconds for datasets up to 10,000 transaction lines
- Generate within 30 seconds for datasets up to 100,000 transaction lines
- Support pagination or progressive loading for larger datasets

---
