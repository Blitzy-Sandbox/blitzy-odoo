# FR-003: Cash Flow Statement

---

## Metadata

| Attribute          | Value                                                                                      |
|--------------------|--------------------------------------------------------------------------------------------|
| **Story ID**       | FR-003                                                                                     |
| **Title**          | Cash Flow Statement                                                                        |
| **Parent Feature** | [FEATURE-001: Financial Reporting](../../features/FEATURE-001-financial-reporting.md)      |
| **Status**         | Draft                                                                                      |
| **Priority**       | Critical                                                                                   |
| **Estimate**       | TBD (To be determined during sprint planning)                                              |

---

## User Story

**As a** CFO

**I want** to generate a statement of cash flows showing operating, investing, and financing activities

**So that** I can analyze cash generation and usage patterns, assess liquidity, and make informed financial decisions

### Secondary Persona

**As a** Business Owner

**I want** to view cash flow reports showing where cash comes from and where it goes

**So that** I can understand the company's liquidity position and plan for future cash needs

---

## Acceptance Criteria

### Scenario 1: Generate Cash Flow Statement using indirect method

- **Given** I am on the financial reports menu and have posted journal entries for the reporting period
- **When** I select Cash Flow Statement, choose indirect method, and specify the reporting period
- **Then** I see a cash flow statement starting with net income and adjusting for non-cash items (depreciation, amortization, gains/losses on asset disposal) and working capital changes (changes in receivables, payables, inventory)

### Scenario 2: Generate Cash Flow Statement using direct method

- **Given** I am on the financial reports menu and have posted journal entries for the reporting period
- **When** I select Cash Flow Statement, choose direct method, and specify the reporting period
- **Then** I see a cash flow statement showing actual cash receipts (collections from customers, interest received, dividends received) and cash payments (payments to suppliers, payments to employees, interest paid, taxes paid) categorized by activity type

### Scenario 3: Operating activities presentation

- **Given** a Cash Flow Statement is generated for a reporting period
- **When** I view the operating activities section
- **Then** I see cash flows from core business operations including:
  - Cash collected from customers
  - Cash paid to suppliers and service providers
  - Cash paid to employees (salaries, wages, benefits)
  - Interest paid (unless classified as financing)
  - Income taxes paid
  - Net cash provided by (used in) operating activities subtotal

### Scenario 4: Investing activities presentation

- **Given** a Cash Flow Statement is generated for a reporting period
- **When** I view the investing activities section
- **Then** I see cash flows related to long-term asset transactions including:
  - Purchases of property, plant, and equipment
  - Proceeds from sale of fixed assets
  - Purchases of intangible assets
  - Investments in securities or other entities
  - Proceeds from sale of investments
  - Loans made to third parties
  - Collections on loans
  - Net cash provided by (used in) investing activities subtotal

### Scenario 5: Financing activities presentation

- **Given** a Cash Flow Statement is generated for a reporting period
- **When** I view the financing activities section
- **Then** I see cash flows from financing transactions including:
  - Proceeds from issuing equity (stock issuance)
  - Proceeds from borrowings (loans, bonds)
  - Repayment of debt principal
  - Dividend payments to shareholders
  - Treasury stock transactions
  - Net cash provided by (used in) financing activities subtotal

### Scenario 6: Cash reconciliation verification

- **Given** a Cash Flow Statement is generated for a reporting period
- **When** I view the statement summary
- **Then** I see:
  - Beginning cash and cash equivalents balance (agrees with prior period Balance Sheet)
  - Net increase (decrease) in cash from all activities
  - Effect of exchange rate changes on cash (if multi-currency)
  - Ending cash and cash equivalents balance (agrees with current Balance Sheet)
  - The reconciliation confirms: Beginning Cash + Net Change + FX Effect = Ending Cash

---

## Constraints

### License and Compliance

- [x] **AGPL-3.0 Compatibility**: Module/feature must be distributed under AGPL-3.0 compatible license
- [x] **No Enterprise Dependencies**: No imports or dependencies on Odoo Enterprise edition modules (specifically not `account_reports` or `account_accountant`)
- [x] **OCA Coding Standards**: Implementation must follow Odoo and OCA (Odoo Community Association) coding standards

### Version Compatibility

- [x] **Target Version**: Odoo 18.0 compatibility required
- [x] **Repository Note**: Current repository is Odoo 19.0; implementation should be version-agnostic where possible

### Accounting Standards Compliance

- [x] **GAAP Compliance**: Statement format must comply with ASC 230 (US GAAP) Statement of Cash Flows requirements
- [x] **IFRS Compliance**: Statement format must also support IAS 7 (International Financial Reporting Standards) presentation requirements
- [x] **Method Support**: Both direct and indirect methods must be available per ASC 230-10-45 and IAS 7.18-20

---

## Technical Discovery Notes

### Codebase Analysis Areas

| Area | Files/Modules to Examine | Analysis Focus |
|------|-------------------------|----------------|
| Account Types | `addons/account/models/account_account.py` | Identify `asset_cash` account type for cash accounts; understand account classification for activity categorization |
| Journal Entries | `addons/account/models/account_move.py` | Analyze cash transaction patterns; understand move types for cash flow classification |
| Move Lines | `addons/account/models/account_move_line.py` | Examine balance computation patterns; understand debit/credit aggregation for cash flow calculation |
| Report Patterns | `addons/account/report/account_invoice_report.py` | Review SQL-view based reporting approach; understand aggregation patterns |
| Initial Balances | `addons/account/models/account_account.py` | Review `include_initial_balance` field for balance-forward account handling |

### Relevant Existing Modules

- `addons/account/` - Core accounting module providing:
  - `account.account` model with `account_type` field including `asset_cash` for cash accounts
  - `account.move` model for journal entries with move types and payment state
  - `account.move.line` model for transaction-level detail with debit/credit amounts
  - `account.journal` model for journal classification (bank, cash journals)
  
- `addons/analytic/` - Analytic accounting for:
  - Cost center and project-based cash flow analysis (optional enhancement)
  - Multi-dimensional cash flow reporting

### OCA Module Compatibility

| OCA Repository | Module | Compatibility Consideration |
|----------------|--------|----------------------------|
| OCA/account-financial-reporting | `account_financial_report` | Review Cash Flow Statement implementation patterns; assess integration vs. replacement strategy |
| OCA/account-financial-tools | Various modules | Examine any existing cash flow related utilities |

### Cash Flow Classification Logic

The implementing agent should analyze how to classify transactions into the three activity categories:

**Operating Activities (per IAS 7.14 / ASC 230-10-45-16):**
- Cash receipts from customers (receivable collections)
- Cash payments to suppliers (payable payments)
- Cash payments to employees
- Interest received/paid (GAAP: operating; IFRS: can be operating or financing/investing)
- Taxes paid

**Investing Activities (per IAS 7.16 / ASC 230-10-45-11):**
- Fixed asset purchases/sales (asset_fixed account movements)
- Investment purchases/sales
- Loan collections/disbursements to third parties

**Financing Activities (per IAS 7.17 / ASC 230-10-45-14):**
- Equity issuance/buyback (equity account movements)
- Debt proceeds/repayments (liability_non_current for long-term debt)
- Dividend payments

### Indirect Method Derivation

For indirect method, the implementing agent should analyze how to derive:
1. Start with Net Income (from P&L/equity_unaffected account)
2. Add back non-cash expenses (depreciation from `expense_depreciation` accounts)
3. Remove gains/add losses on asset sales
4. Adjust for working capital changes:
   - (Increase)/Decrease in receivables
   - (Increase)/Decrease in inventory
   - Increase/(Decrease) in payables

### Account Type Mapping Reference

From `addons/account/models/account_account.py`, the `account_type` selection includes:
- `asset_cash` - Bank and Cash accounts (identifies cash equivalents)
- `asset_receivable` - Receivables (working capital adjustments)
- `asset_current` - Current Assets
- `asset_fixed` - Fixed Assets (investing activities)
- `liability_payable` - Payables (working capital adjustments)
- `liability_current` - Current Liabilities
- `liability_non_current` - Long-term Liabilities (financing activities)
- `equity` - Equity accounts (financing activities)
- `expense_depreciation` - Depreciation (non-cash expense adjustment)

---

## Dependencies

### Story Dependencies

| Dependency Type | Story ID | Story Title | Relationship |
|-----------------|----------|-------------|--------------|
| Parent Feature | FEATURE-001 | Financial Reporting | This story is part of the Financial Reporting feature |
| Related | FR-001 | Balance Sheet Report | Cash balance verification; ending cash must agree with Balance Sheet cash line |
| Related | FR-002 | Profit & Loss Statement | Net income figure for indirect method starting point |
| Related | FR-004 | General Ledger Report | Cash account transactions provide source data for direct method |
| Related | FR-007 | Report Export & Drill-down | Export functionality for Cash Flow Statement outputs |
| Blocked By | None | N/A | Can be developed independently (uses same base data as other reports) |

### External Dependencies

| Dependency | Type | Notes |
|------------|------|-------|
| IAS 7 / ASC 230 | Accounting Standard | Defines statement format, classification rules, and disclosure requirements |
| Multi-currency rates | System Configuration | Exchange rate effects on cash require currency rate data |

### Integration Points

| Odoo Model/Module | Integration Type | Purpose |
|-------------------|------------------|---------|
| `account.move` | Read | Source of all journal entries for cash flow calculation |
| `account.move.line` | Read | Transaction-level detail for activity classification and amounts |
| `account.account` | Read | Account classification by type for activity categorization; identify cash accounts |
| `account.journal` | Read | Identify bank and cash journals for cash transaction filtering |
| `res.currency.rate` | Read | Exchange rate effects on cash (multi-currency environments) |

---

## Test Requirements

### Coverage Requirement

| Metric | Requirement | Notes |
|--------|-------------|-------|
| **Minimum Test Coverage** | **80%** | Mandatory for all new functionality |
| Unit Test Coverage | 80%+ | Cash flow calculation logic, activity classification, method derivation |
| Integration Test Coverage | 80%+ | Report generation, data aggregation, Balance Sheet reconciliation |

### Unit Test Scenarios

| Acceptance Scenario | Unit Test Focus | Key Assertions |
|---------------------|-----------------|----------------|
| Scenario 1 (Indirect Method) | Indirect method calculation logic | Net income correctly adjusted for non-cash items; working capital changes computed accurately |
| Scenario 2 (Direct Method) | Direct method calculation logic | Cash receipts and payments correctly aggregated by activity |
| Scenario 3 (Operating) | Operating activity classification | Customer collections, supplier payments, employee payments correctly classified |
| Scenario 4 (Investing) | Investing activity classification | Asset purchases/sales, investment transactions correctly classified |
| Scenario 5 (Financing) | Financing activity classification | Debt transactions, equity transactions, dividends correctly classified |
| Scenario 6 (Reconciliation) | Cash reconciliation logic | Beginning + Change = Ending; reconciles to Balance Sheet |

### Integration Test Considerations

- [ ] Test integration with `account.move` model for journal entry retrieval
- [ ] Test integration with `account.move.line` model for line-level aggregation
- [ ] Test integration with `account.account` for account type classification
- [ ] Test reconciliation with Balance Sheet cash balance (FR-001 integration)
- [ ] Test reconciliation with P&L net income for indirect method (FR-002 integration)
- [ ] Test multi-currency cash flow with exchange rate effects
- [ ] Test report generation performance with large transaction volumes

### Acceptance Test Mapping

| BDD Scenario | Test Method Name | Test Type |
|--------------|------------------|-----------|
| Scenario 1: Indirect Method Generation | `test_cash_flow_indirect_method` | Acceptance |
| Scenario 2: Direct Method Generation | `test_cash_flow_direct_method` | Acceptance |
| Scenario 3: Operating Activities | `test_operating_activities_presentation` | Acceptance |
| Scenario 4: Investing Activities | `test_investing_activities_presentation` | Acceptance |
| Scenario 5: Financing Activities | `test_financing_activities_presentation` | Acceptance |
| Scenario 6: Cash Reconciliation | `test_cash_reconciliation_verification` | Acceptance |

### Additional Test Scenarios

| Test Category | Specific Test | Expected Outcome |
|---------------|---------------|------------------|
| Edge Cases | Zero activity period | Statement generates with zero values in all categories |
| Edge Cases | Single transaction type | Only affected activity section shows values |
| Data Integrity | Negative cash flow | Properly displays parentheses or negative sign per format |
| Standards | GAAP vs IFRS toggle | Interest classification differs appropriately |
| Performance | 100,000 transactions | Report generates in under 30 seconds |

---

## Definition of Done

### Implementation Checklist

- [ ] All 6 acceptance criteria scenarios pass
- [ ] 80% minimum test coverage achieved
- [ ] Unit tests written and passing for calculation logic
- [ ] Integration tests written and passing for data retrieval and aggregation
- [ ] Both direct and indirect methods implemented and tested
- [ ] Cash reconciliation verifies against Balance Sheet

### Compliance Checklist

- [ ] No Enterprise module dependencies introduced (no imports from `account_reports`, `account_accountant`)
- [ ] AGPL-3.0 license compliance verified in module manifest
- [ ] Code follows OCA coding standards (passes pre-commit, pylint-odoo checks)
- [ ] Code reviewed and approved by peer reviewer

### Documentation Checklist

- [ ] Code documentation (docstrings, comments) complete for all public methods
- [ ] User-facing help text added for report parameters
- [ ] Technical documentation updated with cash flow calculation methodology
- [ ] Classification rules documented for activity categorization

### Quality Checklist

- [ ] No critical or high-severity bugs
- [ ] Performance acceptable: report generates in <30 seconds for typical datasets (up to 100,000 transactions)
- [ ] Security considerations addressed: access rights configured for Accountant and Manager roles
- [ ] Multi-currency handling verified

---

## INVEST Compliance Verification

| Principle | Compliance | Notes |
|-----------|------------|-------|
| **I**ndependent | ✓ | Can be developed without completing other FR stories first; uses same base data |
| **N**egotiable | ✓ | Describes outcomes (cash flow statement) not implementation details |
| **V**aluable | ✓ | Clear business value: liquidity analysis, financial decision-making |
| **E**stimable | ✓ | Well-defined scope with 6 clear scenarios |
| **S**mall | ✓ | Single report type with two method variations; completable in one sprint |
| **T**estable | ✓ | BDD scenarios provide objective pass/fail criteria; reconciliation is verifiable |

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2024 | Enterprise Accounting Team | Initial story creation per Agent Action Plan |

---

## Notes

### Accounting Standards References

- **IAS 7**: International Accounting Standard 7 - Statement of Cash Flows
  - IAS 7.18-20: Direct vs Indirect method requirements
  - IAS 7.14-15: Operating activities definition
  - IAS 7.16: Investing activities definition
  - IAS 7.17: Financing activities definition
  
- **ASC 230**: FASB Accounting Standards Codification Topic 230 - Statement of Cash Flows
  - ASC 230-10-45-16: Operating activities
  - ASC 230-10-45-11: Investing activities
  - ASC 230-10-45-14: Financing activities

### Interest Classification Note

GAAP (ASC 230) requires interest paid and received to be classified as operating activities. IFRS (IAS 7) provides flexibility—entities may classify interest as operating, investing, or financing consistently. The implementation should support both approaches via configuration.

### Cash Equivalents Definition

Per both GAAP and IFRS, cash equivalents are short-term, highly liquid investments readily convertible to known amounts of cash with insignificant risk of value change. Typically includes:
- Short-term treasury bills
- Money market funds
- Commercial paper with maturity ≤3 months from acquisition

The implementation should allow configuration of which accounts are considered cash equivalents.

### Non-Cash Transactions Disclosure

Both GAAP (ASC 230-10-50) and IFRS (IAS 7.43) require disclosure of significant non-cash investing and financing activities separately from the cash flow statement. Examples include:
- Asset acquisitions via debt or equity issuance
- Conversion of debt to equity
- Asset exchanges

The implementation should consider a supplementary schedule for these disclosures.
