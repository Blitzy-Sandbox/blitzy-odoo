# AM-005: Asset Modification

| Attribute       | Value                                                    |
|-----------------|----------------------------------------------------------|
| **Story ID**    | AM-005                                                   |
| **Title**       | Asset Modification                                       |
| **Parent Feature** | [FEATURE-004: Asset Management](../../features/FEATURE-004-asset-management.md) |
| **Status**      | Draft                                                    |
| **Priority**    | Medium                                                   |
| **Estimate**    | L (Large)                                                |

---

## User Story

**As an** Accountant

**I want** to adjust asset values due to revaluation or impairment events, with automatic recalculation of remaining depreciation schedules and generation of appropriate adjustment journal entries

**So that** I can maintain accurate asset valuations on financial statements, comply with IAS 16 (Property, Plant and Equipment) and IAS 36 (Impairment of Assets) accounting standards, and ensure the depreciation board reflects current asset values throughout the remaining useful life

---

## Acceptance Criteria

### Scenario 1: Asset revaluation with value increase (credit revaluation reserve)

- **Given** I have a registered fixed asset in open status
  - And the asset has a current net book value (NBV) recorded
  - And I have Accountant permissions for asset modifications
  - And the company's accounting policy permits the revaluation model under IAS 16
- **When** I initiate a revaluation to increase the asset value
  - And I enter the new fair value amount greater than the current NBV
  - And I specify the effective date of the revaluation
  - And I provide a reference to the valuation source (e.g., appraisal report number)
- **Then** a revaluation journal entry is automatically generated containing:
  - Debit to the asset account for the revaluation surplus (increase in gross value)
  - Credit to the revaluation reserve account (equity account) for the net increase
  - Adjustment to accumulated depreciation account if using the proportionate method
- **And** the journal entry is dated on the specified effective date
- **And** the asset's gross value and accumulated depreciation are updated accordingly
- **And** the modification is recorded in the asset's audit history with timestamp and user
- **And** the revaluation reserve balance is tracked separately for future reversals or disposals

### Scenario 2: Asset impairment with value decrease (debit impairment loss)

- **Given** I have a registered fixed asset in open status
  - And the asset has a current net book value (NBV) recorded
  - And I have Accountant permissions for asset modifications
  - And indicators of impairment exist (market decline, physical damage, obsolescence, adverse regulatory changes)
- **When** I initiate an impairment recognition
  - And I enter the recoverable amount (higher of fair value less costs to sell, or value in use)
  - And the recoverable amount is less than the current carrying amount (NBV)
  - And I specify the effective date of the impairment
  - And I provide an impairment reason/description
- **Then** an impairment loss journal entry is automatically generated containing:
  - Debit to impairment loss expense account for the impairment amount
  - Credit to the asset account (or accumulated impairment loss account) for the write-down
- **And** if a revaluation surplus exists for the asset, the impairment first reduces the surplus (OCI debit) before recognizing expense
- **And** the journal entry is dated on the specified effective date
- **And** the asset's carrying amount is reduced to the recoverable amount
- **And** the modification is recorded in the asset's audit history with timestamp, user, and impairment reason
- **And** the impairment amount is tracked separately for potential future reversal

### Scenario 3: Automatic recalculation of remaining depreciation schedule after modification

- **Given** an asset's value has been modified through revaluation or impairment
  - And the asset has remaining useful life (depreciation periods remaining)
  - And the asset's depreciation configuration includes method, remaining useful life, and salvage value
- **When** the asset modification is confirmed
- **Then** the system automatically recalculates the depreciation schedule based on:
  - New carrying amount (adjusted gross value less accumulated depreciation)
  - Remaining useful life (unchanged unless explicitly modified)
  - Salvage value (unchanged unless explicitly modified)
- **And** future depreciation amounts are computed using the new carrying amount
- **And** the depreciation board (AM-003) displays the updated schedule with:
  - Historical depreciation amounts unchanged (already posted)
  - Modified depreciation amounts for remaining periods
  - Clear indication of the modification point in the schedule
- **And** a recalculation summary is available showing before/after depreciation amounts per period
- **And** the recalculated schedule ensures the final NBV equals the salvage value at end of useful life

### Scenario 4: Generation of adjustment journal entries per accounting standards

- **Given** I have completed an asset modification (revaluation or impairment)
  - And the modification requires journal entries to reflect the value change
  - And appropriate accounts are configured for the modification type
- **When** I confirm the asset modification
- **Then** the system generates a journal entry that follows GAAP/IFRS requirements:
  - Entry type is "Journal Entry" (not invoice or payment type)
  - Entry is automatically posted (or remains in draft per configuration)
  - Entry reference includes the asset reference number and modification type
  - Entry memo/narration describes the modification details
- **And** the journal entry is linked to the asset record for audit trail purposes
- **And** account types are validated before posting:
  - Revaluation surplus: equity account (revaluation reserve)
  - Impairment loss: expense account
  - Asset account: fixed asset type
  - Accumulated depreciation: contra-asset type
- **And** the entry uses the correct currency and exchange rate if multi-currency
- **And** the entry is balanced (total debits equal total credits)

### Scenario 5: Complete audit trail of all modifications with effective dates

- **Given** an asset has undergone one or more modifications over its lifetime
  - And each modification was processed through the asset modification workflow
- **When** I view the asset's modification history
- **Then** I can see a complete chronological log containing for each modification:
  - Modification type (revaluation, impairment, useful life change, salvage value adjustment)
  - Effective date of the modification
  - Previous value and new value
  - Modification amount (increase or decrease)
  - User who performed the modification
  - Timestamp of when the modification was recorded
  - Reference to the supporting documentation (appraisal, impairment assessment)
  - Link to the associated journal entry
- **And** the modification history cannot be edited or deleted (immutable audit trail)
- **And** modifications are displayed in chronological order (oldest first or most recent first, user-selectable)
- **And** the modification history is exportable for audit documentation purposes
- **And** any modification reason or notes entered at the time are preserved

### Scenario 6: Reversal of impairment when conditions change

- **Given** an asset has a previously recognized impairment loss
  - And the impairment indicators that originally triggered the impairment no longer exist
  - And the asset's recoverable amount has increased since the impairment was recognized
  - And the increase is related to a reversal of the specific impairment event (not general appreciation)
- **When** I initiate an impairment reversal
  - And I enter the new recoverable amount (higher than current carrying amount)
  - And the new carrying amount does not exceed what it would have been without impairment (depreciated historical cost)
  - And I specify the effective date and provide reversal justification
- **Then** an impairment reversal journal entry is automatically generated containing:
  - Debit to the asset account (or accumulated impairment account) to increase carrying amount
  - Credit to impairment reversal gain in profit or loss
- **And** the reversal amount is limited to:
  - The original impairment amount recognized, or
  - The amount that brings carrying value up to depreciated historical cost (whichever is lower)
- **And** if any original impairment was recorded against revaluation surplus, the reversal first restores the surplus (OCI credit)
- **And** the depreciation schedule is recalculated based on the increased carrying amount
- **And** the reversal is recorded in the modification history with full audit trail
- **And** the impairment tracking shows the original impairment reduced by the reversal amount

---

## Technical Notes

### Codebase Analysis Areas

The following areas of the existing codebase should be analyzed during implementation:

| Source File | Analysis Focus |
|-------------|----------------|
| `addons/account/models/account_move.py` | Journal entry creation patterns, `move_type='entry'` for miscellaneous entries, state management, posting workflow, line item construction with `Command.create()` |
| `addons/account/models/account_move_line.py` | Debit/credit line creation patterns, account assignment, currency handling, partner linking for journal items |
| `addons/account/wizard/account_automatic_entry_wizard.py` | Automatic entry generation patterns, wizard implementation for creating adjustment entries |
| `addons/account/models/account_account.py` | Account type definitions, validation patterns for equity and expense accounts |

### Key Integration Points

| Integration | Description |
|-------------|-------------|
| `AM-001 (Asset Registration)` | Asset modification operates on registered assets; requires access to asset model with acquisition cost, dates, and accounts |
| `AM-003 (Depreciation Board)` | Modification triggers depreciation schedule recalculation; board must display updated future periods |
| `AM-002 (Depreciation Configuration)` | Recalculation uses existing depreciation method configuration; method should remain unchanged unless explicitly modified |
| `account.move` | Adjustment journal entries use standard journal entry model with proper account assignments |
| `mail.activity.mixin` | Modification events should trigger activity/notification for relevant users |

### Accounting Standards Compliance

| Standard | Application |
|----------|-------------|
| **IAS 16** (Property, Plant and Equipment) | Revaluation model requirements: fair value measurement, revaluation surplus treatment, proportionate/elimination methods for accumulated depreciation |
| **IAS 36** (Impairment of Assets) | Impairment recognition, recoverable amount determination (higher of fair value less costs to sell and value in use), impairment loss allocation, reversal conditions and limits |
| **GAAP ASC 360** | Similar impairment testing requirements for US GAAP compliance |

### Model Considerations

**Asset Modification Model Structure:**

| Field | Purpose |
|-------|---------|
| `asset_id` | Many2one link to the asset being modified |
| `modification_type` | Selection: 'revaluation', 'impairment', 'impairment_reversal', 'useful_life_change', 'salvage_change' |
| `effective_date` | Date when modification takes effect |
| `previous_value` | Stored value before modification |
| `new_value` | Value after modification |
| `modification_amount` | Computed difference (new - previous) |
| `reason` | Text field for modification justification |
| `move_id` | Many2one link to generated journal entry |
| `supporting_document` | Reference or attachment for valuation evidence |

**State Machine for Modifications:**
- `draft` → User enters modification details
- `confirmed` → Modification validated and journal entry generated
- `posted` → Journal entry posted to general ledger (may be automatic)
- `cancelled` → Modification reversed (creates offsetting entry)

**Computed Field Requirements:**
- Maximum reversal amount (depreciated historical cost calculation)
- Current revaluation surplus balance for the asset
- Cumulative impairment losses for the asset

### Journal Entry Patterns

From `account_move.py`, key patterns for generating modification entries:

| Pattern | Implementation |
|---------|----------------|
| Entry Creation | Use `self.env['account.move'].create()` with `move_type='entry'` |
| Line Items | Use `Command.create()` for line_ids with debit/credit assignments |
| Posting | Call `action_post()` after creation if auto-post enabled |
| Reference | Set `ref` field with asset reference and modification description |
| Date Handling | Validate effective date against fiscal period locks |

### Account Type Reference

From `addons/account/models/account_account.py`, relevant account types:

| Account Type | Usage in Asset Modification |
|--------------|----------------------------|
| `asset_fixed` | Asset account (debit for revaluation increase, credit for impairment) |
| `asset_non_current` | Accumulated depreciation / accumulated impairment (contra-asset) |
| `equity` | Revaluation reserve account (credit for revaluation surplus) |
| `expense` | Impairment loss expense account |
| `income` | Impairment reversal gain account (if separate from expense) |

### Validation Requirements

| Validation | Rule |
|------------|------|
| Effective Date | Cannot be in a locked fiscal period; must not be before asset acquisition date |
| New Value | Revaluation value must be based on fair value evidence; impairment value must be recoverable amount |
| Reversal Limit | Impairment reversal cannot exceed original impairment or result in carrying amount above depreciated historical cost |
| Account Configuration | All required accounts must be configured before modification is allowed |
| Asset Status | Asset must be in 'open' status (not draft, closed, or disposed) |

---

## Dependencies

### Story Dependencies

| Dependency Type | Story | Description |
|-----------------|-------|-------------|
| **Depends On** | AM-001 | Asset Registration must be complete—modifications operate on registered assets with established acquisition values |
| **Depends On** | AM-003 | Depreciation Board must be available—modifications trigger schedule recalculation and updated board display |
| **Soft Dependency** | AM-002 | Depreciation Configuration is used for recalculation; configuration should exist but modification can proceed without it |
| **Required By** | AM-006 | Asset Disposal may need to handle assets with prior modifications; disposal gain/loss calculation must consider all value adjustments |

### Dependency Flow

```
AM-001 (Asset Registration)
    │
    ├──→ AM-002 (Depreciation Configuration)
    │        │
    │        ▼
    └──→ AM-003 (Depreciation Board) ──→ AM-005 (Asset Modification)
                                              │
                                              │ (Triggers)
                                              ▼
                                         Schedule Recalculation
                                              │
                                              ▼
                                         AM-006 (Asset Disposal)
```

### Module Dependencies

| Module | Dependency Type | Purpose |
|--------|-----------------|---------|
| `account` | Required | Core accounting models (`account.move`, `account.account`, `account.journal`) for journal entry generation |
| `base` | Required | Base models (`res.company`, `ir.sequence`) for company context and audit logging |
| `mail` | Optional | Chatter/activity tracking on modification records |

### External Dependencies

| Constraint | Requirement |
|------------|-------------|
| **No Enterprise Dependencies** | Implementation must NOT import or depend on Odoo Enterprise `account_asset` module |
| **OCA Compatibility** | Should be compatible with OCA `account-financial-tools` patterns where applicable |
| **IAS/GAAP Compliance** | Implementation must support both IAS 16/36 and US GAAP ASC 360 requirements |

---

## Test Requirements

### Coverage Target

| Metric | Target |
|--------|--------|
| **Minimum Test Coverage** | 80% |
| **Unit Test Coverage** | All model methods, computed fields, constraints, and validation logic |
| **Integration Test Coverage** | Modification workflow with journal entry generation and depreciation recalculation |

### Required Test Scenarios

| Test ID | Scenario | Expected Outcome |
|---------|----------|------------------|
| T-AM-005-01 | Revalue asset with value increase | Revaluation journal entry created; debit asset, credit revaluation reserve; NBV updated |
| T-AM-005-02 | Impair asset with value decrease | Impairment journal entry created; debit impairment loss, credit asset/accumulated impairment |
| T-AM-005-03 | Impairment reduces existing revaluation surplus first | Impairment debits revaluation reserve before recognizing expense |
| T-AM-005-04 | Depreciation recalculation after revaluation | Future depreciation amounts reflect new carrying value; schedule periods unchanged |
| T-AM-005-05 | Depreciation recalculation after impairment | Future depreciation amounts reduced proportionally; final NBV equals salvage value |
| T-AM-005-06 | Impairment reversal within limits | Reversal entry generated; carrying amount increased; does not exceed depreciated historical cost |
| T-AM-005-07 | Impairment reversal exceeds limit (rejected) | Validation error raised; reversal amount capped at maximum allowed |
| T-AM-005-08 | Modification audit trail completeness | All modification fields captured in history; immutable record created |
| T-AM-005-09 | Effective date in locked period (rejected) | Validation error raised; modification not allowed in locked period |
| T-AM-005-10 | Modification on disposed asset (rejected) | Validation error raised; cannot modify disposed assets |
| T-AM-005-11 | Journal entry account validation | Appropriate account types enforced for each entry type |
| T-AM-005-12 | Multi-currency revaluation | Exchange rate applied correctly; currency matches asset configuration |

### Recalculation Accuracy Tests

| Test ID | Scenario | Verification Method |
|---------|----------|---------------------|
| T-AM-005-R01 | Straight-line recalculation after revaluation | Manual calculation comparison; (New NBV - Salvage) / Remaining periods |
| T-AM-005-R02 | Declining balance recalculation after impairment | Manual calculation comparison; Rate × New NBV per period |
| T-AM-005-R03 | Recalculation preserves historical entries | Posted depreciation entries unchanged; only future periods recalculated |
| T-AM-005-R04 | Final NBV equals salvage value | After all depreciation, NBV converges to salvage regardless of modifications |

### Validation Criteria

| Validation Area | Criteria |
|-----------------|----------|
| Journal Entry Accuracy | All modification entries are balanced (debits = credits) |
| Account Type Compliance | Correct account types used for each line item |
| Reversal Limit Enforcement | No reversal results in carrying amount exceeding depreciated historical cost |
| Audit Trail Completeness | Every modification recorded with user, timestamp, and all required fields |
| Fiscal Period Respect | No entries created in locked fiscal periods |

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
| **Modification Processing** | < 3 seconds including journal entry generation |
| **Depreciation Recalculation** | < 2 seconds for schedules up to 600 periods |
| **Audit History Query** | < 1 second to retrieve complete modification history |

---

## INVEST Checklist

| Principle | Assessment | Notes |
|-----------|------------|-------|
| **I**ndependent | ✓ Pass | Can be developed after AM-001 and AM-003 are complete; does not block other stories except AM-006 partially |
| **N**egotiable | ✓ Pass | Describes outcomes (value adjustment, recalculation, audit trail) not specific implementation approach |
| **V**aluable | ✓ Pass | Clear business value: accurate asset valuation, IAS/GAAP compliance, auditable modification history |
| **E**stimable | ✓ Pass | Well-defined scope with measurable acceptance criteria; complexity bounded by 6 scenarios |
| **S**mall | ✓ Pass | Focused on modification workflow; disposal is separate story (AM-006) |
| **T**estable | ✓ Pass | All scenarios have objective pass/fail criteria; recalculation accuracy verifiable |

---

## Related Documentation

- [EPIC-001: Enterprise Accounting Capabilities](../../EPIC-001-enterprise-accounting.md)
- [FEATURE-004: Asset Management](../../features/FEATURE-004-asset-management.md)
- [AM-001: Asset Registration](./AM-001-asset-registration.md)
- [AM-002: Depreciation Configuration](./AM-002-depreciation-configuration.md)
- [AM-003: Depreciation Board](./AM-003-depreciation-board.md)
- [AM-006: Asset Disposal](./AM-006-asset-disposal.md)
- [Story Template](../../templates/story-template.md)

---

## Glossary

| Term | Definition |
|------|------------|
| **Carrying Amount** | The amount at which an asset is recognized in the statement of financial position after deducting accumulated depreciation and accumulated impairment losses |
| **Depreciated Historical Cost** | The original cost of an asset minus accumulated depreciation that would have been recognized had no impairment occurred |
| **Fair Value** | The price that would be received to sell an asset in an orderly transaction between market participants |
| **Impairment Loss** | The amount by which the carrying amount of an asset exceeds its recoverable amount |
| **Net Book Value (NBV)** | Synonymous with carrying amount; the asset's book value after depreciation and impairment |
| **Recoverable Amount** | The higher of an asset's fair value less costs of disposal and its value in use |
| **Revaluation Surplus** | The increase in carrying amount arising from revaluation, recognized in other comprehensive income and accumulated in equity |
| **Value in Use** | The present value of the future cash flows expected to be derived from an asset |
