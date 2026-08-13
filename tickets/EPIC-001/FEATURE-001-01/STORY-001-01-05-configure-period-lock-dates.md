# STORY-001-01-05: Configure Period Lock Dates and Closing Controls

---

## Metadata

| Attribute | Value |
|-----------|-------|
| **Story ID** | `STORY-001-01-05` |
| **Title** | Configure Period Lock Dates and Closing Controls |
| **Parent Feature** | [FEATURE-001-01: Chart of Accounts & Fiscal Year](../FEATURE-001-01-chart-of-accounts-fiscal-year.md) |
| **Parent Epic** | [EPIC-001: Enterprise Accounting in Odoo](../../EPIC-001-enterprise-accounting-odoo.md) |
| **Persona** | Group Controller |
| **Status** | Draft |
| **Priority** | 🟠 High |
| **Estimate** | 3 story points (Fibonacci) |
| **Feature Capability** | CAP-005 — configure period lock dates and closing controls that block posting into closed periods |
| **Epic Success Metric** | SM-003 — the close cycle is measured in business days from period end **to the period lock date being applied**, so the control this story delivers is the instrument the metric is read from; SM-004 measures report availability from the same lock-date application; SM-016 (post-close audit adjustments halved) is the outcome a closed period protects; SM-006 is asserted **unchanged** across every lock change |
| **Owner/Author** | Enterprise Accounting Team |

This is the fifth and last of the five stories in FEATURE-001-01, and the one that turns a reported period into a closed one. The four stories before it build the books — the accounts, their reporting taxonomy, the fiscal calendar and the opening position; this story protects what has already been reported from them. It is **blocked by [STORY-001-01-03](./STORY-001-01-03-define-fiscal-year-periods.md)**, because a lock date is a date on a fiscal calendar and locking an arbitrary date closes nothing nameable, and it is the counterpart of Scenario 7 of [STORY-001-01-04](./STORY-001-01-04-import-legacy-coa.md), where a lock date at **31 December 2025** blocks the back-dated opening entry of **Acme Group NV** until the **Group Controller** releases it.

> **Monetary convention used throughout this ticket.** Every amount is stated in USD, carried to 2 decimal places, and rounded half-up at the USD rounding increment of 0.01. Where a company reports in a functional currency other than USD, the same assertion is made in that currency at that currency's own decimal precision. Every date is stated as an explicit calendar date rather than as a relative period, and every lock behaviour names the lock-date field that governs it.

---

## User Story

**As a** Group Controller

**I want** the five lock dates held per company on `res.company` administered for **Acme Group NV** and for **Acme Industries Inc.** independently — the Global Lock Date (`fiscalyear_lock_date`), the Tax Return Lock Date (`tax_lock_date`), the Sales Lock Date (`sale_lock_date`), the Purchase Lock date (`purchase_lock_date`) and the irreversible Hard Lock Date (`hard_lock_date`) — together with the time-boxed release recorded on `account.lock_exception` for the single entry that has to reach a period already closed

**So that** a period whose figures have been filed with a tax authority, given to a lender or signed off by an auditor refuses further posting and cannot change after the fact, and every release from that control carries the person who granted it, the person it was granted to, the company and lock date it covers, and the moment it expires — so the close date is a fact the External Auditor can test (SM-003, SM-016) rather than a convention the finance team observes.

---

## INVEST Principles Compliance

| Principle | Compliance | Notes |
|-----------|------------|-------|
| **Independent** | ✅ | The one predecessor is [STORY-001-01-03](./STORY-001-01-03-define-fiscal-year-periods.md), and that dependency is **configuration sequencing, not code coupling**: a lock date is a date on a fiscal calendar, so the calendar has to exist for **31 December 2025** to mean the end of FY2025 rather than an arbitrary day. Nothing in this story shares an implementation with that one — the five lock-date fields, their computed per-user counterparts and the lock-exception record are supplied by module `account` independently of how the fiscal-year end day and month were set, and this story is developed against the boundary the calendar states rather than against the mechanism that stated it. It needs no account from [STORY-001-01-01](./STORY-001-01-01-configure-coa-hierarchy.md) beyond the codes its verification entries post to, and no migrated balance from [STORY-001-01-04](./STORY-001-01-04-import-legacy-coa.md). |
| **Negotiable** | ✅ | The outcome is stated — a closed period refuses posting, and any release is time-boxed, attributed and readable — while the mechanism stays open. Which of the five fields is administered at which stage of the close, whether the Sales Lock Date and Purchase Lock date are used at all or the Global Lock Date carries the whole control, when a Hard Lock Date is set relative to the statutory filing, and the surface the values are maintained on are each negotiable with the Group Controller and settled in the discovery recorded below. |
| **Valuable** | ✅ | Without this control every earlier story is reversible: a figure filed with a tax authority or given to a board keeps changing behind it, and restatement risk persists (SM-016). The lock date is also the instrument two Epic metrics are measured with — SM-003 counts business days from period end to the lock date being applied, and SM-004 times report publication from the same moment — and Epic Definition-of-Done item 6 requires journal-entry and tax lock dates applied with post-lock posting attempts blocked before one full close can be accepted. |
| **Estimable** | ✅ | The deliverable is countable: five date fields on the company record, five computed per-user counterparts, one immutable exception record with its expiry, four refusal paths (a locked posting, a tax-locked posting, a backward Hard Lock Date, and a Hard Lock Date attempted over draft entries) and one permitted-then-expired release. Every field, message and access right was read in the repository during discovery, so nothing waits on an open decision; it is sized at 3 Fibonacci points with the rationale in § Estimation. |
| **Small** | ✅ | One configuration outcome — the closing controls of one company, reproduced independently for a second company — demonstrated in a single walkthrough: the lock-date values, one refused posting, one recorded exception, one permitted posting and one expiry. The close checklist itself, the deferral cutoff and the statement set are period-close work carried by FEATURE-001-07, and the chart, taxonomy, calendar and opening balances are the four sibling stories, so this story is not a container for the close. |
| **Testable** | ✅ | Every criterion below resolves to a date, a stored value, an amount or a refusal: a Global Lock Date of 31 December 2025, a Tax Return Lock Date of 30 November 2025, a Hard Lock Date that stays at 30 September 2025 after a backward attempt, an entry left in Draft with total debits of USD 2,400.00 equal to total credits of USD 2,400.00, account 2000 Accounts Payable held at a credit of USD 540,400.00 instead of USD 542,800.00, and an exception that permits one posting and then reads Expired. Each of the five scenarios maps to exactly one named automated test in § Test Requirements, so pass or fail is decided without judgement (C-008, C-009). |

---

## Acceptance Criteria

Five criteria are authored, inside the 4-to-8 bound the Epic sets in [§5.3](../../EPIC-001-enterprise-accounting-odoo.md#53-feature-and-story-decomposition-guidelines), and they carry the mandated coverage distribution: **Scenarios 1 and 2 are valid-input cases** (a Global Lock Date applied to a filed fiscal year, a Tax Return Lock Date applied to a submitted VAT period), **Scenario 3 is the invalid-input case** (a Hard Lock Date moved backwards), **Scenario 4 is the error-handling case** (a balanced posting refused by the lock and left in Draft), and **Scenario 5 is the accounting edge case** (a time-boxed release that permits one entry, records who granted it and to whom, and then expires).

Each scenario states its own fixture in its **Given**, so no criterion depends on another having run first. Two conventions hold across all five: the entry used to probe a lock is always **balanced**, so a refusal is attributable to the lock date and never to an imbalance; and the amounts of **Acme Group NV** tie to migration fixture M-1 in [STORY-001-01-04](./STORY-001-01-04-import-legacy-coa.md), whose opening entry dated **31 December 2025** carries total debits of **USD 4,875,300.00** equal to total credits of **USD 4,875,300.00** with account **2000 Accounts Payable** at a credit of **USD 540,400.00**.

### Scenario 1: A Global Lock Date closes the filed fiscal year of one company and leaves its subsidiary open

- **Given** fiscal year **FY2025** of **Acme Group NV** spans **01 January 2025 to 31 December 2025** on the calendar fixed by [STORY-001-01-03](./STORY-001-01-03-define-fiscal-year-periods.md); the statutory accounts of that company for FY2025 are filed; every journal entry of **Acme Group NV** dated on or before **31 December 2025** stands in state **Posted**, including the opening entry of fixture M-1 whose total debits of **USD 4,875,300.00** equal its total credits of **USD 4,875,300.00** — a difference of **USD 0.00**, each amount rounded to 2 decimal places using half-up rounding; no bank statement line of that company dated on or before **31 December 2025** is left unreconciled; and the Global Lock Date (`fiscalyear_lock_date`) of **Acme Group NV** and of **Acme Industries Inc.** is empty
- **When** the **Group Controller** sets the Global Lock Date (`fiscalyear_lock_date`) of **Acme Group NV** to **31 December 2025**
- **Then** the stored Global Lock Date of **Acme Group NV** reads **31 December 2025** and every attempt to add or modify a journal entry of that company dated on or before **31 December 2025** is refused; a **Miscellaneous** journal entry of **Acme Group NV** dated **02 January 2026** debiting **Expense 6100** by **USD 2,400.00** against a credit of **USD 2,400.00** to **Accounts Payable 2000** posts with **total debits of USD 2,400.00 equal to total credits of USD 2,400.00** — a difference of **USD 0.00**, each amount rounded to 2 decimal places using half-up rounding; the Global Lock Date of **Acme Industries Inc.** stays empty, so a **Miscellaneous** journal entry of **Acme Industries Inc.** dated **15 December 2025** debiting **Expense 6100** by **USD 900.00** against a credit of **USD 900.00** to **Accounts Payable 2000** posts with **total debits of USD 900.00 equal to total credits of USD 900.00** at a difference of **USD 0.00**; the **Trial Balance** of **Acme Group NV** for **01 January 2025 to 31 December 2025** reports account **2000 Accounts Payable** at a credit of **USD 540,400.00** and total debits of **USD 4,875,300.00** equal to total credits of **USD 4,875,300.00**, the same figures it reported before the lock date was set; and the lock-date change is retained on the company record with its author and its timestamp

### Scenario 2: A Tax Return Lock Date closes a submitted VAT period with the tax split held apart

- **Given** the VAT return of **Acme Group NV** for the period **01 November 2025 to 30 November 2025** is submitted to the tax authority; the tax it reports stands on account **2200 Tax Payable** at a credit of **USD 10,500.00** for that period, rounded to 2 decimal places using half-up rounding; the Tax Return Lock Date (`tax_lock_date`), the Global Lock Date (`fiscalyear_lock_date`) and the Sales Lock Date (`sale_lock_date`) of that company are empty; and a customer invoice of **Acme Group NV** stands in state **Draft** in the **Sales** journal dated **15 November 2025**, bearing tax code **`VAT-STD-21`** on a **base amount of USD 50,000.00** with a **tax amount of USD 10,500.00** held on its own line, debiting **Accounts Receivable 1200** by **USD 60,500.00** against a credit of **USD 50,000.00** to **Revenue 4000** and a credit of **USD 10,500.00** to **Tax Payable 2200**, so its **total debits of USD 60,500.00 equal its total credits of USD 60,500.00** — a difference of **USD 0.00**, each amount rounded to 2 decimal places using half-up rounding
- **When** the **Group Controller** sets the Tax Return Lock Date (`tax_lock_date`) of **Acme Group NV** to **30 November 2025**
- **Then** the stored Tax Return Lock Date of **Acme Group NV** reads **30 November 2025**; the draft customer invoice dated **15 November 2025** carries a lock-date warning naming the **Tax Return Lock Date of 30 November 2025**, and the subsequent attempt to post it is refused with an Odoo validation message stating that the operation would affect an already issued tax statement and naming the **Tax Return Lock Date (30 November 2025)** as the value to change to proceed; that invoice stays in state **Draft** with its tax code **`VAT-STD-21`**, its **base amount of USD 50,000.00** and its **tax amount of USD 10,500.00** recorded separately and unchanged; the **Trial Balance** of **Acme Group NV** for **01 November 2025 to 30 November 2025** reports account **2200 Tax Payable** unchanged at a credit of **USD 10,500.00** rather than the **USD 21,000.00** it would carry had the invoice posted, so the tax amount on the submitted return still ties to the tax control account at a difference of **USD 0.00**, each amount rounded to 2 decimal places using half-up rounding; and a customer invoice of the same company dated **01 December 2025** bearing the same tax code on the same **base amount of USD 50,000.00** with the same **tax amount of USD 10,500.00** posts with **total debits of USD 60,500.00 equal to total credits of USD 60,500.00** at a difference of **USD 0.00**, rounded to 2 decimal places using half-up rounding

### Scenario 3: A Hard Lock Date moved backwards is refused and the stored value survives

- **Given** the Hard Lock Date (`hard_lock_date`) of **Acme Group NV** reads **30 September 2025**, set when the half-year figures of that company were signed off; its Global Lock Date (`fiscalyear_lock_date`) reads **31 December 2025**; its Tax Return Lock Date (`tax_lock_date`) reads **30 November 2025**; and the **Group Controller** is editing the closing controls of that company
- **When** the **Group Controller** saves a Hard Lock Date (`hard_lock_date`) of **31 August 2025** for **Acme Group NV**
- **Then** the save is refused with an Odoo validation message stating that a new Hard Lock Date must be later than or equal to the previous one, so the lock cannot be moved backwards; the stored Hard Lock Date of **Acme Group NV** remains **30 September 2025**; the Global Lock Date of that company remains **31 December 2025** and its Tax Return Lock Date remains **30 November 2025**, so a refused save on one field leaves the other four untouched; an attempt by the same role to clear the Hard Lock Date altogether is refused with a message stating that the Hard Lock Date cannot be removed; no journal entry is created, amended or unposted by either refused attempt; and the Hard Lock Date of **Acme Industries Inc.** is unaffected by both attempts

### Scenario 4: A balanced entry dated inside the locked period is refused and left in Draft

- **Given** the Global Lock Date (`fiscalyear_lock_date`) of **Acme Group NV** reads **31 December 2025**; the **Chief Accountant** holds a **Miscellaneous** journal entry of that company in state **Draft** dated **15 December 2025**, debiting **Expense 6100** by **USD 2,400.00** against a credit of **USD 2,400.00** to **Accounts Payable 2000**, so its **total debits of USD 2,400.00 equal its total credits of USD 2,400.00** — a difference of **USD 0.00**, each amount rounded to 2 decimal places using half-up rounding; and no lock exception is in force for that company, that user or that lock-date field
- **When** the **Chief Accountant** attempts to post that entry dated **15 December 2025**
- **Then** the posting is refused with an Odoo lock-date validation message naming the **Global Lock Date (31 December 2025)** of **Acme Group NV** as the date on and before which entries cannot be added or modified, measured against the entry's own accounting date of **15 December 2025**; the entry remains in state **Draft** with its two lines and its two totals unchanged at **USD 2,400.00** each, rounded to 2 decimal places using half-up rounding; no journal item of that entry reaches the posted sub-ledger, so the **Trial Balance** of **Acme Group NV** for **01 December 2025 to 31 December 2025** still reports account **2000 Accounts Payable** at a credit of **USD 540,400.00** rather than the **USD 542,800.00** it would carry had the entry posted, account **6100 Expense** unchanged, and total debits of **USD 4,875,300.00** equal to total credits of **USD 4,875,300.00** at a difference of **USD 0.00**, each amount rounded to 2 decimal places using half-up rounding; and the refused attempt writes no value to any of the five lock-date fields of that company

### Scenario 5: A time-boxed lock exception admits one entry, records who granted it, and then expires

- **Given** the refusal of Scenario 4 stands — the Global Lock Date (`fiscalyear_lock_date`) of **Acme Group NV** reads **31 December 2025**, its Hard Lock Date (`hard_lock_date`) is empty, and the **Chief Accountant** holds the balanced **Miscellaneous** journal entry dated **15 December 2025** in state **Draft** with **total debits of USD 2,400.00 equal to total credits of USD 2,400.00**, a difference of **USD 0.00**, each amount rounded to 2 decimal places using half-up rounding — and the External Auditor has proposed that adjustment against the December 2025 period, so it cannot be re-dated into FY2026
- **When** the **Group Controller** records an `account.lock_exception` for **Acme Group NV** that changes the Global Lock Date for the **Chief Accountant** alone to **30 November 2025**, with a stated reason and an End Date **24 hours** after the grant
- **Then** the effective Global Lock Date resolved for the **Chief Accountant** through `user_fiscalyear_lock_date` reads **30 November 2025** while the stored `fiscalyear_lock_date` of **Acme Group NV** stays **31 December 2025** for every other user; the balanced entry dated **15 December 2025** posts with **total debits of USD 2,400.00 equal to total credits of USD 2,400.00** — a difference of **USD 0.00**, each amount rounded to 2 decimal places using half-up rounding — so the **Trial Balance** of **Acme Group NV** for **01 December 2025 to 31 December 2025** then reports account **2000 Accounts Payable** at a credit of **USD 542,800.00** and total debits of **USD 4,877,700.00** equal to total credits of **USD 4,877,700.00**; the exception is readable with the **Group Controller** who granted it, the **Chief Accountant** it was granted to, the company **Acme Group NV**, the lock-date field it changed, the changed lock date of **30 November 2025** against the original lock date of **31 December 2025**, its reason and its End Date, and it is recorded on the message history of that company so the External Auditor reads it without a data request; the record admits no edit and no deletion, only revocation; and once the End Date has passed the exception reads state **Expired**, so a further **Miscellaneous** journal entry of that company dated **16 December 2025** debiting **Expense 6100** by **USD 1,500.00** against a credit of **USD 1,500.00** to **Accounts Payable 2000** is refused with the same **Global Lock Date (31 December 2025)** message and stays in state **Draft**

---

## Sub-Tasks

| # | Sub-Task | Assignee |
|---|----------|----------|
| 1 | Define the closing calendar with the Group Controller and the Finance SME: for each in-scope company, which of the five lock dates is set at which stage of the close, on which date, and against which statutory filing — the Tax Return Lock Date at VAT submission, the Global Lock Date at period sign-off, the Hard Lock Date at statutory filing | `@functional-consultant` |
| 2 | Record the exception policy: who may grant a lock exception, who may receive one, the maximum validity in hours, the reason text a grant must carry, and the review step that reads every exception granted in a period at the following close | `@functional-consultant` |
| 3 | Configure the five lock-date fields per company and make each value readable beside the fiscal-period boundary it sits on, so the Group Controller sees the boundary being closed before the value is saved | `@developer` |
| 4 | Deliver the exception workflow end to end: grant against one company, one lock-date field and one user with a stated expiry; resolve the effective per-user lock date through the computed `user_*_lock_date` values; expire the grant without manual intervention; and surface the journal items touched while the grant was in force | `@developer` |
| 5 | Author the five automated acceptance tests named in § Test Requirements, one per scenario, plus the negative tests for a Hard Lock Date moved backwards, a Hard Lock Date cleared, and a Hard Lock Date attempted over a period that still holds draft entries | `@qa-engineer` |
| 6 | Test the audit trail as evidence: every lock-date change carries its author and timestamp, every exception carries grantor, grantee, company, lock-date field, changed and original lock dates, reason and expiry, and a role restricted to **Acme Group NV** can neither read nor amend the lock dates of **Acme Industries Inc.** (C-014, D-007) | `@qa-engineer` |
| 7 | Confirm the control satisfies the period-integrity expectation the External Auditor tests, sign off the exception approval path as segregation of duties — the Group Controller grants, the Chief Accountant posts — and countersign each company's Hard Lock Date before it is set, since it cannot be undone | `@finance-sme` |

---

## Edge Cases

| # | Edge Case | Expected Handling |
|---|-----------|-------------------|
| 1 | A lock date is set to a mid-month date rather than a period end — the Global Lock Date of **Acme Group NV** set to **15 January 2026** while FY2026 runs 01 January 2026 to 31 December 2026 | The value is accepted, because the field holds a date and not a period: entries dated on or before **15 January 2026** are refused and a **Miscellaneous** entry dated **16 January 2026** debiting **Expense 6100** by **USD 3,200.00** against a credit of **USD 3,200.00** to **Accounts Payable 2000** posts with total debits of **USD 3,200.00** equal to total credits of **USD 3,200.00**, a difference of **USD 0.00**, rounded to 2 decimal places using half-up rounding. The period 01 January 2026 to 31 January 2026 is then part closed and part open, so a **Trial Balance** for that range mixes a closed segment with a writable one. The group close calendar therefore records lock dates at period boundaries, and a mid-month value is set only on Group Controller approval with the reason retained beside the change |
| 2 | The effective lock date a user sees differs from the value stored on the company — the **Chief Accountant** holds an active exception on **Acme Group NV** while every other role does not | The stored `fiscalyear_lock_date` stays the single administered value at **31 December 2025**, and the computed `user_fiscalyear_lock_date` resolves per user: **30 November 2025** for the **Chief Accountant** while the exception is active, **31 December 2025** for everyone else, and the same distinction holds for the tax, sales and purchase counterparts. Membership of an accounting-manager group grants no implicit release — only a recorded exception changes the effective value — and if the Group Controller writes a new stored lock date while a grant is live, Odoo revokes that grant and re-creates it against the new stored value, leaving two records rather than a silently re-scoped one, so the history stays readable to the External Auditor |
| 3 | A Hard Lock Date is set while the period still holds draft entries — the Hard Lock Date of **Acme Group NV** attempted at **31 December 2025** while the balanced draft of Scenario 4 dated **15 December 2025** with total debits of **USD 2,400.00** equal to total credits of **USD 2,400.00** is still open | The change is refused with a warning that names the draft entries standing in the period and offers the list of them, and every draft stays in state **Draft** with its two totals unchanged at **USD 2,400.00** each, rounded to 2 decimal places using half-up rounding. The Group Controller resolves each draft first — posted before the lock is applied, or deleted with its reason retained — and only then is the Hard Lock Date accepted. The same guard refuses a lock over a period holding unreconciled bank statement lines, which is the hand-over point to the reconciliation work of FEATURE-001-04. Because the Hard Lock Date admits no exception, cannot be moved backwards and cannot be removed, the Finance SME countersigns it before it is set |
| 4 | An entry inside a locked period has to be corrected — a posted **Miscellaneous** entry of **Acme Group NV** dated **10 December 2025** debiting **Expense 6100** by **USD 6,000.00** against a credit of **USD 6,000.00** to **Accounts Payable 2000**, with the Global Lock Date at **31 December 2025** | The entry is not amended and not unposted; it is reversed forward. The reversal is dated **02 January 2026**, outside the lock, and posts debiting **Accounts Payable 2000** by **USD 6,000.00** against a credit of **USD 6,000.00** to **Expense 6100**, with total debits of **USD 6,000.00** equal to total credits of **USD 6,000.00** — a difference of **USD 0.00**, rounded to 2 decimal places using half-up rounding — and keeps its link to the entry it reverses. FY2025 as reported is therefore unchanged and the correction is presented in FY2026. A reversal dated **10 December 2025** is refused by the same Global Lock Date message, which is the behaviour that makes the reported year final |
| 5 | A vendor bill is captured with a bill date inside the locked period — a bill of **Acme Group NV** for **USD 2,400.00**, rounded to 2 decimal places using half-up rounding, in the **Purchase** journal with a bill date of **20 December 2025** while the Global Lock Date reads **31 December 2025** | The bill is not refused: its accounting date is moved past the lock to a date inside the first open period after **31 December 2025**, and the form states the Global Lock Date it was moved past together with the accounting date the entry will carry on posting, while the bill date of **20 December 2025** stays on the document as the vendor stated it. The bill then posts in FY2026 debiting **Expense 6100** by **USD 2,400.00** against a credit of **USD 2,400.00** to **Accounts Payable 2000**, total debits of **USD 2,400.00** equal to total credits of **USD 2,400.00** at a difference of **USD 0.00**. A manual **Miscellaneous** entry dated **20 December 2025** is refused instead of moved, so the two behaviours are documented side by side and the December expense for goods received before the year end is recognized through the period-close cutoff of FEATURE-001-07 rather than by re-dating the bill |

---

## Demonstration

The story is accepted when the **Group Controller** walks the **Finance Controller** and the **Product Owner** through the following path in the Odoo user interface, with the External Auditor invited to observe the control being tested. Where a reviewer prefers the public API, the same seven steps are demonstrated through it; either way the walkthrough is recorded against this story. Every figure shown is read in USD at 2 decimal places, rounded half-up.

1. **The lock-date configuration screen — Accounting ▸ Accounting ▸ Lock Dates** — the five values of **Acme Group NV** shown together: Global Lock Date, Tax Return Lock Date, Sales Lock Date, Purchase Lock date and Hard Lock Date. Discovery in this repository found the five fields present and enforced on the company record by module `account` with no dedicated screen shipped in the Community baseline, so which surface carries them follows from DEC-002; the walkthrough shows whichever surface the confirmed platform provides, and the field names above are the values being read either way.
2. **The Global Lock Date set to 31 December 2025** for **Acme Group NV**, with the FY2025 boundary of **31 December 2025** from [STORY-001-01-03](./STORY-001-01-03-define-fiscal-year-periods.md) shown beside it, and the change then read back from the company's message history with its author and timestamp.
3. **The refused posting — Accounting ▸ Accounting ▸ Journal Entries** — the balanced **Miscellaneous** entry dated **15 December 2025**, debit **Expense 6100 USD 2,400.00** against credit **Accounts Payable 2000 USD 2,400.00**, posted by the **Chief Accountant** and refused with the Odoo lock-date validation message naming the **Global Lock Date (31 December 2025)**, the entry shown still in state **Draft** afterwards.
4. **The ledger shown unmoved** — the **Trial Balance** of **Acme Group NV** for **01 December 2025 to 31 December 2025** read before and after the refused attempt: account **2000 Accounts Payable** at a credit of **USD 540,400.00** and total debits of **USD 4,875,300.00** equal to total credits of **USD 4,875,300.00** in both runs.
5. **The tax lock** — the Tax Return Lock Date of **Acme Group NV** set to **30 November 2025**, and the draft customer invoice dated **15 November 2025** carrying tax code **`VAT-STD-21`** with its **base amount of USD 50,000.00** and **tax amount of USD 10,500.00** shown refused with the tax-statement message, followed by the **Trial Balance** for **01 November 2025 to 30 November 2025** showing account **2200 Tax Payable** unchanged at a credit of **USD 10,500.00**.
6. **The time-boxed release** — the lock exception granted to the **Chief Accountant** for **Acme Group NV** moving that user's effective Global Lock Date to **30 November 2025** with a stated reason and an End Date **24 hours** out; the same entry then posting with **total debits of USD 2,400.00 equal to total credits of USD 2,400.00**; the exception record shown with its grantor, grantee, company, lock-date field, changed and original lock dates, reason and expiry, and its list of the journal items touched while it was in force; and the **Trial Balance** for **01 December 2025 to 31 December 2025** re-read at account **2000 Accounts Payable USD 542,800.00** with total debits of **USD 4,877,700.00** equal to total credits of **USD 4,877,700.00**.
7. **The negative walkthrough** — the Hard Lock Date of **Acme Group NV** at **30 September 2025** with an attempt to move it to **31 August 2025** refused, an attempt to clear it refused, the stored value shown still at **30 September 2025**; and the expired exception shown in state **Expired** with a **Miscellaneous** entry dated **16 December 2025** for **USD 1,500.00** on each side refused once more.

---

## Constraints

### License and Compliance

- [ ] **C-001 — AGPL-3.0 compatible licence.** Any module delivering the lock-date administration, the exception workflow or the closing-control reporting is distributed under an AGPL-3.0 compatible licence, matching the Community-edition accounting add-ons already present in this repository.
- [ ] **C-002 — LGPL-3 of `account` respected.** The five lock-date fields, their computed per-user counterparts, the lock-exception model and the posting validations that read them are LGPL-3 code declared in `addons/account/__manifest__.py`; derived and dependent work stays licence-compatible with it and no derived work misstates its licence.
- [ ] **C-005 and C-006 — Odoo and OCA coding standards.** Python follows Odoo and OCA module guidelines including PEP 8, and static analysis passes with the repository's configured tooling in `ruff.toml` at zero violations.
- [ ] **C-012 — build on the existing models.** The control is expressed on the existing lock-date fields of `res.company`, the existing lock-exception record and the existing posting validations on `account.move` and `account.move.line`, rather than as a parallel period-status table, so one ledger, one control and one audit trail survive the change.
- [ ] **C-014 — access rights and segregation of duties.** The Group Controller administers the lock dates and grants each exception; the Chief Accountant executes the close and posts under a granted exception but cannot grant one to themselves; the External Auditor holds read-only access to the lock-date values, their change history and every exception with its expiry; and a role restricted to **Acme Group NV** can neither read nor amend the lock dates of **Acme Industries Inc.** In the Odoo 19.0 baseline read during discovery, an exception record is creatable and revocable only by a member of the accounting-manager group and is readable but not editable or deletable by anyone, which is the property the audit trail rests on.
- [ ] **C-020 — refusal messages stay actionable and disclose nothing internal.** Each refusal names the lock-date field, its date and the company whose books are affected, and discloses no stack trace, SQL, file-system path or credential; diagnostic detail goes to the server log under an access-controlled channel.

### Version Compatibility

The platform target of this programme is an **open decision (DEC-001)** recorded in the Epic's [Open Decisions Register](../../EPIC-001-enterprise-accounting-odoo.md#appendix-b-open-decisions-register) and stated here without being resolved:

| Candidate target | Evidence on record | Consequence for this story |
|------------------|--------------------|----------------------------|
| **Odoo 17** | Named by the originating programme request | The five field names and labels asserted here, the wording of each refusal message and the presence of a time-boxed exception record are re-checked against the 17 series, where the exception mechanism may not exist and the release path would then be a lock-date change for every user rather than a grant to one |
| **Odoo 18.0** | Targeted by the prior, superseded backlog | Neither the request nor this repository is served; the field names, the refusal messages and the exception fields asserted here are restated for 18.0 |
| **Odoo 19.0** | The baseline present in this repository: `version_info = (19, 0, 0, FINAL, 0, '')` in `odoo/release.py` | Every behaviour cited in the criteria holds as written: the five lock-date fields and their computed per-user counterparts exist on `res.company`, the Hard Lock Date refuses a backward move and a removal, a locked posting is refused with the lock date named, a tax-locked posting is refused with the tax-statement message, and a time-boxed exception with grantor, grantee, scope and expiry is recorded on `account.lock_exception` |

- [ ] **C-010 — the confirmed version is recorded** in the Epic and restated in the parent Feature before development starts; this story does not choose it.
- [ ] **C-011 — Python and PostgreSQL versions follow the confirmed target**, since each candidate release carries its own supported matrix.
- [ ] **Edition source (DEC-002) does not gate the behaviour, only its surface and its verification.** The five lock-date fields, their computed per-user counterparts and the lock-exception record were all read in `addons/account` in this Odoo 19.0 **Community** repository, so the control itself is deliverable here and does not wait on the Enterprise-versus-OCA decision. What DEC-002 settles is the screen the values are maintained on — no dedicated lock-date screen ships in this Community baseline — and the engine that renders the verifying **Trial Balance**, which is Enterprise capability in `account_reports`, absent here, while the AGPL-3 `account_financial_report_ce` add-on present in this repository supplies the same report with the date-range parameter every criterion cites.

### Accounting Standards Compliance

- [ ] **Period integrity.** Once a period is reported, its figures are fixed: the lock date is the technical expression of that principle, and a correction to a closed period is presented as a reversal or an adjustment in an open period rather than as a change to the closed one (Edge Case 4).
- [ ] **IAS 1 — Presentation of Financial Statements.** A complete set of statements is presented for a stated period; a period whose statements have been issued is closed to further posting so that the issued statements and the ledger continue to agree, and any post-issue adjustment is disclosed with the period it is recognized in.
- [ ] **Audit trail and internal control.** Every lock-date change carries its author and timestamp, and every exception carries its grantor, its grantee, the company and lock-date field it covers, its reason and its expiry. This is the evidence an internal-control assessment under SOX Section 404 tests for a financial-close control, and it is readable by the External Auditor without a data request.
- [ ] **Segregation of duties for exception approval.** The role that grants a release is not the role that posts under it: the Group Controller grants, the Chief Accountant posts, and no role may grant itself a release. Every grant is time-boxed, and every grant made in a period is reviewed at the following close.
- [ ] **Irreversibility is a governance decision, not a technical one.** The Hard Lock Date cannot be loosened, removed or excepted once set, so it is applied only after the statutory filing for the period is complete and only with the Finance SME's countersignature on record.
- [ ] **Tax-period integrity.** A submitted tax return fixes its period: the Tax Return Lock Date refuses any later entry that would change the tax base or the tax amount for that period, so the tax amount on the filed return continues to tie to the tax control account **2200 Tax Payable** at a difference of **USD 0.00** (SM-010).

---

## Technical Discovery Notes

> **Purpose:** these notes direct the codebase analysis that precedes implementation. This story states WHICH control finance needs and WHY; the surface the values are maintained on, the model inheritance, the view architecture and the shape of any reporting over exceptions emerge from discovery and are deliberately not prescribed here.

### Codebase Analysis Areas

| Area | Files/Modules to Examine | Analysis Focus |
|------|--------------------------|----------------|
| The five lock-date fields and their labels | `addons/account/models/company.py` | The four soft lock-date fields and the one hard field held on the company record, their user-facing labels, their help text, and the fact that each is change-tracked on a company that inherits the messaging mixin — which is where the author-and-timestamp evidence of Scenario 1 comes from. Determine which document type each field governs, because that mapping is the closing calendar sub-task 1 produces |
| Which lock applies to which document | `addons/account/models/company.py` | The routine that collects the lock dates violated by an accounting date: the global and hard locks are evaluated for every entry, the sales lock only for a sales-type journal, the purchase lock only for a purchase-type journal, and the tax lock only where the entry affects the tax report. Determine the consequence for the closing calendar — a Global Lock Date alone closes everything, while the sales and purchase locks close one side at a time |
| Effective versus stored lock date | `addons/account/models/company.py` | The five computed per-user lock-date values, how each resolves the stored value together with any active exception, and how the resolution walks the company and its parent companies. Determine how the computed value interacts with access groups, since Edge Case 2 asserts that group membership alone grants no release |
| The guards on setting a lock | `addons/account/models/company.py` | The validation that runs before a lock date is written: a hard lock cannot be lowered or removed, a hard lock over a period holding draft entries is refused with the drafts listed, and a global or hard lock over a period holding unreconciled bank statement lines is refused. Determine the operational sequence these guards imply for the close, and what the write path does to exceptions already granted on a lock date being changed |
| The time-boxed release | `addons/account/models/account_lock_exception.py` | The exception record: the company, the user it is valid for, the reason, the end date, the lock-date field it changes, the changed lock date and the original lock date it was granted against, and the computed state that turns it from active to expired. Determine how the grant is recorded on the company's message history, how the journal items touched while it was in force are surfaced, and what the model refuses — duplication, and any edit or deletion |
| Access rights over the release | `addons/account/security/ir.model.access.csv`, `addons/account/security/account_security.xml` | Which group may create an exception, which may revoke one, and which may only read. This is the segregation-of-duties assertion of C-014, and it decides whether the approval path needs additional restriction or is already carried by the existing groups |
| Posting validation | `addons/account/models/account_move.py` | The constraint that refuses adding or modifying an entry inside a locked period and the message it raises, the points in the write and post paths where it runs, and the computed warning shown on a draft document whose date sits before a lock. Determine the difference Edge Case 5 rests on: an invoice or bill has its accounting date moved past the lock, while a manual entry is refused |
| The sub-ledger and the tax check | `addons/account/models/account_move_line.py` | The journal-item level check that refuses an operation which would change an already issued tax statement, and the tax tags that decide whether an entry affects the tax report. This is the mechanism behind Scenario 2, and the journal items it protects are what the Trial Balance sums |
| Reversal into an open period | `addons/account/wizard/account_move_reversal.py` | How a reversal date is chosen and validated against the lock dates, and how the reversal keeps its link to the entry it reverses — the behaviour Edge Case 4 depends on |
| Entry immutability beside the lock | `addons/account/wizard/account_secure_entries_wizard.py` | The securing and hashing of posted entries and its use of the effective hard lock date. Determine how period locking and entry hashing are sequenced at the close, since both are read by the External Auditor as one control set |
| Verification reports | `addons/account_financial_report_ce/models/trial_balance.py`, `addons/account_financial_report_ce/models/general_ledger.py` | The date-range parameter of the Trial Balance and the General Ledger and the sub-ledger query behind each line — the reports every criterion is proved against, and the surface that shows a locked period reporting the same figures before and after a refused attempt |
| Company hierarchy and currency | `odoo/addons/base/models/res_company.py`, `odoo/addons/base/models/res_currency.py` | The parent-and-subsidiary structure that carries one set of lock dates per company independently, the record rules that keep one company's values out of another's reach, and the currency decimal precision every monetary assertion is rounded to |

### Relevant Existing Modules

- `addons/account/` — "Invoicing", version 1.4, licence LGPL-3. Supplies the five lock-date fields with their labels and change tracking, the five computed per-user counterparts, the guards that run before a lock is written, the lock-exception record with its expiry and audit linkage, and the posting validations on the entry and on the journal item that raise the refusals every criterion asserts.
- `addons/account_financial_report_ce/` — version 19.0.1.1.0, AGPL-3. Supplies the Trial Balance and General Ledger with the date ranges the criteria cite, so the "unchanged before and after" assertions are demonstrable while DEC-002 stays open.
- `addons/account_payment/` — Community. Reads the same lock dates when a payment is posted, so the closing calendar has to account for payment entries and not only for manual entries and invoices.
- `odoo/addons/base/` — `res.company`, `res.users` and `res.currency`: the company hierarchy that carries lock dates per entity, the user record an exception is granted to, and the decimal precision the monetary assertions are rounded to.
- `addons/mail/` — the messaging and tracking mixin the company record inherits, which is what makes a lock-date change and an exception grant readable as history rather than as a current value alone.

### OCA Module Compatibility

| OCA Repository | Module | Compatibility Consideration |
|----------------|--------|-----------------------------|
| OCA/account-financial-tools | `account_lock_date_update` | Relaxes who may change a lock date and under which conditions. Determine whether it conflicts with the segregation of duties this story requires, since a broader write path would let the role that posts also move the boundary it posts against |
| OCA/account-financial-tools | `account_move_line_no_delete` | Prevents deletion of journal items and complements a period lock, which refuses change rather than deletion of already posted data. Determine whether it is needed once locking and entry securing are both in force |
| OCA/account-closing | `account_fiscal_year_closing` | Runs a templated year-end close whose steps end at the boundary this story locks. Determine the order between its closing moves and the lock date, since a lock applied too early refuses the closing moves themselves |
| OCA/account-financial-reporting | `account_financial_report` | Renders the Trial Balance and General Ledger from date-range parameters and is the alternative surface for the "unchanged before and after" verification if DEC-002 selects the OCA path |

The decision to integrate, extend or replace any add-on above belongs to DEC-002 in the Epic and is not taken in this story.

> **Model identifier note.** The lock-exception model read in this repository during discovery is named `account.lock_exception`, described as "Account Lock Exception", and defined in `addons/account/models/account_lock_exception.py`. Where a programme document renders the same model as `account.lock.exception`, it refers to this record; the identifier used throughout this ticket is the one verified in the code.

---

## Dependencies

### Story Dependencies

| Dependency Type | Story / Feature ID | Title | Relationship |
|-----------------|--------------------|-------|--------------|
| Parent Feature | [FEATURE-001-01](../FEATURE-001-01-chart-of-accounts-fiscal-year.md) | Chart of Accounts & Fiscal Year | This story is the fifth and last of the feature's five stories and delivers its capability CAP-005 |
| **Blocked By** | [STORY-001-01-03](./STORY-001-01-03-define-fiscal-year-periods.md) | Define Fiscal Year and Accounting Periods | **A lock date is a date on a fiscal calendar.** The period boundaries have to exist before one of them can be closed, so **31 December 2025** means the end of FY2025 rather than an arbitrary day. Edge Cases 1 and 4 of that story hand this boundary here explicitly. The dependency is configuration sequencing, not code coupling |
| Related | [STORY-001-01-04](./STORY-001-01-04-import-legacy-coa.md) | Import Legacy Chart of Accounts and Opening Balances | Its Scenario 7 is the mirror of this story: a Global Lock Date at **31 December 2025** blocks the back-dated opening entry of **Acme Group NV** carrying total debits of **USD 4,875,300.00** equal to total credits of **USD 4,875,300.00** until the Group Controller releases it. Fixture M-1 of that story supplies every ledger figure asserted here, including account **2000 Accounts Payable** at a credit of **USD 540,400.00** |
| Related | [STORY-001-01-01](./STORY-001-01-01-configure-coa-hierarchy.md) | Configure Multi-Level Chart of Accounts Hierarchy | Supplies the deterministic codes the verification entries post to — **Expense 6100**, **Accounts Payable 2000**, **Tax Payable 2200**, **Accounts Receivable 1200** and **Revenue 4000** — and the five journal types whose sales and purchase kinds decide which lock date applies to which document |
| Related | FEATURE-001-05 (Tax Configuration & Compliance) | — | Defines tax code **`VAT-STD-21`** with its base and tax accounts, and generates the VAT return whose submission is the event that sets the Tax Return Lock Date of Scenario 2 (ORD-002). In the platform baseline read during discovery the tax lock date is also set by the tax closing entry itself, so the two features agree on one value |
| Related | FEATURE-001-07 (Financial Reporting & Period Close) | — | Owns the period-close checklist, the deferral cutoff and the statement set. This story supplies the control the checklist ends on: applying the lock date is the last step of the close and the moment SM-003 and SM-004 are measured from. Referenced by identifier under ORD-004; the close stories are authored in that feature and not linked from here |
| Related | FEATURE-001-06 (Multi-Company & Intercompany Consolidation) | — | Consolidation consumes closed, locked entity results so the group figures are reproducible (ORD-005), which is why the lock dates are administered per company and never once for the group |
| Related | FEATURE-001-04 (Bank Reconciliation & Cash Management) | — | A global or hard lock over a period holding unreconciled bank statement lines is refused, so the reconciliation of that feature is a precondition of closing the period (Edge Case 3) |

### External Dependencies

| Dependency | Type | Notes |
|------------|------|-------|
| Group close calendar | Governance artifact | Owned by the Group Controller; states the date each lock is applied per company per period, and every lock date set away from a period boundary is approved against it (Edge Case 1) |
| Statutory filing deadline per jurisdiction | Regulatory requirement | Fixes when a tax period and a statutory year may be closed: the Tax Return Lock Date follows the VAT submission, and the Hard Lock Date follows the statutory filing, so the deadlines drive the sequence rather than the other way round |
| External-audit period sign-off | Governance artifact | The auditor's sign-off is the event after which a period is closed for good; audit-proposed adjustments arriving before it are the reason the time-boxed release of Scenario 5 exists, and the count of them is SM-016 |
| Exception approval policy | Governance artifact | States who may grant a release, who may receive one, the maximum validity in hours and the reason a grant must carry; produced by sub-task 2 and countersigned by the Finance SME |
| Legal-entity register | Master data | **Acme Group NV** and **Acme Industries Inc.** exist as company records with their functional currency set, since every lock date is held per company |
| Report engine for the verification reports | Odoo module | `account_reports` is Enterprise capability and absent here; the AGPL-3 `account_financial_report_ce` add-on present in this repository supplies the Trial Balance date range the criteria cite (DEC-002) |
| Platform version and edition confirmation | Open decision (DEC-001, DEC-002) | Recorded in the Epic's [Open Decisions Register](../../EPIC-001-enterprise-accounting-odoo.md#appendix-b-open-decisions-register); DEC-001 fixes the field names and messages this story is implemented against, and DEC-002 fixes the surface the values are maintained on and the engine that renders the verification reports |
| IAS 1 and SOX Section 404 | Accounting standard and internal-control framework | Fix the period-presentation expectation and the internal-control evidence a financial-close control is tested against |

### Integration Points

| Odoo Model | Integration Type | Purpose |
|------------|------------------|---------|
| `res.company` | Read and write | The record the control is held on: `fiscalyear_lock_date`, `tax_lock_date`, `sale_lock_date`, `purchase_lock_date` and `hard_lock_date`, their computed per-user counterparts, and the change history that carries the author and timestamp of every lock-date change |
| `account.lock_exception` | Read and write | The time-boxed release: one company, one lock-date field, one changed lock date against the original, one grantee, one reason and one expiry, with its state resolving from active to expired and its record admitting no edit and no deletion |
| `account.move` | Read | The entry whose accounting date is tested against the lock dates: the balanced draft of **USD 2,400.00** refused in Scenario 4, the entries permitted in Scenarios 1, 2 and 5, and the reversal dated outside the lock in Edge Case 4 |
| `account.move.line` | Read | The posted sub-ledger the Trial Balance sums and the level at which an operation affecting an already issued tax statement is refused; the items touched while a release was in force are read from here as audit evidence |
| `res.users` | Read | The user an exception is granted to and the user who granted it, and the identity the computed per-user lock dates resolve against |
| `account.journal` | Read | The journal whose type decides whether the sales or purchase lock applies — Sales, Purchase, Bank, Cash and Miscellaneous — and the sequence a moved accounting date has to respect (Edge Case 5) |
| `account.account` | Read | **Expense 6100**, **Accounts Payable 2000**, **Tax Payable 2200**, **Accounts Receivable 1200** and **Revenue 4000**, the codes every criterion's amounts land on |
| `account.tax` | Read | Tax code **`VAT-STD-21`** and the tax tags that decide whether an entry affects the tax report and therefore meets the Tax Return Lock Date |
| `res.currency` | Read | The `USD` definition and the 2-decimal precision every monetary assertion is rounded to using half-up rounding |

---

## Estimation

| Dimension | Rating | Basis |
|-----------|--------|-------|
| **Effort** | Low | Five date fields per company, one exception record with an expiry, and the access rights over both, made reproducible for a second company and covered by five acceptance tests plus three negative tests. No posting logic, no report and no migration is delivered |
| **Complexity** | Medium | The configuration surface is small but the rules interact: five fields with different document scopes, an effective value that differs per user while one value is stored, guards that refuse a lock over draft entries or unreconciled statement lines, a write path that re-creates live exceptions when the stored value moves, and one field that cannot be undone. The segregation of duties over the release has to hold as an access-rights matrix rather than as a convention |
| **Uncertainty** | Low | Every field, guard, refusal message and access right cited here was read in the repository during discovery. The residual unknown is the surface the values are maintained on, which follows from DEC-002 and changes the demonstration path rather than the control delivered |
| **Story Points** | **3** (Fibonacci: 1, 2, 3, 5, 8, 13) | |

Three points reflects a small configuration surface whose risk sits in the rules rather than in the volume: five interacting fields, one irreversible field, and one release path that has to be attributable and time-boxed. Two points would understate the exception workflow, the per-user effective value and the three negative paths that all have to be proved. Five would overstate work that introduces no new model, no posting logic and no report, and would put it level with the twelve-line migration load of [STORY-001-01-04](./STORY-001-01-04-import-legacy-coa.md), which is materially broader. The estimate assumes the closing calendar and the exception policy are confirmed by the Group Controller during the sprint, and it excludes the close checklist and the statement set, which belong to FEATURE-001-07.

---

## Test Requirements

### Coverage Requirement

| Metric | Requirement | Notes |
|--------|-------------|-------|
| **Minimum Test Coverage** | **80%** | Mandatory for all new functionality delivered by this story (C-007) |
| Unit Test Coverage | 80% or higher | Lock-date resolution per user, the guards that refuse a lock change, and the state transition of an exception from active to expired |
| Integration Test Coverage | 80% or higher | Refused and permitted postings across the five fields, the tax-statement refusal, the exception grant and expiry, and the Trial Balance read before and after each attempt |
| Accounting assertion style | Numeric | Every monetary and balance assertion is compared as an amount in USD at 2 decimal places with half-up rounding, and every date assertion as a date, never inspected by eye (C-009) |
| Traceability | One test per criterion | Each of the five scenarios maps to exactly one named acceptance test (C-008) |

### Unit Test Scenarios

| Acceptance Scenario | Unit Test Focus | Key Assertions |
|---------------------|-----------------|----------------|
| Scenario 1 | Writing the Global Lock Date and scoping it to one company | After the write, the stored value of **Acme Group NV** equals 31 December 2025 and the stored value of **Acme Industries Inc.** is empty; the collected violations for an accounting date of 31 December 2025 in **Acme Group NV** name the global lock and for 02 January 2026 name none; the same call for **Acme Industries Inc.** on 15 December 2025 names none |
| Scenario 2 | Tax-lock resolution for a tax-bearing entry | With the Tax Return Lock Date at 30 November 2025, an entry dated 15 November 2025 that affects the tax report yields a tax-lock violation while the same entry with no tax line yields none; an entry dated 01 December 2025 yields none; and the base amount of USD 50,000.00 and the tax amount of USD 10,500.00 are held on separate lines with the tax amount equal to 21% of the base, rounded to 2 decimal places using half-up rounding |
| Scenario 3 | The guard on the hard lock | Writing 31 August 2025 over a stored 30 September 2025 raises an error and leaves the stored value at 30 September 2025; writing an empty value raises an error; writing 31 October 2025 succeeds in a company holding no draft entry and no unreconciled statement line dated on or before that date; and neither refusal alters the other four lock-date fields |
| Scenario 4 | Refusal of a posting inside the locked period | Posting the entry dated 15 December 2025 raises an error naming the global lock and its date of 31 December 2025; the entry's state stays draft; the sum of posted journal items on account 2000 for 01 December 2025 to 31 December 2025 stays USD 540,400.00 credit and does not become USD 542,800.00; the entry's debit total of USD 2,400.00 equals its credit total of USD 2,400.00 throughout, each amount compared in USD at 2 decimal places using half-up rounding |
| Scenario 5 | Grant, effect and expiry of the release | With an active grant, the effective global lock resolved for the **Chief Accountant** equals 30 November 2025 while the value resolved for another user and the stored value both equal 31 December 2025; the entry dated 15 December 2025 posts with debits of USD 2,400.00 equal to credits of USD 2,400.00, compared in USD at 2 decimal places using half-up rounding; the record carries its grantor, grantee, company, lock-date field, changed lock date of 30 November 2025 and original lock date of 31 December 2025, reason and end date; after the end date the state reads expired and the effective value returns to 31 December 2025; and an attempt to edit, delete or duplicate the record is refused |

### Integration Test Considerations

Every assertion below is compared numerically in USD at 2 decimal places using half-up rounding, and every report date range is passed explicitly.

- [ ] Post the FY2025 population of **Acme Group NV** including the opening entry of fixture M-1, run the **Trial Balance** for 01 January 2025 to 31 December 2025, apply the Global Lock Date of 31 December 2025, re-run the same report, and assert both runs report account 2000 at a credit of USD 540,400.00 with total debits of USD 4,875,300.00 equal to total credits of USD 4,875,300.00.
- [ ] Post the entry dated 02 January 2026 for USD 2,400.00 on each side after the lock is applied and assert total debits equal total credits at a difference of USD 0.00.
- [ ] Attempt the balanced entry dated 15 December 2025, assert the refusal, assert the entry stays in draft, and assert the **Trial Balance** for 01 December 2025 to 31 December 2025 reports the same figures line for line as the run taken before the attempt, each line compared at a difference of USD 0.00.
- [ ] Exercise the tax path end to end: post the November 2025 tax position onto account 2200 at a credit of USD 10,500.00, submit the VAT return, set the Tax Return Lock Date to 30 November 2025, attempt the draft invoice dated 15 November 2025 carrying `VAT-STD-21` with a base of USD 50,000.00 and a tax of USD 10,500.00, assert the refusal, and assert account 2200 stays at USD 10,500.00 credit for that range.
- [ ] Grant a lock exception to one user with a short expiry, assert the permitted posting, let the grant expire, assert the next posting inside the period is refused, and assert the journal items touched while the grant was in force are retrievable from the exception record.
- [ ] Change the stored Global Lock Date while a grant is active and assert the grant is revoked and re-created against the new stored value, with both records readable and the effective per-user value recomputed.
- [ ] Attempt a Hard Lock Date over a period holding one draft entry of USD 2,400.00 on each side, assert the refusal names the draft entries, post that draft outside the lock or delete it, then assert the Hard Lock Date is accepted.
- [ ] Attempt a global lock over a period holding one unreconciled bank statement line and assert the refusal, then reconcile the line and assert the lock is accepted.
- [ ] Capture a vendor bill in the **Purchase** journal with a bill date of 20 December 2025 under a Global Lock Date of 31 December 2025 and assert its accounting date is moved past the lock while its bill date stays 20 December 2025, and that it posts with total debits of USD 2,400.00 equal to total credits of USD 2,400.00.
- [ ] Reverse a posted entry of USD 6,000.00 dated 10 December 2025 with a reversal date of 02 January 2026 and assert the reversal posts with total debits of USD 6,000.00 equal to total credits of USD 6,000.00, then assert a reversal dated 10 December 2025 is refused.
- [ ] Verify the access-rights matrix (C-014): only the granting role may create an exception, only the accounting-manager group may revoke one, no role may edit or delete one, the External Auditor reads lock dates and exceptions without write access, and a role restricted to **Acme Group NV** can neither read nor amend the lock dates of **Acme Industries Inc.**
- [ ] Measure the lock-date validation overhead on a single posting with all five fields administered and assert it stays under the parent Feature's 200 ms budget.

### Acceptance Test Mapping

| BDD Scenario | Test Method Name | Test Type |
|--------------|------------------|-----------|
| Scenario 1: A Global Lock Date closes the filed fiscal year of one company and leaves its subsidiary open | `test_global_lock_date_closes_filed_year_and_scopes_to_company` | Acceptance |
| Scenario 2: A Tax Return Lock Date closes a submitted VAT period with the tax split held apart | `test_tax_return_lock_date_refuses_tax_bearing_entry_with_split_held_apart` | Acceptance |
| Scenario 3: A Hard Lock Date moved backwards is refused and the stored value survives | `test_hard_lock_date_backward_change_refused_and_value_retained` | Acceptance |
| Scenario 4: A balanced entry dated inside the locked period is refused and left in Draft | `test_balanced_entry_in_locked_period_refused_and_left_in_draft` | Acceptance |
| Scenario 5: A time-boxed lock exception admits one entry, records who granted it, and then expires | `test_time_boxed_lock_exception_admits_entry_then_expires` | Acceptance |

---

## Definition of Done

### Implementation Checklist

- [ ] All five acceptance-criteria scenarios pass, each proved by its named automated test in § Acceptance Test Mapping.
- [ ] **80% minimum test coverage achieved** for the functionality delivered by this story, reported by the repository's coverage tooling (C-007).
- [ ] Unit tests written and passing for per-user lock-date resolution, the guards that refuse a lock change, and the transition of an exception from active to expired.
- [ ] Integration tests written and passing for the refused and permitted postings, the tax-statement refusal, the grant-and-expiry cycle, the re-creation of a live grant when the stored value moves, and the Trial Balance read before and after each attempt.
- [ ] The five lock dates are administered per company and reproduced independently on **Acme Industries Inc.**, with no value of one company read from the other.
- [ ] The closing calendar states, per company and per period, which lock date is applied on which date against which statutory filing, and it is signed off by the Group Controller.
- [ ] The exception policy is recorded — who grants, who receives, the maximum validity in hours, the reason a grant must carry, and the review of every grant at the following close — and countersigned by the Finance SME.
- [ ] The control is handed to FEATURE-001-07 as the final step of the period-close checklist and the moment SM-003 and SM-004 are measured from, and the hand-over is recorded against ORD-004.

### Accounting Reconciliation Gate

This gate is the accounting contract of the story. Each item is asserted as an amount, in the currency named, rounded to 2 decimal places using half-up rounding.

- [ ] **Debits equal credits on every entry permitted after a lock change.** The entry dated 02 January 2026 posts with total debits of **USD 2,400.00** equal to total credits of **USD 2,400.00**; the entry of **Acme Industries Inc.** dated 15 December 2025 posts at **USD 900.00** on each side; the invoice dated 01 December 2025 posts at **USD 60,500.00** on each side; the entry admitted by the release posts at **USD 2,400.00** on each side; and the reversal of Edge Case 4 posts at **USD 6,000.00** on each side — every one a difference of **USD 0.00**, each amount rounded to 2 decimal places using half-up rounding.
- [ ] **The refused entry is proved balanced before it is refused.** The draft dated 15 December 2025 carries total debits of **USD 2,400.00** equal to total credits of **USD 2,400.00**, rounded to 2 decimal places using half-up rounding, so its refusal is attributable to the Global Lock Date of **31 December 2025** and not to an imbalance, and those totals are unchanged after the refusal.
- [ ] **The tax amount ties to its tax code and base amount.** Tax code **`VAT-STD-21`** on a **base amount of USD 50,000.00** yields a **tax amount of USD 10,500.00**, held on its own line and rounded to 2 decimal places using half-up rounding; that tax amount equals the movement on tax control account **2200 Tax Payable** for the same date range at a difference of **USD 0.00**; and the amount on the submitted VAT return for 01 November 2025 to 30 November 2025 still ties to account 2200 at **USD 10,500.00** after the refused invoice (SM-010).
- [ ] **The locked period reports the same figures before and after a blocked attempt.** The **Trial Balance** of **Acme Group NV** for **01 December 2025 to 31 December 2025** reports account **2000 Accounts Payable** at a credit of **USD 540,400.00** and total debits of **USD 4,875,300.00** equal to total credits of **USD 4,875,300.00** both before and after the refused posting, and the **Trial Balance** for **01 November 2025 to 30 November 2025** reports account **2200 Tax Payable** at a credit of **USD 10,500.00** in both runs.
- [ ] **Every report line ties to the sub-ledger.** Each Trial Balance line cited above equals the sum of the posted `account.move.line` records for that account and that date range at a difference of **USD 0.00**, so the refusal is proved at the sub-ledger and not only at the report.
- [ ] **A permitted release changes the ledger by exactly the entry it admitted.** After the release, account **2000 Accounts Payable** reads a credit of **USD 542,800.00** — the **USD 540,400.00** before it plus the **USD 2,400.00** admitted — and total debits of **USD 4,877,700.00** equal total credits of **USD 4,877,700.00**, a difference of **USD 0.00**, each amount rounded to 2 decimal places using half-up rounding, with no other line moved.
- [ ] **Trial Balance integrity survives every lock change.** For each company and each period touched by this story, total debits equal total credits with a difference of **USD 0.00**, before the lock is applied, after it is applied, after a refused attempt and after a released posting — the per-period form of SM-006.

### Compliance Checklist

- [ ] Licence compatibility verified per C-001 and C-002: an AGPL-3.0 compatible licence declared, and the LGPL-3 licence of `account` respected by every derived work.
- [ ] No parallel period-status or lock table introduced; the control stays on the existing company fields, the existing exception record and the existing posting validations (C-012).
- [ ] The access-rights matrix is exercised by test (C-014): the Group Controller grants a release, the Chief Accountant posts under one but cannot grant one, no role edits or deletes an exception, the External Auditor holds read-only access to lock dates and exceptions, and a role restricted to **Acme Group NV** can neither read nor amend the lock dates of **Acme Industries Inc.** (D-007).
- [ ] Every refusal message names the lock-date field, its date and the company affected, and discloses no stack trace, SQL, path or credential (C-020).
- [ ] Static analysis passes with the repository's configured tooling at zero violations, and the code follows Odoo and OCA standards (C-005, C-006).
- [ ] The confirmed platform version and edition, once DEC-001 and DEC-002 are recorded, are restated in the parent Feature and the field names, labels and refusal messages asserted here are re-checked against them (C-010, C-011).
- [ ] The internal-control evidence a SOX Section 404 assessment tests is in place for the close control: the lock-date change history, the exception register with grantor, grantee, scope, reason and expiry, and the journal items touched under each release.
- [ ] Code reviewed and approved, with each company's Hard Lock Date countersigned by the Finance SME before it is set.

### Documentation Checklist

- [ ] Docstrings and inline comments complete for every public method delivered.
- [ ] The closing calendar is documented alongside the code that enforces it: which lock date is applied at which stage of the close, on which date, per company.
- [ ] The five fields are documented for the operating team by the behaviour each governs — the global lock over every entry, the tax lock over entries affecting the tax report, the sales and purchase locks over one document side each, and the hard lock as the irreversible one that admits no exception.
- [ ] The exception policy and its audit trail are documented: who grants, who receives, how long a grant lasts, what reason it carries, how it expires, and where the items posted under it are read.
- [ ] The two behaviours of Edge Case 5 are documented side by side — an invoice or bill dated inside a lock has its accounting date moved past it, while a manual entry is refused — so a moved date is not read as a lost entry.
- [ ] The irreversibility of the Hard Lock Date is documented for stakeholders before the first one is set, together with the operational sequence its guards imply: drafts resolved and bank statement lines reconciled first.

### Quality Checklist

- [ ] No critical or high-severity defect open against the lock-date administration, the exception workflow or the refusal messages.
- [ ] Lock-date validation adds under 200 ms to a single posting with all five fields administered, the parent Feature's validation-overhead budget, and the **Trial Balance** runs cited above stay inside the Epic's budget of under 5 minutes per statement (SM-005).
- [ ] Access rights verified per finance role, with the granting role and the posting role held apart in the matrix rather than in guidance.
- [ ] Every lock-date change and every exception grant and revocation is retained with its author and timestamp and is readable by the External Auditor without a data request.
- [ ] **Demonstrated in the Odoo user interface to the Finance Controller and the Product Owner** by walking the seven steps of § Demonstration — the lock-date configuration screen at **Accounting ▸ Accounting ▸ Lock Dates**, the Global Lock Date set to 31 December 2025, the refused posting in **Accounting ▸ Accounting ▸ Journal Entries** with its validation message, the Trial Balance unmoved before and after, the tax lock and its refused invoice, the time-boxed release and the entry it admits, and the negative walkthrough over the Hard Lock Date and the expired release — with the walkthrough recorded against this story.

---

## References

### Accounting Standards

| Standard | Reference | Application to This Story |
|----------|-----------|---------------------------|
| IAS 1 | Presentation of Financial Statements, IFRS Foundation | A complete set of statements is presented for a stated period; closing that period to further posting is what keeps the issued statements and the ledger in agreement, and any adjustment arriving afterwards is recognized and disclosed in an open period |
| IAS 10 | Events after the Reporting Period, IFRS Foundation | Distinguishes an event that adjusts the reported period from one that does not, which is the accounting test behind granting or refusing a release into a closed period (Scenario 5) |
| ASC 250 | FASB Accounting Standards Codification, Accounting Changes and Error Corrections | Governs how a correction to a period already reported is presented, which is why Edge Case 4 reverses forward into an open period instead of amending a locked entry |
| SOX Section 404 | Sarbanes-Oxley Act of 2002, Section 404 — Management Assessment of Internal Controls | The period lock is a financial-close control whose design and operating effectiveness are assessed; the lock-date change history, the exception register and the items posted under each release are the evidence that assessment reads |
| COSO Internal Control — Integrated Framework | Committee of Sponsoring Organizations of the Treadway Commission | Frames the control activity and the segregation of duties this story implements: the role that grants a release is not the role that posts under it |
| IFRS Foundation standards | <https://www.ifrs.org/issued-standards/list-of-standards/> | Source of the presentation and post-reporting-period requirements cited above |
| FASB Accounting Standards Codification | <https://asc.fasb.org/> | Source of the US GAAP treatment of corrections to a reported period |

### OCA Modules (Reference)

| Repository | Module | Relevance |
|------------|--------|-----------|
| OCA/account-financial-tools | `account_lock_date_update` | Alters who may change a lock date; assessed against the segregation of duties this story requires before it is adopted |
| OCA/account-financial-tools | `account_move_line_no_delete` | Prevents deletion of journal items, complementing a control that refuses change to posted data |
| OCA/account-closing | `account_fiscal_year_closing` | Templated year-end closing whose closing moves have to post before the boundary they close is locked |
| OCA/account-financial-reporting | `account_financial_report` | Trial Balance and General Ledger from date-range parameters, the alternative verification surface if DEC-002 selects the OCA path |

### Source Code References

| Path | Relevance |
|------|-----------|
| `addons/account/models/company.py` | The five lock-date fields on `res.company` — `fiscalyear_lock_date` (Global Lock Date), `tax_lock_date` (Tax Return Lock Date), `sale_lock_date` (Sales Lock Date), `purchase_lock_date` (Purchase Lock date) and `hard_lock_date` (Hard Lock Date, documented as irreversible and admitting no exception) — each change-tracked on a company that inherits the messaging mixin; the computed `user_fiscalyear_lock_date`, `user_tax_lock_date`, `user_sale_lock_date`, `user_purchase_lock_date` and `user_hard_lock_date` counterparts that resolve the effective lock for the current user across the company and its parents; the validation that refuses lowering or removing the hard lock, refuses a hard lock over a period holding draft entries and refuses a lock over a period holding unreconciled bank statement lines; the collection of violated lock dates by accounting date, journal type and tax involvement; and the write path that re-creates live exceptions when a stored lock date moves |
| `addons/account/models/account_lock_exception.py` | The `account.lock_exception` record: its company, the user it is valid for, its reason, its end date, the lock-date field it changes, the changed and original lock dates, its computed active-revoked-expired state, the message it posts on the company's history when granted, the refusal to duplicate it, the revocation restricted to the accounting-manager group, and the retrieval of the journal items touched while it was in force |
| `addons/account/models/account_move.py` | The constraint that refuses adding or modifying an entry inside a locked period with the violated lock dates named, the write and post paths it runs on, the computed lock-date warning shown on a draft document, and the accounting-date derivation that moves an invoice or bill past the lock instead of refusing it — the behaviour of Edge Case 5 |
| `addons/account/models/account_move_line.py` | The journal-item check that refuses an operation which would affect an already issued tax statement and names the Tax Return Lock Date to change — the mechanism of Scenario 2 — and the posted sub-ledger the Trial Balance sums |
| `addons/account/security/ir.model.access.csv` | The access rights over the exception record: read for every internal user, read and create for the accounting-manager group, with no write and no delete for anyone — the immutability the audit trail of Scenario 5 rests on |
| `addons/account/views/account_lock_exception_views.xml` | The exception form showing the grantor, the grantee, the reason, the creation and end dates, the changed lock date against the original, the revocation action and the audit view of the items posted under the grant |
| `addons/account/wizard/account_move_reversal.py` | Reversal date selection and its validation against the lock dates, and the link a reversal keeps to the entry it reverses (Edge Case 4) |
| `addons/account/wizard/account_secure_entries_wizard.py` | The securing of posted entries and its use of the effective hard lock date, the second half of the control set the External Auditor reads |
| `addons/account/views/res_config_settings_views.xml` | The Fiscal Periods block of the accounting settings page, where the fiscal-period configuration sits in this baseline and where the lock-date surface is settled by DEC-002 |
| `addons/account_financial_report_ce/models/trial_balance.py` | The Trial Balance with its date range and its opening-balance cut, the report every "unchanged before and after" assertion is read from |
| `addons/account/__manifest__.py` | The `account` module identity cited in the constraints: "Invoicing", version 1.4, category `Accounting/Accounting`, licence LGPL-3 |
| `odoo/release.py` | The platform baseline `version_info = (19, 0, 0, FINAL, 0, '')` cited by DEC-001 |

### Ticket References

| Document | Link |
|----------|------|
| Parent Feature | [FEATURE-001-01: Chart of Accounts & Fiscal Year](../FEATURE-001-01-chart-of-accounts-fiscal-year.md) |
| Parent Epic | [EPIC-001: Enterprise Accounting in Odoo](../../EPIC-001-enterprise-accounting-odoo.md) |
| Persona register the WHO is drawn from | [EPIC-001 §3.1 User Personas](../../EPIC-001-enterprise-accounting-odoo.md#31-user-personas) |
| Success metrics SM-003, SM-004, SM-006 and SM-016, which this control is measured through | [EPIC-001 §4.1 Measurable Outcomes](../../EPIC-001-enterprise-accounting-odoo.md#41-measurable-outcomes) |
| Authoring bounds: 4-to-8 criteria, coverage distribution, Fibonacci scale | [EPIC-001 §5.3 Decomposition Guidelines](../../EPIC-001-enterprise-accounting-odoo.md#53-feature-and-story-decomposition-guidelines) |
| Ordering rules ORD-002, ORD-004 and ORD-005, which route through this control | [EPIC-001 §6.2 Inter-Feature Ordering](../../EPIC-001-enterprise-accounting-odoo.md#62-inter-feature-ordering) |
| Constraint set C-001 to C-022 | [EPIC-001 §7 Constraints](../../EPIC-001-enterprise-accounting-odoo.md#7-constraints) |
| Epic Definition of Done item 6, which requires the lock dates applied and post-lock postings blocked | [EPIC-001 §13 Epic-Level Definition of Done](../../EPIC-001-enterprise-accounting-odoo.md#13-epic-level-definition-of-done) |
| Open decisions DEC-001 and DEC-002 | [EPIC-001 Appendix B: Open Decisions Register](../../EPIC-001-enterprise-accounting-odoo.md#appendix-b-open-decisions-register) |
| Blocking sibling | [STORY-001-01-03: Define Fiscal Year and Accounting Periods](./STORY-001-01-03-define-fiscal-year-periods.md) |
| Related sibling, whose Scenario 7 mirrors this control | [STORY-001-01-04: Import Legacy Chart of Accounts and Opening Balances](./STORY-001-01-04-import-legacy-coa.md) |
| Sibling stories supplying the accounts and their presentation | [STORY-001-01-01](./STORY-001-01-01-configure-coa-hierarchy.md) · [STORY-001-01-02](./STORY-001-01-02-map-accounts-ifrs-gaap-taxonomy.md) |

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-01 | Enterprise Accounting Team | Initial story creation |

---

## Notes

**Platform version and edition remain open (DEC-001, DEC-002).** The originating programme request names Odoo 17, this repository is Odoo 19.0 Community, and the prior superseded backlog targeted 18.0. This story states the five field names, their labels, the refusal messages and the exception fields as they exist in the 19.0 baseline it was verified against, and flags the mismatch for stakeholder confirmation rather than choosing a target. The edition decision does not gate the control: the five lock-date fields, their computed per-user counterparts and the lock-exception record were all read in `addons/account` in this Community repository, so the behaviour every criterion asserts is deliverable here. What DEC-002 settles is narrower — the screen the values are maintained on, since no dedicated lock-date screen ships in this Community baseline, and the engine that renders the verifying Trial Balance, for which the AGPL-3 `account_financial_report_ce` add-on present here supplies the date-range parameter the criteria cite.

**The Hard Lock Date is a one-way decision and needs stakeholder communication before the first one is set.** Once written it cannot be lowered, cannot be cleared and admits no exception — not for the Group Controller, not for an administrator. That is its value as an assertion to an auditor and its risk to an unprepared finance team: an audit adjustment arriving after a hard lock has no release path and can only be presented in an open period. The programme therefore treats the four soft locks as the working close control and the Hard Lock Date as the post-filing seal, applied on the Finance SME's countersignature after the statutory filing is complete and after the guards it enforces are satisfied — every draft in the period resolved and every bank statement line in it reconciled.

**A release is a recorded event, not a relaxation.** The exception mechanism deliberately changes the effective lock date for one named user, for one lock-date field, in one company, until one stated moment, and leaves the administered value untouched for everyone else. Two consequences are worth stating to stakeholders: the value shown on the company record is not what every user experiences while a grant is live (Edge Case 2), and moving the administered value while a grant is live leaves two exception records rather than one silently re-scoped record. Both are properties the audit trail depends on, and both are asserted by tests rather than described in guidance.

**This story completes FEATURE-001-01.** With it, the feature's five stories cover the whole configuration foundation: the account hierarchy (STORY-001-01-01), its IFRS and US GAAP presentation taxonomy (STORY-001-01-02), the fiscal calendar (STORY-001-01-03), the migrated opening position (STORY-001-01-04) and the closing controls that protect what has been reported from all four (this story). The parent Feature declares a Story Count of 5, so no sibling is added here; the period-close checklist that ends by applying these lock dates, and the deferral cutoff dated on the boundary they close, are authored in FEATURE-001-07 and referenced by identifier rather than linked.

**One deliberate identifier correction.** Programme documents preceding this ticket render the lock-exception model as `account.lock.exception`. The model read in this repository during discovery is named `account.lock_exception` and is defined in `addons/account/models/account_lock_exception.py`; the verified identifier is used throughout this ticket, and the equivalence is stated in § Technical Discovery Notes so a reader searching for either form finds the same record. The same care applies to the refusal wording: the Odoo lock-date message names the lock-date field and the lock date it holds, so each criterion names that value alongside the accounting date of the entry being refused rather than the entry date alone.

**No user-specified rules govern this file.** The rules input for this change returned an empty set, so no project-specific rule constrains this ticket, none has been invented, and the authoring bar is not lowered on that account. The governing constraints applied here are the Epic's own and were each verified against this file before it was published: the naming convention and nested layout, the 4-to-8 criteria bound with its coverage distribution from [§5.3](../../EPIC-001-enterprise-accounting-odoo.md#53-feature-and-story-decomposition-guidelines), the ban on unquantified qualifiers, monetary precision in USD at 2 decimal places with half-up rounding, the debits-equal-credits assertion on every entry-bearing criterion, INVEST conformance, demonstrability in the Odoo user interface, the single named finance persona, referential integrity across the epic-feature-story tree, accounting determinism, the constraint set of [§7](../../EPIC-001-enterprise-accounting-odoo.md#7-constraints), the 80% coverage gate, and the section structure of `tickets/templates/story-template.md`.
