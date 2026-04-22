# BR-004 Reconciliation Rules

| Attribute       | Value                                                    |
|-----------------|----------------------------------------------------------|
| **Story ID**    | BR-004                                                   |
| **Title**       | Reconciliation Rules                                     |
| **Parent Feature** | [FEATURE-002: Bank Reconciliation](../../features/FEATURE-002-bank-reconciliation.md) |
| **Status**      | Draft                                                    |
| **Priority**    | High                                                     |
| **Estimate**    | L (Large)                                                |

---

## User Story

**As an** Accountant / Bookkeeper

**I want** to configure reconciliation rules that define matching criteria and automatic journal entry creation

**So that** repetitive reconciliation patterns are automated, reducing manual effort and ensuring consistency in how common transaction types are processed

---

## Acceptance Criteria

### Scenario 1: Create Pattern-Based Matching Rule

- **Given** I am configuring a new reconciliation rule
- **When** I define matching criteria based on label contains "PAYROLL" and amount range $10,000-$50,000
- **Then** the rule is saved and will be suggested when bank statement lines match these criteria

### Scenario 2: Configure Auto-Reconcile Rule

- **Given** a reconciliation rule with specific matching conditions
- **When** I set the rule trigger to "Automated"
- **Then** statement lines matching the conditions are automatically reconciled without user intervention

### Scenario 3: Define Write-off Amount in Rule

- **Given** a reconciliation rule for bank fee transactions
- **When** I configure the rule with a fixed write-off amount to a bank charges expense account
- **Then** matching transactions automatically create the write-off entry when the rule is applied

### Scenario 4: Configure Regex-Based Label Matching

- **Given** I need to match transactions with varying formats like "INV-12345" or "INVOICE-12345"
- **When** I configure a rule with regex pattern matching `(INV(OICE)?-\d+)`
- **Then** the rule matches all transactions whose label contains invoice references matching the pattern

### Scenario 5: Test Rule Against Historical Transactions

- **Given** a newly created reconciliation rule
- **When** I preview the rule against existing unreconciled statement lines
- **Then** I see a list of statement lines that would match this rule, allowing verification before activation

### Scenario 6: Manage Rule Priority and Sequence

- **Given** multiple reconciliation rules that could apply to the same transaction
- **When** I reorder rules by sequence number
- **Then** rules are evaluated in the specified order, and the first matching rule takes precedence

---

## Success Metric

| Metric | Target | Measurement Method |
|--------|--------|-------------------|
| **Rule Creation Success** | 100% valid rules | All saved rules pass validation constraints |
| **Auto-Reconcile Accuracy** | ≥98% correct matches | Automated reconciliations reviewed for accuracy |
| **Rule Evaluation Speed** | <1 second per rule | Timed rule execution benchmark |
| **User Adoption** | ≥3 rules per active company | Count of active rules per company |

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
| Reconciliation Model | `addons/account/models/account_reconcile_model.py` | Existing `account.reconcile.model` structure: `trigger` field (manual vs auto_reconcile), `match_label` selection (contains, not_contains, match_regex), `match_amount` selection (lower, greater, between), `match_partner_ids`, `match_journal_ids`, `sequence` ordering |
| Reconciliation Model Line | `addons/account/models/account_reconcile_model.py` | `account.reconcile.model.line` for write-off configuration: `account_id`, `amount_type` (fixed, percentage, regex), `amount_string`, `tax_ids`, `partner_id`, `label` fields |
| Regex Validation | `addons/account/models/account_reconcile_model.py` | `_check_match_label_param` constraint method using Python `re.compile()` for regex validation; `_validate_amount` for regex amount extraction patterns |
| Bank Statement Line | `addons/account/models/account_bank_statement_line.py` | Fields available for rule matching: `payment_ref` (label), `amount`, `partner_id`, `partner_name`, `transaction_type`, `transaction_details`; `is_reconciled` state tracking |
| Reconciliation Views | `addons/account/views/account_reconcile_model_views.xml` | Form view structure for rule configuration; tree view with sequence handle widget; field visibility conditions based on `match_label` and `match_amount` selections |

### Relevant Existing Modules

- `addons/account/models/account_reconcile_model.py` - Core reconciliation rule model `AccountReconcileModel` with condition fields and `AccountReconcileModelLine` for counterpart entry configuration; provides complete foundation for rule definition
- `addons/account/models/account_bank_statement_line.py` - Bank statement line model with fields for matching (`payment_ref`, `amount`, `partner_id`); `is_reconciled` computed field tracks reconciliation state
- `addons/account/views/account_reconcile_model_views.xml` - Existing form/tree views for rule management; includes sequence widget for priority ordering and conditional field visibility

### OCA Module Compatibility

| OCA Repository | Module | Compatibility Consideration |
|----------------|--------|----------------------------|
| OCA/account-reconcile | `account_reconcile_oca` | Reconciliation interface that uses reconciliation models; ensure rule configuration integrates with OCA reconciliation workflow |
| OCA/account-reconcile | `account_reconciliation_widget` | Widget may display rule suggestions; verify rule application UI patterns |

### Existing Model Field Reference

The implementing agent should analyze these existing fields in `account.reconcile.model`:

| Field | Type | Purpose |
|-------|------|---------|
| `name` | Char | Rule name for identification |
| `sequence` | Integer | Evaluation order (lower = higher priority) |
| `trigger` | Selection | 'manual' or 'auto_reconcile' mode |
| `match_journal_ids` | Many2many | Limit rule to specific bank/cash journals |
| `match_amount` | Selection | 'lower', 'greater', 'between' amount conditions |
| `match_amount_min` | Float | Minimum amount for range matching |
| `match_amount_max` | Float | Maximum amount for range matching |
| `match_label` | Selection | 'contains', 'not_contains', 'match_regex' label conditions |
| `match_label_param` | Char | Pattern string or regex for label matching |
| `match_partner_ids` | Many2many | Limit rule to specific partners |
| `line_ids` | One2many | Write-off/counterpart line configurations |

### Rule Evaluation Approach

The implementing agent should discover:
- How existing rules are evaluated against statement lines during reconciliation
- Order of evaluation based on `sequence` field
- How `trigger='auto_reconcile'` differs from `trigger='manual'` in processing flow
- Integration point between rule matching and the algorithmic matching engine (BR-002)
- How write-off lines from `line_ids` are applied to create journal entries

---

## Dependencies

### Story Dependencies

| Dependency Type | Story ID | Story Title | Relationship |
|-----------------|----------|-------------|--------------|
| Parent Feature | FEATURE-002 | Bank Reconciliation | This story is part of the Bank Reconciliation feature |
| Blocked By | BR-002 | Algorithmic Matching | Reconciliation rules extend the algorithmic matching engine with pattern configuration |
| Related | BR-001 | Statement Import | Rules apply to imported statement lines |
| Related | BR-003 | Manual Reconciliation | Rules can suggest matches for manual review |
| Related | BR-005 | Partial Reconciliation | Rules may include write-off amounts for partial matches |

### External Dependencies

| Dependency | Type | Notes |
|------------|------|-------|
| Python `re` module | Standard Library | Regex compilation and matching for `match_regex` label patterns; already used in existing `account_reconcile_model.py` |
| Regex Pattern Syntax | Standard | User-provided regex patterns must be validated before storage |

### Integration Points

| Odoo Model/Module | Integration Type | Purpose |
|-------------------|------------------|---------|
| `account.reconcile.model` | Extend/Configure | Primary model for reconciliation rules; may extend for preview functionality |
| `account.reconcile.model.line` | Configure | Counterpart entry lines for write-offs and automatic journal entries |
| `account.bank.statement.line` | Read | Read statement lines to evaluate rule matching criteria |
| `account.journal` | Read | Filter rules by applicable bank/cash journals |
| `account.account` | Read | Select target accounts for write-off entries in rule lines |
| `res.partner` | Read | Partner filtering for rule matching conditions |
| `account.tax` | Read | Tax configuration for write-off lines |

---

## Test Requirements

### Coverage Requirement

| Metric | Requirement | Notes |
|--------|-------------|-------|
| **Minimum Test Coverage** | **80%** | Mandatory for all new functionality |
| Unit Test Coverage | 80%+ | Rule matching logic, regex validation, sequence ordering |
| Integration Test Coverage | 80%+ | Rule application to statement lines, write-off entry creation |

### Unit Test Scenarios

| Acceptance Scenario | Unit Test Focus | Key Assertions |
|---------------------|-----------------|----------------|
| Scenario 1: Pattern-Based Rule | Label contains matching, amount range validation | Rule correctly matches lines with "PAYROLL" label and amount in range |
| Scenario 2: Auto-Reconcile | Trigger field behavior, automatic reconciliation | Lines matching auto-reconcile rules are reconciled without manual step |
| Scenario 3: Write-off Amount | Write-off line creation, account assignment | Correct write-off amount posted to configured expense account |
| Scenario 4: Regex Matching | Regex compilation, pattern matching | Valid regex saved; invalid regex rejected; pattern correctly matches variations |
| Scenario 5: Rule Preview | Statement line filtering, candidate identification | Preview returns correct list of matching unreconciled lines |
| Scenario 6: Sequence Priority | Sequence ordering, first-match precedence | Lower sequence rule evaluated first; only first matching rule applied |

### Integration Test Considerations

- [ ] Test integration with `account.reconcile.model` for rule creation and storage
- [ ] Test integration with `account.reconcile.model.line` for write-off configuration
- [ ] Test integration with `account.bank.statement.line` for matching evaluation
- [ ] Test rule evaluation order across multiple rules with different sequences
- [ ] Test auto-reconcile trigger creating journal entries without user intervention
- [ ] Test regex validation constraint rejects invalid patterns with appropriate error message
- [ ] Test write-off entries are correctly linked to reconciled statement lines

### Acceptance Test Mapping

| BDD Scenario | Test Method Name | Test Type |
|--------------|------------------|-----------|
| Scenario 1: Create Pattern-Based Matching Rule | `test_create_pattern_based_rule` | Acceptance |
| Scenario 2: Configure Auto-Reconcile Rule | `test_configure_auto_reconcile_rule` | Acceptance |
| Scenario 3: Define Write-off Amount in Rule | `test_writeoff_amount_configuration` | Acceptance |
| Scenario 4: Configure Regex-Based Label Matching | `test_regex_label_matching_configuration` | Acceptance |
| Scenario 5: Test Rule Against Historical Transactions | `test_rule_preview_historical_transactions` | Acceptance |
| Scenario 6: Manage Rule Priority and Sequence | `test_rule_priority_sequence_management` | Acceptance |

### Edge Case Test Scenarios

| Test Case | Description | Expected Behavior |
|-----------|-------------|-------------------|
| Invalid regex pattern | User enters `[invalid(` as regex | Validation error raised; rule not saved |
| Overlapping rules | Two rules match same statement line | Rule with lower sequence number applied |
| Zero write-off amount | Fixed write-off configured with $0 | Validation error or warning |
| Empty matching criteria | Rule saved with no conditions | Rule applies to all statement lines (intentional catch-all) |
| Multi-currency write-off | Write-off amount in different currency | Currency conversion handled appropriately |

---

## Definition of Done

### Implementation Checklist

- [ ] All 6 acceptance criteria scenarios pass
- [ ] 80% minimum test coverage achieved
- [ ] Unit tests written and passing for rule matching logic
- [ ] Integration tests written and passing for rule application workflow
- [ ] Regex validation tested with valid and invalid patterns
- [ ] Sequence ordering tested with multiple overlapping rules

### Compliance Checklist

- [ ] No Enterprise module dependencies introduced (specifically no `account_accountant` imports)
- [ ] AGPL-3.0 license compliance verified for all new code
- [ ] Code follows OCA coding standards (pre-commit hooks pass, pylint-odoo clean)
- [ ] Code reviewed and approved by peer

### Documentation Checklist

- [ ] Code documentation (docstrings, comments) complete for rule matching logic
- [ ] Rule configuration fields documented with help text
- [ ] User-facing documentation for creating and managing reconciliation rules
- [ ] Technical documentation for regex pattern syntax supported

### Quality Checklist

- [ ] No critical or high-severity bugs
- [ ] Performance acceptable (<1 second per rule evaluation)
- [ ] Security considerations addressed (regex denial-of-service protection)
- [ ] User input validation complete (regex patterns, amount values)

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2024 | Enterprise Accounting Team | Initial story creation |

---

## Notes

### Rule Configuration Best Practices

When configuring reconciliation rules, users should consider:

1. **Specificity**: More specific rules should have lower sequence numbers (higher priority) to prevent overly broad rules from matching first
2. **Testing**: Always use the preview functionality (Scenario 5) to validate rules before setting to auto-reconcile
3. **Journals**: Limit rules to specific journals when the pattern is journal-specific (e.g., payroll rules only for payroll bank account)
4. **Write-offs**: Use fixed amounts for known recurring fees; use percentages for tolerance-based matching

### Regex Pattern Examples

Common regex patterns for the implementing agent to consider supporting:

| Pattern | Purpose | Example Matches |
|---------|---------|-----------------|
| `INV[-/]?\d+` | Invoice references | "INV-12345", "INV12345", "INV/12345" |
| `PAYROLL.*\d{4}-\d{2}` | Payroll with date | "PAYROLL 2024-01", "PAYROLL RUN 2024-03" |
| `TRANSFER.*\d+` | Transfer references | "TRANSFER 123456", "BANK TRANSFER 789" |
| `FEE.*MONTHLY` | Monthly fee transactions | "SERVICE FEE MONTHLY", "FEE CHARGE MONTHLY" |

### Security Considerations

- **Regex Denial-of-Service (ReDoS)**: Implementing agents should consider timeout mechanisms or complexity limits for regex evaluation to prevent maliciously crafted patterns from causing performance issues
- **Automatic Entry Creation**: Auto-reconcile rules create journal entries automatically; proper access rights should ensure only authorized users can create/modify auto-reconcile rules

### Relationship to Algorithmic Matching (BR-002)

Reconciliation rules (this story) extend the algorithmic matching engine (BR-002) by:

1. Providing **configurable patterns** that supplement the algorithmic matching logic
2. Enabling **automatic actions** (write-offs, specific account assignments) beyond simple matching
3. Allowing **customization per company/journal** for organization-specific transaction patterns
4. Supporting **deterministic matching** for known recurring transactions vs. probabilistic algorithmic matching

---

<!--
================================================================================
INVEST VALIDATION CHECKLIST
================================================================================
Before finalizing this story, validate against INVEST principles:

✓ Independent: This story can be developed after BR-002 (Algorithmic Matching) is complete;
  does not require BR-003 or BR-005 to be implemented first.

✓ Negotiable: The story describes rule configuration outcomes without prescribing
  specific UI implementations or database schema decisions.

✓ Valuable: Clear business value - reduces manual effort, ensures consistency,
  automates repetitive patterns for the Accountant/Bookkeeper persona.

✓ Estimable: Scoped to rule configuration functionality with clear acceptance
  criteria that can be estimated by development team.

✓ Small: Six focused scenarios covering rule creation, configuration, and management;
  does not include full reconciliation interface or advanced rule features.

✓ Testable: All scenarios have clear Given/When/Then conditions that can be
  objectively verified through automated tests.
================================================================================
-->
