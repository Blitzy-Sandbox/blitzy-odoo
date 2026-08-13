# STORY-001-01-03: Define Fiscal Year and Accounting Periods

---

## Metadata

| Attribute | Value |
|-----------|-------|
| **Story ID** | `STORY-001-01-03` |
| **Title** | Define Fiscal Year and Accounting Periods |
| **Parent Feature** | [FEATURE-001-01: Chart of Accounts & Fiscal Year](../FEATURE-001-01-chart-of-accounts-fiscal-year.md) |
| **Parent Epic** | [EPIC-001: Enterprise Accounting in Odoo](../../EPIC-001-enterprise-accounting-odoo.md) |
| **Persona** | Chief Accountant |
| **Status** | Draft |
| **Priority** | 🔴 Critical |
| **Estimate** | 3 story points (Fibonacci) |
| **Feature Capability** | CAP-003 — define the fiscal year, its accounting periods and the fiscal-year-end date per company |
| **Epic Success Metric** | SM-006 — Trial Balance integrity, asserted per company **and per period** with the difference column at 0.00 in the company currency; the calendar fixed here is also the unit of measure of SM-003 (close within 5 business days of period end) and SM-005 (under 5 minutes per statement) |
| **Owner/Author** | Enterprise Accounting Team |

This is the third of the five stories in FEATURE-001-01 and the one that fixes the **fiscal calendar** the rest of EPIC-001 reports against. Every date range quoted in another ticket — the Trial Balance range, the Balance Sheet as-of date, the depreciation period, the VAT return period, the budget period, the consolidation period — is a range on the calendar this story defines. It has no blocking predecessor, and it is a documented prerequisite of [STORY-001-01-04](./STORY-001-01-04-import-legacy-coa.md) and [STORY-001-01-05](./STORY-001-01-05-configure-period-lock-dates.md).

> **Monetary convention used throughout this ticket.** Every amount is stated in USD, carried to 2 decimal places, and rounded half-up at the USD rounding increment of 0.01. Where a company reports in a functional currency other than USD, the same assertion is made in that currency at that currency's own decimal precision. Every date is stated as an explicit calendar date rather than as a relative period.

---

## User Story

**As a** Chief Accountant

**I want** a fiscal year and its twelve accounting periods defined per company on `res.company` for Acme Group NV — a fiscal-year end day and a fiscal-year end month from which every reportable period is derived, with the same setting available and independent for each subsidiary

**So that** every journal item posted in the group falls in exactly one reportable period, and every statement is run for a date range that is stated rather than inferred: a Balance Sheet as of a named fiscal-year end date, and a Trial Balance and General Ledger for a named fiscal-year date range whose total debits equal total credits at a difference of USD 0.00, rounded to 2 decimal places using half-up rounding (SM-006).

---

## INVEST Principles Compliance

| Principle | Compliance | Notes |
|-----------|------------|-------|
| **Independent** | ✅ | This story has **no blocking predecessor**. The fiscal-year end day and month live on the company record, so the calendar can be configured before the chart of accounts of [STORY-001-01-01](./STORY-001-01-01-configure-coa-hierarchy.md) is finalized and before any account exists to post into; it needs only module `account` and one `res.company` record, both present in the platform baseline. It **blocks** [STORY-001-01-04](./STORY-001-01-04-import-legacy-coa.md), because the opening entry has to be dated inside a defined fiscal year, and [STORY-001-01-05](./STORY-001-01-05-configure-period-lock-dates.md), because a lock date is set at a period boundary that must exist first. Both relationships are **configuration sequencing, not code coupling**: neither sibling shares an implementation with this story, and each is developed against the calendar this story fixes rather than against how it was set. |
| **Negotiable** | ✅ | The outcome is stated — one fiscal year per company, twelve periods, deterministic date ranges — and the mechanism is left open. Whether the fiscal-year end is entered on the company form, on the financial-year opening wizard, on a settings page, or seeded per company by a localization pack is deferred to the discovery recorded below. The shape of the year itself (calendar, April-to-March, or another statutory year) is negotiable per entity with the Group Controller for as long as each entity carries exactly one fiscal-year definition. |
| **Valuable** | ✅ | Without a defined fiscal calendar there is no period to close, no comparative column to present and no date range to reconcile: the close-cycle target of SM-003, the statement-generation target of SM-005 and the per-period Trial Balance assertion of SM-006 are each measured against a period boundary this story creates. It is also the control point that makes the lock dates of STORY-001-01-05 meaningful, because a lock date without a period boundary locks an arbitrary date. |
| **Estimable** | ✅ | The work is bounded by a countable deliverable: two fields per company (fiscal-year end day and fiscal-year end month), the twelve derived period ranges they produce, one constraint path that refuses an out-of-range day, and the report date ranges that consume them. Nothing in it waits on an open decision, so it is sized at 3 Fibonacci points with the rationale recorded in § Estimation. |
| **Small** | ✅ | One configuration outcome — the fiscal calendar of one company, reproduced independently for a second company — demonstrated in a single walkthrough of the fiscal-year settings, one Balance Sheet run and one Trial Balance run. The chart of accounts, the taxonomy tags, the opening-balance load and the lock-date administration are each a separate sibling story, so this story is not a container for the whole feature. |
| **Testable** | ✅ | Every criterion below is asserted as a date, a count, an amount or a refusal: FY2026 spanning 01 January 2026 to 31 December 2026, 12 periods covering 365 days with no gap and no overlap, a refused fiscal-year end of 31 February, an opening entry left at total debits of USD 4,812,600.00 equal to total credits of USD 4,812,600.00, and Current Year Earnings of USD 70,000.00 against Trial Balance totals of USD 430,000.00 on each side, every amount in USD at 2 decimal places using half-up rounding. Each of the five scenarios maps to one named automated test in § Test Requirements, so pass or fail is decided without judgement. |

---

## Acceptance Criteria

Five criteria are authored, inside the 4-to-8 bound the Epic sets in [§5.3](../../EPIC-001-enterprise-accounting-odoo.md#53-feature-and-story-decomposition-guidelines), and they carry the mandated coverage distribution: **Scenarios 1 and 2 are valid-input cases** (a calendar fiscal year for the parent, a non-calendar fiscal year for the subsidiary), **Scenario 3 is the invalid-input case**, **Scenario 4 is the error-handling case**, and **Scenario 5 is the accounting edge case** at the year-end period boundary.

Scenarios 3 and 4 are two distinct refusal paths rather than one repeated: in Scenario 3 no opening journal entry exists, so the length of the selected month is evaluated against the year in which the setting is saved; in Scenario 4 a posted opening entry exists, so the length of the selected month is evaluated against the year of that entry, and the refusal has to leave the posted entry and its journal items untouched.

### Scenario 1: Calendar fiscal year defined for the parent company

- **Given** Acme Group NV exists as a company whose functional currency is `USD`, module `account` ("Invoicing", version 1.4, licence LGPL-3) is installed in it, and its fiscal calendar is held as a fiscal-year end day and a fiscal-year end month on the company record with no accounting period stored as a separate record
- **When** the Chief Accountant sets Fiscal Year Last Day to 31 and Fiscal Year Last Month to December for Acme Group NV
- **Then** fiscal year FY2026 of Acme Group NV spans 01 January 2026 to 31 December 2026; its twelve monthly periods are offered as selectable date ranges from 01 January 2026 to 31 December 2026 — 01 January 2026 to 31 January 2026, 01 February 2026 to 28 February 2026, and so on to 01 December 2026 to 31 December 2026; the count of periods in FY2026 is 12 and they cover 365 days with each period's start date one day after the preceding period's end date, so no day of FY2026 falls in two periods and no day falls in none; a Trial Balance requested for FY2026 resolves to the date range 01 January 2026 to 31 December 2026; and a Balance Sheet requested as of 31 December 2026 resolves its fiscal-year start to 01 January 2026

### Scenario 2: Non-calendar fiscal year defined for the subsidiary without disturbing the parent

- **Given** Acme Group NV carries Fiscal Year Last Day 31 with Fiscal Year Last Month December, and its subsidiary **Acme Industries Inc.** files with its statutory regulator on an April-to-March year
- **When** the Chief Accountant sets Fiscal Year Last Day to 31 and Fiscal Year Last Month to March for **Acme Industries Inc.**
- **Then** fiscal year FY2026 of **Acme Industries Inc.** spans 01 April 2025 to 31 March 2026, and its twelve monthly periods run from 01 April 2025 to 31 March 2026 — 01 April 2025 to 30 April 2025 through to 01 March 2026 to 31 March 2026; fiscal year FY2026 of **Acme Group NV** is unchanged at 01 January 2026 to 31 December 2026 with its Fiscal Year Last Month still December; the Trial Balance run for **Acme Industries Inc.** over 01 April 2025 to 31 March 2026 reports total debits equal to total credits at a difference of USD 0.00, rounded to 2 decimal places using half-up rounding; and the Trial Balance run for **Acme Group NV** over 01 January 2026 to 31 December 2026 reports total debits equal to total credits at a difference of USD 0.00 on its own calendar, so neither company's reporting range is derived from the other's setting

### Scenario 3: A fiscal-year end day beyond the length of the selected month is refused

- **Given** the Chief Accountant is editing the fiscal-year settings of Acme Group NV, whose stored values are Fiscal Year Last Day 31 and Fiscal Year Last Month December, and Acme Group NV holds no opening journal entry
- **When** the Chief Accountant saves a fiscal-year end of 31 February for Acme Group NV
- **Then** the save is refused with an Odoo validation message stating that the fiscal-year end day is out of range for the month selected — day 31 against the 28 days February holds in 2026, the year the setting is saved in — the stored values of Acme Group NV remain Fiscal Year Last Day 31 and Fiscal Year Last Month December, fiscal year FY2026 still spans 01 January 2026 to 31 December 2026, the twelve period ranges of FY2026 are unchanged, and no report date range is altered by the refused save

### Scenario 4: A fiscal-year change refused against the posted opening entry leaves it intact

- **Given** Acme Group NV holds a posted opening journal entry whose Opening Entry date is 01 January 2026 and which is therefore dated 31 December 2025, carrying total debits of USD 4,812,600.00 equal to total credits of USD 4,812,600.00 — a difference of USD 0.00, each amount rounded to 2 decimal places using half-up rounding — this entry is the only entry posted in Acme Group NV on or before 31 December 2025, and the stored fiscal-year values are Fiscal Year Last Day 31 and Fiscal Year Last Month December
- **When** the Chief Accountant saves a fiscal-year end of 30 February for Acme Group NV
- **Then** the save is refused with an Odoo validation message stating that the fiscal-year end day is out of range for the month selected, the month length having been evaluated against the year of the opening entry — day 30 against the 28 days February holds in 2026; the stored values remain Fiscal Year Last Day 31 and Fiscal Year Last Month December; the opening journal entry keeps its date of 31 December 2025 and its total debits of USD 4,812,600.00 equal to its total credits of USD 4,812,600.00 at a difference of USD 0.00, rounded to 2 decimal places using half-up rounding; no journal item is added, amended or removed by the refused save; and the Trial Balance for Acme Group NV over 01 January 2025 to 31 December 2025 reports the same total debits of USD 4,812,600.00 equal to the same total credits of USD 4,812,600.00 that it reported before the attempt

### Scenario 5: Year-end earnings roll across the FY2026 period boundary

- **Given** Acme Group NV carries Fiscal Year Last Day 31 with Fiscal Year Last Month December, so FY2026 spans 01 January 2026 to 31 December 2026 and FY2027 spans 01 January 2027 to 31 December 2027; the entries posted in FY2026 are one Sales journal entry debiting Accounts Receivable 1200 by USD 250,000.00 against a credit of USD 250,000.00 to Revenue 4000, and one Purchase journal entry debiting Expense 6100 by USD 180,000.00 against a credit of USD 180,000.00 to Accounts Payable 2000, every amount stated in USD and rounded to 2 decimal places using half-up rounding; and no entry is dated after 31 December 2026
- **When** the Chief Accountant runs the **Balance Sheet** for Acme Group NV as of 31 December 2026
- **Then** the Balance Sheet reports a Current Year Earnings line of USD 70,000.00 credit — the FY2026 revenue of USD 250,000.00 less the FY2026 expense of USD 180,000.00, rounded to 2 decimal places using half-up rounding; the same Balance Sheet run as of 01 January 2027 reports a Current Year Earnings line of USD 0.00 for FY2027 and presents that USD 70,000.00 in the Retained Earnings line as the result of the preceding fiscal year, while the posted balance of Retained Earnings 3100 stays USD 0.00 until the year-end allocation entry of Edge Case 5 is posted onto it; and the **Trial Balance** for Acme Group NV over 01 January 2026 to 31 December 2026 reports Revenue 4000 at a credit of USD 250,000.00, Expense 6100 at a debit of USD 180,000.00, and total debits of USD 430,000.00 equal to total credits of USD 430,000.00 — a difference of USD 0.00 — every amount rounded to 2 decimal places using half-up rounding

---

## Sub-Tasks

| # | Sub-Task | Assignee |
|---|----------|----------|
| 1 | Confirm the fiscal-year shape of every in-scope legal entity with the Finance SME and the Group Controller — the fiscal-year end day and month per company — and document the resulting twelve-period calendar per company against the group close calendar | `@functional-consultant` |
| 2 | Record which entities file on a statutory year other than the calendar year, and reconcile the fiscal-year defaults each in-scope `l10n_*` pack seeds for its country against that record, so a pack installation cannot silently move a company's year-end (D-006) | `@functional-consultant` |
| 3 | Configure the fiscal-year end day and month per company and carry the derived period ranges into the date-range and as-of parameters the statements are requested with, so a statement is selected by period instead of by hand-typed dates | `@developer` |
| 4 | Surface the derived fiscal year and its twelve period ranges where the Chief Accountant maintains the setting, so the boundary a lock date will later be set at is readable before it is set | `@developer` |
| 5 | Author the five automated acceptance tests named in § Test Requirements, one per scenario, plus the two refusal tests — a fiscal-year end of 31 February with no opening entry, and one of 30 February against a posted opening entry — and the two-company test that holds a calendar year and an April-to-March year in one database | `@qa-engineer` |
| 6 | Verify the FY2026 year-end figures — Current Year Earnings of USD 70,000.00, and Trial Balance total debits of USD 430,000.00 equal to total credits of USD 430,000.00 — each amount in USD at 2 decimal places using half-up rounding — and sign off each company's fiscal-year end date against the group close calendar | `@finance-sme` |

---

## Edge Cases

| # | Edge Case | Expected Handling |
|---|-----------|-------------------|
| 1 | An entry is dated in a fiscal year nobody configured — an entry dated 15 January 2028 in Acme Group NV, whose fiscal-year setting was last reviewed for FY2026 | Periods are derived from the fiscal-year end day and month rather than held as stored period records, so 15 January 2028 falls in the derived FY2028 (01 January 2028 to 31 December 2028) and the entry posts with total debits of USD 5,000.00 equal to total credits of USD 5,000.00, a difference of USD 0.00, rounded to 2 decimal places using half-up rounding. There is no "period not created" refusal to rely on: control over posting into a reported or future year is the journal-entry lock date administered in [STORY-001-01-05](./STORY-001-01-05-configure-period-lock-dates.md), and this story's Definition of Done hands that boundary to it |
| 2 | A fiscal-year end falls in February across a leap year — Fiscal Year Last Day 29 with Fiscal Year Last Month February for Acme Group NV | The pair is accepted deliberately, because the setting carries no year value against which the intent could be disambiguated. The derived year-end then resolves to the last day of February in the year concerned: FY2026 spans 01 March 2025 to 28 February 2026 and covers 365 days, and FY2028 spans 01 March 2027 to 29 February 2028 and covers 366 days. Each statement states its own date range rather than a period count, and the Trial Balance for each of the two ranges reports total debits equal to total credits at a difference of USD 0.00, rounded to 2 decimal places using half-up rounding |
| 3 | A short first fiscal year — Acme Group NV begins keeping its books on 01 July 2025 while its fiscal-year end stays 31 December | The fiscal-year end day and month describe a full year, so the derived FY2025 still spans 01 January 2025 to 31 December 2025; the six-month opening period is expressed by the Opening Entry date of 01 July 2025 rather than by a shortened fiscal year. Every statement covering it is therefore run with the explicit range 01 July 2025 to 31 December 2025, its comparative column is labelled with its own range, and the shorter period with the reason for it is disclosed alongside the statements as IAS 1 requires when a reporting period is not one year and the comparative amounts are not fully comparable. The Trial Balance for 01 July 2025 to 31 December 2025 reports total debits equal to total credits at a difference of USD 0.00, rounded to 2 decimal places using half-up rounding |
| 4 | A company changes its fiscal-year end after the first period holds posted entries — **Acme Industries Inc.** moves Fiscal Year Last Month from March to December once its FY2026 (01 April 2025 to 31 March 2026) holds posted entries | The save is accepted whenever the day is inside the length of the selected month, and from that moment every reporting boundary of **Acme Industries Inc.** is re-derived, so a statement re-run for the same as-of date can report a different Current Year Earnings figure than the run taken before the change. The change is therefore made only on Group Controller approval, retained with its author and timestamp, and preceded by a journal-entry lock date set at the old boundary of 31 March 2026 ([STORY-001-01-05](./STORY-001-01-05-configure-period-lock-dates.md)) so the periods already reported cannot be re-opened by the re-derivation. Both statement runs are retained with their fiscal-year parameters, and the difference between them is explained in the close file in USD at 2 decimal places using half-up rounding |
| 5 | Non-coterminous fiscal years in one database, and the allocation of the year-end result — Acme Group NV on the calendar year against **Acme Industries Inc.** on 01 April 2025 to 31 March 2026, with the FY2026 result of Acme Group NV allocated onto Retained Earnings 3100 | Each company's statements are run on its own calendar, and the group reporting period is stated on the parent's calendar, so the figures of **Acme Industries Inc.** for the group period 01 January 2026 to 31 December 2026 are compiled from that company's own posted journal items for that range rather than from its own FY2026; the non-coterminous year-end, the reporting-date adjustment and the elimination treatment are carried by FEATURE-001-06 (Multi-Company & Intercompany Consolidation) rather than settled here. Where the group elects to allocate the FY2026 result of **Acme Group NV**, the allocation entry dated 31 December 2026 in the Miscellaneous journal debits Revenue 4000 by USD 250,000.00 and credits Expense 6100 by USD 180,000.00 and Retained Earnings 3100 by USD 70,000.00, posting total debits of USD 250,000.00 equal to total credits of USD 250,000.00 — a difference of USD 0.00 — every amount rounded to 2 decimal places using half-up rounding |

---

## Demonstration

The story is accepted when the Chief Accountant walks the **Finance Controller** and the **Product Owner** through the following path in the Odoo user interface, with the Group Controller present to sign off each company's year-end date against the group close calendar. Where a reviewer prefers the public API, the same six steps are demonstrated through it; either way the walkthrough is recorded against this story. Every figure shown in the walkthrough is read in USD at 2 decimal places, rounded half-up.

1. **Accounting ▸ Configuration ▸ Settings ▸ Fiscal Year** — the **Fiscal Year Last Day** and **Fiscal Year Last Month** settings of Acme Group NV shown at 31 and December. In the Odoo 19.0 baseline present in this repository the Fiscal Periods block of that Settings page carries the fiscal-year setting with its own field hidden, and the day-and-month pair is edited on the financial-year opening form — "Opening Balance of Financial Year", which labels the pair **Fiscal Year End** and states that the last day of the month is used when the chosen day does not exist. Whether the setting is exposed directly on the Settings page follows from DEC-001, so both surfaces are shown.
2. **The derived FY2026 calendar** — the twelve period ranges from 01 January 2026 to 31 December 2026 read back from that setting, with the period count shown at 12 and the boundary between 28 February 2026 and 01 March 2026 shown as contiguous.
3. **The same setting on Acme Industries Inc.**, changed to Fiscal Year Last Day 31 with Fiscal Year Last Month March, showing FY2026 of that company at 01 April 2025 to 31 March 2026 while FY2026 of Acme Group NV stays at 01 January 2026 to 31 December 2026.
4. **The Balance Sheet as of 31 December 2026** — the Current Year Earnings line at USD 70,000.00, followed by the same report as of 01 January 2027 showing USD 0.00 on Current Year Earnings for FY2027 and the USD 70,000.00 carried into the Retained Earnings line.
5. **The Trial Balance for 01 January 2026 to 31 December 2026** — Revenue 4000 at a credit of USD 250,000.00, Expense 6100 at a debit of USD 180,000.00, and total debits of USD 430,000.00 equal to total credits of USD 430,000.00, a difference of USD 0.00.
6. **The negative walkthrough** — a fiscal-year end of 31 February attempted and refused on Acme Group NV, then a fiscal-year end of 30 February attempted and refused on the company holding the posted opening entry, with the stored setting shown unchanged at 31 and December and the opening entry shown unchanged at total debits of USD 4,812,600.00 equal to total credits of USD 4,812,600.00 after both attempts.

---

## Constraints

### License and Compliance

- [ ] **C-001 — AGPL-3.0 compatible licence.** Any module delivering the fiscal-calendar configuration, the derived period ranges or their report parameters is distributed under an AGPL-3.0 compatible licence, matching the Community-edition accounting add-ons already present in this repository.
- [ ] **C-002 — LGPL-3 of `account` respected.** The fiscal-year end day and month, the opening-entry hook and the lock-date fields are LGPL-3 code declared in `addons/account/__manifest__.py`; derived and dependent work stays licence-compatible with it and no derived work misstates its licence.
- [ ] **C-005 and C-006 — Odoo and OCA coding standards.** Python follows Odoo and OCA module guidelines including PEP 8, and static analysis passes with the repository's configured tooling in `ruff.toml` at zero violations.
- [ ] **C-012 — build on the existing models.** The fiscal calendar is expressed on the company record and on the existing report date parameters rather than as a parallel fiscal-year or period table, so one ledger, one calendar and one audit trail survive the change.
- [ ] **C-014 — multi-company access rights.** The Chief Accountant maintains the calendar, the Group Controller approves each year-end date and any later change to it, the External Auditor holds read-only access to the setting and its change history, and a role restricted to Acme Group NV can neither read nor amend the fiscal-year setting of Acme Industries Inc.

### Version Compatibility

The platform target of this programme is an **open decision (DEC-001)** recorded in the Epic's [Open Decisions Register](../../EPIC-001-enterprise-accounting-odoo.md#appendix-b-open-decisions-register) and stated here without being resolved:

| Candidate target | Evidence on record | Consequence for this story |
|------------------|--------------------|----------------------------|
| **Odoo 17** | Named by the originating programme request | The field and label names asserted here — Fiscal Year Last Day, Fiscal Year Last Month, Fiscal Year End — are re-checked against the 17 series, and the `l10n_*` packs that seed a country's fiscal-year default are re-selected for that series |
| **Odoo 18.0** | Targeted by the prior, superseded backlog | Neither the request nor this repository is served; the field names, the refusal messages and the settings-page layout asserted here are restated for 18.0 |
| **Odoo 19.0** | The baseline present in this repository: `version_info = (19, 0, 0, FINAL, 0, '')` in `odoo/release.py`, with `MIN_PY_VERSION = (3, 10)` | The behaviour cited in every criterion holds as written: the fiscal year is derived from the company's fiscal-year end day and month, a day beyond the length of the selected month is refused, a fiscal-year end of 29 February is accepted deliberately, and a February year-end resolves to the last day of that month in the year concerned |

- [ ] **C-010 — the confirmed version is recorded** in the Epic and restated in the parent Feature before development starts; this story does not choose it.
- [ ] **C-011 — Python and PostgreSQL versions follow the confirmed target**, since each candidate release carries its own supported matrix.
- [ ] **Edition source (DEC-002) does not gate the configuration, only its verification.** The fiscal-year setting is supplied by `account`, which is present here under LGPL-3, so the calendar can be configured today. The Balance Sheet and Trial Balance that verify it are Enterprise capability in `account_reports`, which is absent from this repository; the AGPL-3 `account_financial_report_ce` add-on present here supplies both reports with the as-of date and date-range parameters the criteria cite, so the story is demonstrable under the OCA path while DEC-002 stays open.

### Accounting Standards Compliance

- [ ] **IAS 1 — Presentation of Financial Statements.** A complete set of statements is presented at least annually for a stated period, with comparative information for the preceding period; the fiscal calendar defined here is what makes the reporting period and its comparative period both nameable, and the same period length is used from year to year unless a change is disclosed.
- [ ] **IAS 1 — reporting period other than one year.** Where a reporting period is longer or shorter than one year — the short first year of Edge Case 3 and the year-end change of Edge Case 4 — the length of the period, the reason for it, and the fact that the comparative amounts are not fully comparable are disclosed with the statements.
- [ ] **ASC 210 — Balance Sheet.** The as-of date of the Balance Sheet is a date on this calendar, and the current-versus-non-current split is presented as of that date, so the US GAAP presentation of the group's US entities is driven by the same fiscal-year end.
- [ ] **Audit traceability.** The fiscal-year end day and month are retained with the author and timestamp of every change, so a change of year-end is evidence the External Auditor can read without a data request, and each reported figure traces to a period whose boundaries are on record.
- [ ] **One fiscal calendar per company.** Each company carries exactly one fiscal-year definition, which is the property that makes a period boundary — and therefore a lock date and a close — unambiguous.

---


## Technical Discovery Notes

> **Purpose:** these notes direct the codebase analysis that precedes implementation. This story states WHAT calendar finance needs and WHY; the surface the setting is maintained on, the way the derived periods are exposed, and the view architecture emerge from discovery and are deliberately not prescribed here.

### Codebase Analysis Areas

| Area | Files/Modules to Examine | Analysis Focus |
|------|--------------------------|----------------|
| Fiscal-year definition on the company | `addons/account/models/company.py` | The fiscal-year end day and fiscal-year end month fields, both required, defaulting to 31 and December; the method that computes the fiscal year containing an arbitrary date from that pair; and the absence of any fiscal-year or accounting-period record model, which means every period range is derived at read time rather than stored |
| Fiscal-year date derivation | `odoo/tools/date_utils.py` | The routine that turns a date plus a year-end day and month into a first and last day of the year, including its February handling, which snaps a February year-end to the last day of that month and clamps a day longer than the month — the mechanism behind Edge Case 2 and the twelve contiguous ranges asserted in Scenario 1 |
| The two fiscal-year validation paths | `addons/account/models/company.py`, `addons/account/wizard/setup_wizards.py` | The company-level constraint, which evaluates the month length against the year of the opening-entry date when one exists and against the current year otherwise, and the financial-year opening wizard's own constraint, which tests the day-and-month pair against a leap year. Which message the Chief Accountant sees depends on the surface used, so both are exercised by the refusal tests |
| Opening-entry interaction | `addons/account/models/company.py`, `addons/account/wizard/setup_wizards.py` | The opening journal entry, opening journal and Opening Entry date held per company; the derivation that dates the opening move the day before the Opening Entry date; and the posted-state indicator, which is the precondition Scenario 4 depends on |
| Lock dates that sit on this calendar's boundaries | `addons/account/models/company.py`, `addons/account/models/account_lock_exception.py` | The journal-entry, tax, sale, purchase and hard lock-date fields with their computed per-user counterparts, and the lock-exception record. Read here only to confirm that the boundary this story defines is the value [STORY-001-01-05](./STORY-001-01-05-configure-period-lock-dates.md) administers; no lock date is implemented by this story |
| Period resolution when an entry is posted | `addons/account/models/account_move.py`, `addons/account/models/account_move_line.py`, `addons/account/wizard/account_resequence.py` | How an entry's accounting date decides the period and the fiscal year it is reported in, how the resequencing logic derives a fiscal year from the company setting, and what happens to an entry dated in a year for which nothing was configured — the behaviour recorded as Edge Case 1 |
| Statement date parameters and the year-end split | `addons/account_financial_report_ce/models/balance_sheet.py`, `addons/account_financial_report_ce/models/trial_balance.py`, `addons/account_financial_report_ce/models/general_ledger.py` | The as-of date of the Balance Sheet against the date range of the Trial Balance and General Ledger; how the fiscal-year start is resolved from the company setting when it is not passed explicitly; and how current-year earnings are separated from the prior-year result folded into equity — the behaviour Scenario 5 asserts |
| Localization defaults | The 209 `addons/l10n_*` packs | Which packs seed a country-specific fiscal-year default, and what a pack installation does to a company whose year-end has already been agreed with the Group Controller (D-006) |
| Company and currency context | `odoo/addons/base/models/res_company.py`, `odoo/addons/base/models/res_currency.py` | The parent-and-subsidiary structure that carries one calendar per company independently, and the currency decimal precision every monetary assertion is rounded to |
| Accounts the year-end presentation lands on | `addons/account/models/account_account.py` | The account type that carries Current Year Earnings and the equity types behind Retained Earnings 3100 and Share Capital 3000, fixed by [STORY-001-01-01](./STORY-001-01-01-configure-coa-hierarchy.md) and read here as the target of the year-end roll |

### Relevant Existing Modules

- `addons/account/` — "Invoicing", version 1.4, licence LGPL-3. Supplies the fiscal-year end day and month on the company record, the fiscal-year computation used by every date-range consumer, the opening-entry hook, the lock-date fields, and the financial-year opening wizard.
- `addons/l10n_*/` — 209 localization packs present in this repository. Some seed a country-specific fiscal-year default, which is why the group calendar is reconciled against the packs of the operating countries rather than assumed (D-006).
- `addons/account_financial_report_ce/` — version 19.0.1.1.0, AGPL-3. Supplies the Balance Sheet with its as-of date and the Trial Balance and General Ledger with their date ranges, and resolves the fiscal-year start from the company setting, so it is the surface this story is verified through while DEC-002 stays open.
- `odoo/addons/base/` — `res.company` and `res.currency`: the company hierarchy that carries one calendar per entity and the decimal precision the monetary assertions are rounded to.
- `odoo/tools/date_utils.py` — the fiscal-year derivation used by both the accounting module and the reports; the single behaviour every date range in this story rests on.

### OCA Module Compatibility

| OCA Repository | Module | Compatibility Consideration |
|----------------|--------|-----------------------------|
| OCA/account-closing | `account_fiscal_year_closing` | Implements a templated year-end closing and opening-move run for jurisdictions where closing moves are mandatory. Determine whether the year-end allocation entry of Edge Case 5 is delivered by it or authored as one manual entry, and whether its closing moves change the figures the Balance Sheet presents as current-year against prior-year earnings |
| OCA/account-closing | `account_cutoff_start_end_dates` | Computes prepaid and accrued revenue and expense at a cut-off date derived from the fiscal-year end. Determine how it consumes the year-end date this story defines, since the deferral cutoff of FEATURE-001-07 is dated on that boundary |
| OCA/account-financial-reporting | `account_financial_report` | Renders the General Ledger, Trial Balance and Balance Sheet from date-range and as-of parameters. Determine whether it reads the company fiscal-year setting to default those parameters or requires explicit dates, which decides whether a period is selectable or typed |
| OCA/mis-builder | `mis_builder` | Builds management statements from period expressions relative to a fiscal year. Determine how a non-calendar year-end and a later change of year-end affect those expressions, since both are recorded here as supported states |

The decision to integrate, extend or replace any add-on above belongs to DEC-002 in the Epic and is not taken in this story.

---

## Dependencies

### Story Dependencies

| Dependency Type | Story / Feature ID | Title | Relationship |
|-----------------|--------------------|-------|--------------|
| Parent Feature | [FEATURE-001-01](../FEATURE-001-01-chart-of-accounts-fiscal-year.md) | Chart of Accounts & Fiscal Year | This story is the third of the feature's five stories and delivers its capability CAP-003 |
| **Blocked By** | **None** | — | **This story has no predecessor.** The fiscal-year end day and month live on the company record, so the calendar can be configured before the chart of accounts is finalized; it needs only module `account` and one company record, both present in the platform baseline |
| Blocks | [STORY-001-01-04](./STORY-001-01-04-import-legacy-coa.md) | Import Legacy Chart of Accounts and Opening Balances | The opening entry has to be dated inside a defined fiscal year, and the Opening Entry date it is derived from is part of the same fiscal-year configuration; Scenario 4 here shows the two settings interacting |
| Blocks | [STORY-001-01-05](./STORY-001-01-05-configure-period-lock-dates.md) | Configure Period Lock Dates and Closing Controls | A lock date is set at a period boundary, so the boundaries have to exist before one can be locked; Edge Cases 1 and 4 hand that boundary to it explicitly |
| Related | [STORY-001-01-01](./STORY-001-01-01-configure-coa-hierarchy.md) | Configure Multi-Level Chart of Accounts Hierarchy | Deliverable in parallel: its verification entry dated 15 January 2026 lands in a period this story defines, and its codes — Revenue 4000, Expense 6100, Retained Earnings 3100 — are the presentation target of the year-end roll in Scenario 5 |
| Related | [STORY-001-01-02](./STORY-001-01-02-map-accounts-ifrs-gaap-taxonomy.md) | Map Accounts to IFRS and GAAP Reporting Taxonomy | The presentation tags decide which statement line a balance appears on; this story decides which period it appears in, so the two together make a statement line addressable |
| Downstream features | FEATURE-001-02, FEATURE-001-03, FEATURE-001-04, FEATURE-001-05, FEATURE-001-06, FEATURE-001-07, FEATURE-001-08, FEATURE-001-09 | — | Every posting, reporting and close story quotes a range on this calendar — the VAT return period, the depreciation period, the budget period, the consolidation period and the close checklist — under ordering rule ORD-001 in the Epic's [§6.2](../../EPIC-001-enterprise-accounting-odoo.md#62-inter-feature-ordering) |

### External Dependencies

| Dependency | Type | Notes |
|------------|------|-------|
| Group close calendar | Governance artifact | Owned by the Group Controller; each company's fiscal-year end date is signed off against it, and a later change to a year-end is approved against it (Edge Case 4) |
| Statutory filing calendar per jurisdiction | Regulatory requirement | Fixes the year-end an entity files on, which is why Acme Industries Inc. reports on 01 April 2025 to 31 March 2026 rather than on the parent's calendar year |
| Country localization pack per operating country | Odoo module (`l10n_*`) | 209 packs are present here; the pack for an operating country may seed a fiscal-year default, so the pack selection is reconciled against the group calendar (D-006) |
| Legal-entity register | Master data | Acme Group NV and Acme Industries Inc. exist as company records with their functional currency set before a calendar is configured on them |
| Report engine for the verification reports | Odoo module | `account_reports` is Enterprise capability and absent here; the AGPL-3 `account_financial_report_ce` add-on present in this repository supplies the Balance Sheet as-of date and the Trial Balance date range the criteria cite (DEC-002) |
| Platform version and edition confirmation | Open decision (DEC-001, DEC-002) | Recorded in the Epic's [Open Decisions Register](../../EPIC-001-enterprise-accounting-odoo.md#appendix-b-open-decisions-register); DEC-001 fixes the field and label names this story is implemented against, and DEC-002 fixes which engine renders the reports it is verified through |
| IAS 1 and ASC 210 | Accounting standard | Fix the comparative-period presentation, the disclosure required when a period is not one year, and the as-of date convention of the Balance Sheet |

### Integration Points

| Odoo Model | Integration Type | Purpose |
|------------|------------------|---------|
| `res.company` | Read and write | The record the calendar is held on: the fiscal-year end day and month, the Opening Entry date and opening journal entry read by Scenario 4, and the lock-date fields handed to STORY-001-01-05 |
| `account.move` | Read | The accounting date that decides the period an entry is reported in, and the posted opening entry whose totals must stay equal at USD 4,812,600.00 on each side, at 2 decimal places using half-up rounding, through the refusal in Scenario 4 |
| `account.move.line` | Read | The journal items summed inside a period, from which the Trial Balance totals of USD 430,000.00 and the Current Year Earnings figure of USD 70,000.00 are derived, each at 2 decimal places using half-up rounding |
| `account.journal` | Read | The Sales, Purchase and Miscellaneous journals that carry the FY2026 entries and the year-end allocation entry of Edge Case 5 |
| `account.account` | Read | Revenue 4000, Expense 6100, Accounts Receivable 1200, Accounts Payable 2000 and Retained Earnings 3100, plus the account type that carries Current Year Earnings |
| `res.currency` | Read | The `USD` definition and the 2-decimal precision every monetary assertion is rounded to using half-up rounding |
| Financial-year opening wizard | Write | The surface on which the fiscal-year end day and month and the Opening Entry date are maintained, and the second constraint path exercised by the refusal tests |

---

## Estimation

| Dimension | Rating | Basis |
|-----------|--------|-------|
| **Effort** | Low | Two fields per company plus the derived period ranges they produce, made reproducible for a second company and covered by five acceptance tests and two refusal tests. No posting logic, no migration and no integration is delivered |
| **Complexity** | Low to Medium | The configuration surface is small, but the derivation behind it is not obvious: the year is computed rather than stored, a February year-end resolves to the last day of that month, and the month-length check takes its year from the opening entry when one exists. Each mechanism is supplied by existing Odoo code and is read during discovery rather than invented |
| **Uncertainty** | Low | Every field, derivation and refusal message cited here was read in the repository during discovery. The residual unknown is the surface the setting is exposed on, which follows from DEC-001 and changes the demonstration path rather than the calendar delivered |
| **Story Points** | **3** (Fibonacci: 1, 2, 3, 5, 8, 13) | |

Three points reflects a small, well-bounded configuration surface carrying one non-obvious constraint path. Two points would understate the two refusal paths, the two-company case and the year-end presentation that all have to be proved; five would overstate work with no new model, no new posting logic and no open technical decision, and would put it level with the ten-account, nine-group chart of [STORY-001-01-01](./STORY-001-01-01-configure-coa-hierarchy.md), which is materially broader. The estimate assumes each entity's year-end date is confirmed by the Group Controller during the sprint, and it excludes the opening-balance load and the lock-date administration, which are the two stories this one unblocks.

---


## Test Requirements

### Coverage Requirement

| Metric | Requirement | Notes |
|--------|-------------|-------|
| **Minimum Test Coverage** | **80%** | Mandatory for all new functionality delivered by this story (C-007) |
| Unit Test Coverage | 80% or higher | Fiscal-year derivation from the year-end day and month, the twelve period ranges, and both refusal paths |
| Integration Test Coverage | 80% or higher | Report date ranges resolved from the calendar, the year-end earnings split, and the two-company case |
| Accounting assertion style | Numeric | Every monetary and balance assertion is compared as an amount in USD at 2 decimal places with half-up rounding, and every date assertion as a date, never inspected by eye (C-009) |
| Traceability | One test per criterion | Each of the five scenarios maps to exactly one named acceptance test (C-008) |

### Unit Test Scenarios

| Acceptance Scenario | Unit Test Focus | Key Assertions |
|---------------------|-----------------|----------------|
| Scenario 1 | Fiscal-year derivation for a calendar year | With the year-end day at 31 and the year-end month at December, the fiscal year containing 15 June 2026 is 01 January 2026 to 31 December 2026; the derived period list has a length of 12; the first period starts 01 January 2026 and the last ends 31 December 2026; every period's start date is the day after the preceding period's end date; February 2026 ends 28 February 2026 |
| Scenario 2 | Per-company independence of the setting | With the year-end month at March for Acme Industries Inc., the fiscal year containing 15 June 2025 is 01 April 2025 to 31 March 2026 and the period list has a length of 12; reading the same computation for Acme Group NV still returns 01 January 2026 to 31 December 2026, so neither company's value is read from the other |
| Scenario 3 | Month-length validation with no opening entry | Saving a year-end day of 31 with the year-end month at February raises a validation error; the stored day stays 31 and the stored month stays December; the derived FY2026 range is unchanged at 01 January 2026 to 31 December 2026 |
| Scenario 4 | Month-length validation against the opening entry | With the Opening Entry date at 01 January 2026, saving a year-end day of 30 with the year-end month at February raises a validation error whose month length is taken from 2026; the stored values are unchanged; the opening entry's date stays 31 December 2025 and its total debits equal its total credits at USD 4,812,600.00 each, a difference of USD 0.00, at 2 decimal places using half-up rounding |
| Scenario 5 | Year-end earnings split at the boundary | Current-year earnings for the fiscal year containing 31 December 2026 equal USD 70,000.00 (income USD 250,000.00 less expense USD 180,000.00); current-year earnings for the fiscal year containing 01 January 2027 equal USD 0.00 and the FY2026 result of USD 70,000.00 is folded into the retained-earnings figure; every amount rounded to 2 decimal places with half-up rounding |

### Integration Test Considerations

Every assertion below is compared numerically in USD at 2 decimal places using half-up rounding, and every date range is passed to the report explicitly.

- [ ] Post the two FY2026 entries of Scenario 5 through `account.move` and `account.move.line` and assert each posts with total debits equal to total credits at a difference of USD 0.00 before any report is read.
- [ ] Run the Trial Balance for 01 January 2026 to 31 December 2026 and reconcile Revenue 4000 at USD 250,000.00 credit and Expense 6100 at USD 180,000.00 debit to the sum of the `account.move.line` records behind them at a difference of USD 0.00, with total debits of USD 430,000.00 equal to total credits of USD 430,000.00.
- [ ] Run the Balance Sheet as of 31 December 2026 and again as of 01 January 2027 against the same posted data and assert the USD 70,000.00 moves from the Current Year Earnings line to the Retained Earnings line while the posted balance of account 3100 stays USD 0.00.
- [ ] Hold both calendars in one database — Acme Group NV on the calendar year and Acme Industries Inc. on 01 April 2025 to 31 March 2026 — and assert that a Trial Balance run per company uses that company's own range and reports total debits equal to total credits at a difference of USD 0.00 in each.
- [ ] Exercise both refusal surfaces: the company record and the financial-year opening wizard, each with a year-end of 31 February, and assert a validation error from each with the stored values unchanged at 31 and December.
- [ ] Post an entry dated 15 January 2028 with no fiscal-year setting touched since FY2026 and assert it posts into the derived FY2028 with total debits equal to total credits at USD 5,000.00 each, confirming that no unconfigured-year refusal exists and that the control is the lock date of STORY-001-01-05.
- [ ] Install one `l10n_*` localization pack into a test company whose year-end has already been set and assert that the agreed year-end day and month are either preserved or reported as changed, so a pack cannot move a company's year-end unnoticed (D-006).
- [ ] Verify multi-company isolation: a role restricted to Acme Group NV can neither read nor amend the fiscal-year setting of Acme Industries Inc. (C-014).

### Acceptance Test Mapping

| BDD Scenario | Test Method Name | Test Type |
|--------------|------------------|-----------|
| Scenario 1: Calendar fiscal year defined for the parent company | `test_calendar_fiscal_year_derives_twelve_monthly_periods` | Acceptance |
| Scenario 2: Non-calendar fiscal year defined for the subsidiary without disturbing the parent | `test_non_calendar_fiscal_year_scoped_to_subsidiary_company` | Acceptance |
| Scenario 3: A fiscal-year end day beyond the length of the selected month is refused | `test_fiscal_year_last_day_exceeding_month_length_refused` | Acceptance |
| Scenario 4: A fiscal-year change refused against the posted opening entry leaves it intact | `test_fiscal_year_change_refused_against_posted_opening_entry` | Acceptance |
| Scenario 5: Year-end earnings roll across the FY2026 period boundary | `test_year_end_earnings_roll_and_trial_balance_balanced` | Acceptance |

---

## Definition of Done

### Implementation Checklist

- [ ] All five acceptance-criteria scenarios pass, each proved by its named automated test in § Acceptance Test Mapping.
- [ ] **80% minimum test coverage achieved** for the functionality delivered by this story, reported by the repository's coverage tooling (C-007).
- [ ] Unit tests written and passing for the fiscal-year derivation, the twelve derived period ranges, the February month-end resolution, and both month-length refusal paths.
- [ ] Integration tests written and passing for the report date ranges resolved from the calendar, the year-end earnings split, the two-company case and the localization-pack check.
- [ ] The calendar is reproducible for a second company without hand-editing, and was reproduced on Acme Industries Inc. with a 01 April 2025 to 31 March 2026 year during verification.
- [ ] The fiscal-year end date of every in-scope company is recorded and signed off against the group close calendar, with a 12-period calendar per company (a feature-level success criterion of FEATURE-001-01).
- [ ] The period boundaries are handed to [STORY-001-01-04](./STORY-001-01-04-import-legacy-coa.md) as the dating window of the opening entry and to [STORY-001-01-05](./STORY-001-01-05-configure-period-lock-dates.md) as the values its lock dates are set at, and the hand-over is recorded against ORD-001.

### Accounting Reconciliation Gate

This gate is the accounting contract of the story. Each item is asserted as an amount, in the currency named, rounded to 2 decimal places using half-up rounding.

- [ ] **Debits equal credits on the year-end roll.** The year-end allocation entry dated 31 December 2026 in the Miscellaneous journal — debit Revenue 4000 USD 250,000.00, credit Expense 6100 USD 180,000.00, credit Retained Earnings 3100 USD 70,000.00 — posts with total debits of USD 250,000.00 equal to total credits of USD 250,000.00, a difference of USD 0.00.
- [ ] **Debits equal credits on every entry posted during verification,** including the two FY2026 entries of Scenario 5 (USD 250,000.00 and USD 180,000.00) and the opening entry of Scenario 4 (USD 4,812,600.00), each with a difference of USD 0.00.
- [ ] **Trial Balance balances for every period on the calendar.** The Trial Balance for 01 January 2026 to 31 December 2026 reports total debits of USD 430,000.00 equal to total credits of USD 430,000.00, and the same equality holds for each of the twelve monthly ranges and for the subsidiary's 01 April 2025 to 31 March 2026 year — the per-period form of SM-006.
- [ ] **Tax amounts tie to their tax lines.** Where a verification entry carries tax, the tax code, the base amount and the tax amount are recorded separately, and the tax amount equals the movement on the tax control account Tax Payable 2200 for the same date range at a difference of USD 0.00.
- [ ] **Report lines tie to the sub-ledger.** Every Balance Sheet and Trial Balance line for a period on this calendar equals the sum of the `account.move.line` records inside that period at a difference of USD 0.00 — Revenue 4000 at USD 250,000.00 credit, Expense 6100 at USD 180,000.00 debit, and Current Year Earnings at USD 70,000.00 for FY2026.
- [ ] **No period gap and no period overlap.** The twelve derived ranges of FY2026 cover 01 January 2026 to 31 December 2026 with each range starting the day after the preceding one ends, so a journal item dated in FY2026 is reported in exactly one period and in exactly one fiscal year.
- [ ] **The year-end figure carries forward without duplication.** The FY2026 result of USD 70,000.00 appears once as Current Year Earnings on the Balance Sheet as of 31 December 2026 and once as the prior-year result on the Balance Sheet as of 01 January 2027, and never in both lines of a single run.

### Compliance Checklist

- [ ] Licence compatibility verified per C-001 and C-002: an AGPL-3.0 compatible licence declared, and the LGPL-3 licence of `account` respected by every derived work.
- [ ] No parallel fiscal-year or accounting-period table introduced; the calendar stays on the company record and the existing report date parameters (C-012).
- [ ] Multi-company record rules exercised by test: a role restricted to Acme Group NV can neither read nor amend the fiscal-year setting of Acme Industries Inc. (C-014).
- [ ] Static analysis passes with the repository's configured tooling at zero violations, and the code follows Odoo and OCA standards (C-005, C-006).
- [ ] The confirmed platform version and edition, once DEC-001 and DEC-002 are recorded, are restated in the parent Feature and the field and label names asserted here are re-checked against them (C-010, C-011).
- [ ] IAS 1 disclosure prepared for any reporting period that is not one year — the short first year of Edge Case 3 and the year-end change of Edge Case 4 — stating the period length, the reason and the limits of comparability.
- [ ] Code reviewed and approved, with each company's fiscal-year end date countersigned by the Group Controller.

### Documentation Checklist

- [ ] Docstrings and inline comments complete for every public method delivered.
- [ ] The group fiscal-calendar record is documented alongside the code that applies it: the year-end day and month per company, the twelve derived ranges, and the group close calendar they are signed off against.
- [ ] The derivation is documented for the implementing and operating teams: periods are computed from the year-end day and month rather than stored, a February year-end resolves to the last day of that month, and a day beyond the month length is refused.
- [ ] The consequence of changing a year-end after entries are posted is documented, together with the lock-date step that precedes it (Edge Case 4).
- [ ] Finance-facing configuration notes updated so the Chief Accountant can read a company's current fiscal year and its twelve period ranges without a data request.

### Quality Checklist

- [ ] No critical or high-severity defect open against the fiscal-calendar configuration or the report date ranges derived from it.
- [ ] A Balance Sheet as of 31 December 2026 and a Trial Balance for 01 January 2026 to 31 December 2026 each return inside the Epic's budget of under 5 minutes per statement on a 12-period fiscal year (SM-005), and the calendar adds no more than 200 ms to a single posting, the parent Feature's validation-overhead target.
- [ ] Access rights verified per finance role: the Chief Accountant maintains the calendar, the Group Controller approves each year-end date and every later change, and the External Auditor holds read-only access to the setting and its history.
- [ ] Every change to the fiscal-year end day and month is retained with its author and timestamp and is readable by the External Auditor without a data request.
- [ ] **Demonstrated in the Odoo user interface to the Finance Controller and the Product Owner** by walking the six steps of § Demonstration — the Fiscal Year Last Day and Fiscal Year Last Month settings at Accounting ▸ Configuration ▸ Settings ▸ Fiscal Year, the derived FY2026 calendar, the subsidiary's April-to-March year, the Balance Sheet as of 31 December 2026, the Trial Balance for 01 January 2026 to 31 December 2026, and the two refused fiscal-year ends — with the walkthrough recorded against this story.

---

## References

### Accounting Standards

| Standard | Reference | Application to This Story |
|----------|-----------|---------------------------|
| IAS 1 | Presentation of Financial Statements, IFRS Foundation | A complete set of statements is presented at least annually with comparative information for the preceding period, which is what the fiscal calendar makes nameable; the presentation is consistent from period to period unless a change is disclosed |
| IAS 1 | Presentation of Financial Statements — reporting period other than one year | The length of the period, the reason for it and the limits of comparability are disclosed for the short first year of Edge Case 3 and the year-end change of Edge Case 4 |
| ASC 210 | FASB Accounting Standards Codification, Balance Sheet | The as-of date convention of the Balance Sheet and the current-versus-non-current presentation as of a date on this calendar |
| IFRS Foundation standards | <https://www.ifrs.org/issued-standards/list-of-standards/> | Source of the presentation and comparative-period requirements cited above |
| FASB Accounting Standards Codification | <https://asc.fasb.org/> | Source of the US GAAP presentation applied to the group's US entities |

### OCA Modules (Reference)

| Repository | Module | Relevance |
|------------|--------|-----------|
| OCA/account-closing | `account_fiscal_year_closing` | Templated year-end closing and opening moves, the candidate mechanism for the allocation entry of Edge Case 5 |
| OCA/account-closing | `account_cutoff_start_end_dates` | Prepaid and accrued cut-offs computed at a date derived from the fiscal-year end, consumed by the period close of FEATURE-001-07 |
| OCA/account-financial-reporting | `account_financial_report` | General Ledger, Trial Balance and Balance Sheet rendered from the date-range and as-of parameters this calendar supplies |
| OCA/mis-builder | `mis_builder` | Management statements built from period expressions relative to the fiscal year defined here |

### Source Code References

| Path | Relevance |
|------|-----------|
| `addons/account/models/company.py` | The fiscal-year end day and fiscal-year end month on `res.company`, both required with defaults of 31 and December; the fiscal-year computation for an arbitrary date; the opening journal entry, opening journal and Opening Entry date; the lock-date fields with their computed per-user counterparts; and the constraint that refuses a year-end day outside the length of the selected month, evaluated against the opening-entry year when one exists |
| `addons/account/wizard/setup_wizards.py` | The financial-year opening wizard — "Opening Balance of Financial Year" — carrying the year-end day and month and the Opening Entry date, its posted-state indicator, and its own constraint that tests the day-and-month pair against a leap year |
| `addons/account/wizard/setup_wizards_view.xml` | The form that labels the day-and-month pair **Fiscal Year End**, the surface used in the demonstration |
| `addons/account/views/res_config_settings_views.xml` | The Fiscal Periods block of the accounting settings page named in the demonstration path |
| `odoo/tools/date_utils.py` | The fiscal-year derivation from a date plus a year-end day and month, including the February handling behind Edge Case 2 |
| `addons/account/models/account_move.py` | The accounting date that places an entry in a period and a fiscal year, and the posting state read by the Scenario 4 assertions |
| `addons/account/models/account_account.py` | The account types behind Revenue 4000, Expense 6100, Retained Earnings 3100 and the Current Year Earnings presentation line |
| `addons/account/wizard/account_resequence.py` | A consumer of the company fiscal-year computation, showing how a fiscal year is derived for an entry outside the reporting surface |
| `addons/account_financial_report_ce/models/balance_sheet.py` | The Balance Sheet with its as-of date, its optional fiscal-year start, and the split between current-year earnings and the prior-year result folded into equity — the behaviour Scenario 5 asserts |
| `addons/account_financial_report_ce/models/trial_balance.py` | The Trial Balance with its date range and its opening-balance cut at the day before the range start |
| `addons/account/__manifest__.py` | The `account` module identity cited in the criteria: "Invoicing", version 1.4, category `Accounting/Accounting`, licence LGPL-3 |
| `addons/l10n_*/` | The 209 localization packs present here, some of which seed a country-specific fiscal-year default (D-006) |
| `odoo/release.py` | The platform baseline `version_info = (19, 0, 0, FINAL, 0, '')` with `MIN_PY_VERSION = (3, 10)`, cited by DEC-001 |

### Ticket References

| Document | Link |
|----------|------|
| Parent Feature | [FEATURE-001-01: Chart of Accounts & Fiscal Year](../FEATURE-001-01-chart-of-accounts-fiscal-year.md) |
| Parent Epic | [EPIC-001: Enterprise Accounting in Odoo](../../EPIC-001-enterprise-accounting-odoo.md) |
| Persona register the WHO is drawn from | [EPIC-001 §3.1 User Personas](../../EPIC-001-enterprise-accounting-odoo.md#31-user-personas) |
| Success metrics SM-003, SM-005 and SM-006, which this calendar is measured through | [EPIC-001 §4.1 Measurable Outcomes](../../EPIC-001-enterprise-accounting-odoo.md#41-measurable-outcomes) |
| Authoring bounds: 4-to-8 criteria, coverage distribution, Fibonacci scale | [EPIC-001 §5.3 Decomposition Guidelines](../../EPIC-001-enterprise-accounting-odoo.md#53-feature-and-story-decomposition-guidelines) |
| Ordering rule ORD-001, which gates the posting features on this feature | [EPIC-001 §6.2 Inter-Feature Ordering](../../EPIC-001-enterprise-accounting-odoo.md#62-inter-feature-ordering) |
| Constraint set C-001 to C-022 | [EPIC-001 §7 Constraints](../../EPIC-001-enterprise-accounting-odoo.md#7-constraints) |
| Open decisions DEC-001 and DEC-002 | [EPIC-001 Appendix B: Open Decisions Register](../../EPIC-001-enterprise-accounting-odoo.md#appendix-b-open-decisions-register) |
| Sibling stories | [STORY-001-01-01](./STORY-001-01-01-configure-coa-hierarchy.md) · [STORY-001-01-02](./STORY-001-01-02-map-accounts-ifrs-gaap-taxonomy.md) · [STORY-001-01-04](./STORY-001-01-04-import-legacy-coa.md) · [STORY-001-01-05](./STORY-001-01-05-configure-period-lock-dates.md) |

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-01 | Enterprise Accounting Team | Initial story creation |

---

## Notes

**Platform version and edition remain open (DEC-001, DEC-002).** The originating programme request names Odoo 17, this repository is Odoo 19.0 Community, and the prior superseded backlog targeted 18.0. This story states the fields, labels, refusal messages and menu paths as they exist in the 19.0 baseline it was verified against, and flags the mismatch for stakeholder confirmation rather than choosing a target. The edition decision affects only the verification surface: the Balance Sheet and Trial Balance the criteria are proved through are Enterprise capability in `account_reports`, which is absent here, while the AGPL-3 `account_financial_report_ce` add-on present in this repository supplies both with the as-of date and date-range parameters cited, so the story is demonstrable today under either path.

**Odoo derives periods; it does not store them — a discovery point for the implementing agent.** There is no fiscal-year record and no accounting-period record in the baseline read during discovery. A company carries a fiscal-year end day and a fiscal-year end month, and every fiscal year and period range is computed from that pair for the date being reported. Three consequences run through this story and should be carried into implementation: an entry can be dated in a year nobody configured and will still post (Edge Case 1), so the control on posting into a reported or future period is the lock date of [STORY-001-01-05](./STORY-001-01-05-configure-period-lock-dates.md) rather than the calendar; changing the pair re-derives every boundary retroactively (Edge Case 4), so the change is approved and preceded by a lock date; and a February year-end resolves to the last day of that month in the year concerned, which is why a year-end of 29 February is accepted deliberately while a day beyond the month length is refused (Edge Case 2, Scenarios 3 and 4). Whether the twelve derived ranges are surfaced as a selectable period list, and on which form the pair is maintained, is left to the implementing agent's discovery.

**Two refusal surfaces, two messages.** The month-length check exists both on the company record and on the financial-year opening wizard, and the wizard's own check evaluates the day-and-month pair against a leap year while the company check evaluates it against the year of the opening entry or the current year. Scenarios 3 and 4 assert the refusal and the unchanged stored values rather than one message string, so either surface satisfies them; the tests exercise both.

**Company names.** Acme Group NV (parent, functional currency `USD`) and Acme Industries Inc. (subsidiary) are the reference entities used across this backlog so that every multi-company assertion names the books it affects. They stand for the group's legal-entity register, which is enumerated during discovery; substituting the confirmed entity names changes the names in the criteria and nothing else.

**Scope of this ticket.** This file is a planning artifact. It states the fiscal calendar finance requires and the assertions that prove it; it contains no module, model, view or data definition, and it prescribes none. No Odoo module is created, installed or configured by authoring it.

