# BR-003 Manual Reconciliation

| Attribute       | Value                                                    |
|-----------------|----------------------------------------------------------|
| **Story ID**    | BR-003                                                   |
| **Title**       | Manual Reconciliation                                    |
| **Parent Feature** | [FEATURE-002: Bank Reconciliation](../../features/FEATURE-002-bank-reconciliation.md) |
| **Status**      | Draft                                                    |
| **Priority**    | Critical                                                 |
| **Estimate**    | L (Large)                                                |

---

## User Story

**As an** Accountant / Bookkeeper

**I want** to manually reconcile bank statement lines with journal entries when automatic matching fails or is not suitable

**So that** I can ensure all bank transactions are properly accounted for and matched to the correct business transactions, maintaining complete and accurate financial records

---

## Acceptance Criteria

### Scenario 1: Search for Matching Journal Items

- **Given** an unreconciled bank statement line for a customer payment
- **When** I search for matching journal entries using payment reference, amount, or partner name
- **Then** I see a list of candidate journal items matching my search criteria, sorted by relevance

### Scenario 2: Select and Reconcile Single Match

- **Given** an unreconciled bank statement line and a list of candidate journal items
- **When** I select a journal item with matching amount and confirm reconciliation
- **Then** the statement line is reconciled with the selected journal item, both are marked as reconciled, and a matching number is assigned

### Scenario 3: Reconcile with Multiple Journal Items

- **Given** an unreconciled bank statement line for $1,000
- **When** I select two journal items of $400 and $600 for reconciliation
- **Then** the statement line is fully reconciled against both journal items, and all three records share the same matching reference

### Scenario 4: Create Write-off Entry During Reconciliation

- **Given** an unreconciled bank statement line for $998 and a journal item for $1,000
- **When** I reconcile with a $2 write-off entry to a bank charges account
- **Then** a new journal entry for the $2 difference is created and posted, and reconciliation is completed

### Scenario 5: Create New Entry During Reconciliation

- **Given** an unreconciled bank statement line with no matching existing transactions
- **When** I create a new journal entry directly during reconciliation specifying account and details
- **Then** a new journal entry is created and automatically reconciled with the statement line

### Scenario 6: Undo Manual Reconciliation

- **Given** a previously reconciled bank statement line and journal item pair
- **When** I select to unreconcile the statement line
- **Then** the reconciliation is removed, both records return to unreconciled status, and any auto-generated write-off entries are reversed

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
| Bank Statement Line Model | `addons/account/models/account_bank_statement_line.py` | Reconciliation state tracking (`is_reconciled`, `amount_residual` computed fields), `action_undo_reconciliation()` method for unreconciliation, `_seek_for_lines()` helper for liquidity/suspense/other line separation, `_prepare_move_line_default_vals()` for counterpart entry creation |
| Journal Item Model | `addons/account/models/account_move_line.py` | Searchable fields for matching candidates (`ref`, `name`, `partner_id`, `amount_currency`, `date`), `reconciled` field, `amount_residual` tracking, `reconcile()` and `remove_move_reconcile()` methods |
| Reconciliation Model | `addons/account/models/account_reconcile_model.py` | `AccountReconcileModelLine` for write-off line templates, trigger modes (manual vs auto), line configuration for creating counterpart entries during reconciliation |
| Journal Entry Model | `addons/account/models/account_move.py` | Journal entry creation patterns, posting workflow, line synchronization with statement lines |
| Reconciliation Views | `addons/account/views/account_reconcile_model_views.xml` | Existing UI patterns for reconciliation interface; form/tree view structures for reconciliation rules |
| Bank Statement Views | `addons/account/views/account_bank_statement_views.xml` | Statement line display patterns, reconciliation widget integration points, action bindings |

### Relevant Existing Modules

- `addons/account/models/account_bank_statement_line.py` - Bank statement line model with `is_reconciled` computed field tracking reconciliation status based on move line reconciliation state, `amount_residual` for partial reconciliation tracking, `action_undo_reconciliation()` method that removes reconciliation and resets to suspense account lines, `_get_default_amls_matching_domain()` for building search domains of reconcilable journal items
- `addons/account/models/account_move_line.py` - Journal item model with reconciliation methods (`reconcile()`, `remove_move_reconcile()`), `matched_debit_ids`/`matched_credit_ids` for tracking reconciliation pairs, `full_reconcile_id` for matching reference assignment
- `addons/account/models/account_reconcile_model.py` - Reconciliation rule model providing write-off line templates with account assignment, tax handling, and automatic entry creation during reconciliation
- `addons/account/models/account_partial_reconcile.py` - Partial reconciliation tracking model that manages the link between reconciled journal items

### OCA Module Compatibility

| OCA Repository | Module | Compatibility Consideration |
|----------------|--------|----------------------------|
| OCA/account-reconcile | `account_reconcile_oca` | Main OCA reconciliation interface; analyze manual matching workflow implementation for UI patterns and user interaction design |
| OCA/account-reconcile | `account_reconciliation_widget` | Reconciliation widget component; evaluate candidate search interface and multi-select reconciliation patterns |
| OCA/bank-statement-import | Various | Ensure manual reconciliation integrates with imported statement lines without format-specific dependencies |

### Key Implementation Patterns Identified

| Pattern | Source Location | Relevance to Story |
|---------|-----------------|-------------------|
| Reconciliation State Computation | `account_bank_statement_line.py:_compute_is_reconciled()` | Determines when statement line is fully reconciled based on suspense line residual |
| Matching Domain Builder | `account_bank_statement_line.py:_get_default_amls_matching_domain()` | Provides base domain for finding reconcilable journal items (posted, unreconciled, correct account types) |
| Undo Reconciliation | `account_bank_statement_line.py:action_undo_reconciliation()` | Existing pattern for removing reconciliation: unlinks payments, removes move reconcile, resets to default vals |
| Line Separation | `account_bank_statement_line.py:_seek_for_lines()` | Helper to separate liquidity lines, suspense lines, and other lines from statement move |
| Write-off Creation | `account_reconcile_model.py:AccountReconcileModelLine` | Template for creating write-off/counterpart lines with account, tax, and analytic configuration |

### Manual Reconciliation Workflow Considerations

The implementing agent should discover:

1. **Candidate Search Interface**: How to present searchable journal items with filtering by amount, reference, partner, and date range
2. **Multi-Select Reconciliation**: Mechanism for selecting multiple journal items to reconcile against single statement line
3. **Write-off Handling**: Integration with `account.reconcile.model.line` patterns for difference handling with configurable accounts
4. **New Entry Creation**: Workflow for creating and posting journal entries inline during reconciliation without leaving the interface
5. **Reconciliation Confirmation**: Transaction handling to ensure atomicity of multi-item reconciliation operations
6. **Matching Number Assignment**: How `full_reconcile_id` is assigned when reconciliation is complete

---

## Dependencies

### Story Dependencies

| Dependency Type | Story ID | Story Title | Relationship |
|-----------------|----------|-------------|--------------|
| Parent Feature | FEATURE-002 | Bank Reconciliation | This story is part of the Bank Reconciliation feature |
| Blocked By | BR-001 | Statement Import | Manual reconciliation operates on imported bank statement lines |
| Related | BR-002 | Algorithmic Matching | Items without algorithmic matches require manual reconciliation; manual interface may display algorithmic suggestions |
| Blocks | BR-005 | Partial Reconciliation | Partial reconciliation is a specialized manual workflow extending manual reconciliation capabilities |
| Related | BR-004 | Reconciliation Rules | Rules may provide write-off templates used during manual reconciliation |

### External Dependencies

| Dependency | Type | Notes |
|------------|------|-------|
| Journal Item Search | Data Model | Requires efficient search across `account.move.line` records with multiple filter criteria |
| Reconciliation Matching | Algorithm | Linking mechanism between statement lines and journal items via partial reconcile records |
| Write-off Account Configuration | Configuration | Users must have access to configure or select write-off accounts for difference handling |

### Integration Points

| Odoo Model/Module | Integration Type | Purpose |
|-------------------|------------------|---------|
| `account.bank.statement.line` | Read/Write | Read unreconciled statement lines; write reconciliation state and linked journal items |
| `account.move.line` | Read/Write | Search for candidate journal items; create reconciliation links via `reconcile()` method |
| `account.move` | Write | Create new journal entries for write-offs and direct entry creation during reconciliation |
| `account.partial.reconcile` | Write | Create reconciliation links between statement line's move lines and matched journal items |
| `account.full.reconcile` | Write | Assign matching number when reconciliation is complete |
| `account.reconcile.model` | Read | Access reconciliation rules for write-off templates |
| `res.partner` | Read | Partner lookup for search filtering and new entry creation |
| `account.account` | Read | Account selection for write-offs and new entries |

---

## Test Requirements

### Coverage Requirement

| Metric | Requirement | Notes |
|--------|-------------|-------|
| **Minimum Test Coverage** | **80%** | Mandatory for all new functionality |
| Unit Test Coverage | 80%+ | Search functions, reconciliation logic, write-off creation |
| Integration Test Coverage | 80%+ | End-to-end manual reconciliation workflows |

### Unit Test Scenarios

| Acceptance Scenario | Unit Test Focus | Key Assertions |
|---------------------|-----------------|----------------|
| Scenario 1: Search for Matching Journal Items | Candidate search function with domain filtering | Search returns unreconciled items matching criteria; results sorted by relevance; correct fields searchable |
| Scenario 2: Select and Reconcile Single Match | Single-item reconciliation method | Statement line `is_reconciled` becomes True; journal item reconciled; matching number assigned |
| Scenario 3: Reconcile with Multiple Journal Items | Multi-item reconciliation method | All items share same `full_reconcile_id`; total amounts balance; statement line fully reconciled |
| Scenario 4: Create Write-off Entry | Write-off entry creation during reconciliation | Journal entry created with correct account; amounts match difference; entry is posted |
| Scenario 5: Create New Entry During Reconciliation | Inline journal entry creation | New move created and posted; automatically reconciled with statement line |
| Scenario 6: Undo Manual Reconciliation | `action_undo_reconciliation()` method | Reconciliation removed; items return to unreconciled; write-off entries reversed/deleted |

### Integration Test Considerations

- [ ] Test integration with `account.bank.statement.line` model for reading unreconciled lines and updating reconciliation state
- [ ] Test integration with `account.move.line` model for candidate search and reconciliation link creation
- [ ] Test integration with `account.move` model for write-off and new entry creation during reconciliation
- [ ] Test integration with `account.partial.reconcile` and `account.full.reconcile` models for matching number assignment
- [ ] Test cross-module functionality with statement import (BR-001 imported lines as input)
- [ ] Test workflow after algorithmic matching (BR-002 unmatched items as input)
- [ ] Test multi-currency reconciliation scenarios with foreign currency statement lines
- [ ] Test transaction integrity: verify atomic operations for multi-item reconciliation

### Acceptance Test Mapping

| BDD Scenario | Test Method Name | Test Type |
|--------------|------------------|-----------|
| Scenario 1: Search for Matching Journal Items | `test_search_matching_journal_items` | Acceptance |
| Scenario 2: Select and Reconcile Single Match | `test_reconcile_single_match` | Acceptance |
| Scenario 3: Reconcile with Multiple Journal Items | `test_reconcile_multiple_items` | Acceptance |
| Scenario 4: Create Write-off Entry | `test_create_writeoff_during_reconciliation` | Acceptance |
| Scenario 5: Create New Entry During Reconciliation | `test_create_new_entry_during_reconciliation` | Acceptance |
| Scenario 6: Undo Manual Reconciliation | `test_undo_manual_reconciliation` | Acceptance |

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
- [ ] Performance acceptable (manual reconciliation response <2 seconds per action)
- [ ] Security considerations addressed (access rights for reconciliation operations)

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2024 | Enterprise Accounting Team | Initial story creation |

---

## Notes

### Relationship to Algorithmic Matching (BR-002)

Manual reconciliation serves as the fallback workflow when algorithmic matching (BR-002) cannot find suitable matches or when the user disagrees with automatic suggestions. The manual interface should:

- Display any algorithmic suggestions alongside search results
- Allow users to override automatic matches
- Provide clear visual distinction between suggested and user-selected matches

### Write-off Threshold Consideration

For small differences (e.g., bank charges, rounding), the system should provide easy access to common write-off accounts. Consider integration with reconciliation rules (BR-004) to auto-suggest write-off accounts based on patterns.

### Audit Trail Requirements

Manual reconciliation creates an audit trail of user decisions. Each reconciliation action should be traceable to:
- The user who performed the reconciliation
- The timestamp of the action
- The original unreconciled state for potential reversal

### Multi-Currency Handling

When the bank statement line currency differs from the journal item currency, the reconciliation interface must:
- Display amounts in both currencies
- Handle exchange rate differences appropriately
- Create exchange difference entries when needed

### Performance Considerations

The candidate search must remain responsive even with large numbers of unreconciled journal items. Consider:
- Pagination of search results
- Efficient database indexing on search fields
- Caching of frequently accessed reference data
