# DR-002 Automatic Period Allocation

| Attribute       | Value                                                    |
|-----------------|----------------------------------------------------------|
| **Story ID**    | DR-002                                                   |
| **Title**       | Automatic Period Allocation                              |
| **Parent Feature** | [FEATURE-005: Deferred Revenue/Expenses](../../features/FEATURE-005-deferred-revenue.md) |
| **Status**      | Draft                                                    |
| **Priority**    | High                                                     |
| **Estimate**    | M (Medium)                                               |

---

## User Story

**As an** Accountant / Bookkeeper

**I want** deferred revenue and expense amounts to be automatically allocated across accounting periods

**So that** I can ensure accurate revenue/expense recognition without manual calculations each period, reducing errors and ensuring consistent application of ASC 606/IFRS 15 recognition principles

---

## Acceptance Criteria

### Scenario 1: Straight-line Allocation Across Equal Periods

- **Given** I have a deferral schedule for $12,000 over 12 months
  - And the recognition method is straight-line
- **When** the allocation schedule is generated
- **Then** each month should have a recognition amount of $1,000
  - And the sum of all allocations should equal the total deferred amount
  - And each period should be clearly identified by fiscal period

### Scenario 2: Date-based Allocation with Unequal Periods

- **Given** I have a deferral schedule starting mid-month
  - And the recognition method is based on calendar days
- **When** the allocation schedule is generated
- **Then** the first period should be prorated based on days remaining in the month
  - And the last period should be prorated based on days used
  - And full periods should receive proportional amounts based on calendar days
  - And the sum of all allocations should equal the total deferred amount

### Scenario 3: View Allocation Schedule Before Activation

- **Given** I have defined a deferral schedule with recognition parameters
- **When** I view the allocation schedule preview
- **Then** I should see all planned recognition periods and amounts
  - And I should see cumulative recognized and remaining amounts per period
  - And no journal entries should be created until I activate the schedule
  - And I should be able to make adjustments before activation

### Scenario 4: Recalculate Allocation on Schedule Modification

- **Given** I have an active deferral schedule with future allocations
  - And some allocations have already been recognized (posted)
- **When** I modify the total amount or end date of the schedule
- **Then** future allocations should be recalculated based on remaining balance
  - And past allocations (already posted) should remain unchanged
  - And I should be notified of the changes to future periods
  - And the modification should be logged for audit purposes

### Scenario 5: Handle Multi-currency Deferrals

- **Given** I have a deferral schedule in a foreign currency (e.g., EUR)
  - And my company currency is different (e.g., USD)
- **When** allocation entries are generated
- **Then** amounts should be recorded in the original transaction currency
  - And company currency equivalents should be calculated
  - And the exchange rate at each recognition date should be used
  - And exchange differences should be tracked appropriately

### Scenario 6: Respect Fiscal Year Boundaries

- **Given** I have a deferral schedule spanning two fiscal years
  - And my company has a fiscal year ending December 31
- **When** the allocation schedule is generated
- **Then** allocations should respect fiscal period boundaries
  - And year-end periods should be clearly marked
  - And fiscal year totals should be calculable from the schedule
  - And allocations should not cross locked fiscal periods

---

## Allocation Methods

| Method | Description | Use Case | Calculation |
|--------|-------------|----------|-------------|
| Straight-line | Equal amounts per period | Recurring services, subscriptions | Total Amount ÷ Number of Periods |
| Date-based (Calendar Days) | Prorated by calendar days in each period | Partial period starts/ends, varying month lengths | Total Amount × (Days in Period ÷ Total Days) |
| Manual | User-defined amounts per period | Complex contracts, milestone-based recognition | User specifies each period amount |

---

## Constraints

### License and Compliance

- [ ] **AGPL-3.0 Compatibility**: Module/feature must be distributed under AGPL-3.0 compatible license
- [ ] **No Enterprise Dependencies**: No imports or dependencies on Odoo Enterprise edition modules (specifically, no dependency on `account_deferred_revenue` Enterprise module)
- [ ] **OCA Coding Standards**: Implementation must follow Odoo and OCA (Odoo Community Association) coding standards

### Version Compatibility

- [ ] **Target Version**: Odoo 18.0 compatibility required
- [ ] **Repository Note**: Current repository is Odoo 19.0; implementation should be version-agnostic where possible

### Business Rules

- [ ] **ASC 606/IFRS 15 Compliance**: Allocation calculations must comply with revenue recognition standards for proper period matching
- [ ] **Multi-currency Support**: Must handle foreign currency transactions with proper exchange rate application
- [ ] **Fiscal Period Respect**: Must honor company fiscal year configuration and locked period restrictions

---

## Technical Discovery Notes

### Codebase Analysis Areas

| Area | Files/Modules to Examine | Analysis Focus |
|------|-------------------------|----------------|
| Automatic Entry Wizard | `addons/account/wizard/account_automatic_entry_wizard.py` | `_compute_percentage()` and `_compute_total_amount()` methods for percentage-based allocation patterns |
| Period Change Action | `addons/account/wizard/account_automatic_entry_wizard.py` | `change_period` action for understanding period-based entry creation patterns |
| Move Line Handling | `addons/account/wizard/account_automatic_entry_wizard.py` | `_get_move_line_dict_vals_change_period()` for entry line generation |
| Company Settings | `addons/account/models/company.py` | `fiscalyear_last_day` and `fiscalyear_last_month` for fiscal period boundaries |
| Lock Date Validation | `addons/account/models/company.py` | `fiscalyear_lock_date` and lock date validation patterns |
| Journal Entry Model | `addons/account/models/account_move.py` | `_get_accounting_date()` for date validation; currency handling patterns |

### Relevant Existing Modules

- `addons/account/` - Core accounting module containing:
  - Percentage-based calculation via `percentage` field (0-100%) in automatic entry wizard
  - Lock date validation (`_check_date` constraint) for period restrictions
  - Currency conversion patterns in `_get_move_dict_vals_change_account`
  - Fiscal period configuration at company level
- `addons/analytic/` - Analytic accounting module for:
  - Preserving analytic distribution in allocation entries

### OCA Module Compatibility

| OCA Repository | Module | Compatibility Consideration |
|----------------|--------|----------------------------|
| OCA/account-closing | `account_cutoff_accrual_base` | Period-based allocation patterns for reference |
| OCA/account-financial-tools | `account_spread_cost_revenue` | Revenue/expense spreading patterns for date-based allocation |

### Key Implementation Patterns from Source Analysis

The existing `account_automatic_entry_wizard.py` provides important patterns:

1. **Percentage-Based Allocation**: `_compute_total_amount()` calculates amounts based on percentage: `(percentage / 100) * sum(move_line_ids.mapped('balance'))`
2. **Date Grouping**: `_get_move_dict_vals_change_period()` groups entries by date using `groupby(self.move_line_ids, get_lock_safe_date)`
3. **Lock Safe Dates**: `_get_lock_safe_date()` ensures dates respect lock date constraints
4. **Amount Rounding**: Uses `company_id.currency_id.round()` for proper currency rounding
5. **Multi-currency Handling**: Tracks `amount_currency` separately from balance for multi-currency scenarios

---

## Dependencies

### Story Dependencies

| Dependency Type | Story ID | Story Title | Relationship |
|-----------------|----------|-------------|--------------|
| Parent Feature | FEATURE-005 | Deferred Revenue/Expenses | This story is part of this feature |
| Blocked By | DR-001 | Deferral Schedule Definition | Schedule must be defined before period allocation can occur |
| Blocks | DR-003 | Cut-off Entry Generation | Allocation data required for cut-off entry generation |
| Related | DR-004 | Recognition Dashboard | Dashboard displays allocation schedules and progress |

### External Dependencies

| Dependency | Type | Notes |
|------------|------|-------|
| ASC 606 (Revenue from Contracts with Customers) | Accounting Standard | Allocation timing must align with performance obligation satisfaction |
| IFRS 15 (Revenue from Contracts with Customers) | Accounting Standard | International revenue recognition period requirements |
| Company Fiscal Year Configuration | System Configuration | Period boundaries for allocation scheduling |
| Currency Exchange Rates | System Data | Required for multi-currency allocation calculations |

### Integration Points

| Odoo Model/Module | Integration Type | Purpose |
|-------------------|------------------|---------|
| `account.move` | Write | Create recognition journal entries for each allocation period |
| `account.move.line` | Write | Create debit/credit lines for recognition entries |
| `res.company` | Read | Access fiscal period settings and currency configuration |
| `res.currency` | Read | Multi-currency rate conversion for allocation amounts |
| Deferral Schedule Model (from DR-001) | Read | Access schedule parameters for allocation calculation |

---

## Test Requirements

### Coverage Requirement

| Metric | Requirement | Notes |
|--------|-------------|-------|
| **Minimum Test Coverage** | **80%** | Mandatory for all new functionality |
| Unit Test Coverage | 80%+ | Allocation calculation methods, proration logic |
| Integration Test Coverage | 80%+ | Schedule-to-allocation workflow, journal entry creation |

### Unit Test Scenarios

| Acceptance Scenario | Unit Test Focus | Key Assertions |
|---------------------|-----------------|----------------|
| Scenario 1: Straight-line | Straight-line allocation calculation | Equal amounts; sum equals total; period count correct |
| Scenario 2: Date-based | Proration calculation logic | First/last periods prorated; days calculated correctly |
| Scenario 3: Preview | Preview generation without posting | No journal entries created; preview data accurate |
| Scenario 4: Modification | Recalculation on schedule change | Past preserved; future recalculated; notifications sent |
| Scenario 5: Multi-currency | Currency conversion in allocations | Correct currency recorded; exchange rates applied |
| Scenario 6: Fiscal Year | Fiscal boundary handling | Year-end marked; periods respect boundaries; totals calculable |

### Integration Test Considerations

- [ ] Test integration with `account.move` model for journal entry creation
- [ ] Test integration with deferral schedule model (DR-001)
- [ ] Test fiscal year boundary handling with company settings
- [ ] Test lock date validation against company fiscal lock dates
- [ ] Test multi-currency allocations with exchange rate application
- [ ] Test allocation sum always equals total deferred amount (rounding handling)
- [ ] Test schedule modification with posted/unposted allocation handling

### Acceptance Test Mapping

| BDD Scenario | Test Method Name | Test Type |
|--------------|------------------|-----------|
| Scenario 1: Straight-line Allocation | `test_straight_line_allocation_calculation` | Acceptance |
| Scenario 2: Date-based Allocation | `test_date_based_proration_calculation` | Acceptance |
| Scenario 3: Preview Allocation | `test_allocation_preview_no_posting` | Acceptance |
| Scenario 4: Modification Recalculation | `test_schedule_modification_recalculation` | Acceptance |
| Scenario 5: Multi-currency | `test_multi_currency_allocation` | Acceptance |
| Scenario 6: Fiscal Boundaries | `test_fiscal_year_boundary_respect` | Acceptance |

---

## Allocation Calculation Examples

### Example 1: Straight-line Allocation

```
Total Deferral: $12,000
Recognition Period: 12 months (Jan 2024 - Dec 2024)
Method: Straight-line

Allocation Schedule:
| Period    | Recognition Amount | Cumulative | Remaining |
|-----------|-------------------|------------|-----------|
| Jan 2024  | $1,000.00         | $1,000.00  | $11,000.00|
| Feb 2024  | $1,000.00         | $2,000.00  | $10,000.00|
| ...       | ...               | ...        | ...       |
| Dec 2024  | $1,000.00         | $12,000.00 | $0.00     |
```

### Example 2: Date-based Proration

```
Total Deferral: $1,000
Recognition Period: Jan 15, 2024 - Mar 15, 2024 (60 days)
Method: Date-based (calendar days)

Calculation:
- Jan 2024: 17 days (Jan 15-31) → $1,000 × (17/60) = $283.33
- Feb 2024: 29 days (leap year) → $1,000 × (29/60) = $483.33
- Mar 2024: 14 days (Mar 1-14) → $1,000 × (14/60) = $233.34
- Total: $283.33 + $483.33 + $233.34 = $1,000.00
```

---

## Definition of Done

### Implementation Checklist

- [ ] All acceptance criteria scenarios pass
- [ ] 80% minimum test coverage achieved
- [ ] Unit tests for all allocation calculation methods written and passing
- [ ] Integration tests for schedule-to-allocation workflow written and passing
- [ ] Rounding reconciliation ensures sum equals total in all cases

### Compliance Checklist

- [ ] No Enterprise module dependencies introduced
- [ ] AGPL-3.0 license compliance verified
- [ ] Code follows OCA coding standards
- [ ] ASC 606/IFRS 15 compliant allocation logic implemented
- [ ] Code reviewed and approved

### Documentation Checklist

- [ ] Code documentation (docstrings, comments) complete
- [ ] Allocation method documentation complete
- [ ] User-facing help text for allocation configuration

### Quality Checklist

- [ ] No critical or high-severity bugs
- [ ] Performance acceptable for schedules with 60+ periods
- [ ] Multi-currency calculations accurate
- [ ] Fiscal year boundary handling correct

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2024 | Enterprise Accounting Team | Initial story creation |

---

## Notes

### ASC 606/IFRS 15 Compliance Notes

The automatic period allocation must support the following revenue recognition concepts:

1. **Over-time Recognition**: For performance obligations satisfied over time, revenue should be allocated based on progress toward completion
2. **Point-in-time Recognition**: For instantaneous transfers of control, allocation should recognize full amount in the period of transfer
3. **Variable Consideration**: Allocation calculations should handle adjustments to deferred amounts when variable consideration changes

### Rounding Considerations

To ensure the sum of all period allocations exactly equals the total deferred amount:
- Use the "last period adjustment" method: Calculate all periods except the last, then assign the remaining balance to the final period
- Apply company currency rounding rules consistently
- Track and display any rounding adjustments for audit purposes

### Multi-company Considerations

- Each company may have different fiscal year configurations
- Allocation schedules should respect the company-specific fiscal calendar
- Lock date validation should use the appropriate company's lock dates
