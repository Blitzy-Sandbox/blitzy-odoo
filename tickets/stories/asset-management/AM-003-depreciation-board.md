# AM-003: Depreciation Board

| Attribute       | Value                                                    |
|-----------------|----------------------------------------------------------|
| **Story ID**    | AM-003                                                   |
| **Title**       | Depreciation Board                                       |
| **Parent Feature** | [FEATURE-004: Asset Management](../../features/FEATURE-004-asset-management.md) |
| **Status**      | Draft                                                    |
| **Priority**    | High                                                     |
| **Estimate**    | M (Medium)                                               |

---

## User Story

**As an** Accountant

**I want** to view a complete depreciation schedule for any fixed asset showing period-by-period depreciation amounts, accumulated depreciation, and net book value throughout the asset's useful life

**So that** I can understand the future depreciation impact on financial statements, verify that depreciation calculations are correct, plan for asset replacement timing, and provide accurate information for budgeting and financial forecasting

---

## Acceptance Criteria

### Scenario 1: Display complete depreciation schedule for an asset

- **Given** I have a registered fixed asset in open status
  - And the asset has depreciation configuration completed (method, useful life, salvage value)
  - And I have access to the asset management module with Accountant permissions
- **When** I navigate to the depreciation board for the selected asset
- **Then** the system displays a complete depreciation schedule table containing:
  - Period number or date for each depreciation period
  - Depreciation amount for each period
  - Accumulated depreciation running total at the end of each period
  - Net book value (remaining book value) at the end of each period
- **And** the schedule spans the entire useful life of the asset from start to end
- **And** the final period shows accumulated depreciation equal to (Acquisition Cost - Salvage Value)
- **And** the final period shows net book value equal to the salvage value

### Scenario 2: Display accumulated depreciation running total

- **Given** I am viewing the depreciation board for an asset
  - And the asset has completed at least one depreciation period
- **When** the depreciation board is displayed
- **Then** each row shows the accumulated depreciation as of that period
  - And accumulated depreciation is calculated as the sum of all depreciation amounts from period 1 through the current period
  - And the running total increases with each successive period
  - And the accumulated depreciation values reconcile with the depreciation expense accounts in the general ledger
- **And** the accumulated depreciation column clearly distinguishes between:
  - Periods where depreciation has already been posted (actual values)
  - Periods where depreciation is projected (forecast values)

### Scenario 3: Display net book value at each period

- **Given** I am viewing the depreciation board for an asset
  - And the asset has a valid acquisition cost and depreciation configuration
- **When** the depreciation board is displayed
- **Then** each row shows the net book value (NBV) at the end of that period
  - And NBV is calculated as: Acquisition Cost - Accumulated Depreciation
  - And the initial NBV equals the acquisition cost before any depreciation
  - And NBV decreases period over period as depreciation accumulates
  - And the final NBV equals the configured salvage value (residual value)
- **And** the NBV column provides a clear visualization of the asset's value decline over its useful life

### Scenario 4: Indicate posted versus pending depreciation lines

- **Given** I am viewing the depreciation board for an asset
  - And some depreciation entries have been posted to the general ledger
  - And future depreciation entries are pending (not yet posted)
- **When** the depreciation board is displayed
- **Then** each depreciation line clearly indicates its status:
  - **Posted**: Depreciation journal entry has been created and posted to the ledger
  - **Pending**: Depreciation is scheduled but the journal entry has not been created
  - **Skipped**: Depreciation period was skipped or modified (if applicable)
- **And** posted lines display a reference or link to the corresponding journal entry
- **And** the visual distinction between posted and pending is immediately apparent (e.g., different styling, icons, or status column)
- **And** the count of posted vs pending periods is summarized in the board header or footer

### Scenario 5: Filter and sort depreciation board by date range or fiscal period

- **Given** I am viewing the depreciation board for an asset or a group of assets
  - And the asset(s) have depreciation schedules spanning multiple fiscal periods
- **When** I apply filtering and sorting options
- **Then** I can filter the depreciation board by:
  - Date range (from date to end date)
  - Fiscal year
  - Fiscal period (month, quarter)
  - Status (posted only, pending only, or all)
- **And** I can sort the depreciation lines by:
  - Period date (ascending or descending)
  - Depreciation amount
  - Status
- **And** the filtered/sorted view updates immediately
- **And** the totals displayed reflect only the filtered subset of depreciation lines
- **And** the filter selections persist during the current session

### Scenario 6: Export depreciation board to spreadsheet format

- **Given** I am viewing the depreciation board for one or more assets
  - And I need to share the depreciation schedule with external stakeholders (auditors, management, board)
- **When** I select the export option and choose the desired format (Excel/XLSX or CSV)
- **Then** the system generates a downloadable file containing:
  - Asset identification information (name, reference number, category)
  - All depreciation schedule columns (period, depreciation amount, accumulated depreciation, NBV)
  - Status indicators for each line (posted/pending)
  - Summary totals and asset configuration details
- **And** the export includes column headers matching the on-screen display
- **And** the file is generated within 5 seconds for assets with schedules up to 600 periods (50 years monthly)
- **And** numeric values are formatted appropriately for spreadsheet calculations
- **And** the exported data can be used for audit documentation and external reporting

---

## Technical Notes

### Codebase Analysis Areas

The following areas of the existing codebase should be analyzed during implementation:

| Source File | Analysis Focus |
|-------------|----------------|
| `addons/account/models/account_move.py` | Journal entry reference patterns, entry linking for posted depreciation entries |
| `addons/account/models/account_account.py` | Account type references for depreciation expense and accumulated depreciation accounts |
| `addons/account/views/account_move_views.xml` | View patterns for list/tree views, filtering, and export functionality |
| `addons/account/report/` | Report export patterns for Excel/CSV generation |

### Key Integration Points

| Integration | Description |
|-------------|-------------|
| `AM-001 (Asset Registration)` | Depreciation board displays data for registered assets; requires asset identification and acquisition details |
| `AM-002 (Depreciation Configuration)` | Depreciation schedule calculations are based on configured method, useful life, and salvage value |
| `AM-004 (Automatic Depreciation Entries)` | Posted depreciation lines link to journal entries created by automatic depreciation |
| `account.move` | Posted depreciation lines reference the corresponding journal entries for drill-down |

### Implementation Considerations

This story is primarily a **read/visualization feature** that presents data computed from:
- Asset registration records (acquisition cost, date)
- Depreciation configuration (method, useful life, salvage value)
- Posted depreciation journal entries (for status indication)

**Key Calculation Requirements:**

| Depreciation Method | Board Generation Logic |
|---------------------|----------------------|
| **Straight-Line** | Equal depreciation amount per period; NBV decreases linearly |
| **Declining Balance** | Depreciation amount decreases per period; NBV shows exponential decline pattern |
| **Units of Production** | Periods show actual units and calculated depreciation; may have varying amounts |

**Board Data Sources:**

| Data Element | Source |
|--------------|--------|
| Period dates | Computed from depreciation start date, useful life, and period frequency |
| Depreciation amount | Computed using formulas from AM-002 depreciation configuration |
| Accumulated depreciation | Running sum of depreciation amounts |
| Net book value | Acquisition cost minus accumulated depreciation |
| Posted status | Query `account.move` for existing depreciation journal entries linked to the asset |

### Performance Considerations

- Depreciation board should load efficiently for assets with long useful lives (up to 50 years = 600 monthly periods)
- Consider lazy loading or pagination for very long schedules
- Cache computed depreciation schedules where appropriate to avoid recalculation on every view
- Export functionality should handle large datasets without timeout

### View Requirements

| View Type | Purpose |
|-----------|---------|
| **Tree View (List)** | Primary tabular display of depreciation schedule with all columns |
| **Kanban View** | Optional: Visual summary cards showing asset with depreciation progress |
| **Graph View** | Optional: Chart showing NBV decline and depreciation curve over time |

### Account Type Reference

From `addons/account/models/account_account.py`, relevant account types for depreciation board context:
- `asset_fixed` - Fixed Assets (for original asset value)
- `expense_depreciation` - Depreciation (for depreciation expense entries)
- `asset_non_current` - Non-current Assets (commonly used for accumulated depreciation contra-asset)

---

## Dependencies

### Story Dependencies

| Dependency Type | Story | Description |
|-----------------|-------|-------------|
| **Depends On** | AM-001 | Asset Registration must be complete—depreciation board displays registered assets |
| **Depends On** | AM-002 | Depreciation Configuration must be complete—board uses configured parameters for schedule calculation |
| **Required By** | AM-006 | Asset Disposal uses current NBV from depreciation board for gain/loss calculation |

### Dependency Flow

```
AM-001 (Asset Registration)
    │
    ▼
AM-002 (Depreciation Configuration)
    │
    ▼
AM-003 (Depreciation Board) ◄── You are here
    │
    ├──► AM-004 (Automatic Depreciation Entries) [sibling dependency on AM-002]
    │
    └──► AM-006 (Asset Disposal) [uses NBV from board]
```

### Module Dependencies

| Module | Dependency Type | Purpose |
|--------|-----------------|---------|
| `account` | Required | Journal entry references for posted depreciation entries |
| `base` | Required | Base models for export functionality |
| Asset module (new) | Required | Asset model from AM-001 and depreciation config from AM-002 |
| `web` | Required | View rendering, filtering, sorting, and export functionality |

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
| **Unit Test Coverage** | Depreciation schedule computation, NBV calculations, status determination |
| **Integration Test Coverage** | Board display with posted entries, export functionality, filtering |

### Required Test Scenarios

| Test ID | Scenario | Expected Outcome |
|---------|----------|------------------|
| T-AM-003-01 | Display depreciation board for straight-line asset | All periods shown with equal depreciation amounts |
| T-AM-003-02 | Display depreciation board for declining balance asset | Depreciation amounts decrease each period; NBV shows exponential decline |
| T-AM-003-03 | Display depreciation board for units of production asset | Periods reflect variable depreciation based on configured units |
| T-AM-003-04 | Verify accumulated depreciation running total | Each period's accumulated depreciation equals sum of prior periods |
| T-AM-003-05 | Verify net book value calculations | NBV = Acquisition Cost - Accumulated Depreciation for each period |
| T-AM-003-06 | Verify final period values | Final accumulated depreciation = Cost - Salvage; Final NBV = Salvage |
| T-AM-003-07 | Display posted vs pending status correctly | Posted entries show journal reference; pending show appropriate status |
| T-AM-003-08 | Filter by date range | Only periods within range displayed; totals reflect filtered data |
| T-AM-003-09 | Filter by status (posted only) | Only posted depreciation lines displayed |
| T-AM-003-10 | Sort by period date descending | Most recent periods appear first |
| T-AM-003-11 | Export to Excel format | File downloads with correct data and formatting |
| T-AM-003-12 | Export to CSV format | File downloads with correct data as comma-separated values |
| T-AM-003-13 | Performance test: 50-year monthly schedule | Board loads in <5 seconds for 600-period schedule |
| T-AM-003-14 | Display board for asset with no posted entries | All lines show "pending" status; no journal references |
| T-AM-003-15 | Display board for fully depreciated asset | All lines show "posted" status; final NBV equals salvage value |

### Calculation Accuracy Verification

| Test Case | Input Values | Expected Board Output |
|-----------|--------------|----------------------|
| Straight-Line Year 1 | Cost: $10,000, Salvage: $1,000, Life: 5 years | Period 1: Dep $1,800, Accum $1,800, NBV $8,200 |
| Straight-Line Year 5 | Same asset | Period 5: Dep $1,800, Accum $9,000, NBV $1,000 |
| Declining Balance Year 1 | Cost: $10,000, Rate: 40%, Salvage: $1,000 | Period 1: Dep $4,000, Accum $4,000, NBV $6,000 |
| Declining Balance Year 2 | Same asset | Period 2: Dep $2,400, Accum $6,400, NBV $3,600 |

### Validation Criteria

| Validation Area | Criteria |
|-----------------|----------|
| Calculation Accuracy | All displayed values match manual calculations to the cent |
| Schedule Completeness | Board displays all periods from start date through end of useful life |
| Status Accuracy | Posted/pending status matches actual journal entry existence |
| Export Accuracy | Exported data exactly matches on-screen display |
| Filter Behavior | Filtered results are accurate and totals update correctly |
| Performance | Board loads within specified time limits |

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
| **Board Load Time** | < 5 seconds for single asset with up to 600 periods |
| **Batch Board Load** | < 10 seconds for 100 assets summary view |
| **Export Generation** | < 5 seconds for single asset schedule export |
| **Filter Application** | < 1 second for filter/sort operations |

---

## INVEST Checklist

| Principle | Assessment | Notes |
|-----------|------------|-------|
| **I**ndependent | ✓ Pass | Depends on AM-001 and AM-002 but can be developed after those are complete |
| **N**egotiable | ✓ Pass | Describes visualization outcomes (schedule display, filtering, export) without prescribing UI implementation |
| **V**aluable | ✓ Pass | Clear business value: enables forecasting, audit verification, and stakeholder communication |
| **E**stimable | ✓ Pass | Well-defined scope with clear calculation requirements and display expectations |
| **S**mall | ✓ Pass | Focused on read/display functionality; automatic entry generation is separate story (AM-004) |
| **T**estable | ✓ Pass | All scenarios have objective pass/fail criteria with specific calculation verification |

---

## Related Documentation

- [EPIC-001: Enterprise Accounting Capabilities](../../EPIC-001-enterprise-accounting.md)
- [FEATURE-004: Asset Management](../../features/FEATURE-004-asset-management.md)
- [AM-001: Asset Registration](./AM-001-asset-registration.md) (Prerequisite)
- [AM-002: Depreciation Configuration](./AM-002-depreciation-configuration.md) (Prerequisite)
- [AM-004: Automatic Depreciation Entries](./AM-004-automatic-depreciation-entries.md) (Related)
- [AM-006: Asset Disposal](./AM-006-asset-disposal.md) (Dependent)

---

## Appendix: Depreciation Board Visualization Reference

### Sample Depreciation Board Layout

The depreciation board provides a period-by-period view of asset value decline:

| Period | Date | Depreciation | Accumulated Depreciation | Net Book Value | Status | Journal Entry |
|--------|------|--------------|-------------------------|----------------|--------|---------------|
| 1 | Jan 2024 | $1,800.00 | $1,800.00 | $8,200.00 | Posted | JE-2024-001 |
| 2 | Feb 2024 | $1,800.00 | $3,600.00 | $6,400.00 | Posted | JE-2024-045 |
| 3 | Mar 2024 | $1,800.00 | $5,400.00 | $4,600.00 | Pending | — |
| 4 | Apr 2024 | $1,800.00 | $7,200.00 | $2,800.00 | Pending | — |
| 5 | May 2024 | $1,800.00 | $9,000.00 | $1,000.00 | Pending | — |

**Legend:**
- **Depreciation**: Amount expensed in the period
- **Accumulated Depreciation**: Total depreciation recognized to date
- **Net Book Value**: Remaining book value of the asset (Cost - Accumulated Depreciation)
- **Status**: Posted (journal entry exists) or Pending (scheduled but not yet posted)
- **Journal Entry**: Reference to the posted depreciation journal entry for audit trail

### Use Cases for Depreciation Board

| Use Case | Description |
|----------|-------------|
| **Financial Planning** | Forecast depreciation expense for budgeting purposes |
| **Asset Replacement** | Identify when assets will be fully depreciated to plan replacements |
| **Audit Support** | Provide detailed depreciation schedule documentation for external auditors |
| **Balance Sheet Verification** | Reconcile net book value with fixed asset balances on financial statements |
| **Tax Reporting** | Support tax return preparation with depreciation documentation |
