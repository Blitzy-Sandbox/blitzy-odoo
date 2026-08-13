# STORY-001-06-01: Configure Company Hierarchy and Currencies

---

## Metadata

| Attribute | Value |
|-----------|-------|
| **Story ID** | `STORY-001-06-01` |
| **Title** | Configure Company Hierarchy and Currencies |
| **Parent Feature** | [FEATURE-001-06: Multi-Company & Intercompany Consolidation](../FEATURE-001-06-multi-company-consolidation.md) |
| **Parent Epic** | [EPIC-001: Enterprise Accounting in Odoo](../../EPIC-001-enterprise-accounting-odoo.md) |
| **Status** | Draft |
| **Priority** | 🔴 Critical |
| **Estimate** | 5 story points (Fibonacci) |
| **Persona** | Group Controller |
| **Feature Capability** | CAP-001 — define the parent and subsidiary company hierarchy with functional and presentation currencies and ownership percentages |
| **Epic Success Metric** | SM-013 — Consolidated Balance Sheet and Profit & Loss published within 48 hours of the last entity close |
| **Owner/Author** | Enterprise Accounting Team |

This is the root story of the `FEATURE-001-06/` folder. It fixes the group whose books the other four stories of the feature consolidate — **Global Holdings Inc.** (entity code `US-01`, functional currency USD, which is also the group presentation currency), **Global Europe SARL** (`NL-01`, functional currency EUR, wholly owned at 100.00%, incorporated by the parent on 2019-01-01) and **Global Asia Pte Ltd** (`SG-01`, functional currency SGD, wholly owned at 100.00%, incorporated by the parent on 2021-01-01) — together with the closing, average and historical rates that translate each subsidiary into USD. Ordering rule **ORD-003** in the Epic places this story ahead of every other story in the feature for that reason: an intercompany entry has no second set of books to post into, and a consolidation rule has no entity chart to map, until the hierarchy and its currencies exist.

---

## User Story

**As a** Group Controller

**I want** the group's legal entities held as one hierarchy in the system of record — Global Holdings Inc. as the parent of Global Europe SARL and Global Asia Pte Ltd, each subsidiary carrying its functional currency, its ownership percentage and full consolidation as its method, with USD fixed as the group presentation currency and with the closing, average and historical rates that translate each subsidiary into it recorded against a rate date

**So that** every consolidation run reads the group's composition and its translation rates from governed configuration instead of from a workbook tab, and Global Europe SARL's Trial Balance total assets of `€850,000.00 EUR` reach the group presentation currency as `$922,250.00 USD` at the 2025-03-31 closing rate of 1.0850 USD/EUR — rounded to 2 decimal places at the USD rounding increment of 0.01 — with no manual conversion step between the entity ledger and the group position (SM-013).

---

## INVEST Principles Compliance

| Principle | Compliance | Notes |
|-----------|------------|-------|
| **Independent** | ✅ with a stated data prerequisite | This story does **not** claim bare independence. It is **blocked by** [STORY-001-01-01](../FEATURE-001-01/STORY-001-01-01-configure-coa-hierarchy.md) and [STORY-001-01-02](../FEATURE-001-01/STORY-001-01-02-map-accounts-ifrs-gaap-taxonomy.md): the group chart of accounts and its IFRS and US GAAP taxonomy must exist before an entity chart can be mapped onto the group, and before the five group codes this feature adds — Intercompany Receivable 1300, Intercompany Payable 2100, Investment in Subsidiary 1700, Currency Translation Adjustment 3200 and Foreign Exchange Gain/Loss 7200 — can be approved into that chart. The prerequisite is **master-data configuration, not code coupling**: it is satisfied by a chart-and-taxonomy fixture, so this story can be built, tested and demonstrated against that fixture while FEATURE-001-01 is still in flight, and it shares no implementation with either predecessor. Within `FEATURE-001-06/` it has no predecessor at all. |
| **Negotiable** | ✅ | The outcome is fixed — three named entities in one hierarchy, one functional currency and one ownership percentage per entity, one group presentation currency, and three classes of rate addressable by rate date — while the mechanism stays open. Whether the ownership percentage and the group-membership flag are held on the company record, on a group-structure record beside it, or on a consolidation-scope record is deferred to the discovery recorded in § Technical Discovery Notes. The entity codes `US-01`, `NL-01` and `SG-01` and the labels shown to the Group Controller stay negotiable for as long as each entity still resolves to exactly one parent and one functional currency. |
| **Valuable** | ✅ | Nothing else in `FEATURE-001-06/` can be delivered before it: ORD-003 gates the intercompany, rule-set, elimination and consolidated-statement stories on this configuration, and the Epic's 48-hour consolidated-pack target (SM-013) and its intercompany-elimination completeness target (SM-012) both read the group composition this story fixes. It also carries the IFRS 12 disclosure of the group's composition from informal notes into reportable configuration. |
| **Estimable** | ✅ | The deliverable is countable: 3 companies, 2 parent links, 3 functional currencies, 2 ownership percentages, 1 group presentation currency and 7 dated rate records across two currency pairs, against `res.company`, `res.currency` and `res.currency.rate`, whose field surfaces were read in this repository and are cited below. The one unknown — where the ownership percentage lives, since no such field exists on `res.company` — is bounded and named, which is why the estimate lands at 5 rather than 3 (see § Estimation). |
| **Small** | ✅ | One configuration outcome, demonstrated in a single walkthrough: the hierarchy of three entities, the rate table behind it, and one translated total of `$922,250.00 USD` taken at the 2025-03-31 closing rate of 1.0850 USD/EUR and rounded to 2 decimal places at the USD rounding increment of 0.01. Intercompany posting, the consolidation rule set, the eliminations and the consolidated statements are each a separate sibling story, so this story is not a container for the feature. |
| **Testable** | ✅ | Every criterion below resolves to a count, a code, a currency, a percentage, a named refusal message or an amount: 2 subsidiaries whose root company is Global Holdings Inc., an ownership percentage of 100.00% each, a count of 0 entities missing a parent link or a functional currency or an ownership percentage, a translated total of exactly `$922,250.00 USD` at the 2025-03-31 closing rate of 1.0850 USD/EUR rounded to 2 decimal places at the USD rounding increment of 0.01, and a refused save that leaves the group at 3 companies. Each of the seven scenarios maps to one named automated test in § Test Requirements, so pass or fail is decided without judgement. |

---

## Acceptance Criteria

Seven criteria are authored, inside the 4-to-8 bound the Epic sets for a story, and they carry the mandated coverage distribution: **Scenarios 1, 2 and 3** are the valid-input cases (the euro-area subsidiary, the Singapore subsidiary, then the rate that translates one of them); **Scenario 4** is the invalid and incomplete-input case; **Scenario 5** is the error-handling case; **Scenario 6** is the accounting edge case, where a locked period refuses a functional-currency change; and **Scenario 7** is the multi-company isolation case required by C-014 and D-007.

Every criterion names the company whose configuration or books are affected. Every amount states its currency and its rounding, and every translated amount also states the rate and the rate date it was translated at, so no figure below is a bare conversion. The scenarios are cumulative: Scenario 1 leaves the group at two entities, Scenario 2 brings it to three, and Scenarios 3 to 7 are asserted against that three-entity group.

### Scenario 1: Euro-area subsidiary linked to the group parent with its functional currency and ownership

- **Given** Global Holdings Inc. (entity code `US-01`) exists as a company whose functional currency is USD and whose group presentation currency is USD, it holds no parent link, and Global Europe SARL (entity code `NL-01`) exists as a company holding no parent link, no ownership percentage and no consolidation method, while the group chart of accounts and its IFRS and US GAAP taxonomy released by FEATURE-001-01 are present in both companies
- **When** the Group Controller saves the group-structure attributes of Global Europe SARL in one operation: parent company Global Holdings Inc., functional currency EUR, ownership percentage 100.00% and full consolidation as its method
- **Then** the group hierarchy presents Global Holdings Inc. as the root company of Global Europe SARL, Global Europe SARL as a subsidiary rather than a branch of Global Holdings Inc., the functional currency of Global Europe SARL as EUR, its ownership percentage as 100.00% and its consolidation method as full consolidation; the group presentation currency held against Global Holdings Inc. stays USD; across Global Holdings Inc. and Global Europe SARL the count of in-scope entities with no parent link where one is required, no functional currency, or no ownership percentage is 0; and no posted journal item in either company is altered by the change, so the Trial Balance of Global Europe SARL for the date range 2025-01-01 to 2025-03-31 reports total debits equal to total credits at a difference of `€0.00 EUR`, rounded to 2 decimal places at the EUR rounding increment of 0.01

### Scenario 2: Singapore subsidiary added in a third currency with its ownership percentage and method

- **Given** Global Holdings Inc. is the root company of Global Europe SARL with functional currency EUR and ownership percentage 100.00% as configured in Scenario 1, and Global Asia Pte Ltd (entity code `SG-01`) exists as a company holding no parent link, no ownership percentage and no consolidation method
- **When** the Group Controller saves the group-structure attributes of Global Asia Pte Ltd in one operation: parent company Global Holdings Inc., functional currency SGD, ownership percentage 100.00% and full consolidation as its method
- **Then** the group hierarchy presents Global Holdings Inc. as the root company of both Global Europe SARL and Global Asia Pte Ltd, the functional currency of Global Asia Pte Ltd as SGD, its ownership percentage as 100.00% and its consolidation method as full consolidation; the count of companies whose root company is Global Holdings Inc. is 3 including Global Holdings Inc. itself, and the count of consolidated subsidiaries is 2; because Global Asia Pte Ltd is wholly owned, the non-controlling interest arising on it is 0.00% and no minority-interest measurement is carried for it, matching the Epic's scope boundary; the entity codes `US-01`, `NL-01` and `SG-01` each resolve to exactly one company, so no two entities share an identifier; the group presentation currency held against Global Holdings Inc. stays USD while Global Europe SARL keeps EUR and Global Asia Pte Ltd keeps SGD as their functional currencies; and the group composition — parent, functional currency, ownership percentage, consolidation method and country of incorporation per entity — is readable as configuration for the IFRS 12 disclosure rather than held in narrative notes

### Scenario 3: Closing rate recorded and the euro-area Trial Balance reaches the group presentation currency

- **Given** the three-entity hierarchy of Scenario 2 is in force with USD as the group presentation currency; the rate table already carries the EUR average rate of 1.0720 USD/EUR for the date range 2025-01-01 to 2025-03-31, the EUR historical rate of 1.1000 USD/EUR dated 2019-01-01 for the incorporation of Global Europe SARL, the SGD closing rate of 0.7450 USD/SGD dated 2025-03-31, the SGD average rate of 0.7380 USD/SGD for the same date range and the SGD historical rate of 0.7300 USD/SGD dated 2021-01-01 for the incorporation of Global Asia Pte Ltd; no EUR closing rate is recorded for 2025-03-31; and the Trial Balance of Global Europe SARL for the date range 2025-01-01 to 2025-03-31 reports total assets of `€850,000.00 EUR` with total debits equal to total credits at a difference of `€0.00 EUR`, every amount rounded to 2 decimal places at the EUR rounding increment of 0.01
- **When** the Group Controller records the EUR closing rate of 1.0850 USD/EUR against the rate date 2025-03-31
- **Then** the total assets of `€850,000.00 EUR` held by Global Europe SARL translate to `$922,250.00 USD` at the 2025-03-31 closing rate of 1.0850 USD/EUR, rounded to 2 decimal places at the USD rounding increment of 0.01, and that translated total is reproducible from the stored rate rather than from a figure typed by hand; each of the three EUR rates stays addressable by its own rate type and rate date — closing at 2025-03-31 of 1.0850 USD/EUR, average for 2025-01-01 to 2025-03-31 of 1.0720 USD/EUR and historical at 2019-01-01 of 1.1000 USD/EUR — so no translation reads an undated rate; the three SGD rates for Global Asia Pte Ltd stay unchanged at 0.7450 USD/SGD closing at 2025-03-31, 0.7380 USD/SGD average for the same date range and 0.7300 USD/SGD historical at 2021-01-01; the count of currency pairs and rate dates required by the group and missing from the rate table falls to 0; and the decimal precision applied to each translated amount is read from the currency record of the group presentation currency USD, which carries a rounding increment of 0.01 and therefore 2 decimal places

### Scenario 4: Subsidiary saved with no functional currency and no ownership percentage is refused

- **Given** the three-entity hierarchy of Scenario 2 is in force, holding Global Holdings Inc., Global Europe SARL and Global Asia Pte Ltd
- **When** the Group Controller saves a candidate fourth entity as a consolidated subsidiary of Global Holdings Inc. with its functional currency left empty and its ownership percentage left empty
- **Then** the save is refused with an Odoo validation message that names the functional currency and the ownership percentage as the required attributes that are absent; no company record is created for the candidate entity, so the group still holds exactly the 3 companies Global Holdings Inc., Global Europe SARL and Global Asia Pte Ltd, and the count of consolidated subsidiaries stays at 2; no rate record is written for a currency that was never assigned; Global Europe SARL keeps functional currency EUR at ownership 100.00% and Global Asia Pte Ltd keeps functional currency SGD at ownership 100.00%; and the translated total assets of Global Europe SARL as of 2025-03-31 stay at `$922,250.00 USD` at the closing rate of 1.0850 USD/EUR, rounded to 2 decimal places at the USD rounding increment of 0.01

### Scenario 5: Circular hierarchy is blocked and the group structure is left intact

- **Given** the three-entity hierarchy of Scenario 2 is in force, with Global Holdings Inc. as the root company of both Global Europe SARL and Global Asia Pte Ltd
- **When** the Group Controller sets the parent company of Global Holdings Inc. to Global Europe SARL, which is its own descendant
- **Then** the save is refused with an Odoo validation message that names Global Holdings Inc. and Global Europe SARL and states that the assignment would place a company inside its own hierarchy; the hierarchy is unchanged, so Global Holdings Inc. remains the root company of both Global Europe SARL and Global Asia Pte Ltd and holds no parent link; Global Europe SARL keeps functional currency EUR at ownership 100.00% and Global Asia Pte Ltd keeps functional currency SGD at ownership 100.00%; the count of companies whose root company is Global Holdings Inc. stays at 3 including itself; and no rate record, no configuration attribute of another entity and no posted journal item in any of the three companies is modified by the refused attempt

### Scenario 6: Functional-currency change refused for a company whose period is locked

- **Given** Global Europe SARL carries posted journal items for the date range 2025-01-01 to 2025-03-31 whose Trial Balance reports total assets of `€850,000.00 EUR` with total debits equal to total credits at a difference of `€0.00 EUR`, each amount rounded to 2 decimal places at the EUR rounding increment of 0.01, its journal-entry lock date is set to 2025-03-31 under the closing controls owned by STORY-001-01-05, and the EUR closing rate of 1.0850 USD/EUR is recorded against the rate date 2025-03-31
- **When** the Group Controller changes the functional currency of Global Europe SARL from EUR to USD
- **Then** the change is refused with an Odoo validation message that names Global Europe SARL and its journal-entry lock date of 2025-03-31; Global Europe SARL keeps EUR as its functional currency and 100.00% as its ownership percentage; every journal item already posted in Global Europe SARL keeps the EUR amount it was posted at, so its Trial Balance for the date range 2025-01-01 to 2025-03-31 still reports total assets of `€850,000.00 EUR` with total debits equal to total credits at a difference of `€0.00 EUR`, rounded to 2 decimal places at the EUR rounding increment of 0.01; the translated total assets of Global Europe SARL as of 2025-03-31 stay at `$922,250.00 USD` at the closing rate of 1.0850 USD/EUR, rounded to 2 decimal places at the USD rounding increment of 0.01, so the group position already published for that period stays reproducible; and the message states the re-measurement path — a change of functional currency applies from a date after the lock date, with the entity's comparative balances re-presented rather than its locked journal items rewritten

### Scenario 7: Company isolation holds across the three entities

- **Given** the three-entity hierarchy of Scenario 2 is in force; a Consolidation Accountant whose allowed companies contain Global Europe SARL alone; a Group Controller whose allowed companies contain Global Holdings Inc., Global Europe SARL and Global Asia Pte Ltd; and posted journal items for the date range 2025-01-01 to 2025-03-31 in all three companies
- **When** the Consolidation Accountant reads the group's journal items for the date range 2025-01-01 to 2025-03-31
- **Then** the result contains the journal items of Global Europe SARL alone, no journal item of Global Asia Pte Ltd and no journal item of Global Holdings Inc. is returned, and the count of companies readable by the Consolidation Accountant is 1; the same read performed by the Group Controller returns the journal items of all three companies and the count of companies readable by the Group Controller is 3, with the Trial Balance total assets of Global Europe SARL reported at `€850,000.00 EUR` and those of Global Asia Pte Ltd at `S$1,200,000.00 SGD`, each rounded to 2 decimal places at the rounding increment of 0.01 for its currency; and the cross-company read performed on behalf of the group is recorded with the persona and the companies it covered, so the External Auditor reads which entities were accessed and by whom rather than inferring it

---

## Sub-Tasks

| # | Sub-Task | Assignee |
|---|----------|----------|
| 1 | Document the group structure as the source of truth for the whole feature: Global Holdings Inc. (`US-01`, United States, functional currency USD, group presentation currency USD), Global Europe SARL (`NL-01`, euro area, functional currency EUR, ownership 100.00%, incorporated by the parent on 2019-01-01) and Global Asia Pte Ltd (`SG-01`, Singapore, functional currency SGD, ownership 100.00%, incorporated by the parent on 2021-01-01), each with full consolidation as its method and each carrying the consequence that no non-controlling interest arises | `@finance-sme` |
| 2 | Specify the configuration model the Group Controller maintains: the parent link per entity, the functional currency per entity, the group presentation currency, the ownership percentage, the consolidation method and the group-membership flag — recording for each attribute whether it is held on the existing company record or on a group-structure record beside it, with the answer taken from the discovery in § Technical Discovery Notes rather than assumed | `@functional-consultant` |
| 3 | Specify the rate policy this story configures and the four sibling stories consume: closing rate at the as-of date, average rate for the reporting date range, and historical rate at an entity's incorporation date, each addressable by rate type and rate date, with the worked set being 1.0850 USD/EUR at 2025-03-31, 1.0720 USD/EUR for 2025-01-01 to 2025-03-31, 1.1000 USD/EUR at 2019-01-01, 0.7450 USD/SGD at 2025-03-31, 0.7380 USD/SGD for the same range and 0.7300 USD/SGD at 2021-01-01 | `@functional-consultant` |
| 4 | Implement the ownership-percentage and consolidation-method configuration, with the percentage constrained to a value greater than 0.00% and at most 100.00% for an entity declared a consolidated subsidiary, and with the functional currency required on every entity in the group | `@developer` |
| 5 | Implement rate maintenance and retrieval for the closing, average and historical rate classes, reading each currency's rounding increment and decimal places from the currency record so no translation hard-wires 2 decimal places | `@developer` |
| 6 | Implement the hierarchy guards: refusal of a parent assignment that places a company inside its own hierarchy, and refusal of a functional-currency change for a company whose journal-entry lock date already covers posted journal items | `@developer` |
| 7 | Verify record-rule scoping across the three entities — a Consolidation Accountant holding Global Europe SARL alone reads no journal item of Global Asia Pte Ltd or Global Holdings Inc., while a Group Controller holding all three reads all three — and verify the circular-hierarchy refusal leaves Global Holdings Inc. as the root company of both subsidiaries | `@qa-engineer` |
| 8 | Author the seven automated acceptance tests named in § Test Requirements, one per scenario, plus the hostile-input tests C-022 requires on the exchange-rate feed path, with every count, percentage and amount written as an assertion | `@qa-engineer` |
| 9 | Confirm the translated figure against its source: total assets of `€850,000.00 EUR` for Global Europe SARL at the 2025-03-31 closing rate of 1.0850 USD/EUR give `$922,250.00 USD`, rounded to 2 decimal places at the USD rounding increment of 0.01, and sign off that each entity's opening balances tie to its own Trial Balance before the first consolidation run | `@finance-sme` |
| 10 | Sign off the group composition disclosure — parent, ownership percentage, functional currency and country per entity — as the configuration the IFRS 12 note is drawn from, and confirm the consolidation scope with the External Auditor | `@finance-sme` |

---

## Edge Cases

| # | Edge Case | Expected Handling |
|---|-----------|-------------------|
| 1 | **Zero or absent value in a required group attribute** — an entity declared a consolidated subsidiary of Global Holdings Inc. is saved with its ownership percentage set to 0.00%, or with its functional currency left empty | Both saves are refused with an Odoo validation message naming the attribute at fault: an ownership percentage of 0.00% states that the parent holds nothing, which contradicts the declaration of the entity as a consolidated subsidiary, and a company with no functional currency has no unit to measure its books in. No company record is created and no attribute of an existing entity is changed, so the group stays at 3 companies with Global Europe SARL at functional currency EUR and ownership 100.00% and Global Asia Pte Ltd at functional currency SGD and ownership 100.00%. An entity held for sale and excluded from the group is expressed by clearing its group-membership flag, not by setting its ownership percentage to 0.00% |
| 2 | **Fiscal-period lock already covers the change** — the functional currency of Global Europe SARL, or its parent link to Global Holdings Inc., is changed after journal items have been posted in a period on or before its journal-entry lock date of 2025-03-31 | The change is refused with an Odoo validation message naming Global Europe SARL and the lock date of 2025-03-31, and every posted journal item keeps the EUR amount it was posted at, so the translated total assets of Global Europe SARL as of 2025-03-31 stay at `$922,250.00 USD` at the closing rate of 1.0850 USD/EUR, rounded to 2 decimal places at the USD rounding increment of 0.01, and the group position already published for that period stays reproducible. A change of group structure takes effect from a date after the lock date, and where the group has to reopen the period it does so through the recorded lock-date exception path rather than by editing locked journal items |
| 3 | **An entity whose currency rounding increment is not 0.01** — a fourth entity measured in a currency such as JPY, whose rounding increment is 1 and whose decimal places are therefore 0, joins the group whose presentation currency USD carries a rounding increment of 0.01 and 2 decimal places | Precision is read from each currency record at translation time rather than assumed: the entity's own balances are held and presented at the decimal places its functional currency declares, and the amount translated into the group presentation currency USD is rounded to 2 decimal places at the USD rounding increment of 0.01. The rounding difference that arises on translation is presented in Currency Translation Adjustment 3200 rather than absorbed into Retained Earnings 3100, and no code path hard-wires 2 decimal places for an entity currency |
| 4 | **Entity joins the group part-way through the fiscal year** — an entity acquired on 2025-02-15 inside the reporting date range 2025-01-01 to 2025-03-31 | The acquisition date is recorded against the entity alongside its ownership percentage, and only results arising from 2025-02-15 onward belong to the group, while its pre-acquisition reserves are carried at the historical rate on the acquisition date rather than at the 2025-03-31 closing rate of the reporting period. The Balance Sheet position of the acquired entity is consolidated in full as of 2025-03-31 while its Profit & Loss is included from the acquisition date, and the configuration records which date each treatment is drawn from so the split is reproducible rather than re-derived per run |
| 5 | **Parent assignment that would place a company inside its own hierarchy** — the parent company of Global Holdings Inc. is set to Global Europe SARL or to Global Asia Pte Ltd, or an entity is set as its own parent | The save is refused with an Odoo validation message naming both companies in the attempted link, the existing hierarchy is left intact with Global Holdings Inc. as the root company of both Global Europe SARL and Global Asia Pte Ltd, and the count of companies whose root company is Global Holdings Inc. stays at 3 including itself. A genuine restructuring — an intermediate holding company inserted between Global Holdings Inc. and Global Europe SARL — is expressed by parenting the new entity under Global Holdings Inc. first and reparenting Global Europe SARL onto it second, so no intermediate state is circular |

---

## Constraints

### License and Compliance

- [ ] **C-001 — AGPL-3.0 compatible licence.** Any module delivering the group hierarchy, the ownership-percentage configuration or the rate policy is distributed under an AGPL-3.0 compatible licence, matching the Community-edition accounting add-ons already present in this repository.
- [ ] **C-002 — Existing licence respected.** `res.company`, `res.currency` and `res.currency.rate` are `base` models and `account.account` and `account.journal` are `account` models, all under LGPL-3; any extension of them stays licence-compatible, and no derived work misstates the licence of the code it extends.
- [ ] **C-005 and C-006 — Odoo and OCA standards.** Python follows Odoo and OCA module guidelines including PEP 8, and static analysis passes with the repository's configured tooling, whose lint configuration is declared in `ruff.toml` at the repository root.
- [ ] **C-012 — Build on the existing models.** The hierarchy is expressed against the existing company model and the currencies and rates against the existing currency and rate models rather than against a parallel structure, so one audit trail covers the group's composition.

### Dependency and Edition Considerations

- [ ] **C-003 — The edition source is an open decision, recorded as DEC-002.** `account_consolidation` is **absent from `addons/`** in this repository: the present accounting layer is `account`, the "Invoicing" application at version 1.4 under LGPL-3, alongside `account_payment`, `account_edi` and 209 `l10n_*` localization packs. Consolidation capability therefore arrives from an Odoo Enterprise subscription, from Odoo Community Association add-ons such as those in OCA/account-consolidation and OCA/multi-company, or from bespoke development on the company, currency and accounting models already present. The three paths differ in licensing, cost and remaining build, so the choice is **flagged for stakeholder confirmation** as DEC-002, owned by the CFO / Finance Director with the Group Controller, and the Epic gates FEATURE-001-06 through FEATURE-001-09 on it. This story is the least exposed of the five, because the company hierarchy, the functional currencies and the rate records it configures are held on `base` models present under every candidate path.
- [ ] **C-004 — OCA ecosystem compatibility.** Whichever path DEC-002 confirms, the hierarchy, the ownership percentages and the rate records configured here stay consumable by OCA add-ons, so the group can be rendered by an OCA reporting engine without restating this configuration.

**On the prior prohibition and the prior scope boundary.** The superseded backlog that preceded this tree took the opposite position on both counts: it declared multi-company consolidation with intercompany eliminations out of scope, fixed single-company operation as the programme boundary, and prohibited any dependency on Odoo Enterprise modules outright. Both positions are withdrawn rather than restated. Multi-entity operation is the stated objective of this Epic, which is why a group of three legal entities is configured here at all; and the blanket prohibition is replaced by the open edition decision above, because the absence of `account_consolidation` from this repository is a fact to plan around rather than a rule forbidding its use. Asserting either edition inside this story would pre-empt a decision that carries licensing and cost consequences for the programme.

### Version Compatibility

- [ ] **C-010 — The platform version target is an open decision, recorded as DEC-001 and inherited from the Epic's platform-version dependency.** Three targets are on record and they are mutually exclusive: the originating programme request names **Odoo 17**; this repository is **Odoo 19.0 Community**, where `odoo/release.py` declares `version_info = (19, 0, 0, FINAL, 0, '')`; and the prior, superseded backlog targeted **18.0**. The mismatch is **flagged for stakeholder confirmation** and is not resolved inside this story. Any statement of a single target version made elsewhere in the prior tooling is superseded by DEC-001.
- [ ] **C-011 — Language and database versions follow the confirmed target.** The 19.0 baseline in this repository declares `MIN_PY_VERSION = (3, 10)` and `MIN_PG_VERSION = 13` in `odoo/release.py`; an earlier platform target carries a different supported matrix.
- [ ] **Impact if DEC-001 resolves to a version other than 19.0.** The company parent-child field surface cited in § Technical Discovery Notes is restated for the confirmed version, because the hierarchy mechanism and the fields computed from it changed across those releases; the multi-company record-rule and allowed-companies behaviour behind Scenario 7 is re-verified; the direction in which a stored currency rate is expressed is re-confirmed, since every translated amount in this story depends on it; and the lock-date fields behind Scenario 6 are re-checked.

### Multi-Company Access and Untrusted Input

- [ ] **C-014 and D-007 — Company isolation is respected rather than bypassed.** Record rules and the allowed-companies mechanism scope which entities a finance role reads; the cross-company read a consolidation run performs is an explicit, logged elevation rather than a suspension of record rules, and Scenario 7 is the test that proves it.
- [ ] **C-015 through C-022 — The exchange-rate feed is an untrusted boundary.** The feed that supplies the closing, average and historical rates this story records is validated before a rate record is written: response content type and size are checked against an allowlist, XML is parsed with document-type definitions and external-entity resolution disabled and entity expansion bounded, the payload is validated against its declared schema before any field is read, and each rate value is range-checked. A rejected response writes no rate record, creates no journal entry, leaves the last confirmed rate in force, discloses no stack trace or complete payload, and leaves the service available. C-022 requires this story to carry at least one acceptance test per hostile case.

### Accounting Standards Compliance

- [ ] **IFRS 10 and US GAAP ASC 810 — consolidation scope.** Control determines the scope: Global Europe SARL and Global Asia Pte Ltd are wholly owned at 100.00% and are consolidated in full, which is why no non-controlling interest arises and no minority-interest measurement is configured. Non-controlling-interest allocation and equity-method accounting are outside this Epic's scope.
- [ ] **IAS 21 and US GAAP ASC 830 — functional currency and translation.** Each entity's functional currency is recorded as a governed attribute, and the rate classes this story configures carry the translation policy the sibling stories apply: closing rate for assets and liabilities at the as-of date, average rate for income and expense over the reporting date range, and historical rate for subscribed capital at the incorporation date, with the residual presented in Currency Translation Adjustment 3200 rather than in Retained Earnings 3100.
- [ ] **IFRS 12 — disclosure of interests in other entities.** The composition of the group — parent, ownership percentage, functional currency and country of incorporation per entity — is held as reportable configuration, so the disclosure is read from the system of record.

---

## Technical Discovery Notes

This section records **what the implementing agent must determine**, with the repository evidence that frames each question. It prescribes no design: no module name, no model inheritance approach, no view architecture, no report engine, no interface structure and no database schema is dictated here. Every field and file cited below was read in this repository at Odoo 19.0 Community and is re-verified against the platform target DEC-001 confirms.

### Codebase Analysis Areas

| Area | Files/Modules to Examine | Analysis Focus |
|------|--------------------------|----------------|
| Company hierarchy | `odoo/addons/base/models/res_company.py` — `parent_id` is a `Many2one` to `res.company` labelled "Parent Company", indexed, with `ondelete='restrict'` (L36); `child_ids` is the reciprocal `One2many` **labelled "Branches"** (L37); `all_child_ids` (L38) and an indexed `parent_path` (L39) sit beside it; `parent_ids` (L40) and `root_id` (L41) are computed with `compute_sudo=True` and derived from `parent_path` (L118–L119) | Whether a mechanism whose own field label reads "Branches" expresses a group of separate legal entities, so that Global Europe SARL and Global Asia Pte Ltd are subsidiaries of Global Holdings Inc. rather than branches of it; what `root_id` implies for records that default to the root company of a hierarchy; and which guard refuses the parent assignment of Scenario 5 and with what message |
| Ownership percentage and consolidation method | `odoo/addons/base/models/res_company.py` in full — **no ownership-percentage field, no consolidation-method field and no group-membership flag exist on the company model**; the token "ownership" does not appear anywhere in the file | This is the one genuinely new attribute set in the story: because no such field exists, the ownership percentage of 100.00%, the consolidation method and the group-membership flag are **configuration to be introduced**, not existing fields to reuse. Where they live — on the company record, on a group-structure record beside it, or on a consolidation-scope record — is for the implementing agent to settle, together with the validation that refuses 0.00% and an empty value for a declared consolidated subsidiary |
| Delegated attributes propagated from the parent | `odoo/addons/base/models/res_company.py` — the `parent_id` onchange handler (L184–L189) copies the values named by `_get_company_root_delegated_field_names()` from the parent onto the child | Which attributes are delegated from Global Holdings Inc. to Global Europe SARL and Global Asia Pte Ltd on parenting, whether the functional currency is among them, and how a subsidiary keeps EUR or SGD as its own functional currency while the group presentation currency stays USD on the parent |
| Currency precision and rate structure | `odoo/addons/base/models/res_currency.py` — `rounding` is a `Float` labelled "Rounding Factor" with `digits=(12, 6)` and a default of `0.01` (L37) and `decimal_places` is computed and stored from it (L39); `res.currency.rate` is declared at L343 with a required, indexed `name` date field, a `rate` labelled "Technical Rate", and `company_rate` (L357) and `inverse_company_rate` (L364) beside it | Which direction a stored rate expresses, since every translated amount in this story depends on it; how the closing rate at 2025-03-31, the average rate for 2025-01-01 to 2025-03-31 and the historical rate at an incorporation date are each derived from dated rate records; and at which step the result is rounded to 2 decimal places at the USD rounding increment of 0.01 read from the currency record rather than hard-wired |
| Multi-company access scoping | `addons/account/security/account_security.xml` — `account_move_comp_rule` (L128) and `account_move_line_comp_rule` (L134) filter on `[('company_id', 'in', company_ids)]` while `journal_comp_rule` (L146) uses `parent_of`; `odoo/addons/base/models/res_users.py` — `company_id` is required (L245) and `company_ids` is a `Many2many` through `res_company_users_rel` (L247); `allowed_company_ids` is referenced twelve times across the `base` and `account` models | How Scenario 7 holds: what confines the Consolidation Accountant to Global Europe SARL, why a `parent_of` domain behaves differently from an `in` domain once a hierarchy exists, and how a group-level read across all three companies is authorized and logged so the External Auditor sees which entities were accessed and by whom |
| Entity chart against the group taxonomy | `addons/account/models/account_account.py` — `company_ids` is a required `Many2many` to `res.company` (L97) and `code_store` is marked `company_dependent=True` (L40), with the account code computed over it | Whether one account record can serve Global Holdings Inc., Global Europe SARL and Global Asia Pte Ltd while carrying a per-company code, which would make account sharing itself part of the mapping mechanism, and what that implies for the five group codes this feature adds to FEATURE-001-01's baseline |
| Lock dates against a configuration change | `addons/account/models/company.py` — `fiscalyear_lock_date` (L77), `tax_lock_date` (L82) and `hard_lock_date` (L98), with `user_fiscalyear_lock_date` (L109) and `user_tax_lock_date` (L110) computed beside them; `addons/account/models/account_lock_exception.py` declares `account.lock_exception` (L12) | Which lock refuses the functional-currency change of Scenario 6 and with which message, whether a change of group structure is governed by the same lock as a posting, and how the recorded exception path applies where the group has to reopen a locked period |
| Per-entity tax treatment | `addons/account/models/partner.py` — `account.fiscal.position` is declared at L26–L27, and the per-entity positions themselves are configured by FEATURE-001-05 | Whether a fiscal position is resolved per company once the hierarchy exists, so that the entity raising a cross-entity document applies its own position; this story reads that configuration and does not define it |
| Localization interaction | 209 `addons/l10n_*` localization packs are present | Which pack serves each country of incorporation — a United States pack for Global Holdings Inc., a euro-area pack for Global Europe SARL and a Singapore pack for Global Asia Pte Ltd — and what happens where two packs issue the same numeric code for accounts of different type, which would otherwise merge unrelated balances into one group line |

### Relevant Existing Modules

- `odoo/addons/base/` (version 1.3, LGPL-3) — supplies the company hierarchy, `res.currency` with its rounding factor and computed decimal places, `res.currency.rate`, the company assignment held against each finance role, and the record-rule machinery this story configures against.
- `addons/account/` (version 1.4, LGPL-3, the "Invoicing" application, category `Accounting/Accounting`) — supplies `account.account`, `account.journal`, the multi-company record rules and the per-company lock dates that Scenarios 6 and 7 assert against.
- `addons/l10n_*` (209 packs) — statutory chart and tax content per country of incorporation for each entity of the group.
- `addons/account_consolidation` — **absent from this repository.** Its absence is the substance of the open DEC-002 edition decision, and the reason this story is written against the company, currency and rate models that are present.

### OCA Module Compatibility

| OCA Repository | Module | Compatibility Consideration |
|----------------|--------|-----------------------------|
| OCA/account-consolidation | consolidation models | Whether its group-structure model already carries an ownership percentage and a consolidation method per entity, which would make this story a configuration exercise rather than a build under the OCA path |
| OCA/multi-company | `account_invoice_inter_company`, `purchase_sale_inter_company` | Whether the intercompany counterparty mapping these modules expect is satisfied by the hierarchy configured here, so [STORY-001-06-02](./STORY-001-06-02-post-intercompany-transactions.md) inherits it rather than restating it |
| OCA/currency | rate-provider modules | Whether a rate provider supplies the closing and average rate classes with the validation C-015 through C-022 require, and whether its stored rate direction matches the one this story's translations assume |
| Branch alignment for every candidate | — | Whether each candidate publishes a branch matching the platform target DEC-001 confirms; a module published only for an earlier series carries a migration assessment, and that assessment belongs in the estimate of the story depending on it |

### Discovery versus Prescription

**Fixed by this story and not open to redesign:** the three named entities with their entity codes, functional currencies and ownership percentages; USD as the group presentation currency; full consolidation as the method for both subsidiaries; the seven dated rates across the two currency pairs; the translated total of `$922,250.00 USD` from `€850,000.00 EUR` at the 2025-03-31 closing rate of 1.0850 USD/EUR, rounded to 2 decimal places at the USD rounding increment of 0.01; the refusals in Scenarios 4, 5 and 6; the isolation outcome in Scenario 7; and the Definition of Done below, including the 80% coverage gate and demonstrability in the Odoo user interface or through the public API.

**Deferred to agent discovery:** where the ownership percentage, the consolidation method and the group-membership flag are held; whether the group presentation currency is an attribute of the parent company or of a group-structure record; how the closing, average and historical rate classes are derived from dated rate records; how the cross-company read is authorized and logged; and the field-level and view-level design of every model this story touches.

---

## Dependencies

### Story Dependencies

| Dependency Type | Story ID | Story Title | Relationship |
|-----------------|----------|-------------|--------------|
| Parent Feature | [FEATURE-001-06](../FEATURE-001-06-multi-company-consolidation.md) | Multi-Company & Intercompany Consolidation | This story is CAP-001 of that feature and its root story under ORD-003 |
| Blocked By | [STORY-001-01-01](../FEATURE-001-01/STORY-001-01-01-configure-coa-hierarchy.md) | Configure Multi-Level Chart of Accounts Hierarchy | The group chart of accounts must exist before an entity chart can be mapped onto the group and before the five codes this feature adds are approved into it; the prerequisite is master data, satisfiable by a fixture |
| Blocked By | [STORY-001-01-02](../FEATURE-001-01/STORY-001-01-02-map-accounts-ifrs-gaap-taxonomy.md) | Map Accounts to IFRS and GAAP Reporting Taxonomy | The IFRS and US GAAP presentation taxonomy is what a consolidated statement line is drawn from, so the taxonomy exists before an entity chart is mapped into the group |
| Blocks | [STORY-001-06-02](./STORY-001-06-02-post-intercompany-transactions.md) | Post Intercompany Transactions | An intercompany entry needs both companies, their functional currencies and the counterparty mapping between them before it can be raised in each company's books |
| Blocks | [STORY-001-06-03](./STORY-001-06-03-define-consolidation-rules.md) | Define Consolidation Rules | A rule maps an entity account onto the group taxonomy and names the rate class that translates it, so the entities, their functional currencies and the group presentation currency exist first |
| Related | [FEATURE-001-01](../FEATURE-001-01-chart-of-accounts-fiscal-year.md) | Chart of Accounts & Fiscal Year | Owns the group chart, the fiscal calendar and the period lock dates; the journal-entry lock date of Scenario 6 and the closing controls of STORY-001-01-05 are administered there and consumed here |
| Related | [FEATURE-001-05](../FEATURE-001-05-tax-configuration-compliance.md) | Tax Configuration & Compliance | Owns the per-entity fiscal positions and tax codes that determine the tax treatment of a cross-entity document; this story configures the entities those positions are attached to and defines no tax treatment itself |

### External Dependencies

| Dependency | Type | Notes |
|------------|------|-------|
| **IFRS 10 — Consolidated Financial Statements** | Accounting standard | Control determines consolidation scope: both subsidiaries are wholly owned at 100.00% and consolidated in full, so no non-controlling interest arises for the hierarchy this story records |
| **IAS 21 — The Effects of Changes in Foreign Exchange Rates** | Accounting standard | Governs the functional currency of each entity and the rate classes that translate a foreign operation into the group presentation currency USD, with the residual carried to Currency Translation Adjustment 3200 |
| **IFRS 12 — Disclosure of Interests in Other Entities** | Accounting standard | Sets the disclosure of the group's composition, which is why parent, ownership percentage, functional currency and country of incorporation are recorded as reportable configuration |
| **US GAAP ASC 810 — Consolidation** | Accounting standard | The United States framework for consolidation scope read by the stakeholders of Global Holdings Inc., whose functional currency is USD |
| **US GAAP ASC 830 — Foreign Currency Matters** | Accounting standard | The United States framework for translation and for the cumulative translation adjustment, aligning with the treatment of Currency Translation Adjustment 3200 |
| Exchange-rate feed | External service, untrusted boundary | Supplies the closing, average and historical rates recorded here. Validated under C-015 through C-022 before any rate record is written; a rejected response leaves the last confirmed rate in force |
| Statutory registry evidence per entity | External source | Incorporation dates of 2019-01-01 for Global Europe SARL and 2021-01-01 for Global Asia Pte Ltd, and the ownership percentage of 100.00% per subsidiary, are evidenced from the group's statutory records for the External Auditor |
| Platform version and edition confirmation | Programme decision | DEC-001 (platform version target) and DEC-002 (edition source for consolidation capability) are confirmed by stakeholders before this feature enters development |

### Integration Points

| Odoo Model/Module | Integration Type | Purpose |
|-------------------|------------------|---------|
| `res.company` | Read / Write / Extend | Holds the parent link between Global Holdings Inc., Global Europe SARL and Global Asia Pte Ltd, each entity's functional currency and the group presentation currency; extended with the ownership percentage, the consolidation method and the group-membership flag, none of which exists on the model today |
| `res.currency` | Read | Supplies USD, EUR and SGD with the rounding increment and decimal places every translated amount is rounded at, read from the currency record rather than assumed |
| `res.currency.rate` | Read / Write | Holds the seven dated rates this story configures: 1.0850 and 1.0720 and 1.1000 USD/EUR, and 0.7450 and 0.7380 and 0.7300 USD/SGD, each addressable by rate type and rate date |
| `res.users` | Read | Carries the company assignment that scopes each finance role, so a Consolidation Accountant holding Global Europe SARL alone and a Group Controller holding all three entities resolve to different readable sets |
| `ir.rule` | Read | The multi-company record rules that enforce the isolation asserted in Scenario 7; they are respected rather than bypassed, and a cross-company group read is an explicit, logged elevation |
| `account.account` | Read | Each entity's chart, which the consolidation rule set of STORY-001-06-03 maps onto the group taxonomy; this story confirms the chart is present per company and defines no account |
| `account.journal` | Read | The per-company journal set that entity postings and later elimination entries are routed through; this story confirms its presence per company before the first cross-entity posting |
| `account.fiscal.position` | Read | The per-entity tax treatment configured by FEATURE-001-05, attached to the entities this story defines; read as context, never redefined here |

---


## Estimation

| Dimension | Rating | Justification |
|-----------|--------|---------------|
| **Effort** | Medium | A countable deliverable: 3 companies, 2 parent links, 3 functional currencies, 1 group presentation currency, 2 ownership percentages with their consolidation method, and 7 dated rate records across two currency pairs — plus three refusal guards (missing required attribute, circular hierarchy, locked-period currency change) and one isolation behaviour to verify across three entities |
| **Complexity** | Medium | The hierarchy, currency and rate models are present and their field surfaces were read in this repository, so no mechanism has to be invented for them. Complexity concentrates in three places: the ownership percentage, consolidation method and group-membership flag have **no existing home** on the company model; the rate classes have to be derived from dated rate records with the stored rate direction confirmed first; and the record-rule interaction has to hold for a role scoped to one entity while a group read spans all three |
| **Uncertainty** | Medium-Low | The uncertainty is named rather than open: where the new ownership attributes live is a bounded design question, and the direction a stored rate expresses is answered by reading the currency-rate model. Two programme decisions sit above the story — DEC-001 for the platform version and DEC-002 for the edition source — but neither changes the outcome, because every model this story configures is present under all three candidate versions and under every candidate edition path |
| **Story Points** | **5** | Fibonacci scale (1, 2, 3, 5, 8, 13) |

**Why 5 and not 3.** The configuration surface is small and well understood, which alone would place the story at 3. Two factors move it to 5: the ownership percentage, the consolidation method and the group-membership flag are new configuration with no field to reuse, so a design decision precedes the build; and the verification breadth is wider than the build, because the record-rule interaction across three entities, the circular-hierarchy guard and the locked-period refusal each need a test of their own on top of the seven acceptance tests.

**Why 5 and not 8.** Nothing in the story waits on an unanswered question outside it, no data migration is involved, no report is produced, and no journal entry is posted by it. The intercompany postings, the consolidation rule set, the eliminations and the consolidated statements — the parts that carry the feature's real arithmetic — are each a separate sibling story.

---

## Test Requirements

### Coverage Requirement

| Metric | Requirement | Notes |
|--------|-------------|-------|
| **Minimum Test Coverage** | **80%** | Mandatory for all new functionality (C-007) |
| Unit Test Coverage | 80%+ | Hierarchy guards, required-attribute validation, ownership-percentage bounds, rate retrieval and rounding |
| Integration Test Coverage | 80%+ | Cross-company record-rule scoping, lock-date interaction, translation of an entity Trial Balance into the group presentation currency |
| Traceability | 1 acceptance test per criterion | Each of the seven scenarios maps to exactly one named acceptance test (C-008) |
| Numeric assertions | Amounts, counts and percentages asserted, not inspected | The translated total of `$922,250.00 USD` taken at the 2025-03-31 closing rate of 1.0850 USD/EUR, the ownership percentage of 100.00%, the company counts of 1 and 3, and the Trial Balance difference of `€0.00 EUR` are written as assertions, each amount rounded to 2 decimal places at the rounding increment of 0.01 for its currency (C-009) |

### Unit Test Scenarios

| Acceptance Scenario | Unit Test Focus | Key Assertions |
|---------------------|-----------------|----------------|
| Scenario 1 | Parent assignment and functional-currency assignment for Global Europe SARL | The root company of Global Europe SARL is Global Holdings Inc.; its functional currency is EUR; its ownership percentage is 100.00%; the count of entities missing a required group attribute is 0 |
| Scenario 2 | Second subsidiary in a third currency, with ownership and method | The root company of Global Asia Pte Ltd is Global Holdings Inc.; its functional currency is SGD; its ownership percentage is 100.00%; the non-controlling interest arising is 0.00%; the count of companies under the root is 3 and the count of consolidated subsidiaries is 2 |
| Scenario 3 | Rate storage, retrieval by rate type and rate date, and rounding | `€850,000.00 EUR` at the 2025-03-31 closing rate of 1.0850 USD/EUR gives `$922,250.00 USD` rounded to 2 decimal places at the USD rounding increment of 0.01; the closing, average and historical rates are each retrievable by rate date; decimal places are read from the currency record; the count of missing required rates is 0 |
| Scenario 4 | Required-attribute validation on a candidate subsidiary | The save raises a validation error naming the functional currency and the ownership percentage; the company count stays at 3; the consolidated-subsidiary count stays at 2; no rate record is written |
| Scenario 5 | Circular-hierarchy guard | The save raises a validation error naming Global Holdings Inc. and Global Europe SARL; Global Holdings Inc. holds no parent link; the count of companies under the root stays at 3 |
| Scenario 6 | Functional-currency change against the journal-entry lock date | The change raises a validation error naming Global Europe SARL and the lock date 2025-03-31; the functional currency stays EUR; the Trial Balance total assets stay `€850,000.00 EUR`; the translated total stays `$922,250.00 USD` at the 2025-03-31 closing rate of 1.0850 USD/EUR, each amount rounded to 2 decimal places at the rounding increment of 0.01 for its currency |
| Scenario 7 | Record-rule scoping per allowed companies | The readable company count is 1 for the Consolidation Accountant and 3 for the Group Controller; no journal item of Global Asia Pte Ltd or Global Holdings Inc. is returned to the Consolidation Accountant; the cross-company read is logged with its persona and companies |

### Integration Test Considerations

- [ ] Test the hierarchy against `res.company` for all three entities, asserting the computed root company and the parent path of Global Europe SARL and Global Asia Pte Ltd.
- [ ] Test rate retrieval against `res.currency.rate` for each of the seven dated rates, asserting the stored rate direction before asserting any translated amount.
- [ ] Test translation of Global Europe SARL's Trial Balance for 2025-01-01 to 2025-03-31 into the group presentation currency USD, asserting `$922,250.00 USD` from `€850,000.00 EUR` at the 2025-03-31 closing rate of 1.0850 USD/EUR, rounded to 2 decimal places at the USD rounding increment of 0.01.
- [ ] Test record-rule scoping end to end through `res.users` and `ir.rule` with two personas and three companies, and assert the audit record the cross-company read leaves behind.
- [ ] Test the lock-date interaction against the per-company lock dates in `account`, including the recorded exception path for a period that has to be reopened.
- [ ] Test that `account.account` and `account.journal` records resolve per company for all three entities before a cross-entity posting is attempted.
- [ ] **Hostile-input tests on the exchange-rate feed path (C-022)** — one per case: a malformed response, a schema-invalid response, a payload carrying an external-entity reference, an oversized response, a disallowed content type and an out-of-range rate value. Each asserts a named rejection error, that no `res.currency.rate` record is written, that no journal entry is created, that the last confirmed rate stays in force, and that the service stays available.

### Acceptance Test Mapping

| BDD Scenario | Test Method Name | Test Type |
|--------------|------------------|-----------|
| Scenario 1: Euro-area subsidiary linked to the group parent | `test_link_euro_subsidiary_to_group_parent` | Acceptance |
| Scenario 2: Singapore subsidiary added in a third currency | `test_add_singapore_subsidiary_with_ownership_and_method` | Acceptance |
| Scenario 3: Closing rate recorded and Trial Balance translated | `test_record_closing_rate_and_translate_trial_balance` | Acceptance |
| Scenario 4: Subsidiary with no functional currency and no ownership refused | `test_reject_subsidiary_missing_currency_and_ownership` | Acceptance |
| Scenario 5: Circular hierarchy blocked | `test_block_circular_company_hierarchy` | Acceptance |
| Scenario 6: Functional-currency change refused in a locked period | `test_reject_functional_currency_change_after_lock_date` | Acceptance |
| Scenario 7: Company isolation across the three entities | `test_company_isolation_across_group_entities` | Acceptance |
| Edge case 1: zero or absent required attribute | `test_reject_zero_ownership_percentage` | Unit |
| Edge case 3: currency whose rounding increment is not 0.01 | `test_translate_entity_currency_with_non_cent_rounding` | Unit |
| Edge case 4: entity acquired part-way through the fiscal year | `test_consolidate_entity_from_acquisition_date` | Integration |
| C-022 hostile-input cases on the rate feed | `test_reject_hostile_exchange_rate_feed_response` | Integration |

---

## Demonstration Path

The story is accepted when the **Group Controller** walks the **Finance Controller** and the **Product Owner** through the path below in the Odoo user interface, with the Chief Accountant present to confirm the chart and journal set of each entity and the Treasury Analyst present to confirm the rate source. The walkthrough is recorded against this story.

1. **Settings ▸ Users & Companies ▸ Companies** — the three companies shown in one hierarchy: Global Holdings Inc. (`US-01`) as the root company with Global Europe SARL (`NL-01`) and Global Asia Pte Ltd (`SG-01`) beneath it, each opened to show its functional currency (USD, EUR and SGD), its ownership percentage of 100.00% for each subsidiary, its consolidation method of full consolidation, and USD held against Global Holdings Inc. as the group presentation currency.
2. **The live parenting step** — Global Asia Pte Ltd saved with its group-structure attributes in one operation, showing the hierarchy resolve so that Global Holdings Inc. becomes the root company of both subsidiaries and the count of consolidated subsidiaries reads 2.
3. **Accounting ▸ Configuration ▸ Currencies**, opening EUR and SGD to show the rounding increment of 0.01 and the resulting 2 decimal places, then the rate list of each currency showing the closing rate of 1.0850 USD/EUR at 2025-03-31, the average rate of 1.0720 USD/EUR for 2025-01-01 to 2025-03-31, the historical rate of 1.1000 USD/EUR at 2019-01-01, and the SGD rates of 0.7450, 0.7380 and 0.7300 at their own rate dates.
4. **The Trial Balance of Global Europe SARL for 2025-01-01 to 2025-03-31** — total assets of `€850,000.00 EUR` with total debits equal to total credits at a difference of `€0.00 EUR`, followed by the same total presented in the group presentation currency at `$922,250.00 USD`, translated at the 2025-03-31 closing rate of 1.0850 USD/EUR and rounded to 2 decimal places at the USD rounding increment of 0.01.
5. **The negative walkthrough** — a candidate subsidiary saved with no functional currency and no ownership percentage and refused; the parent company of Global Holdings Inc. set to Global Europe SARL and refused as circular; and a functional-currency change on Global Europe SARL refused against its journal-entry lock date of 2025-03-31 — with the company count shown unchanged at 3 after all three attempts.
6. **The isolation walkthrough** — the same journal-item read performed twice, once as a Consolidation Accountant holding Global Europe SARL alone, returning that company's items only, and once as the Group Controller holding all three companies, returning all three entities' items, with the readable company counts of 1 and 3 shown.

**API alternative.** Where a reviewer prefers the public API, the same six steps are demonstrated over JSON-RPC or XML-RPC against the `/jsonrpc` and `/xmlrpc/2/object` endpoints: reading and writing the company hierarchy and its group attributes on `res.company`, reading `res.currency` for the rounding increment and decimal places, writing and reading the dated rates on `res.currency.rate`, reading the translated Trial Balance total for Global Europe SARL, attempting each of the three refused operations and capturing the validation message returned as a fault, and repeating the journal-item read under two sessions whose allowed companies differ so the record-rule scoping is observed from outside the interface.

---

## Definition of Done

### Implementation Checklist

- [ ] All seven acceptance criteria scenarios pass, with the counts, percentages, rates and amounts asserted rather than inspected.
- [ ] 80% minimum test coverage achieved for the delivered functionality (C-007).
- [ ] Unit tests written and passing, including the ownership-percentage bounds, the circular-hierarchy guard and the rate-rounding behaviour.
- [ ] Integration tests written and passing, including the record-rule scoping across the three entities and the lock-date refusal.
- [ ] The hostile-input tests C-022 requires on the exchange-rate feed path are present and passing, each asserting a named rejection with no rate record written and no journal entry created.
- [ ] Global Holdings Inc., Global Europe SARL and Global Asia Pte Ltd are configured as one hierarchy, each subsidiary carrying its functional currency, an ownership percentage of 100.00% and full consolidation as its method, with USD held as the group presentation currency and the count of entities missing a required group attribute asserted at 0.
- [ ] All seven dated rates are recorded and retrievable by rate type and rate date, and the count of currency pairs and rate dates required by the group and missing from the rate table is asserted at 0.

### Accounting Reconciliation Gate

- [ ] **Debits equal credits.** No journal entry is produced by this configuration story; the gate is nonetheless binding on any entry a delivered mechanism does produce, which must post with total debits equal to total credits at a difference of `0.00` in the posting company's functional currency, asserted **separately in each participating company's books** (C-009).
- [ ] **Opening balances tie per entity.** The group's opening balance per entity ties to that entity's own Trial Balance for the same date range at a difference of `0.00` in the entity's functional currency: `€0.00 EUR` for Global Europe SARL and `S$0.00 SGD` for Global Asia Pte Ltd, every amount rounded to 2 decimal places at the rounding increment of 0.01 for its currency.
- [ ] **The translated total is confirmed.** Global Europe SARL's Trial Balance total assets of `€850,000.00 EUR` translate to `$922,250.00 USD` at the 2025-03-31 closing rate of 1.0850 USD/EUR, rounded to 2 decimal places at the USD rounding increment of 0.01, and the figure is signed off against the entity source rather than against a prior group workbook.
- [ ] **Tax amounts match their base.** This story defines no tax treatment; where a tax line exists on an entity's ledger, its tax code, base amount and tax amount stay separated under the fiscal position FEATURE-001-05 configures, and the amounts agree with that configuration in the affected company's books.
- [ ] **Report lines tie to the sub-ledger.** Every translated entity total presented for the group ties to the journal items of the named company behind it, so a group figure for Global Europe SARL or Global Asia Pte Ltd drills down to that entity's own ledger rather than to an aggregate with no owner.

### Compliance Checklist

- [ ] Licence compliance verified: any module delivered here declares an AGPL-3.0 compatible licence, and no derived work misstates the LGPL-3 licence of the `base` and `account` code it extends (C-001, C-002).
- [ ] No module manifest declares a dependency on a module absent from the platform configuration DEC-002 confirms; the open edition decision is recorded rather than pre-empted.
- [ ] The platform version target DEC-001 confirms is recorded against the delivery, and the field surfaces cited in § Technical Discovery Notes are re-verified against it.
- [ ] Code follows Odoo and OCA standards and static analysis reports zero violations under the repository's configured tooling (C-005, C-006).
- [ ] Company isolation is respected: no record rule is suspended, and the cross-company read a group run performs is explicit and logged (C-014, D-007).
- [ ] Code reviewed and approved, with the group-structure attribute design reviewed by the Group Controller.

### Documentation Checklist

- [ ] Public methods and models carry docstrings.
- [ ] The group consolidation policy is recorded alongside the configuration that enforces it: consolidation scope, method, ownership percentage per entity, the group presentation currency, and which rate class applies to which class of line.
- [ ] The IFRS 12 composition disclosure — parent, ownership percentage, functional currency and country of incorporation per entity — is readable from the configuration by the External Auditor without a data request.
- [ ] The change history of the hierarchy, of an ownership percentage and of a translation rate is retained with its author and timestamp.

### Quality Checklist

- [ ] No critical or high-severity defects open against the delivered configuration.
- [ ] Hierarchy resolution, rate retrieval and the cross-company read meet the feature's stated performance targets on a group of 3 companies holding 250,000 journal lines for the reporting date range.
- [ ] Access rights are defined per finance role and verified by the access-rights test matrix: the Group Controller maintains the hierarchy and the rate policy, the Chief Accountant administers each entity's lock date, the Consolidation Accountant reads the entities allowed to it, and the External Auditor holds read-only access to the group composition and its change history.
- [ ] The seven scenarios are demonstrated to the Finance Controller and the Product Owner in the Odoo user interface or through the public API, and the walkthrough is recorded against this story.

---

## References

### Accounting Standards

| Standard | Relevance |
|----------|-----------|
| **IFRS 10 — Consolidated Financial Statements** | Control as the basis of consolidation scope; both subsidiaries wholly owned at 100.00% and consolidated in full, so no non-controlling interest arises |
| **IAS 21 — The Effects of Changes in Foreign Exchange Rates** | Functional currency per entity, translation of a foreign operation into the group presentation currency, and presentation of the translation difference in Currency Translation Adjustment 3200 |
| **IFRS 12 — Disclosure of Interests in Other Entities** | Disclosure of the composition of the group, drawn from the configuration this story records |
| **US GAAP ASC 810 — Consolidation** | United States framework for consolidation scope and intercompany elimination, read by the stakeholders of Global Holdings Inc. |
| **US GAAP ASC 830 — Foreign Currency Matters** | United States framework for translation and the cumulative translation adjustment |

### OCA Modules (Reference)

| Repository | Module | Relevance |
|------------|--------|-----------|
| OCA/account-consolidation | consolidation models | Candidate source of the group-structure and consolidation-scope model under the OCA path of DEC-002 |
| OCA/multi-company | `account_invoice_inter_company`, `purchase_sale_inter_company` | Consume the intercompany counterparty mapping that rests on the hierarchy configured here |
| OCA/currency | rate-provider modules | Candidate source of the closing and average rate classes, subject to the ingestion validation C-015 through C-022 |
| OCA/mis-builder | `mis_builder` | Candidate group column set over the three entities, reading the translation policy this story configures |

### Source Code References

| Path | What It Supplies |
|------|------------------|
| `odoo/addons/base/models/res_company.py` | `parent_id` (L36), `child_ids` (L37), `all_child_ids` (L38), `parent_path` (L39), computed `parent_ids` (L40) and `root_id` (L41), required `currency_id` (L52), and the `parent_id` onchange that copies delegated parent values (L184–L189). No ownership-percentage, consolidation-method or group-membership field exists on this model |
| `odoo/addons/base/models/res_currency.py` | `rounding` with a default of `0.01` (L37) and computed, stored `decimal_places` (L39); `res.currency.rate` declared at L343 with its required date field, `company_rate` (L357) and `inverse_company_rate` (L364) |
| `odoo/addons/base/models/res_users.py` | `company_id` required (L245) and `company_ids` through `res_company_users_rel` (L247), the assignment that scopes each persona in Scenario 7 |
| `addons/account/security/account_security.xml` | `account_move_comp_rule` (L128), `account_move_line_comp_rule` (L134) and `journal_comp_rule` (L146), the multi-company record rules behind Scenario 7 |
| `addons/account/models/account_account.py` | `code_store` marked `company_dependent=True` (L40) and required `company_ids` (L97), which determine how one account record serves more than one company |
| `addons/account/models/company.py` | `fiscalyear_lock_date` (L77), `tax_lock_date` (L82) and `hard_lock_date` (L98) with their computed counterparts (L109–L110), the locks behind Scenario 6 |
| `addons/account/models/account_lock_exception.py` | `account.lock_exception` (L12), the recorded exception path for a locked period |
| `addons/account/models/partner.py` | `account.fiscal.position` (L26–L27), the per-entity tax treatment configured by FEATURE-001-05 |
| `addons/account/__manifest__.py` | The "Invoicing" application (L4), version `1.4` (L5), category `Accounting/Accounting` (L15), licence `LGPL-3` (L140) |
| `odoo/release.py` | `version_info = (19, 0, 0, FINAL, 0, '')` (L15) and `MIN_PY_VERSION = (3, 10)` (L39), the repository baseline behind the DEC-001 mismatch |
| `addons/l10n_*` | 209 localization packs, one per jurisdiction, relevant because the three entities are incorporated in three countries |

### Ticket References

| Ticket | Relationship |
|--------|--------------|
| [EPIC-001: Enterprise Accounting in Odoo](../../EPIC-001-enterprise-accounting-odoo.md) | Parent Epic — objective, personas, constraint set, success metrics and the open decisions DEC-001 and DEC-002 |
| [FEATURE-001-06: Multi-Company & Intercompany Consolidation](../FEATURE-001-06-multi-company-consolidation.md) | Parent Feature — CAP-001, the group canon, the rate set and the feature Definition of Done |
| [STORY-001-06-02: Post Intercompany Transactions](./STORY-001-06-02-post-intercompany-transactions.md) | Successor — consumes the hierarchy, the functional currencies and the counterparty mapping configured here |
| [STORY-001-06-03: Define Consolidation Rules](./STORY-001-06-03-define-consolidation-rules.md) | Successor — consumes the entities, their functional currencies, the group presentation currency and the rate classes configured here |
| [STORY-001-01-01: Configure Multi-Level Chart of Accounts Hierarchy](../FEATURE-001-01/STORY-001-01-01-configure-coa-hierarchy.md) | Predecessor — the group chart of accounts each entity chart is mapped onto |
| [STORY-001-01-02: Map Accounts to IFRS and GAAP Reporting Taxonomy](../FEATURE-001-01/STORY-001-01-02-map-accounts-ifrs-gaap-taxonomy.md) | Predecessor — the presentation taxonomy a consolidated statement line is drawn from |
| [FEATURE-001-01: Chart of Accounts & Fiscal Year](../FEATURE-001-01-chart-of-accounts-fiscal-year.md) | Owner of the group chart, the fiscal calendar and the period lock dates, including the closing controls of STORY-001-01-05 that Scenario 6 asserts against |
| [FEATURE-001-05: Tax Configuration & Compliance](../FEATURE-001-05-tax-configuration-compliance.md) | Owner of the per-entity fiscal positions attached to the entities configured here |

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-08-13 | Enterprise Accounting Team | Initial story creation: three-entity group hierarchy with functional currencies, ownership percentages and consolidation method, the group presentation currency USD, the seven dated translation rates, seven acceptance criteria, five edge cases and the accounting reconciliation gate |

---

## Notes

### Business Context

Group reporting in this organization is a spreadsheet exercise because the group itself is not held anywhere. No parent-subsidiary relationship, no ownership percentage and no group presentation currency exist against Global Holdings Inc., Global Europe SARL or Global Asia Pte Ltd, so a consolidation run has nothing to read and an entity added mid-year reaches the group statements only when someone extends a formula range. This story is the smallest change that turns the group's composition into governed configuration, and it is the reason the four sibling stories can assert amounts at all: an intercompany entry needs two configured sets of books, a consolidation rule needs an entity chart and a rate class, an elimination needs a matched pair, and a consolidated statement needs a presentation currency.

### Why the Ownership Percentage Is Recorded Even at 100.00%

Both subsidiaries are wholly owned, so the ownership percentage changes no arithmetic today. It is recorded for three reasons. It is the IFRS 12 disclosure of the group's composition, which is reportable rather than incidental. It is the attribute a future acquisition of a partly owned entity would be measured against, so the group structure does not have to be re-modelled when one arrives. And it makes the consolidation scope explicit: an entity with no ownership percentage is an entity nobody has decided about, which is exactly the state Scenario 4 refuses.

### Deterministic Artifact Set Used by This Story

| Artifact | Value |
|----------|-------|
| Entities | Global Holdings Inc. (`US-01`, United States, USD, group presentation currency USD); Global Europe SARL (`NL-01`, euro area, EUR, 100.00%, incorporated 2019-01-01); Global Asia Pte Ltd (`SG-01`, Singapore, SGD, 100.00%, incorporated 2021-01-01) |
| Consolidation method | Full consolidation of both wholly owned subsidiaries; no goodwill arises and no non-controlling interest is measured |
| Currencies and rounding | USD, EUR and SGD, each carrying a rounding increment of 0.01 and therefore 2 decimal places |
| EUR rates | Closing 1.0850 USD/EUR at 2025-03-31; average 1.0720 USD/EUR for 2025-01-01 to 2025-03-31; historical 1.1000 USD/EUR at 2019-01-01 |
| SGD rates | Closing 0.7450 USD/SGD at 2025-03-31; average 0.7380 USD/SGD for 2025-01-01 to 2025-03-31; historical 0.7300 USD/SGD at 2021-01-01 |
| Worked translation | Total assets of `€850,000.00 EUR` for Global Europe SARL translate to `$922,250.00 USD` at the 2025-03-31 closing rate of 1.0850 USD/EUR, rounded to 2 decimal places at the USD rounding increment of 0.01 |
| Group codes added by this feature | Intercompany Receivable 1300, Intercompany Payable 2100, Investment in Subsidiary 1700, Currency Translation Adjustment 3200, Foreign Exchange Gain/Loss 7200 |
| Group codes consumed unchanged | Share Capital 3000, Retained Earnings 3100, Revenue 4000, Expense 6100, all defined by FEATURE-001-01 |
| Reporting date range | 2025-01-01 to 2025-03-31, with the as-of date 2025-03-31 |

### Open Questions for Refinement

- Which attribute expresses that an entity is in the consolidation scope but dormant for a period — the group-membership flag alone, or a dated scope record — and how a dormant entity is presented on the group statements.
- Whether the group presentation currency belongs on the parent company record or on a group-structure record, which decides what happens if the group ever reports in a currency no entity uses as its functional currency.
- Whether an intermediate holding company is expected between Global Holdings Inc. and either subsidiary, which would deepen the hierarchy beyond two levels and change what a group read has to traverse.
- Which rate source is authoritative per currency pair, and what the group does when the source publishes a revised rate after a period has been locked and the consolidated pack has been issued.

