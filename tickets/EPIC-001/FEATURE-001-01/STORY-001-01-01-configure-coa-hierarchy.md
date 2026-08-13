# STORY-001-01-01: Configure Multi-Level Chart of Accounts Hierarchy

---

## Metadata

| Attribute | Value |
|-----------|-------|
| **Story ID** | `STORY-001-01-01` |
| **Title** | Configure Multi-Level Chart of Accounts Hierarchy |
| **Parent Feature** | [FEATURE-001-01: Chart of Accounts & Fiscal Year](../FEATURE-001-01-chart-of-accounts-fiscal-year.md) |
| **Parent Epic** | [EPIC-001: Enterprise Accounting in Odoo](../../EPIC-001-enterprise-accounting-odoo.md) |
| **Persona** | Chief Accountant |
| **Status** | Draft |
| **Priority** | 🔴 Critical |
| **Estimate** | 5 story points (Fibonacci) |
| **Feature Capability** | CAP-001 — define a multi-level Chart of Accounts with account types, codes and hierarchy across all legal entities |
| **Epic Success Metric** | SM-006 — Trial Balance integrity, with the difference column asserted at 0.00 in the company currency |
| **Owner/Author** | Enterprise Accounting Team |

This story is the root of the `FEATURE-001-01/` folder and the first ticket of EPIC-001 that can be built. The ten account codes, the `account.group` hierarchy and the five journal types it fixes are cited by the other eight features and the other forty stories of this backlog, so an assertion made here propagates across the whole tree.

---

## User Story

**As a** Chief Accountant

**I want** a multi-level chart of accounts released into Acme Group NV — ten baseline `account.account` records carrying deterministic codes and `account_type` values, rolled up through an `account.group` hierarchy whose code-prefix ranges span 1000 to 6999, alongside the five journal types every entry is routed through

**So that** every journal item posted in the group, and every line of the Trial Balance and the Balance Sheet read back from it, resolves to exactly one account code whose type and hierarchy position were fixed before the first posting, and the Trial Balance for any company and any period reports total debits equal to total credits at a difference of USD 0.00 rounded to 2 decimal places using half-up rounding (SM-006).

---

## INVEST Principles Compliance

| Principle | Compliance | Notes |
|-----------|------------|-------|
| **Independent** | ✅ | This story has **no blocking predecessor**. It is the root of `FEATURE-001-01/`: it needs only the `account` module and one `res.company` record, both present in the platform baseline, so it can start before every other ticket in EPIC-001. It **blocks** [STORY-001-01-02](./STORY-001-01-02-map-accounts-ifrs-gaap-taxonomy.md), because a presentation tag is attached to an account record that must already exist, and [STORY-001-01-04](./STORY-001-01-04-import-legacy-coa.md), because an opening entry needs target codes to debit and credit. Both are **configuration sequencing, not code coupling**: neither sibling shares an implementation with this story, and each is developed against the ten codes fixed here rather than against how they were created. |
| **Negotiable** | ✅ | The outcome is stated — ten typed codes resolving through a group hierarchy — and the mechanism is left open. Whether the chart arrives by reconciling a `l10n_*` statutory pack, by a chart template, or by configuration data is deferred to the discovery recorded below. The group names and the prefix boundaries are open to negotiation with the Group Controller for as long as every code still resolves to exactly one most-specific group. |
| **Valuable** | ✅ | Without this story no entry can be posted and no statement can be grouped: FEATURE-001-02, FEATURE-001-03 and FEATURE-001-07 are gated on it by ordering rule ORD-001 in the Epic. It converts the manual mapping step that today precedes every group balance into a structural property of the ledger, and it is the precondition of the Epic's 2-to-4-hour-to-under-5-minute statement target (SM-005) and of Trial Balance integrity (SM-006). |
| **Estimable** | ✅ | The work is bounded by a countable deliverable: nine account groups, ten accounts, ten `account_type` assignments, two Allow Reconciliation flags and five journal types, against existing Odoo models whose fields are already known. Nothing in it awaits an open decision, so it is sized at 5 Fibonacci points with the rationale recorded in § Estimation. |
| **Small** | ✅ | One configuration outcome — the account structure of one company, reproducible across the others — demonstrated in a single walkthrough of the Chart of Accounts, the Account Groups and one Trial Balance run. The fiscal calendar, the taxonomy tags, the legacy load and the lock dates are each a separate sibling story, so this story is not a container for the whole feature. |
| **Testable** | ✅ | Every criterion below is asserted as a number, a code, a type value or a refusal message: exactly ten accounts, one group per code, total debits equal to total credits at a difference of USD 0.00, a refused duplicate code, a blocked deletion. Each of the six scenarios maps to one named automated test in § Test Requirements, so pass or fail is decided without judgement. |

---

## Acceptance Criteria

Six criteria are authored, inside the 4-to-8 bound the Epic sets in [§5.3](../../EPIC-001-enterprise-accounting-odoo.md#53-feature-and-story-decomposition-guidelines), and they carry the mandated coverage distribution: Scenarios 1 and 2 are valid-input cases (configuration, then a report that proves the roll-up), Scenario 3 is the invalid and incomplete-input case, Scenario 4 is the error-handling case, and Scenarios 5 and 6 are accounting edge cases (multi-company sharing and a foreign-currency account).

Scenarios 1 to 5 are asserted against the ten-account baseline. Scenario 6 adds account 1015 Bank EUR to that baseline as the group's foreign-currency bank account, so the eleventh-account refusal in Scenario 3 and the eleventh account created in Scenario 6 are two separate states of the chart rather than a contradiction.

### Scenario 1: Ten baseline accounts created under the account-group hierarchy

- **Given** Acme Group NV exists as a company whose functional currency is `USD`, module `account` is installed, and no chart of accounts has been loaded into that company
- **When** the Chief Accountant releases the group chart-of-accounts policy into Acme Group NV as the account-group structure and its ten baseline accounts
- **Then** the Chart of Accounts of Acme Group NV lists exactly ten `account.account` records — 1010 Bank (`asset_cash`), 1200 Accounts Receivable (`asset_receivable`), 1500 Fixed Assets (`asset_fixed`), 1590 Accumulated Depreciation (`asset_fixed`), 2000 Accounts Payable (`liability_payable`), 2200 Tax Payable (`liability_current`), 3000 Share Capital (`equity`), 3100 Retained Earnings (`equity`), 4000 Revenue (`income`) and 6100 Expense (`expense`) — each one nested under the most specific `account.group` whose `code_prefix_start`-to-`code_prefix_end` range contains its code: 1010 under `10 Bank and Cash` (1000–1099), 1200 under `12 Receivables` (1200–1299), 1500 and 1590 under `15 Non-current Assets` (1500–1599), 2000 under `20 Payables` (2000–2099), 2200 under `22 Tax` (2200–2299), 3000 and 3100 under `3 Equity` (3000–3999), 4000 under `4 Income` (4000–4999) and 6100 under `6 Expenses` (6000–6999); groups `10`, `12` and `15` resolve to parent group `1 Assets` and groups `20` and `22` resolve to parent group `2 Liabilities`; the count of accounts with no `account_type` value is 0 and the count of accounts falling outside every group range is 0; accounts 1200 and 2000 each carry Allow Reconciliation enabled; and the five journal types exist in Acme Group NV — Sales (`sale`), Purchase (`purchase`), Bank (`bank`), Cash (`cash`) and Miscellaneous (`general`)

### Scenario 2: Group roll-up proved on the Trial Balance

- **Given** the ten baseline accounts of Scenario 1 exist in Acme Group NV and one journal entry dated 15 January 2026 is posted in the Miscellaneous journal (journal type `general`) debiting account 1010 Bank by USD 10,000.00 and crediting account 3000 Share Capital by USD 10,000.00, each amount rounded to 2 decimal places using half-up rounding
- **When** the Chief Accountant runs the Trial Balance for Acme Group NV over the date range 01 January 2026 to 31 January 2026
- **Then** the Trial Balance reports account 1010 Bank at a debit of USD 10,000.00 and account 3000 Share Capital at a credit of USD 10,000.00, group `1 Assets` at a debit subtotal of USD 10,000.00 and group `3 Equity` at a credit subtotal of USD 10,000.00, and total debits of USD 10,000.00 equal to total credits of USD 10,000.00 — a difference of USD 0.00 — with every amount rounded to 2 decimal places using half-up rounding

### Scenario 3: Duplicate account code and missing account type both refused

- **Given** the ten baseline accounts exist in Acme Group NV and the Chief Accountant is creating an eleventh account in that company
- **When** the Chief Accountant saves the eleventh account with code `1010`, the code account 1010 Bank already occupies in Acme Group NV
- **Then** the save is refused with a validation message that names the duplicate code `1010` and the company Acme Group NV, no eleventh `account.account` record is created, and the Chart of Accounts of Acme Group NV still lists exactly ten accounts; by the same required-field rule, an account saved with an unused code but with `account_type` left empty is also refused and no record is created, so the account count of Acme Group NV stays at ten in both cases

### Scenario 4: Deletion of an account carrying journal items is blocked

- **Given** account 1200 Accounts Receivable in Acme Group NV carries posted journal items whose debit total is USD 48,750.00, rounded to 2 decimal places using half-up rounding
- **When** the Chief Accountant requests deletion of account 1200 Accounts Receivable
- **Then** the deletion is refused with a message stating that the account contains journal items, account 1200 remains in the Chart of Accounts of Acme Group NV with its debit balance held at USD 48,750.00, no journal item is removed, the Trial Balance for 01 January 2026 to 31 January 2026 reports the same total debits and total credits as it did before the attempt and they stay equal at a difference of USD 0.00, every amount rounded to 2 decimal places using half-up rounding, and the message directs the Chief Accountant to the account deactivation flag as the retirement path — the flag labelled Deprecated in the Odoo 17 series named by DEC-001, and the `active` archive flag in the Odoo 19.0 baseline present in this repository

### Scenario 5: Payable account shared with the subsidiary company

- **Given** Acme Group NV (parent, functional currency `USD`) and Acme Industries Inc. (subsidiary) both exist, and account 2000 Accounts Payable carries a credit balance of USD 312,480.00 in Acme Group NV, rounded to 2 decimal places using half-up rounding
- **When** the Chief Accountant adds Acme Industries Inc. to the `company_ids` of account 2000 Accounts Payable
- **Then** account 2000 Accounts Payable becomes selectable on journal items in Acme Industries Inc. and carries a code in that company, the balance of account 2000 in **Acme Industries Inc.** is USD 0.00 against 0 journal items, the balance of account 2000 in **Acme Group NV** is held at USD 312,480.00 credit, and the Trial Balance for 01 January 2026 to 31 January 2026 run separately for each company reports total debits equal to total credits at a difference of USD 0.00 in **Acme Group NV** and a difference of USD 0.00 in **Acme Industries Inc.**, every amount rounded to 2 decimal places using half-up rounding

### Scenario 6: Foreign-currency bank account reported at the closing rate

- **Given** account 1015 Bank EUR exists in Acme Group NV alongside the ten baseline accounts, carrying `account_type` `asset_cash`, Account Currency `EUR` and a position under group `10 Bank and Cash` (1000–1099), while the functional currency of Acme Group NV is `USD` and the rate recorded for 31 January 2026 is 1 EUR = 1.1000 USD
- **When** an entry dated 31 January 2026 is posted in the Miscellaneous journal (journal type `general`) debiting account 1015 Bank EUR by EUR 1,000.00 against a credit of EUR 1,000.00 to account 4000 Revenue, each amount rounded to 2 decimal places using half-up rounding
- **Then** each journal item retains its foreign-currency amount of EUR 1,000.00 rounded to 2 decimal places using half-up rounding, the Trial Balance for Acme Group NV over the date range 01 January 2026 to 31 January 2026 reports account 1015 Bank EUR at a debit of USD 1,100.00 and account 4000 Revenue at a credit of USD 1,100.00 — each translated at 1 EUR = 1.1000 USD and rounded to 2 decimal places using half-up rounding — and total debits of USD 1,100.00 equal total credits of USD 1,100.00, a difference of USD 0.00

---

## Sub-Tasks

| # | Sub-Task | Assignee |
|---|----------|----------|
| 1 | Draft the group chart-of-accounts policy: the three-level `account.group` design with its prefix ranges (`1 Assets` → `10 Bank and Cash` 1000–1099, `12 Receivables` 1200–1299, `15 Non-current Assets` 1500–1599; `2 Liabilities` → `20 Payables` 2000–2099, `22 Tax` 2200–2299; `3 Equity` 3000–3999; `4 Income` 4000–4999; `6 Expenses` 6000–6999) and the ten-account baseline with one `account_type` value per code, then obtain Group Controller approval | `@functional-consultant` |
| 2 | Reconcile the statutory chart that each in-scope `l10n_*` pack installs against that policy with the Tax Accountant, and record every divergence as a per-company account code mapping instead of a parallel chart | `@functional-consultant` |
| 3 | Configure the chart data so a company created from the group policy receives the ten accounts, their group hierarchy and the five journal types — Sales (`sale`), Purchase (`purchase`), Bank (`bank`), Cash (`cash`) and Miscellaneous (`general`) — in one repeatable step | `@developer` |
| 4 | Enable Allow Reconciliation on 1200 Accounts Receivable and 2000 Accounts Payable and prove the receivable-and-payable reconciliation constraint holds for both codes | `@developer` |
| 5 | Make the group roll-up readable on the Chart of Accounts and on the Trial Balance so a group subtotal is derived from the code-prefix ranges rather than re-entered by hand | `@developer` |
| 6 | Author the six automated acceptance tests named in § Test Requirements, one per scenario, with every monetary and debits-equal-credits assertion written as an amount | `@qa-engineer` |
| 7 | Add the negative tests: a duplicate code inside one company, an empty `account_type`, deletion of an account carrying journal items, and an overlapping group prefix range | `@qa-engineer` |
| 8 | Sign off each code-to-`account_type` assignment and the Trial Balance tie-out for 01 January 2026 to 31 January 2026, confirming total debits equal total credits at a difference of USD 0.00 | `@finance-sme` |

---

## Edge Cases

| # | Edge Case | Expected Handling |
|---|-----------|-------------------|
| 1 | An account holds no journal item for the reported range — account 2200 Tax Payable between 01 January 2026 and 31 January 2026 | The Trial Balance for that range reports account 2200 at USD 0.00 debit and USD 0.00 credit when zero-balance accounts are included, and omits its row when the run is restricted to accounts with activity; the report's total debits and total credits are unaffected by the choice and stay equal at a difference of USD 0.00, every amount rounded to 2 decimal places using half-up rounding |
| 2 | A group prefix range overlaps its neighbour at the same granularity — a new group Petty Cash given the two-character prefix range `10` to `12`, covering 1000–1299, against the existing `10 Bank and Cash` (1000–1099) and `12 Receivables` (1200–1299) | The save is refused by the same-granularity overlap validation, the hierarchy is unchanged so account 1010 stays under `10 Bank and Cash` and account 1200 stays under `12 Receivables`, and the Chief Accountant re-cuts the group at a finer granularity — the four-character range 1050–1099, which nests inside `10 Bank and Cash` — so every code still resolves to exactly one most-specific group |
| 3 | A contra-asset carries a credit balance inside an asset group — account 1590 Accumulated Depreciation at USD 84,000.00 credit inside `15 Non-current Assets` alongside account 1500 Fixed Assets at USD 420,000.00 debit | Group `15 Non-current Assets` presents both accounts on their own lines and subtotals to USD 336,000.00 net debit; the credit balance is retained on 1590 rather than reclassified to a liability group, so the Balance Sheet shows cost and accumulated depreciation separately and the Trial Balance total debits stay equal to total credits at a difference of USD 0.00, every amount rounded to 2 decimal places using half-up rounding |
| 4 | An account typed `off_balance` is added to the chart — commitments account 9000 under a new group `9 Off-Balance Sheet` (9000–9999) | Account 9000 is excluded from the accounting equation and from the Balance Sheet and Trial Balance totals of the on-balance report set, its own journal items balance within it, and the on-balance Trial Balance still reports total debits equal to total credits at a difference of USD 0.00, every amount rounded to 2 decimal places using half-up rounding |
| 5 | An account that already carries posted journal items is renamed or re-coded — account 6100 Expense re-coded to 6110 after posting | The change is accepted and reaches the existing journal items through the account link rather than by rewriting them, the account balance is unaffected, the old and new values are retained on the account's tracked-field history with their author and timestamp for the External Auditor, the account moves to the group whose range contains the new code so 6110 stays under `6 Expenses` (6000–6999), and the Trial Balance for the same date range reports total debits equal to total credits at a difference of USD 0.00, every amount rounded to 2 decimal places using half-up rounding |

---

## Demonstration Path

The story is accepted when the Chief Accountant walks the **Finance Controller** and the **Product Owner** through the following path in the Odoo user interface, with the Group Controller present to sign off the policy. Where a reviewer prefers the public API, the same five steps are demonstrated through it; either way the walkthrough is recorded against this story.

1. **Accounting ▸ Configuration ▸ Chart of Accounts** — filtered to Acme Group NV, showing the ten baseline accounts with their code, name and Type columns, the count of accounts at ten, and Allow Reconciliation enabled on 1200 Accounts Receivable and 2000 Accounts Payable.
2. **Accounting ▸ Configuration ▸ Account Groups** — showing each group with its `code_prefix_start`, `code_prefix_end` and parent, followed by the Chart of Accounts grouped on Group so that every account is seen resolving to one group. In the Odoo 19.0 baseline present in this repository the `account.group` form, list and search views ship without a dedicated menu item, so the group list is reached through the Group column and the Group grouping on the Chart of Accounts; whether that menu item is exposed directly follows from DEC-001.
3. **The Scenario 2 entry, posted live in the Miscellaneous journal** — debit account 1010 Bank USD 10,000.00, credit account 3000 Share Capital USD 10,000.00, each amount rounded to 2 decimal places using half-up rounding, showing the posted entry's total debits of USD 10,000.00 equal to its total credits of USD 10,000.00.
4. **The Trial Balance for 01 January 2026 to 31 January 2026** — showing group `1 Assets` at a debit subtotal of USD 10,000.00, group `3 Equity` at a credit subtotal of USD 10,000.00, and total debits of USD 10,000.00 equal to total credits of USD 10,000.00, a difference of USD 0.00.
5. **The negative walkthrough** — the duplicate code `1010` attempted and refused, and the deletion of account 1200 attempted and blocked, with the account count of Acme Group NV shown unchanged at ten after both attempts.

---

## Constraints

### License and Compliance

- [ ] **C-001 — AGPL-3.0 compatible licence.** Any module delivering the group chart-of-accounts policy, the group hierarchy or the journal baseline is distributed under an AGPL-3.0 compatible licence, matching the six Community-edition accounting add-ons already present in this repository.
- [ ] **C-002 — LGPL-3 of `account` respected.** `account.account`, `account.group` and `account.journal` are LGPL-3 code declared in `addons/account/__manifest__.py`; derived and dependent work stays licence-compatible with them and no derived work misstates their licence.
- [ ] **C-005 and C-006 — Odoo and OCA coding standards.** Python follows Odoo and OCA module guidelines including PEP 8, and static analysis passes with the repository's configured tooling in `ruff.toml` at zero violations.
- [ ] **C-012 — build on the existing models.** The chart, the hierarchy and the journal set are expressed on `account.account`, `account.group` and `account.journal` rather than on parallel structures, so one ledger and one audit trail survive the change.
- [ ] **C-014 — multi-company access rights.** The Chief Accountant maintains the chart, the Group Controller approves the policy, the External Auditor holds read-only access, and a role restricted to Acme Group NV can neither read nor post the accounts of Acme Industries Inc.

### Version Compatibility

The platform target of this programme is an **open decision (DEC-001)** recorded in the Epic's [Open Decisions Register](../../EPIC-001-enterprise-accounting-odoo.md#appendix-b-open-decisions-register) and stated here without being resolved:

| Candidate target | Evidence on record | Consequence for this story |
|------------------|--------------------|----------------------------|
| **Odoo 17** | Named by the originating programme request | The 209 `l10n_*` packs present here are 19.0-series, so each statutory chart this story reconciles against is re-selected for the 17 series; the account deactivation flag is the field labelled Deprecated in that series |
| **Odoo 18.0** | Targeted by the prior, superseded backlog | Neither the request nor this repository is served, and the field and view names asserted here are restated for 18.0 |
| **Odoo 19.0** | The baseline present in this repository: `version_info = (19, 0, 0, FINAL, 0, '')` in `odoo/release.py`, with `MIN_PY_VERSION = (3, 10)`, `MAX_PY_VERSION = (3, 13)` and `MIN_PG_VERSION = 13` | The field names, constraint messages and menu paths cited in this story hold as written; the account deactivation flag is `active`, rendered as the archive toggle, because the 19.0 `account.account` model carries no Deprecated field |

- [ ] **C-010 — the confirmed version is recorded** in the Epic and restated in the parent Feature before development starts; this story does not choose it.
- [ ] **C-011 — Python and PostgreSQL versions follow the confirmed target**, since each candidate release carries its own supported matrix.
- [ ] **Edition source (DEC-002) does not gate this story.** The capability is served by `account` and the `l10n_*` packs, both present here under LGPL-3. The edition decision governs which engine renders the Trial Balance and Balance Sheet this story is verified through, which is why the group roll-up is expressed as data on `account.group` rather than against one report engine's internals.

### Accounting Standards Compliance

- [ ] **IAS 1 — Presentation of Financial Statements.** The current-versus-non-current split is carried by the `account_type` value together with the account's position in the group hierarchy, so a Balance Sheet section order is derived from the chart rather than re-entered per report.
- [ ] **ASC 210 — Balance Sheet classification.** The same ten codes resolve to US GAAP balance-sheet captions for the group's US entities, with cost (1500) and accumulated depreciation (1590) presented as separate lines rather than netted in the ledger.
- [ ] **Audit traceability.** `code`, `name` and `account_type` are tracked fields, so every change to a code or a classification is retained with its author and timestamp and is readable by the External Auditor without a data request; each statement line traces to an account and from there to its `account.move.line` detail.
- [ ] **One classification per account.** Every account resolves to exactly one group and one `account_type`, which is the property that makes the presentation mapping in [STORY-001-01-02](./STORY-001-01-02-map-accounts-ifrs-gaap-taxonomy.md) unambiguous.

---

## Technical Discovery Notes

> **Purpose:** these notes direct the codebase analysis that precedes implementation. This story states WHAT structure finance needs and WHY; the module structure, the choice between extending a model and adding one, and the view architecture emerge from discovery and are deliberately not prescribed here.

### Codebase Analysis Areas

| Area | Files/Modules to Examine | Analysis Focus |
|------|--------------------------|----------------|
| Account model and its type taxonomy | `addons/account/models/account_account.py` | The nineteen-value `account_type` selection and which of the ten baseline codes maps to which value; `code` as a `Char(64)` whose value is company-dependent; `currency_id` (Account Currency), `reconcile` (Allow Reconciliation), `include_initial_balance` (Bring Accounts Balance Forward), `company_ids`, `tag_ids` and the computed `group_id` and `internal_group` |
| Receivable-and-payable reconciliation constraint | `addons/account/models/account_account.py` | The constraint that refuses a receivable or payable account with reconciliation switched off, and what it implies for the configuration order of codes 1200 and 2000 |
| Account group hierarchy | `addons/account/models/account_account.py` (the `account.group` model) | `parent_id`, `name`, `code_prefix_start`, `code_prefix_end`, `company_id`; the ordering on `code_prefix_start`; the equal-length prefix constraint; the same-granularity overlap constraint; the recursion guard; and the routine that attaches each group to its most specific parent, which is the mechanism the three-level design relies on |
| Per-company code divergence | `addons/account/models/account_code_mapping.py` | Whether one account can carry a different statutory code per company, what the uniqueness check does across parent and child companies, and how a report that groups on code behaves when the code differs by company |
| Chart instantiation | `addons/account/models/chart_template.py`, `addons/account/models/template_generic_coa.py`, the 209 `addons/l10n_*` packs | What a chart template creates — accounts, groups, taxes, fiscal positions, journals — what a country pack adds on top, and how either behaves against a company that already holds postings |
| Tagging surface reserved for the sibling story | `addons/account/models/account_account_tag.py` | The `applicability` selection that separates account tags from tax and product tags, so this story leaves the tag structure to STORY-001-01-02 without foreclosing it |
| Journal baseline | `addons/account/models/account_journal.py` | The journal `type` selection — Sales, Purchase, Cash, Bank, Credit Card, Miscellaneous — and the sequence and default accounts each journal type needs per company |
| Company and currency context | `odoo/addons/base/models/res_company.py`, `odoo/addons/base/models/res_currency.py` | The parent-and-subsidiary structure the chart is applied across, the functional currency per company, and the decimal precision every monetary assertion is rounded to |
| Multi-company sharing rules | `addons/account/models/account_account.py` (the company-consistency constraint) | Which account may be shared across `company_ids` and which may not: the constraint refuses a Bank and Cash (`asset_cash`) account shared between companies, and refuses to unlink a company while journal items of that company reference the account. This is why the multi-company criterion in Scenario 5 is asserted on 2000 Accounts Payable rather than on 1010 Bank, and it fixes the structure the subsidiary charts have to follow |
| Report grouping already present | `addons/account_financial_report_ce/models/trial_balance.py`, `balance_sheet.py`, `general_ledger.py` | How the present AGPL-3 implementations group their lines. Their hierarchy mode groups on the internal account group rather than on `account.group` prefixes, so discovery decides whether the group subtotal asserted in Scenario 2 is rendered from `account.group` or from `internal_group`, and confirms that a change of hierarchy does not silently move an existing statement line |

### Relevant Existing Modules

- `addons/account/` — "Invoicing", version 1.4, licence LGPL-3. Supplies every model this story configures: `account.account`, `account.group`, `account.journal`, `account.move`, `account.move.line` and `account.code.mapping`.
- `addons/l10n_*/` — 209 localization packs present in this repository. Each supplies one jurisdiction's statutory chart of accounts, statutory codes and statutory presentation, which the group policy reconciles against; the pack per operating country is selected during localization discovery (D-006).
- `addons/analytic/` — analytic accounts and plans, the second dimension alongside the general-ledger account. Relevant here only where a baseline account is expected to carry an analytic distribution, and consumed mainly by FEATURE-001-09.
- `addons/account_financial_report_ce/` — version 19.0.1.1.0, AGPL-3. The Trial Balance, Balance Sheet and General Ledger implementations already present, and the reference point for how this story's structure reaches a statement line while DEC-002 is open.
- `odoo/addons/base/` — `res.company` and `res.currency`, which supply the company hierarchy and the currency decimal precision the monetary assertions are rounded to.

### OCA Module Compatibility

| OCA Repository | Module | Compatibility Consideration |
|----------------|--------|-----------------------------|
| OCA/account-financial-reporting | `account_financial_report` | Renders the General Ledger, Trial Balance and Balance Sheet from account types and hierarchy; determine whether the group structure defined here feeds it without a translation layer under the OCA path of DEC-002 |
| OCA/account-financial-tools | `account_chart_update` | Compares an installed chart against its country template and applies template changes; determine whether it is the mechanism that keeps a statutory chart reconciled to its pack, and how it behaves where the group policy diverges from the template on purpose |
| OCA/mis-builder | `mis_builder` | Builds management statements from account code expressions rather than from types; determine how stable the ten-code baseline has to be for those expressions, and how a per-company code mapping affects them |

The decision to integrate, extend or replace any add-on above belongs to DEC-002 in the Epic and is not taken in this story.

---

## Dependencies

### Story Dependencies

| Dependency Type | Story / Feature ID | Title | Relationship |
|-----------------|--------------------|-------|--------------|
| Parent Feature | [FEATURE-001-01](../FEATURE-001-01-chart-of-accounts-fiscal-year.md) | Chart of Accounts & Fiscal Year | This story is the first of the feature's five stories and delivers its capability CAP-001 |
| **Blocked By** | **None** | — | **This story has no predecessor.** It needs only module `account` and one company record, so it can be delivered before every other ticket in EPIC-001 |
| Blocks | [STORY-001-01-02](./STORY-001-01-02-map-accounts-ifrs-gaap-taxonomy.md) | Map Accounts to IFRS and GAAP Reporting Taxonomy | A presentation tag is attached to an account record, so the ten accounts exist before the taxonomy is mapped onto them |
| Blocks | [STORY-001-01-04](./STORY-001-01-04-import-legacy-coa.md) | Import Legacy Chart of Accounts and Opening Balances | The opening entry needs the target codes established here to debit and credit, and the legacy mapping needs them as its destination |
| Related | [STORY-001-01-03](./STORY-001-01-03-define-fiscal-year-periods.md) | Define Fiscal Year and Accounting Periods | The fiscal calendar is configured on the company and can be built alongside this story; the entry posted in Scenario 2 lands in a period that story defines |
| Related | [STORY-001-01-05](./STORY-001-01-05-configure-period-lock-dates.md) | Configure Period Lock Dates and Closing Controls | Lock dates protect the periods these accounts are posted into, and the re-code case in Edge Case 5 is constrained by them once a period is locked |
| Downstream features | FEATURE-001-02, FEATURE-001-03, FEATURE-001-04, FEATURE-001-07, FEATURE-001-08, FEATURE-001-09 | — | Every posting and reporting story consumes these codes — Accounts Payable 2000 and Expense 6100 for vendor bills, Accounts Receivable 1200 and Revenue 4000 for customer invoices, Bank 1010 for reconciliation, Fixed Assets 1500 and Accumulated Depreciation 1590 for the asset register — under ordering rule ORD-001 in the Epic's [§6.2](../../EPIC-001-enterprise-accounting-odoo.md#62-inter-feature-ordering) |

### External Dependencies

| Dependency | Type | Notes |
|------------|------|-------|
| Group chart-of-accounts policy | Governance artifact | Owned by the Group Controller and approved before the chart is released; it is the authority the ten codes and the prefix ranges are drawn from |
| Country localization pack per operating country | Odoo module (`l10n_*`) | 209 packs are present here; the pack per country supplies the statutory chart this policy reconciles against, and each divergence is recorded as a per-company account code mapping (D-006) |
| Legal-entity register | Master data | Acme Group NV and Acme Industries Inc. exist as company records with their functional currency set before the chart is applied to them |
| Exchange-rate source | Master data / integration | Supplies the 1 EUR = 1.1000 USD rate that Scenario 6 translates at, and the decimal precision of 2 places per currency that every amount is rounded to |
| Platform version and edition confirmation | Open decision (DEC-001, DEC-002) | Recorded in the Epic's [Open Decisions Register](../../EPIC-001-enterprise-accounting-odoo.md#appendix-b-open-decisions-register); DEC-001 fixes the field and view names this story is implemented against, and DEC-002 fixes which engine renders the Trial Balance it is verified through |
| IAS 1 and ASC 210 | Accounting standard | Fix the presentation classification each `account_type` value has to support |

### Integration Points

| Odoo Model | Integration Type | Purpose |
|------------|------------------|---------|
| `account.account` | Define and extend | The ten baseline codes with their `account_type`, `company_ids`, Account Currency and Allow Reconciliation values |
| `account.group` | Define | The three-level hierarchy whose `code_prefix_start`-to-`code_prefix_end` ranges roll every code up to a statement section |
| `account.journal` | Define | The five journal types per company — `sale`, `purchase`, `bank`, `cash` and `general` — that entries against these accounts are routed through |
| `res.company` | Read | Acme Group NV and Acme Industries Inc., their parent-and-subsidiary relationship and their functional currency |
| `account.move.line` | Read | The journal items whose debit and credit totals the Trial Balance assertions in Scenarios 2, 4, 5 and 6 are read from, and the records whose presence blocks the deletion in Scenario 4 |
| `account.move` | Read | The verification entries posted during acceptance, each proved balanced before its totals are read back |
| `account.code.mapping` | Write | The per-company statutory code divergence recorded against one account rather than duplicated as a second account |
| `res.currency` | Read | The `USD` and `EUR` definitions and the 2-decimal precision every monetary assertion is rounded to |
| `account.fiscal.position` | Read | Confirms that the tax base and tax control accounts a fiscal position selects — Tax Payable 2200 among them — exist before FEATURE-001-05 maps onto them |

---

## Estimation

| Dimension | Rating | Basis |
|-----------|--------|-------|
| **Effort** | Medium | Nine account groups, ten accounts with one `account_type` each, two Allow Reconciliation flags and five journal types, made repeatable per company and covered by six acceptance tests plus four negative tests |
| **Complexity** | Medium | The prefix ranges have to partition the code space so that every code resolves to exactly one most-specific group, and the per-company code mapping and multi-company sharing paths both have to hold; each mechanism is supplied by existing Odoo models rather than invented here |
| **Uncertainty** | Low | Every field, constraint and message this story relies on is present in the repository and was read during discovery; the residual unknown is whether the group subtotal is rendered from `account.group` or from the internal group, which is a reporting question that does not change the structure delivered |
| **Story Points** | **5** (Fibonacci: 1, 2, 3, 5, 8, 13) | |

Five points reflects breadth against low technical risk. The configuration itself is shallow — no new posting logic, no integration, no migration — but it is broad: ten codes, nine groups, five journal types, two companies and four refusal paths all have to be demonstrated, and the assertions have to hold in a second company before the story is accepted. Three points would understate the number of distinct outcomes proved; eight would overstate a story with no unresolved technical decision, since each mechanism it uses already exists in `account`. The estimate assumes the group policy is approved by the Group Controller during the sprint, and it excludes the taxonomy tagging, the fiscal calendar, the legacy load and the lock-date administration, which are the four sibling stories.

---

## Test Requirements

### Coverage Requirement

| Metric | Requirement | Notes |
|--------|-------------|-------|
| **Minimum Test Coverage** | **80%** | Mandatory for all new functionality delivered by this story (C-007) |
| Unit Test Coverage | 80% or higher | Group-to-code resolution, `account_type` assignment, reconciliation flag defaults, per-company code behaviour |
| Integration Test Coverage | 80% or higher | Posting into the baseline accounts, Trial Balance grouping and totals, multi-company sharing |
| Accounting assertion style | Numeric | Every monetary and balance assertion is compared as an amount at 2 decimal places with half-up rounding, never inspected by eye (C-009) |
| Traceability | One test per criterion | Each of the six scenarios maps to exactly one named acceptance test (C-008) |

### Unit Test Scenarios

| Acceptance Scenario | Unit Test Focus | Key Assertions |
|---------------------|-----------------|----------------|
| Scenario 1 | Account and group creation from the policy | Ten accounts exist; each `account_type` equals its baseline value; each account's group is the most specific one whose prefix range contains its code; groups `10`, `12`, `15` resolve to `1 Assets` and `20`, `22` to `2 Liabilities`; the untyped count is 0; Allow Reconciliation is enabled on 1200 and 2000 |
| Scenario 2 | Group roll-up computation | Group `1 Assets` debit subtotal equals USD 10,000.00 and group `3 Equity` credit subtotal equals USD 10,000.00 at 2 decimal places with half-up rounding; the report's total debits equal its total credits with a difference of USD 0.00 |
| Scenario 3 | Uniqueness and required-field validation | Saving a second account with code `1010` in Acme Group NV raises a validation error naming the code; saving with an empty `account_type` raises a required-field error; the account count stays at ten in both cases |
| Scenario 4 | Deletion guard | Deleting account 1200 while `account.move.line` records reference it raises the journal-items error; the record still exists; its debit balance still equals USD 48,750.00 at 2 decimal places with half-up rounding |
| Scenario 5 | Multi-company sharing | Adding Acme Industries Inc. to `company_ids` of account 2000 leaves the Acme Group NV balance at USD 312,480.00 credit and yields USD 0.00 with 0 journal items in Acme Industries Inc., at 2 decimal places with half-up rounding |
| Scenario 6 | Foreign-currency translation | Account 1015 carries Account Currency `EUR`; the journal item retains EUR 1,000.00; the reported figure equals USD 1,100.00 at the 1.1000 rate, rounded to 2 decimal places with half-up rounding, and the report's total debits equal its total credits |

### Integration Test Considerations

- [ ] Post the Scenario 2 entry through `account.move` and `account.move.line` and assert the posted entry's total debits equal its total credits at a difference of USD 0.00 before the Trial Balance is read.
- [ ] Run the Trial Balance for the date range 01 January 2026 to 31 January 2026 and reconcile each reported group subtotal to the sum of the `account.move.line` records beneath it at a difference of USD 0.00.
- [ ] Exercise the chart against a second company, Acme Industries Inc., and assert that a role restricted to one company can neither read nor post the other company's journal items (C-014).
- [ ] Install one `l10n_*` localization pack into a test company and assert that every statutory code either matches the group policy or is recorded as a per-company account code mapping, with no parallel chart created.
- [ ] Assert that the five journal types exist per company with their own sequences and default accounts, and that an entry routed through the Miscellaneous journal reaches the baseline accounts.
- [ ] Re-run the Balance Sheet and the Trial Balance after the Edge Case 5 re-code and assert that no statement line moved other than the re-coded account, and that total debits still equal total credits at a difference of USD 0.00.

### Acceptance Test Mapping

| BDD Scenario | Test Method Name | Test Type |
|--------------|------------------|-----------|
| Scenario 1: Ten baseline accounts created under the account-group hierarchy | `test_baseline_accounts_created_under_group_hierarchy` | Acceptance |
| Scenario 2: Group roll-up proved on the Trial Balance | `test_group_rollup_subtotals_on_trial_balance` | Acceptance |
| Scenario 3: Duplicate account code and missing account type both refused | `test_duplicate_code_and_missing_account_type_refused` | Acceptance |
| Scenario 4: Deletion of an account carrying journal items is blocked | `test_delete_account_with_journal_items_blocked` | Acceptance |
| Scenario 5: Payable account shared with the subsidiary company | `test_payable_account_shared_with_subsidiary_company` | Acceptance |
| Scenario 6: Foreign-currency bank account reported at the closing rate | `test_foreign_currency_account_translated_at_closing_rate` | Acceptance |

---

## Definition of Done

### Implementation Checklist

- [ ] All six acceptance-criteria scenarios pass, each proved by its named automated test in § Acceptance Test Mapping.
- [ ] **80% minimum test coverage achieved** for the functionality delivered by this story, reported by the repository's coverage tooling (C-007).
- [ ] Unit tests written and passing for group-to-code resolution, `account_type` assignment, the reconciliation-flag constraint on 1200 and 2000, and per-company code behaviour.
- [ ] Integration tests written and passing for posting into the baseline accounts, Trial Balance grouping, multi-company sharing and localization-pack reconciliation.
- [ ] The four negative paths are covered by tests: duplicate code, empty `account_type`, deletion of an account carrying journal items, and an overlapping group prefix range.
- [ ] The ten codes, nine groups and five journal types are reproducible in a second company without hand-editing, and were reproduced in Acme Industries Inc. during verification.

### Accounting Reconciliation Gate

This gate is the accounting contract of the story. Each item is asserted as an amount, at 2 decimal places using half-up rounding, in the currency named.

- [ ] **Debits equal credits on every entry posted during verification.** Each verification entry — including the Scenario 2 entry of USD 10,000.00 and the Scenario 6 entry of EUR 1,000.00 translated to USD 1,100.00 — posts with total debits equal to total credits and a difference of USD 0.00.
- [ ] **Trial Balance balances for the reported range.** The Trial Balance for Acme Group NV over 01 January 2026 to 31 January 2026 reports total debits equal to total credits at a difference of USD 0.00, and the same assertion holds for Acme Industries Inc. over the same range.
- [ ] **Report lines tie to the sub-ledger.** Every Trial Balance and Balance Sheet line, and every group subtotal, equals the sum of the `account.move.line` records beneath it at a difference of USD 0.00 — group `1 Assets` at USD 10,000.00 debit and group `3 Equity` at USD 10,000.00 credit for the verification range.
- [ ] **Tax amounts tie to their tax lines.** Where a verification entry carries tax, its tax code, base amount and tax amount are recorded separately, and the tax amount equals the movement on the tax control account Tax Payable 2200 for the same date range at a difference of USD 0.00.
- [ ] **No unexplained suspense balance.** Every suspense or clearing account in the chart reports USD 0.00 for the verification range, or its balance is explained in a retained reconciliation (SM-006).
- [ ] **Contra-asset presentation preserved.** Account 1500 Fixed Assets and account 1590 Accumulated Depreciation are presented on separate lines, and their group subtotal equals the arithmetic net of the two balances at a difference of USD 0.00.

### Compliance Checklist

- [ ] Licence compatibility verified per C-001 and C-002: an AGPL-3.0 compatible licence declared, and the LGPL-3 licence of `account` respected by every derived work.
- [ ] No parallel accounting model introduced; the chart, hierarchy and journal set live on `account.account`, `account.group` and `account.journal` (C-012).
- [ ] Multi-company record rules exercised by test: a role restricted to Acme Group NV can neither read nor post the journal items of Acme Industries Inc. (C-014).
- [ ] Static analysis passes with the repository's configured tooling at zero violations, and the code follows Odoo and OCA standards (C-005, C-006).
- [ ] The confirmed platform version and edition, once DEC-001 and DEC-002 are recorded, are restated in the parent Feature and the field names asserted here are re-checked against them.
- [ ] Code reviewed and approved, with the group policy countersigned by the Group Controller.

### Documentation Checklist

- [ ] Docstrings and inline comments complete for every public method delivered.
- [ ] The group chart-of-accounts policy — the ten codes, their `account_type` values, the nine group ranges and the five journal types — is recorded alongside the code that applies it.
- [ ] The reconciliation of each in-scope `l10n_*` statutory chart to the group policy is documented per country, with every divergence recorded as a per-company account code mapping.
- [ ] Finance-facing configuration notes updated so the Chief Accountant can add an account without breaching the prefix ranges.
- [ ] The account-retirement path is documented: the deactivation flag rather than deletion, with the field name stated for the platform target DEC-001 confirms.

### Quality Checklist

- [ ] No critical or high-severity defect open against the chart, the hierarchy or the journal baseline.
- [ ] The Chart of Accounts view grouped on Group renders in under 3 seconds for a chart of 2,000 accounts, the parent Feature's performance target for this structure.
- [ ] Access rights verified per finance role: the Chief Accountant maintains the chart, the Group Controller approves the policy, and the External Auditor holds read-only access to accounts and entries.
- [ ] Every change to `code`, `name` and `account_type` is retained with its author and timestamp and is readable by the External Auditor without a data request.
- [ ] **Demonstrated in the Odoo user interface to the Finance Controller and the Product Owner** by walking the five steps of § Demonstration — Chart of Accounts, Account Groups, the posted Scenario 2 entry, the Trial Balance for 01 January 2026 to 31 January 2026, and the two refusals — with the walkthrough recorded against this story.

---

## References

### Accounting Standards

| Standard | Reference | Application to This Story |
|----------|-----------|---------------------------|
| IAS 1 | Presentation of Financial Statements, IFRS Foundation | The current-versus-non-current split the `account_type` value and the group hierarchy carry together, so a Balance Sheet section order is derived from the chart |
| ASC 210 | FASB Accounting Standards Codification, Balance Sheet | US GAAP balance-sheet classification of the same ten codes, with cost (1500) and accumulated depreciation (1590) presented separately |
| IFRS Foundation standards | <https://www.ifrs.org/issued-standards/list-of-standards/> | The presentation taxonomy the sibling story STORY-001-01-02 maps these accounts onto |
| FASB Accounting Standards Codification | <https://asc.fasb.org/> | The US GAAP classification carried as the second presentation dimension on each account |

### OCA Modules (Reference)

| Repository | Module | Relevance |
|------------|--------|-----------|
| OCA/account-financial-reporting | `account_financial_report` | Consumes account types and hierarchy to render the General Ledger, Trial Balance and Balance Sheet |
| OCA/account-financial-tools | `account_chart_update` | Keeps an installed chart reconciled with its country template |
| OCA/mis-builder | `mis_builder` | Builds management statements from account code expressions, which depend on the stability of the ten-code baseline |

### Source Code References

| Path | Relevance |
|------|-----------|
| `addons/account/models/account_account.py` | `account.account` with `code`, `name`, the nineteen-value `account_type` selection, `currency_id`, `reconcile`, `include_initial_balance`, `company_ids`, `tag_ids`, `group_id` and `internal_group`; the receivable-and-payable reconciliation constraint; the account-code uniqueness check across parent and child companies; the deletion guard for accounts carrying journal items; and the `account.group` model with `parent_id`, `code_prefix_start`, `code_prefix_end`, `company_id`, the equal-length prefix constraint, the same-granularity overlap constraint and the parent-attachment routine |
| `addons/account/models/account_code_mapping.py` | `account.code.mapping`, the per-company account code divergence recorded against a single account |
| `addons/account/models/chart_template.py`, `addons/account/models/template_generic_coa.py` | How a chart template is instantiated into a company and what it creates |
| `addons/account/models/account_account_tag.py` | `account.account.tag` and its applicability selection, reserved for STORY-001-01-02 |
| `addons/account/models/account_journal.py` | The journal `type` selection — Sales, Purchase, Cash, Bank, Credit Card, Miscellaneous — behind the five-journal baseline |
| `addons/account/views/account_account_views.xml`, `addons/account/views/account_group_views.xml`, `addons/account/views/account_menuitem.xml` | The Chart of Accounts action and its Configuration menu path, the account-group form, list and search views, and the Group column used in the demonstration |
| `addons/account/__manifest__.py` | The `account` module identity cited throughout: "Invoicing", version 1.4, category `Accounting/Accounting`, licence LGPL-3 |
| `addons/l10n_*/` | The 209 localization packs supplying each jurisdiction's statutory chart of accounts |
| `addons/account_financial_report_ce/models/trial_balance.py` | The AGPL-3 Trial Balance implementation present in this repository, with its date-range parameters and its hierarchy mode |
| `odoo/release.py` | The platform baseline `version_info = (19, 0, 0, FINAL, 0, '')` with `MIN_PY_VERSION = (3, 10)`, `MAX_PY_VERSION = (3, 13)` and `MIN_PG_VERSION = 13`, cited by DEC-001 |

### Ticket References

| Document | Link |
|----------|------|
| Parent Feature | [FEATURE-001-01: Chart of Accounts & Fiscal Year](../FEATURE-001-01-chart-of-accounts-fiscal-year.md) |
| Parent Epic | [EPIC-001: Enterprise Accounting in Odoo](../../EPIC-001-enterprise-accounting-odoo.md) |
| Persona register the WHO is drawn from | [EPIC-001 §3.1 User Personas](../../EPIC-001-enterprise-accounting-odoo.md#31-user-personas) |
| Success metric SM-006, which this story is measured on | [EPIC-001 §4.1 Measurable Outcomes](../../EPIC-001-enterprise-accounting-odoo.md#41-measurable-outcomes) |
| Authoring bounds: 4-to-8 criteria, coverage distribution, Fibonacci scale | [EPIC-001 §5.3 Decomposition Guidelines](../../EPIC-001-enterprise-accounting-odoo.md#53-feature-and-story-decomposition-guidelines) |
| Ordering rule ORD-001, which gates the posting features on this story | [EPIC-001 §6.2 Inter-Feature Ordering](../../EPIC-001-enterprise-accounting-odoo.md#62-inter-feature-ordering) |
| Constraint set C-001 to C-014 | [EPIC-001 §7 Constraints](../../EPIC-001-enterprise-accounting-odoo.md#7-constraints) |
| Open decisions DEC-001 and DEC-002 | [EPIC-001 Appendix B: Open Decisions Register](../../EPIC-001-enterprise-accounting-odoo.md#appendix-b-open-decisions-register) |
| Sibling stories | [STORY-001-01-02](./STORY-001-01-02-map-accounts-ifrs-gaap-taxonomy.md) · [STORY-001-01-03](./STORY-001-01-03-define-fiscal-year-periods.md) · [STORY-001-01-04](./STORY-001-01-04-import-legacy-coa.md) · [STORY-001-01-05](./STORY-001-01-05-configure-period-lock-dates.md) |

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-08-13 | Enterprise Accounting Team | Initial story creation |
| 1.1 | 2026-08-13 | Enterprise Accounting Team | Review remediation. Demonstrability section heading normalized to `## Demonstration Path`, the form used across all seventeen stories of this epic, so a reader arrives at the same section name in every story. Revision date aligned to the tree-wide authoring date. Trailing blank line removed at end of file. No acceptance criterion, fixture value or estimate changed |

---

## Notes

**Platform version and edition remain open (DEC-001, DEC-002).** The originating programme request names Odoo 17, this repository is Odoo 19.0 Community, and the prior superseded backlog targeted 18.0. This story states the field names, constraint messages and menu paths as they exist in the 19.0 baseline it was verified against, and flags the mismatch for stakeholder confirmation rather than choosing a target. Two concrete consequences are carried here: the account-retirement path is the flag labelled Deprecated in the Odoo 17 series and the `active` archive flag in 19.0, where `account.account` carries no Deprecated field; and the 209 `l10n_*` packs present here are 19.0-series, so an earlier target changes which pack supplies each statutory chart.

**Report engine for the verification reports (DEC-002).** The Trial Balance and Balance Sheet used to verify the roll-up in Scenario 2 and in the reconciliation gate are supplied by the Enterprise module `account_reports`, which is **absent** from this Community repository. An AGPL-3 Community implementation is present instead — `account_financial_report_ce` version 19.0.1.1.0, whose `account.trial.balance.report` model carries the date-range parameters this story cites — so the story is demonstrable today under the OCA path. Its hierarchy mode groups on the internal account group rather than on `account.group` prefixes, which is why the rendering question is recorded as a discovery item: the structure this story delivers is the same under either engine, and only the presentation of the group subtotal depends on the choice.

**Company names.** Acme Group NV (parent, functional currency `USD`) and Acme Industries Inc. (subsidiary) are the reference entities used across the criteria so that every multi-company assertion names the books it affects. They stand for the group's legal-entity register, which is enumerated during discovery; substituting the confirmed entity names changes the names in the criteria and nothing else.

**Scope of this ticket.** This file is a planning artifact. It states the account structure finance requires and the assertions that prove it; it contains no module, model, view or data definition, and it prescribes none. The mechanism — chart template, localization-pack reconciliation or configuration data — is chosen by the implementing agent from the discovery recorded above.
