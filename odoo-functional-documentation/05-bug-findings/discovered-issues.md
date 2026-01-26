# Discovered Issues and Bug Findings

## Document Information

| Attribute | Value |
|-----------|-------|
| **Document Type** | Bug Findings Registry |
| **Odoo Version** | 19.0 Community Edition |
| **Documentation Scope** | Functional Documentation Analysis |
| **Last Updated** | January 2026 |
| **Document Status** | Active |

---

## 1. Purpose and Scope

### About This Document

This document serves as the **central repository for all bugs, defects, inconsistencies, and unexpected behaviors** discovered during the Odoo 19.0 functional documentation analysis process.

**Important Context:**

This documentation project is a **READ-ONLY task**. All findings documented here are:

- **Observed** during workflow analysis and screenshot capture
- **Recorded** using the standardized template below
- **NOT FIXED** as part of this documentation effort

The purpose of this bug registry is to:

1. Provide transparency about known issues that may affect documented workflows
2. Help customer support teams understand why actual system behavior might differ from expectations
3. Serve as a reference for future development or investigation
4. Document evidence-based findings without modifying any source code

### Relationship to Workflow Documentation

When documenting user workflows (in the [02-user-flows](../02-user-flows/) directory), any discovered bugs are:

1. **Documented here** using the standardized template
2. **Referenced in the affected flow document** with a note explaining the impact
3. **Worked around** in the documentation by describing actual (potentially buggy) system behavior

This approach ensures that users receive accurate documentation of how the system actually behaves, while maintaining a clear record of any issues discovered.

---

## 2. Bug Categories

The following categories of issues are monitored and documented during the Odoo 19.0 functional documentation process:

### 2.1 UI/UX Inconsistencies

Issues where the user interface does not match documented or expected behavior.

**Examples include:**
- Buttons that are labeled incorrectly
- Menu items that lead to unexpected destinations
- Form fields that don't save or display correctly
- Visual elements that appear differently than described
- Missing or incorrectly placed UI elements

### 2.2 Workflow State Machine Violations

Issues where documents transition between states unexpectedly or fail to transition when they should.

**Examples include:**
- Sales orders that cannot be confirmed due to missing validations
- Inventory pickings stuck in intermediate states
- Invoices that don't post correctly
- State transitions that skip expected intermediate steps
- Rollback operations that don't restore previous state correctly

### 2.3 Calculation Errors in Business Logic

Issues where computed values, totals, or derived data are incorrect.

**Examples include:**
- Tax calculations that produce incorrect amounts
- Inventory quantity calculations that don't balance
- Pricing calculations with discount errors
- Currency conversion inaccuracies
- Date/time calculations that produce unexpected results

### 2.4 Error Message Inaccuracies

Issues where error messages are misleading, missing, or technically incorrect.

**Examples include:**
- Error messages that reference fields not visible to the user
- Missing validation messages for required fields
- Unhelpful generic error messages
- Error messages displayed in technical (developer) language
- Incorrect guidance in error recovery suggestions

### 2.5 Screenshot Evidence Contradictions

Issues where captured screenshots reveal behavior different from documented workflows.

**Examples include:**
- Screenshots showing different default values than documented
- UI states that don't match step-by-step descriptions
- Workflow sequences captured differently than expected
- Visual evidence of missing or extra fields

### 2.6 Access Control Inconsistencies

Issues where user permissions don't behave as documented or expected.

**Examples include:**
- Actions available to users who shouldn't have access
- Actions blocked for users who should have access
- Inconsistent permission behavior across similar operations
- Security groups that don't apply as configured
- Multi-company isolation failures

---

## 3. Severity Classification Guide

Each discovered issue is assigned a severity level based on its impact:

### Critical Severity

| Aspect | Definition |
|--------|------------|
| **User Impact** | Prevents users from completing essential business operations |
| **Data Impact** | May cause data loss, corruption, or financial discrepancies |
| **Scope** | Affects core workflows used daily by most users |
| **Workaround** | No reasonable workaround available |
| **Examples** | Cannot confirm sales orders; Invoice totals calculate incorrectly; Data deleted unexpectedly |

### High Severity

| Aspect | Definition |
|--------|------------|
| **User Impact** | Significantly impairs workflow efficiency or accuracy |
| **Data Impact** | May cause incorrect reports or require manual corrections |
| **Scope** | Affects important but not critical business functions |
| **Workaround** | Workaround exists but is inconvenient or time-consuming |
| **Examples** | Stock movements not reflected accurately; Payment matching fails; Approval workflows skip steps |

### Medium Severity

| Aspect | Definition |
|--------|------------|
| **User Impact** | Causes inconvenience but doesn't block operations |
| **Data Impact** | Cosmetic or minor data display issues |
| **Scope** | Affects specific features or edge cases |
| **Workaround** | Simple workaround available |
| **Examples** | Incorrect field labels; Minor calculation rounding; Sorting doesn't work as expected |

### Low Severity

| Aspect | Definition |
|--------|------------|
| **User Impact** | Minimal user-facing impact |
| **Data Impact** | No data impact |
| **Scope** | Rare edge cases or cosmetic issues |
| **Workaround** | Issue may not require workaround |
| **Examples** | Tooltip text typos; Color scheme inconsistencies; Non-critical UI alignment issues |

---

## 4. Bug Documentation Template

When documenting a discovered issue, use the following standardized template:

---

### Template

```markdown
## BUG-[Sequential Number]: [Brief Title]

### Discovery Context

| Aspect | Details |
|--------|---------|
| **Discovered During** | [Which documentation step revealed this issue] |
| **Affected Component** | [File path or module name] |
| **Severity Assessment** | [Critical / High / Medium / Low] |

### Issue Description

[Clear description of the unexpected behavior or defect]

### Expected Behavior

[What should happen based on business logic or documentation]

### Actual Behavior

[What actually occurs, with evidence if available]

### Reproduction Steps

1. [Step 1]
2. [Step 2]
3. [Continue as needed]

### Evidence

| Type | Reference |
|------|-----------|
| **Screenshot reference** | [filename if applicable] |
| **Log output** | [relevant log snippets] |
| **Test result** | [pass/fail status if from test execution] |

### Recommended Fix

[Technical recommendation for resolution]

### Impact Assessment

| Impact Area | Description |
|-------------|-------------|
| **User Impact** | [How this affects end users] |
| **Workflow Impact** | [Which flows are affected] |
| **Documentation Impact** | [How this affects accuracy of generated documentation] |
```

---

## 5. Documentation Guidelines

### When to Document a Bug

Document an issue when you observe:

1. **Deviation from expected behavior**: The system does something different from what business logic would suggest
2. **Inconsistency**: Behavior differs between similar operations or contexts
3. **User confusion**: Behavior likely to confuse end users or support staff
4. **Data integrity risk**: Any risk of incorrect, lost, or corrupted data

### When NOT to Document

Do not document:

1. **Enterprise-only features**: Features requiring Enterprise Edition are noted separately, not as bugs
2. **Intentional design decisions**: Behavior that may seem unusual but is intentional
3. **Configuration-dependent behavior**: Issues that depend on specific settings that aren't the default
4. **Known limitations**: Documented limitations in Odoo's official documentation

### Documentation Process

1. **Discover**: Encounter unexpected behavior during workflow documentation
2. **Verify**: Confirm the behavior is reproducible
3. **Document**: Use the template above to record all details
4. **Reference**: Add a note in the affected workflow documentation
5. **Continue**: Complete the workflow documentation using actual system behavior

### Referencing Bugs in Workflow Documentation

When a documented workflow is affected by a known bug, add a note like:

```markdown
> **Note:** This step may behave differently than expected due to a known issue.
> See [BUG-001: Brief Title](../05-bug-findings/discovered-issues.md#bug-001-brief-title) 
> for details. The documentation below describes the actual current behavior.
```

---

## 6. Discovered Issues Index

This section provides a quick reference to all documented issues.

### Summary Table

| Bug ID | Title | Severity | Affected Module | Status |
|--------|-------|----------|-----------------|--------|
| *No bugs discovered yet* | — | — | — | — |

> **Note:** This table will be populated as issues are discovered during the documentation process.

---

## 7. Documented Bugs

*This section will contain individual bug documentation using the template above.*

---

### No Bugs Discovered

As of the current documentation state, **no bugs have been discovered** that require documentation.

This may indicate:

1. The workflows documented so far are functioning as expected
2. Bug discovery is ongoing as documentation continues
3. Some issues may be edge cases not yet encountered

This document will be updated as the documentation process continues and any issues are discovered.

---

## 8. Related Documentation

For context on the workflows being documented, refer to:

| Document | Description |
|----------|-------------|
| [Documentation Index](../README.md) | Main entry point and table of contents |
| [Sales Quote to Order](../02-user-flows/01-sales-quote-to-order/flow-document.md) | Sales workflow documentation |
| [CRM Lead to Opportunity](../02-user-flows/02-crm-lead-to-opportunity/flow-document.md) | CRM workflow documentation |

### Source Code References

The following source files were analyzed as part of the documentation process:

| Module | Source File | Business Function |
|--------|-------------|-------------------|
| Sales | `addons/sale/models/sale_order.py` | Sales order management and state transitions |
| CRM | `addons/crm/models/crm_lead.py` | Lead and opportunity management |
| Inventory | `addons/stock/models/stock_picking.py` | Stock transfer operations |
| Accounting | `addons/account/models/account_move.py` | Invoice and payment processing |
| Purchase | `addons/purchase/models/purchase_order.py` | Purchase order management |

---

## 9. Change Log

| Date | Change Description | Author |
|------|-------------------|--------|
| January 2026 | Initial document creation with template and guidelines | Blitzy Documentation |

---

*This document is part of the Odoo 19.0 Functional Documentation project. For questions about documented bugs or to report additional issues discovered during support activities, please follow your organization's issue tracking procedures.*
