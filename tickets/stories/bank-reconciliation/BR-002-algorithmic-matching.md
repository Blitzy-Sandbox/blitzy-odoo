# BR-002 Algorithmic Matching

| Attribute       | Value                                                    |
|-----------------|----------------------------------------------------------|
| **Story ID**    | BR-002                                                   |
| **Title**       | Algorithmic Matching                                     |
| **Parent Feature** | [FEATURE-002: Bank Reconciliation](../../features/FEATURE-002-bank-reconciliation.md) |
| **Status**      | Draft                                                    |
| **Priority**    | Critical                                                 |
| **Estimate**    | XL (Extra Large)                                         |

---

## User Story

**As an** Accountant / Bookkeeper

**I want** the system to automatically suggest matching journal entries for bank statement lines using intelligent algorithms

**So that** I can reconcile bank statements faster with ≥95% accuracy, reducing manual effort and errors while maintaining financial data integrity

---

## Acceptance Criteria

### Scenario 1: Exact Amount and Reference Match

- **Given** an imported bank statement line with amount $1,234.56 and reference "INV-2024-001"
- **When** the matching algorithm runs
- **Then** a journal item with exact amount $1,234.56 and matching reference is suggested with high confidence score (≥95%)

### Scenario 2: Partner-Based Matching

- **Given** an imported bank statement line from "ABC Corporation" with amount $5,000
- **When** the matching algorithm runs and ABC Corporation has an open invoice for $5,000
- **Then** the open invoice is suggested as a match based on partner and amount correlation with confidence score reflecting match quality

### Scenario 3: Multiple Candidate Matches

- **Given** an imported bank statement line with amount $500 and multiple open invoices for similar amounts
- **When** the matching algorithm runs
- **Then** all candidate matches are displayed ranked by confidence score (based on reference similarity, date proximity, and partner correlation factors)

### Scenario 4: Batch Accept High-Confidence Suggestions

- **Given** 50 imported bank statement lines with algorithmic suggestions above 95% confidence threshold
- **When** I accept all high-confidence suggestions in batch
- **Then** all 50 statement lines are reconciled with their suggested matches in a single operation and marked as reconciled

### Scenario 5: Rule-Based Matching Enhancement

- **Given** reconciliation rules configured for recurring transactions (e.g., monthly rent payment, weekly payroll)
- **When** the matching algorithm processes statement lines matching rule criteria (amount range, label pattern, partner)
- **Then** the configured reconciliation model is applied and shown as suggestion with rule-based confidence boost

### Scenario 6: No Match Identification

- **Given** an imported bank statement line with no suitable journal item matches
- **When** the matching algorithm runs and no candidates meet minimum confidence threshold
- **Then** the statement line is flagged for manual review with "No Match Found" status and remains in unreconciled state

---

## Success Metric

| Metric | Target | Measurement Method |
|--------|--------|-------------------|
| **Matching Accuracy** | ≥95% | Correct matches / Total suggestions accepted |
| **Processing Speed** | <5 seconds for 1,000 lines | Timed algorithm execution |
| **High-Confidence Batch Rate** | ≥70% of lines | Lines with ≥95% confidence / Total imported lines |

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
| Reconciliation Model | `addons/account/models/account_reconcile_model.py` | Pattern matching approaches: `match_label` (contains, not_contains, match_regex), `match_amount` (lower, greater, between), `match_partner_ids`; trigger modes (manual vs auto_reconcile); line configuration for write-offs |
| Bank Statement Line | `addons/account/models/account_bank_statement_line.py` | Reconciliation state tracking (`is_reconciled`, `amount_residual`), partner extraction (`partner_id`, `partner_name`), reference fields (`payment_ref`, `transaction_details`), link to `account.move` via inherits |
| Journal Item Search | `addons/account/models/account_move_line.py` | Searchable fields for matching candidates (`ref`, `partner_id`, `amount_currency`, `date`), reconciliation status fields, account type filters for receivable/payable |
| Reconciliation Views | `addons/account/views/account_reconcile_model_views.xml` | Existing UI patterns for reconciliation rule configuration; form/tree view structures |
| Bank Statement Views | `addons/account/views/account_bank_statement_views.xml` | Statement line display patterns, reconciliation widget integration points |

### Relevant Existing Modules

- `addons/account/models/account_reconcile_model.py` - Existing reconciliation model with `AccountReconcileModel` and `AccountReconcileModelLine` classes; provides foundation for rule-based matching with triggers and line templates
- `addons/account/models/account_bank_statement_line.py` - Bank statement line model with `is_reconciled` computed field, `amount_residual` tracking, and `payment_ids` many2many for linked payments
- `addons/account/models/account_move_line.py` - Journal item model with reconciliation-related fields; search domain patterns for finding open/unreconciled items
- `addons/analytic/` - Analytic account integration for cost center matching (if applicable to reconciliation suggestions)

### OCA Module Compatibility

| OCA Repository | Module | Compatibility Consideration |
|----------------|--------|----------------------------|
| OCA/account-reconcile | `account_reconcile_oca` | Main OCA reconciliation interface; analyze matching algorithm implementation for patterns and potential integration |
| OCA/account-reconcile | `account_reconciliation_widget` | Reconciliation widget component; evaluate UI approach for displaying suggestions |
| OCA/bank-statement-import | `account_statement_import_base` | Base statement import patterns; ensure algorithmic matching integrates with import pipeline |

### Matching Algorithm Considerations

| Factor | Weight Consideration | Matching Approach |
|--------|---------------------|-------------------|
| Amount | High weight | Exact match = highest score; tolerance-based fuzzy match for near amounts |
| Reference | High weight | Substring matching on `payment_ref` vs `ref`/`name` fields; regex pattern support |
| Partner | Medium-High weight | Direct `partner_id` match; name similarity scoring for `partner_name` field |
| Date | Medium weight | Date proximity scoring; closer dates = higher confidence |
| Transaction Type | Low-Medium weight | Category matching for specific transaction types (payment, receipt, transfer) |

### Confidence Scoring Approach

The implementing agent should discover:
- How to combine weighted factors into a single confidence score (0-100%)
- Threshold configuration for high-confidence (≥95%), medium-confidence (75-94%), low-confidence (<75%)
- Handling of tie-breakers when multiple candidates have similar scores
- Performance optimization for scoring large numbers of candidate matches

---

## Dependencies

### Story Dependencies

| Dependency Type | Story ID | Story Title | Relationship |
|-----------------|----------|-------------|--------------|
| Parent Feature | FEATURE-002 | Bank Reconciliation | This story is part of the Bank Reconciliation feature |
| Blocked By | BR-001 | Statement Import | Statement import must provide statement lines for matching to process |
| Blocks | BR-004 | Reconciliation Rules | Reconciliation rules extend the algorithmic matching engine with pattern configuration |
| Related | BR-003 | Manual Reconciliation | Items without algorithmic matches require manual reconciliation workflow |
| Related | BR-005 | Partial Reconciliation | Partial matches may require specialized handling beyond standard matching |

### External Dependencies

| Dependency | Type | Notes |
|------------|------|-------|
| Fuzzy String Matching | Algorithm | May require analysis of Python libraries (e.g., `difflib`, `fuzzywuzzy`) for reference similarity scoring; verify Odoo dependency availability |
| Scoring Algorithm | Algorithm | Weighted scoring approach for combining match factors; implementation determined through discovery |
| Performance Benchmarking | Infrastructure | Testing infrastructure for validating <5 second requirement on 1,000 lines |

### Integration Points

| Odoo Model/Module | Integration Type | Purpose |
|-------------------|------------------|---------|
| `account.bank.statement.line` | Read/Write | Read statement lines for matching; write reconciliation state and matched entries |
| `account.move.line` | Read | Search for candidate journal items (open invoices, payments) to match against statement lines |
| `account.reconcile.model` | Read | Apply configured reconciliation rules to enhance matching suggestions |
| `account.move` | Write | Create/update journal entries when reconciliation is confirmed |
| `res.partner` | Read | Partner lookup for correlation scoring based on statement partner_name/partner_id |
| `account.account` | Read | Filter candidates by account type (receivable/payable) for appropriate matching context |

---

## Test Requirements

### Coverage Requirement

| Metric | Requirement | Notes |
|--------|-------------|-------|
| **Minimum Test Coverage** | **80%** | Mandatory for all new functionality |
| Unit Test Coverage | 80%+ | Matching algorithm components, confidence scoring |
| Integration Test Coverage | 80%+ | End-to-end matching with real statement/journal data |
| Performance Test Coverage | Required | Validation of <5 second performance on 1,000 lines |

### Unit Test Scenarios

| Acceptance Scenario | Unit Test Focus | Key Assertions |
|---------------------|-----------------|----------------|
| Scenario 1: Exact Match | Amount matching function, reference comparison | Exact amount returns 100% amount score; exact reference returns 100% reference score |
| Scenario 2: Partner Matching | Partner lookup, name similarity | Partner ID match scores higher than name similarity; unrecognized partner returns 0 |
| Scenario 3: Multiple Candidates | Candidate ranking, score sorting | Results ordered by descending confidence; ties handled consistently |
| Scenario 4: Batch Accept | Bulk reconciliation, transaction integrity | All accepted items reconciled atomically; rollback on partial failure |
| Scenario 5: Rule Enhancement | Rule evaluation, confidence boost | Matching rules increase base confidence score; rule criteria correctly evaluated |
| Scenario 6: No Match | Minimum threshold, unreconciled status | Items below threshold flagged; `is_reconciled` remains False |

### Integration Test Considerations

- [ ] Test integration with `account.bank.statement.line` model for reading and updating reconciliation state
- [ ] Test integration with `account.move.line` model for candidate search queries
- [ ] Test integration with `account.reconcile.model` for rule-based matching enhancement
- [ ] Test cross-module functionality with statement import (BR-001 output as input)
- [ ] Test performance with realistic data volumes (100, 500, 1,000 statement lines)
- [ ] Test accuracy metrics calculation (correct matches / total accepted)

### Acceptance Test Mapping

| BDD Scenario | Test Method Name | Test Type |
|--------------|------------------|-----------|
| Scenario 1: Exact Amount and Reference Match | `test_exact_amount_reference_match` | Acceptance |
| Scenario 2: Partner-Based Matching | `test_partner_based_matching` | Acceptance |
| Scenario 3: Multiple Candidate Matches | `test_multiple_candidates_ranked` | Acceptance |
| Scenario 4: Batch Accept High-Confidence | `test_batch_accept_high_confidence` | Acceptance |
| Scenario 5: Rule-Based Matching Enhancement | `test_rule_based_matching_boost` | Acceptance |
| Scenario 6: No Match Identification | `test_no_match_flagged_for_review` | Acceptance |

### Performance Test Scenarios

| Test Case | Data Volume | Target Time | Assertions |
|-----------|-------------|-------------|------------|
| Small batch matching | 100 statement lines | <1 second | All lines processed; suggestions generated |
| Medium batch matching | 500 statement lines | <3 seconds | All lines processed; memory usage stable |
| Large batch matching | 1,000 statement lines | <5 seconds | All lines processed; performance target met |
| Accuracy validation | 100 pre-mapped pairs | ≥95% accuracy | Correct suggestions / Total suggestions ≥ 0.95 |

---

## Definition of Done

### Implementation Checklist

- [ ] All 6 acceptance criteria scenarios pass
- [ ] 80% minimum test coverage achieved
- [ ] Unit tests written and passing for all matching algorithm components
- [ ] Integration tests written and passing for statement line reconciliation workflow
- [ ] Performance tests confirm <5 second execution for 1,000 lines
- [ ] Accuracy tests confirm ≥95% matching accuracy on test data

### Compliance Checklist

- [ ] No Enterprise module dependencies introduced (specifically no `account_accountant` imports)
- [ ] AGPL-3.0 license compliance verified for all new code
- [ ] Code follows OCA coding standards (pre-commit hooks pass, pylint-odoo clean)
- [ ] Code reviewed and approved by peer

### Documentation Checklist

- [ ] Code documentation (docstrings, comments) complete for matching algorithm
- [ ] Confidence scoring approach documented
- [ ] User-facing documentation for matching suggestions interface (if applicable)
- [ ] Technical documentation for algorithm tuning parameters

### Quality Checklist

- [ ] No critical or high-severity bugs
- [ ] Performance acceptable (<5 seconds for 1,000 lines)
- [ ] Security considerations addressed (no SQL injection in search queries)
- [ ] Memory usage optimized for large batch processing

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2024 | Enterprise Accounting Team | Initial story creation |

---

## Notes

### Algorithm Design Principles

The algorithmic matching functionality should adhere to these principles (implementation details determined through codebase discovery):

1. **Deterministic Results**: Same inputs should produce same ranked suggestions for auditability
2. **Explainable Confidence**: Users should understand why a match was suggested (which factors contributed)
3. **Configurable Thresholds**: High-confidence threshold (95%) should be configurable per company/journal
4. **Graceful Degradation**: If one matching factor is unavailable (e.g., no partner), algorithm should still function with remaining factors
5. **Non-Destructive**: Suggestions are proposals only; no automatic reconciliation without user confirmation (except batch accept)

### Edge Cases to Consider

- Statement lines with zero amount (fees, adjustments)
- Multi-currency matching (statement currency vs journal entry currency)
- Negative amounts (refunds, reversals)
- Very old open invoices (date proximity scoring impact)
- Duplicate invoice references across different partners
- Partial payments where statement amount doesn't match any single invoice

### Success Metric Clarification

The ≥95% accuracy target is measured as:
- **Numerator**: Number of algorithmic suggestions that, when accepted by the user, correctly matched the intended journal entry (verified through audit or subsequent reconciliation review)
- **Denominator**: Total number of algorithmic suggestions accepted by users
- **Exclusions**: Items flagged as "No Match Found" are not counted in accuracy calculation
- **Measurement Period**: Calculated monthly or per reconciliation batch for ongoing quality monitoring

---

<!--
================================================================================
INVEST VALIDATION CHECKLIST
================================================================================
✓ Independent - Can be developed after BR-001 (Statement Import) completes
✓ Negotiable - Describes matching behavior outcomes, not specific algorithm implementation
✓ Valuable - Directly enables ≥95% matching accuracy goal, reducing manual effort
✓ Estimable - XL estimate reflects complexity of matching algorithm development
✓ Small - Focused on algorithmic matching only; manual reconciliation is separate story
✓ Testable - Clear acceptance criteria with measurable accuracy and performance targets
================================================================================
-->
