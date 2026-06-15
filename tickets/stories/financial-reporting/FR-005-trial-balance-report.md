# FR-005: Trial Balance Report

| Attribute       | Value                                                    |
|-----------------|----------------------------------------------------------|
| **Story ID**    | FR-005                                                   |
| **Title**       | Trial Balance Report                                     |
| **Parent Feature** | [FEATURE-001: Financial Reporting](../../features/FEATURE-001-financial-reporting.md) |
| **Status**      | Draft                                                    |
| **Priority**    | High                                                     |
| **Estimate**    | M (Medium)                                               |

---

## User Story

**As an** Accountant

**I want** to generate a trial balance report showing all accounts with their debit and credit balances

**So that** I can verify that total debits equal total credits and identify any posting errors before preparing financial statements

---

## Acceptance Criteria

### Scenario 1: Generate Trial Balance for period

- **Given** I am on the financial reports menu and have posted journal entries for the fiscal period
- **When** I select Trial Balance report and specify a date range
- **Then** I see all accounts listed with their debit balances, credit balances, and net balance for the period

### Scenario 2: Verify debit/credit equality

- **Given** a Trial Balance report is generated for a period with posted transactions
- **When** I view the report totals section
- **Then** total debits equal total credits, confirming the books are in balance according to double-entry accounting principles

### Scenario 3: Include opening balances

- **Given** I am generating a Trial Balance for a mid-year period and balance-forward accounts have prior period activity
- **When** I select the option to include opening balances
- **Then** the report shows opening balance, period movement (debits and credits), and closing balance columns for each account

### Scenario 4: Filter by account type

- **Given** I want to review only accounts within a specific classification
- **When** I filter the Trial Balance by account type (e.g., Asset, Liability, Equity, Income, Expense)
- **Then** only accounts matching the selected account type internal group are displayed in the report

### Scenario 5: Show zero-balance accounts option

- **Given** some accounts in the chart of accounts have had no transactions in the selected period
- **When** I generate Trial Balance with the 'Include Zero Balances' option enabled
- **Then** accounts with zero balances are included in the report alongside accounts with activity

### Scenario 6: Comparative Trial Balance

- **Given** I want to compare the current period trial balance to a prior period for trend analysis
- **When** I select the comparative period option and specify both current and prior periods
- **Then** the report shows balances for both periods with variance columns (amount difference and percentage change)

---

## Constraints

### License and Compliance

- [x] **AGPL-3.0 Compatibility**: Module/feature must be distributed under AGPL-3.0 compatible license
- [x] **No Enterprise Dependencies**: No imports or dependencies on Odoo Enterprise edition modules (specifically `account_reports` Enterprise module)
- [x] **OCA Coding Standards**: Implementation must follow Odoo and OCA (Odoo Community Association) coding standards

### Version Compatibility

- [x] **Target Version**: Odoo 18.0 compatibility required
- [x] **Repository Note**: Current repository is Odoo 19.0; implementation should be version-agnostic where possible

### Accounting Standards Compliance

- [x] **GAAP/IFRS**: Trial Balance format must comply with Generally Accepted Accounting Principles and International Financial Reporting Standards
- [x] **Double-Entry Verification**: Total debits must equal total credits to validate accounting equation integrity

---

## Technical Discovery Notes

> **Purpose:** These notes guide implementing agents in their codebase analysis before making implementation decisions. User stories describe WHAT and WHY; implementation details emerge from agent discovery of the codebase.

### Codebase Analysis Areas

| Area | Files/Modules to Examine | Analysis Focus |
|------|-------------------------|----------------|
| Account Types | `addons/account/models/account_account.py` | Analyze `account_type` selection field with 18 types including asset_*, liability_*, equity*, income*, expense* classifications |
| Internal Groups | `addons/account/models/account_account.py` | Review `internal_group` computed field that categorizes accounts into equity, asset, liability, income, expense, off for grouping |
| Balance Forward | `addons/account/models/account_account.py` | Examine `include_initial_balance` field logic for determining which accounts carry forward balances vs. reset each fiscal year |
| Balance Computation | `addons/account/models/account_move_line.py` | Study `debit`, `credit`, `balance` field computations and `cumulated_balance` for running totals |
| Opening Balances | `addons/account/models/account_account.py` | Review `opening_debit`, `opening_credit`, `opening_balance` computed fields |
| Report Patterns | `addons/account/report/account_invoice_report.py` | Examine SQL-view based reporting pattern with `_auto = False` and `_table_query` |

### Relevant Existing Models

- `account.account` - Chart of accounts with account types, internal groups, and balance-forward indicators
  - Key fields: `account_type`, `internal_group`, `include_initial_balance`, `code`, `name`
  - Account types determine if account is balance-forward (asset, liability, equity) or period-reset (income, expense)
  
- `account.move.line` - Journal entry line items containing debit/credit amounts
  - Key fields: `debit`, `credit`, `balance`, `account_id`, `date`, `parent_state`
  - Balance computation: `balance = debit - credit`
  - Only posted entries (`parent_state = 'posted'`) should be included in Trial Balance

- `account.move` - Journal entries (parent records)
  - Key fields: `state`, `date`, `company_id`
  - Filter criteria: `state = 'posted'` for Trial Balance inclusion

### OCA Module Compatibility

| OCA Repository | Module | Compatibility Consideration |
|----------------|--------|----------------------------|
| OCA/account-financial-reporting | `account_financial_report` | Reference implementation for Trial Balance; analyze report structure, wizard parameters, and QWeb templates |
| OCA/mis-builder | `mis_builder` | Alternative reporting framework; evaluate integration vs. independent implementation |

### Key Technical Considerations

1. **Balance-Forward vs. Period-Reset Accounts**
   - Balance sheet accounts (asset, liability, equity) use `include_initial_balance = True`
   - Income statement accounts (income, expense) use `include_initial_balance = False`
   - Opening balance calculation differs based on this flag

2. **Account Type to Internal Group Mapping**
   - `asset_*` types → `internal_group = 'asset'`
   - `liability_*` types → `internal_group = 'liability'`
   - `equity*` types → `internal_group = 'equity'`
   - `income*` types → `internal_group = 'income'`
   - `expense*` types → `internal_group = 'expense'`
   - `off_balance` type → `internal_group = 'off'`

3. **Debit/Credit Equality Verification**
   - Sum of all debit balances must equal sum of all credit balances
   - This validates the fundamental accounting equation: Assets = Liabilities + Equity
   - Any imbalance indicates posting errors that must be investigated

4. **Multi-Currency Considerations**
   - Trial Balance typically displays amounts in company currency
   - `account.move.line.debit` and `credit` are in company currency
   - Foreign currency transactions are converted at transaction date rate

---

## Dependencies

### Story Dependencies

| Dependency Type | Story ID | Story Title | Relationship |
|-----------------|----------|-------------|--------------|
| Parent Feature | FEATURE-001 | Financial Reporting | This story is part of the Financial Reporting feature |
| Related | FR-001 | Balance Sheet Report | Trial Balance validates Balance Sheet account balances |
| Related | FR-002 | Profit & Loss Statement | Trial Balance validates P&L account balances |
| Related | FR-004 | General Ledger Report | Trial Balance summarizes General Ledger; GL provides detail behind Trial Balance |
| Related | FR-007 | Report Export & Drill-down | Trial Balance requires export to PDF/Excel and drill-down capability |

### External Dependencies

| Dependency | Type | Notes |
|------------|------|-------|
| Double-Entry Accounting Principle | Standard | Total debits must equal total credits for valid Trial Balance |
| GAAP/IFRS | Standard | Report format and account classification per accounting standards |

### Integration Points

| Odoo Model/Module | Integration Type | Purpose |
|-------------------|------------------|---------|
| `account.account` | Read | Retrieve chart of accounts with account types, codes, names, and balance-forward settings |
| `account.move.line` | Read | Aggregate debit and credit balances by account for the reporting period |
| `account.move` | Read | Filter journal entries by state (posted only) and date range |
| `res.company` | Read | Company context for multi-company support and currency |

---

## Test Requirements

### Coverage Requirement

| Metric | Requirement | Notes |
|--------|-------------|-------|
| **Minimum Test Coverage** | **80%** | Mandatory for all new functionality |
| Unit Test Coverage | 80%+ | Balance calculations, account filtering, opening balance logic |
| Integration Test Coverage | 80%+ | Report generation, data aggregation, period comparisons |

### Unit Test Scenarios

| Acceptance Scenario | Unit Test Focus | Key Assertions |
|---------------------|-----------------|----------------|
| Scenario 1: Generate Trial Balance | Balance aggregation per account | Debit/credit sums correctly aggregate from move lines |
| Scenario 2: Verify debit/credit equality | Total balance validation | Assert total_debit == total_credit |
| Scenario 3: Include opening balances | Opening balance calculation | Balance-forward accounts include prior period cumulative balance |
| Scenario 4: Filter by account type | Account type filtering | Only accounts matching internal_group are returned |
| Scenario 5: Zero-balance accounts | Zero-balance inclusion | Accounts with no activity appear when option enabled |
| Scenario 6: Comparative Trial Balance | Period comparison calculations | Variance = current_balance - prior_balance |

### Integration Test Considerations

- [ ] Test integration with `account.account` model for account hierarchy and types
- [ ] Test integration with `account.move.line` model for balance aggregation
- [ ] Test integration with `account.move` for posted entry filtering
- [ ] Test multi-company scenarios with company-specific chart of accounts
- [ ] Test period boundary handling (fiscal year start/end dates)
- [ ] Test with various chart of accounts configurations
- [ ] Test performance with large transaction volumes (10,000+ journal items)

### Acceptance Test Mapping

| BDD Scenario | Test Method Name | Test Type |
|--------------|------------------|-----------|
| Scenario 1: Generate Trial Balance for period | `test_generate_trial_balance_for_date_range` | Acceptance |
| Scenario 2: Verify debit/credit equality | `test_debit_credit_totals_equal` | Acceptance |
| Scenario 3: Include opening balances | `test_opening_balance_included_for_balance_forward_accounts` | Acceptance |
| Scenario 4: Filter by account type | `test_filter_by_account_type_internal_group` | Acceptance |
| Scenario 5: Show zero-balance accounts | `test_include_zero_balance_accounts_option` | Acceptance |
| Scenario 6: Comparative Trial Balance | `test_comparative_period_with_variance` | Acceptance |

### Specific Test Cases

1. **Debit/Credit Equality Verification**
   - Create journal entries with balanced debits and credits
   - Generate Trial Balance and assert totals match
   - Test with edge cases: very large amounts, multiple currencies converted to company currency

2. **Opening Balance Calculation**
   - Create prior period transactions for asset and liability accounts
   - Generate Trial Balance starting mid-year
   - Verify opening balance equals prior period closing balance for balance-forward accounts
   - Verify opening balance is zero for income/expense accounts

3. **Account Type Filtering**
   - Generate Trial Balance with filter by 'Asset' internal group
   - Assert only accounts with `internal_group = 'asset'` are displayed
   - Test each internal group filter: asset, liability, equity, income, expense

4. **Comparative Period Calculations**
   - Create transactions in two periods
   - Generate comparative Trial Balance
   - Verify variance calculations (amount and percentage)
   - Test edge case: account has balance in one period but not the other

---

## Definition of Done

### Implementation Checklist

- [ ] All acceptance criteria scenarios pass
- [ ] 80% minimum test coverage achieved
- [ ] Unit tests written and passing
- [ ] Integration tests written and passing
- [ ] Debit/credit equality validation implemented

### Compliance Checklist

- [ ] No Enterprise module dependencies introduced (no imports from `account_reports` or other Enterprise modules)
- [ ] AGPL-3.0 license compliance verified
- [ ] Code follows OCA coding standards (pre-commit hooks, pylint-odoo pass)
- [ ] Code reviewed and approved

### Documentation Checklist

- [ ] Code documentation (docstrings, comments) complete
- [ ] User-facing documentation updated (if applicable)
- [ ] Technical documentation updated (if applicable)

### Quality Checklist

- [ ] No critical or high-severity bugs
- [ ] Performance acceptable (<30 seconds for typical datasets per FEATURE-001 requirements)
- [ ] Security considerations addressed (access rights for Accountant and Manager roles)

---

## INVEST Validation

| Criterion | Assessment | Notes |
|-----------|------------|-------|
| **I**ndependent | ✓ | Can be developed independently; builds on standard account model, doesn't require other report stories |
| **N**egotiable | ✓ | Describes outcomes (debit/credit verification, filtering) without prescribing implementation approach |
| **V**aluable | ✓ | Clear business value: verify books are balanced, prepare for financial statements, support audit |
| **E**stimable | ✓ | Well-scoped with 6 acceptance scenarios; Medium complexity |
| **S**mall | ✓ | Single report type with defined acceptance criteria; completable in one sprint |
| **T**estable | ✓ | All scenarios have objective pass/fail criteria (debits = credits, filters work, etc.) |

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2024 | Enterprise Accounting Team | Initial story creation following BDD and INVEST principles |

---

## Notes

### Auditor Perspective

As a secondary persona, Auditors benefit from Trial Balance reports for:
- Verifying that the accounting records are complete and accurate
- Identifying unusual balances or posting errors requiring investigation
- Supporting audit documentation and working papers
- Cross-referencing with General Ledger and financial statements

### Relationship to Period-End Close Process

The Trial Balance is typically generated as part of the period-end close process:
1. Post all period transactions
2. Generate Trial Balance to verify debits = credits
3. Investigate and resolve any imbalances
4. Generate financial statements (Balance Sheet, P&L)
5. Archive Trial Balance as audit documentation

### Performance Considerations

For large organizations with extensive chart of accounts and high transaction volumes:
- Consider pagination or lazy loading for accounts with many line items
- Implement efficient SQL aggregation rather than ORM-based calculations
- Cache frequently accessed account metadata
- Target: <30 seconds for datasets up to 100,000 transactions per FEATURE-001 requirements

---

## Related Documentation

- [FEATURE-001: Financial Reporting](../../features/FEATURE-001-financial-reporting.md) - Parent feature specification
- [EPIC-001: Enterprise Accounting Capabilities](../../EPIC-001-enterprise-accounting.md) - Parent epic
- [Story Template](../../templates/story-template.md) - Template used for this user story
