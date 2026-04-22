# AM-002: Depreciation Configuration

| Attribute       | Value                                                    |
|-----------------|----------------------------------------------------------|
| **Story ID**    | AM-002                                                   |
| **Title**       | Depreciation Configuration                               |
| **Parent Feature** | [FEATURE-004: Asset Management](../../features/FEATURE-004-asset-management.md) |
| **Status**      | Draft                                                    |
| **Priority**    | High                                                     |
| **Estimate**    | M (Medium)                                               |

---

## User Story

**As an** Accountant

**I want** to configure different depreciation methods and parameters for fixed assets, including straight-line, declining balance, and units of production methods with their respective calculation settings

**So that** I can comply with various accounting standards (GAAP/IFRS) and tax requirements, ensure accurate depreciation calculations over asset useful lives, and maintain flexibility to apply the most appropriate depreciation method for each asset category

---

## Acceptance Criteria

### Scenario 1: Configure straight-line depreciation method with useful life in years

- **Given** I have a registered asset in open status
  - And I have access to the depreciation configuration for that asset
  - And valid depreciation expense and accumulated depreciation accounts are configured
- **When** I configure the depreciation method as "Straight-Line"
  - And I specify the useful life as a number of years (e.g., 5 years)
  - And I optionally specify a salvage value (residual value at end of useful life)
- **Then** the system calculates the annual depreciation amount as (Acquisition Cost - Salvage Value) / Useful Life Years
  - And the system stores the depreciation method, useful life, and salvage value on the asset record
  - And the configuration is validated as complete and consistent
  - And the asset is ready for depreciation board generation (AM-003)

### Scenario 2: Configure straight-line depreciation method with useful life in months

- **Given** I have a registered asset requiring monthly depreciation precision
  - And the asset has a valid acquisition cost and date
- **When** I configure the depreciation method as "Straight-Line"
  - And I specify the useful life in months instead of years (e.g., 36 months)
  - And I specify a salvage value of zero or greater
- **Then** the system calculates the monthly depreciation amount as (Acquisition Cost - Salvage Value) / Useful Life Months
  - And the useful life period is stored in months for precise scheduling
  - And the total depreciation schedule spans exactly the specified number of months
  - And partial-month prorating rules are applied based on the start date configuration

### Scenario 3: Configure declining balance depreciation method

- **Given** I have a registered asset that benefits from accelerated depreciation
  - And I have access to the depreciation configuration
- **When** I configure the depreciation method as "Declining Balance"
  - And I specify the depreciation rate percentage (e.g., 40% per year)
  - And I specify the useful life period (years or months)
  - And I optionally enable "Switch to straight-line at optimal point" option
- **Then** the system stores the declining balance rate and useful life
  - And if switch-to-straight-line is enabled, the system calculates the optimal crossover point
  - And the crossover point is where straight-line on remaining book value exceeds declining balance depreciation
  - And the asset depreciation schedule reflects the declining balance pattern with optional switch
  - And the total depreciation over the useful life equals (Acquisition Cost - Salvage Value)

### Scenario 4: Configure units of production depreciation method

- **Given** I have a registered asset where depreciation correlates to usage rather than time
  - And examples include manufacturing equipment, vehicles, or production machinery
- **When** I configure the depreciation method as "Units of Production"
  - And I specify the total expected units over the asset's useful life (e.g., 100,000 units)
  - And I specify the salvage value
- **Then** the system calculates the per-unit depreciation rate as (Acquisition Cost - Salvage Value) / Total Expected Units
  - And the configuration stores the total expected units
  - And the system is prepared to accept periodic actual units for depreciation calculation
  - And each period's depreciation is calculated as Actual Units × Per-Unit Rate
  - And the asset tracks cumulative units produced against total expected units

### Scenario 5: Configure depreciation start date options

- **Given** I have a registered asset with a configured depreciation method
  - And the asset has a valid acquisition date
- **When** I configure the depreciation start date
- **Then** I can select from the following start date options:
  - **Acquisition Date**: Depreciation begins on the exact acquisition date with prorating
  - **First Day of Next Month**: Depreciation begins on the first day of the month following acquisition
  - **First Day of Current Month**: Depreciation begins on the first day of the acquisition month
  - **Manual Date**: I can specify a custom start date on or after acquisition date
- **And** the selected start date determines the first depreciation period
- **And** prorating rules are applied automatically based on the start date option
- **And** the depreciation schedule aligns with the company's fiscal calendar

### Scenario 6: Configure asset category templates with default depreciation settings

- **Given** I am an Accountant managing multiple assets of similar types
  - And I want to standardize depreciation settings across asset categories
- **When** I create or edit an asset category (e.g., "Office Equipment", "Vehicles", "Buildings")
  - And I configure the following default depreciation settings on the category:
  - Default depreciation method (Straight-Line, Declining Balance, or Units of Production)
  - Default useful life (years or months)
  - Default salvage value or salvage percentage
  - Default depreciation start date option
  - Default depreciation rate (for declining balance method)
- **Then** new assets assigned to this category automatically inherit these default settings
  - And inherited settings can be overridden on individual assets if needed
  - And category changes do not retroactively affect assets already configured
  - And the system maintains traceability of which settings came from the category template

### Scenario 7: Validation of depreciation configuration completeness and consistency

- **Given** I am configuring depreciation settings for an asset
- **When** I attempt to save or confirm the depreciation configuration
- **Then** the system validates the following requirements:
  - Depreciation method is selected
  - For straight-line and declining balance: useful life is greater than zero
  - For declining balance: depreciation rate is between 0% and 100%
  - For units of production: total expected units is greater than zero
  - Salvage value is not negative
  - Salvage value does not exceed acquisition cost
  - Depreciation start date is on or after acquisition date
  - Depreciation expense account is of type `expense_depreciation`
  - Accumulated depreciation account is properly configured
- **And** if any validation fails, a clear error message indicates which requirement is not met
- **And** the configuration is not saved until all validations pass

---

## Technical Notes

### Codebase Analysis Areas

The following areas of the existing codebase should be analyzed during implementation:

| Source File | Analysis Focus |
|-------------|----------------|
| `addons/account/models/account_move.py` | Journal entry creation patterns for depreciation entries, amount calculations |
| `addons/account/models/account_account.py` | Account type definitions (`expense_depreciation`, `asset_fixed`), account validation patterns |
| `addons/account/wizard/account_automatic_entry_wizard.py` | Patterns for automatic entry generation that can inform depreciation entry automation |
| `addons/account/__manifest__.py` | Module structure and dependency patterns |

### Key Integration Points

| Integration | Description |
|-------------|-------------|
| `AM-001 (Asset Registration)` | Depreciation configuration extends registered asset records |
| `AM-003 (Depreciation Board)` | Depreciation calculations feed the schedule display in the depreciation board |
| `AM-004 (Automatic Depreciation Entries)` | Configuration parameters drive automatic journal entry generation |
| `account.account` | Account type filtering ensures correct depreciation and accumulated depreciation accounts |
| Asset Categories | Category model stores default depreciation templates for inheritance |

### Depreciation Calculation Formulas

The implementation should support the following standard formulas:

| Method | Formula | Notes |
|--------|---------|-------|
| **Straight-Line** | (Cost - Salvage) / Useful Life | Constant depreciation per period |
| **Declining Balance** | Book Value × Rate | Applied to remaining book value each period |
| **Double Declining Balance** | Book Value × (2 / Useful Life) | Special case with rate = 200% / Useful Life |
| **Units of Production** | (Cost - Salvage) / Total Units × Actual Units | Variable based on actual usage |

### Declining Balance Switch-to-Straight-Line Logic

When "Switch to straight-line at optimal point" is enabled:
1. Calculate declining balance depreciation for current period
2. Calculate straight-line depreciation on remaining book value over remaining useful life
3. If straight-line > declining balance, switch methods for remainder of asset life
4. This ensures the asset is fully depreciated by end of useful life

### Model Considerations

- Depreciation configuration should be stored on the asset model with appropriate fields
- Selection field for depreciation method: `straight_line`, `declining_balance`, `units_of_production`
- Flexible useful life storage: support both months and years with conversion
- Computed fields for depreciation amounts and schedules
- Proper use of `@api.constrains` for configuration validation
- Asset category model extension for default settings inheritance

### Account Type Reference

From `addons/account/models/account_account.py`, relevant account types:
- `asset_fixed` - Fixed Assets (for asset accounts)
- `expense_depreciation` - Depreciation (for depreciation expense accounts)
- `asset_non_current` - Non-current Assets (can be used for accumulated depreciation)

---

## Dependencies

### Story Dependencies

| Dependency Type | Story | Description |
|-----------------|-------|-------------|
| **Depends On** | AM-001 | Asset Registration must be complete before depreciation can be configured |
| **Required By** | AM-003 | Depreciation Board requires configured depreciation parameters to display schedule |
| **Required By** | AM-004 | Automatic Depreciation Entries requires configuration to generate correct amounts |

### Dependency Flow

```
AM-001 (Asset Registration)
    │
    ▼
AM-002 (Depreciation Configuration) ◄── You are here
    │
    ├──► AM-003 (Depreciation Board)
    │
    └──► AM-004 (Automatic Depreciation Entries)
```

### Module Dependencies

| Module | Dependency Type | Purpose |
|--------|-----------------|---------|
| `account` | Required | Account type definitions, journal entry patterns |
| `base` | Required | Base models (`res.company` for fiscal settings) |
| Asset module (new) | Required | Asset model from AM-001 implementation |

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
| **Unit Test Coverage** | All depreciation calculation methods, validation constraints, field computations |
| **Integration Test Coverage** | Category inheritance, configuration save/confirm workflows |

### Required Test Scenarios

| Test ID | Scenario | Expected Outcome |
|---------|----------|------------------|
| T-AM-002-01 | Configure straight-line depreciation in years | Correct annual depreciation amount calculated |
| T-AM-002-02 | Configure straight-line depreciation in months | Correct monthly depreciation amount calculated |
| T-AM-002-03 | Configure declining balance depreciation | Correct declining balance schedule generated |
| T-AM-002-04 | Configure declining balance with switch to straight-line | Crossover point correctly identified and applied |
| T-AM-002-05 | Configure units of production depreciation | Per-unit rate calculated correctly |
| T-AM-002-06 | Test all depreciation start date options | Start date correctly determines first period |
| T-AM-002-07 | Create asset from category with default depreciation | Settings inherited correctly from category |
| T-AM-002-08 | Override category defaults on individual asset | Override values used instead of category defaults |
| T-AM-002-09 | Attempt to save invalid configuration (missing method) | Validation error raised |
| T-AM-002-10 | Attempt to save invalid configuration (salvage > cost) | Validation error raised with clear message |
| T-AM-002-11 | Attempt to save invalid configuration (negative useful life) | Validation error raised |
| T-AM-002-12 | Verify account type restrictions | Only appropriate account types selectable |

### Depreciation Calculation Verification

| Method | Test Case | Input Values | Expected Depreciation |
|--------|-----------|--------------|----------------------|
| Straight-Line | Annual | Cost: $10,000, Salvage: $1,000, Life: 5 years | $1,800/year |
| Straight-Line | Monthly | Cost: $10,000, Salvage: $1,000, Life: 36 months | $250/month |
| Declining Balance | Year 1 | Cost: $10,000, Rate: 40% | $4,000 (Year 1) |
| Declining Balance | Year 2 | Book Value: $6,000, Rate: 40% | $2,400 (Year 2) |
| Units of Production | Per Unit | Cost: $10,000, Salvage: $1,000, Units: 100,000 | $0.09/unit |

### Validation Criteria

| Validation Area | Criteria |
|-----------------|----------|
| Calculation Accuracy | Depreciation amounts match manual calculations to the cent |
| Method Support | All three depreciation methods fully functional |
| Category Inheritance | Default settings properly inherited and overridable |
| Start Date Options | All four start date options produce correct schedules |
| Validation Completeness | All configuration errors caught with clear messages |

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
| **Depreciation Calculation** | < 1 second per asset configuration |
| **Schedule Generation** | < 2 seconds for full useful life schedule |
| **Category Inheritance** | < 0.5 seconds for default value population |

---

## INVEST Checklist

| Principle | Assessment | Notes |
|-----------|------------|-------|
| **I**ndependent | ✓ Pass | Depends only on AM-001 (asset registration foundation) |
| **N**egotiable | ✓ Pass | Describes depreciation configuration outcomes, not implementation details |
| **V**aluable | ✓ Pass | Enables compliance with GAAP/IFRS through flexible depreciation methods |
| **E**stimable | ✓ Pass | Well-defined scope with clear calculation formulas and validation rules |
| **S**mall | ✓ Pass | Focused on configuration; board display and entry generation are separate stories |
| **T**estable | ✓ Pass | All scenarios have objective pass/fail criteria with calculation verification |

---

## Related Documentation

- [EPIC-001: Enterprise Accounting Capabilities](../../EPIC-001-enterprise-accounting.md)
- [FEATURE-004: Asset Management](../../features/FEATURE-004-asset-management.md)
- [AM-001: Asset Registration](./AM-001-asset-registration.md) (Prerequisite)
- [AM-003: Depreciation Board](./AM-003-depreciation-board.md) (Dependent)
- [AM-004: Automatic Depreciation Entries](./AM-004-automatic-depreciation-entries.md) (Dependent)

---

## Appendix: Depreciation Method Reference

### Straight-Line Depreciation

The most common depreciation method, spreading the cost evenly over the asset's useful life.

**Formula:**
```
Annual Depreciation = (Acquisition Cost - Salvage Value) / Useful Life in Years
Monthly Depreciation = (Acquisition Cost - Salvage Value) / Useful Life in Months
```

**Use Cases:** Office equipment, furniture, buildings, general-purpose assets

### Declining Balance Depreciation

An accelerated depreciation method that front-loads depreciation expense, commonly used for assets that lose value quickly in early years.

**Formula:**
```
Period Depreciation = Current Book Value × Depreciation Rate
Book Value = Previous Book Value - Previous Period Depreciation
```

**Common Rates:**
- 150% Declining Balance: Rate = 1.5 / Useful Life
- 200% Declining Balance (Double Declining): Rate = 2 / Useful Life
- Custom Rate: User-specified percentage

**Use Cases:** Technology equipment, vehicles, machinery with rapid obsolescence

### Units of Production Depreciation

Depreciation based on actual usage rather than time, ideal for assets whose wear correlates directly with output.

**Formula:**
```
Per-Unit Rate = (Acquisition Cost - Salvage Value) / Total Expected Units
Period Depreciation = Actual Units Produced × Per-Unit Rate
```

**Use Cases:** Manufacturing equipment, vehicles (based on mileage), production machinery
