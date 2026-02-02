# AM-001: Asset Registration

| Attribute       | Value                                                    |
|-----------------|----------------------------------------------------------|
| **Story ID**    | AM-001                                                   |
| **Title**       | Asset Registration                                       |
| **Parent Feature** | [FEATURE-004: Asset Management](../../features/FEATURE-004-asset-management.md) |
| **Status**      | Draft                                                    |
| **Priority**    | High                                                     |
| **Estimate**    | M (Medium)                                               |

---

## User Story

**As an** Accountant

**I want** to register and track fixed assets with complete acquisition information including asset name, acquisition date, acquisition cost, useful life, and proper account assignments

**So that** I can maintain accurate asset records for financial reporting, ensure proper depreciation tracking throughout the asset lifecycle, and comply with GAAP/IFRS fixed asset accounting requirements

---

## Acceptance Criteria

### Scenario 1: Create new asset record with required fields

- **Given** I have access to the asset management module
  - And I have the Accountant role with asset creation permissions
  - And valid chart of accounts exists with asset-type accounts configured
- **When** I create a new fixed asset record with the following required information:
  - Asset name/description
  - Acquisition date
  - Acquisition cost (original value)
  - Asset account (account type: `asset_fixed`)
  - Depreciation expense account (account type: `expense_depreciation`)
  - Accumulated depreciation account (contra-asset account)
- **Then** the asset record is created in draft status
  - And all required fields are validated as complete
  - And the asset is available for further configuration before confirmation

### Scenario 2: Automatic creation of acquisition journal entry upon confirmation

- **Given** a draft asset record exists with all required fields completed
  - And the asset has a valid acquisition cost greater than zero
  - And all linked accounts are active and valid
- **When** I confirm the asset registration
- **Then** an acquisition journal entry is automatically created
  - And the journal entry debits the asset account for the acquisition cost
  - And the journal entry credits the appropriate offset account (cash, payables, or clearing account)
  - And the journal entry is dated on the asset acquisition date
  - And the asset status changes from "draft" to "open" (or confirmed state)

### Scenario 3: Assignment of asset to category with inherited default settings

- **Given** asset categories are configured with default settings including:
  - Default depreciation method
  - Default useful life
  - Default asset account
  - Default depreciation expense account
  - Default accumulated depreciation account
- **When** I assign an asset to a category during registration
- **Then** the asset inherits all default settings from the category
  - And inherited values can be overridden on the individual asset if needed
  - And the category assignment is recorded for reporting and filtering purposes

### Scenario 4: Unique asset identification/reference number generation

- **Given** I am creating a new asset record
  - And the company has asset numbering sequence configured
- **When** the asset is saved or confirmed
- **Then** a unique asset reference number is automatically generated
  - And the reference follows the configured sequence pattern
  - And the reference number is displayed on all asset-related documents and reports
  - And duplicate reference numbers are prevented by the system

### Scenario 5: Linking asset to vendor and purchase invoice

- **Given** a vendor bill (purchase invoice) exists in the system for the asset acquisition
  - And the invoice contains the correct acquisition cost
- **When** I create or edit an asset record
- **Then** I can link the asset to the originating vendor
  - And I can link the asset to the source purchase invoice
  - And the linked invoice amount is validated against the asset acquisition cost
  - And the vendor and invoice information is available for audit trail purposes

### Scenario 6: Validation of required accounts before asset confirmation

- **Given** I am attempting to confirm an asset registration
- **When** I submit the asset for confirmation
- **Then** the system validates that:
  - The asset account is of type `asset_fixed` or equivalent fixed asset type
  - The depreciation expense account is of type `expense_depreciation` or expense type
  - The accumulated depreciation account is properly configured as a contra-asset
  - All three accounts belong to the same company as the asset
  - All linked accounts are active (not archived)
- **And** if validation fails, a clear error message indicates which requirements are not met
- **And** the asset remains in draft status until all validations pass

---

## Technical Notes

### Codebase Analysis Areas

The following areas of the existing codebase should be analyzed during implementation:

| Source File | Analysis Focus |
|-------------|----------------|
| `addons/account/models/account_move.py` | Journal entry creation patterns, state management, posting workflow, line item structure |
| `addons/account/models/account_move_line.py` | Debit/credit line creation, account assignment, partner linking |
| `addons/account/models/account_account.py` | Account type definitions (`asset_fixed`, `expense_depreciation`), account validation patterns |
| `addons/account/__manifest__.py` | Module structure, dependency declaration patterns |

### Key Integration Points

| Integration | Description |
|-------------|-------------|
| `account.move` | Asset registration should create acquisition journal entries using the standard journal entry model |
| `account.account` | Account type filtering ensures only appropriate accounts are selectable for asset/depreciation/accumulated depreciation |
| `ir.sequence` | Asset reference numbers should use Odoo's sequence mechanism for unique identification |
| `res.partner` | Vendor linking uses standard partner model |
| `account.move` (vendor bill) | Purchase invoice linking references existing vendor bill records |

### Model Considerations

- Asset model should follow Odoo model conventions with proper `_name`, `_description`, and `_inherit` patterns
- State machine for asset lifecycle: `draft` → `open` → `close` (or similar)
- Computed fields for current book value (acquisition cost - accumulated depreciation)
- Proper use of `@api.constrains` for validation logic
- Consideration of multi-company support via `company_id` field

### Account Type Reference

From `addons/account/models/account_account.py`, relevant account types:
- `asset_fixed` - Fixed Assets (for asset accounts)
- `expense_depreciation` - Depreciation (for depreciation expense accounts)
- Accumulated depreciation accounts typically use `asset_non_current` or a custom contra-asset type

---

## Dependencies

### Story Dependencies

| Dependency Type | Description |
|-----------------|-------------|
| **Foundation Story** | This is the foundational story for the Asset Management feature. No prior stories required. |
| **Dependent Stories** | All other AM stories depend on AM-001: |
| | - AM-002 (Depreciation Configuration) requires registered assets |
| | - AM-003 (Depreciation Board) displays data for registered assets |
| | - AM-004 (Automatic Depreciation Entries) processes registered assets |
| | - AM-005 (Asset Modification) modifies registered assets |
| | - AM-006 (Asset Disposal) disposes registered assets |

### Module Dependencies

| Module | Dependency Type | Purpose |
|--------|-----------------|---------|
| `account` | Required | Core accounting models (`account.move`, `account.account`, `account.journal`) |
| `base` | Required | Base models (`res.partner`, `res.company`, `ir.sequence`) |
| `mail` | Optional | Chatter/activity tracking on asset records |

### External Dependencies

| Constraint | Requirement |
|------------|-------------|
| **No Enterprise Dependencies** | Implementation must NOT import or depend on Odoo Enterprise `account_asset` module |
| **OCA Compatibility** | Should be compatible with OCA `account-financial-tools` patterns where applicable |

---

## Test Requirements

### Coverage Target

| Metric | Target |
|--------|--------|
| **Minimum Test Coverage** | 80% |
| **Unit Test Coverage** | All model methods, computed fields, and constraints |
| **Integration Test Coverage** | Asset creation with journal entry generation workflow |

### Required Test Scenarios

| Test ID | Scenario | Expected Outcome |
|---------|----------|------------------|
| T-AM-001-01 | Create asset with all required fields | Asset created in draft status with all fields populated |
| T-AM-001-02 | Confirm asset and verify journal entry | Acquisition journal entry created with correct debit/credit |
| T-AM-001-03 | Create asset from category defaults | Asset inherits category settings correctly |
| T-AM-001-04 | Verify unique reference generation | Each asset gets unique, sequential reference |
| T-AM-001-05 | Link asset to vendor bill | Asset correctly linked to purchase invoice |
| T-AM-001-06 | Attempt confirmation with invalid accounts | Validation error raised, asset remains draft |
| T-AM-001-07 | Attempt confirmation with missing required fields | Validation error raised with field-specific message |
| T-AM-001-08 | Multi-company asset creation | Asset and journal entry respect company boundaries |

### Validation Criteria

| Validation Area | Criteria |
|-----------------|----------|
| Journal Entry Accuracy | Debit amount equals acquisition cost; Credit amount equals acquisition cost; Entry is balanced |
| Account Type Compliance | Only `asset_fixed` type accounts allowed for asset account field |
| Reference Uniqueness | No duplicate asset references allowed within company |
| Date Validation | Acquisition date not in locked fiscal period |

---

## Constraints (Inherited from Epic)

### License Requirements

| Constraint | Requirement |
|------------|-------------|
| **License** | AGPL-3.0 compatible |
| **Compliance** | Module must be distributable under AGPL-3.0 license |

### Coding Standards

| Standard | Requirement |
|----------|-------------|
| **OCA Guidelines** | Follow OCA coding standards and module structure |
| **Odoo Guidelines** | Adhere to Odoo development best practices |
| **Pre-commit Hooks** | Code must pass pre-commit and pylint-odoo checks |

### Performance Requirements

| Metric | Target |
|--------|--------|
| **Asset Registration** | < 2 seconds per asset |
| **Journal Entry Creation** | < 1 second for acquisition entry |
| **Batch Creation** | Support batch import of 100+ assets |

---

## INVEST Checklist

| Principle | Assessment | Notes |
|-----------|------------|-------|
| **I**ndependent | ✓ Pass | Foundational story with no upstream dependencies |
| **N**egotiable | ✓ Pass | Describes outcomes (asset tracking, journal entry creation) not implementation |
| **V**aluable | ✓ Pass | Clear business value: accurate financial reporting and compliance |
| **E**stimable | ✓ Pass | Well-defined scope with measurable acceptance criteria |
| **S**mall | ✓ Pass | Focused on registration workflow; depreciation and disposal are separate stories |
| **T**estable | ✓ Pass | All scenarios have objective pass/fail criteria |

---

## Related Documentation

- [EPIC-001: Enterprise Accounting Capabilities](../../EPIC-001-enterprise-accounting.md)
- [FEATURE-004: Asset Management](../../features/FEATURE-004-asset-management.md)
- [AM-002: Depreciation Configuration](./AM-002-depreciation-configuration.md)
- [Story Template](../../templates/story-template.md)
