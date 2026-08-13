# FEATURE-001-08: Fixed Assets & Depreciation

---

## Metadata

| Attribute | Value |
|-----------|-------|
| **Feature ID** | `FEATURE-001-08` |
| **Title** | Fixed Assets & Depreciation |
| **Parent Epic** | [EPIC-001: Enterprise Accounting in Odoo](../EPIC-001-enterprise-accounting-odoo.md) |
| **Status** | Draft |
| **Priority** | 🟠 High |
| **Story Count** | 4 stories |
| **Last Updated** | 2026-08-13 |
| **Owner/Author** | Enterprise Accounting Team |

---

## 1. Feature Overview

### 1.1 Purpose and Business Value

This feature enables the **Fixed-Asset Accountant** and the **Chief Accountant** to run one governed asset sub-ledger inside Odoo across the whole life of a capital item: register the asset from the vendor bill that capitalized it, configure the depreciation method its class demands and read the projected depreciation board that method produces, post the periodic depreciation entry from that board as a balanced journal entry without duplicating it, and derecognize the asset on sale, scrapping or write-off with the gain or loss computed from net book value rather than from a spreadsheet. The **Financial Reporting Manager** presents the resulting net book value on the Balance Sheet, the **External Auditor** ties the asset register to the ledger and reads the impairment evidence behind it, and the **Tax Accountant** reads the book depreciation charge that the tax computation diverges from.

It is delivered against the following modules:

- **`account`** — the "Invoicing" application, version 1.4, category `Accounting/Accounting`, licence LGPL-3, present in this repository. It supplies `account.move` and `account.move.line` for the acquisition, depreciation, adjustment and disposal entries, `account.journal` for the Purchase and Miscellaneous journals those entries post through, `account.account` with the fixed-asset and depreciation account types the sub-ledger is anchored on, and the company lock-date fields that refuse a posting into a reported period.
- **`account_asset`** — the Enterprise asset application named in the Epic's module scope. It is **absent from `addons/`** in this repository, which the Epic records as a platform fact at [§5.4](../EPIC-001-enterprise-accounting-odoo.md#54-odoo-module-scope) rather than as a prohibition. Its absence is what makes the edition lock-in decision in §5.2 material: the asset register, the depreciation board and the disposal workflow this feature specifies must arrive either through an Odoo Enterprise subscription or through the Odoo Community Association (OCA) route with bespoke development for the residual gap.
- **`account_asset_management`** — present Community context at version 19.0.1.0.0 under AGPL-3, category `Accounting/Assets`, carrying `account.asset`, `account.asset.category` and `account.asset.depreciation.line` models together with `account.move` and `account.move.line` extensions. Discovery note **D-003** in the Epic credits it with asset registration, categories, the three depreciation methods, the depreciation board, scheduled posting and revaluation, and records the residual gap for this feature as disposal with gain or loss on sale, scrapping and write-off, impairment and impairment reversal, partial disposal, and the register-to-ledger tie-out at a `0.00` difference.
- **`analytic`** — "Analytic Accounting", version 1.2, licence LGPL-3, present in this repository. Optional: it carries the analytic distribution of the depreciation charge where cost-centre reporting is required, and FEATURE-001-09 reads that distribution as the actual side of capital-expenditure budget-versus-actual.

**Business Value Statement:**

> Every capital item is recorded once, depreciated from a schedule the system computes, and derecognized with a gain or loss the ledger can prove. The scheduled depreciation run posts 100% of the entries the depreciation board projects for the period (SM-008), so a charge is never missed and never entered twice; and the **Fixed Asset Register** ties to Fixed Assets 1500 less Accumulated Depreciation 1590 at a difference of `0.00 USD` (SM-009), so the net book value the Balance Sheet presents is the sub-ledger position rather than a restatement of it. That replaces the 8 to 16 hours of manual depreciation work a mid-sized portfolio consumes each month with a posted, evidenced sub-ledger, which is how this feature carries its part of the Epic's reduction of the close from 10 business days to 5 business days per legal entity (SM-003) and its 50% reduction in post-close audit adjustments (SM-016).

This feature serves the Epic's three objectives as follows:

| Epic Objective | Contribution of This Feature |
|----------------|------------------------------|
| Multi-entity financial operations | Each legal entity holds its own asset register in its own functional currency, with its own asset categories, its own asset reference sequence and its own Miscellaneous journal. Every register, board and tie-out statement in this feature names the company whose books are affected — `US-01`, `NL-01` or `GB-01` — because an asset belongs to one entity and its depreciation charge lands in that entity's Profit & Loss |
| Compliance reporting | Depreciation is measured under a named method whose formula is recorded against the asset, and derecognition, impairment and impairment reversal are measurement events with their own balanced entries and their own effective dates. That is the evidence IAS 16, IAS 36 and US GAAP ASC 360 require, and it is what the External Auditor reads instead of requesting an extract |
| Real-time financial visibility | Net book value is read from posted journal items and the projected board, so the asset position is current as of the last posted depreciation entry. The board also projects the charge forward across the remaining useful life, which is what makes future depreciation expense visible to budgeting before the period it lands in |

Ordering rule **ORD-001** in the Epic makes FEATURE-001-01 a prerequisite of every posting story here, because a depreciation entry cannot post without Fixed Assets 1500, Accumulated Depreciation 1590 and Depreciation Expense 6500, without the Miscellaneous journal, and without an open fiscal period. FEATURE-001-02 is the second prerequisite, because a capitalized vendor bill is the source record an asset is registered from. Ordering rule **ORD-004** makes this feature a prerequisite of FEATURE-001-07, whose Balance Sheet, Profit & Loss and close checklist consume the depreciation entries posted here. The Epic's implementation sequence places this feature in **Phase 4 — Group and sub-ledgers** alongside FEATURE-001-06 and FEATURE-001-09.

### 1.2 Problem Statement

Fixed assets are tracked in spreadsheets alongside the ledger rather than inside it, so the asset position on the Balance Sheet is a periodic transcription of a file that only one person maintains. Six consequences follow, and each recurs every month the portfolio is depreciated:

- **Depreciation is recomputed by hand every period.** A mid-sized portfolio consumes 8 to 16 hours of manual work per month: the Fixed-Asset Accountant reopens the spreadsheet, extends each schedule by one row, sums the column, and types one journal entry per asset class into the ledger. The work is repeated in full each period because nothing carries the previous period's computation forward.
- **Arithmetic errors reach the financial statements.** A mistyped useful life, a formula dragged one row short, or a salvage value omitted from the numerator produces a depreciation charge that is wrong in the Profit & Loss and an accumulated balance that is wrong in the Balance Sheet. Because the spreadsheet is also the control, the error is found when an auditor recomputes the schedule rather than when it is made.
- **Charges are missed or posted late.** With no scheduled run, the depreciation entry is posted when someone remembers it. A charge omitted from one period is either absent from that period's result or posted twice into the next, and both outcomes distort the period they land in and the comparative beside them.
- **There is no centralized history to audit.** An asset's acquisition cost, its category defaults, the method it was configured under, the revaluations and impairments applied to it, and the entries posted against it live in different files and different email threads. The External Auditor cannot walk from a Balance Sheet line to the asset that produced it, so every asset question becomes a data request.
- **Gain and loss on disposal are computed manually.** Disposal requires accumulated depreciation catch-up to the disposal date, net book value at that date, and the difference against proceeds. Each of those three figures is derived by hand, so a disposal that should recognize a `$4,500.00 USD` gain, stated to 2 decimal places at the USD rounding increment of 0.01, instead recognizes whatever the spreadsheet arrives at, and the asset is sometimes left on the books after it has left the building.
- **The register cannot be tied to the ledger.** Nothing reconciles the total net book value in the spreadsheet against Fixed Assets 1500 less Accumulated Depreciation 1590 in the general ledger. The two drift apart across periods, and by the time the difference is investigated there is no record of which period introduced it.

### 1.3 Key Capabilities

| Capability ID | Capability Description | Related Stories |
|---------------|------------------------|-----------------|
| CAP-001 | Register fixed assets with acquisition cost, acquisition date, category, useful life and salvage value | STORY-001-08-01 |
| CAP-002 | Configure depreciation methods per asset category and project the full depreciation board | STORY-001-08-02 |
| CAP-003 | Generate and post balanced depreciation journal entries on schedule, without duplication | STORY-001-08-03 |
| CAP-004 | Dispose of or sell an asset with automatic gain or loss recognition | STORY-001-08-04 |

The four capabilities are sequential across one asset's life: CAP-001 records the item and capitalizes it, CAP-002 fixes the measurement basis and projects every charge it implies, CAP-003 commits those charges to the ledger period by period, and CAP-004 derecognizes the item and books the difference between what it was carried at and what it realized.

**Depreciation methods in scope.** The three methods below are the measurement bases CAP-002 configures and the board projects. Each is stated as a formula so the board can be recomputed independently of the implementation, which is how the Fixed-Asset Accountant and the External Auditor verify it.

| Method | Basis | Notes |
|--------|-------|-------|
| Straight-line | (Cost − salvage value) ÷ useful life | Equal charge per period, with the useful life expressed in whole years or whole months. The rounding residual is absorbed in the final period so the accumulated total equals cost less salvage value exactly |
| Declining balance | Net book value × rate | Accelerated charge that falls each period, the rate commonly set at 150% or 200% of the straight-line rate. Optional switch to straight-line at the crossover period — the first period in which the straight-line charge on the remaining net book value over the remaining life exceeds the declining charge — after which the remaining periods carry an equal charge |
| Units of production | (Cost − salvage value) × units this period ÷ total estimated units | Charge varies with recorded usage. The per-unit rate is fixed at configuration, cumulative units are tracked against the total estimate, and the charge stops when cumulative units reach the estimate |

### 1.4 Success Criteria at Feature Level

| Criterion | Target | Verification Method |
|-----------|--------|---------------------|
| Straight-line board reconciles to cost | An asset registered in `US-01` with an acquisition cost of `$60,000.00 USD`, a 5-year useful life expressed as 60 months and a salvage value of `$0.00 USD` produces a 60-period **Depreciation Schedule (Depreciation Board)** whose every period reads `$1,000.00 USD` and whose accumulated total at period 60 reads `$60,000.00 USD`, each amount rounded to 2 decimal places at the USD rounding increment of 0.01, with any rounding residual absorbed in the final period so the accumulated total equals the acquisition cost less the salvage value at a difference of `0.00 USD` | Board recomputed from the straight-line formula and reconciled period by period to the asset cost, with the final-period residual asserted (C-009) |
| Rounding residual is absorbed, not dropped | An asset registered in `US-01` with an acquisition cost of `$50,000.00 USD`, a 36-month useful life and a salvage value of `$0.00 USD` charges `$1,388.89 USD` in each of periods 1 to 35 and `$1,388.85 USD` in period 36, each amount rounded to 2 decimal places at the USD rounding increment of 0.01, so the accumulated total reads `$50,000.00 USD` at a difference of `0.00 USD` from the acquisition cost | Board summed across all 36 periods and compared with the acquisition cost, with the final-period amount asserted as the residual-bearing period (SM-009, C-009) |
| Declining-balance crossover is asserted as an amount | The same `$60,000.00 USD` asset in `US-01` configured as declining balance at 40% per year over 5 annual periods with the switch to straight-line enabled charges `$24,000.00 USD`, `$14,400.00 USD` and `$8,640.00 USD` in periods 1 to 3, then switches at period 4 — the first period in which the straight-line charge on the remaining net book value of `$12,960.00 USD` over the remaining 2 periods, `$6,480.00 USD`, exceeds the declining charge of `$5,184.00 USD` — and charges `$6,480.00 USD` in each of periods 4 and 5, so the accumulated total reads `$60,000.00 USD` at a difference of `0.00 USD`, each amount rounded to 2 decimal places at the USD rounding increment of 0.01 | Board recomputed from the declining-balance formula, with the crossover period identified numerically and the accumulated total reconciled to cost (Epic Appendix C.3.5, C-009) |
| Units-of-production charge follows recorded usage | The same `$60,000.00 USD` asset in `US-01` configured as units of production over a total estimate of 100,000 units carries a per-unit rate of `$0.60 USD` and charges `$2,520.00 USD` for a period recording 4,200 units, each amount rounded to 2 decimal places at the USD rounding increment of 0.01, and the charge stops once cumulative units reach 100,000 with an accumulated total of `$60,000.00 USD` at a difference of `0.00 USD` from the acquisition cost | Per-unit rate recomputed from the formula, the period charge recomputed from recorded units, and the accumulated total reconciled to cost at cumulative-unit exhaustion (C-009) |
| Depreciation entry posts balanced | Each monthly depreciation entry for the worked asset posts in the **Miscellaneous** journal of `US-01` as debit Depreciation Expense 6500 `$1,000.00 USD` and credit Accumulated Depreciation 1590 `$1,000.00 USD`, so total debits of `$1,000.00 USD` equal total credits of `$1,000.00 USD` at a difference of `0.00 USD`, each amount rounded to 2 decimal places at the USD rounding increment of 0.01 | Posted entry inspected line by line with the debit-minus-credit difference asserted at `0.00 USD` (C-009) |
| Acquisition capitalizes balanced | Confirming the worked asset against its capitalizing vendor bill posts one entry in the **Purchase** journal of `US-01` that debits Fixed Assets 1500 `$60,000.00 USD` and credits Accounts Payable 2000 `$60,000.00 USD`, so total debits of `$60,000.00 USD` equal total credits of `$60,000.00 USD` at a difference of `0.00 USD`, each amount rounded to 2 decimal places at the USD rounding increment of 0.01, and the asset cost equals the capitalized bill line amount at a difference of `0.00 USD` | Posted entry inspected line by line with the difference asserted at `0.00 USD`, and the asset cost reconciled to the source bill line (ORD-001, FEATURE-001-02) |
| Scheduled posting automation is complete | 100% of the depreciation entries the board projects for the period are posted by the scheduled run, and the count of board periods due on or before the run date with no posted entry is 0 | Scheduled-run execution log compared line by line with the depreciation board for the same period and company (SM-008) |
| The run is idempotent | Re-running the depreciation job for a period already posted creates no second entry: the journal-entry count for the asset and the period is unchanged, and the attempt reports an Odoo validation message naming the asset, the period and the existing entry | Negative test executing the run twice over the same period, with the entry count asserted before and after and the message content asserted |
| Fixed Asset Register ties to the ledger | For company `US-01` and the as-of-date parameter 2025-12-31, the **Fixed Asset Register** presents the worked asset at an acquisition cost of `$60,000.00 USD`, accumulated depreciation of `$30,000.00 USD` and a net book value of `$30,000.00 USD`, within register totals of `$4,820,000.00 USD` cost, `$1,930,000.00 USD` accumulated depreciation and `$2,890,000.00 USD` net book value, and that net book value total equals Fixed Assets 1500 of `$4,820,000.00 USD` less Accumulated Depreciation 1590 of `$1,930,000.00 USD` at a difference of `0.00 USD`, each amount rounded to 2 decimal places at the USD rounding increment of 0.01 | Register-to-ledger tie-out worksheet per company per period, compared against the Trial Balance balances of 1500 and 1590 for the same as-of date and retained as close evidence (SM-009) |
| Disposal on sale recognizes gain balanced | Disposing the worked asset in `US-01` on 2025-12-31 at a net book value of `$30,000.00 USD` for proceeds of `$34,500.00 USD` posts one entry in the **Miscellaneous** journal that debits Bank 1010 `$34,500.00 USD` and Accumulated Depreciation 1590 `$30,000.00 USD` and credits Fixed Assets 1500 `$60,000.00 USD` and Gain/Loss on Disposal 7200 `$4,500.00 USD`, so total debits of `$64,500.00 USD` equal total credits of `$64,500.00 USD` at a difference of `0.00 USD`, each amount rounded to 2 decimal places at the USD rounding increment of 0.01, and the asset leaves the register at that as-of date | Posted disposal entry inspected line by line with the difference asserted at `0.00 USD`, the gain recomputed as proceeds less net book value, and the register re-run to confirm removal |
| Scrapping at zero proceeds recognizes loss balanced | Scrapping the same asset at a net book value of `$30,000.00 USD` for proceeds of `$0.00 USD` posts one entry in the **Miscellaneous** journal that debits Accumulated Depreciation 1590 `$30,000.00 USD` and Gain/Loss on Disposal 7200 `$30,000.00 USD` and credits Fixed Assets 1500 `$60,000.00 USD`, so total debits of `$60,000.00 USD` equal total credits of `$60,000.00 USD` at a difference of `0.00 USD`, each amount rounded to 2 decimal places at the USD rounding increment of 0.01 | Posted disposal entry inspected line by line with the difference asserted at `0.00 USD`, and the zero-proceeds case exercised as the zero-amount edge case |
| Impairment and its reversal each post balanced | An impairment of the worked asset in `US-01` at 2025-12-31 from a carrying amount of `$30,000.00 USD` to a recoverable amount of `$22,000.00 USD` posts an `$8,000.00 USD` charge as debit Impairment Loss 6510 and credit Accumulated Depreciation 1590 with total debits equal to total credits at a difference of `0.00 USD`, and a later reversal capped at the carrying amount that would have applied without the impairment posts as debit Accumulated Depreciation 1590 and credit Impairment Loss 6510 with total debits equal to total credits at a difference of `0.00 USD`, each amount rounded to 2 decimal places at the USD rounding increment of 0.01 | Both posted entries inspected line by line with the difference asserted at `0.00 USD`, and the reversal ceiling recomputed under IAS 36 (Epic Appendix C.3.5) |
| Refusal of posting into a locked period | 100% of attempts to post a depreciation, adjustment or disposal entry dated on or before the company's fiscal-year lock date are refused with an Odoo validation message naming the company and the lock date, and no journal entry is created by the refused attempt | Negative test executed per company after the lock date is applied |
| Test coverage | ≥80% for all 4 story implementations, with every board, balance, register and gain-or-loss assertion tested as an amount | Coverage tooling in the repository's configured test run (C-007, C-009) |
| Demonstrability | 4 of 4 stories demonstrated in the Odoo user interface, or through its public API, to the Finance Controller and the Product Owner | Recorded acceptance walkthrough per story |

---

## 2. User Personas

### 2.1 Persona Mapping

Every persona below is a named finance role drawn from the Epic's persona register at [§3.1](../EPIC-001-enterprise-accounting-odoo.md#31-user-personas). The five roles marked applicable take a registration, configuration, posting, measurement or review action inside the asset sub-ledger. The roles marked not applicable consume the asset balances and the depreciation charge this feature produces, and their work is specified in the features named against them.

| Persona | Role Description | Primary Use Cases | Applicable |
|---------|------------------|-------------------|------------|
| **Fixed-Asset Accountant** | Maintains the asset register and depreciation schedules | Registers an asset from its capitalizing vendor bill with acquisition cost, acquisition date, category, useful life and salvage value; assigns the asset to a category and overrides the inherited defaults where the item demands it; configures the depreciation method and reads the projected board period by period; applies revaluation and impairment and reads the recalculated remaining schedule; disposes of the asset by sale, scrapping, write-off or partial disposal and confirms the gain or loss against net book value | ☑ Yes |
| **Chief Accountant** | Owns the general ledger, the chart of accounts and the integrity of every posted entry | Approves the asset, accumulated-depreciation and depreciation-expense account assignment on each category; confirms that every depreciation, adjustment and disposal entry posts balanced through the **Miscellaneous** journal with total debits equal to total credits; aligns the depreciation period with the fiscal calendar and administers the lock date that refuses a posting into a reported period; reviews the scheduled-run log at each close before the period is locked | ☑ Yes |
| **Financial Reporting Manager** | Produces statutory and management statements for each entity and the group | Presents Fixed Assets 1500 and the contra Accumulated Depreciation 1590 on the Balance Sheet and reads net book value as the difference between them; presents the Depreciation Expense 6500 movement and the Gain/Loss on Disposal 7200 result in the Profit & Loss; carries the register-to-ledger tie-out into the close evidence pack for each entity | ☑ Yes |
| **External Auditor** | Tests balances and controls and issues the audit opinion | Ties the **Fixed Asset Register** to Fixed Assets 1500 less Accumulated Depreciation 1590 at a `0.00` difference for the as-of date under test; recomputes a depreciation board from the recorded method, cost, salvage value and useful life; reads the impairment and impairment-reversal evidence with its effective dates and its recoverable-amount basis; drills from a Balance Sheet asset line to the journal items and the asset behind it | ☑ Yes |
| **Tax Accountant** | Determines tax on transactions and files statutory returns | Reads the book depreciation charge per asset and per period as the starting point of the book-to-tax reconciliation, because the tax computation applies a jurisdiction's own rates and lives to the same cost; reads the gain or loss on disposal as a book figure the taxable result is reconciled from; confirms that the divergence between book and tax depreciation is evidenced from the register rather than reconstructed | ☑ Yes |
| Accounts Payable Clerk | Captures vendor bills, runs three-way match and prepares payment runs | Captures the capitalizing vendor bill in FEATURE-001-02 whose line is directed to Fixed Assets 1500 rather than Expense 6100; takes no action on the asset record, its board or its disposal | ☐ No |
| Accounts Receivable Specialist | Issues customer invoices, allocates receipts and manages collections | Issues the customer invoice where an asset is sold to a third party on credit rather than settled to Bank 1010; takes no action inside the asset sub-ledger | ☐ No |
| Treasury Analyst | Owns bank and cash positions and statement reconciliation | Matches the disposal proceeds credited or debited against Bank 1010 to the imported statement line in FEATURE-001-04; takes no action on the asset record | ☐ No |
| FP&A Analyst | Builds budgets and explains variances to management | Reads the projected board as forward depreciation expense and the posted charge as the actual against Depreciation Expense 6500 in FEATURE-001-09; takes no action inside the asset sub-ledger | ☐ No |
| Group Controller | Governs group accounting policy and approves the consolidated result | Approves the group depreciation and impairment policy the categories are configured to, and reads the consolidated asset position in FEATURE-001-06; does not register, depreciate or dispose of an asset | ☐ No |
| Consolidation Accountant | Executes consolidation runs, eliminations and currency translation | Translates each entity's asset and accumulated-depreciation balances into the group reporting currency in FEATURE-001-06; takes no action inside an entity's asset register | ☐ No |
| CFO / Finance Director | Executive stakeholder accountable for financial health and compliance | Consumes the capital position and the depreciation charge; confirms the open platform and edition decisions recorded in §5.2 and §5.5 | ☐ No |

### 2.2 Persona-to-Story Mapping

Each story carries exactly one primary persona in its WHO statement. Secondary personas approve, review or consume the outcome, and they are named so that the access rights derived from these stories keep the role that maintains the register apart from the role that owns the ledger: the Fixed-Asset Accountant configures the method and initiates the disposal, and the Chief Accountant approves the account assignment and the period the entry lands in.

| Story | Primary Persona | Secondary Personas |
|-------|-----------------|--------------------|
| STORY-001-08-01 Register Fixed Assets with Acquisition Detail | Fixed-Asset Accountant | Chief Accountant (asset, accumulated-depreciation and expense account assignment), Accounts Payable Clerk (the capitalizing vendor bill the asset is registered from), External Auditor (asset reference, vendor and source-bill trail) |
| STORY-001-08-02 Configure Depreciation Methods and Projected Board | Fixed-Asset Accountant | Chief Accountant (method approval per category and fiscal-period alignment), Tax Accountant (book basis the tax computation diverges from), FP&A Analyst (projected charge as forward expense), External Auditor (board recomputed from the recorded method) |
| STORY-001-08-03 Post Automated Depreciation Entries | Chief Accountant | Fixed-Asset Accountant (board review and exception handling before the run), Financial Reporting Manager (the Depreciation Expense 6500 movement in the Profit & Loss), External Auditor (balanced-entry, run-log and lock-date evidence) |
| STORY-001-08-04 Dispose of Assets with Gain or Loss Recognition | Fixed-Asset Accountant | Chief Accountant (derecognition account assignment and period), Treasury Analyst (proceeds against Bank 1010), Financial Reporting Manager (Gain/Loss on Disposal 7200 in the Profit & Loss), External Auditor (net book value, impairment and disposal evidence) |

---

## 3. Story List

### 3.1 User Stories

| Story ID | Story Title | Persona | Priority | Status | Link |
|----------|-------------|---------|----------|--------|------|
| STORY-001-08-01 | Register Fixed Assets with Acquisition Detail | Fixed-Asset Accountant | 🟠 High | Draft | [STORY-001-08-01](./FEATURE-001-08/STORY-001-08-01-register-fixed-assets.md) |
| STORY-001-08-02 | Configure Depreciation Methods and Projected Board | Fixed-Asset Accountant | 🟠 High | Draft | [STORY-001-08-02](./FEATURE-001-08/STORY-001-08-02-configure-depreciation-methods.md) |
| STORY-001-08-03 | Post Automated Depreciation Entries | Chief Accountant | 🟠 High | Draft | [STORY-001-08-03](./FEATURE-001-08/STORY-001-08-03-post-depreciation-entries.md) |
| STORY-001-08-04 | Dispose of Assets with Gain or Loss Recognition | Fixed-Asset Accountant | 🟡 Medium | Draft | [STORY-001-08-04](./FEATURE-001-08/STORY-001-08-04-dispose-assets.md) |

**Priority legend:** 🟠 High — significant finance value that consumes what the transaction backbone creates and that the statements depend on; 🟡 Medium — required for the full release, and sequenced after the periodic charge it derecognizes against.

### 3.2 Story Count Assessment

| Count | Assessment | Status |
|-------|------------|--------|
| **4 stories** | Within the mandated range of 2 to 5 stories per feature | ✓ Feature is scoped for independent delivery |

This feature carries **4 stories**, inside the 2-to-5 range recorded in the Epic's decomposition guidelines at [§5.3](../EPIC-001-enterprise-accounting-odoo.md#53-feature-and-story-decomposition-guidelines). The earlier 3-to-7 guidance carried by the feature template is superseded by that bound and is not applied here. The count is stated identically in four places, and the four must stay equal: the Story Count row in §Metadata, this assessment, the 4 rows of §3.1, and the 4 links of §9.2. The Epic's feature summary declares the same count of 4 stories for `FEATURE-001-08`.

**The count is the result of a declared migration, not a reduction in scope.** The superseded flat-layout backlog held six asset stories. The Epic's retirement map at [Appendix C](../EPIC-001-enterprise-accounting-odoo.md#appendix-c-legacy-retirement-and-migration-map) folds them into these four:

| Retired story | Destination here | Obligation the destination carries |
|---------------|------------------|------------------------------------|
| Asset registration | STORY-001-08-01 | Rehomed one for one; the acquisition entry gains an explicit debits-equal-credits assertion under C-009 |
| Depreciation configuration **+** depreciation board | STORY-001-08-02 | Merged, because a board is the visible form of a configured method. The three methods, the start-date options, the declining-balance switch to straight-line and the board's accumulated total and net book value per period are each a named criterion, and the switch-over period is asserted numerically rather than described. The board export inherits the shared export convention and C-017 |
| Automatic depreciation entries | STORY-001-08-03 | Rehomed one for one; the locked-period case is retained as this story's accounting edge case |
| Asset modification **+** asset disposal | STORY-001-08-04 | Merged, and recorded as a high-risk merge. Revaluation crediting the reserve, impairment debiting the loss, impairment reversal, remaining-schedule recalculation, the audit trail with effective dates and partial disposal are measurement events and are criteria distinct from disposal, and each adjusting entry asserts debits equal credits at a difference of `0.00` in the company currency |

Splitting further would produce stories with no accounting proof of their own — a board has nothing to project until a method is configured against a registered asset, and a scheduled run has nothing to post until a board exists. Merging further would breach the Small criterion of INVEST, because registration, measurement configuration, periodic posting and derecognition are each demonstrated against a different artifact: a confirmed asset with a capitalized cost, a projected board reconciling to that cost, a posted balanced depreciation entry, and a posted disposal entry carrying a computed gain or loss.

### 3.3 Story Dependency Ordering

Each of the four stories delivers an outcome demonstrable on its own, which keeps them Independent under INVEST. The rows below are sequencing prerequisites — the record or configuration that must already exist for the dependent story to be demonstrated — and not shared implementation.

| Story | Depends On | Notes |
|-------|-----------|-------|
| STORY-001-08-01 (Register Fixed Assets with Acquisition Detail) | None within this feature | Foundation story; the confirmed asset carrying its acquisition cost, category, useful life and salvage value is the object every later story in this feature acts on |
| STORY-001-08-02 (Configure Depreciation Methods and Projected Board) | STORY-001-08-01 | A board is projected for a registered asset: the method, the useful life and the salvage value are measured against the acquisition cost recorded at registration, so there is nothing to project before an asset exists |
| STORY-001-08-03 (Post Automated Depreciation Entries) | STORY-001-08-02 | Postings follow the board: the scheduled run reads the projected period, its amount and its due date from the board, so the entry it posts has no source until the board is projected |
| STORY-001-08-04 (Dispose of Assets with Gain or Loss Recognition) | STORY-001-08-03 | Disposal removes cost and the accumulated depreciation already posted: net book value at the disposal date is the acquisition cost less the posted accumulated charge plus any catch-up to that date, so the gain or loss cannot be computed before depreciation posts |

Outside this feature, FEATURE-001-01 is a prerequisite of every posting story here under ORD-001 and FEATURE-001-02 supplies the capitalizing vendor bill an asset is registered from; both are recorded in §7.1.

### 3.4 Recommended Implementation Order

```text
1. STORY-001-08-01  Register Fixed Assets with Acquisition Detail
   Foundation: acquisition cost, acquisition date, category, useful life and salvage value
   on a confirmed asset, with a unique asset reference, the vendor and source vendor bill
   retained against it, and the acquisition capitalized as debit Fixed Assets 1500 /
   credit Accounts Payable 2000 in the Purchase journal, total debits equal total credits
        |
        v
2. STORY-001-08-02  Configure Depreciation Methods and Projected Board
   Measurement: straight-line, declining balance or units of production configured on the
   asset or inherited from its category, with the full Depreciation Schedule
   (Depreciation Board) projected across the useful life — period charge, accumulated
   total and net book value per period — reconciling to cost less salvage value
        |
        v
3. STORY-001-08-03  Post Automated Depreciation Entries
   Ledger: the scheduled run posts one balanced entry per due board period in the
   Miscellaneous journal — debit Depreciation Expense 6500, credit Accumulated
   Depreciation 1590, total debits equal total credits — idempotently, with a per-batch
   log and a refusal for a locked period or an incomplete configuration
        |
        v
4. STORY-001-08-04  Dispose of Assets with Gain or Loss Recognition
   Derecognition and measurement events: revaluation, impairment and impairment reversal
   with recalculated remaining schedules, then disposal by sale, scrapping, write-off or
   partial disposal — cost and accumulated depreciation removed, proceeds recorded and
   Gain/Loss on Disposal 7200 booked, total debits equal total credits
```

The four steps are strictly sequential because each acts on the artifact the previous step produced: an asset is registered before it is measured, measured before it is charged, and charged before the charge can be reversed out on derecognition. The whole feature is a prerequisite of FEATURE-001-07 under ORD-004, which is why the Epic sequences it in Phase 4 — Group and sub-ledgers, after the transaction backbone has produced the capitalizing bills this register is built from.

---

## 4. Acceptance Criteria Summary

### 4.1 Feature-Level Acceptance Criteria

These are feature-level gates. The Given/When/Then acceptance criteria live in the four story files, where each is written against one workflow with 4 to 8 criteria and the coverage distribution the Epic requires.

The feature is considered complete when:

- [ ] All 4 stories within this feature have status "Done"
- [ ] All 4 stories achieve minimum 80% test coverage (C-007)
- [ ] Feature-level integration tests pass, with every board, balance, register and gain-or-loss assertion tested as an amount rather than inspected by eye (C-009)
- [ ] Each of the 4 stories has been demonstrated in the Odoo user interface, or through its public API, to the Finance Controller and the Product Owner, and the walkthrough is recorded against the story
- [ ] **The worked asset capitalizes balanced.** In `US-01`, confirming an asset registered from its capitalizing vendor bill at an acquisition cost of `$60,000.00 USD` posts one entry in the **Purchase** journal that debits Fixed Assets 1500 `$60,000.00 USD` and credits Accounts Payable 2000 `$60,000.00 USD`, so total debits of `$60,000.00 USD` equal total credits of `$60,000.00 USD` at a difference of `0.00 USD`, each amount rounded to 2 decimal places at the USD rounding increment of 0.01, and the asset cost equals the capitalized bill line amount at a difference of `0.00 USD`
- [ ] Every registered asset carries an acquisition cost, an acquisition date, a category, a useful life and a salvage value, and the count of confirmed assets missing any one of the five is 0
- [ ] **Account assignment is validated before confirmation.** Confirmation is refused with an Odoo validation message naming the failing requirement when the asset account is not of the fixed-asset type, the depreciation expense account is not of the `expense_depreciation` type, the accumulated-depreciation account is not configured as a contra-asset against Fixed Assets 1500, any of the three belongs to a company other than the asset's own, or any of the three is archived; the asset stays in Draft and no journal entry is created by the refused attempt
- [ ] **Each asset carries a unique reference from its company's sequence.** The reference is generated on confirmation from the asset reference sequence resolved with the asset's company, reads `FA/00001` for the first asset confirmed in that company and advances by 1 for each subsequent asset of the same company, and the count of assets sharing a reference within one company is 0
- [ ] The vendor and the source vendor bill are retained against the asset, and the bill line amount is compared with the acquisition cost with the difference asserted at `0.00` in the company currency, so the capitalization trail from the Balance Sheet line back to the vendor document is readable without a data request
- [ ] **Category defaults are inherited and overridable, and never retroactive.** An asset assigned to a category inherits that category's depreciation method, useful life, salvage basis, start-date option, declining-balance rate and the three accounts; each inherited value is overridable on the individual asset with the override recorded; and a later change to the category leaves assets already configured under it unchanged, proved by re-reading the board of an asset configured before the change
- [ ] **The straight-line board reconciles to cost.** The worked `$60,000.00 USD` asset in `US-01` with a 60-month useful life and a `$0.00 USD` salvage value projects 60 board periods each reading `$1,000.00 USD`, an accumulated total at period 60 of `$60,000.00 USD` and a net book value at period 60 of `$0.00 USD`, each amount rounded to 2 decimal places at the USD rounding increment of 0.01, so the accumulated total equals cost less salvage value at a difference of `0.00 USD`
- [ ] **The rounding residual is absorbed in the final period.** A `$50,000.00 USD` asset in `US-01` over 36 months with a `$0.00 USD` salvage value charges `$1,388.89 USD` in each of periods 1 to 35 and `$1,388.85 USD` in period 36, each amount rounded to 2 decimal places at the USD rounding increment of 0.01, so the accumulated total reads `$50,000.00 USD` at a difference of `0.00 USD` from cost and no fraction of a cent is lost or double-counted
- [ ] **The declining-balance switch to straight-line is asserted numerically.** The worked `$60,000.00 USD` asset in `US-01` at 40% per year over 5 annual periods with the switch enabled charges `$24,000.00 USD`, `$14,400.00 USD` and `$8,640.00 USD` in periods 1 to 3, switches at period 4 because the straight-line charge on the remaining net book value of `$12,960.00 USD` over 2 remaining periods, `$6,480.00 USD`, exceeds the declining charge of `$5,184.00 USD`, and charges `$6,480.00 USD` in each of periods 4 and 5, giving an accumulated total of `$60,000.00 USD` at a difference of `0.00 USD` from cost, each amount rounded to 2 decimal places at the USD rounding increment of 0.01
- [ ] **The units-of-production charge follows recorded usage.** The worked `$60,000.00 USD` asset in `US-01` over a total estimate of 100,000 units carries a per-unit rate of `$0.60 USD`, charges `$2,520.00 USD` for a period recording 4,200 units, tracks cumulative units against the estimate, and stops charging once cumulative units reach 100,000 with an accumulated total of `$60,000.00 USD` at a difference of `0.00 USD` from cost, each amount rounded to 2 decimal places at the USD rounding increment of 0.01
- [ ] **A mid-period acquisition is prorated and the board extends by one period.** The worked `$60,000.00 USD` asset in `US-01` acquired 2025-03-14 under the acquisition-date start option charges `$580.65 USD` for the 18 days from 2025-03-14 to 2025-03-31 of a 31-day period, `$1,000.00 USD` in each of periods 2 to 60 and `$419.35 USD` in period 61, each amount rounded to 2 decimal places at the USD rounding increment of 0.01, so the accumulated total reads `$60,000.00 USD` at a difference of `0.00 USD` from cost
- [ ] The four start-date options are each demonstrated against the same acquisition date — the acquisition date with proration, the first day of the acquisition month, the first day of the following month, and a manual date on or after the acquisition date — and a manual date earlier than the acquisition date is refused with an Odoo validation message naming both dates, with no board recomputed by the refused attempt
- [ ] **Depreciation configuration is validated as a set.** Saving the configuration is refused with an Odoo validation message naming the failing requirement when the method is unset, the useful life is not greater than zero for straight-line or declining balance, the declining-balance rate falls outside the range above 0% to 100%, the total estimated units is not greater than zero for units of production, the salvage value is negative, or the salvage value exceeds the acquisition cost; no board is projected until the set is complete
- [ ] **The Depreciation Schedule (Depreciation Board) presents four values per period and reconciles across them.** Each board period presents its period number and date, its depreciation charge, its accumulated depreciation as the running sum of all charges to that period, and its net book value as acquisition cost less that accumulated total, with the identity `cost − accumulated = net book value` asserted at a difference of `0.00` in the company currency on every period, and the net book value of the final period equal to the salvage value
- [ ] Each board period is marked Posted or Pending against the existence of a posted depreciation entry for that asset and period, the posted rows carry the reference of the entry that posted them, and the board drills from a posted row to the journal items behind it with the filters preserved
- [ ] The board filters and sorts by date range and by fiscal period, and it exports to PDF and to XLSX with every exported cell neutralized against formula injection so a cell value beginning with `=`, `+`, `-`, `@`, a tab or a carriage return is rendered as text (C-017)
- [ ] **Each depreciation entry posts balanced.** A monthly depreciation entry for the worked asset posts in the **Miscellaneous** journal of `US-01` as debit Depreciation Expense 6500 `$1,000.00 USD` and credit Accumulated Depreciation 1590 `$1,000.00 USD`, so total debits of `$1,000.00 USD` equal total credits of `$1,000.00 USD` at a difference of `0.00 USD`, each amount rounded to 2 decimal places at the USD rounding increment of 0.01, and the entry is dated on the board period date and references the asset and the period
- [ ] **Scheduled posting automation is complete.** 100% of the board periods due on or before the run date are posted by the scheduled run, the count of due periods with no posted entry is 0, and the run writes a per-batch log recording the assets processed, the entries created, the amount posted per company and every asset it skipped with the reason (SM-008)
- [ ] **The run is idempotent.** Re-running the depreciation job over a period already posted creates no second entry: the journal-entry count for the asset and the period is identical before and after, and the attempt reports an Odoo validation message naming the asset, the period and the existing entry
- [ ] **Concurrent runs do not double-post.** Two runs initiated over the same company and period produce one entry per due board period in total, proved by a concurrency test that asserts the entry count and the accumulated total on the board are unchanged by the second run
- [ ] The draft-versus-automatic posting option is demonstrated in both settings: under the draft setting the run creates the entry unposted for the Chief Accountant to review and post, and under the automatic setting the run posts it, with both paths asserting total debits equal total credits at a difference of `0.00` in the company currency
- [ ] **A fully depreciated asset receives no further charge.** An asset whose accumulated depreciation equals cost less salvage value carries a net book value equal to its salvage value, and the count of depreciation entries the run posts against it in any later period is 0
- [ ] **A zero-cost asset is refused.** Confirming an asset with an acquisition cost of `$0.00 USD`, stated to 2 decimal places at the USD rounding increment of 0.01, is refused with an Odoo validation message naming the asset and the cost, so no board is projected and no journal entry is created
- [ ] **An asset in a currency other than the group reporting currency rounds to its own currency.** A `£25,000.00 GBP` asset in `GB-01` over 36 months with a `£0.00 GBP` salvage value charges `£694.44 GBP` in each of periods 1 to 35 and `£694.60 GBP` in period 36, each amount rounded to 2 decimal places at the GBP rounding increment of 0.01, and each entry balances in the functional currency of `GB-01` at a difference of `0.00 GBP`
- [ ] **Revaluation credits the reserve and recalculates the remaining schedule.** Revaluing the worked asset in `US-01` from a carrying amount of `$30,000.00 USD` to `$36,000.00 USD` posts one entry in the **Miscellaneous** journal that debits Fixed Assets 1500 `$6,000.00 USD` and credits Revaluation Reserve 3200 `$6,000.00 USD`, so total debits of `$6,000.00 USD` equal total credits of `$6,000.00 USD` at a difference of `0.00 USD`, and the remaining 30 board periods are recalculated to `$1,200.00 USD` each, each amount rounded to 2 decimal places at the USD rounding increment of 0.01
- [ ] **Impairment debits the loss and recalculates the remaining schedule.** Impairing the worked asset in `US-01` at 2025-12-31 from a carrying amount of `$30,000.00 USD` to a recoverable amount of `$22,000.00 USD` posts one entry in the **Miscellaneous** journal that debits Impairment Loss 6510 `$8,000.00 USD` and credits Accumulated Depreciation 1590 `$8,000.00 USD`, so total debits of `$8,000.00 USD` equal total credits of `$8,000.00 USD` at a difference of `0.00 USD`, and the remaining 30 board periods are recalculated to `$733.33 USD` for periods 1 to 29 and `$733.43 USD` for period 30, giving a recalculated accumulated total of `$22,000.00 USD` at a difference of `0.00 USD` from the recoverable amount, each amount rounded to 2 decimal places at the USD rounding increment of 0.01
- [ ] **Impairment reversal is capped and posts balanced.** Where the recoverable amount of the impaired asset later recovers to `$27,000.00 USD` while its impaired carrying amount stands at `$20,533.34 USD` and the carrying amount it would have held without the impairment stands at `$28,000.00 USD`, the reversal is limited to the lower of the two ceilings and posts one entry in the **Miscellaneous** journal that debits Accumulated Depreciation 1590 `$6,466.66 USD` and credits Impairment Loss 6510 `$6,466.66 USD`, so total debits of `$6,466.66 USD` equal total credits of `$6,466.66 USD` at a difference of `0.00 USD`, each amount rounded to 2 decimal places at the USD rounding increment of 0.01
- [ ] Each revaluation, impairment and impairment reversal is recorded with its effective date, its basis and its author, so the measurement history of an asset is readable in date order and the External Auditor reads the recoverable-amount basis behind an impairment without a data request
- [ ] **Disposal on sale recognizes the gain balanced.** Disposing the worked asset in `US-01` on 2025-12-31 at a net book value of `$30,000.00 USD` for proceeds of `$34,500.00 USD` posts one entry in the **Miscellaneous** journal that debits Bank 1010 `$34,500.00 USD` and Accumulated Depreciation 1590 `$30,000.00 USD` and credits Fixed Assets 1500 `$60,000.00 USD` and Gain/Loss on Disposal 7200 `$4,500.00 USD`, so total debits of `$64,500.00 USD` equal total credits of `$64,500.00 USD` at a difference of `0.00 USD`, each amount rounded to 2 decimal places at the USD rounding increment of 0.01
- [ ] **Scrapping and write-off at zero proceeds recognize the loss balanced.** Scrapping or writing off the same asset at a net book value of `$30,000.00 USD` for proceeds of `$0.00 USD` posts one entry in the **Miscellaneous** journal that debits Accumulated Depreciation 1590 `$30,000.00 USD` and Gain/Loss on Disposal 7200 `$30,000.00 USD` and credits Fixed Assets 1500 `$60,000.00 USD`, so total debits of `$60,000.00 USD` equal total credits of `$60,000.00 USD` at a difference of `0.00 USD`, each amount rounded to 2 decimal places at the USD rounding increment of 0.01
- [ ] **Depreciation is caught up to the disposal date before the gain or loss is computed.** Where the disposal date falls after the last posted board period, the charge for the part-period to the disposal date is posted first as debit Depreciation Expense 6500 and credit Accumulated Depreciation 1590 with total debits equal to total credits at a difference of `0.00` in the company currency, and the net book value the gain or loss is measured against is the acquisition cost less the accumulated total including that catch-up
- [ ] **Partial disposal removes its share and leaves a proved remainder.** Disposing 1 of the 4 identical units carried in the worked `$60,000.00 USD` asset in `US-01` for proceeds of `$9,000.00 USD` removes a cost of `$15,000.00 USD` and accumulated depreciation of `$7,500.00 USD`, posts one entry in the **Miscellaneous** journal that debits Bank 1010 `$9,000.00 USD` and Accumulated Depreciation 1590 `$7,500.00 USD` and credits Fixed Assets 1500 `$15,000.00 USD` and Gain/Loss on Disposal 7200 `$1,500.00 USD`, so total debits of `$16,500.00 USD` equal total credits of `$16,500.00 USD` at a difference of `0.00 USD`, and the remaining asset carries a cost of `$45,000.00 USD`, accumulated depreciation of `$22,500.00 USD`, a net book value of `$22,500.00 USD` and a recalculated period charge of `$750.00 USD`, each amount rounded to 2 decimal places at the USD rounding increment of 0.01
- [ ] **Disposal is validated before it posts.** Disposal is refused with an Odoo validation message naming the failing requirement when the disposal date precedes the acquisition date, the asset is not in the running state, the proceeds amount is negative, a partial-disposal quantity is not greater than zero or exceeds the quantity remaining, or any of the asset, accumulated-depreciation, proceeds and gain-or-loss accounts is unconfigured; no journal entry is created by the refused attempt
- [ ] **A posting into a locked period is refused.** An attempt to post a depreciation, revaluation, impairment or disposal entry dated on or before the fiscal-year lock date of the affected company is refused with an Odoo validation message naming the company and the lock date, and no journal entry is created by the refused attempt
- [ ] **The Fixed Asset Register ties to the ledger.** For company `US-01` and the as-of-date parameter 2025-12-31, the register presents the worked asset at a cost of `$60,000.00 USD`, accumulated depreciation of `$30,000.00 USD` and a net book value of `$30,000.00 USD`, and register totals of `$4,820,000.00 USD` cost, `$1,930,000.00 USD` accumulated depreciation and `$2,890,000.00 USD` net book value, so the net book value total equals Fixed Assets 1500 of `$4,820,000.00 USD` less Accumulated Depreciation 1590 of `$1,930,000.00 USD` at a difference of `0.00 USD`, each amount rounded to 2 decimal places at the USD rounding increment of 0.01 (SM-009)
- [ ] The register is produced per company, so the register of `US-01` presents no asset belonging to `NL-01` or `GB-01`, and a group view of the three registers names each contributing company beside its own cost, accumulated-depreciation and net book value totals
- [ ] The register drills from an asset line to its board and from a board period to the journal items behind it, and it exports to PDF and to XLSX under the same formula-injection neutralization as the board (C-017)
- [ ] **The Balance Sheet presents the asset position from the same figures.** For `US-01` and the as-of-date parameter 2025-12-31, the Balance Sheet presents Fixed Assets 1500 at `$4,820,000.00 USD` and the contra Accumulated Depreciation 1590 at `$1,930,000.00 USD`, a net `$2,890,000.00 USD` equal to the register net book value total at a difference of `0.00 USD`, each amount rounded to 2 decimal places at the USD rounding increment of 0.01
- [ ] The book depreciation charge per asset and per period, and the gain or loss on disposal, are readable from the register and the board as the starting point of the book-to-tax reconciliation, so the divergence between book and tax depreciation is evidenced from the sub-ledger rather than reconstructed by the Tax Accountant
- [ ] **A run-time report parameter that is hostile is rejected.** A malformed as-of date, an out-of-range date, an over-long filter value, a filter value carrying a formula-injection payload and a filter value carrying a search-domain payload are each rejected with an error naming the parameter and the check that failed, disclosing no stack trace or file-system path, with no journal entry created and the service still available (C-015, C-019, C-020, C-022)
- [ ] The posted Depreciation Expense 6500 movement, the Fixed Assets 1500 and Accumulated Depreciation 1590 balances, the Gain/Loss on Disposal 7200 result and the projected board are handed to FEATURE-001-07 and FEATURE-001-09 as the posted data their stories consume, and the hand-over is recorded against ORD-004

### 4.2 Cross-Cutting Concerns

Every story in this feature inherits the criteria below from the Epic's constraint set.

| Concern | Acceptance Criterion |
|---------|----------------------|
| License | New modules are distributed under an AGPL-3.0 compatible licence, integration with `account` and `analytic` respects their LGPL-3 licence, and extension of the present `account_asset_management` add-on respects its AGPL-3 licence (C-001, C-002) |
| Dependencies | Every declared module dependency exists in the platform configuration confirmed by DEC-002, and delivered code stays consumable by the OCA add-on ecosystem including the `OCA/account-financial-tools` asset add-ons (C-003, C-004) |
| Coding Standards | Python follows Odoo and OCA standards including PEP 8, and static analysis passes with the repository's configured tooling in `ruff.toml` (C-005, C-006) |
| Test Coverage | Each story achieves minimum 80% test coverage, and each acceptance test is traceable to one Given/When/Then criterion (C-007, C-008) |
| Documentation | Public methods and models are documented with docstrings, and the depreciation formula per method, the declining-balance switch rule, the rounding-residual placement and the impairment-reversal ceiling are recorded alongside the code that computes them |
| Security | Access rights are defined per finance role and verified by an access-rights test matrix: the Fixed-Asset Accountant registers assets, configures methods, reads boards and initiates revaluation, impairment and disposal; the Chief Accountant approves account assignment, posts the depreciation and disposal entries and administers the lock date; the Financial Reporting Manager and the Tax Accountant hold read access to the register, the board and the posted charge without altering an asset; the External Auditor holds read-only access to assets, boards, measurement history and posted entries; and no role reads, depreciates or disposes of an asset in a company outside its allowed companies (C-014) |
| Segregation of duties | The role that initiates a disposal or an impairment and the role that posts the resulting entry are distinct, and a test proves that the initiating role cannot post the entry and that no role can alter an asset's acquisition cost after the acquisition entry is posted (C-014) |
| Multi-company isolation | Every criterion that touches more than one company names the company whose books are affected — `US-01`, `NL-01` or `GB-01` — an asset is held against exactly one company, and a test proves that a role restricted to one company can neither read nor depreciate another company's assets (C-014, D-007) |
| Build on the existing models | Acquisition, depreciation, revaluation, impairment and disposal entries are expressed on `account.move` and `account.move.line` in the company's **Miscellaneous** and **Purchase** journals rather than on a parallel posting structure, and account resolution reads `account.account` rather than duplicating the chart (C-012) |
| Untrusted input | The as-of dates, date ranges, filter values and grouping selections supplied to the register and the board at run time cross the trust boundary, as does any legacy asset extract loaded at migration: file type and size are checked against an allowlist at the ingestion boundary, values are validated before use, data access is expressed through the ORM or parameterized SQL with no concatenated search domain, exported cell values are neutralized against formula injection, a rejected value returns a named error disclosing no internal detail, and a hostile-input test proves the rejection with no journal entry created and the service still available (C-015, C-017, C-019, C-020, C-022) |
| Rendered text | Asset names, asset references, category names, vendor names and disposal memo text are sanitized and context-encoded before they are rendered into a PDF or XLSX register, a board row or a run-log entry, and templates render such values as escaped text rather than as raw markup (C-018) |
| Document parsing | No story in this feature parses an XML document, so the external-entity and entity-expansion surface does not arise here; if the legacy asset extract loaded at migration is implemented against a structured document format rather than a tabular extract, that path inherits C-016 in full — DTD processing and external-entity resolution disabled, entity expansion bounded, and schema validation before any field is read (C-016) |
| Credentials | No story in this feature holds an endpoint credential, API key or signing certificate; where the scheduled run notifies a recipient through an outbound mail server, its credentials are held outside module source and outside version control under the Epic's secret-handling rule (C-021) |
| Audit trail | Asset registration and confirmation, the category and method assignment with any override, each revaluation, impairment and impairment reversal with its effective date and basis, each posted depreciation entry, and the disposal with its method and proceeds are recorded with their author and timestamp and are readable by the External Auditor without a data request |
| Performance | The targets in §4.4 are met on a portfolio of 10,000 assets, a board of 600 periods and a scheduled run covering the whole portfolio |

### 4.3 Integration Requirements

| Integration Point | Requirement | Verification |
|-------------------|-------------|--------------|
| `account.move` | Write: the acquisition entry in the **Purchase** journal and the depreciation, revaluation, impairment and disposal entries in the **Miscellaneous** journal are created as `entry` documents, dated on the board period date or the event date, referencing the asset and the period. Read: the capitalizing vendor bill that is the asset's source record | Document-type, journal, date and reference assertions per created entry, with the asset cost reconciled to the source bill line at a difference of `0.00` in the company currency |
| `account.move.line` | Write: each depreciation entry produces one debit line on Depreciation Expense 6500 and one credit line on Accumulated Depreciation 1590, and each disposal entry produces the cost-removal, accumulated-depreciation-removal, proceeds and gain-or-loss lines; every entry posts only when total debits equal total credits at a difference of `0.00` in the company currency | Posted entry inspected line by line with the debit-minus-credit difference asserted at `0.00` in the company currency (C-009) |
| `account.account` | Read: Fixed Assets 1500 as the asset account, Accumulated Depreciation 1590 as the contra-asset, Depreciation Expense 6500 as the charge account, Gain/Loss on Disposal 7200 as the derecognition result account, Impairment Loss 6510 as the impairment charge account, Revaluation Reserve 3200 as the revaluation surplus account, and Accounts Payable 2000 and Bank 1010 as the acquisition and proceeds counterparts — each resolved by code and by account type on the asset's own company | Account resolution asserted per posted line, with the account type checked against the role the line plays and the company checked against the asset's company |
| `account.journal` | Read: the **Miscellaneous** journal of the asset's company carries the depreciation, revaluation, impairment and disposal entries, and the **Purchase** journal carries the capitalizing acquisition, each with its own sequence and default accounts as configured in FEATURE-001-01 | Journal assignment asserted per posted entry, with the journal type checked against the entry's role |
| Scheduled-action mechanism | Extend: the periodic depreciation run selects the board periods due on or before the run date across the assets of each company, creates one entry per due period, and is idempotent so a repeat over the same period creates no second entry; it writes a per-batch log and it takes a lock that prevents two concurrent runs from double-posting | Timed run against a seeded portfolio, executed twice, with the entry count asserted identical after the second execution and the log inspected for the assets processed, the amount posted per company and every skip reason (SM-008) |
| `ir.sequence` | Read: the asset reference sequence resolved with the asset's company generates `FA/00001` for the first asset confirmed in that company and advances by 1 for each subsequent asset of the same company | Reference generation asserted per confirmed asset, with the count of assets sharing a reference within one company asserted at 0 |
| `res.company` | Read: the company that owns the asset, its functional currency and decimal precision, and the fiscal-year lock date that refuses a posting into a reported period | Per-company posting test after the lock date is applied, asserting refusal with the company and the lock date named, plus the isolation test proving one company's assets are invisible to a role restricted to another |
| `res.currency` | Read: the rounding increment and decimal precision every cost, charge, accumulated total, net book value, proceeds and gain-or-loss amount is rounded to | Board and disposal assertions repeated for a USD asset in `US-01`, a EUR asset in `NL-01` and a GBP asset in `GB-01` |
| `analytic` | Optional: the analytic distribution carried on the depreciation charge, so a period's charge is attributable to a cost centre or a project without a parallel dimension model (C-013) | Analytic line creation asserted on a posted depreciation entry, with the analytic amounts summing to the entry's charge at a difference of `0.00` in the company currency |
| FEATURE-001-02 Accounts Payable & Vendor Bills | A capitalized vendor bill is the source record of an asset: its line is directed to Fixed Assets 1500 rather than Expense 6100, and the asset traces back to the bill that created it | Asset-creation test from a capitalized bill, asserting that the asset cost equals the capitalized bill line amount at a difference of `0.00` in the company currency |
| FEATURE-001-07 Financial Reporting & Period Close | Posted depreciation supplies the Depreciation Expense 6500 movement in the Profit & Loss, the Fixed Assets 1500 and contra Accumulated Depreciation 1590 balances give the net book value presented on the Balance Sheet, the Gain/Loss on Disposal 7200 result appears in the Profit & Loss, and the register-to-ledger tie-out is one of the close checklist's evidence items; that feature owns the shared export and drill-down convention the register and the board inherit rather than redefine | Balance Sheet and Profit & Loss section totals reconciled to the register and the board for the same as-of date and company at a difference of `0.00` in the company currency (ORD-004) |
| FEATURE-001-09 Budgeting & Variance Analysis | The posted charge on Depreciation Expense 6500 is the actual side of capital-expenditure budget-versus-actual, and the projected board is the forward charge a budget is planned against | Actual amount for Depreciation Expense 6500 reconciled to the depreciation board for the same period, company and analytic distribution at a difference of `0.00` in the company currency |
| FEATURE-001-06 Multi-Company & Intercompany Consolidation | Asset registers are held per legal entity and translated into the group reporting currency for the consolidated position, and an asset transferred between entities is derecognized in one register and recognized in the other rather than shared | Group asset position compared against the sum of the entity registers at a difference of at most `0.02` in the group reporting currency from translation rounding |
| FEATURE-001-04 Bank Reconciliation & Cash Management | Disposal proceeds debited to Bank 1010 appear as a bank movement matched against the imported statement line, so the proceeds are cleared in the ledger rather than tracked outside it | Statement-line reconciliation test executed against the proceeds line of a posted disposal |

### 4.4 Performance Requirements

| Metric | Requirement | Measurement Method |
|--------|-------------|--------------------|
| Asset operations across the portfolio | Under 5 seconds for any single registration, configuration, revaluation, impairment or disposal operation in a portfolio of up to 10,000 assets | Timed operation on a seeded `US-01` portfolio of 10,000 assets, measured from submission to the record reaching its new state |
| Depreciation board render | Under 5 seconds to render a single asset's board of 600 periods, the maximum implied by a 50-year useful life measured monthly | Timed board load for a seeded 600-period asset, measured from request to the last period being readable |
| Depreciation board export | Under 5 seconds to export a single asset's 600-period board to XLSX with formula-injection neutralization applied to every cell | Timed export of the same seeded 600-period asset, with the exported cell count asserted at 600 data rows |
| Board filter and sort | Under 1 second to apply a date-range or fiscal-period filter, or a sort, to a 600-period board | Timed filter and sort operations on the same seeded asset |
| Scheduled depreciation run | Under 10 minutes to post the due entries for 10,000 assets, with a per-batch log written as the run proceeds | Timed scheduled-action run against the seeded 10,000-asset portfolio, with the posted entry count reconciled to the due board periods and the log inspected for batch progress (SM-008) |
| Fixed Asset Register render | Under 30 seconds for a 10,000-asset register at a fixed as-of date, including the cost, accumulated-depreciation and net book value totals | Timed register run for `US-01` as at 2025-12-31 on the seeded portfolio, with the net book value total tied to Fixed Assets 1500 less Accumulated Depreciation 1590 at a difference of `0.00 USD` (SM-009) |
| Disposal gain-or-loss computation | Under 2 seconds per disposal, including depreciation catch-up to the disposal date and the net book value it is measured against | Timed disposal on a seeded asset whose disposal date falls after its last posted board period |
| Register-to-ledger tie-out | Under 60 seconds to produce the tie-out worksheet for a 10,000-asset portfolio at a period end | Timed tie-out run comparing the register totals with the Trial Balance balances of 1500 and 1590 for the same as-of date |

---

## 5. Constraints (Inherited from Epic)

The constraint identifiers below are the Epic's own. They are restated here in the terms of this feature rather than renumbered, so a reviewer reads one constraint set across the whole tree.

### 5.1 License Requirements

| Constraint | Requirement | Rationale |
|------------|-------------|-----------|
| **C-001 — Licence compatibility** | New modules delivering the asset register, the depreciation board, the scheduled posting run, the measurement events and the register-to-ledger tie-out are distributed under an AGPL-3.0 compatible licence | Matches the licence of the Community-edition accounting add-ons already present in this repository, including `account_asset_management` at AGPL-3, so the delivered asset layer stays redistributable and contributable |
| **C-002 — Existing licence respected** | Extension of `account` and `analytic` respects their LGPL-3 licence, declared in `addons/account/__manifest__.py` and `addons/analytic/__manifest__.py`, and extension of `account_asset_management` respects its AGPL-3 licence declared in `addons/account_asset_management/__manifest__.py` | `account.move`, `account.move.line`, `account.account`, `account.journal` and the analytic models are LGPL-3 code, while the present asset add-on is AGPL-3. Derived and dependent code must remain licence-compatible with both, and an AGPL-3 extension of an LGPL-3 module is checked before it is written |

**Acceptance Criterion:** every module delivered by this feature declares an AGPL-3.0 compatible licence in its manifest, and no derived work misstates the licence of the `account`, `analytic` or `account_asset_management` code it extends.

### 5.2 Dependency and Edition Considerations

| Constraint | Requirement | Rationale |
|------------|-------------|-----------|
| **C-003 — Edition source is an open decision that gates this feature** | The edition that supplies the Enterprise-only fixed-asset capability is **not decided**. It is recorded as DEC-002 in the Epic's open decisions register, owned by the CFO / Finance Director with the Group Controller, and it must be confirmed before this feature enters development | `account_asset` is **absent from `addons/`** in this repository and is an Enterprise module. This is recorded as a platform fact, not as a prohibition: the earlier backlog forbade the module by name, and that blanket restriction is superseded. Two paths carry the capability — an Odoo Enterprise subscription, which supplies the asset register, the depreciation board and the disposal workflow as supported product, or the OCA route with the `OCA/account-financial-tools` asset add-ons alongside the present `account_asset_management` add-on, with bespoke development for the residual gap. The paths differ in licensing, cost and implementation approach, so the choice is confirmed with stakeholders rather than presumed |
| **C-004 — OCA ecosystem compatibility** | Whichever edition path is confirmed, the asset records, the categories, the projected board, the posted charge and the measurement history delivered here stay consumable by OCA add-ons | Preserves the option to adopt an OCA asset, batch-compute or disposal add-on, and keeps the present `account_asset_management` add-on usable against the same accounts, journals and analytic dimensions without restating this feature's records |
| **Present add-on is credited, not assumed complete** | The capability already delivered by `account_asset_management` — the asset, asset-category and depreciation-line models, the three depreciation methods, the depreciation board, scheduled posting and revaluation — is credited under D-003 and confirmed against each story's acceptance criteria before any bespoke build is authorized | D-003 records the residual gap for this feature as asset disposal with gain or loss on sale, scrapping and write-off, impairment and impairment reversal, partial disposal, and the register-to-ledger tie-out at a `0.00` difference. Building what is already present would split the asset record in two and let a board and a posted charge diverge |
| **Absent module that bounds the residual scope** | Because `account_asset` is absent, the register presentation, the board view and the tie-out worksheet are specified here by their columns, their as-of-date parameter and their tie-out to Fixed Assets 1500 less Accumulated Depreciation 1590 rather than against one engine's internal structure | Keeps the acceptance criteria valid under either edition path, so a confirmed DEC-002 changes how a register is rendered without changing what it must prove |

**Acceptance Criterion:** DEC-002 is confirmed and recorded before development starts; no module delivered by this feature declares a dependency on a module absent from the configuration DEC-002 confirms; the register presentation and the board are demonstrated under each candidate edition path; and the model-and-report coverage of `account_asset_management` is compared against the four stories' criteria, with the comparison retained as the evidence that confirms or narrows the residual gap.

### 5.3 Coding Standards

| Constraint | Requirement | Rationale |
|------------|-------------|-----------|
| **C-005 — Odoo and OCA standards** | Python follows Odoo and OCA module guidelines, including PEP 8 | Keeps the delivered code reviewable by the Odoo community and eligible for OCA contribution |
| **C-006 — Static analysis** | Static analysis passes with the repository's configured tooling; `ruff.toml` at the repository root defines the lint configuration in force | A defect in the depreciation formula or the posting path propagates to every asset measured under it and to every period it charges, so it is caught before review rather than at the tie-out |
| **C-012 — Build on the existing models** | Acquisition, depreciation, revaluation, impairment and disposal entries are expressed on `account.move` and `account.move.line` in the company's existing journals, and account resolution reads `account.account`, rather than on a parallel posting or chart structure | Preserves one ledger and one audit trail, so a register net book value and the Fixed Assets 1500 less Accumulated Depreciation 1590 balance cannot disagree by construction |
| **C-013 — Analytic layer, not a parallel one** | Where the depreciation charge carries a cost-centre or project dimension, it is expressed on `account.analytic.account` and `account.analytic.plan` through the analytic distribution on the journal item | The analytic layer already provides the multi-dimensional allocation FEATURE-001-09 reads as the actual side of capital-expenditure budget-versus-actual; a parallel dimension would let the budget dimension and the posted dimension diverge |
| **C-019 — Data access discipline** | All data access in registration, board projection, scheduled posting, measurement events, disposal and reporting is expressed through the Odoo ORM or parameterized SQL, with no string-concatenated query construction, no shell invocation, and no file path derived from an uploaded legacy-extract file name | Register filters, as-of dates and any migration extract carry externally supplied values into search domains and file operations; concatenation and name-derived paths convert those values into injection and traversal paths |

**Acceptance Criterion:** static analysis reports zero violations for the delivered modules, no new model duplicates a field or a relation the existing accounting or asset models already provide, and no query in the delivered code is assembled by string concatenation.

### 5.4 Test Coverage

| Constraint | Requirement | Rationale |
|------------|-------------|-----------|
| **C-007 — Minimum coverage** | Minimum 80% test coverage for each of the four story implementations | Enterprise-grade assurance for the sub-ledger that carries the capital position on the Balance Sheet and the depreciation charge in the Profit & Loss |
| **C-008 — Test types and traceability** | Unit, integration and acceptance tests, with each acceptance test traceable to one Given/When/Then criterion in its story file | Makes each story's criteria executable rather than declarative |
| **C-009 — Numeric accounting assertions** | The accounting assertions of this feature are tested as amounts: the straight-line board of the worked `$60,000.00 USD` asset sums to `$60,000.00 USD` across 60 periods of `$1,000.00 USD`; the `$50,000.00 USD` asset over 36 months charges `$1,388.89 USD` for 35 periods and `$1,388.85 USD` for the last, summing to `$50,000.00 USD`; the declining-balance switch occurs at period 4 where `$6,480.00 USD` exceeds `$5,184.00 USD`; each depreciation entry reports total debits equal to total credits at a difference of `0.00 USD`; the sale disposal reports total debits of `$64,500.00 USD` equal to total credits of `$64,500.00 USD`; and the Fixed Asset Register net book value total of `$2,890,000.00 USD` equals Fixed Assets 1500 of `$4,820,000.00 USD` less Accumulated Depreciation 1590 of `$1,930,000.00 USD` at a difference of `0.00 USD`. Every amount in this row is rounded to 2 decimal places at its currency's rounding increment of 0.01 | Balance and reconciliation are the accounting contract; they are asserted numerically, not inspected by eye. The board is additionally recomputed from the recorded formula so the assertion does not depend on the implementation that produced it |
| **C-022 — Hostile-input tests** | `STORY-001-08-02` carries at least one acceptance test submitting hostile input to the board's date-range and fiscal-period filters and to its export path — an over-long filter value, an out-of-range date, a malformed date and a formula-injection cell value — and `STORY-001-08-01` carries the equivalent tests on any legacy asset extract loaded at migration, covering a malformed file, an oversized file and a disallowed file type; each asserts rejection with a named error, no journal entry created, and the service still available | The ingestion and rendering constraints C-015, C-017, C-019 and C-020 are proved only by tests that attempt the failure, and these tests discharge the invalid-input and error-handling coverage the Epic requires of every story |

**Acceptance Criterion:** each story implementation reports coverage of 80% or higher from the repository's coverage tooling, and the board-reconciliation, balanced-entry, gain-or-loss and register tie-out assertions are present as numeric test assertions rather than as narrative statements.

### 5.5 Version Compatibility

The platform target is an **open decision** and is stated here as the Epic states it. Three targets are on record and they are mutually exclusive:

| Constraint | Requirement | Notes |
|------------|-------------|-------|
| **C-010 — Platform version target** | Recorded as DEC-001 and confirmed with stakeholders before development, not chosen inside this feature | The originating programme request names **Odoo 17**; this repository is **Odoo 19.0 Community**, where `odoo/release.py` declares `version_info = (19, 0, 0, FINAL, 0, '')`; and the prior, superseded backlog targeted **18.0**. The three targets imply different `account.move` and `account.account` field surfaces, different lock-date administration and different migration effort |
| **C-011 — Language and database versions** | Python and PostgreSQL versions follow the confirmed platform target | The Odoo 19.0 baseline in this repository declares `MIN_PY_VERSION = (3, 10)`, `MAX_PY_VERSION = (3, 13)` and `MIN_PG_VERSION = 13` in `odoo/release.py`; an earlier platform target carries a different supported matrix |
| **Edition baseline** | `account` is present as the "Invoicing" application at version 1.4 under LGPL-3 and `analytic` as "Analytic Accounting" at version 1.2 under LGPL-3; `account_asset` is **absent**; `account_asset_management` is present at version 19.0.1.0.0 under AGPL-3 in category `Accounting/Assets`, carrying `account_asset.py`, `account_asset_category.py`, `account_asset_depreciation_line.py`, `account_move.py` and `account_move_line.py` | The present add-on was built for the 19.0 series. A confirmed target other than 19.0 changes whether it can be credited at all, which feeds directly into the residual-gap assessment under D-003 |

**Impact on this feature if DEC-001 resolves to a version other than 19.0:** the account-type values that anchor the asset, contra-asset and depreciation-expense accounts are restated for the confirmed version, because the account-type selection changed across the three candidate releases; the lock-date behaviour that refuses a depreciation or disposal posting is re-verified, because lock-date administration differs across those releases; the scheduled-action definition behind the periodic run is restated for that version; and the credit given to `account_asset_management` under D-003 is re-assessed, since a 19.0-series add-on is not directly installable on an earlier target. The decision is recorded in the Epic's open decisions register and is not resolved here.

---

## 6. Technical Discovery Notes

> **Purpose:** these notes direct the codebase analysis that precedes implementation. This feature records what to investigate and what the outcome must prove; it does not choose the implementation.

### 6.1 Codebase Analysis Areas

| Analysis Area | Purpose | Key Questions |
|---------------|---------|---------------|
| `addons/account/models/account_account.py` | The account-type selection that anchors the sub-ledger: the fixed-asset type behind Fixed Assets 1500, the non-current-asset type commonly used for a contra-asset, the depreciation-expense type behind Depreciation Expense 6500, and the income and expense types the disposal result lands in | Which selection value carries a fixed asset in this release, and which value does the chart use for a contra-asset held against it? Is a contra-asset expressed by account type, by sign, or by a flag, and how does the Balance Sheet learn to present Accumulated Depreciation 1590 as a deduction rather than an addition? Which type is required of a depreciation-expense account, and is that requirement enforced or advisory? |
| `addons/account/models/account_move.py` | The entry model behind the acquisition, depreciation, revaluation, impairment and disposal entries: the `entry` document type, the draft-posted-cancelled state machine, the date and reference fields, and the validation that refuses an unbalanced entry | Which validation raises when total debits do not equal total credits, and what does its message name? What does the reference field carry for a system-generated entry, and is it enough to identify the asset and the period without reading the lines? Which transitions remain available after an entry is posted, and how is a posted depreciation entry reversed if a board is recomputed? |
| `addons/account/models/account_move_line.py` | The journal-item model that carries the charge line and the contra line, and the multi-line construction a four-line disposal entry needs | How are debit and credit amounts stored and rounded, and at which point is the currency rounding increment applied — per line or on the entry total? How is an analytic distribution attached to a line, and does it survive a batch create? |
| `addons/account/wizard/account_automatic_entry_wizard.py` | The automatic-entry pattern already in the codebase for generating an entry from a source record, which is the nearest precedent for generating a depreciation entry from a board period | Does this wizard's construction pattern extend to a per-asset, per-period entry, or is a scheduled model method the better fit? How does it handle the lock date, and what does it do when the target period is closed? |
| `odoo/addons/base/models/ir_cron.py` and the scheduled-action data pattern | The mechanism behind the periodic depreciation run: interval, next-call date, priority, failure handling and the transaction boundary each execution runs in | How is a scheduled action made idempotent so a repeat over the same period creates no second entry — by a uniqueness constraint on asset and period, by a posted-state check on the board period, or by both? How is a lock taken so two concurrent executions cannot double-post, and what happens to the batch if one asset raises? Where does per-batch progress get logged so the Chief Accountant can read the run at close? |
| `odoo/addons/base/models/ir_sequence.py` | The sequence mechanism behind the asset reference, including per-company resolution and the prefix and padding that produce `FA/00001` | How is a sequence resolved per company, and what guarantees uniqueness under concurrent creation? What happens to numbering when an asset is created and then discarded, and is a gap acceptable to the audit trail? |
| `addons/account_asset_management/models/account_asset.py` | The present Community asset model: its state machine, its cost, salvage, useful-life and start-date fields, and the computation that produces the depreciation lines | Which of the four start-date options in §4.1 does it already implement, and how does it prorate a mid-period acquisition? Where does it place the rounding residual — in the first period, spread across periods, or in the final period as §4.1 requires? Is its state machine the draft-running-disposed model the workflow in §8 assumes? |
| `addons/account_asset_management/models/account_asset_category.py` | The present category model that carries the default method, useful life, salvage basis and the three accounts | Are category defaults copied onto the asset at assignment or read through at computation time? If read through, does a later category change alter an already-configured asset's board, and does that breach the non-retroactivity criterion in §4.1? |
| `addons/account_asset_management/models/account_asset_depreciation_line.py` | The present depreciation-line model behind the board: the per-period amount, its accumulated total, its net book value and its posted state | Does the model store the accumulated total and net book value per period or recompute them on read, and which behaviour meets the 5-second render target for 600 periods? How is the link from a line to its posted entry expressed, and does it support the drill-down in §4.1? |
| `addons/account_asset_management/models/account_move.py` and `account_move_line.py` | The extensions the present add-on makes to the entry and journal-item models, which reveal how an asset is linked to the entries posted against it | Is the asset linkage on the entry, on the line, or on both, and which direction does the register tie-out read? Does the extension prevent the deletion or reversal of a posted depreciation entry, and if not, what protects the accumulated total? |
| Depreciation formula precision and residual placement | The arithmetic behind the three methods, the placement of the rounding residual, and the declining-balance crossover to straight-line | Is each period's charge computed independently from cost, or cumulatively from the previous period's net book value, and which of the two keeps the accumulated total tied to cost under rounding? Where is the residual absorbed, and is the final period recomputed as `cost − salvage − accumulated to the penultimate period` rather than as a rounded quotient? Is the crossover period computed once at configuration or evaluated each period, and does the answer change the board a re-projection produces? |
| Impairment and revaluation measurement | The adjustment path behind an impairment, a revaluation and an impairment reversal, and the recalculation of the remaining board each triggers | Does the present add-on's revaluation cover impairment and impairment reversal, or only revaluation? How is the IAS 36 reversal ceiling — the carrying amount that would have applied without the impairment — derived, and is it derivable from the stored board or does it need its own record? How does an adjustment interact with a board period already posted? |
| `addons/account/models/company.py` | The lock-date fields on `res.company` and their per-user computed counterparts, which decide whether a depreciation or disposal entry may post into a given period | Which lock-date field refuses an `entry` document, and what does the refusal message name? How does the hard lock date differ in reversibility from the fiscal-year lock date, and which of the two governs a depreciation catch-up posted at disposal? |
| `addons/account_financial_report_ce/` | The Community-edition statement implementation at version 19.0.1.1.0, whose balance-sheet and trial-balance objects present the Fixed Assets 1500 and Accumulated Depreciation 1590 balances the register ties to | Does the present balance sheet already present a contra-asset as a deduction within the asset section, and does its trial balance expose the two account balances the tie-out worksheet needs at an as-of date? What is the residual gap between that output and the register in §4.1? |

### 6.2 Existing Odoo Modules to Examine

| Module | Path | Relevance to This Feature |
|--------|------|---------------------------|
| `account` | `addons/account/` | "Invoicing", version 1.4, licence LGPL-3: supplies `account.move` and `account.move.line` for every entry this feature posts, `account.account` with the asset, contra-asset and depreciation-expense types, `account.journal` for the Miscellaneous and Purchase journals, the automatic-entry wizard pattern, and the lock-date fields on `res.company` |
| `account_asset_management` | `addons/account_asset_management/` | Version 19.0.1.0.0, AGPL-3, category `Accounting/Assets`: the present Community asset implementation, carrying the asset, asset-category and depreciation-line models with `account.move` and `account.move.line` extensions, and declaring straight-line, declining-balance and units-of-production methods, the depreciation board, scheduled posting, revaluation and impairment. Credited under D-003 and confirmed story by story before any bespoke build |
| `analytic` | `addons/analytic/` | "Analytic Accounting", version 1.2, licence LGPL-3: the analytic distribution carried on the depreciation charge, consumed by FEATURE-001-09 as the actual side of capital-expenditure budget-versus-actual |
| `account_financial_report_ce` | `addons/account_financial_report_ce/` | Version 19.0.1.1.0, AGPL-3: the present balance-sheet and trial-balance implementation whose Fixed Assets 1500 and Accumulated Depreciation 1590 balances the register tie-out is asserted against |
| `account_payment` | `addons/account_payment/` | "Payment - Account", version 2.0, licence LGPL-3: the registration surface through which disposal proceeds reach Bank 1010 where the sale is settled in cash rather than on credit |
| `base` | `odoo/addons/base/` | `res.company`, `res.currency`, `ir.sequence` and `ir.cron`: the company owning the asset, the currency precision every amount is rounded to, the asset reference numbering, and the scheduled-action mechanism behind the periodic run |

### 6.3 OCA Module Compatibility Considerations

| OCA Module | Repository | Consideration |
|------------|------------|---------------|
| `account_asset_management` | OCA/account-financial-tools | The upstream of the add-on already present here; determine whether the present copy has diverged from upstream, and whether the residual gap is closed by adopting a later upstream release or by extending the local copy |
| `account_asset_batch_compute` | OCA/account-financial-tools | Batch depreciation computation patterns; determine whether it meets the 10-minute scheduled-run target for 10,000 assets in §4.4, and whether its batching is idempotent under a repeat execution |
| `account_asset_disposal` | OCA/account-financial-tools | Disposal workflow and gain-or-loss patterns; determine whether it covers sale, scrapping, write-off and partial disposal, and whether its entry construction asserts total debits equal to total credits as C-009 requires |
| `account_asset_management_hierarchy` and the asset add-on set | OCA/account-financial-tools | Asset grouping and hierarchy extensions; determine whether the register's per-company grouping and the group view in §4.1 are served by an existing extension or remain bespoke |
| `account_financial_report` | OCA/account-financial-reporting | Renders the statutory statement set from posted journal items; determine whether the Balance Sheet presentation of Fixed Assets 1500 net of Accumulated Depreciation 1590 comes from it, from the `account_financial_report_ce` add-on already present, or from the engine DEC-002 confirms |
| `mis_builder` | OCA/mis-builder | Management reporting over posted balances; determine whether the register-to-ledger tie-out worksheet is expressed as a management report here or as a dedicated view |

The decision to integrate, extend or replace any add-on above belongs to DEC-002 in the Epic and is not taken in this feature.

### 6.4 Integration Points

| Integration Point | Model/Module | Integration Type | Notes |
|-------------------|--------------|------------------|-------|
| Acquisition entry | `account.move`, `account.move.line` | Write | Capitalization in the Purchase journal: debit Fixed Assets 1500, credit Accounts Payable 2000, total debits equal total credits |
| Depreciation entry | `account.move`, `account.move.line` | Write | One entry per due board period in the Miscellaneous journal: debit Depreciation Expense 6500, credit Accumulated Depreciation 1590, total debits equal total credits at a difference of `0.00` in the company currency |
| Measurement adjustments | `account.move`, `account.move.line` | Write | Revaluation as debit Fixed Assets 1500 and credit Revaluation Reserve 3200, impairment as debit Impairment Loss 6510 and credit Accumulated Depreciation 1590, and its reversal as the opposite pair, each in the Miscellaneous journal and each posting total debits equal to total credits at a difference of `0.00` in the company currency |
| Disposal entry | `account.move`, `account.move.line` | Write | Credit Fixed Assets 1500 to remove cost, debit Accumulated Depreciation 1590 to clear the contra balance, debit Bank 1010 with the proceeds and post the result to Gain/Loss on Disposal 7200, so total debits equal total credits at a difference of `0.00` in the company currency |
| Capitalizing vendor bill | `account.move` | Read | The source record of the asset, whose line amount the acquisition cost is reconciled against (FEATURE-001-02) |
| Account resolution | `account.account` | Read | Fixed Assets 1500, Accumulated Depreciation 1590, Depreciation Expense 6500, Gain/Loss on Disposal 7200, Impairment Loss 6510, Revaluation Reserve 3200, Accounts Payable 2000 and Bank 1010, each on the asset's own company |
| Journal selection | `account.journal` | Read | Miscellaneous for depreciation, adjustments and disposal; Purchase for the capitalizing acquisition; each as configured in FEATURE-001-01 |
| Periodic run | Scheduled-action mechanism | Extend | Idempotent per-period posting across each company's assets, with a lock against concurrent execution and a per-batch log |
| Asset reference numbering | `ir.sequence` | Read | Per-company resolution producing `FA/00001` and advancing by 1, with uniqueness held under concurrent creation |
| Company and currency | `res.company`, `res.currency` | Read | The company owning the asset, its functional currency and decimal precision, and the lock date that refuses a posting into a reported period |
| Analytic distribution | `account.analytic.account`, `account.analytic.plan` | Write, optional | The cost-centre or project dimension carried on the depreciation charge, consumed by FEATURE-001-09 |
| Statement presentation | `account_financial_report_ce` and the engine DEC-002 confirms | Read | The Balance Sheet and Trial Balance balances of Fixed Assets 1500 and Accumulated Depreciation 1590 the register tie-out is asserted against |

### 6.5 Discovery vs. Prescription Guidelines

> **Important:** this feature and its four stories describe WHAT fixed-asset outcome is needed and WHY finance needs it. They do not prescribe HOW it is built.

**Not specified by this feature or its stories:**

- New model names, field definitions or database schema decisions for the asset, category, depreciation-line or measurement-event records
- Whether a capability is delivered by extending `account_asset_management`, by adopting an OCA add-on, or by a new model
- Whether the depreciation board is stored as records or computed on read, and whether long boards are paginated, lazily loaded or cached
- Whether the periodic run is a scheduled model method, a queued job, or a scheduled action coordinating batches
- Whether impairment is presented against the accumulated-depreciation account or against a separate accumulated-impairment account, provided the Balance Sheet presentation and the register tie-out in §4.1 hold either way
- View architecture, including the choice between an OWL board component and a server-rendered list
- The specific Odoo API methods used to create, post, adjust or reverse an entry
- Module structure and file organization

**Deferred to agent discovery, under the Epic's discovery notes:**

- **D-002** — which edition path supplies the asset capability, and what remains bespoke under each option
- **D-003** — the residual gap for this feature: asset disposal with gain or loss on sale, scrapping and write-off, impairment and impairment reversal, partial disposal, and the register-to-ledger tie-out at a `0.00` difference. Registration, categories, methods, board and scheduled posting are credited to the present `account_asset_management` add-on, and that credit is confirmed against each story's criteria before any bespoke build is authorized
- **D-004** — the report engine and the drill-down path from a Balance Sheet asset line to the board period and the journal items behind it, shared with the reporting feature
- **D-005** — extension versus new model for the measurement-event record that carries a revaluation, an impairment and an impairment reversal with its effective date and basis
- **D-007** — company isolation, record rules and the access-right groups implied by the five applicable personas of §2.1, including the separation of the role that initiates a disposal or an impairment from the role that posts the resulting entry
- **D-009** — the deterministic fixture set for the worked `$60,000.00 USD` asset and its board, the `$50,000.00 USD` residual-bearing asset and the `£25,000.00 GBP` asset in `GB-01` — each cost stated to 2 decimal places at its currency's rounding increment of 0.01 — together with the 600-period asset and the 10,000-asset portfolio, held apart from the hostile-input fixtures C-022 requires on the filter and export paths
- **D-010** — the migration treatment of the legacy asset register at cutover, so an in-life asset enters the register at its original acquisition cost and accumulated depreciation with its remaining board projected from the remaining life rather than from a fresh start, and the register ties to the opening Fixed Assets 1500 and Accumulated Depreciation 1590 balances at a difference of `0.00` in the company currency on day one

---

## 7. Dependencies

### 7.1 Related Features

| Feature | ID | Relationship | Notes |
|---------|----|--------------|-------|
| Chart of Accounts & Fiscal Year | FEATURE-001-01 | Prerequisite | Every entry this feature posts lands in accounts and a journal defined there — Fixed Assets 1500, Accumulated Depreciation 1590, Depreciation Expense 6500, Gain/Loss on Disposal 7200, Impairment Loss 6510, Revaluation Reserve 3200, Accounts Payable 2000 and Bank 1010, through the Miscellaneous and Purchase journals — and into a fiscal period opened there, with the lock date administered there refusing a posting into a reported period. Fixed Assets 1500 and Accumulated Depreciation 1590 are two of that feature's ten deterministic group codes; the depreciation, disposal, impairment and revaluation codes are added to the group chart under its governance rather than defined here. An entry cannot post without its accounts, its journal and an open period, which is ordering rule ORD-001 |
| Accounts Payable & Vendor Bills | FEATURE-001-02 | Prerequisite | An asset acquisition arrives as a vendor bill: the capitalized bill line is directed to Fixed Assets 1500 rather than Expense 6100, and the asset is registered from that bill with the vendor and the bill retained against it and the cost reconciled to the bill line at a difference of `0.00` in the company currency. Without the capitalizing bill there is no source record to register an asset from, and no audit trail from the Balance Sheet asset line back to the vendor document |
| Financial Reporting & Period Close | FEATURE-001-07 | Successor | Posted depreciation supplies the Depreciation Expense 6500 movement in the Profit & Loss, the Fixed Assets 1500 and contra Accumulated Depreciation 1590 balances give the net book value presented on the Balance Sheet, the Gain/Loss on Disposal 7200 result appears in the Profit & Loss, and the register-to-ledger tie-out at a `0.00` difference is one of the close checklist's evidence items. That feature also owns the shared export and drill-down convention the register and the board inherit rather than redefine (ORD-004) |
| Budgeting & Variance Analysis | FEATURE-001-09 | Related | Capital expenditure is budgeted against the accounts this feature charges: the projected board is the forward depreciation expense a budget is planned against, and the posted charge on Depreciation Expense 6500 is the actual placed beside it. That feature's own integration table already names the depreciation entries posted from the board through the Miscellaneous journal as its capital-expenditure actuals |
| Multi-Company & Intercompany Consolidation | FEATURE-001-06 | Related | Asset registers are per legal entity: `US-01`, `NL-01` and `GB-01` each hold their own assets, categories, reference sequence and Miscellaneous journal, and each register is proved against its own company's Fixed Assets 1500 and Accumulated Depreciation 1590. Consolidation translates those balances into the group reporting currency, and an asset transferred between entities is derecognized in one register and recognized in the other rather than shared across both |
| Bank Reconciliation & Cash Management | FEATURE-001-04 | Related | Disposal proceeds debited to Bank 1010 become a bank movement matched against the imported statement line there, so the cash side of a sale is cleared in the ledger rather than tracked outside it |

### 7.2 Required Odoo Modules

| Module | Technical Name | Dependency Type | Purpose |
|--------|----------------|-----------------|---------|
| Invoicing | `account` | Required | Supplies `account.move` and `account.move.line` for the acquisition, depreciation, adjustment and disposal entries, `account.account` with the asset, contra-asset and depreciation-expense types, `account.journal` for the Miscellaneous and Purchase journals, and the lock-date fields on `res.company`; present in this repository at version 1.4 under LGPL-3 |
| Fixed Assets | `account_asset` | Required capability | The Enterprise asset application named in the Epic's module scope, supplying the asset register, the depreciation board and the disposal workflow. **Absent from `addons/` in this repository**, which is recorded as a platform fact rather than a prohibition: the capability arrives through an Odoo Enterprise subscription or through the OCA route, and the choice is DEC-002 |
| Asset Management | `account_asset_management` | Present Community context, credited under D-003 | Present at version 19.0.1.0.0 under AGPL-3 in category `Accounting/Assets`, carrying the asset, asset-category and depreciation-line models with `account.move` and `account.move.line` extensions, and declaring the three depreciation methods, the depreciation board, scheduled posting, revaluation and impairment. Its coverage is credited and confirmed story by story before any bespoke build is authorized |
| Analytic Accounting | `analytic` | Optional | Supplies the analytic distribution carried on the depreciation charge where cost-centre or project reporting is required; consumed mainly by FEATURE-001-09 for capital-expenditure budget-versus-actual. Present at version 1.2 under LGPL-3 |
| Payment - Account | `account_payment` | Optional | Supplies the registration surface through which disposal proceeds reach Bank 1010 where a sale is settled in cash rather than on credit; present at version 2.0 under LGPL-3 |
| Financial Reports (Community edition) | `account_financial_report_ce` | Optional | Present at version 19.0.1.1.0 under AGPL-3: the balance-sheet and trial-balance implementation whose Fixed Assets 1500 and Accumulated Depreciation 1590 balances the register tie-out is asserted against |

### 7.3 External Standards and Specifications

| Standard | Reference | Application to This Feature |
|----------|-----------|-----------------------------|
| IFRS | IAS 16 — Property, Plant and Equipment | Initial measurement at cost, which is what the capitalizing vendor bill establishes; depreciation of the depreciable amount over the useful life on a systematic basis, which is what the three methods and the projected board express; review of useful life, residual value and method, which is what a recalculated remaining board records; the revaluation model, whose surplus is recognized in other comprehensive income and credited to Revaluation Reserve 3200; and derecognition, where the gain or loss is the difference between net disposal proceeds and the carrying amount and is recognized in the Profit & Loss through Gain/Loss on Disposal 7200 |
| IFRS | IAS 36 — Impairment of Assets | Recognition of an impairment loss where the carrying amount exceeds the recoverable amount, which is the `$8,000.00 USD` charge in §4.1; revision of the remaining depreciation charge over the remaining useful life after impairment; and the reversal of an impairment loss capped at the carrying amount that would have applied had no impairment been recognized, which is the ceiling asserted on the `$6,466.66 USD` reversal in §4.1 — each amount rounded to 2 decimal places at the USD rounding increment of 0.01 |
| US GAAP | FASB Accounting Standards Codification Topic 360 — Property, Plant and Equipment | Presentation of property, plant and equipment and of accumulated depreciation as a deduction from it, which is the Balance Sheet presentation of Fixed Assets 1500 net of Accumulated Depreciation 1590; recognition of depreciation as a systematic and rational allocation of cost over the service life; and recognition of the gain or loss on retirement or disposal in the period of derecognition |
| US GAAP | FASB Accounting Standards Codification | The accrual basis behind the periodic charge: depreciation expense is recognized in the period the asset was used rather than the period a payment was made, which is why the scheduled run posts to the board period date and a missed period is posted to the period it belongs to rather than to the current one |
| IFRS | IAS 1 — Presentation of Financial Statements | The current-versus-non-current split that places the asset net book value outside current assets, and the offsetting rules under which accumulated depreciation is presented as a deduction from the asset it relates to rather than netted off outside the ledger |
| IFRS | IAS 21 — The Effects of Changes in Foreign Exchange Rates | Translation of the asset and accumulated-depreciation balances of `NL-01` and `GB-01` into the group reporting currency for the consolidated position produced by FEATURE-001-06, with each entity's own amounts rounded to its own currency's decimal precision before translation |
| ISO 4217 | Currency codes and minor units | The decimal precision behind every rounding assertion in this feature: 2 decimal places at a rounding increment of 0.01 for USD, EUR and GBP, applied to every acquisition cost, salvage value, period charge, accumulated total, net book value, proceeds amount and gain-or-loss amount |
| Internal-control frameworks | COSO Internal Control — Integrated Framework, and the internal-control-over-financial-reporting expectations built on it | The scheduled depreciation run is an automated control, so its execution log, its skip reasons and its idempotency are retained as evidence; the register-to-ledger tie-out is a reconciliation control performed each period and retained; and the framework requires that the role initiating a disposal or an impairment is separate from the role posting the resulting entry, which is the segregation recorded in §4.2 and mapped in §2.2 |

---

## 8. Feature Workflow Diagram

### 8.1 Asset Lifecycle

The state model below is the one the four stories are demonstrated against. Depreciation drives the asset from Running through PartiallyDepreciated to FullyDepreciated, while revaluation and impairment are measurement branches that recalculate the remaining board and return the asset to the depreciating path. Derecognition is reachable from any depreciating state, because an asset can be sold, scrapped or written off before its useful life ends.

```mermaid
stateDiagram-v2
    [*] --> Draft : Asset created from the capitalizing vendor bill
    Draft --> Draft : Account type, company, salvage or useful-life validation refuses confirmation
    Draft --> [*] : Draft discarded before confirmation, no journal entry created
    Draft --> Running : Confirmed, acquisition posted as debit Fixed Assets 1500 and credit Accounts Payable 2000, total debits equal total credits
    Running --> Running : Method configured or overridden and the board projected across the useful life
    Running --> PartiallyDepreciated : First board period posted as debit Depreciation Expense 6500 and credit Accumulated Depreciation 1590, total debits equal total credits at a difference of 0.00
    PartiallyDepreciated --> PartiallyDepreciated : Each further due board period posted by the scheduled run, total debits equal total credits
    PartiallyDepreciated --> PartiallyDepreciated : Repeat run over a posted period creates no second entry and reports a validation message
    PartiallyDepreciated --> Revalued : Revaluation posted as debit Fixed Assets 1500 and credit Revaluation Reserve 3200, total debits equal total credits at a difference of 0.00
    Revalued --> PartiallyDepreciated : Remaining board recalculated on the revalued carrying amount
    PartiallyDepreciated --> Impaired : Impairment posted as debit Impairment Loss 6510 and credit Accumulated Depreciation 1590, total debits equal total credits at a difference of 0.00
    Impaired --> PartiallyDepreciated : Remaining board recalculated on the recoverable amount
    Impaired --> ImpairmentReversed : Reversal posted as debit Accumulated Depreciation 1590 and credit Impairment Loss 6510 with total debits equal to total credits at a difference of 0.00, capped at the carrying amount that would have applied without the impairment
    ImpairmentReversed --> PartiallyDepreciated : Remaining board recalculated after the reversal
    PartiallyDepreciated --> LockedOut : Entry dated on or before the company fiscal-year lock date
    LockedOut --> PartiallyDepreciated : Refused with a validation message naming the company and the lock date, no journal entry created
    PartiallyDepreciated --> PartiallyDisposed : Part of the asset derecognized, cost and accumulated depreciation removed pro rata, Gain/Loss on Disposal 7200 booked, total debits equal total credits at a difference of 0.00
    PartiallyDisposed --> PartiallyDepreciated : Remaining quantity continues on a recalculated board
    PartiallyDepreciated --> FullyDepreciated : Accumulated depreciation equals cost less salvage value, net book value equals salvage value
    FullyDepreciated --> FullyDepreciated : Scheduled run posts no further charge against a fully depreciated asset
    PartiallyDepreciated --> Disposed : Sold, scrapped or written off with depreciation caught up to the disposal date
    FullyDepreciated --> Disposed : Sold, scrapped or written off at a net book value equal to the salvage value
    Disposed --> Reported : Register re-run, net book value tied to Fixed Assets 1500 less Accumulated Depreciation 1590 at a difference of 0.00
    FullyDepreciated --> Reported : Register and Balance Sheet present the asset at its salvage value
    Reported --> Closed : Period locked with the asset position proved
    Closed --> [*]
```

### 8.2 Acquisition to Register Tie-Out Workflow

```mermaid
flowchart TD
    A["Capitalized vendor bill posted in FEATURE-001-02:<br/>line directed to Fixed Assets 1500"] --> B["STORY-001-08-01<br/>Asset registered: cost, acquisition date, category,<br/>useful life, salvage value, vendor and source bill"]
    B --> C{"Asset, accumulated-depreciation and<br/>expense accounts valid, same company, active?"}
    C -->|"No"| D["Confirmation refused with a validation message<br/>naming the failed requirement, asset stays in Draft,<br/>no journal entry created"]
    D --> B
    C -->|"Yes"| E["Reference generated from the company sequence as FA/00001,<br/>acquisition posted in the Purchase journal:<br/>debit Fixed Assets 1500, credit Accounts Payable 2000,<br/>total debits equal total credits at a difference of 0.00"]
    E --> F["STORY-001-08-02<br/>Method configured or inherited from the category:<br/>straight-line, declining balance or units of production"]
    F --> G{"Method, useful life, rate, total units and<br/>salvage value complete and in range?"}
    G -->|"No"| H["Save refused with a validation message<br/>naming the failed requirement, no board projected"]
    H --> F
    G -->|"Yes"| I["Depreciation board projected across the useful life:<br/>period charge, accumulated total, net book value,<br/>rounding residual absorbed in the final period"]
    I --> J["STORY-001-08-03<br/>Scheduled run selects the board periods<br/>due on or before the run date"]
    J --> K{"Period already posted for this asset?"}
    K -->|"Yes"| L["No second entry created,<br/>validation message names the asset,<br/>the period and the existing entry"]
    K -->|"No"| M{"Period date on or before the<br/>company fiscal-year lock date?"}
    M -->|"Yes"| N["Posting refused with a validation message<br/>naming the company and the lock date,<br/>no journal entry created"]
    M -->|"No"| O["Entry posted in the Miscellaneous journal:<br/>debit Depreciation Expense 6500,<br/>credit Accumulated Depreciation 1590,<br/>total debits equal total credits at a difference of 0.00"]
    O --> P["Board period marked Posted with the entry reference,<br/>per-batch log written"]
    P --> Q["STORY-001-08-04<br/>Measurement event or derecognition"]
    Q --> R["Revaluation or impairment posted in the Miscellaneous journal,<br/>total debits equal total credits at a difference of 0.00,<br/>remaining board recalculated"]
    R --> P
    Q --> S["Depreciation caught up to the disposal date,<br/>then cost and accumulated depreciation removed,<br/>proceeds recorded and Gain/Loss on Disposal 7200 booked,<br/>total debits equal total credits at a difference of 0.00"]
    S --> T["Fixed Asset Register run per company at the as-of date:<br/>net book value total equals Fixed Assets 1500<br/>less Accumulated Depreciation 1590 at a difference of 0.00"]
    P --> T
    T --> U["Handed to FEATURE-001-07 for the Balance Sheet,<br/>the Profit & Loss and the close checklist,<br/>and to FEATURE-001-09 as capital-expenditure actuals"]
```

### 8.3 Periodic Depreciation Run

```mermaid
sequenceDiagram
    participant SCH as Scheduled Run
    participant AST as Asset Register
    participant BRD as Depreciation Board
    participant GL as Miscellaneous Journal
    participant FAA as Fixed-Asset Accountant
    participant CA as Chief Accountant

    SCH->>AST: Select the running assets of each company
    AST-->>SCH: Asset set per company with its functional currency
    SCH->>BRD: Read the board periods due on or before the run date
    BRD-->>SCH: Due period, charge amount and period date per asset
    SCH->>SCH: Take the run lock so a concurrent execution cannot double-post
    SCH->>BRD: Skip any due period already marked Posted
    SCH->>GL: Post one entry per remaining due period, debit Depreciation Expense 6500 and credit Accumulated Depreciation 1590 with total debits equal to total credits
    GL-->>SCH: Entries posted, total debits equal total credits at a difference of 0.00
    SCH->>BRD: Mark each posted period with the entry reference
    SCH->>SCH: Write the per-batch log with assets processed, amount posted per company and every skip reason
    SCH-->>FAA: Run complete, exceptions listed for review
    FAA->>BRD: Review the exceptions and amend the configuration or the period
    FAA->>CA: Submit the run log and the board for close review
    CA->>GL: Confirm each entry balances and lies inside an open period
    CA->>AST: Run the Fixed Asset Register at the as-of date and tie the net book value total to Fixed Assets 1500 less Accumulated Depreciation 1590
    AST-->>CA: Tie-out difference of 0.00 in the company currency
    CA->>GL: Apply the period lock date once the asset position is proved
```

---

## 9. Related Documentation

### 9.1 Epic Reference

| Document | Link |
|----------|------|
| Parent Epic | [EPIC-001: Enterprise Accounting in Odoo](../EPIC-001-enterprise-accounting-odoo.md) |
| Epic success metrics SM-008 and SM-009, which this feature is measured on | [EPIC-001 §4.1 Measurable Outcomes](../EPIC-001-enterprise-accounting-odoo.md#41-measurable-outcomes) |
| Decomposition bounds, including the 2-to-5 stories per feature this file applies | [EPIC-001 §5.3 Feature and Story Decomposition Guidelines](../EPIC-001-enterprise-accounting-odoo.md#53-feature-and-story-decomposition-guidelines) |
| Odoo module scope, which records `account_asset` as absent from this repository | [EPIC-001 §5.4 Odoo Module Scope](../EPIC-001-enterprise-accounting-odoo.md#54-odoo-module-scope) |
| Ordering rules ORD-001 and ORD-004, which place this feature after the foundations and before reporting | [EPIC-001 §6.2 Inter-Feature Ordering](../EPIC-001-enterprise-accounting-odoo.md#62-inter-feature-ordering) |
| Phase 4 — Group and sub-ledgers, where this feature is sequenced | [EPIC-001 §6.3 Implementation Sequence](../EPIC-001-enterprise-accounting-odoo.md#63-implementation-sequence) |
| Constraint set C-001 to C-022, restated for this feature in §5 | [EPIC-001 §7 Constraints](../EPIC-001-enterprise-accounting-odoo.md#7-constraints) |
| Security and untrusted-input constraints C-015 to C-022, which govern the register filters, the board export and the migration extract | [EPIC-001 §7.7 Security and Untrusted-Input Handling](../EPIC-001-enterprise-accounting-odoo.md#77-security-and-untrusted-input-handling) |
| Discovery note D-003, which credits `account_asset_management` and records this feature's residual gap | [EPIC-001 §9.3 D-003](../EPIC-001-enterprise-accounting-odoo.md#93-d-003-reuse-of-the-existing-community-edition-accounting-add-ons) |
| Platform version and edition lock-in, the source of DEC-001 and DEC-002 | [EPIC-001 §10.1.1](../EPIC-001-enterprise-accounting-odoo.md#1011-platform-version-and-edition-lock-in) |
| Master data readiness, which requires the asset categories to be complete before these stories | [EPIC-001 §10.1.5](../EPIC-001-enterprise-accounting-odoo.md#1015-master-data-readiness) |
| Open decisions DEC-001 (platform version) and DEC-002 (edition source, which gates this feature) | [EPIC-001 Appendix B: Open Decisions Register](../EPIC-001-enterprise-accounting-odoo.md#appendix-b-open-decisions-register) |
| Retirement map, which records the six retired asset stories folding into these four | [EPIC-001 Appendix C: Legacy Retirement and Migration Map](../EPIC-001-enterprise-accounting-odoo.md#appendix-c-legacy-retirement-and-migration-map) |
| The asset merge obligations that STORY-001-08-02 and STORY-001-08-04 must carry | [EPIC-001 Appendix C.3.5](../EPIC-001-enterprise-accounting-odoo.md#c35-the-bank-budget-and-asset-mergers) |
| Prerequisite feature — accounts, journals, fiscal periods and lock dates | [FEATURE-001-01: Chart of Accounts & Fiscal Year](./FEATURE-001-01-chart-of-accounts-fiscal-year.md) |
| Prerequisite feature — the capitalizing vendor bill an asset is registered from | [FEATURE-001-02: Accounts Payable & Vendor Bills](./FEATURE-001-02-accounts-payable-vendor-bills.md) |
| Related feature — capital expenditure budgeted against the accounts this feature charges | [FEATURE-001-09: Budgeting & Variance Analysis](./FEATURE-001-09-budgeting-variance-analysis.md) |

### 9.2 Story Files

| Story | Link |
|-------|------|
| STORY-001-08-01: Register Fixed Assets with Acquisition Detail | [STORY-001-08-01](./FEATURE-001-08/STORY-001-08-01-register-fixed-assets.md) |
| STORY-001-08-02: Configure Depreciation Methods and Projected Board | [STORY-001-08-02](./FEATURE-001-08/STORY-001-08-02-configure-depreciation-methods.md) |
| STORY-001-08-03: Post Automated Depreciation Entries | [STORY-001-08-03](./FEATURE-001-08/STORY-001-08-03-post-depreciation-entries.md) |
| STORY-001-08-04: Dispose of Assets with Gain or Loss Recognition | [STORY-001-08-04](./FEATURE-001-08/STORY-001-08-04-dispose-assets.md) |

### 9.3 External References

| Resource | URL | Purpose |
|----------|-----|---------|
| Odoo fixed-asset documentation | <https://www.odoo.com/documentation/19.0/applications/finance/accounting/vendor_bills/assets.html> | Functional behaviour of asset creation from a vendor bill, depreciation board and disposal in the baseline release |
| Odoo Accounting user documentation | <https://www.odoo.com/documentation/19.0/applications/finance/accounting.html> | Journal entries, account types and journal behaviour the asset entries post through |
| Odoo Editions comparison | <https://www.odoo.com/page/editions> | The Community and Enterprise capability split that places `account_asset` outside this repository and makes DEC-002 necessary |
| OCA/account-financial-tools | <https://github.com/OCA/account-financial-tools> | Home of `account_asset_management`, `account_asset_batch_compute` and `account_asset_disposal`: the asset register, batch depreciation and disposal patterns evaluated under DEC-002 |
| OCA/account-financial-reporting | <https://github.com/OCA/account-financial-reporting> | `account_financial_report` patterns for the Balance Sheet presentation of Fixed Assets 1500 net of Accumulated Depreciation 1590 |
| OCA/mis-builder | <https://github.com/OCA/mis-builder> | `mis_builder` management-reporting patterns assessed for the register-to-ledger tie-out worksheet |
| IFRS Foundation list of standards | <https://www.ifrs.org/issued-standards/list-of-standards/> | Source of IAS 16, IAS 36, IAS 1 and IAS 21 as applied in §7.3 |
| IAS 16 — Property, Plant and Equipment | <https://www.ifrs.org/issued-standards/list-of-standards/ias-16-property-plant-and-equipment/> | Measurement, depreciation, revaluation and derecognition requirements the board and the disposal entry answer to |
| IAS 36 — Impairment of Assets | <https://www.ifrs.org/issued-standards/list-of-standards/ias-36-impairment-of-assets/> | Impairment recognition, the revised remaining charge and the reversal ceiling asserted in §4.1 |
| FASB Accounting Standards Codification | <https://asc.fasb.org/> | US GAAP Topic 360 presentation of property, plant and equipment and accumulated depreciation, and the accrual basis behind the periodic charge |
| COSO Internal Control — Integrated Framework | <https://www.coso.org/guidance-on-ic> | Control expectations behind the automated depreciation run, the register-to-ledger reconciliation and the segregation of disposal initiation from posting |

---

## 10. Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1 | 2026-08-13 | Enterprise Accounting Team | Initial draft: 4 stories indexed under `./FEATURE-001-08/`, capabilities CAP-001 to CAP-004 mapped to those stories, feature success criteria tied to SM-008 and SM-009, the worked `$60,000.00 USD` asset over 60 months at `$1,000.00 USD` per period — rounded to 2 decimal places at the USD rounding increment of 0.01 with the residual absorbed in the final period — fixed as the board archetype against Fixed Assets 1500, Accumulated Depreciation 1590 and Depreciation Expense 6500, the sale, scrapping and partial-disposal archetypes fixed against Gain/Loss on Disposal 7200 and Bank 1010, constraints restated from C-001 to C-022 including C-012 on building on the existing entry models and C-015 to C-022 on run-time report parameters and the migration extract, the platform-version and edition decisions carried forward as DEC-001 and DEC-002, `account_asset` recorded as absent from this repository with `account_asset_management` credited under D-003, and the six-story-to-four-story migration recorded with the Appendix C.3.5 merge obligations assigned to STORY-001-08-02 and STORY-001-08-04 |
