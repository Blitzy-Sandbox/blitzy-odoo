# AM-006: Asset Disposal

| Attribute       | Value                                                    |
|-----------------|----------------------------------------------------------|
| **Story ID**    | AM-006                                                   |
| **Title**       | Asset Disposal                                           |
| **Parent Feature** | [FEATURE-004: Asset Management](../../features/FEATURE-004-asset-management.md) |
| **Status**      | Draft                                                    |
| **Priority**    | High                                                     |
| **Estimate**    | L (Large)                                                |

---

## User Story

**As an** Accountant

**I want** to dispose of fixed assets through sale, scrapping, or write-off, with automatic calculation of gain or loss on disposal and generation of closing journal entries

**So that** I can properly remove assets from the books when they are no longer in use, accurately recognize any gain or loss on disposal in accordance with GAAP/IFRS standards, and maintain complete financial records for audit purposes and regulatory compliance

---

## Acceptance Criteria

### Scenario 1: Dispose of asset through sale with proceeds

- **Given** I have a registered fixed asset in "open" (active) status
  - And the asset has a known net book value (NBV) calculated as acquisition cost minus accumulated depreciation
  - And I have Accountant permissions for asset disposal operations
  - And all depreciation entries through the disposal date have been posted or will be computed
- **When** I initiate a disposal by sale
  - And I enter the sale proceeds amount
  - And I specify the disposal date
  - And I optionally link the sale to a customer invoice or receivable
- **Then** a disposal journal entry is automatically generated containing:
  - Credit to the asset account for the original acquisition cost (removing the asset)
  - Debit to the accumulated depreciation account for the total depreciation recorded (clearing accumulated depreciation)
  - Debit to cash/receivables account for the sale proceeds
  - Debit or Credit to gain/loss on disposal account for the difference:
    - **Gain** (credit): If proceeds > NBV (proceeds minus net book value is positive)
    - **Loss** (debit): If proceeds < NBV (proceeds minus net book value is negative)
- **And** the journal entry is dated on the specified disposal date
- **And** the journal entry reference includes the asset identifier and "Disposal - Sale"
- **And** the asset status changes to "disposed" or "closed"
- **And** the disposal transaction is recorded in the asset's audit history

### Scenario 2: Dispose of asset through scrapping (zero proceeds)

- **Given** I have a registered fixed asset in "open" (active) status
  - And the asset has become obsolete, damaged beyond repair, or is no longer usable
  - And the asset has remaining net book value (NBV > 0) or is fully depreciated (NBV = 0)
  - And I have Accountant permissions for asset disposal operations
- **When** I initiate a disposal by scrapping
  - And I specify the disposal date
  - And I provide a reason for scrapping (optional but recommended for audit trail)
  - And I confirm that sale proceeds are zero
- **Then** a disposal journal entry is automatically generated containing:
  - Credit to the asset account for the original acquisition cost (removing the asset)
  - Debit to the accumulated depreciation account for the total depreciation recorded
  - Debit to loss on disposal account for the remaining net book value (if NBV > 0)
- **And** if the asset was fully depreciated (NBV = 0), no gain or loss is recognized
- **And** the journal entry is dated on the specified disposal date
- **And** the journal entry reference includes the asset identifier and "Disposal - Scrapped"
- **And** the asset status changes to "disposed" or "closed"
- **And** the scrapping reason is recorded in the disposal audit trail

### Scenario 3: Dispose of asset through write-off

- **Given** I have a registered fixed asset in "open" (active) status
  - And the asset has been lost, stolen, destroyed, or is otherwise unrecoverable
  - And the asset has remaining net book value that must be written off
  - And I have Accountant permissions for asset disposal operations
- **When** I initiate a disposal by write-off
  - And I specify the disposal date
  - And I select write-off as the disposal method
  - And I provide documentation reference (insurance claim number, police report, etc.)
  - And I optionally enter any insurance recovery amount receivable
- **Then** a disposal journal entry is automatically generated containing:
  - Credit to the asset account for the original acquisition cost
  - Debit to the accumulated depreciation account for the total depreciation recorded
  - Debit to loss on disposal account for the net book value minus any insurance recovery
  - Debit to insurance receivable account for expected recovery amount (if applicable)
- **And** the journal entry is dated on the specified disposal date
- **And** the journal entry reference includes the asset identifier and "Disposal - Write-off"
- **And** the asset status changes to "disposed" or "closed"
- **And** the write-off reason and documentation reference are recorded in the audit trail

### Scenario 4: Automatic gain/loss calculation based on net book value versus proceeds

- **Given** I am disposing of an asset through any method (sale, scrap, or write-off)
  - And the asset has a calculable net book value:
    - NBV = Acquisition Cost - Accumulated Depreciation
  - And any un-posted depreciation through the disposal date has been calculated
- **When** I confirm the disposal with the specified proceeds amount
- **Then** the system automatically calculates the gain or loss:
  - **Calculation Formula**: Gain/Loss = Proceeds - Net Book Value
  - **Positive Result** (Gain): Credited to gain on disposal account
  - **Negative Result** (Loss): Debited to loss on disposal account
  - **Zero Result**: No gain/loss entry if proceeds exactly equal NBV
- **And** the calculation considers:
  - All posted depreciation entries
  - Any catch-up depreciation from last depreciation date to disposal date
  - Any revaluation surplus previously recorded (to be reversed on disposal per IAS 16)
  - Any impairment losses previously recorded
- **And** the calculated gain/loss amount is displayed before disposal confirmation for user review
- **And** the gain/loss calculation details are stored for audit purposes

### Scenario 5: Partial asset disposal (disposing of a portion of an asset)

- **Given** I have a registered fixed asset representing multiple units or a divisible asset
  - And the asset has been configured to allow partial disposal
  - And I need to dispose of only a portion of the asset (e.g., sell 30 of 100 units)
  - And the asset has a defined quantity or is tracked by units
- **When** I initiate a partial disposal
  - And I specify the portion or quantity to dispose (e.g., percentage or unit count)
  - And I enter the proceeds for the disposed portion (if sale)
  - And I specify the disposal date
- **Then** the system calculates the proportional values:
  - Proportional acquisition cost = (Disposed Quantity / Total Quantity) × Original Acquisition Cost
  - Proportional accumulated depreciation = (Disposed Quantity / Total Quantity) × Total Accumulated Depreciation
  - Proportional NBV = Proportional Acquisition Cost - Proportional Accumulated Depreciation
  - Gain/Loss = Proceeds - Proportional NBV
- **And** a disposal journal entry is generated for the proportional amounts
- **And** the original asset record is updated:
  - Acquisition cost reduced by the proportional amount disposed
  - Accumulated depreciation reduced by the proportional amount disposed
  - Remaining quantity updated to reflect partial disposal
- **And** future depreciation schedule is recalculated based on the reduced asset value
- **And** a disposal history record links to the original asset showing the partial disposal details
- **And** the asset remains in "open" status with the retained portion continuing depreciation

### Scenario 6: Disposal date validation against depreciation schedule

- **Given** I am disposing of an asset
  - And the asset has an established depreciation schedule with posted entries
  - And depreciation has been processed through a certain date
- **When** I specify a disposal date
- **Then** the system validates the disposal date:
  - **Validation 1**: Disposal date cannot be before the asset acquisition date
  - **Validation 2**: Disposal date cannot be in a locked fiscal period
  - **Validation 3**: If disposal date is after the last depreciation entry date, catch-up depreciation must be computed
  - **Validation 4**: Disposal date cannot be in the future beyond the current accounting period (configurable)
- **And** if the disposal date falls between the last depreciation date and end of current period:
  - The system calculates prorated depreciation from last depreciation date to disposal date
  - This catch-up depreciation is either:
    - Included in the disposal journal entry as a combined transaction, or
    - Generated as a separate depreciation entry immediately before the disposal entry
- **And** clear validation messages are displayed if any date constraints are violated
- **And** the user can adjust the disposal date to satisfy validation requirements

---

## Technical Notes

### Codebase Analysis Areas

The following areas of the existing codebase should be analyzed during implementation:

| Source File | Analysis Focus |
|-------------|----------------|
| `addons/account/models/account_move.py` | Journal entry creation patterns using `move_type='entry'`, state management (`draft`/`posted`), `line_ids` construction with `Command.create()`, posting workflow via `action_post()` |
| `addons/account/models/account_move_line.py` | Debit/credit line creation patterns, account assignment validation, partner linking, currency handling for disposal entries |
| `addons/account/wizard/account_automatic_entry_wizard.py` | Automatic entry generation patterns, wizard implementation that could serve as a model for disposal wizard |
| `addons/account/models/account_account.py` | Account type definitions (`asset_fixed`, `expense`, `income`), account validation patterns for disposal accounts |

### Key Integration Points

| Integration | Description |
|-------------|-------------|
| `AM-001 (Asset Registration)` | Disposal operates on registered assets; requires access to asset model with acquisition cost, accumulated depreciation, and linked accounts |
| `AM-004 (Automatic Depreciation Entries)` | Disposal must account for all depreciation through disposal date; may need to trigger catch-up depreciation generation |
| `AM-005 (Asset Modification)` | Disposal calculation must consider any prior revaluations or impairments that affect carrying value |
| `account.move` | Disposal journal entries use standard journal entry model with proper multi-line debit/credit structure |
| `account.account` | Account type filtering ensures appropriate accounts are used for gain/loss recognition |

### Accounting Standards Compliance

| Standard | Application |
|----------|-------------|
| **IAS 16** (Property, Plant and Equipment) | Derecognition requirements: remove carrying amount on disposal; recognize gain/loss in profit or loss; transfer revaluation surplus to retained earnings (not through P&L) |
| **GAAP ASC 360-10-40** | Asset disposal and derecognition: gain/loss computed as difference between net proceeds and carrying amount |
| **IAS 36** | If asset was previously impaired, no special treatment on disposal; impairment loss already recognized |

### Model Considerations

**Asset Disposal Model Structure:**

| Field | Purpose |
|-------|---------|
| `asset_id` | Many2one link to the asset being disposed |
| `disposal_method` | Selection: 'sale', 'scrap', 'write_off' |
| `disposal_date` | Date of disposal (transaction date) |
| `proceeds_amount` | Sale proceeds or insurance recovery amount |
| `proceeds_account_id` | Account for proceeds (cash, receivables, etc.) |
| `gain_loss_amount` | Computed gain or loss on disposal |
| `gain_account_id` | Account for gains (income type) |
| `loss_account_id` | Account for losses (expense type) |
| `move_id` | Many2one link to generated disposal journal entry |
| `catchup_depreciation_move_id` | Many2one link to catch-up depreciation entry (if separate) |
| `disposal_reason` | Text field for scrapping/write-off reason |
| `documentation_ref` | Reference to supporting documentation |
| `is_partial` | Boolean indicating partial disposal |
| `disposed_quantity` | Quantity disposed (for partial disposals) |

**State Machine for Disposal:**
- `draft` → User enters disposal details and method
- `confirmed` → Disposal validated and journal entry generated
- `posted` → Journal entry posted to general ledger
- `cancelled` → Disposal reversed (creates offsetting entry to reinstate asset)

**Computed Field Requirements:**
- Net book value at disposal date (acquisition cost - accumulated depreciation - impairments + revaluations)
- Prorated catch-up depreciation amount (if disposal date > last depreciation date)
- Gain/loss preview before confirmation
- Proportional values for partial disposal calculations

### Journal Entry Patterns

From `account_move.py`, key patterns for generating disposal entries:

| Pattern | Implementation |
|---------|----------------|
| Entry Creation | Use `self.env['account.move'].create()` with `move_type='entry'` |
| Multi-Line Entry | Create `line_ids` with multiple `Command.create()` entries for asset, accumulated depreciation, proceeds, and gain/loss |
| Balancing | Ensure total debits equal total credits in the entry |
| Posting | Call `action_post()` after creation if auto-post enabled |
| Reference | Set `ref` field with asset reference and disposal method description |
| Date Handling | Validate disposal date against fiscal period locks using company fiscal year settings |

### Account Type Reference

From `addons/account/models/account_account.py`, relevant account types for disposal:

| Account Type | Usage in Asset Disposal |
|--------------|-------------------------|
| `asset_fixed` | Asset account (credited to remove asset from books) |
| `asset_non_current` | Accumulated depreciation account (debited to clear contra-asset) |
| `asset_receivable` or `liquidity` | Proceeds account (cash or receivables debited for sale proceeds) |
| `income` or `income_other` | Gain on disposal account (credited when proceeds > NBV) |
| `expense` or `expense_direct_cost` | Loss on disposal account (debited when proceeds < NBV) |

### Gain/Loss Calculation Logic

```
# Pseudocode for disposal gain/loss calculation

def calculate_disposal_gain_loss(asset, disposal_date, proceeds):
    # Calculate depreciation through disposal date
    accumulated_depreciation = sum(posted_depreciation_entries)
    if disposal_date > last_depreciation_date:
        catchup_depreciation = calculate_prorated_depreciation(
            last_depreciation_date, 
            disposal_date
        )
        accumulated_depreciation += catchup_depreciation
    
    # Calculate net book value
    nbv = asset.acquisition_cost - accumulated_depreciation
    
    # Adjust for revaluations and impairments
    nbv += asset.revaluation_surplus  # If using revaluation model
    nbv -= asset.impairment_losses_unrecovered
    
    # Calculate gain or loss
    gain_loss = proceeds - nbv
    
    return {
        'nbv': nbv,
        'gain_loss': gain_loss,
        'is_gain': gain_loss > 0,
        'catchup_depreciation': catchup_depreciation
    }
```

### Validation Requirements

| Validation | Rule |
|------------|------|
| Disposal Date | Cannot be before acquisition date; cannot be in locked fiscal period |
| Asset Status | Asset must be in 'open' status (not draft, already disposed, or cancelled) |
| Proceeds Amount | Must be >= 0; cannot be negative |
| Partial Disposal Quantity | Must be > 0 and <= remaining asset quantity |
| Account Configuration | All required accounts (asset, accumulated depreciation, gain/loss) must be configured |
| Depreciation Status | All scheduled depreciation through disposal date must be posted or computable |

---

## Dependencies

### Story Dependencies

| Dependency Type | Story | Description |
|-----------------|-------|-------------|
| **Depends On** | AM-001 | Asset Registration must be complete—disposal operates on registered assets with established acquisition values and account assignments |
| **Depends On** | AM-004 | Automatic Depreciation Entries must function—disposal requires accurate accumulated depreciation through disposal date and may trigger catch-up depreciation |
| **Soft Dependency** | AM-005 | Asset Modification should be considered—disposal gain/loss calculation must account for any prior revaluations or impairments that adjusted the carrying value |

### Dependency Flow

```
AM-001 (Asset Registration)
    │
    ├──→ AM-002 (Depreciation Configuration)
    │        │
    │        ▼
    │   AM-003 (Depreciation Board)
    │        │
    │        ▼
    └──→ AM-004 (Automatic Depreciation Entries) ──┐
                                                    │
    AM-005 (Asset Modification) ───────────────────┤
                                                    │
                                                    ▼
                                        AM-006 (Asset Disposal)
                                                    │
                                                    ▼
                                        Disposal Journal Entry
                                        + Asset Closed/Disposed
```

### Module Dependencies

| Module | Dependency Type | Purpose |
|--------|-----------------|---------|
| `account` | Required | Core accounting models (`account.move`, `account.account`, `account.journal`) for disposal journal entry generation |
| `base` | Required | Base models (`res.company`, `ir.sequence`) for company context and disposal reference numbering |
| `mail` | Optional | Chatter/activity tracking on disposal records for audit trail |

### External Dependencies

| Constraint | Requirement |
|------------|-------------|
| **No Enterprise Dependencies** | Implementation must NOT import or depend on Odoo Enterprise `account_asset` module |
| **OCA Compatibility** | Should be compatible with OCA `account-financial-tools` asset management patterns where applicable |
| **GAAP/IFRS Compliance** | Implementation must support both IAS 16 derecognition requirements and US GAAP ASC 360 disposal rules |

---

## Constraints

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

---

## Test Requirements

### Coverage Target

| Metric | Target |
|--------|--------|
| **Minimum Test Coverage** | 80% |
| **Unit Test Coverage** | All model methods, computed fields, constraints, gain/loss calculations, and validation logic |
| **Integration Test Coverage** | Complete disposal workflow with journal entry generation, asset status update, and depreciation coordination |

### Required Test Scenarios

| Test ID | Scenario | Expected Outcome |
|---------|----------|------------------|
| T-AM-006-01 | Dispose asset by sale with gain | Disposal entry created with credit to gain account; gain = proceeds - NBV |
| T-AM-006-02 | Dispose asset by sale with loss | Disposal entry created with debit to loss account; loss = NBV - proceeds |
| T-AM-006-03 | Dispose asset by sale with no gain/loss | Disposal entry created with no gain/loss line when proceeds = NBV |
| T-AM-006-04 | Dispose asset by scrapping (zero proceeds) | Disposal entry created with full NBV debited to loss account |
| T-AM-006-05 | Dispose fully depreciated asset (NBV = 0) | Disposal entry clears asset and accumulated depreciation; no gain/loss |
| T-AM-006-06 | Dispose asset by write-off with insurance recovery | Disposal entry includes insurance receivable debit; loss reduced by recovery amount |
| T-AM-006-07 | Partial asset disposal | Proportional amounts calculated correctly; remaining asset continues with reduced values |
| T-AM-006-08 | Disposal with catch-up depreciation | Catch-up depreciation computed from last entry to disposal date; included in disposal calculation |
| T-AM-006-09 | Disposal date before acquisition date (rejected) | Validation error raised; disposal not allowed |
| T-AM-006-10 | Disposal date in locked fiscal period (rejected) | Validation error raised; disposal not allowed in locked period |
| T-AM-006-11 | Disposal of already disposed asset (rejected) | Validation error raised; cannot dispose an already disposed asset |
| T-AM-006-12 | Disposal of draft/unconfirmed asset (rejected) | Validation error raised; only open/active assets can be disposed |
| T-AM-006-13 | Disposal journal entry account validation | Appropriate account types enforced for each line in disposal entry |
| T-AM-006-14 | Disposal journal entry balance validation | Total debits equal total credits in disposal entry |
| T-AM-006-15 | Asset status update after disposal | Asset status changed to 'disposed' or 'closed' after successful disposal |
| T-AM-006-16 | Disposal audit trail completeness | All disposal details recorded in asset history including method, date, proceeds, gain/loss |

### Gain/Loss Calculation Accuracy Tests

| Test ID | Scenario | Verification Method |
|---------|----------|---------------------|
| T-AM-006-G01 | Sale with proceeds > NBV (gain) | Manual calculation: Proceeds $15,000 - NBV $10,000 = Gain $5,000 |
| T-AM-006-G02 | Sale with proceeds < NBV (loss) | Manual calculation: Proceeds $5,000 - NBV $10,000 = Loss $5,000 |
| T-AM-006-G03 | Scrapping with remaining NBV | Manual calculation: Proceeds $0 - NBV $8,000 = Loss $8,000 |
| T-AM-006-G04 | Disposal after revaluation increase | Gain/loss calculated from revalued carrying amount; revaluation surplus treatment per IAS 16 |
| T-AM-006-G05 | Disposal after impairment | Gain/loss calculated from impaired carrying amount |
| T-AM-006-G06 | Partial disposal proportional calculation | Disposed portion: 25% of asset; verify 25% of acquisition cost and accumulated depreciation used |
| T-AM-006-G07 | Catch-up depreciation accuracy | Prorated depreciation from last entry to disposal date calculated correctly |

### Journal Entry Structure Tests

| Test ID | Scenario | Verification Points |
|---------|----------|---------------------|
| T-AM-006-J01 | Sale disposal entry structure | 4 lines: Credit Asset, Debit Accum Depr, Debit Cash/AR, Credit/Debit Gain/Loss |
| T-AM-006-J02 | Scrap disposal entry structure | 3 lines: Credit Asset, Debit Accum Depr, Debit Loss |
| T-AM-006-J03 | Write-off with insurance entry structure | 4 lines: Credit Asset, Debit Accum Depr, Debit Insurance Receivable, Debit Loss (net) |
| T-AM-006-J04 | Entry reference format | Reference includes asset ID and disposal method |
| T-AM-006-J05 | Entry date validation | Entry dated on specified disposal date |

### Validation Criteria

| Validation Area | Criteria |
|-----------------|----------|
| **Journal Entry Accuracy** | Total debits equal total credits; each line has correct account type |
| **Gain/Loss Accuracy** | Calculated gain/loss matches manual verification within rounding tolerance |
| **NBV Calculation** | NBV = Acquisition Cost - All Posted Depreciation - Catch-up Depreciation |
| **Partial Disposal Math** | Proportional calculations maintain asset integrity (remaining value + disposed value = original value) |
| **Audit Trail Completeness** | Disposal method, date, proceeds, calculated gain/loss, and user recorded |
| **Status Update** | Asset marked as disposed and no longer appears in active asset lists |

---

## Glossary

| Term | Definition |
|------|------------|
| **Net Book Value (NBV)** | The carrying amount of an asset calculated as Acquisition Cost minus Accumulated Depreciation, also known as carrying value or book value |
| **Gain on Disposal** | The positive difference when proceeds from asset disposal exceed the net book value |
| **Loss on Disposal** | The negative difference when proceeds from asset disposal are less than the net book value |
| **Catch-up Depreciation** | Prorated depreciation calculated from the last posted depreciation date to the disposal date |
| **Partial Disposal** | Disposing of a portion of an asset while retaining the remainder for continued use and depreciation |
| **Write-off** | A disposal method used when an asset is lost, stolen, destroyed, or otherwise unrecoverable |
| **Scrapping** | A disposal method used when an asset has become obsolete or damaged beyond repair with no sale value |
| **Revaluation Surplus** | The increase in asset value above historical cost recorded in equity under the revaluation model (IAS 16) |

---

## Change History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2024 | Blitzy Platform | Initial creation of AM-006 Asset Disposal user story |
