# BR-005 Partial Reconciliation

| Attribute       | Value                                                    |
|-----------------|----------------------------------------------------------|
| **Story ID**    | BR-005                                                   |
| **Title**       | Partial Reconciliation                                   |
| **Parent Feature** | [FEATURE-002: Bank Reconciliation](../../features/FEATURE-002-bank-reconciliation.md) |
| **Status**      | Draft                                                    |
| **Priority**    | High                                                     |
| **Estimate**    | L (Large)                                                |

---

## User Story

**As an** Accountant / Bookkeeper

**I want** to partially reconcile bank statement lines with journal entries when amounts don't match exactly

**So that** I can handle real-world scenarios where one bank transaction covers multiple invoices or one invoice is paid in installments, maintaining accurate financial records without forcing artificial matches

---

## Acceptance Criteria

### Scenario 1: Partial Payment Against Single Invoice

- **Given** a bank statement line for $500 and an open invoice for $1,000
- **When** I reconcile the statement line against the invoice as a partial payment
- **Then** a partial reconciliation record is created linking the statement line to the invoice with amount $500, and the invoice shows remaining balance of $500

### Scenario 2: Single Payment Against Multiple Invoices

- **Given** a bank statement line for $1,500 and three open invoices for $400, $500, and $600
- **When** I select all three invoices for reconciliation against the statement line
- **Then** all three invoices are fully reconciled, the statement line is fully matched with total $1,500, and a full reconciliation record links all items together

### Scenario 3: Partial Match with Write-off

- **Given** a bank statement line for $995 and an open invoice for $1,000
- **When** I reconcile the statement line against the invoice and configure a $5 write-off for bank charges
- **Then** the invoice is fully reconciled, a write-off entry for $5 is created and posted, and the statement line is fully matched

### Scenario 4: View Partial Reconciliation Status

- **Given** an invoice that has been partially paid through multiple bank transactions
- **When** I view the invoice reconciliation details
- **Then** I see a list of all partial reconciliation records with payment amounts and dates, the max date of matched lines, and the remaining open balance

### Scenario 5: Unreconcile Partial Match

- **Given** a partially reconciled invoice with one of multiple payments
- **When** I unreconcile a specific partial reconciliation
- **Then** only that partial reconciliation is removed, other partial reconciliations remain intact, the invoice balance is updated accordingly, and any associated exchange difference entries are reversed

### Scenario 6: Multi-Currency Partial Reconciliation

- **Given** a bank statement line in EUR and an open invoice in USD
- **When** I partially reconcile with exchange rate conversion
- **Then** the partial reconciliation records company currency amount, debit currency amount (EUR), and credit currency amount (USD), and any exchange difference is tracked via an exchange move entry

---

## Constraints

### License and Compliance

- [x] **AGPL-3.0 Compatibility**: Module/feature must be distributed under AGPL-3.0 compatible license
- [x] **No Enterprise Dependencies**: No imports or dependencies on Odoo Enterprise edition modules (specifically `account_accountant` module which provides Enterprise reconciliation features)
- [x] **OCA Coding Standards**: Implementation must follow Odoo and OCA (Odoo Community Association) coding standards

### Version Compatibility

- [x] **Target Version**: Odoo 18.0 compatibility required
- [x] **Repository Note**: Current repository is Odoo 19.0; implementation should be version-agnostic where possible

---

## Technical Discovery Notes

> **Purpose:** These notes guide implementing agents in their codebase analysis before making implementation decisions. User stories describe WHAT and WHY; implementation details emerge from agent discovery of the codebase.

### Codebase Analysis Areas

| Area | Files/Modules to Examine | Analysis Focus |
|------|-------------------------|----------------|
| Partial Reconcile Model | `addons/account/models/account_partial_reconcile.py` | Core partial reconciliation record structure: `debit_move_id`/`credit_move_id` linking to journal items, `amount` in company currency, `debit_amount_currency`/`credit_amount_currency` for multi-currency, `full_reconcile_id` when complete, `exchange_move_id` for exchange differences, `max_date` computation for reporting |
| Full Reconcile Model | `addons/account/models/account_full_reconcile.py` | Understanding when partial becomes full: `partial_reconcile_ids` linking partials, `reconciled_line_ids` for matched journal items, creation triggers when all partials balance |
| Bank Statement Line | `addons/account/models/account_bank_statement_line.py` | Statement line reconciliation state: `is_reconciled` computed field, `amount_residual` for partial tracking, reconciliation helpers `_seek_for_lines()` for liquidity/suspense separation |
| Journal Item Reconciliation | `addons/account/models/account_move_line.py` | `matched_debit_ids`/`matched_credit_ids` for tracking partial reconciliations, `amount_residual`/`amount_residual_currency` for remaining balance, `reconcile()` method for creating partials |
| Reconciliation Model | `addons/account/models/account_reconcile_model.py` | Write-off handling patterns in `AccountReconcileModelLine`, counterpart entry creation during partial reconciliation with difference handling |

### Relevant Existing Modules

- `addons/account/models/account_partial_reconcile.py` - Core partial reconciliation model with `debit_move_id`/`credit_move_id` linking two journal items, multi-currency support via separate currency amount fields, `_compute_max_date()` for aged report integration, `unlink()` method handling cascade deletion of full reconcile and reversal of exchange/CABA moves
- `addons/account/models/account_full_reconcile.py` - Full reconciliation model tracking when all partial reconciliations for a set of journal items balance completely; manages matching number assignment via `_update_matching_number()` callback
- `addons/account/models/account_bank_statement_line.py` - Bank statement line with `is_reconciled` computed from suspense line residual, `action_undo_reconciliation()` for removing partial matches, move-based architecture via `_inherits`
- `addons/account/models/account_move_line.py` - Journal item reconciliation through `matched_debit_ids`/`matched_credit_ids` One2many fields to `account.partial.reconcile`, residual tracking for partial payment scenarios

### OCA Module Compatibility

| OCA Repository | Module | Compatibility Consideration |
|----------------|--------|----------------------------|
| OCA/account-reconcile | `account_reconcile_oca` | Main OCA reconciliation interface; analyze partial reconciliation workflow patterns and multi-select interface for splitting payments |
| OCA/account-reconcile | `account_partial_reconcile` | If exists, evaluate for patterns on partial match UI and remaining balance visualization |
| OCA/account-financial-tools | `account_partial_reconcile_mixin` | Potential mixin patterns for reusable partial reconciliation logic |

### Key Implementation Patterns Identified

| Pattern | Source Location | Relevance to Story |
|---------|-----------------|-------------------|
| Partial Reconcile Creation | `account_partial_reconcile.py:create()` | Creates partial record linking debit/credit moves; updates payment state via `_get_to_update_payments()` |
| Partial Reconcile Deletion | `account_partial_reconcile.py:unlink()` | Reverses exchange moves and CABA entries, unlinks full reconcile, updates matching numbers |
| Multi-Currency Amounts | `account_partial_reconcile.py` fields | `amount` (company), `debit_amount_currency`, `credit_amount_currency` - always positive amounts |
| Exchange Move Tracking | `account_partial_reconcile.py:exchange_move_id` | Links to exchange difference journal entry for multi-currency reconciliation |
| Matching Number Update | `account_partial_reconcile.py:_update_matching_number()` | Graph-based algorithm for assigning matching numbers across related partial reconciliations |
| Reconciliation State | `account_bank_statement_line.py:_compute_is_reconciled()` | Checks if suspense line amount_currency is zero to determine reconciled status |

### Partial Reconciliation Workflow Considerations

The implementing agent should discover:

1. **Partial Record Creation**: How `account.partial.reconcile` links a debit move line to a credit move line with specified amounts, respecting both company currency and foreign currencies
2. **Full Reconcile Trigger**: Logic determining when partial reconciliations collectively balance and trigger `account.full.reconcile` creation
3. **Multi-Invoice Selection**: Interface pattern for selecting multiple invoices against single payment with automatic amount distribution
4. **Write-off Integration**: Creating counterpart write-off entries for payment differences while maintaining partial reconciliation links
5. **Currency Handling**: Managing `debit_currency_id`/`credit_currency_id` fields and exchange difference move generation
6. **Unreconciliation Cascade**: Proper cleanup when removing individual partial reconciliations vs. entire reconciliation sets

---

## Dependencies

### Story Dependencies

| Dependency Type | Story ID | Story Title | Relationship |
|-----------------|----------|-------------|--------------|
| Parent Feature | FEATURE-002 | Bank Reconciliation | This story is part of the Bank Reconciliation feature |
| Blocked By | BR-001 | Statement Import | Partial reconciliation operates on imported bank statement lines |
| Blocked By | BR-003 | Manual Reconciliation | Partial reconciliation extends manual reconciliation with amount splitting capability |
| Related | BR-002 | Algorithmic Matching | Algorithmic suggestions may identify partial match candidates; partial reconciliation provides resolution mechanism |
| Related | BR-004 | Reconciliation Rules | Rules may configure default write-off accounts for partial reconciliation differences |

### External Dependencies

| Dependency | Type | Notes |
|------------|------|-------|
| Multi-Currency Configuration | Configuration | Company and journal currency settings must be properly configured for multi-currency partial reconciliation |
| Exchange Rate Source | Data | Current exchange rates required for multi-currency reconciliation calculations |
| Write-off Account Configuration | Configuration | Users must have configured write-off accounts (bank charges, exchange differences) for handling reconciliation differences |

### Integration Points

| Odoo Model/Module | Integration Type | Purpose |
|-------------------|------------------|---------|
| `account.partial.reconcile` | Write | Create and manage partial reconciliation records linking bank statement move lines to invoice move lines |
| `account.full.reconcile` | Write | Assign matching numbers when partial reconciliations collectively balance |
| `account.bank.statement.line` | Read/Write | Read statement lines for reconciliation; update reconciliation state |
| `account.move.line` | Read/Write | Read candidate journal items; update matched_debit_ids/matched_credit_ids via partial reconcile |
| `account.move` | Write | Create exchange difference entries, write-off entries during partial reconciliation |
| `res.currency` | Read | Currency conversion for multi-currency partial reconciliation |
| `account.reconcile.model` | Read | Access write-off templates for difference handling |

---

## Test Requirements

### Coverage Requirement

| Metric | Requirement | Notes |
|--------|-------------|-------|
| **Minimum Test Coverage** | **80%** | Mandatory for all new functionality |
| Unit Test Coverage | 80%+ | Partial reconcile CRUD, amount calculations, currency handling |
| Integration Test Coverage | 80%+ | End-to-end partial reconciliation workflows, multi-module interactions |

### Unit Test Scenarios

| Acceptance Scenario | Unit Test Focus | Key Assertions |
|---------------------|-----------------|----------------|
| Scenario 1: Partial Payment Against Single Invoice | Partial reconcile record creation | Partial reconcile links correct move lines; invoice shows correct remaining balance; amounts are positive |
| Scenario 2: Single Payment Against Multiple Invoices | Multi-invoice reconciliation | All invoices marked reconciled; full reconcile created; total amounts balance to statement line |
| Scenario 3: Partial Match with Write-off | Write-off entry creation | Write-off journal entry created; correct account used; amounts reconciled to zero |
| Scenario 4: View Partial Reconciliation Status | Status retrieval logic | Partial reconcile records accessible; max_date computed correctly; remaining balance accurate |
| Scenario 5: Unreconcile Partial Match | Partial unlink cascade | Only target partial removed; full reconcile updated or deleted; exchange moves reversed |
| Scenario 6: Multi-Currency Partial Reconciliation | Currency amount handling | Company and foreign amounts recorded; exchange_move_id created when difference exists |

### Integration Test Considerations

- [ ] Test partial reconciliation creation via `account.partial.reconcile.create()` with all required fields
- [ ] Test partial reconciliation unlink and cascade effects on full reconcile and exchange moves
- [ ] Test multi-invoice reconciliation ensuring correct matching number assignment
- [ ] Test write-off creation during partial reconciliation with configurable accounts
- [ ] Test multi-currency scenarios with EUR bank statements against USD invoices
- [ ] Test edge case: partial reconcile amount equals zero (should not be allowed)
- [ ] Test edge case: partial reconcile where both move lines have same currency
- [ ] Test integration with statement import (BR-001) and manual reconciliation (BR-003)
- [ ] Test transaction integrity: ensure atomic operations for complex partial reconciliation sets

### Acceptance Test Mapping

| BDD Scenario | Test Method Name | Test Type |
|--------------|------------------|-----------|
| Scenario 1: Partial Payment Against Single Invoice | `test_partial_payment_single_invoice` | Acceptance |
| Scenario 2: Single Payment Against Multiple Invoices | `test_payment_multiple_invoices` | Acceptance |
| Scenario 3: Partial Match with Write-off | `test_partial_match_with_writeoff` | Acceptance |
| Scenario 4: View Partial Reconciliation Status | `test_view_partial_reconciliation_status` | Acceptance |
| Scenario 5: Unreconcile Partial Match | `test_unreconcile_partial_match` | Acceptance |
| Scenario 6: Multi-Currency Partial Reconciliation | `test_multicurrency_partial_reconciliation` | Acceptance |

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
- [ ] Performance acceptable (partial reconciliation operations <2 seconds)
- [ ] Security considerations addressed (access rights for reconciliation operations)

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2024 | Enterprise Accounting Team | Initial story creation |

---

## Notes

### Business Context

Partial reconciliation is essential for handling real-world payment scenarios:

1. **Installment Payments**: Customers paying invoices in multiple installments over time
2. **Bulk Payments**: Single bank transfer covering multiple invoices
3. **Payment Differences**: Minor discrepancies due to bank charges, exchange rates, or rounding
4. **Advance Payments**: Deposits applied against future invoices

### Accounting Standards Compliance

Partial reconciliation implementation should ensure:

- **GAAP Compliance**: Proper recognition of partially settled receivables/payables
- **IFRS Compliance**: Correct treatment of exchange differences per IAS 21
- **Audit Trail**: Complete tracking of all partial matches for audit purposes

### Related Odoo Models Summary

The partial reconciliation feature builds upon these core Odoo models:

```
account.partial.reconcile
├── debit_move_id → account.move.line (debit side)
├── credit_move_id → account.move.line (credit side)
├── full_reconcile_id → account.full.reconcile (when complete)
├── exchange_move_id → account.move (exchange difference entry)
├── amount (company currency)
├── debit_amount_currency (debit line currency)
└── credit_amount_currency (credit line currency)

account.full.reconcile
├── partial_reconcile_ids → account.partial.reconcile (linked partials)
└── reconciled_line_ids → account.move.line (all matched lines)
```

### Discovery Notes for Implementation

The implementing agent should particularly focus on:

1. The `_update_matching_number()` method in `account_partial_reconcile.py` which uses a graph-based algorithm to assign matching numbers
2. The `unlink()` override which handles cascade deletion and reversal of associated entries
3. The `_check_required_computed_currencies()` constraint ensuring currency fields are populated
4. The relationship between `is_reconciled` on statement lines and `amount_residual` on move lines
