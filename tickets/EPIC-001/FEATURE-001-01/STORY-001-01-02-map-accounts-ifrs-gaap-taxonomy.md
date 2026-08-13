# STORY-001-01-02: Map Accounts to IFRS and GAAP Reporting Taxonomy

---

## Metadata

| Attribute | Value |
|-----------|-------|
| **Story ID** | `STORY-001-01-02` |
| **Title** | Map Accounts to IFRS and GAAP Reporting Taxonomy |
| **Parent Feature** | [FEATURE-001-01: Chart of Accounts & Fiscal Year](../FEATURE-001-01-chart-of-accounts-fiscal-year.md) |
| **Parent Epic** | [EPIC-001: Enterprise Accounting in Odoo](../../EPIC-001-enterprise-accounting-odoo.md) |
| **Persona** | Financial Reporting Manager |
| **Status** | Draft |
| **Priority** | 🔴 Critical |
| **Estimate** | 5 story points (Fibonacci) |
| **Feature Capability** | CAP-002 — map every account to the IFRS and US GAAP reporting taxonomy used by the statement generators |
| **Epic Success Metric** | SM-001 — 100% of the seven named statements producible per entity and per period, which requires every account to resolve to a statement line before a statement can be generated |
| **Owner/Author** | Enterprise Accounting Team |

This is the second of the five stories in `FEATURE-001-01/` and the story that turns the raw chart of accounts into **dual-framework reportable data**. [STORY-001-01-01](./STORY-001-01-01-configure-coa-hierarchy.md) fixes ten account codes and their `account_type` values; this story attaches to each of those codes one **IFRS (IAS 1)** presentation line and one **US GAAP (ASC 210 / ASC 220)** presentation line, so that a single posted balance is presented under both frameworks without a restatement step at close. IFRS and US GAAP are delivered together in one story on purpose: a code carries one line per framework, and the two assignments are only verifiable against each other — splitting them would allow a code to be classified under one framework and left unclassified under the other.

---

## User Story

**As a** Financial Reporting Manager

**I want** every `account.account` record in the baseline chart tagged to exactly one IFRS presentation line and exactly one US GAAP presentation line, with the contra treatment of account 1590 Accumulated Depreciation stated per framework and the count of untagged on-balance accounts held at 0 in each in-scope company

**So that** the same ledger produces an IAS 1 statement of financial position for Acme Group NV and an ASC 210 balance sheet for Acme Industries Inc. from one set of posted journal items, with no manual re-mapping step at close, and every statement line traces back to the `account.move.line` records beneath it at a difference of USD 0.00 rounded to 2 decimal places using half-up rounding.

---

## INVEST Principles Compliance

| Principle | Compliance | Notes |
|-----------|------------|-------|
| **Independent** | ✅ | This story's single predecessor, [STORY-001-01-01](./STORY-001-01-01-configure-coa-hierarchy.md), is a dependency of **configuration sequencing, not code coupling**: a presentation line is attached to an account record, so the ten accounts have to exist before they can be tagged. Nothing about how those accounts were created constrains this story. The mapping matrix, the completeness check, the single-line-per-framework rule and the six acceptance tests are therefore designed, built and unit-tested **in parallel** with the predecessor against the ten codes and `account_type` values it fixes, and only the end-to-end demonstration waits on the accounts being present. No sibling story shares an implementation with this one. |
| **Negotiable** | ✅ | The outcome is fixed — each on-balance code resolves to one IAS 1 line and one ASC 210/220 line — and the mechanism is left open. Whether the classification is carried by `account.account.tag` records, by `account.report.line` definitions sourced from an account-code prefix, or by a combination of the two is deferred to the discovery recorded in § Technical Discovery Notes. The line captions themselves are negotiable with the Financial Reporting Manager and the External Auditor for as long as each code still resolves to exactly one line per framework. |
| **Valuable** | ✅ | Without this classification, no statement generator can group a balance: the Epic's manual baseline of 2 to 4 hours of compilation per statement exists precisely because the chart carries no presentation dimension. This story removes that step, is the direct precondition of SM-001 and SM-005, and is what allows one group of legal entities to file under IFRS and under US GAAP from one ledger — the Epic's compliance-reporting objective. It also serves SM-016, because a classification fixed in the ledger and evidenced to the External Auditor removes a recurring source of post-close reclassification entries. |
| **Estimable** | ✅ | The deliverable is countable: ten codes, two frameworks, twenty line assignments, one completeness check, one conflicting-assignment refusal and two companies, all expressed on models whose fields were read during discovery. No open decision sits inside the work — DEC-001 and DEC-002 change the platform it runs on, not the mapping it delivers — so it is sized at 5 Fibonacci points with the rationale recorded in § Estimation. |
| **Small** | ✅ | One configuration outcome: the presentation classification of one chart of accounts, demonstrated in a single walkthrough of the Chart of Accounts and two Balance Sheet runs. The chart itself, the fiscal calendar, the legacy load and the lock dates are each a separate sibling story, and the statements this classification feeds are built in FEATURE-001-07, so this story is not a container for the feature or for the reporting work downstream of it. |
| **Testable** | ✅ | Every criterion below is asserted as an amount, a code, a caption or a refusal: "Trade and other receivables" at USD 48,750.00, "Property and equipment, gross" at USD 500,000.00, an unmapped-account count of 1 naming code 1590, a refused dual assignment, a net figure of USD 425,000.00 tied to the sub-ledger, and a tax amount of USD 21,000.00 split from a base amount of USD 100,000.00. Each of the six scenarios maps to exactly one named automated test in § Test Requirements, so pass or fail is decided without judgement (C-008, C-009). |

---

## Acceptance Criteria

Six criteria are authored, inside the 4-to-8 bound the Epic sets in [§5.3](../../EPIC-001-enterprise-accounting-odoo.md#53-feature-and-story-decomposition-guidelines), and they carry the mandated coverage distribution: **Scenarios 1 and 2 are the valid-input cases** (the IFRS mapping proved on a report, then the US GAAP mapping proved on a second company's report), **Scenario 3 is the invalid and incomplete-input case**, **Scenario 4 is the error-handling case**, and **Scenarios 5 and 6 are accounting edge cases** (contra-asset net presentation with a sub-ledger tie-out, and a tax line whose base and tax amounts are held apart).

All six are asserted against the ten-account baseline that [STORY-001-01-01](./STORY-001-01-01-configure-coa-hierarchy.md) establishes, at the reporting date **31 December 2026** and over the fiscal year **01 January 2026 to 31 December 2026**. The reporting entities are **Acme Group NV** (parent, functional currency `USD`, reports under IFRS) and **Acme Industries Inc.** (subsidiary, functional currency `USD`, reports under US GAAP). Every monetary figure is stated in `USD` at 2 decimal places using half-up rounding.

Three fixture states are used, and naming them here keeps each criterion independently testable rather than leaving two figures for one code looking like a contradiction:

| Fixture | Used by | Ledger state | Mapping state |
|---------|---------|--------------|---------------|
| **F-1 — base** | Scenarios 1, 2 and 4 | Account 1200 Accounts Receivable at a debit balance of USD 48,750.00 in Acme Group NV; accounts 1500 and 1590 at USD 500,000.00 debit and USD 75,000.00 credit in Acme Industries Inc. | All ten codes assigned, one line per framework |
| **F-2 — incomplete mapping** | Scenario 3 | The F-1 ledger, extended so that accounts 1500 and 1590 also hold USD 500,000.00 debit and USD 75,000.00 credit in Acme Group NV | Account 1590 deliberately carries no line, which is why "Property, plant and equipment" reports the gross USD 500,000.00 there and the net USD 425,000.00 in Scenario 5 |
| **F-3 — tax posting** | Scenario 6 | The F-1 ledger plus one further entry of USD 121,000.00 dated 31 December 2026, which is why account 1200 is not asserted at USD 48,750.00 in this scenario | All ten codes assigned, as in F-1 |

Scenario 5 uses F-2's ledger with account 1590 assigned, so Scenarios 3 and 5 are the unmapped and mapped states of the same two codes and together prove that the classification — not the ledger — is what moves the reported figure from USD 500,000.00 to USD 425,000.00. Each fixture is deterministic and reproducible per D-009.

### Scenario 1: Every baseline account resolves to one IAS 1 line on the Balance Sheet

- **Given** the ten baseline accounts exist in Acme Group NV with the `account_type` values fixed by STORY-001-01-01 — 1010 Bank (`asset_cash`), 1200 Accounts Receivable (`asset_receivable`), 1500 Fixed Assets (`asset_fixed`), 1590 Accumulated Depreciation (`asset_fixed`), 2000 Accounts Payable (`liability_payable`), 2200 Tax Payable (`liability_current`), 3000 Share Capital (`equity`), 3100 Retained Earnings (`equity`), 4000 Revenue (`income`) and 6100 Expense (`expense`) — Acme Group NV is designated an IFRS reporting entity, and posted journal items for 01 January 2026 to 31 December 2026 leave account 1200 Accounts Receivable at a debit balance of USD 48,750.00 rounded to 2 decimal places using half-up rounding
- **When** the Financial Reporting Manager assigns the IFRS presentation line of the group mapping matrix to each of those ten accounts
- **Then** the **Balance Sheet** as of **31 December 2026** for **Acme Group NV** presents the line "Trade and other receivables" at **USD 48,750.00**, sourced from account 1200 Accounts Receivable and rounded to 2 decimal places using half-up rounding; each of the ten codes resolves to exactly one named IAS 1 line — 1010 to "Cash and cash equivalents", 1200 to "Trade and other receivables", 1500 and 1590 to "Property, plant and equipment", 2000 to "Trade and other payables", 2200 to "Current tax liabilities", 3000 to "Issued capital", 3100 to "Retained earnings", 4000 to "Revenue" and 6100 to "Operating expenses"; and the count of on-balance accounts presented outside a named IAS 1 line is 0

### Scenario 2: The same codes resolve to ASC 210 lines in the US GAAP entity without disturbing the IFRS entity

- **Given** the same ten codes exist in **Acme Industries Inc.**, which is designated a US GAAP reporting entity, the IFRS assignment of Scenario 1 stands in **Acme Group NV**, and posted journal items for 01 January 2026 to 31 December 2026 leave account 1500 Fixed Assets at a debit balance of USD 500,000.00 and account 1590 Accumulated Depreciation at a credit balance of USD 75,000.00 in Acme Industries Inc., each rounded to 2 decimal places using half-up rounding
- **When** the Financial Reporting Manager assigns the US GAAP presentation line of the group mapping matrix to account 1500 Fixed Assets and to account 1590 Accumulated Depreciation in Acme Industries Inc.
- **Then** the **Balance Sheet** as of **31 December 2026** for **Acme Industries Inc.** reports "Property and equipment, gross" at **USD 500,000.00** and "Less: accumulated depreciation" at **USD 75,000.00** on two separate lines, each rounded to 2 decimal places using half-up rounding; the **Balance Sheet** as of **31 December 2026** for **Acme Group NV** still presents both codes on the single IAS 1 line "Property, plant and equipment" with every other IFRS line holding the value it reported in Scenario 1, including "Trade and other receivables" at USD 48,750.00; and no account in **Acme Industries Inc.** carries an IFRS line and no account in **Acme Group NV** carries a US GAAP line as a result of the assignment

### Scenario 3: An account left without a presentation line blocks publication of the mapping

- **Given** fixture F-2 applies in Acme Group NV — account 1500 Fixed Assets holds a debit balance of USD 500,000.00 and account 1590 Accumulated Depreciation a credit balance of USD 75,000.00 for 01 January 2026 to 31 December 2026, each rounded to 2 decimal places using half-up rounding — and nine of the ten baseline accounts carry an IFRS presentation line while account 1590 carries none
- **When** the Financial Reporting Manager requests the mapping-completeness check for Acme Group NV
- **Then** the check reports an unmapped-account count of **1**, names code **1590 Accumulated Depreciation** together with its balance of **USD 75,000.00** rounded to 2 decimal places using half-up rounding and the framework the assignment is missing under (IFRS), and publication of the Acme Group NV taxonomy mapping is refused while that count stands above 0; the nine assigned accounts keep the lines they already carry, and the **Balance Sheet** as of **31 December 2026** for **Acme Group NV** reports "Property, plant and equipment" at **USD 500,000.00** rather than at the net of the two codes, because the contra account is not yet part of that line

### Scenario 4: A second presentation line under the same framework is refused

- **Given** account 1200 Accounts Receivable in Acme Group NV carries the single IFRS presentation line "Trade and other receivables"
- **When** the Financial Reporting Manager adds the IFRS line "Non-current receivables" to account 1200 alongside the line it already carries
- **Then** the assignment is refused with an Odoo validation message that names account **1200 Accounts Receivable**, both lines "Trade and other receivables" and "Non-current receivables", and the IFRS framework under which they conflict; account 1200 retains "Trade and other receivables" as its only IFRS line and carries no second line; and the **Balance Sheet** as of **31 December 2026** for **Acme Group NV** still reports "Trade and other receivables" at **USD 48,750.00** rounded to 2 decimal places using half-up rounding, with USD 0.00 presented on "Non-current receivables"

### Scenario 5: Contra-asset net presentation ties out to the Trial Balance and the sub-ledger

- **Given** fixture F-2 applies with account 1590 now assigned — account 1500 Fixed Assets carries a debit balance of USD 500,000.00 and account 1590 Accumulated Depreciation carries a credit balance of USD 75,000.00 in Acme Group NV for 01 January 2026 to 31 December 2026, each rounded to 2 decimal places using half-up rounding — and both codes carry the IFRS line "Property, plant and equipment" with 1590 designated the contra element of that line
- **When** the Financial Reporting Manager runs the **Balance Sheet** as of **31 December 2026** for **Acme Group NV** with net presentation enabled
- **Then** the line "Property, plant and equipment" reports **USD 425,000.00** rounded to 2 decimal places using half-up rounding; the **Trial Balance** for **01 January 2026 to 31 December 2026** lists account 1500 at a debit of USD 500,000.00 and account 1590 at a credit of USD 75,000.00 on two separate rows, with **total debits equal to total credits** and a difference of **USD 0.00**; and the net figure of USD 425,000.00 equals the arithmetic sum of the `account.move.line` balances of codes 1500 and 1590 at a difference of USD 0.00, so no amount is created or lost by the net presentation

### Scenario 6: A tax line reports the tax amount only, held apart from its base amount

- **Given** fixture F-3 applies, account 2200 Tax Payable in Acme Group NV carries the IFRS line "Current tax liabilities", and one journal entry dated 31 December 2026 posted in the Sales journal (journal type `sale`) records tax code **`VAT-21-S`** on a **base amount of USD 100,000.00** with a **tax amount of USD 21,000.00** — debiting account 1200 Accounts Receivable by USD 121,000.00, crediting account 4000 Revenue by USD 100,000.00 and crediting account 2200 Tax Payable by USD 21,000.00 — every amount rounded to 2 decimal places using half-up rounding
- **When** the Financial Reporting Manager runs the **Balance Sheet** as of **31 December 2026** for **Acme Group NV**
- **Then** the line "Current tax liabilities" reports **USD 21,000.00** rounded to 2 decimal places using half-up rounding, which reconciles to tax code **`VAT-21-S`** for 01 January 2026 to 31 December 2026 at a difference of USD 0.00, with that code's **base amount of USD 100,000.00** reported separately from its **tax amount of USD 21,000.00** and no part of the base amount presented on the "Current tax liabilities" line; the base amount of USD 100,000.00 is presented on the IFRS line "Revenue" instead; and the journal entry carrying those lines holds **total debits of USD 121,000.00 equal to total credits of USD 121,000.00**, a difference of **USD 0.00**

---

## Sub-Tasks

| # | Sub-Task | Assignee |
|---|----------|----------|
| 1 | Author the account-to-taxonomy mapping matrix — each of the ten baseline codes against one IAS 1 line and one ASC 210/220 line, with the contra treatment of account 1590 Accumulated Depreciation stated per framework — and obtain Finance SME and Chief Accountant sign-off on it as the group presentation policy | `@functional-consultant` |
| 2 | Record the reporting framework of each legal entity — Acme Group NV under IFRS and Acme Industries Inc. under US GAAP — so that a code carries one line per framework rather than one line overall, and confirm with the External Auditor which framework each entity files under | `@functional-consultant` |
| 3 | Reconcile the matrix against the presentation lines and account tags that each in-scope `l10n_*` statutory pack installs, and record every divergence against the group line rather than creating a parallel line set | `@functional-consultant` |
| 4 | Configure the taxonomy classification and the report-line mapping that carries each account onto its IAS 1 line and its ASC 210/220 line, keeping account 1590 presentable as a contra element of "Property, plant and equipment" under IFRS and as its own line "Less: accumulated depreciation" under US GAAP | `@developer` |
| 5 | Deliver the mapping-completeness check: report the count of accounts carrying no line assignment per company and per framework, exclude `off_balance` accounts from that count, name each unmapped code with its balance in USD at 2 decimal places using half-up rounding, and refuse publication while the count stands above 0 | `@developer` |
| 6 | Enforce the single-line-per-framework rule so that a second conflicting line on one account is refused with a message naming the account code, both lines and the framework, leaving the prior assignment intact | `@developer` |
| 7 | Author the six automated acceptance tests named in § Test Requirements, one per scenario, with every monetary figure, tax split and debits-equal-credits assertion written as an amount rather than inspected by eye (C-009) | `@qa-engineer` |
| 8 | Verify each mapped line against IAS 1 and ASC 210/220 presentation, and confirm the tie-out of every mapped Balance Sheet line to the **Trial Balance** for 01 January 2026 to 31 December 2026 with total debits equal to total credits at a difference of USD 0.00 | `@finance-sme` |

---

## Edge Cases

| # | Edge Case | Expected Handling |
|---|-----------|-------------------|
| 1 | A mapped account holds no movement for the reported range — account 2200 Tax Payable at a balance of USD 0.00 in Acme Group NV for 01 January 2026 to 31 December 2026 | The IFRS line "Current tax liabilities" reports **USD 0.00** rounded to 2 decimal places using half-up rounding when the run retains zero-balance lines, and its row is omitted when the run suppresses them; the choice is a presentation option that changes no other line and no total, and the **Balance Sheet** as of 31 December 2026 continues to tie to the **Trial Balance** for the same range with total debits equal to total credits at a difference of USD 0.00 |
| 2 | A legacy account is loaded **after** the taxonomy mapping is published — account 1210 Trade Receivables — Retail imported into Acme Group NV by [STORY-001-01-04](./STORY-001-01-04-import-legacy-coa.md) with no line assignment of its own | Account 1210 inherits the IFRS line "Trade and other receivables" and the US GAAP line "Accounts receivable, net" from the closest parent account in its code range, account 1200 Accounts Receivable; the mapping-completeness check of Scenario 3 is re-run at cutover and reports an unmapped-account count of 0; and the opening balance carried on 1210 is presented on those two lines at its loaded amount in USD rounded to 2 decimal places using half-up rounding rather than falling outside every line. Where the inherited line is not the one finance intends, the assignment is overridden on account 1210 before publication is re-issued |
| 3 | An account typed `off_balance` must appear under neither framework — commitments account 9000 in Acme Group NV | Account 9000 carries no IFRS line and no US GAAP line; the mapping-completeness check excludes `off_balance` accounts from its unmapped count, so the count stays at 0 and publication is not blocked by the deliberate omission; account 9000 contributes **USD 0.00** to every line of both Balance Sheets as of 31 December 2026; and the on-balance **Trial Balance** for 01 January 2026 to 31 December 2026 still reports total debits equal to total credits at a difference of **USD 0.00**, every amount rounded to 2 decimal places using half-up rounding |
| 4 | One code requires a different line per framework and per company — account 1590 Accumulated Depreciation, netted into "Property, plant and equipment" under IFRS in **Acme Group NV** and presented on its own line "Less: accumulated depreciation" under US GAAP in **Acme Industries Inc.** | Both assignments coexist on the same code, each resolving only inside its own framework and its own company: the **Balance Sheet** as of 31 December 2026 for **Acme Group NV** reports "Property, plant and equipment" at **USD 425,000.00**, while the **Balance Sheet** as of 31 December 2026 for **Acme Industries Inc.** reports "Property and equipment, gross" at **USD 500,000.00** and "Less: accumulated depreciation" at **USD 75,000.00**. Neither presentation alters a balance — both trace to the same `account.move.line` records of USD 500,000.00 debit and USD 75,000.00 credit at a difference of USD 0.00, every amount rounded to 2 decimal places using half-up rounding |
| 5 | A taxonomy line carries no mapped account — the IAS 1 line "Investment property" with 0 accounts assigned to it in Acme Group NV | The line reports **USD 0.00** rounded to 2 decimal places using half-up rounding and is retained in the statement structure rather than dropped, so the statement's line set does not change in the first period the group acquires investment property and the comparative column stays alignable; the mapping-completeness check records it as a line with 0 mapped accounts as information and does **not** refuse publication, because the gate in Scenario 3 is on accounts without a line and not on lines without an account |

---

## Demonstration Path

This story is accepted when the Financial Reporting Manager walks the **Finance Controller** and the **Product Owner** through the following path in the Odoo user interface, with the Chief Accountant present as the account owner and the External Auditor invited as the consumer of the presentation evidence. Where a reviewer prefers the public API, the same five steps are demonstrated through it; either way the walkthrough is recorded against this story (R-G).

The walkthrough runs on the **combined verification dataset** — fixtures F-1, F-2 and F-3 applied together — so account 1200 Accounts Receivable carries the F-1 balance of USD 48,750.00 plus the F-3 tax entry of USD 121,000.00, a debit balance of **USD 169,750.00** rounded to 2 decimal places using half-up rounding.

1. **Accounting ▸ Configuration ▸ Chart of Accounts** — filtered to **Acme Group NV**, with the **account tags** column and the **account type** column both displayed, showing each of the ten baseline codes beside its `account_type` value and its IFRS presentation line, and the count of on-balance accounts carrying no line assignment shown at 0.
2. **Accounting ▸ Configuration ▸ Chart of Accounts** — filtered to **Acme Industries Inc.**, showing the same ten codes with their US GAAP presentation lines in the account tags column, and account 1590 Accumulated Depreciation seen carrying "Less: accumulated depreciation" in this company while carrying the contra element of "Property, plant and equipment" in Acme Group NV.
3. **The Balance Sheet as of 31 December 2026 for Acme Group NV, grouped by taxonomy line** — showing "Trade and other receivables" at USD 169,750.00, "Property, plant and equipment" at USD 425,000.00 net, and "Current tax liabilities" at USD 21,000.00, each rounded to 2 decimal places using half-up rounding, with a drill-down from the "Property, plant and equipment" line to the `account.move.line` records of codes 1500 and 1590 that sum to it at a difference of USD 0.00, and a drill-down from "Trade and other receivables" to the two postings on account 1200 that sum to USD 169,750.00.
4. **The Balance Sheet as of 31 December 2026 for Acme Industries Inc., grouped by taxonomy line** — showing "Property and equipment, gross" at USD 500,000.00 and "Less: accumulated depreciation" at USD 75,000.00 on separate lines, demonstrated immediately after step 3 so that the two frameworks are seen reading the same underlying balances.
5. **The negative walkthrough** — the second IFRS line attempted on account 1200 and refused with the message naming both lines, followed by the taxonomy line removed from account 1590 and the mapping-completeness check re-run to show an unmapped-account count of 1 naming code 1590 at USD 75,000.00 and publication refused; the line is then restored and the count shown back at 0.

---

## Constraints

### License and Compliance

- [ ] **C-001 — AGPL-3.0 compatible licence.** Any module delivering the taxonomy classification, the mapping-completeness check or the single-line-per-framework rule is distributed under an AGPL-3.0 compatible licence, matching the six Community-edition accounting add-ons already present in this repository.
- [ ] **C-002 — LGPL-3 of `account` respected.** `account.account`, `account.account.tag` and the `account.report` family are LGPL-3 code declared in `addons/account/__manifest__.py`; derived and dependent work stays licence-compatible with them and no derived work misstates their licence.
- [ ] **C-005 and C-006 — Odoo and OCA coding standards.** Python follows Odoo and OCA module guidelines including PEP 8, and static analysis passes with the repository's configured tooling in `ruff.toml` at zero violations.
- [ ] **C-012 — build on the existing models.** The classification is carried on `account.account` and its tagging and report-line structures rather than on a parallel presentation table, so one ledger, one classification and one audit trail survive the change.
- [ ] **C-014 — multi-company access rights.** The Financial Reporting Manager maintains the mapping, the Chief Accountant owns the accounts it is attached to, and the External Auditor holds read-only access to both. A role restricted to Acme Group NV can neither read nor alter the US GAAP assignments of Acme Industries Inc., and the framework designation of one company is not editable from the other.
- [ ] **C-015 to C-022 — untrusted input.** This story defines no ingestion surface of its own: it classifies accounts that already exist and reads balances that are already posted. Two inherited surfaces still apply and are proved by the tests named in § Test Requirements — the **run-time report parameters** (the as-of date and the date range supplied to the Balance Sheet and Trial Balance) are validated before use under C-019, and any **line caption or mapping worksheet value imported** rather than typed is neutralized against formula injection on export under C-017 and context-encoded before it is rendered into a report under C-018. Where the mapping is loaded from a file instead of entered, the ingestion checks of C-015 and the hostile-input test of C-022 apply in full.

### Version Compatibility

The platform target of this programme is an **open decision (DEC-001)** recorded in the Epic's [Open Decisions Register](../../EPIC-001-enterprise-accounting-odoo.md#appendix-b-open-decisions-register). It is stated here without being resolved, because this story asserts field and caption names that differ between the candidates:

| Candidate target | Evidence on record | Consequence for this story |
|------------------|--------------------|----------------------------|
| **Odoo 17** | Named by the originating programme request | The `account_type` selection and the tagging surface exist in that series but the 209 `l10n_*` packs present here are 19.0-series, so each statutory presentation this mapping reconciles against is re-selected for the 17 series |
| **Odoo 18.0** | Targeted by the prior, superseded backlog | Neither the request nor this repository is served; the model and field names asserted here are restated for 18.0 before development starts |
| **Odoo 19.0** | The baseline present in this repository: `version_info = (19, 0, 0, FINAL, 0, '')` in `odoo/release.py` | The nineteen-value `account_type` selection, the `tag_ids` field on `account.account`, the `applicability` selection on `account.account.tag` and the six computation engines on `account.report.expression` hold exactly as cited in § Technical Discovery Notes |

- [ ] **C-010 — the confirmed version is recorded** in the Epic and restated in the parent Feature before development starts; this story does not choose it.
- [ ] **C-011 — Python and PostgreSQL versions follow the confirmed target**, since each candidate release carries its own supported matrix.
- [ ] **Edition source (DEC-002) is an open decision that this story is exposed to.** The **dynamic report engine that renders a Balance Sheet from presentation lines ships with the Enterprise module `account_reports`, which is absent from this repository**: `addons/account/data/account_reports_data.xml` defines only the three generic tax reports and **zero** `account.report.line` records, so Community supplies the report *structures* (`account.report`, `account.report.line`, `account.report.expression`) without a balance-sheet line set to populate. The decision between an Odoo Enterprise subscription and the OCA path is therefore recorded, not presumed. It is **not a blocker**: the AGPL-3 add-on `account_financial_report_ce` version 19.0.1.1.0 is present, and its `account.balance.sheet.report` and `account.trial.balance.report` models carry the as-of and date-range parameters this story's criteria are asserted through, so the story is demonstrable today under the OCA path. This is why the classification is expressed as data attached to the account rather than against one report engine's internals — the mapping outcome is identical under either edition, and only the renderer changes.

### Accounting Standards Compliance

- [ ] **IAS 1 — Presentation of Financial Statements.** Each IFRS line assigned by this story is one of the captions IAS 1 requires or permits on the statement of financial position, and the current-versus-non-current split it mandates is carried by the `account_type` value together with the assigned line, so a section order is derived from the chart rather than re-entered per report. Account 1590 Accumulated Depreciation is presented as a contra element of "Property, plant and equipment", which is the net presentation IAS 1 expects on the face of the statement while the gross amount and the accumulated depreciation remain separable for the note disclosure.
- [ ] **ASC 210 — Balance Sheet.** Each US GAAP line assigned by this story is a balance-sheet caption under ASC 210, with cost (account 1500) and accumulated depreciation (account 1590) presented on separate lines rather than netted in the ledger, so the gross-and-contra presentation customary under US GAAP is available without a second set of accounts.
- [ ] **ASC 220 — Income Statement, Reporting Comprehensive Income.** Accounts 4000 Revenue and 6100 Expense are classified to income-statement captions ("Revenues" and "Operating expenses") under ASC 220 and to "Revenue" and "Operating expenses" under IAS 1, so the two frameworks' income-statement presentations are produced from the same two codes. Where expenses are analysed by function rather than by nature, the analysis is derived from the assigned line and the account hierarchy rather than from a re-keyed schedule.
- [ ] **Dual-framework consistency.** No posted amount differs between the two presentations: a difference between an IFRS line total and the corresponding US GAAP line total is a classification difference that is explained and evidenced, never a difference in the underlying `account.move.line` records. Every recognition and measurement difference between the frameworks is out of scope for this story and is handled where it is measured, not where it is presented.
- [ ] **Audit traceability.** The `account_type` value and the presentation assignment are tracked, so every change to a classification is retained with its author and timestamp and is readable by the External Auditor without a data request. Each statement line drills to its accounts and from there to the `account.move.line` detail beneath it.
- [ ] **One line per framework per account.** Every on-balance account resolves to exactly one IAS 1 line and exactly one ASC 210/220 line, which is the property that makes both statements reproducible from the ledger and is enforced by the refusal in Scenario 4.

---

## Technical Discovery Notes

> **Purpose:** these notes direct the codebase analysis that precedes implementation. This story states WHAT classification finance needs and WHY; the tagging mechanism, the report-engine technology, the model inheritance approach and the view architecture emerge from discovery and are deliberately **not** prescribed here.

### The Mapping Matrix

This matrix is the presentation policy the story delivers. Each row states the account code, the `account_type` value fixed by [STORY-001-01-01](./STORY-001-01-01-configure-coa-hierarchy.md), the IAS 1 line the code is presented on under IFRS, and the ASC 210/220 line it is presented on under US GAAP. Rows 1200, 1500, 1590 and 2200 are the rows asserted directly in § Acceptance Criteria.

| Code | Account | `account_type` | IFRS (IAS 1) line | US GAAP (ASC 210/220) line |
|---|---|---|---|---|
| 1010 | Bank | `asset_cash` | Cash and cash equivalents | Cash and cash equivalents |
| 1200 | Accounts Receivable | `asset_receivable` | Trade and other receivables | Accounts receivable, net |
| 1500 | Fixed Assets | `asset_fixed` | Property, plant and equipment | Property and equipment, gross |
| 1590 | Accumulated Depreciation | `asset_fixed` | Property, plant and equipment (contra, net presentation) | Less: accumulated depreciation |
| 2000 | Accounts Payable | `liability_payable` | Trade and other payables | Accounts payable |
| 2200 | Tax Payable | `liability_current` | Current tax liabilities | Taxes payable |
| 3000 | Share Capital | `equity` | Issued capital | Common stock |
| 3100 | Retained Earnings | `equity` | Retained earnings | Retained earnings |
| 4000 | Revenue | `income` | Revenue | Revenues |
| 6100 | Expense | `expense` | Operating expenses | Operating expenses |

Two rows carry the presentation nuance that drives the estimate. **Row 1590** is the only code whose treatment differs structurally between the frameworks: netted into a single IAS 1 line under IFRS, and given its own subtractive caption under ASC 210. **Row 2200** is the only code whose reported figure has to be reconciled to a tax code rather than to a single account balance, which is why its criterion separates the base amount from the tax amount.

### Codebase Analysis Areas

| Area | Files/Modules to Examine | Analysis Focus |
|------|--------------------------|----------------|
| Account classification fields | `addons/account/models/account_account.py` | The nineteen-value `account_type` selection at the head of the model — `asset_receivable`, `asset_cash`, `asset_current`, `asset_non_current`, `asset_prepayments`, `asset_fixed`, `liability_payable`, `liability_credit_card`, `liability_current`, `liability_non_current`, `equity`, `equity_unaffected`, `income`, `income_other`, `expense`, `expense_other`, `expense_depreciation`, `expense_direct_cost` and `off_balance` — and which of the ten codes maps to which value. It is `tracking=True` and `required=True`, so a classification change is already retained for the External Auditor. Determine how much presentation the type alone can carry and where a second dimension becomes necessary |
| Carry-forward behaviour by type | `addons/account/models/account_account.py` | The `include_initial_balance` field ("Bring Accounts Balance Forward"), which decides whether a type's balance carries across fiscal years. This is the property that separates the balance-sheet rows of the matrix from the income-statement rows, and discovery confirms it agrees with the line assignment for all ten codes |
| Account tagging surface | `addons/account/models/account_account_tag.py`, and `tag_ids` on `account.account` | `account.account.tag` with `name` (translatable), the `applicability` selection `accounts` / `taxes` / `products` that keeps account tags apart from tax and product tags, `country_id`, `active`, and the uniqueness constraint on name-plus-applicability-plus-country. Three master tags ship with the chart definition and are protected from deletion — the operating, financing and investing tags used for cash-flow classification — so determine whether the IFRS and US GAAP lines are a fourth tag family, a separate structure, or an extension of this one, and how a per-framework and per-company assignment is expressed without overloading one tag |
| Tag inheritance on new accounts | `addons/account/models/account_account.py` | The routine that assigns tags from the closest parent account to accounts that carry a code but no tags. This is the mechanism Edge Case 2 relies on when a legacy account is loaded after publication, so confirm when it runs, whether it runs on import, and whether an inherited assignment can be overridden before publication is re-issued |
| Report line and expression structure | `addons/account/models/account_report.py` | `account.report`, `account.report.line`, `account.report.expression`, `account.report.column` and `account.report.external.value`, and the six computation engines on the expression — `domain` (Odoo Domain), `tax_tags` (Tax Tags), `aggregation` (Aggregate Other Formulas), `account_codes` (Prefix of Account Codes), `external` (External Value) and `custom` (Custom Python Function) — together with `formula`, `subformula` and `date_scope`. Determine which engine sources each matrix row: an account-code prefix, a domain on the classification, or an aggregation for the net contra line, and how the sign of a subtractive caption is carried |
| Balance-sheet line set availability | `addons/account/data/account_reports_data.xml` | This file defines only `generic_tax_report`, `generic_tax_report_account_tax` and `generic_tax_report_tax_account`, and **zero** `account.report.line` records. Confirm that Community ships the report structures without a balance-sheet line set, which is the concrete shape of the DEC-002 gap, and decide where the line set is authored under each edition path |
| Per-company code and framework divergence | `addons/account/models/account_code_mapping.py` | `account.code.mapping` with its `account_id`, `company_id` and `code` fields. Determine how a report that groups on account code behaves when the code differs by company, and whether the presentation assignment follows the account or the per-company code — the question behind Edge Case 4 |
| Statutory presentation already installed | The 209 `addons/l10n_*` packs | Enumerate which of the 209 packs ship country-specific account tags and statutory report lines, then determine, per in-scope country, whether the statutory presentation and the group IFRS/US GAAP presentation coexist as separate line sets over one chart, and record each divergence against the group line rather than duplicating the account (D-006) |
| Rendering already present in this repository | `addons/account_financial_report_ce/models/balance_sheet.py`, `trial_balance.py`, `profit_loss.py` | The AGPL-3 implementations present today: `account.balance.sheet.report` with its `date_from` and `date_to` fields, and `account.trial.balance.report` with the date range this story's tie-out is asserted over. Determine how their grouping is driven, whether a taxonomy-line grouping can be added without a translation layer, and confirm that adopting one does not silently move an existing statement line |
| Multi-company isolation of the mapping | `addons/account/models/account_account.py` (company-consistency constraints), `odoo/addons/base/models/res_company.py` | How a per-company assignment is isolated so that the framework designation and line assignment of Acme Industries Inc. are neither readable nor editable from a role restricted to Acme Group NV (C-014), and where the reporting-framework designation of a company is best recorded |
| Tax reconciliation surface | `addons/account/models/account_tax.py`, `account_move_line.py` | How a tax code's base amount and tax amount are recorded on separate lines, so that the Scenario 6 assertion — "Current tax liabilities" reporting the tax amount only, reconciled to `VAT-21-S` — is read from the tax records rather than inferred from the account balance |

### Relevant Existing Modules

- `addons/account/` — "Invoicing", version 1.4, licence LGPL-3. Supplies every model this story classifies against: `account.account` and its `account_type` and `tag_ids`, `account.account.tag`, `account.group`, `account.code.mapping`, the `account.report` family, and `account.move` and `account.move.line` as the sub-ledger every mapped line ties back to.
- `addons/l10n_*/` — the 209 localization packs present in this repository. Each supplies one jurisdiction's statutory presentation, account tags and report lines, which the group mapping matrix is reconciled against rather than replaced by.
- `addons/account_financial_report_ce/` — version 19.0.1.1.0, AGPL-3. The Balance Sheet, Trial Balance, Profit & Loss, General Ledger, Cash Flow and Aged Partner Balance implementations already present, and the reference point for how a classification reaches a statement line while DEC-002 is open.
- `addons/account_deferred_revenue/`, `addons/account_asset_management/` — the Community-edition add-ons whose accounts consume this classification downstream; examined only to confirm that the accounts they create fall inside the matrix rather than outside it.
- `odoo/addons/base/` — `res.company` for the reporting-framework designation per legal entity, and `res.currency` for the `USD` decimal precision every monetary assertion is rounded to.

### OCA Module Compatibility

| OCA Repository | Module | Compatibility Consideration |
|----------------|--------|-----------------------------|
| OCA/account-financial-reporting | `account_financial_report` | Renders the Balance Sheet, Profit & Loss, General Ledger and Trial Balance from account types and hierarchy. Determine whether a taxonomy-line dimension can drive its grouping directly, or whether a mapping layer is needed, under the OCA path of DEC-002 |
| OCA/mis-builder | `mis_builder` | Builds management and statutory statements from account-code expressions rather than from types, which makes it a candidate for expressing both framework line sets over one chart. Determine how stable the ten-code baseline has to be for those expressions and how a per-company code mapping affects them |
| OCA/account-financial-tools | `account_chart_update` | Compares an installed chart against its country template and applies template changes. Determine whether it preserves an existing presentation assignment when it updates an account, so that a template refresh does not silently drop a mapped line |
| OCA/account-financial-reporting | `account_tax_balance` | Reports balances per tax code, which is the surface the Scenario 6 base-and-tax split is verified against. Determine whether it reconciles to the tax control account 2200 Tax Payable without a translation layer |

The decision to integrate, extend or replace any add-on above belongs to **DEC-002** in the Epic and is not taken in this story.

---

## Dependencies

### Story Dependencies

| Dependency Type | Story / Feature ID | Title | Relationship |
|-----------------|--------------------|-------|--------------|
| Parent Feature | [FEATURE-001-01](../FEATURE-001-01-chart-of-accounts-fiscal-year.md) | Chart of Accounts & Fiscal Year | This story is the second of the feature's five stories and delivers its capability CAP-002 |
| **Blocked By** | [STORY-001-01-01](./STORY-001-01-01-configure-coa-hierarchy.md) | Configure Multi-Level Chart of Accounts Hierarchy | **The ten accounts must exist before they can be tagged** — a presentation line is attached to an `account.account` record, and the `account_type` values this mapping is built on are fixed there. This is configuration sequencing, not code coupling: the matrix, the completeness check and the tests are built in parallel and only the end-to-end demonstration waits |
| Related | [STORY-001-01-04](./STORY-001-01-04-import-legacy-coa.md) | Import Legacy Chart of Accounts and Opening Balances | Accounts loaded by the legacy import inherit the presentation lines published here from the closest parent account in their code range (Edge Case 2), so the completeness check is re-run at cutover and the unmapped count is asserted at 0 before the opening position is reported |
| Related | [STORY-001-01-03](./STORY-001-01-03-define-fiscal-year-periods.md) | Define Fiscal Year and Accounting Periods | The fiscal calendar supplies the reporting boundary every criterion here is asserted at — the as-of date of 31 December 2026 and the range 01 January 2026 to 31 December 2026 — and can be built in parallel with this story |
| Related | [STORY-001-01-05](./STORY-001-01-05-configure-period-lock-dates.md) | Configure Period Lock Dates and Closing Controls | A published mapping is what makes a locked period's statements reproducible; a classification change made after a period is locked is evidenced through the tracked-field history this story relies on |
| Downstream feature | **FEATURE-001-07** — Financial Reporting & Period Close | — | The Balance Sheet, Profit & Loss, Cash Flow Statement, General Ledger and Trial Balance stories consume this classification as the grouping dimension of every statement line. This story delivers the classification; those stories deliver the statements. Referenced by identifier because that feature's files are authored separately in this backlog |
| Downstream feature | **FEATURE-001-06** — Multi-Company & Intercompany Consolidation | — | Consolidation maps like to like only if both entities' accounts resolve to the same line under the group's reporting framework, so the per-framework and per-company assignment delivered here is the precondition of a consolidated statement |
| Downstream feature | **FEATURE-001-05** — Tax Configuration & Compliance | — | The tax control account 2200 Tax Payable is classified here to "Current tax liabilities" and "Taxes payable"; the tax codes whose base and tax amounts Scenario 6 reconciles against, including `VAT-21-S`, are configured there |
| Downstream feature | **FEATURE-001-08** — Fixed Assets & Depreciation | — | The asset register posts to accounts 1500 Fixed Assets and 1590 Accumulated Depreciation, whose gross-and-contra presentation is fixed here, so the register's net book value and the statement's net line are the same figure |

### External Dependencies

| Dependency | Type | Notes |
|------------|------|-------|
| IFRS Foundation presentation taxonomy | Accounting standard / taxonomy | IAS 1 *Presentation of Financial Statements* supplies the statement-of-financial-position captions the IFRS column of the matrix is drawn from; the IFRS Accounting Taxonomy supplies the element names where a filing is made in a structured format |
| US GAAP FASB Accounting Standards Codification | Accounting standard / taxonomy | ASC 210 supplies the balance-sheet captions and ASC 220 the income-statement captions of the US GAAP column; the FASB US GAAP Financial Reporting Taxonomy supplies the element names for structured filing |
| Group presentation policy | Governance artifact | Owned by the Financial Reporting Manager, countersigned by the Chief Accountant and reviewed by the External Auditor; it is the authority the mapping matrix is drawn from and the artifact that is published |
| Reporting-framework designation per legal entity | Master data | Acme Group NV designated an IFRS reporting entity and Acme Industries Inc. a US GAAP reporting entity, recorded before the mapping is applied, since a code carries one line per framework |
| Country localization pack per operating country | Odoo module (`l10n_*`) | 209 packs are present here; each supplies a statutory presentation this mapping is reconciled against, with divergences recorded against the group line (D-006) |
| Tax code configuration | Configuration dependency | Tax code `VAT-21-S` with its base and tax accounts exists before Scenario 6 is verified; it is delivered by FEATURE-001-05 |
| Platform version and edition confirmation | Open decision (DEC-001, DEC-002) | DEC-001 fixes the field and selection names this story is implemented against; DEC-002 fixes which engine renders the Balance Sheet the mapping is verified through, and is the decision the absent `account_reports` module makes unavoidable |

### Integration Points

| Odoo Model | Integration Type | Purpose |
|------------|------------------|---------|
| `account.account` | Read and extend | The ten baseline codes whose `account_type`, `tag_ids` and presentation assignment carry the classification this story delivers |
| `account.account.tag` | Define and write | The tagging surface the presentation lines are expressed through, with `applicability` set to accounts so that the assignment is held apart from tax and product tags |
| `account.group` | Read | The code-prefix hierarchy from STORY-001-01-01, read so that a line assignment agrees with the group a code already resolves to and so that a prefix can source a line where a per-account assignment is unnecessary |
| `account.report` | Read and extend | The report, line, expression and column structures a taxonomy line set is authored into, including the computation engine each matrix row is sourced by |
| `res.company` | Read and write | Acme Group NV and Acme Industries Inc., their parent-and-subsidiary relationship, their functional currency, and the reporting-framework designation that decides which line set applies |
| `account.move.line` | Read | The sub-ledger every mapped statement line ties back to, and the records the Scenario 5 net figure of USD 425,000.00 and the Scenario 6 tax amount of USD 21,000.00 are reconciled against |
| `account.move` | Read | The verification entries — including the Scenario 6 entry of USD 121,000.00 — each proved balanced before its totals are read onto a statement line |
| `account.code.mapping` | Read | The per-company statutory code divergence, read so that a presentation assignment follows the account rather than a code that differs by company |
| `account.tax` | Read | Tax code `VAT-21-S` and the base-and-tax split the "Current tax liabilities" line is reconciled to |
| `res.currency` | Read | The `USD` definition and the 2-decimal precision every monetary assertion is rounded to at half-up |

---

## Estimation

| Dimension | Rating | Basis |
|-----------|--------|-------|
| **Effort** | Medium | Twenty line assignments across ten codes and two frameworks, a mapping-completeness check, a single-line-per-framework refusal, a per-company framework designation, and six acceptance tests plus five edge-case tests — all against models whose fields already exist |
| **Complexity** | Medium | Two frameworks over one chart is the source of the complexity: account 1590 is netted under IFRS and given its own subtractive caption under ASC 210, and account 2200 has to reconcile to a tax code's tax amount rather than to a plain account balance. Neither requires new posting logic |
| **Uncertainty** | Low | Every field, selection and constraint this story relies on was read in the repository during discovery. The one residual unknown is where the balance-sheet line set is authored, which follows from DEC-002 and changes the renderer rather than the classification |
| **Story Points** | **5** (Fibonacci: 1, 2, 3, 5, 8, 13) | |

Five points reflects two frameworks laid over one chart against low technical risk. The configuration itself is shallow — no posting logic, no integration, no migration — but the review load is heavy: each of the twenty assignments is signed off against a named standard by the Finance SME and the External Auditor, and the contra-asset and tax-presentation nuances are the two rows most likely to be re-cut in review. Three points would understate that review effort and the eleven distinct outcomes proved; eight would overstate a story that introduces no unresolved technical decision, since the classification surface and the report structures both already exist in `account`. The estimate assumes the group presentation policy is signed off during the sprint, and it excludes authoring the statements themselves, which is FEATURE-001-07.

---

## Test Requirements

### Coverage Requirement

| Metric | Requirement | Notes |
|--------|-------------|-------|
| **Minimum Test Coverage** | **80%** | Mandatory for all new functionality delivered by this story (C-007) |
| Unit Test Coverage | 80% or higher | Line resolution per framework, the single-line-per-framework rule, the completeness count, `off_balance` exclusion, tag inheritance on a newly created account |
| Integration Test Coverage | 80% or higher | Balance Sheet and Trial Balance runs under both frameworks, the contra-asset net figure, the tax-code reconciliation, and multi-company isolation of the mapping |
| Accounting assertion style | Numeric | Every monetary, tax-split and debits-equal-credits assertion is compared as an amount in `USD` at 2 decimal places using half-up rounding, never inspected by eye (C-009) |
| Traceability | One test per criterion | Each of the six scenarios maps to exactly one named acceptance test below (C-008) |

### Unit Test Scenarios

| Acceptance Scenario | Unit Test Focus | Key Assertions |
|---------------------|-----------------|----------------|
| Scenario 1 | IFRS line resolution across the ten codes | Each of the ten codes resolves to exactly one IAS 1 line matching the mapping matrix; the count of on-balance accounts with no IFRS line is 0; the "Trade and other receivables" line resolves to account 1200 and to no other code |
| Scenario 2 | US GAAP line resolution and framework isolation | Account 1500 resolves to "Property and equipment, gross" and account 1590 to "Less: accumulated depreciation" in Acme Industries Inc.; no account in Acme Industries Inc. resolves to an IAS 1 line and no account in Acme Group NV resolves to an ASC 210 line; the Acme Group NV assignments are byte-for-byte unchanged after the Acme Industries Inc. assignment |
| Scenario 3 | Mapping-completeness check and the publication gate | With account 1590 unassigned, the unmapped count equals 1, the reported record names code 1590 and framework IFRS, its balance equals USD 75,000.00 at 2 decimal places with half-up rounding, and publication raises the refusal; with all ten assigned, the count equals 0 and publication succeeds |
| Scenario 4 | Single-line-per-framework validation | Adding a second IFRS line to account 1200 raises a validation error naming the code and both line captions; after the error, account 1200 holds exactly one IFRS line and its caption still equals "Trade and other receivables" |
| Scenario 5 | Contra-asset net computation | The IFRS line figure equals USD 425,000.00 at 2 decimal places with half-up rounding; it equals the arithmetic sum of the two `account.move.line` balances at a difference of USD 0.00; the Trial Balance rows for 1500 and 1590 remain separate and its total debits equal its total credits |
| Scenario 6 | Tax line composition and the base-and-tax split | The "Current tax liabilities" figure equals USD 21,000.00 and equals the tax amount of `VAT-21-S` at a difference of USD 0.00; the base amount of USD 100,000.00 is absent from that line and present on "Revenue"; the source entry's total debits of USD 121,000.00 equal its total credits of USD 121,000.00 |

### Integration Test Considerations

- [ ] Post the Scenario 6 entry through `account.move` and `account.move.line` and assert total debits of USD 121,000.00 equal total credits of USD 121,000.00 at a difference of USD 0.00 **before** any statement line is read from it.
- [ ] Run the **Balance Sheet** as of 31 December 2026 for Acme Group NV and for Acme Industries Inc. in the same test and assert that each mapped line equals the sum of the `account.move.line` records beneath it at a difference of USD 0.00, and that the two runs read the same underlying balances.
- [ ] Run the **Trial Balance** for 01 January 2026 to 31 December 2026 alongside each Balance Sheet run and assert total debits equal total credits at a difference of USD 0.00, so that a presentation change is never able to mask an unbalanced ledger.
- [ ] Assert multi-company isolation per C-014: a role restricted to Acme Group NV can neither read nor alter the US GAAP assignments of Acme Industries Inc., and a Balance Sheet run under that role returns only Acme Group NV figures.
- [ ] Install one `l10n_*` localization pack into a test company and assert that its statutory presentation and the group line set coexist over one chart, that no account is duplicated, and that every divergence is recorded against the group line.
- [ ] Create an account inside an already-mapped code range, assert that it inherits the IFRS and US GAAP lines of its closest parent account, then re-run the completeness check and assert an unmapped count of 0 (Edge Case 2).
- [ ] Add an `off_balance` account, assert it is excluded from the unmapped count, contributes USD 0.00 to every line of both Balance Sheets, and leaves the on-balance Trial Balance totals equal at a difference of USD 0.00 (Edge Case 3).
- [ ] Supply a malformed as-of date and an inverted date range to the Balance Sheet and Trial Balance runs and assert each is rejected with a named validation error that discloses no stack trace, no SQL and no file-system path, and that no journal entry and no line assignment is created by the rejected request (C-019, C-020, C-022).
- [ ] Export a mapped statement to CSV and XLSX with a line caption beginning with `=` and assert the value is neutralized so the spreadsheet treats it as text (C-017).

### Acceptance Test Mapping

| BDD Scenario | Test Method Name | Test Type |
|--------------|------------------|-----------|
| Scenario 1: Every baseline account resolves to one IAS 1 line on the Balance Sheet | `test_baseline_accounts_resolve_to_single_ifrs_line` | Acceptance |
| Scenario 2: The same codes resolve to ASC 210 lines in the US GAAP entity without disturbing the IFRS entity | `test_us_gaap_lines_isolated_from_ifrs_presentation` | Acceptance |
| Scenario 3: An account left without a presentation line blocks publication of the mapping | `test_unmapped_account_blocks_taxonomy_publication` | Acceptance |
| Scenario 4: A second presentation line under the same framework is refused | `test_conflicting_second_ifrs_line_refused` | Acceptance |
| Scenario 5: Contra-asset net presentation ties out to the Trial Balance and the sub-ledger | `test_contra_asset_net_presentation_ties_to_subledger` | Acceptance |
| Scenario 6: A tax line reports the tax amount only, held apart from its base amount | `test_tax_liability_line_splits_base_and_tax_amount` | Acceptance |

---

## Definition of Done

### Implementation Checklist

- [ ] **All six acceptance-criteria scenarios pass**, each proved by its named automated test in § Acceptance Test Mapping.
- [ ] **80% minimum test coverage achieved** for the functionality delivered by this story, reported by the repository's coverage tooling (C-007).
- [ ] Unit tests written and passing for per-framework line resolution, the single-line-per-framework rule, the completeness count, the `off_balance` exclusion and tag inheritance on a newly created account.
- [ ] Integration tests written and passing for both Balance Sheet runs, the Trial Balance tie-out, the contra-asset net figure, the tax-code reconciliation and multi-company isolation.
- [ ] All five edge cases in § Edge Cases are covered by tests: the zero-balance line, the legacy account loaded after publication, the `off_balance` exclusion, the per-framework divergence on account 1590, and the taxonomy line with no mapped account.
- [ ] The mapping matrix is applied to a second company without hand-editing, and was applied to Acme Industries Inc. under US GAAP during verification while Acme Group NV's IFRS presentation was proved unchanged.
- [ ] The mapping-completeness check reports an unmapped-account count of **0** for every in-scope company under every framework that company reports under, before the mapping is published.

### Accounting Reconciliation Gate

This gate is the accounting contract of the story. Each item is asserted as an amount, in the currency named, at 2 decimal places using half-up rounding.

- [ ] **Debits equal credits on every entry posted during verification.** Each verification entry — including the Scenario 6 entry with total debits of USD 121,000.00 and total credits of USD 121,000.00 — posts with a difference of **USD 0.00**, and no statement line is read from an entry until that assertion has passed.
- [ ] **The mapped statement reconciles to a balanced Trial Balance.** The **Trial Balance** for **01 January 2026 to 31 December 2026** reports **total debits equal to total credits** at a difference of **USD 0.00** for Acme Group NV and, run separately, for Acme Industries Inc.; every Balance Sheet line produced by this mapping ties to that Trial Balance, so a classification can never be accepted against an unbalanced ledger.
- [ ] **Every mapped statement line ties to the `account.move.line` sub-ledger.** Each line equals the sum of the journal items beneath it at a difference of **USD 0.00** — "Trade and other receivables" at USD 48,750.00, "Property, plant and equipment" at USD 425,000.00 net of USD 500,000.00 and USD 75,000.00, and "Current tax liabilities" at USD 21,000.00 — and each line drills through to those records.
- [ ] **The tax line's base and tax amounts tie to their tax code.** The "Current tax liabilities" figure of **USD 21,000.00** equals the tax amount recorded against tax code **`VAT-21-S`** for 01 January 2026 to 31 December 2026 at a difference of **USD 0.00**, its **base amount of USD 100,000.00** is reported separately and presented on the "Revenue" line, and no part of the base amount reaches the tax line.
- [ ] **Contra-asset presentation preserved in the ledger.** Accounts 1500 and 1590 remain separate records with balances of USD 500,000.00 debit and USD 75,000.00 credit; the IFRS net line of USD 425,000.00 is a presentation outcome only, and the US GAAP gross-and-contra presentation of the same two balances agrees with it at a difference of USD 0.00.
- [ ] **No amount falls outside a line and none is double-counted.** The sum of all IFRS line figures equals the sum of all mapped account balances at a difference of **USD 0.00**, and the same assertion holds for the US GAAP line set, so the count of accounts contributing to zero lines and the count contributing to two lines under one framework are both 0.

### Compliance Checklist

- [ ] Licence compatibility verified per C-001 and C-002: an AGPL-3.0 compatible licence declared, and the LGPL-3 licence of `account` respected by every derived work.
- [ ] No parallel presentation model introduced; the classification is carried on `account.account` and the existing tagging and report structures (C-012).
- [ ] Multi-company record rules exercised by test: a role restricted to Acme Group NV can neither read nor alter the assignments or statements of Acme Industries Inc. (C-014).
- [ ] The inherited untrusted-input requirements are discharged: report date parameters validated (C-019), failures reported without internal detail (C-020), exported cell values neutralized (C-017), rendered captions context-encoded (C-018), each proved by the hostile-input tests required by C-022.
- [ ] Static analysis passes with the repository's configured tooling at zero violations, and the code follows Odoo and OCA standards (C-005, C-006).
- [ ] The confirmed platform version and edition, once DEC-001 and DEC-002 are recorded, are restated in the parent Feature and the field and selection names asserted here are re-checked against them.
- [ ] Code reviewed and approved, with the group presentation policy countersigned by the Chief Accountant and reviewed by the External Auditor.

### Documentation Checklist

- [ ] Docstrings and inline comments complete for every public method delivered.
- [ ] The mapping matrix — the ten codes with their `account_type` values, IAS 1 lines and ASC 210/220 lines — is recorded alongside the code that applies it, with the standard reference cited per line.
- [ ] The contra-asset treatment of account 1590 is documented per framework: netted into "Property, plant and equipment" under IFRS, presented as "Less: accumulated depreciation" under US GAAP.
- [ ] The reconciliation of each in-scope `l10n_*` statutory presentation to the group line set is documented per country, with every divergence recorded against the group line.
- [ ] Finance-facing notes updated so the Financial Reporting Manager can classify a newly created account without breaching the single-line-per-framework rule, including how an inherited assignment is overridden.
- [ ] The publication procedure is documented: run the completeness check, resolve every unmapped account to 0, obtain sign-off, publish, and re-run the check after any legacy load.

### Quality Checklist

- [ ] No critical or high-severity defect open against the classification, the completeness check or either framework's line set.
- [ ] The Chart of Accounts view showing the account tags and account type columns renders in under 3 seconds for a chart of 2,000 accounts, the parent Feature's performance target for this structure.
- [ ] Access rights verified per finance role: the Financial Reporting Manager maintains the mapping, the Chief Accountant owns the accounts, and the External Auditor holds read-only access to the mapping and its change history.
- [ ] Every change to a presentation assignment and to `account_type` is retained with its author and timestamp and is readable by the External Auditor without a data request.
- [ ] **Demonstrated in the Odoo user interface to the Finance Controller and the Product Owner** by walking the five steps of § Demonstration — the Chart of Accounts with the account tags and account type columns for Acme Group NV, the same view for Acme Industries Inc., the Balance Sheet as of 31 December 2026 grouped by taxonomy line for each company, and the two refusals — with the walkthrough recorded against this story (R-G).

---

## References

### Accounting Standards

| Standard | Reference | Application to This Story |
|----------|-----------|---------------------------|
| **IAS 1** | Presentation of Financial Statements, IFRS Foundation | Supplies every caption in the IFRS column of the mapping matrix, the current-versus-non-current split the `account_type` value carries, and the net presentation of account 1590 Accumulated Depreciation inside "Property, plant and equipment" |
| **ASC 210** | FASB Accounting Standards Codification, Balance Sheet | Supplies the US GAAP balance-sheet captions, including the gross-and-contra presentation of accounts 1500 and 1590 as "Property and equipment, gross" and "Less: accumulated depreciation" |
| **ASC 220** | FASB Accounting Standards Codification, Income Statement — Reporting Comprehensive Income | Supplies the income-statement captions for accounts 4000 Revenue ("Revenues") and 6100 Expense ("Operating expenses"), the US GAAP counterpart of the IAS 1 income-statement presentation |
| IFRS Foundation issued standards | <https://www.ifrs.org/issued-standards/list-of-standards/> | The authority for the IAS 1 captions and for the IFRS Accounting Taxonomy element names used where a filing is made in a structured format |
| FASB Accounting Standards Codification | <https://asc.fasb.org/> | The authority for the ASC 210 and ASC 220 captions and for the US GAAP Financial Reporting Taxonomy element names |

### OCA Modules (Reference)

| Repository | Module | Relevance |
|------------|--------|-----------|
| OCA/account-financial-reporting | `account_financial_report` | Renders the Balance Sheet, Profit & Loss, General Ledger and Trial Balance from account types and hierarchy; the candidate consumer of this classification under the OCA path of DEC-002 |
| OCA/account-financial-reporting | `account_tax_balance` | Reports balances per tax code, the surface the Scenario 6 base-and-tax split is verified against |
| OCA/mis-builder | `mis_builder` | Expresses statement line sets as account-code expressions, a candidate for carrying both framework line sets over one chart |
| OCA/account-financial-tools | `account_chart_update` | Applies country-template changes to an installed chart; examined to confirm a template refresh preserves an existing presentation assignment |

### Source Code References

| Path | Relevance |
|------|-----------|
| `addons/account/models/account_account.py` | `account.account` with the nineteen-value `account_type` selection (`asset_receivable`, `asset_cash`, `asset_current`, `asset_non_current`, `asset_prepayments`, `asset_fixed`, `liability_payable`, `liability_credit_card`, `liability_current`, `liability_non_current`, `equity`, `equity_unaffected`, `income`, `income_other`, `expense`, `expense_other`, `expense_depreciation`, `expense_direct_cost`, `off_balance`), declared `required=True` and `tracking=True`; the `tag_ids` many-to-many that carries the classification; `include_initial_balance` ("Bring Accounts Balance Forward"), which separates the balance-sheet rows of the matrix from the income-statement rows; and the routine that assigns tags from the closest parent account to an account created with a code and no tags, which Edge Case 2 relies on |
| `addons/account/models/account_account_tag.py` | `account.account.tag` with its translatable `name`, the `applicability` selection `accounts` / `taxes` / `products`, `country_id`, `active`, the uniqueness constraint on name-plus-applicability-plus-country, and the three master cash-flow tags protected from deletion because they are used on the chart-of-accounts definition |
| `addons/account/models/account_report.py` | `account.report`, `account.report.line`, `account.report.expression`, `account.report.column` and `account.report.external.value`, and the six computation engines on the expression — `domain`, `tax_tags`, `aggregation`, `account_codes`, `external` and `custom` — with `formula`, `subformula` and `date_scope`; the structures a taxonomy line set is authored into |
| `addons/account/data/account_reports_data.xml` | Defines only `generic_tax_report`, `generic_tax_report_account_tax` and `generic_tax_report_tax_account`, with **zero** `account.report.line` records — the concrete evidence that this Community repository ships report structures without a balance-sheet line set, and therefore the concrete shape of DEC-002 |
| `addons/account/models/account_code_mapping.py` | `account.code.mapping` with `account_id`, `company_id` and `code`, the per-company statutory code divergence recorded against one account |
| `addons/account/models/account_tax.py`, `addons/account/models/account_move_line.py` | How a tax code's base amount and tax amount are recorded on separate lines, the source of the Scenario 6 split |
| `addons/account/__manifest__.py` | The `account` module identity cited throughout: "Invoicing", version 1.4, category `Accounting/Accounting`, licence LGPL-3 |
| `addons/l10n_*/` | The 209 localization packs; the country-specific account tags and statutory report lines they ship are what the group line set is reconciled against, pack by pack for each in-scope country |
| `addons/account_financial_report_ce/models/balance_sheet.py`, `trial_balance.py`, `profit_loss.py` | The AGPL-3 implementations present today — `account.balance.sheet.report` with `date_from` and `date_to`, and `account.trial.balance.report` with the date range this story's tie-out is asserted over — version 19.0.1.1.0 |
| `odoo/addons/base/models/res_company.py`, `res_currency.py` | The company hierarchy the reporting-framework designation is recorded against, and the `USD` decimal precision every monetary assertion is rounded to |
| `odoo/release.py` | The platform baseline `version_info = (19, 0, 0, FINAL, 0, '')`, cited by DEC-001 |

### Ticket References

| Document | Link |
|----------|------|
| Parent Feature | [FEATURE-001-01: Chart of Accounts & Fiscal Year](../FEATURE-001-01-chart-of-accounts-fiscal-year.md) |
| Parent Epic | [EPIC-001: Enterprise Accounting in Odoo](../../EPIC-001-enterprise-accounting-odoo.md) |
| Blocking predecessor, which fixes the ten codes and their types | [STORY-001-01-01: Configure Multi-Level Chart of Accounts Hierarchy](./STORY-001-01-01-configure-coa-hierarchy.md) |
| Related sibling, whose imported accounts inherit this mapping | [STORY-001-01-04: Import Legacy Chart of Accounts and Opening Balances](./STORY-001-01-04-import-legacy-coa.md) |
| Persona register the WHO is drawn from | [EPIC-001 §3.1 User Personas](../../EPIC-001-enterprise-accounting-odoo.md#31-user-personas) |
| Success metric SM-001, which this story is measured on | [EPIC-001 §4.1 Measurable Outcomes](../../EPIC-001-enterprise-accounting-odoo.md#41-measurable-outcomes) |
| Authoring bounds: 4-to-8 criteria, coverage distribution, Fibonacci scale | [EPIC-001 §5.3 Decomposition Guidelines](../../EPIC-001-enterprise-accounting-odoo.md#53-feature-and-story-decomposition-guidelines) |
| Odoo module scope, including the absent Enterprise modules | [EPIC-001 §5.4 Odoo Module Scope](../../EPIC-001-enterprise-accounting-odoo.md#54-odoo-module-scope) |
| Constraint set C-001 to C-022 | [EPIC-001 §7 Constraints](../../EPIC-001-enterprise-accounting-odoo.md#7-constraints) |
| Open decisions DEC-001 and DEC-002 | [EPIC-001 Appendix B: Open Decisions Register](../../EPIC-001-enterprise-accounting-odoo.md#appendix-b-open-decisions-register) |
| Capability CAP-002, which this story delivers | [FEATURE-001-01 §1.3 Key Capabilities](../FEATURE-001-01-chart-of-accounts-fiscal-year.md#13-key-capabilities) |
| Story ordering inside the feature | [FEATURE-001-01 §3.3 Story Dependency Ordering](../FEATURE-001-01-chart-of-accounts-fiscal-year.md#33-story-dependency-ordering) |

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-08-13 | Enterprise Accounting Team | Initial story creation |
| 1.1 | 2026-08-13 | Enterprise Accounting Team | Review remediation. Tax code `VAT-STD-21` replaced throughout by `VAT-21-S`, the 21% output-tax code in the governed tax-code set owned by [FEATURE-001-05](../FEATURE-001-05-tax-configuration-compliance.md); the rate, the base amount, the tax amount and the postings are unchanged, only the code name now resolves against the one governed vocabulary. Demonstrability section heading normalized to `## Demonstration Path`. Revision date aligned to the tree-wide authoring date. Trailing blank line removed at end of file |

---

## Notes

**Governing rules for this ticket.** The rules review for this task returned **no user-specified rules**. None govern this file, none have been invented to fill the gap, and the authoring bar is not lowered because of it: the Epic's own output requirements and validation gates — the naming convention, the 4-to-8 criteria bound with its coverage distribution, the forbidden-qualifier ban, monetary precision, the debits-equal-credits assertion, INVEST conformance, demonstrability, the named finance persona, referential integrity and accounting determinism — together with the constraint set C-001 to C-022 and the structure of `tickets/templates/story-template.md`, are treated as the mandatory acceptance rules for this file and were each verified against it before it was published.

**Platform version and edition remain open (DEC-001, DEC-002).** The originating programme request names Odoo 17, this repository is Odoo 19.0 Community, and the prior superseded backlog targeted 18.0. This story states the model names, field names and selection values as they exist in the 19.0 baseline it was verified against — the nineteen-value `account_type` selection, `tag_ids` on `account.account`, the `applicability` selection on `account.account.tag`, and the six computation engines on `account.report.expression` — and flags the mismatch for stakeholder confirmation rather than choosing a target. The consequence carried here is that the 209 `l10n_*` packs present are 19.0-series, so an earlier target changes which pack supplies each statutory presentation this mapping is reconciled against.

**The Enterprise report-engine gap is this story's most material open dependency (DEC-002).** The dynamic report engine that renders a Balance Sheet from presentation lines ships with the Enterprise module **`account_reports`, which is absent from this repository**. The gap is concrete rather than theoretical: `addons/account/data/account_reports_data.xml` defines three generic tax reports and **zero** `account.report.line` records, so Community supplies `account.report`, `account.report.line` and `account.report.expression` as structures with no balance-sheet line set to populate. The story is nonetheless demonstrable today under the OCA path, because the AGPL-3 add-on `account_financial_report_ce` version 19.0.1.1.0 is present and its `account.balance.sheet.report` and `account.trial.balance.report` models carry the as-of and date-range parameters every criterion here is asserted through. This is the reason the classification is expressed as data attached to the account rather than against one engine's internals: the mapping outcome is identical under an Enterprise subscription and under the OCA path, and only the renderer changes. The edition decision is surfaced, not presumed.

**Why IFRS and US GAAP are one story.** Splitting them would permit a code to be classified under one framework and left unclassified under the other, and the completeness gate in Scenario 3 would then be satisfiable while half the mapping was missing. Holding them together is also what makes account 1590 Accumulated Depreciation verifiable at all, since its net treatment under IAS 1 and its subtractive caption under ASC 210 are only meaningful against each other. Recognition and measurement differences between the two frameworks are deliberately out of scope: this story presents one set of posted amounts two ways and never restates an amount.

**Company names and reference figures.** Acme Group NV (parent, functional currency `USD`, IFRS) and Acme Industries Inc. (subsidiary, functional currency `USD`, US GAAP) are the reference entities used across the criteria so that every framework and multi-company assertion names the books it affects. They stand for the group's legal-entity register, which is enumerated during discovery; substituting the confirmed entity names changes the names in the criteria and nothing else. The balances used — USD 48,750.00 on account 1200, USD 500,000.00 on account 1500, USD 75,000.00 on account 1590, and the USD 100,000.00 base with USD 21,000.00 tax on tax code `VAT-21-S` — are the deterministic verification fixtures for this story (D-009) and are not a forecast of production volumes.

**Scope of this ticket.** This file is a planning artifact. It states the presentation classification finance requires and the assertions that prove it; it contains no module, model, view, report or data definition, and it prescribes none. The mechanism — an account-tag family, a report-line set sourced from account-code prefixes, or a combination of the two — is chosen by the implementing agent from the discovery recorded above.
