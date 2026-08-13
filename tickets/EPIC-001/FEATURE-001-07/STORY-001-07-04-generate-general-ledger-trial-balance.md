# STORY-001-07-04: Generate General Ledger and Trial Balance

---

## Metadata

| Attribute | Value |
|-----------|-------|
| **Story ID** | `STORY-001-07-04` |
| **Title** | Generate General Ledger and Trial Balance |
| **Parent Feature** | [FEATURE-001-07: Financial Reporting & Period Close](../FEATURE-001-07-financial-reporting-period-close.md) |
| **Parent Epic** | [EPIC-001: Enterprise Accounting in Odoo](../../EPIC-001-enterprise-accounting-odoo.md) |
| **Persona** | Chief Accountant (primary) — with the External Auditor as the secondary consumer of the General Ledger and of every drill-down, and the Financial Reporting Manager as the consumer of the tie-out |
| **Status** | Draft |
| **Priority** | 🔴 Critical |
| **Estimate** | 8 story points (Fibonacci) |
| **Feature Capability** | CAP-004 — generate the General Ledger and the Trial Balance with debit and credit verification |
| **Epic Success Metric** | SM-006 — the Trial Balance difference is asserted as an amount per company and per period, which is the metric this story is the instrument of; SM-001 — the General Ledger and the Trial Balance are 2 of the 7 reports producible for a named company and a named period; SM-005 — each report is produced in under 5 minutes for a named company and date range; SM-016 — post-close audit adjustments are halved, which an entry-level ledger trail is what makes testable |
| **Owner/Author** | Enterprise Accounting Team |

This is the **sub-ledger surface of FEATURE-001-07**, and it is the first of the feature's five stories to be delivered. The Balance Sheet of [STORY-001-07-01](./STORY-001-07-01-generate-balance-sheet.md), the Profit & Loss of [STORY-001-07-02](./STORY-001-07-02-generate-profit-loss.md) and the Cash Flow Statement of [STORY-001-07-03](./STORY-001-07-03-generate-cash-flow-statement.md) each aggregate the same posted journal items that these two reports present at a lower level of aggregation, and each is reconciled back to the Trial Balance rather than to a second aggregation of its own. The close executed by [STORY-001-07-05](./STORY-001-07-05-execute-period-close-deferrals.md) reads the Trial Balance difference before it applies a lock date. **This story therefore owns the canonical assertion of the whole feature: that total debits equal total credits.** Scenario 2 states that equality as an amount, and every statement above it inherits the result rather than re-proving it.

Both reports are read-only against the ledger. Neither creates, alters nor reverses a journal entry: the journal-entry count and the account balances of the reported company and date range are identical before and after a run, and only [STORY-001-07-05](./STORY-001-07-05-execute-period-close-deferrals.md) writes into the period.

> **Monetary and date conventions used throughout this ticket.** Every amount is stated in USD, carried to 2 decimal places, and rounded half-up at the USD rounding increment of 0.01 (ISO 4217 currency code `USD`). Where a company reports in a functional currency other than USD, the same assertion is made in that currency at that currency's own decimal precision, and a journal item held in a currency other than the company currency is presented at its company-currency equivalent with the original currency alongside it. Every date is stated as an explicit calendar date in ISO 8601 form rather than as a relative period. Every account is named by the code of the mandated chart — Bank **1010**, Accounts Receivable **1200**, Prepaid / Deferred Expense **1400**, Fixed Assets **1500**, Accumulated Depreciation **1590**, Accounts Payable **2000**, Tax Payable **2200**, Deferred Revenue **2300**, Share Capital **3000**, Retained Earnings **3100**, Revenue **4000**, Expense **6100** and Depreciation Expense **6500** — together with Suspense **1099**, which is owned by [FEATURE-001-04](../FEATURE-001-04-bank-reconciliation-cash-management.md) and cited here only where a zero-balance account is the subject of the assertion. Every tax figure is stated as three separate values: the tax code, the base amount and the tax amount.

---

## User Story

**As a** Chief Accountant

**I want** the **General Ledger** and the **Trial Balance** produced from the posted `account.move.line` population of one named company for one named date range — the General Ledger grouping every posted journal item under its `account.account` with the item's date, entry reference, label, partner, debit, credit and running balance, preceded by an opening-balance line for each balance-forward account; and the Trial Balance presenting the same population aggregated to one row per account with its opening balance, period debit, period credit and closing balance, a difference column, an account-type filter, an include-zero-balance option and a comparative prior period

**So that** I can prove that total debits equal total credits at a difference of `$0.00 USD` before any statement leaves the finance function, locate the posting error behind a difference at the account and at the entry that caused it rather than by re-adding the books, and answer an audit query from the ledger itself — which is what allows the close to run in 5 business days instead of 10 (SM-003), the statement set to be published within 24 hours of the lock date (SM-004), and post-close audit adjustments to fall by half (SM-016).

### Demonstration Path

The outcome is observable by the Finance Controller and by the Product Owner in a database loaded with the deterministic fixture named in § Test Requirements, without a developer present:

- In **Accounting → Reporting**, with the **General Ledger** selected for company `US-01` and the date range 2025-01-01 to 2025-03-31, the report presents the Bank **1010** group opening at `$196,450.00 USD` and closing at `$248,300.00 USD`, and the Accounts Receivable **1200** group opening at `$2,000,000.00 USD` and closing at `$2,093,811.88 USD`, each amount rounded half-up to 2 decimal places at the USD rounding increment of 0.01.
- In the same menu, with the **Trial Balance** selected for the same company and the same date range, the report presents total debits of `$8,284,600.00 USD` equal to total credits of `$8,284,600.00 USD` and a difference column reading `$0.00 USD`, and its Bank **1010** and Accounts Receivable **1200** closing balances are the two figures the General Ledger closed at.
- Selecting the Trial Balance closing line for Accounts Receivable **1200** presents the journal items behind it, whose signed sum is the `$2,093,811.88 USD` the line was opened from, which is the trail the **External Auditor** accepts under Epic Definition of Done item 10.
- The same two results are readable through the Odoo ORM and the external API for the same parameters, so the demonstration does not depend on the screen.
- Before and after both runs, the posted journal-entry count and every account balance of company `US-01` for that range are unchanged, which is what makes the demonstration repeatable.

---

## INVEST Principles Compliance

| Principle | Compliance | Notes |
|-----------|------------|-------|
| **Independent** | ✅ | The story has no predecessor inside FEATURE-001-07. It reads posted journal data alone, so it is developed and demonstrated against the ledger produced by the sub-ledger features — the chart of accounts, account types and fiscal calendar published by [FEATURE-001-01](../FEATURE-001-01-chart-of-accounts-fiscal-year.md) and the postings made in FEATURE-001-02, FEATURE-001-03, FEATURE-001-04, FEATURE-001-08 and FEATURE-001-09 — rather than against another report. Nothing in the three statement stories is needed for it to be built or accepted; the coupling runs the other way, because they are reconciled to it. |
| **Negotiable** | ✅ | The outcome is fixed and the mechanism is open. That the General Ledger groups items under their account with a running balance and an opening-balance line, and that the Trial Balance proves debit and credit equality at account level, are not negotiable. Whether the running balance is computed in the report layer or read from a computed field, whether the two reports share one data source or two, whether presentation is a list view, a QWeb rendering or a client-side report, and which of the OCA modules in § Technical Discovery Notes is extended rather than replaced, are all settled in discovery with the Chief Accountant and the Financial Reporting Manager. |
| **Valuable** | ✅ | Without this story every other statement in the feature is unverifiable: a Balance Sheet can present a total without anything proving the books behind it balance, and an auditor has no path from a published figure to the entry that produced it. The Trial Balance difference is the instrument SM-006 is read from and the gate [STORY-001-07-05](./STORY-001-07-05-execute-period-close-deferrals.md) checks before a lock date is applied, and the General Ledger is the evidence that turns a post-close audit query into a lookup rather than a re-performance (SM-016). |
| **Estimable** | ✅ | The deliverable is countable: 2 reports, 4 parameters shared between them (company, date range, account or account-type filter, comparative period), 7 General Ledger columns, 4 Trial Balance value columns plus a difference column, 1 include-zero-balance option, 1 centralized-journal aggregation rule, 1 drill-down surface and 2 export formats inherited from the feature convention. Every account, amount and tie-out asserted below is fixed in advance in the figure table, so no criterion waits on an open decision. It is sized at 8 Fibonacci points with the rationale in § Estimation. |
| **Small** | ✅ | The two reports are **one** sprint-sized outcome rather than two, and the merge of the superseded pair is justified rather than assumed: both read the identical population — posted `account.move.line` records of one company inside one date range — over the identical date-range and filter parameters, and they differ only in the level at which that population is aggregated. The Trial Balance is the General Ledger summed to one row per account, which is why the two must tie to each other at a difference of `$0.00 USD`, and delivering them apart would mean building the same account-level aggregation twice and reconciling two implementations instead of one. Scope stays inside these two reports: the Balance Sheet, the Profit & Loss, the Cash Flow Statement and the close belong to the four sibling stories, and receivables ageing belongs to [STORY-001-03-05](../FEATURE-001-03/STORY-001-03-05-report-aged-receivables.md). |
| **Testable** | ✅ | Every criterion below resolves to an amount, a date, a count or a refusal: an opening balance of `$196,450.00 USD`, a closing running balance of `$248,300.00 USD`, total debits of `$8,284,600.00 USD` against total credits of `$8,284,600.00 USD` at a difference of `$0.00 USD`, a tax amount of `$129,195.00 USD` on a base amount of `$1,782,000.00 USD` at tax code `ST-CA-0725`, a report of 0 lines with totals of `$0.00 USD`, a rejected date range that produces no report, and a drilled item set summing to `$2,093,811.88 USD`. Each of the 8 scenarios maps to exactly 1 named automated test in § Test Requirements, so pass and fail are decided without judgement (C-008, C-009). |

---

## Acceptance Criteria

Eight criteria are authored, inside the 4-to-8 bound the Epic sets in [§5.3](../../EPIC-001-enterprise-accounting-odoo.md#53-feature-and-story-decomposition-guidelines), and they carry the mandated coverage distribution: **Scenarios 1, 2, 3 and 4 are valid-input cases** (the General Ledger of a bank account, the Trial Balance of the whole chart with its debit and credit equality, the opening-balance treatment of a balance-forward account beside a period-reset account, and the tax row with its base and tax amounts held apart), **Scenario 5 is the invalid-input case** (a date range whose end precedes its start), **Scenario 6 is the error-handling case** (a fiscal year holding no posted entry), **Scenario 7 is the accounting edge case** (an account with no period movement and a non-zero opening balance, beside an account whose balance is `$0.00 USD`), and **Scenario 8 is the audit-trail case** (a report line resolved down to the journal items that compose it).

Each scenario states its parameters in its **Given** and reduces its **When** to the single act of requesting the report, so no criterion depends on another having run first and no criterion carries two triggers. Two conventions hold across all eight: every journal entry contributing to either report is itself posted with **total debits equal to its total credits at a difference of `$0.00 USD`**, so a difference in a report is attributable to the report and never to an unbalanced entry; and both reports are scoped to the books of the single company named in the criterion, `US-01`, with a consolidated scope produced only through [FEATURE-001-06](../FEATURE-001-06-multi-company-consolidation.md) and never inferred by summing entities here.

### Reference figure set

Every figure asserted below is drawn from one deterministic population: the posted `account.move.line` records of **Global Holdings Inc. (`US-01`)**, functional currency USD, for the date range **2025-01-01 to 2025-03-31** (the first quarter of fiscal year 2025, whose first day is the fiscal-year start). Amounts are rounded half-up to 2 decimal places at the USD rounding increment of 0.01.

| Account | Opening balance (USD) | Period debit (USD) | Period credit (USD) | Closing balance (USD) |
|---------|---------------------:|-------------------:|--------------------:|----------------------:|
| Bank **1010** | $196,450.00 Dr | $1,817,383.12 | $1,765,533.12 | **$248,300.00 Dr** |
| Accounts Receivable **1200** | $2,000,000.00 Dr | $1,911,195.00 | $1,817,383.12 | **$2,093,811.88 Dr** |
| Prepaid / Deferred Expense **1400** | $40,000.00 Dr | $0.00 | $21,511.88 | **$18,488.12 Dr** |
| Fixed Assets **1500** | $4,117,000.00 Dr | $265,000.00 | $0.00 | **$4,382,000.00 Dr** |
| Accumulated Depreciation **1590** | $1,786,000.00 Cr | $0.00 | $144,000.00 | **$1,930,000.00 Cr** |
| Accounts Payable **2000** | $1,218,345.00 Cr | $1,305,083.12 | $1,371,038.12 | **$1,284,300.00 Cr** |
| Tax Payable **2200** | $157,705.00 Cr | $100,000.00 | $129,195.00 | **$186,900.00 Cr** |
| Deferred Revenue **2300** | $201,400.00 Cr | $60,000.00 | $0.00 | **$141,400.00 Cr** |
| Share Capital **3000** | $2,000,000.00 Cr | $0.00 | $0.00 | **$2,000,000.00 Cr** |
| Retained Earnings **3100** | $990,000.00 Cr | $90,000.00 | $0.00 | **$900,000.00 Cr** |
| Revenue **4000** | $0.00 | $0.00 | $1,842,000.00 | **$1,842,000.00 Cr** |
| Expense **6100** | $0.00 | $1,398,000.00 | $0.00 | **$1,398,000.00 Dr** |
| Depreciation Expense **6500** | $0.00 | $144,000.00 | $0.00 | **$144,000.00 Dr** |
| **Totals** | **$6,353,450.00 Dr = $6,353,450.00 Cr** | **$7,090,661.24** | **$7,090,661.24** | **$8,284,600.00 Dr = $8,284,600.00 Cr** |

Three properties of this population are asserted rather than assumed, and each is checked by the tests in § Test Requirements:

- **The population balances in all three column pairs.** Opening debits of `$6,353,450.00 USD` equal opening credits of `$6,353,450.00 USD`; period debits of `$7,090,661.24 USD` equal period credits of `$7,090,661.24 USD`; closing debits of `$8,284,600.00 USD` equal closing credits of `$8,284,600.00 USD`. Each pair is a difference of `$0.00 USD`.
- **Revenue 4000, Expense 6100 and Depreciation Expense 6500 open at `$0.00 USD`** because income and expense accounts carry no balance across the fiscal-year boundary, while the ten balance-forward accounts open at the closing position of fiscal year 2024.
- **The closing column reconciles to the statements of the sibling stories** at a difference of `$0.00 USD`: total assets of `$4,812,600.00 USD` (Bank 1010 plus Accounts Receivable 1200 plus Prepaid / Deferred Expense 1400 plus Fixed Assets 1500 less the contra Accumulated Depreciation 1590) equal total liabilities of `$1,612,600.00 USD` plus total equity of `$3,200,000.00 USD`, where equity is Share Capital 3000 of `$2,000,000.00 USD` plus Retained Earnings 3100 of `$900,000.00 USD` plus current-year earnings of `$300,000.00 USD`, and current-year earnings are Revenue 4000 of `$1,842,000.00 USD` less Expense 6100 of `$1,398,000.00 USD` less Depreciation Expense 6500 of `$144,000.00 USD`.

### Scenario 1: The General Ledger presents a bank account from its opening balance to its closing running balance

- **Given** the posted journal population of company `US-01` for 2025-01-01 to 2025-03-31 is the reference figure set above, and every `account.move` contributing to it is in state Posted with its own total debits equal to its own total credits at a difference of `$0.00 USD`; Bank **1010** is a balance-forward account whose fiscal-year 2024 closing position is `$196,450.00 USD` debit; and the **General Ledger** parameters are company `US-01`, the date range 2025-01-01 to 2025-03-31, the account filter Bank **1010**, and no comparative period
- **When** the **General Ledger** is requested for those parameters
- **Then** the report presents one account group for Bank **1010** in which an opening-balance line dated 2025-01-01 states `$196,450.00 USD` debit ahead of the first item of the period; every item of that group carries its accounting date, the reference of the journal entry that produced it, its label, its partner where the item records one, its debit and its credit; the group's in-period debits total `$1,817,383.12 USD` and its in-period credits total `$1,765,533.12 USD`; the running balance carried on the last item of the group reads `$248,300.00 USD` debit and equals the opening balance plus in-period debits less in-period credits at a difference of `$0.00 USD`; each amount is rounded half-up to 2 decimal places at the USD rounding increment of 0.01; that closing running balance equals the **Trial Balance** closing balance for Bank **1010** over the same company and date range at a difference of `$0.00 USD`; the reference on each line identifies the source journal entry the line came from, so the entry stands one step away from the ledger; and the count of posted journal entries and every account balance of company `US-01` for that range are the same after the run as before it

### Scenario 2: The Trial Balance proves that total debits equal total credits for the whole chart

- **Given** the posted journal population of company `US-01` for 2025-01-01 to 2025-03-31 is the reference figure set above, and every `account.move` contributing to it is in state Posted with its own total debits equal to its own total credits at a difference of `$0.00 USD`; and the **Trial Balance** parameters are company `US-01`, the date range 2025-01-01 to 2025-03-31, every account of the chart, the include-zero-balance option disabled, and no comparative period
- **When** the **Trial Balance** is requested for those parameters
- **Then** the report presents one row per account carrying that account's opening balance, period debit, period credit and closing balance exactly as stated in the reference figure set — Bank **1010** closing at `$248,300.00 USD` debit, Accounts Receivable **1200** at `$2,093,811.88 USD` debit, Accumulated Depreciation **1590** at `$1,930,000.00 USD` credit, Accounts Payable **2000** at `$1,284,300.00 USD` credit and Revenue **4000** at `$1,842,000.00 USD` credit among them; **total debits of `$8,284,600.00 USD` equal total credits of `$8,284,600.00 USD`**, and the difference column reads `$0.00 USD`; the opening columns likewise total `$6,353,450.00 USD` on both sides and the period movement columns `$7,090,661.24 USD` on both sides, each pair at a difference of `$0.00 USD`; each amount is rounded half-up to 2 decimal places at the USD rounding increment of 0.01; each row's closing balance equals the closing running balance the **General Ledger** presents for that account over the same company and date range at a difference of `$0.00 USD`; and the count of posted journal entries and every account balance of company `US-01` for that range are the same after the run as before it

### Scenario 3: A balance-forward account opens at its carried position while a period-reset account opens at zero

- **Given** the posted journal population of company `US-01` for 2025-01-01 to 2025-03-31 is the reference figure set above; Accounts Receivable **1200** is a balance-forward account whose fiscal-year 2024 closing position is `$2,000,000.00 USD` debit; Revenue **4000** is an income account that carries no balance across the fiscal-year boundary, so its position at 2025-01-01 is `$0.00 USD`; each receivable item of the period records the partner it was raised against; and the **General Ledger** parameters are company `US-01`, the date range 2025-01-01 to 2025-03-31, and the account filter Accounts Receivable **1200** together with Revenue **4000**
- **When** the **General Ledger** is requested for those parameters
- **Then** the Accounts Receivable **1200** group is preceded by an opening-balance line stating `$2,000,000.00 USD` debit, records in-period debits of `$1,911,195.00 USD` and in-period credits of `$1,817,383.12 USD`, and closes at a running balance of `$2,093,811.88 USD` debit; each of its lines presents the partner recorded on the item, so a receivable movement is readable by counterparty; the Revenue **4000** group is preceded by an opening-balance line stating `$0.00 USD`, records in-period credits of `$1,842,000.00 USD` and no in-period debit, and closes at a running balance of `$1,842,000.00 USD` credit; only the two requested accounts appear, and the remaining 11 accounts of the reference figure set are absent from the output; and each amount is rounded half-up to 2 decimal places at the USD rounding increment of 0.01

### Scenario 4: The Trial Balance tax row keeps the tax code, the base amount and the tax amount apart

- **Given** the posted journal population of company `US-01` for 2025-01-01 to 2025-03-31 is the reference figure set above; the output tax of the period was raised under tax code `ST-CA-0725` at 7.25% on a base amount of `$1,782,000.00 USD`, giving a tax amount of `$129,195.00 USD` recorded on its own journal item against Tax Payable **2200**; a remittance of `$100,000.00 USD` to the tax authority was posted through the **Bank** journal in the same period; and the **Trial Balance** parameters are company `US-01`, the date range 2025-01-01 to 2025-03-31 and the account filter Tax Payable **2200**
- **When** the **Trial Balance** is requested for those parameters
- **Then** the Tax Payable **2200** row presents an opening balance of `$157,705.00 USD` credit, a period debit of `$100,000.00 USD`, a period credit of `$129,195.00 USD` and a closing balance of `$186,900.00 USD` credit, each rounded half-up to 2 decimal places at the USD rounding increment of 0.01; the period credit of `$129,195.00 USD` resolves to tax items that each carry tax code `ST-CA-0725` and record the base amount they were computed on and the tax amount computed from it as two separate values, those base amounts totalling `$1,782,000.00 USD` and those tax amounts totalling `$129,195.00 USD`, so the tax code, the base amount and the tax amount are three readable values and no line presents a base amount and a tax amount added together; the tax amount of `$129,195.00 USD` is the base amount of `$1,782,000.00 USD` at 7.25% rounded half-up to 2 decimal places at the USD rounding increment of 0.01; and the closing balance of `$186,900.00 USD` is the figure the **VAT/Tax Return** of [FEATURE-001-05](../FEATURE-001-05-tax-configuration-compliance.md) reconciles to for the same company and the same date range at a difference of `$0.00 USD`

### Scenario 5: A date range whose end precedes its start is rejected and no report is produced

- **Given** the posted journal population of company `US-01` for 2025-01-01 to 2025-03-31 is the reference figure set above; and the **Trial Balance** parameters are company `US-01` with a range start of 2025-03-31 and a range end of 2025-01-01, so the end of the range falls before its start
- **When** the **Trial Balance** is requested for those parameters
- **Then** no report is produced — no row, no total and no partial output; the request is refused with a validation message that names the parameter at fault, the date range, and the check it failed, that the end of a range may not fall before its start; the message discloses no stack trace, no query text, no file-system path and no credential (C-015, C-019, C-020, C-022); no journal entry of company `US-01` is created, altered or reversed, and the count of posted journal entries and every account balance of that company are the same after the refusal as before it; and a subsequent request for the corrected range 2025-01-01 to 2025-03-31 produces the report of Scenario 2 with total debits of `$8,284,600.00 USD` equal to total credits of `$8,284,600.00 USD` at a difference of `$0.00 USD`, each amount rounded half-up to 2 decimal places at the USD rounding increment of 0.01

### Scenario 6: A fiscal year holding no posted entry returns an empty report rather than a partial one

- **Given** the ledger of company `US-01` holds no journal entry with an accounting date between 2023-01-01 and 2023-12-31, because the earliest posted entry of that company is the entry that carried its legacy balances into Odoo, dated 2024-01-01 under the migration mechanism defined by [STORY-001-01-04](../FEATURE-001-01/STORY-001-01-04-import-legacy-coa.md); the fiscal year 2025 population of the reference figure set stands posted and unchanged; and the **Trial Balance** parameters are company `US-01` and the date range 2023-01-01 to 2023-12-31
- **When** the **Trial Balance** is requested for those parameters
- **Then** the report is produced and states that the requested range holds no posted journal item; it presents 0 account rows, total debits of `$0.00 USD` equal to total credits of `$0.00 USD` and a difference column of `$0.00 USD`, each amount rounded half-up to 2 decimal places at the USD rounding increment of 0.01; no opening balance is carried into it from an adjacent period and no figure of the 2025-01-01 to 2025-03-31 population appears in it, so the output is an empty report rather than a partial one; the requested range is restated on the report beside that outcome, so an empty result is distinguishable from an unexecuted request; and no journal entry of company `US-01` is created, altered or reversed by the run

### Scenario 7: An account with no period movement carries its opening balance to closing, and a zero-balance account appears only when it is asked for

- **Given** the posted journal population of company `US-01` for 2025-01-01 to 2025-03-31 is the reference figure set above; Share Capital **3000** holds an opening balance of `$2,000,000.00 USD` credit and no journal item dated inside that range, so its period debit and its period credit are each `$0.00 USD`; Suspense **1099**, the account owned by [FEATURE-001-04](../FEATURE-001-04-bank-reconciliation-cash-management.md), holds an opening balance of `$0.00 USD`, no journal item inside the range and a closing balance of `$0.00 USD`; and the **Trial Balance** parameters are company `US-01`, the date range 2025-01-01 to 2025-03-31, every account of the chart and the include-zero-balance option enabled
- **When** the **Trial Balance** is requested for those parameters
- **Then** the Share Capital **3000** row is present with an opening balance of `$2,000,000.00 USD` credit, a period debit of `$0.00 USD`, a period credit of `$0.00 USD` and a closing balance of `$2,000,000.00 USD` credit, so a quarter of no movement carries the opening figure to closing unaltered; the Suspense **1099** row is present with `$0.00 USD` in each of its four columns; the report still reports total debits of `$8,284,600.00 USD` equal to total credits of `$8,284,600.00 USD` at a difference of `$0.00 USD`, because a row whose four columns are each `$0.00 USD` moves no total; the Suspense **1099** row is the one row whose presence turns on the include-zero-balance option, while the Share Capital **3000** row is present under either setting of that option because the account holds a balance even though it recorded no movement; and each amount is rounded half-up to 2 decimal places at the USD rounding increment of 0.01

### Scenario 8: A report line resolves to the journal items that compose it, and those items sum back to the line

- **Given** the **Trial Balance** of company `US-01` for 2025-01-01 to 2025-03-31 stands produced as in Scenario 2, with its Accounts Receivable **1200** closing line reading `$2,093,811.88 USD` debit; the population behind that line is an opening position of `$2,000,000.00 USD` debit together with in-period debits of `$1,911,195.00 USD` and in-period credits of `$1,817,383.12 USD`; the filters in force on that report are the company `US-01`, the date range 2025-01-01 to 2025-03-31 and the account; and the **External Auditor** holds read access to the books of that company
- **When** the journal items behind the Accounts Receivable **1200** closing line are opened from that line
- **Then** those items are presented, each stating the reference of its journal entry, its accounting date, its account and its amount, and each belonging to a journal entry whose own total debits equal its own total credits at a difference of `$0.00 USD`; the opening position of `$2,000,000.00 USD` debit plus in-period debits of `$1,911,195.00 USD` less in-period credits of `$1,817,383.12 USD` sums to `$2,093,811.88 USD`, equal to the line the detail was opened from at a difference of `$0.00 USD`, each amount rounded half-up to 2 decimal places at the USD rounding increment of 0.01; the company, date-range and account filters that produced the line govern the detail, so no item dated outside 2025-01-01 to 2025-03-31 and no item of another company is present; the detail carries the path back to the report it came from, and returning by that path presents the same report at the same position without it being produced a second time; the detail is available within 2 seconds of the line being opened; and no journal entry is created, altered or reversed by opening it

---

## Sub-Tasks

- [ ] **Specify the parameters and the columns of both reports** — company, date range, account and account-type filter, comparative period, include-zero-balance option and centralized-journal option for the Trial Balance; date, entry reference, label, partner, debit, credit and running balance for the General Ledger; and the difference column that carries the debit-and-credit equality — with each parameter's validation rule and each column's rounding behaviour stated in USD to 2 decimal places, half-up, at the rounding increment of 0.01. `@functional-consultant`
- [ ] **Analyse account types, internal groups and the balance-forward flag** in `addons/account` to establish which accounts open at their carried position and which open at `$0.00 USD` at the fiscal-year boundary, and record the account-type-to-grouping mapping consumed by the Trial Balance so one account cannot appear under two captions. `@developer`
- [ ] **Build the account-level aggregation and the running balance** so that the General Ledger presents an opening-balance line before the first item of the period for each balance-forward account, carries a running balance down each account group, and closes at the figure the Trial Balance reports for the same account and range at a difference of `$0.00 USD`. `@developer`
- [ ] **Build the Trial Balance opening, period-debit, period-credit, closing and difference columns**, together with the account-type filter, the include-zero-balance option and the comparative prior period with its absolute and percentage variance, where a prior-period balance of `$0.00 USD` presents no percentage rather than a division result. `@developer`
- [ ] **Implement the centralized-journal aggregation rule**: each centralized journal contributes one aggregated line per account per period, and that line's debit and credit totals equal the sum of the underlying journal items it stands for at a difference of `$0.00 USD`. `@developer`
- [ ] **Deliver the export and drill-down surface** inherited from the feature convention in [FEATURE-001-07 §4.1](../FEATURE-001-07-financial-reporting-period-close.md) — PDF carrying the report title, the company, the parameters, the generation timestamp and page numbers; XLSX writing numeric cells as numbers rather than as text with headers identical to the on-screen labels; both preserving the active filters and the expanded detail; and drill-down from any line to the journal items that sum to it — with export cell values neutralized against spreadsheet formula injection under C-017. `@developer`
- [ ] **Validate every run-time parameter before use** — as-of date, date range, account filter and analytic filter — returning an error that names the parameter and the failed check and discloses no stack trace, query text, file-system path or credential, with data access expressed through the Odoo ORM or parameterized SQL and no concatenated search domain (C-015, C-019, C-020). `@developer`
- [ ] **Author the automated tests** mapped one-to-one to the 8 scenarios above, to the 5 edge cases below and to the performance envelope in § Test Requirements, asserting every balance, total and difference as an amount rather than by inspection, and reaching the 80% minimum coverage of C-007. `@qa`
- [ ] **Seed the volume fixture** of 100,000 posted journal items for one company and time a quarter-length run of both reports, an XLSX export and a drill-down against the stated envelope. `@qa`
- [ ] **Reconcile the Trial Balance against the sub-ledgers and sign the tie-out off** — the Accounts Receivable **1200** closing balance of `$2,093,811.88 USD` against the receivables sub-ledger, the Accounts Payable **2000** closing balance of `$1,284,300.00 USD` against the payables sub-ledger, the Bank **1010** closing balance of `$248,300.00 USD` against the reconciled bank position from [FEATURE-001-04](../FEATURE-001-04-bank-reconciliation-cash-management.md), the Tax Payable **2200** closing balance of `$186,900.00 USD` against the VAT/Tax Return of [FEATURE-001-05](../FEATURE-001-05-tax-configuration-compliance.md), and the Fixed Assets **1500** and Accumulated Depreciation **1590** closing balances of `$4,382,000.00 USD` and `$1,930,000.00 USD` against the asset register of [FEATURE-001-08](../FEATURE-001-08-fixed-assets-depreciation.md) — each at a difference of `$0.00 USD`. `@finance-sme`
- [ ] **Accept the audit trail** by opening 1 line of each report down to its journal items and confirming the items sum to the line at a difference of `$0.00 USD`, which is Epic Definition of Done item 10. `@finance-sme`

---

## Edge Cases

| # | Edge case | Expected outcome |
|---|-----------|------------------|
| **EC-1** | An account holds a non-zero opening balance and no journal item inside the requested range — Share Capital **3000** at `$2,000,000.00 USD` credit for 2025-01-01 to 2025-03-31 | The Trial Balance presents the account with a period debit of `$0.00 USD`, a period credit of `$0.00 USD` and a closing balance equal to its opening balance of `$2,000,000.00 USD` credit; the General Ledger presents the opening-balance line and no item line for that account; the report totals are unmoved, staying at total debits of `$8,284,600.00 USD` equal to total credits of `$8,284,600.00 USD` at a difference of `$0.00 USD`, each rounded half-up to 2 decimal places at the USD rounding increment of 0.01 |
| **EC-2** | A journal item falls inside a period already closed by the lock dates administered in [STORY-001-01-05](../FEATURE-001-01/STORY-001-01-05-configure-period-lock-dates.md) | Both reports read the locked period and present its items and balances in full, because reading a closed period is what an audit of it requires; neither report creates, alters nor reverses an entry in it, so the lock is never exercised by a report run; and an attempt to post into that range while the reports are open is refused by the lock date with the ledger and both reports unchanged |
| **EC-3** | A journal item is denominated in a currency other than the company currency — EUR 20,000.00 received into Bank **1010** of company `US-01` on 2025-02-14 at a rate of 1.0850 USD per EUR | The General Ledger presents the company-currency amount of `$21,700.00 USD` in its debit column, rounded half-up to 2 decimal places at the USD rounding increment of 0.01, with the original EUR 20,000.00 shown alongside it at the EUR rounding increment of 0.01; the running balance and both Trial Balance totals are stated in USD only, so the debit-and-credit equality is asserted in one currency; and the period effect of revaluing foreign-currency cash is presented as its own line by the Cash Flow Statement of [STORY-001-07-03](./STORY-001-07-03-generate-cash-flow-statement.md) rather than folded into a ledger total here |
| **EC-4** | The requested range covers a company holding 100,000 posted journal items | Both reports are produced within 30 seconds for a quarter-length range, and within 10 seconds for a range holding 10,000 posted journal items; the closing balances and the totals are identical to those produced over the same population without the volume, and total debits still equal total credits at a difference of `$0.00 USD`; an XLSX export of either report completes within 10 seconds and a drill-down resolves within 2 seconds |
| **EC-5** | An account receives its period movement through a centralized journal that holds many items for the same account and period | The General Ledger presents one aggregated line per account per period for that journal, and that line's debit and credit totals equal the sum of the journal items it stands for at a difference of `$0.00 USD`; the account's closing running balance is the same figure it would carry had every item been listed; and the Trial Balance closing balance for that account matches the aggregated General Ledger position at a difference of `$0.00 USD`, each amount rounded half-up to 2 decimal places at the USD rounding increment of 0.01 |

---

## Estimation

| Dimension | Assessment | Rationale |
|-----------|------------|-----------|
| **Effort** | Medium-high | Two report surfaces are delivered together: 7 General Ledger columns with an opening-balance line and a running balance carried down each account group, and 5 Trial Balance columns with an account-type filter, an include-zero-balance option and a comparative period. The shared export and drill-down surface inherited from the feature convention, the run-time parameter validation, and the 100,000-item volume fixture are inside this estimate. |
| **Complexity** | Medium | The arithmetic is double-entry arithmetic and holds no algorithmic surprise, but three rules have to be right at once: which accounts carry a balance across the fiscal-year boundary and which reset, how the running balance orders items inside an account group so the closing figure is reproducible, and how a centralized journal aggregates without changing a total. The account-type-to-grouping mapping is consumed rather than invented here, which removes the largest source of complexity from this story. |
| **Uncertainty** | Low-medium | The reports themselves are settled: every figure asserted above is fixed in advance and every field consumed exists in `addons/account` in this repository. The open items are programme-level rather than story-level — the platform version target (DEC-001, C-010) and the edition source for the reporting layer (DEC-002, C-003), which decide whether the OCA modules in § Technical Discovery Notes are extended or replaced. Neither changes the criteria, only the code path that satisfies them. |
| **Story points** | **8** (Fibonacci: 1, 2, 3, 5, 8, 13) | Two reports over one population, plus the export and drill-down surface they share with the three statement stories, plus the volume envelope, is more than the 5 points a single report of this shape would carry and less than the 13 a story with unresolved requirements would carry. The merge is what keeps it at one estimate: a second aggregation of the same population, built and reconciled separately, would cost more than the 8 points asked for here. |

---

## Constraints

### License and Compliance

- **AGPL-3.0 compatibility (C-001)**: new code delivered for these reports is distributed under an AGPL-3.0 compatible licence, matching `addons/account_financial_report_ce` (19.0.1.1.0, AGPL-3) already present in this repository.
- **LGPL-3 interoperation (C-002)**: `addons/account/__manifest__.py` declares `'license': 'LGPL-3'` for the **Invoicing** module (version 1.4). Code that reads `account.account`, `account.move`, `account.move.line` and `account.journal` stays licence-compatible with it.
- **Odoo and OCA coding standards (C-005, C-006)**: implementation follows Odoo and OCA conventions including PEP 8, and passes static analysis under the repository's configured tooling, whose lint configuration is `ruff.toml` at the repository root.

### Platform and Edition

- **Platform version target is an open decision (C-010, DEC-001)**: this repository is Odoo 19.0 — `odoo/release.py` declares `version_info = (19, 0, 0, FINAL, 0, '')` — while the programme request named Odoo 17 and the superseded backlog named 18.0. The target is inherited from the Epic as a dependency **flagged for stakeholder confirmation** and is not settled inside this story; the criteria above are stated in accounting terms and hold under any of the three, while the API surface behind them does not.
- **Edition source for the reporting layer is an open decision (C-003, DEC-002)**: `account_reports` is **absent from `addons/`** in this repository, because it ships with Odoo Enterprise rather than with the Community edition. Whether the reporting layer is taken from an Odoo Enterprise subscription or assembled from OCA add-ons is a decision the Epic records as unresolved and requires confirmed before FEATURE-001-07 enters development. This story states that absence as a fact about the current repository, not as a prohibition.
- **OCA ecosystem compatibility (C-004)**: whichever edition path is confirmed, delivered code stays consumable alongside `account_financial_report`, `report_xlsx` and the Community-edition add-ons already present.

### Accounting Standards Compliance

- **Double-entry integrity (C-009)**: the accounting contract of both reports is asserted as an amount — total debits equal total credits at a difference of `$0.00 USD`, each contributing journal entry balanced in its own right, and each report line equal to the sum of the journal items behind it.
- **Presentation under IAS 1 and US GAAP**: account grouping and captions follow the account-type mapping declared once for the feature, so the General Ledger, the Trial Balance and the three statements present one account under one caption. IAS 1 governs presentation and disclosure of the statements these two reports tie to; the FASB Accounting Standards Codification and the IFRS Foundation Standards are the frameworks the published set is prepared under.
- **Currency and date notation**: amounts carry an ISO 4217 currency code and dates are stated in ISO 8601 form, in both the on-screen reports and their exports.

### Security and Data Handling

- **Multi-company isolation (C-014)**: both reports run against the books of the company named in the request under Odoo's record rules, and a persona without access to a company obtains no line of that company's ledger.
- **Run-time parameter validation (C-015, C-019, C-020, C-022)**: every as-of date, date range, account filter and analytic filter is validated before use; data access is expressed through the Odoo ORM or parameterized SQL with no concatenated search domain; a rejected value returns an error naming the parameter and the failed check and discloses no stack trace, query text, file-system path or credential; and at least 1 hostile-input test proves the rejection with the ledger unchanged.
- **Export safety (C-017, C-018)**: a value written to XLSX or CSV that begins with `=`, `+`, `-`, `@`, a tab or a carriage return is written as text, and partner names, entry references and labels are context-encoded before they are rendered into a QWeb template or a PDF.

### Testing

- **Coverage floor (C-007)**: 80% minimum for the delivered functionality.
- **Traceable tests (C-008)**: unit, integration and acceptance tests, with each acceptance test traceable to one of the 8 Given/When/Then criteria above.

---

## Technical Discovery Notes

> **Purpose:** these notes tell the implementing agent WHAT to analyse. The story states the reporting outcome and its arithmetic; the module structure, model inheritance, view architecture, report engine and schema emerge from that analysis rather than from this ticket.

### Codebase Analysis Areas

| Area | Files/Modules to Examine | Analysis Focus |
|------|--------------------------|----------------|
| Account classification and balance-forward behaviour | `addons/account/models/account_account.py` | The account-type selection and the internal group it computes, which drive the Trial Balance account-type filter and the grouping captions; the balance-forward indicator (`include_initial_balance`) that decides whether an account opens at its carried position or at `$0.00 USD` at the fiscal-year boundary; and the opening debit, opening credit and opening balance fields already computed on the account |
| Debit, credit and running balance | `addons/account/models/account_move_line.py` | The `debit`, `credit` and `balance` fields and the state of the parent entry that admits an item to a report; the cumulated-balance computation (`_compute_cumulated_balance`) as the established running-balance pattern and the ordering it depends on; and how a company-currency amount relates to `amount_currency` and its currency for the multi-currency presentation of EC-3 |
| Entry-level balance and posted state | `addons/account/models/account_move.py` | How an entry's own debit-and-credit equality is established and where its posted state is held, so a report can assert that every contributing entry is balanced and can exclude draft and cancelled entries from both reports |
| Journal behaviour and centralized journals | `addons/account/models/account_journal.py` | The journal configuration that marks a journal centralized, and what one aggregated line per account per period has to sum for EC-5 to hold |
| Company scope, currency and rounding | `res.company` and `res.currency` in `odoo/addons/base` as consumed by `addons/account` | The company whose books a report is scoped to, its functional currency, and the currency rounding increment against which the half-up rounding to 2 decimal places is applied |
| Present Community implementation of these reports | `addons/account_financial_report_ce/` | The prior-phase Community-edition implementation credited by D-003 (19.0.1.1.0, AGPL-3, depending on `account` and `analytic`): its General Ledger and Trial Balance behaviour, its parameter set and its export path, to decide what is extended rather than rebuilt |
| Existing report and export infrastructure | `addons/account/report/` and the web report controller in `odoo/addons/web` | The QWeb rendering path for PDF and the export path for XLSX, together with the existing SQL-view report pattern, as candidates for the export half of the feature convention |
| Analytic dimension | `addons/analytic/` | The analytic mixin carried by journal items, which the analytic filter of both reports and of the drill-down detail reads |

### OCA Module Compatibility

| OCA Repository | Module | Compatibility Consideration |
|----------------|--------|----------------------------|
| OCA/account-financial-reporting | `account_financial_report` | The reference General Ledger and Trial Balance under the OCA path of DEC-002: assess whether its parameters, its opening-balance handling and its grouping match the account-type mapping declared for this feature, and whether it is extended or replaced |
| OCA/reporting-engine | `report_xlsx` | The XLSX half of the export convention: whether it writes numeric cells as numbers rather than as text, keeps headers identical to the on-screen labels, and admits the formula-injection neutralization C-017 requires |
| OCA/reporting-engine | `report_py3o` | An alternative templated-document export path, assessed against the QWeb PDF route rather than assumed to replace it |
| OCA/mis-builder | `mis_builder` | An alternative reporting framework whose account-level aggregation could serve the Trial Balance; assessed for whether one account can end up under two captions, which the declared mapping forbids |

---

## Dependencies

### Story Dependencies

| Dependency Type | Story ID | Story Title | Relationship |
|-----------------|----------|-------------|--------------|
| Parent Feature | [`FEATURE-001-07`](../FEATURE-001-07-financial-reporting-period-close.md) | Financial Reporting & Period Close | This story is part of this feature and delivers its CAP-004 capability; it also inherits the feature's export and drill-down convention (CAP-X01) rather than restating it |
| Blocks | [`STORY-001-07-03`](./STORY-001-07-03-generate-cash-flow-statement.md) | Generate Cash Flow Statement | The cash flow derives from ledger transaction data: the indirect method adjusts net income for non-cash items and working-capital movement read from the journal items this General Ledger presents, and both ends of that statement agree to the Bank **1010** position of `$196,450.00 USD` opening and `$248,300.00 USD` closing reported here |
| Blocks | [`STORY-001-07-05`](./STORY-001-07-05-execute-period-close-deferrals.md) | Execute Period-End Close with Deferred Revenue and Expense Cutoff | The close checklist requires the Trial Balance difference at `$0.00 USD` before the journal-entry and tax lock dates are applied, and the regenerated Trial Balance after the cutoff entries post is the evidence the period may be closed |
| Blocked By | [`FEATURE-001-01`](../FEATURE-001-01-chart-of-accounts-fiscal-year.md) | Chart of Accounts & Fiscal Year | Configuration sequencing rather than code coupling: the account codes, the account types that decide the Trial Balance grouping and the balance-forward behaviour, and the fiscal calendar that makes 2025-01-01 the start of fiscal year 2025, are published there and consumed here |
| Blocked By | [`STORY-001-01-05`](../FEATURE-001-01/STORY-001-01-05-configure-period-lock-dates.md) | Configure Period Lock Dates and Closing Controls | EC-2 asserts that a locked period is readable by both reports while remaining unpostable, so the lock dates have to exist for that behaviour to be demonstrable |
| Blocked By | [`STORY-001-01-04`](../FEATURE-001-01/STORY-001-01-04-import-legacy-coa.md) | Import Legacy Chart of Accounts and Opening Balances | Scenario 6 rests on the earliest posted entry of company `US-01` being its legacy-balance entry dated 2024-01-01, which is what leaves fiscal year 2023 without a posted entry, and the opening column of the reference figure set is the fiscal-year 2024 closing position that migration and the subsequent close produced |
| Related | [`STORY-001-07-01`](./STORY-001-07-01-generate-balance-sheet.md) | Generate Balance Sheet | Its total assets of `$4,812,600.00 USD`, total liabilities of `$1,612,600.00 USD` and total equity of `$3,200,000.00 USD` are the closing column of this Trial Balance regrouped by account type, and the two are reconciled at a difference of `$0.00 USD` |
| Related | [`STORY-001-07-02`](./STORY-001-07-02-generate-profit-loss.md) | Generate Profit & Loss Statement | Its Revenue **4000** of `$1,842,000.00 USD`, Expense **6100** of `$1,398,000.00 USD`, Depreciation Expense **6500** of `$144,000.00 USD` and net income of `$300,000.00 USD` are the income and expense rows of this Trial Balance, and its net income is the current-year-earnings line of the Balance Sheet |
| Related | [`STORY-001-03-05`](../FEATURE-001-03/STORY-001-03-05-report-aged-receivables.md) | Generate Aged Receivables Report | Receivables ageing is not restated here; that report's total reconciles to the Accounts Receivable **1200** closing balance of `$2,093,811.88 USD` this Trial Balance reports for the same company and as-of date at a difference of `$0.00 USD` |
| Related | [`FEATURE-001-06`](../FEATURE-001-06-multi-company-consolidation.md) | Multi-Company & Intercompany Consolidation | Both reports are scoped to the books of one named company; a group-level ledger or trial balance is produced through consolidation there, and is never inferred by summing entity reports produced here |

### External Dependencies

| Dependency | Type | Notes |
|------------|------|-------|
| FASB Accounting Standards Codification | Accounting standard | The United States framework the statements these two reports tie to are prepared under; it governs the classification the account-type mapping expresses rather than the ledger arithmetic |
| IFRS Foundation Standards, with IAS 1 *Presentation of Financial Statements* | Accounting standard | Presentation and disclosure of the statement set the Trial Balance is the tie-out for; IAS 1 decides the captions an account is presented under |
| Double-entry bookkeeping | Accounting principle | Total debits equal total credits is the property this story exists to prove, asserted as an amount at a difference of `$0.00 USD` rather than declared |
| ISO 4217 | Standard | Currency codes on every amount presented and exported, `USD` for company `US-01` and `EUR` for the foreign-currency item of EC-3 |
| ISO 8601 | Standard | Date notation for the range parameters, the accounting dates on ledger lines and the generation timestamp carried by the PDF export |
| Platform version target (DEC-001, C-010) | Programme decision | Inherited from the Epic and flagged for stakeholder confirmation: this repository is Odoo 19.0, the request named Odoo 17 and the superseded backlog named 18.0 |
| Reporting-layer edition source (DEC-002, C-003) | Programme decision | Inherited from the Epic: `account_reports` is absent from `addons/` in this repository, so the reporting layer comes from an Odoo Enterprise subscription or from OCA add-ons, and the choice is confirmed before this feature enters development |

### Integration Points

| Odoo Model/Module | Integration Type | Purpose |
|-------------------|------------------|---------|
| `account.move` | Read | Admits only entries in the posted state to both reports, supplies the entry reference each ledger line carries and each drill-down item states, and is the record whose own total debits equal its own total credits at a difference of `$0.00 USD` |
| `account.move.line` | Read | The population both reports present: the debit, credit, accounting date, label, partner and account of every item, the running balance carried down each General Ledger account group, and the items a drill-down resolves a report line into |
| `account.account` | Read | The account a line is grouped under, its code and name, its account type and internal group — which drive the Trial Balance account-type filter and its grouping — and its balance-forward behaviour, which decides whether the account opens at its carried position or at `$0.00 USD` |
| `account.journal` | Read | The journal each item was posted through (**Sales**, **Purchases**, **Bank**, **Payroll**, **Miscellaneous**) and the centralized-journal configuration that produces the aggregated line of EC-5 |
| `res.company` | Read | The company whose books each report is scoped to, its functional currency and its fiscal-year boundary; multi-company record rules restrict the population to permitted companies |
| `res.currency` | Read | The rounding increment of 0.01 that the half-up rounding to 2 decimal places is applied at, and the conversion of a foreign-currency item to the company-currency amount presented in EC-3 |
| `analytic.mixin` on `account.move.line` | Read | The analytic dimension the analytic filter of both reports and of the drill-down detail reads |

---

## Test Requirements

### Coverage Requirement

| Metric | Requirement | Notes |
|--------|-------------|-------|
| **Minimum Test Coverage** | **80%** | Mandatory for all new functionality delivered by this story (C-007) |
| Unit Test Coverage | 80%+ | Opening-balance derivation, running-balance accumulation, account-level aggregation, difference computation, rounding at the currency increment |
| Integration Test Coverage | 80%+ | Both reports against a seeded ledger, the General Ledger to Trial Balance tie-out, the export formats and the drill-down |
| Numeric assertion rule | Every balance, total, variance and difference asserted as an amount | No accounting figure is confirmed by inspection (C-009) |

### Test Dataset

The deterministic load source is **`test_data/financial_reports/sample_journal_entries.csv`**, recorded as D-009 for this feature and read but never modified. Its columns are `Date, Journal, Reference, Account Code, Account Name, Partner, Label, Debit, Credit`, which is the shape a ledger tie-out is demonstrated against: dated items carrying an account, a partner, a label and a debit and credit pair.

Two caveats govern its use, and both are load-time mappings rather than changes to the file:

1. **Account codes are mapped onto the mandated chart.** The file carries 6-digit legacy codes and this backlog's chart is 4-digit, so each row is loaded against the mapped account rather than against the code as written. The crosswalk is recorded in § Notes, and no acceptance criterion above states a legacy code.
2. **The asserted population extends the file.** The rows in the file are dated in fiscal year 2024 and are loaded as the opening position that the reference figure set carries at 2025-01-01; the fiscal year 2025 first-quarter movement asserted in the criteria is seeded from the feature's fixed artifact set for company `US-01` on the same column shape. Fiscal year 2023 is left without a posted entry, which is what Scenario 6 requires.

### Unit Test Scenarios

| Acceptance Scenario | Unit Test Focus | Key Assertions |
|---------------------|-----------------|----------------|
| Scenario 1 | Opening-balance derivation and running-balance accumulation for a balance-forward account | Opening `$196,450.00 USD` debit; in-period debits `$1,817,383.12 USD`; in-period credits `$1,765,533.12 USD`; closing running balance `$248,300.00 USD` debit; rounding half-up to 2 decimal places at the USD increment of 0.01 |
| Scenario 2 | Account-level aggregation and the difference column | Closing debits `$8,284,600.00 USD` equal closing credits `$8,284,600.00 USD`; opening columns `$6,353,450.00 USD` both sides; period columns `$7,090,661.24 USD` both sides; difference `$0.00 USD` on each pair |
| Scenario 3 | Balance-forward flag against the fiscal-year boundary | Accounts Receivable **1200** opens at `$2,000,000.00 USD` debit and closes at `$2,093,811.88 USD` debit; Revenue **4000** opens at `$0.00 USD` and closes at `$1,842,000.00 USD` credit; the account filter yields exactly 2 groups |
| Scenario 4 | Tax triple separation and rate computation | Tax code `ST-CA-0725`, base `$1,782,000.00 USD` and tax `$129,195.00 USD` held as 3 values; `$1,782,000.00 USD` at 7.25% rounds half-up to `$129,195.00 USD`; Tax Payable **2200** closes at `$186,900.00 USD` credit |
| Scenario 5 | Date-range parameter validation | Inverted range rejected; error names the date-range parameter and the failed check; no report object produced; no stack trace, query text, file-system path or credential in the message |
| Scenario 6 | Empty-population handling | 0 rows; totals `$0.00 USD` on both sides; difference `$0.00 USD`; no opening balance carried in from an adjacent period; the requested range restated on the output |
| Scenario 7 | Zero-movement and zero-balance rows under the include-zero-balance option | Share Capital **3000** carries `$2,000,000.00 USD` credit from opening to closing with `$0.00 USD` movement; Suspense **1099** presents `$0.00 USD` in 4 columns; report totals unchanged at `$8,284,600.00 USD` both sides |
| Scenario 8 | Drill-down composition | Drilled items plus the opening position sum to `$2,093,811.88 USD` at a difference of `$0.00 USD`; every item inside 2025-01-01 to 2025-03-31 and inside company `US-01`; each drilled entry balanced in its own right |

### Integration Test Considerations

- [ ] Both reports read `account.move` and `account.move.line` for one company and date range, with draft and cancelled entries excluded from every figure
- [ ] The General Ledger closing running balance equals the Trial Balance closing balance for the same account, company and range at a difference of `$0.00 USD`, asserted for all 13 accounts of the reference figure set
- [ ] The Trial Balance closing column reconciles to the sub-ledgers: Accounts Receivable **1200** at `$2,093,811.88 USD`, Accounts Payable **2000** at `$1,284,300.00 USD`, Bank **1010** at `$248,300.00 USD`, Tax Payable **2200** at `$186,900.00 USD`, and Fixed Assets **1500** and Accumulated Depreciation **1590** at `$4,382,000.00 USD` and `$1,930,000.00 USD`
- [ ] Read-only behaviour: the posted journal-entry count and every account balance of company `US-01` for the range are identical before and after each report run, each export and each drill-down
- [ ] Multi-company isolation: a request naming company `US-01` yields no line belonging to another entity, and a persona without access to that company obtains no line of it
- [ ] Locked-period behaviour of EC-2: the reports present a locked period in full, and a posting attempt into it is refused with both reports unchanged
- [ ] Export integrity under the feature convention: PDF carries the report title, the company, the parameters and page numbers; XLSX numeric cells hold numbers rather than text with headers identical to the on-screen labels; a cell value beginning with `=` is written as text (C-017)
- [ ] Hostile-input tests required by C-022: a malformed date, the inverted range of Scenario 5, an out-of-range value and an over-long filter value are each rejected with a named error, no journal entry created and the service still available

### Acceptance Test Mapping

| BDD Scenario | Test Method Name | Test Type |
|--------------|------------------|-----------|
| Scenario 1: General Ledger from opening balance to closing running balance | `test_general_ledger_bank_account_opening_to_closing_running_balance` | Acceptance |
| Scenario 2: Trial Balance proves total debits equal total credits | `test_trial_balance_total_debits_equal_total_credits` | Acceptance |
| Scenario 3: Balance-forward account beside a period-reset account | `test_general_ledger_opening_balance_forward_versus_period_reset` | Acceptance |
| Scenario 4: Tax row keeps code, base amount and tax amount apart | `test_trial_balance_tax_row_code_base_and_tax_separated` | Acceptance |
| Scenario 5: Inverted date range rejected with no report produced | `test_report_request_rejects_inverted_date_range` | Acceptance |
| Scenario 6: Fiscal year with no posted entry returns an empty report | `test_trial_balance_empty_report_for_unposted_fiscal_year` | Acceptance |
| Scenario 7: Zero movement carried to closing and zero balance included on request | `test_trial_balance_zero_movement_and_zero_balance_rows` | Acceptance |
| Scenario 8: Report line resolves to journal items that sum back to it | `test_report_line_drilldown_items_sum_to_line_total` | Acceptance |
| EC-1 to EC-5 | `test_edge_case_zero_movement_account`, `test_edge_case_locked_period_is_readable`, `test_edge_case_foreign_currency_company_equivalent`, `test_edge_case_volume_envelope`, `test_edge_case_centralized_journal_aggregation` | Acceptance |

### Performance Tests

| Measure | Target | Method |
|---------|--------|--------|
| Report generation over volume | Under 30 seconds for a quarter-length range on a company holding 100,000 posted journal items, and under 10 seconds at 10,000 posted journal items | Timed run of both reports against the seeded volume company, with the closing balances and the debit-and-credit equality asserted identical to the low-volume run |
| Export to XLSX | Under 10 seconds for either report | Timed export with each exported cell value compared against the on-screen value |
| Drill-down response | Under 2 seconds from a line being opened to its journal items being available | Timed resolution of the Accounts Receivable **1200** closing line of Scenario 8 on the seeded company |

---

## Definition of Done

### Implementation Checklist

- [ ] All 8 acceptance criteria scenarios pass, each against the reference figure set for company `US-01` and the date range 2025-01-01 to 2025-03-31
- [ ] All 5 edge cases EC-1 to EC-5 pass with the outcomes stated for them
- [ ] The **General Ledger** presents, per account, an opening-balance line for each balance-forward account followed by every posted item with its date, entry reference, label, partner, debit, credit and running balance, and honours the account and account-type filters
- [ ] The **Trial Balance** presents, per account, an opening balance, a period debit, a period credit and a closing balance with a difference column, and honours the account-type filter, the include-zero-balance option and a comparative prior period whose absolute and percentage variance are stated, a prior-period balance of `$0.00 USD` presenting no percentage rather than a division result
- [ ] Export to PDF and to XLSX and drill-down from any line to its journal items are delivered under the feature convention of [FEATURE-001-07 §4.1](../FEATURE-001-07-financial-reporting-period-close.md), with active filters and expanded detail preserved
- [ ] Both reports are read-only: the posted journal-entry count and every account balance of the reported company and range are identical before and after a run, an export and a drill-down
- [ ] **80% minimum test coverage achieved** for the delivered functionality (C-007)
- [ ] Unit tests written and passing for opening-balance derivation, running-balance accumulation, account-level aggregation, the difference column and rounding at the currency increment
- [ ] Integration tests written and passing for the General Ledger to Trial Balance tie-out, the sub-ledger reconciliation, multi-company isolation, the export formats and the drill-down
- [ ] Each acceptance test is traceable to exactly one Given/When/Then criterion above (C-008)
- [ ] The performance envelope is met and evidenced: both reports under 30 seconds at 100,000 posted journal items and under 10 seconds at 10,000, an XLSX export under 10 seconds, a drill-down under 2 seconds

### Accounting Reconciliation Gate

All three checks are asserted numerically as amounts, not inspected (C-009):

- [ ] **Debits equal credits.** The **Trial Balance** for company `US-01` and the date range 2025-01-01 to 2025-03-31 reports total debits of `$8,284,600.00 USD` equal to total credits of `$8,284,600.00 USD` with the difference column at `$0.00 USD`; its opening columns are equal at `$6,353,450.00 USD` and its period movement columns equal at `$7,090,661.24 USD`; and every journal entry contributing to either report is itself posted with its own total debits equal to its own total credits at a difference of `$0.00 USD`. Each amount is rounded half-up to 2 decimal places at the USD rounding increment of 0.01
- [ ] **Tax amounts match.** The Tax Payable **2200** period credit of `$129,195.00 USD` is the base amount of `$1,782,000.00 USD` at tax code `ST-CA-0725` (7.25%), held as 3 separate values, and the account's closing balance of `$186,900.00 USD` credit reconciles to the **VAT/Tax Return** of [FEATURE-001-05](../FEATURE-001-05-tax-configuration-compliance.md) for the same company and date range at a difference of `$0.00 USD`
- [ ] **Report lines tie to the sub-ledger.** Two ties are evidenced for the same company and date range: a line opened for drill-down resolves to journal items whose signed sum, taken with the account's opening position, equals the line total — the Accounts Receivable **1200** closing line of `$2,093,811.88 USD` being the worked case; and the **General Ledger** per-account closing running balances equal the **Trial Balance** closing column for the same accounts at a difference of `$0.00 USD` across all 13 accounts, with Accounts Receivable **1200** at `$2,093,811.88 USD`, Accounts Payable **2000** at `$1,284,300.00 USD`, Bank **1010** at `$248,300.00 USD`, Tax Payable **2200** at `$186,900.00 USD`, Fixed Assets **1500** at `$4,382,000.00 USD` and Accumulated Depreciation **1590** at `$1,930,000.00 USD` each also reconciled to their sub-ledger of record

### Compliance Checklist

- [ ] New code is distributed under an AGPL-3.0 compatible licence (C-001) and stays licence-compatible with the LGPL-3 `account` module it reads (C-002)
- [ ] The reporting-layer edition source is recorded as the open programme decision DEC-002 rather than assumed, with `account_reports` noted as absent from `addons/` in this repository (C-003), and the delivered code stays consumable alongside the OCA add-ons (C-004)
- [ ] The platform version target is recorded as the open programme decision DEC-001 and confirmed with the stakeholder before implementation begins (C-010)
- [ ] Code follows Odoo and OCA standards and passes static analysis under the repository's configured tooling (C-005, C-006)
- [ ] Multi-company record rules are respected, so each persona reads only the companies permitted to them (C-014)
- [ ] Every run-time report parameter is validated before use, data access is expressed through the ORM or parameterized SQL, and a rejected value returns a named error disclosing no stack trace, query text, file-system path or credential (C-015, C-019, C-020), proved by at least 1 hostile-input test (C-022)
- [ ] Export cell values are neutralized against spreadsheet formula injection and rendered text is context-encoded (C-017, C-018)
- [ ] Code reviewed and approved

### Documentation Checklist

- [ ] Docstrings and inline comments complete for the aggregation, running-balance and rounding logic
- [ ] The report parameters, the columns of both reports and the account-type-to-grouping mapping they consume are documented for the finance function
- [ ] The reconciliation procedure — General Ledger to Trial Balance, Trial Balance to each sub-ledger, and the drill-down path an auditor follows — is documented as a close-time procedure referenced by [STORY-001-07-05](./STORY-001-07-05-execute-period-close-deferrals.md)
- [ ] Both open programme decisions and their effect on this story are recorded in § Constraints and carried into the release note

### Quality Checklist

- [ ] No critical or high-severity defect open against either report
- [ ] The performance envelope in § Test Requirements is met on the seeded volume company, and no report run degrades the response of concurrent postings
- [ ] Security review confirms parameter validation, multi-company isolation, export neutralization and the absence of internal detail in error messages
- [ ] The **Chief Accountant** accepts the Trial Balance as the period tie-out and the **External Auditor** accepts the trail from a report line to its journal items, which is Epic Definition of Done item 10

---

## References

### Accounting Standards

| Reference | Scope | Relevance to this story |
|-----------|-------|-------------------------|
| FASB Accounting Standards Codification | United States GAAP | The framework the statements this ledger ties to are prepared under; it decides the classification the account-type mapping expresses |
| IFRS Foundation Standards | International reporting framework | The framework applied where an entity of the group reports under IFRS, consumed here through the same account-type mapping |
| IAS 1 *Presentation of Financial Statements* | Presentation and disclosure | The captions and the ordering the Trial Balance grouping and the statement sections present accounts under |
| Double-entry bookkeeping | Accounting principle | Total debits equal total credits, the property Scenario 2 asserts as an amount |
| ISO 4217 | Currency codes | `USD` on every amount of company `US-01`; `EUR` on the foreign-currency item of EC-3 |
| ISO 8601 | Date notation | The date-range parameters, the accounting dates on ledger lines, and the generation timestamp on the PDF export |

### Source Code References

| Path | Relevance |
|------|-----------|
| `addons/account/models/account_account.py` | Account type, internal group, balance-forward indicator and opening-balance fields |
| `addons/account/models/account_move_line.py` | Debit, credit and balance fields and the cumulated-balance computation behind the running balance |
| `addons/account/models/account_move.py` | Posted state and entry-level debit-and-credit equality |
| `addons/account/models/account_journal.py` | Journal configuration including the centralized-journal behaviour of EC-5 |
| `addons/account/report/` | Existing report and QWeb rendering patterns available to the export half of the feature convention |
| `addons/account/__manifest__.py` | The **Invoicing** module, version 1.4, licence LGPL-3 — the module both reports read |
| `addons/account_financial_report_ce/` | Present Community-edition implementation of these reports, credited as D-003 (19.0.1.1.0, AGPL-3) |
| `addons/analytic/` | The analytic mixin the analytic filter reads |
| `odoo/release.py` | `version_info = (19, 0, 0, FINAL, 0, '')`, the repository baseline behind the DEC-001 version question |
| `test_data/financial_reports/sample_journal_entries.csv` | The deterministic load source D-009 named in § Test Requirements |

### OCA Repositories

| Repository | URL | Relevance |
|------------|-----|-----------|
| OCA/account-financial-reporting | <https://github.com/OCA/account-financial-reporting> | `account_financial_report` patterns for the General Ledger and the Trial Balance under the OCA path of DEC-002 |
| OCA/reporting-engine | <https://github.com/OCA/reporting-engine> | `report_xlsx` and `report_py3o` as export options assessed against the QWeb PDF route |
| OCA/mis-builder | <https://github.com/OCA/mis-builder> | `mis_builder` as an alternative account-level reporting framework |

### Backlog References

| Reference | Link |
|-----------|------|
| Parent feature, its capability map and its export and drill-down convention | [FEATURE-001-07: Financial Reporting & Period Close](../FEATURE-001-07-financial-reporting-period-close.md) |
| Parent epic, its constraint set and its success metrics | [EPIC-001: Enterprise Accounting in Odoo](../../EPIC-001-enterprise-accounting-odoo.md) |
| Sibling statements reconciled to this tie-out | [STORY-001-07-01](./STORY-001-07-01-generate-balance-sheet.md), [STORY-001-07-02](./STORY-001-07-02-generate-profit-loss.md), [STORY-001-07-03](./STORY-001-07-03-generate-cash-flow-statement.md) |
| Close execution that reads the Trial Balance difference before locking | [STORY-001-07-05](./STORY-001-07-05-execute-period-close-deferrals.md) |
| Chart of accounts, account types, fiscal calendar, migrated opening balances and lock dates | [FEATURE-001-01](../FEATURE-001-01-chart-of-accounts-fiscal-year.md), [STORY-001-01-04](../FEATURE-001-01/STORY-001-01-04-import-legacy-coa.md), [STORY-001-01-05](../FEATURE-001-01/STORY-001-01-05-configure-period-lock-dates.md) |
| Receivables ageing, which this story does not restate | [STORY-001-03-05](../FEATURE-001-03/STORY-001-03-05-report-aged-receivables.md) |
| Tax configuration and the VAT/Tax Return the tax control account reconciles to | [FEATURE-001-05](../FEATURE-001-05-tax-configuration-compliance.md) |
| Consolidated scope, which is produced there rather than summed here | [FEATURE-001-06](../FEATURE-001-06-multi-company-consolidation.md) |

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-08-13 | Enterprise Accounting Team | Initial story: 8 acceptance criteria over one deterministic figure set for company `US-01` and the date range 2025-01-01 to 2025-03-31, carrying the feature's canonical assertion that total debits of `$8,284,600.00 USD` equal total credits of `$8,284,600.00 USD` at a difference of `$0.00 USD`; 5 edge cases; the INVEST table with the merge justified under Small; sub-tasks assigned across the functional consultant, developer, QA and finance SME; an estimate of 8 Fibonacci points; the accounting-reconciliation gate stated as 3 numeric checks alongside the 80% coverage floor; and the export and drill-down convention inherited from the parent feature rather than restated |

**Migration note.** This story supersedes two stories of the retired flat backlog — `FR-004` (General Ledger Report) and `FR-005` (Trial Balance Report) — and absorbs the report-export and drill-down half of `FR-007`, which the parent feature re-homed as the shared convention CAP-X01. The two retired identifiers are recorded here once, for traceability, and appear nowhere else in this tree: the identifier of this work is `STORY-001-07-04`. Four substantive corrections were applied on the way in: the vague qualifier the retired centralized-journal criterion carried is replaced by the definite rule of EC-5, that each centralized journal contributes one aggregated line per account per period whose debit and credit totals equal the sum of the underlying journal items; every monetary assertion now carries a currency, an amount and a rounding behaviour; debit-and-credit equality is now a numeric assertion of two stated totals rather than a statement of principle; and the retired persona "Accountant" is replaced by the **Chief Accountant**, with the **External Auditor** retained as the persona of the drill-down criteria. The retired estimate, which the flat backlog left open for sprint planning to settle, is replaced by 8 Fibonacci points, and the retired blanket claim of no Enterprise dependency is replaced by the recorded fact that `account_reports` is absent from `addons/` together with the open edition decision DEC-002.

---

## Notes

**Export and drill-down are a shared capability, not a separate deliverable.** The feature owns one export and drill-down convention (CAP-X01 in [FEATURE-001-07 §4.1](../FEATURE-001-07-financial-reporting-period-close.md)), and [STORY-001-07-01](./STORY-001-07-01-generate-balance-sheet.md), [STORY-001-07-02](./STORY-001-07-02-generate-profit-loss.md), [STORY-001-07-03](./STORY-001-07-03-generate-cash-flow-statement.md) and this story each inherit it rather than restate it. The retired backlog carried it as a standalone story; folding it into the report stories keeps one implementation of PDF and XLSX export and one drill-down surface across all four, and it is why Scenario 8 and the third reconciliation check of the Definition of Done are stated here as the audit trail of this story's own lines rather than as a general capability.

**The platform target is unresolved and deliberately left so.** This repository is Odoo 19.0, the programme request named Odoo 17 and the retired backlog named 18.0. The criteria above are written as accounting outcomes and hold under any of the three, but the API surface behind them does not, so the target is inherited from the Epic as DEC-001 and flagged for stakeholder confirmation rather than chosen here. The same applies to DEC-002: `account_reports`, the Enterprise reporting module, is absent from `addons/` in this repository, while `addons/account_financial_report_ce` is present, so the reporting layer is assembled from an Enterprise subscription or from OCA add-ons once the decision is confirmed. Neither decision changes a single figure asserted above.

**Account-code crosswalk for the fixture.** The deterministic load source `test_data/financial_reports/sample_journal_entries.csv` carries 6-digit legacy codes while this backlog's mandated chart is 4-digit. The file is loaded through the mapping below, and no acceptance criterion states a legacy code:

| Legacy code in the fixture | Legacy name | Mandated chart account |
|----------------------------|-------------|------------------------|
| `110100` | Cash at Bank | Bank **1010** |
| `110000` | Accounts Receivable | Accounts Receivable **1200** |
| `200000` | Accounts Payable | Accounts Payable **2000** |
| `400000` | Product Sales Revenue | Revenue **4000** |
| `600000` | Cost of Goods Sold | Expense **6100** |
| `630000` | Bank Service Charges | Expense **6100** |

The remaining legacy codes in the file — rent, salary and interest-income lines — are mapped when the migration crosswalk of [STORY-001-01-04](../FEATURE-001-01/STORY-001-01-04-import-legacy-coa.md) is published, and they carry no figure asserted in this story.

**Which artifact set the figures belong to.** Every entity, date, account balance and tax figure above is drawn from the fixed artifact set of the parent feature — the entity register **Global Holdings Inc. (`US-01`)**, **Global Europe SARL (`NL-01`)** and **Global Asia Pte Ltd (`SG-01`)**, the reporting range 2025-01-01 to 2025-03-31, and the closing position the four sibling statements are reconciled against. Sibling features declare their own worked entities and dates for their own criteria, so no figure asserted here depends on another feature's fixture, and the two artifact sets are reconciled to one register when the entity and migration crosswalks are published rather than assumed identical now.

**Why the two reports are demonstrated as one.** A Trial Balance is the General Ledger summed to one row per account: same population, same company scope, same date-range parameter, same posted-state filter, and the same rounding at the currency increment. Building them apart would mean two aggregations of one population and a reconciliation between two implementations of the same arithmetic — which is the defect this story exists to prevent, since every statement in the feature is reconciled to the Trial Balance rather than to a second aggregation of its own.

**What this story does not carry.** Receivables and payables ageing (owned by [STORY-001-03-05](../FEATURE-001-03/STORY-001-03-05-report-aged-receivables.md) and by FEATURE-001-02), the statement set itself, the period-end close checklist and the deferral cutoff, and any group-level or consolidated ledger (owned by [FEATURE-001-06](../FEATURE-001-06-multi-company-consolidation.md)). Both reports here are scoped to the books of one named company, and the reference figure set names that company as `US-01` on every criterion.
