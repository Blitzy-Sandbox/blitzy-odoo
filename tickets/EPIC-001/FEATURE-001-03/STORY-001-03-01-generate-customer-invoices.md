# STORY-001-03-01: Generate and Post Customer Invoices

---

## Metadata

| Attribute | Value |
|-----------|-------|
| **Story ID** | `STORY-001-03-01` |
| **Title** | Generate and Post Customer Invoices |
| **Parent Feature** | [FEATURE-001-03: Accounts Receivable & Customer Invoices](../FEATURE-001-03-accounts-receivable-customer-invoices.md) |
| **Parent Epic** | [EPIC-001: Enterprise Accounting in Odoo](../../EPIC-001-enterprise-accounting-odoo.md) |
| **Status** | Draft |
| **Priority** | 🔴 Critical |
| **Estimate** | 5 story points (Fibonacci) |
| **Persona** | Accounts Receivable Specialist |
| **Secondary Personas** | Chief Accountant (approves the balanced posting to Accounts Receivable 1200, Revenue 4000 and Tax Payable 2200 and administers the period lock date), Tax Accountant (owns the output tax code the fiscal position selects), Credit Controller (records the credit-limit override), Treasury Analyst (reads the receivable the invoice creates as a collections forecast), External Auditor (traces a posted invoice to its journal items), Finance Controller and Product Owner (accept the demonstration). Persona governance: the **Credit Controller** named above is a registered named secondary role rather than a thirteenth persona: the Epic's [§3.2](../../EPIC-001-enterprise-accounting-odoo.md#32-persona-notes) records it, and every other non-register role this feature names, as a stakeholder who reviews, approves or receives an outcome, never the WHO of a story, mapping onto the **Accounts Receivable Specialist** for access rights |
| **Story Position** | Story 1 of the 5 in FEATURE-001-03; blocks the other four |
| **Platform Target** | Open decision DEC-001 — see [Version Compatibility](#version-compatibility) |
| **Last Updated** | 2026-08-16 |
| **Owner/Author** | Enterprise Accounting Team |

> **Platform target.** This story fixes no platform version of its own. The target is the Epic's open decision **DEC-001** in the [Open Decisions Register](../../EPIC-001-enterprise-accounting-odoo.md#appendix-b-open-decisions-register): the originating programme request names Odoo 17, the superseded prior backlog named 18.0, and the baseline this story was written and verified against is **Odoo 19.0 Community**, where `odoo/release.py` declares `version_info = (19, 0, 0, FINAL, 0, '')`. The three candidate releases carry different `account.move` and `account.move.line` field surfaces and different lock-date administration, so the mismatch is surfaced for stakeholder confirmation rather than settled inside this story (AAP §0.8.2, §0.8.3).

---

## User Story

**As an** Accounts Receivable Specialist

**I want** to raise a customer invoice as an `account.move` record of type `out_invoice` — carrying its customer, its invoice lines, its currency, its payment term and its output tax code — and confirm it so that it posts through the **Sales** journal of the company whose books it belongs to, as one journal entry whose total debits equal its total credits

**So that** the receivable and the revenue it earns are recognised in the accounting period they belong to, the residual on the invoice is the amount the group is owed from the moment it posts, and the **Aged Receivable** report and the **Profit & Loss** statement are read from posted journal items rather than assembled from a spreadsheet — which is the condition Days Sales Outstanding must be measured under before the 15% to 25% improvement targeted by SM-017 against the 58.0-day baseline can be attributed to any collection action.

---

## Business Value

### Value Statement

> A customer invoice is the document that creates the receivable, recognises the revenue and records the output tax, and everything downstream in this feature settles, reduces, chases or reports the balance it leaves behind. When the invoice posts as a balanced entry — debit Accounts Receivable 1200, credit Revenue 4000 and credit Tax Payable 2200 — three figures become derivable instead of negotiable: what the group is owed, what it earned, and what it owes the tax authority. This story is therefore the first place in the programme where the ledger, not a spreadsheet, becomes the source of the receivable position. It is also the cheapest place to enforce the controls that protect it: an invoice that cannot post into a locked period cannot restate a reported result, an invoice whose line lacks an income account cannot land revenue in a suspense balance, and a customer whose exposure would pass the credit limit is surfaced to the Credit Controller before the receivable exists rather than after it has aged.

### Success Metrics

| Metric | Baseline | Target | Measurement Method |
|--------|----------|--------|--------------------|
| Invoice creation to posting, elapsed clerical time | Keyed into a spreadsheet, then re-keyed at month end | Under 2 minutes for a three-line invoice raised by the Accounts Receivable Specialist | Timed walkthrough of the Scenario 1 invoice, from record creation to the Posted state |
| Invoice posting time, system | Not measured | Under 3 seconds to confirm and post a 50-line customer invoice carrying output tax, matching the parent Feature's §4.4 budget | Timed confirmation of a seeded 50-line invoice in company `US-01` |
| Sequence-number coverage on posted invoices | Manual reference numbers, gaps unexplained | 100% of posted customer invoices carry a **Sales**-journal sequence number; the count of posted invoices with no sequence number is 0 | Query over the posted `out_invoice` population per company per period |
| Balanced-entry integrity | Unproven | 0 unbalanced posted invoice entries; total debits minus total credits asserted at `0.00` in the company's functional currency on every posted entry (SM-006, C-009) | Posted entry inspected line by line, with the difference asserted numerically |
| Output tax recorded as a separated triple | Tax embedded in one gross figure | 100% of posted invoice tax lines carry a tax code, a base amount and a tax amount as three separate values; the count with a null tax code or a null base amount is 0 | Tax-line completeness query over the posted invoice population for the period |
| Residual initialisation | Derived by hand at month end | `amount_residual` equals `amount_total` on 100% of invoices at the moment they post, at a difference of `0.00` in the invoice currency | Residual compared with the total on the posted population, before any receipt is allocated |
| Refused postings leave no trace | Partial documents posted and reversed | 100% of refused confirmations create no journal entry and consume no **Sales**-journal sequence number | Negative tests for the incomplete-line and locked-period paths, with the entry count and the sequence high-water mark asserted unchanged |
| Contribution to receivable visibility | Receivable position reconstructed monthly | The Accounts Receivable 1200 balance equals the sum of open invoice residuals at a difference of `0.00 USD` in `US-01`, which is the tie-out the **Aged Receivable** report of `STORY-001-03-05` depends on (SM-001) | Trial Balance compared with the sum of residuals for the same as-of date |
| Contribution to Days Sales Outstanding | DSO 58.0 days, computed quarterly from a manual extract | Posted due dates and residuals available continuously, so DSO is computed from the ledger and the 15% to 25% improvement to between 43.5 and 49.3 days becomes measurable (SM-017) | DSO computed from posted residuals and compared with the 58.0-day baseline |

### Business Rules

Rule identifiers carry the `AR-INV-BR-` prefix so that a rule of this story is unambiguous beside the rules of [STORY-001-03-02](./STORY-001-03-02-register-customer-payments.md), which uses `AR-PAY-BR-`, and so that the bare `BR-001` through `BR-005` identifiers stay reserved for the retired bank-reconciliation stories the Epic's [retirement map](../../EPIC-001-enterprise-accounting-odoo.md#appendix-c-legacy-retirement-and-migration-map) traces. No identifier below is issued anywhere else in the backlog.

| Rule ID | Rule | Consequence If Broken |
|---------|------|-----------------------|
| **AR-INV-BR-001** | A customer invoice posts only from the Draft state. A posted invoice is amended by a credit note under [STORY-001-03-03](./STORY-001-03-03-manage-customer-credit-notes.md) and never by editing the posted document | An edited posted invoice restates a reported period and breaks the audit trail the External Auditor reads |
| **AR-INV-BR-002** | The **Sales**-journal sequence number is assigned when the invoice posts, not when the record is created, and a refused confirmation consumes no number | Unexplained gaps in the invoice sequence are a statutory numbering defect in every jurisdiction that requires an unbroken invoice sequence, and the gap cannot be evidenced away afterwards |
| **AR-INV-BR-003** | Every invoice line carries an income account and a tax code before the invoice is confirmed; output tax posts to Tax Payable 2200 and never to Revenue 4000 | Revenue lands in a suspense balance, or tax is reported as revenue and the statutory return no longer ties to the tax control account |
| **AR-INV-BR-004** | The due date is derived from the customer's payment term held on `res.partner` — Net 30 on an invoice dated 2025-02-10 giving a due date of 2025-03-12 — and an invoice with no payment term is refused at confirmation | Aging buckets and the follow-up ladder measure from a date nobody agreed, so an invoice is chased early or late by construction |
| **AR-INV-BR-005** | An invoice whose accounting date falls on or before the journal-entry lock date of the company whose books it belongs to does not post into that closed period: `account.move._post` re-dates the entry to the last day of the first open period before the state becomes Posted, the invoice date stays as issued, and the change is recorded on the entry naming both the company and the lock date. Refusal is reserved for a change to an already-posted entry inside a locked period and for the tax lock, as [STORY-001-01-05](../FEATURE-001-01/STORY-001-01-05-configure-period-lock-dates.md) administers | A reported period is restated after it was filed, and the close of that period stops being reproducible |
| **AR-INV-BR-006** | `amount_residual` equals `amount_total` at the moment of posting. Reducing the residual is the business of [STORY-001-03-02](./STORY-001-03-02-register-customer-payments.md) and [STORY-001-03-03](./STORY-001-03-03-manage-customer-credit-notes.md), never of this story | The receivable position is overstated or understated from the first day of its life, and every downstream aging figure inherits the error |
| **AR-INV-BR-007** | Total debits equal total credits on every posted invoice entry, both totals stated and their difference asserted at `0.00` in the company's functional currency | An unbalanced entry cannot be presented in a Trial Balance and blocks the close for the whole company (SM-006) |
| **AR-INV-BR-008** | Every monetary figure is rounded half-up to 2 decimal places at its currency's 0.01 rounding precision, and the company's tax-rounding method is stated alongside a multi-line tax figure | A one-minor-unit divergence between the document total and the sum of its journal items is enough to fail the debits-equal-credits check |
| **AR-INV-BR-009** | A projected receivable balance above the customer's credit limit raises a warning that states the limit, the projected balance and the excess, and the invoice posts only once the Credit Controller records an override against it, retained with its author and timestamp | Credit exposure grows with no decision recorded anywhere, and the Treasury Analyst cannot show why an over-limit invoice was allowed |
| **AR-INV-BR-010** | Revenue is recognised in the period the performance obligation is satisfied, per ASC 606 and IFRS 15, so the invoice's accounting date governs the period rather than the date the document was keyed | Revenue is recognised in the wrong period, which is a restatement risk rather than a clerical one |

---

## Acceptance Criteria

Seven criteria, inside the mandated band of 4 to 8. Each carries one non-compound **When**, and each **Then** asserts only what the Accounts Receivable Specialist, the Chief Accountant, the Credit Controller or the External Auditor can observe on the document, on the journal entry or in a named report — no interface gesture, no query and no implementation internal appears in a criterion. Every monetary figure states its currency as an ISO 4217 code, its amount to 2 decimal places and the rounding rule applied to it; every tax assertion states the **tax code**, the **base amount** and the **tax amount** as three separate values; every journal entry described states its total debits and its total credits as equal amounts; and every criterion touching more than one company names the company whose books are affected.

| Scenario | Coverage class |
|----------|----------------|
| 1 | Valid input — happy-path posting with a balanced journal entry |
| 2 | Valid input — accounting determinism, the tax code, base amount and tax amount recorded as three separate values |
| 3 | Invalid or incomplete input — an invoice line missing its income account and its unit price |
| 4 | Behaviour branch — a confirmation into a locked period is re-dated into the first open period under the Epic's [lock-date behaviour contract](../../EPIC-001-enterprise-accounting-odoo.md#78-lock-date-behaviour-contract) row L-1, and the locked period receives 0 journal items |
| 5 | Accounting edge case — a zero-amount line together with foreign-currency tax rounding |
| 6 | Error handling — a credit-limit breach blocks the posting with a named warning, the invoice staying Draft and 0 journal entries created |
| 7 | Valid input — release under a recorded credit override, with the posted entry balanced and the override retained |

### Scenario 1: Post a customer invoice with a balanced journal entry

- **Given** a Draft customer invoice exists as an `account.move` record whose `move_type` is `out_invoice`, raised for customer **Northwind Trading** in the **Sales** journal of company `US-01` (the United States parent, functional currency USD), dated 2025-02-10, carrying the customer's payment term of Net 30 and three invoice lines of 7,200.00 USD, 3,750.00 USD and 1,500.00 USD that total a net amount of **12,450.00 USD**, each line pointed at Revenue 4000 and each carrying output tax code **`ST-CA-0800`** at 8%, so the invoice records a base amount of 12,450.00 USD, a tax amount of **996.00 USD** and an `amount_total` of **13,446.00 USD** — every amount in this criterion rounded half-up to 2 decimal places per the USD 0.01 rounding precision
- **When** the Accounts Receivable Specialist confirms the invoice
- **Then** the invoice state changes from Draft to Posted
  - **And** a **Sales**-journal sequence number is assigned to the invoice and is visible on the document
  - **And** one journal entry is created whose `account.move.line` records debit **Accounts Receivable 1200** 13,446.00 USD, credit **Revenue 4000** 12,450.00 USD and credit **Tax Payable 2200** 996.00 USD, so **total debits of 13,446.00 USD equal total credits of 13,446.00 USD** at a difference of 0.00 USD
  - **And** `amount_residual` on the posted invoice equals `amount_total` at 13,446.00 USD, because no receipt has been allocated to it
  - **And** the due date is 2025-03-12, derived from the customer's payment term of Net 30 against the invoice date of 2025-02-10
  - **And** the books of `US-01` are the only books affected, and every amount above is rounded half-up to 2 decimal places per the USD 0.01 rounding precision

### Scenario 2: Tax code, base amount and tax amount are reported as three separate values

- **Given** the posted customer invoice of Scenario 1 in company `US-01`, carrying output tax code **`ST-CA-0800`** at 8% on three lines that total a base amount of 12,450.00 USD, each amount rounded half-up to 2 decimal places per the USD 0.01 rounding precision
- **When** the Accounts Receivable Specialist opens the invoice's tax summary
- **Then** the summary presents one tax line showing tax code **`ST-CA-0800`**, base amount **12,450.00 USD** and tax amount **996.00 USD** as three distinct values, none of them combined into a gross figure
  - **And** the tax amount of 996.00 USD equals the base amount of 12,450.00 USD multiplied by 8%, rounded half-up to 2 decimal places per the USD 0.01 rounding precision, with the tax-rounding method in force on `US-01` stated alongside the figure
  - **And** that same tax amount of 996.00 USD is the balance posted to **Tax Payable 2200** by the entry of Scenario 1, so no part of the 996.00 USD reaches Revenue 4000
  - **And** the base amount of 12,450.00 USD equals the sum of the three revenue lines of 7,200.00 USD, 3,750.00 USD and 1,500.00 USD, each rounded half-up to 2 decimal places per the USD 0.01 rounding precision
  - **And** the tax code, the base amount and the tax amount stay readable from the posted journal items without reconstruction, so the External Auditor traces the triple from the tax summary to the ledger

### Scenario 3: An invoice carrying an incomplete line is not posted

- **Given** a Draft customer invoice as an `account.move` record of type `out_invoice` for customer Northwind Trading in the **Sales** journal of company `US-01`, whose first and third lines each carry a product, a quantity, a unit price and Revenue 4000, and whose **second line** carries a product and a quantity of 4.00 units but no income account and no unit price
- **When** the Accounts Receivable Specialist attempts to confirm the invoice
- **Then** the invoice remains in the Draft state
  - **And** no journal entry is created, so the balance of Accounts Receivable 1200 in `US-01` moves by 0.00 USD, rounded half-up to 2 decimal places per the USD 0.01 rounding precision
  - **And** no **Sales**-journal sequence number is consumed, so the sequence high-water mark of the **Sales** journal of `US-01` is unchanged and the next invoice that posts takes the number this attempt did not
  - **And** the returned message identifies the incomplete line by its line number — line 2 — and names the two missing elements, the income account and the unit price, so the Accounts Receivable Specialist resolves the document without inspecting every line
  - **And** the first and third lines retain the values that were entered, so the work already keyed is not discarded by the refusal

### Scenario 4: Confirming into a locked fiscal period moves the accounting date into the first open period

Odoo does not refuse this confirmation. `account.move._post` resolves the violated lock dates and moves the accounting date through `_get_accounting_date` to the last day of the first open period before the state becomes Posted, so the closed period is protected by where the invoice lands rather than by the confirmation failing. That is the behaviour asserted here, and it is why the criterion asserts the **posted accounting date** rather than a refusal — an assertion of refusal would pass review and fail against the platform. The same contract is stated in full by [STORY-001-01-05](../FEATURE-001-01/STORY-001-01-05-configure-period-lock-dates.md), which administers the boundary.

- **Given** the journal-entry lock date of company **Global Europe SARL** — the legal entity the Epic's canonical register ([Appendix E.4](../../EPIC-001-enterprise-accounting-odoo.md#e4-canonical-legal-entity-register)) holds against entity code `NL-01`, the Netherlands operating subsidiary whose functional currency is EUR — is set to 2025-03-31; a Draft customer invoice of type `out_invoice` for customer Atlantia SRL exists in the **Sales** journal of Global Europe SARL carrying an invoice date of 2025-03-15, which falls on or before that lock date; that journal's entry sequence resets monthly; and the confirmation is attempted after April 2025
- **When** the Accounts Receivable Specialist confirms the invoice
- **Then** the invoice moves to the Posted state carrying an accounting date of **2025-04-30**, the last day of the first period open after the lock date, rather than the 2025-03-15 it was drafted at
  - **And** the invoice date stays **2025-03-15** on the document as issued to the customer, so the commercial date and the accounting date are held apart rather than one overwriting the other
  - **And** the date change is recorded on the entry, naming the lock date **2025-03-31** and the affected company **Global Europe SARL**, so the Accounts Receivable Specialist can see which period the revenue landed in
  - **And** the locked period is untouched: the balance of **Accounts Receivable 1200** in Global Europe SARL for 2025-03-01 to 2025-03-31 moves by 0.00 EUR, rounded half-up to 2 decimal places per the EUR 0.01 rounding precision
  - **And** the entry that does post carries total debits equal to total credits at a difference of 0.00 EUR, and the movement it contributes to **Accounts Receivable 1200** appears in the period 2025-04-01 to 2025-04-30
  - **And** the books of Global Holdings Inc. (`US-01`) — the only other group entity in existence at the 2025-03-15 accounting date, since Global UK Ltd (`GB-01`) is incorporated on 2025-04-01 — are untouched by the confirmation: the count of journal items this invoice adds to `US-01` is **0** and the balances of **Accounts Receivable 1200**, **Revenue 4000** and **Tax Payable 2200** in `US-01` each move by **0.00 USD**. The entry itself is readable in **Global Europe SARL**, which is the company that posted it, and a role restricted to `US-01` can read neither that entry nor the invoice behind it (C-014, D-007)

### Scenario 5: A zero-amount line and foreign-currency tax rounding

- **Given** a Draft customer invoice of type `out_invoice` in **EUR** for customer **Atlantia SRL** in the **Sales** journal of company Global Europe SARL (`NL-01`), whose accounting date of 2025-04-30 falls after that company's journal-entry lock date of 2025-03-31, containing one line of **0.00 EUR** for a no-charge item pointed at Revenue 4000 and carrying the same governed output tax code **`VAT-21-S`** at 21% as every other line, so no line is confirmed without a tax code, and one line of **333.33 EUR** pointed at Revenue 4000 and carrying output tax code **`VAT-21-S`** at 21%, for which the untruncated tax computation is 69.9993 EUR
- **When** the Accounts Receivable Specialist confirms the invoice
- **Then** the tax amount posted to **Tax Payable 2200** is **70.00 EUR**, being 69.9993 EUR rounded half-up to 2 decimal places per the EUR 0.01 rounding precision, recorded against tax code **`VAT-21-S`** on a base amount of **333.33 EUR** as three separate values
  - **And** the zero-amount line is retained on the invoice rather than dropped, contributes **0.00 EUR** to the entry, and keeps both its income account and its tax code, so it stays part of the invoice-line population any later analysis reads and satisfies AR-INV-BR-003 without an exception: at tax code **`VAT-21-S`** it records a base amount of **0.00 EUR** and a tax amount of **0.00 EUR** as three separate values, and it is **not** coded to a zero-rate code, because `VAT-00-ZR` and `VAT-00-EX` in the register [TAX-REG-001](../FEATURE-001-05-tax-configuration-compliance.md#111-authoritative-tax-code-register-tax-reg-001) each require a non-zero base amount
  - **And** the journal entry records debit **Accounts Receivable 1200** 403.33 EUR against credit **Revenue 4000** 333.33 EUR and credit **Tax Payable 2200** 70.00 EUR, so **total debits of 403.33 EUR equal total credits of 403.33 EUR** at a difference of 0.00 EUR
  - **And** `amount_total` and `amount_residual` on the posted invoice both read 403.33 EUR
  - **And** the books of Global Europe SARL are the only books affected, and every amount above is rounded half-up to 2 decimal places per the EUR 0.01 rounding precision, with the tax-rounding method in force on that company stated alongside the tax figure

### Scenario 6: A credit-limit breach is surfaced before the invoice posts

- **Given** customer **Northwind Trading** carries a credit limit of **25,000.00 USD** recorded on its `res.partner` record in company `US-01` and holds an open receivable balance of **18,000.00 USD** against Accounts Receivable 1200, each amount rounded half-up to 2 decimal places per the USD 0.01 rounding precision
- **When** the Accounts Receivable Specialist confirms a further Draft customer invoice of type `out_invoice` for that customer with an `amount_total` of **13,446.00 USD**, which would take the customer's open receivable balance to **31,446.00 USD**
- **Then** a credit-limit warning is raised against the invoice stating the limit of **25,000.00 USD**, the projected balance of **31,446.00 USD** and the excess of **6,446.00 USD** as three separate values, each rounded half-up to 2 decimal places per the USD 0.01 rounding precision
  - **And** with no override recorded the invoice stays in the Draft state, no journal entry is created, and the balance of Accounts Receivable 1200 in `US-01` moves by 0.00 USD
  - **And** the customer's open receivable balance still reads 18,000.00 USD, so the warning is raised on a projection and not on a posted figure
  - **And** the warning discloses no stack trace, no file-system path and no credential (C-020)

The release of the invoice under an override is a second trigger and is asserted separately as Scenario 7.

### Scenario 7: An invoice released by a recorded credit override posts with its entry balanced

- **Given** the state Scenario 6 leaves, extended by one recorded authorization: customer **Northwind Trading** in company `US-01` holds an open receivable balance of **18,000.00 USD** against a credit limit of **25,000.00 USD**, the **Credit Controller** has already recorded an override against that invoice authorising the excess of **6,446.00 USD**, with its author and its timestamp retained, and the Draft customer invoice of type `out_invoice` with an `amount_total` of **13,446.00 USD** carries the credit-limit warning naming the excess of **6,446.00 USD**, each amount rounded half-up to 2 decimal places per the USD 0.01 rounding precision
- **When** the Accounts Receivable Specialist confirms that invoice
- **Then** the invoice moves to the Posted state, the line records output tax code **`ST-CA-0800`**, a base amount of **12,450.00 USD** and a tax amount of **996.00 USD** as three separate values, and the entry records debit **Accounts Receivable 1200** 13,446.00 USD against credit **Revenue 4000** 12,450.00 USD and credit **Tax Payable 2200** 996.00 USD, so **total debits of 13,446.00 USD equal total credits of 13,446.00 USD** at a difference of 0.00 USD
  - **And** the override is retained with its author, its timestamp and the excess amount of **6,446.00 USD** it authorised, and admits no edit and no deletion, so the External Auditor reads who released the exposure without a data request
  - **And** the customer's open receivable balance after posting reads **31,446.00 USD**, which is the figure the Treasury Analyst reads as exposure against the **25,000.00 USD** limit
  - **And** the credit limit on the `res.partner` record is unchanged at **25,000.00 USD**, so an override releases one invoice rather than raising the limit
  - **And** every amount in this criterion is rounded half-up to 2 decimal places per the USD 0.01 rounding precision

---

## Sub-Tasks

- [ ] Confirm the invoice-line-to-account mapping with the Chief Accountant and record it: which product and line categories reach **Revenue 4000**, which control account carries the receivable (**Accounts Receivable 1200**), and which account receives output tax (**Tax Payable 2200**) — then sign the mapping off against the Trial Balance presentation the close depends on — `@finance-sme`
- [ ] Specify the Draft-to-Posted transition: the completeness checks that run at confirmation (customer, payment term, currency, at least one line, an income account and a tax code on every line), the wording of each refusal message including the line number it names, and the point at which the **Sales**-journal sequence number is consumed — `@functional-consultant`
- [ ] Specify the credit-limit control: where the limit is held on `res.partner`, how the projected balance and the excess are presented as three separate values, what the Credit Controller's override record carries (author, timestamp, authorised excess) and how long it is retained — `@functional-consultant`
- [ ] Deliver the posting behaviour: the balanced entry across Accounts Receivable 1200, Revenue 4000 and Tax Payable 2200; the initialisation of `amount_residual` to `amount_total`; the derivation of the due date from the payment term; and half-up rounding to 2 decimal places at each currency's 0.01 rounding precision on every amount written to a journal item — `@developer`
- [ ] Deliver the refusal path so that an incomplete line leaves the invoice in Draft with no journal entry created and no sequence number consumed, and the lock-date path so that an accounting date inside a locked period is re-dated to the last day of the first open period with the change recorded on the entry, each message or recorded note naming the failing element or the lock date and the company without disclosing a stack trace, a file path or a credential (C-020) — `@developer`
- [ ] Deliver the deterministic fixtures this story is demonstrated from — customer Northwind Trading in `US-01` with its 25,000.00 USD credit limit and Net 30 term, customer Atlantia SRL in Global Europe SARL (`NL-01`), output tax codes **`ST-CA-0800`** and **`VAT-21-S`**, and the 2025-03-31 lock date — held apart from the hostile-input fixtures so a hostile record is never mistaken for sample data (D-009) — `@developer`
- [ ] Author the tests for all seven acceptance criteria: the balanced-entry assertion with both totals compared numerically, the tax triple, the 69.9993-to-70.00 EUR rounding case, the zero-amount line carrying tax code `VAT-21-S` on a base of 0.00 EUR, the incomplete-line refusal, the re-dating into the first open period, the credit-limit warning that blocks the posting, and the release under a recorded override — mapping one test to one criterion (C-008) and linting every criterion for banned vague terms — `@qa-engineer`
- [ ] Validate the posted entry against the ledger: agree the Scenario 1 entry to the Trial Balance of `US-01`, and agree the sum of open invoice residuals to the Accounts Receivable 1200 balance at a difference of `0.00 USD`, which is the tie-out the **Aged Receivable** report of `STORY-001-03-05` inherits — `@finance-sme`

---

## Edge Cases

| Edge Case | Expected Behaviour |
|-----------|--------------------|
| **Zero-amount invoice line.** A line priced at 0.00 EUR for a no-charge item sits alongside chargeable lines on the same invoice | The line is retained on the invoice rather than dropped, keeps its income account and its tax code, and contributes 0.00 EUR to the journal entry. The entry still balances: total debits of 403.33 EUR equal total credits of 403.33 EUR at a difference of 0.00 EUR, rounded half-up to 2 decimal places per the EUR 0.01 rounding precision. A zero-amount line is never a silent deletion, because the no-charge item is part of what was delivered and the customer document must show it (Scenario 5) |
| **Confirming into a locked fiscal period.** An invoice with an invoice date of 2025-03-15 is confirmed after the journal-entry lock date of Global Europe SARL (`NL-01`) has been set to 2025-03-31 | The invoice posts with its **accounting date moved to 2025-04-30**, the last day of the first open period, while its invoice date stays 2025-03-15 as issued; the date change is recorded on the entry naming the lock date 2025-03-31 and the company Global Europe SARL; the Accounts Receivable 1200 balance of that company for 2025-03-01 to 2025-03-31 moves by 0.00 EUR and the movement appears in April instead. Re-dating is what the platform does rather than what a finance role chooses — `account.move._post` performs it before the state becomes Posted — so the control that matters is asserting the posted accounting date and reading the recorded change; where the document has to stay in March the boundary is released first through a recorded lock exception retained with its author, its timestamp and its expiry for the External Auditor (Scenario 4) |
| **Foreign-currency tax that rounds on the half-minor-unit.** A line of 333.33 EUR at output tax code `VAT-21-S` (21%) computes an untruncated tax of 69.9993 EUR, and the parent Feature's worked United States case computes 634.375 USD on a base of 8,750.00 USD | The posted tax amount is 70.00 EUR — 69.9993 EUR rounded half-up to 2 decimal places per the EUR 0.01 rounding precision — and 634.38 USD on the United States case under the same half-up rule at the USD 0.01 rounding precision. The company's tax-rounding method is stated alongside the figure, because rounding once per tax and rounding once per line can differ by one minor unit on a multi-line document, and a one-minor-unit divergence is enough to fail the debits-equal-credits check. Where the invoice currency differs from the company's functional currency, the transaction amount, the converted amount, the conversion rate and the rate date are each recorded, and both amounts are rounded half-up at their own currency's 0.01 rounding precision |
| **Customer whose exposure would pass the credit limit.** Northwind Trading holds an open receivable of 18,000.00 USD against a credit limit of 25,000.00 USD when an invoice of 13,446.00 USD is confirmed | A warning states the limit of 25,000.00 USD, the projected balance of 31,446.00 USD and the excess of 6,446.00 USD as three separate values, each rounded half-up to 2 decimal places per the USD 0.01 rounding precision. The invoice is neither posted silently nor blocked silently: it posts once the Credit Controller records an override retained with author, timestamp and the authorised excess, and it stays in Draft with no journal entry while no override exists. The projected balance of 31,446.00 USD is the exposure figure the Treasury Analyst then reads against the limit (Scenario 6) |

---

## INVEST Principles Compliance

| Principle | Compliance | Justification |
|-----------|------------|---------------|
| **Independent** | ✅ | This story stands alone: everything it needs is a chart of accounts holding Accounts Receivable 1200, Revenue 4000 and Tax Payable 2200, a **Sales** journal, an open fiscal period and one output tax code — all satisfiable as demo data in a test company. It **blocks** the other four stories of FEATURE-001-03 and is **blocked by** none of them, because a receipt, a credit note, a follow-up level and an aging bucket each need a posted receivable while a posted receivable needs none of them |
| **Negotiable** | ✅ | The criteria state the accounting outcome required — a balanced entry across three named accounts, a separated tax triple, a residual equal to the total, a named refusal — and leave the model, field, view and method decisions to implementation discovery under D-005, so how the outcome is reached stays open for negotiation between the Accounts Receivable Specialist and the delivery team |
| **Valuable** | ✅ | It is the story that creates the receivable and recognises the revenue, so it is the precondition of every figure this feature reports: the Accounts Receivable 1200 tie-out behind SM-001, and the posted due dates and residuals that make the SM-017 improvement from 58.0 days to between 43.5 and 49.3 days measurable at all |
| **Estimable** | ✅ | The artifact count is fixed and inspectable: one document type (`out_invoice`), one journal (**Sales**), three general ledger accounts, two output tax codes, two companies, two currencies and two refusal paths, all on models already present in this repository — which is why the Effort, Complexity and Uncertainty ratings above could be assigned from evidence rather than from guesswork |
| **Small** | ✅ | One accountant-facing workflow — raise an invoice and confirm it — sized at 5 story points and completable inside one iteration. Cash application, credit notes, dunning and aging are deliberately outside it and are carried by `STORY-001-03-02`, `STORY-001-03-03`, `STORY-001-03-04` and `STORY-001-03-05` |
| **Testable** | ✅ | Every one of the seven criteria is objectively pass or fail: each states amounts to the minor unit with the rounding rule applied, each posting criterion states a debit total and an equal credit total, each refusal names the message content and asserts an unchanged ledger and an unconsumed sequence, and each maps to exactly one automated test in [Acceptance Test Mapping](#acceptance-test-mapping) |

---

## Demonstration Path

Demonstrated in the Odoo user interface to the **Finance Controller** and the **Product Owner**, in this order, with the walkthrough recorded against this story:

- [ ] **The happy path.** **Accounting → Customers → Invoices → New**: select customer Northwind Trading in company `US-01`, confirm the Net 30 payment term is carried from the customer record, add the three lines of 7,200.00 USD, 3,750.00 USD and 1,500.00 USD against Revenue 4000 with output tax code **`ST-CA-0800`**, and observe the document total of 13,446.00 USD. Then **Confirm**. Observable result: the status moves from Draft to **Posted**, a **Sales**-journal sequence number appears on the document, the due date reads 2025-03-12, and the amount due reads 13,446.00 USD — every amount rounded half-up to 2 decimal places per the USD 0.01 rounding precision
- [ ] **The balanced entry.** From the posted invoice open **Journal Items** (also reachable at **Accounting → Accounting → Journal Entries**): the entry shows debit Accounts Receivable 1200 13,446.00 USD, credit Revenue 4000 12,450.00 USD and credit Tax Payable 2200 996.00 USD, with total debits of 13,446.00 USD equal to total credits of 13,446.00 USD
- [ ] **The tax triple.** On the same invoice, the tax summary presents tax code **`ST-CA-0800`**, base amount 12,450.00 USD and tax amount 996.00 USD as three separate values, and the 996.00 USD is traced to the Tax Payable 2200 journal item
- [ ] **The refusals.** Attempt to confirm an invoice whose second line has no income account and no unit price, and observe the document stay in Draft with a message naming line 2 and the missing elements. Then, in company **Global Europe SARL** (`NL-01`) with its journal-entry lock date at 2025-03-31, confirm an invoice dated 2025-03-15 and observe it post with its accounting date moved to 2025-04-30, its invoice date left at 2025-03-15, and the recorded date change naming the lock date and the company
- [ ] **The credit-control gate.** On an invoice for Northwind Trading that would take the customer's open receivable to 31,446.00 USD, observe the warning stating the 25,000.00 USD limit, the 31,446.00 USD projected balance and the 6,446.00 USD excess, then observe the invoice post once the Credit Controller's override is recorded against it
- [ ] **Headless alternative, on the access contract C-023 fixes.** Where interactive access is not available, the same evidence is presented over the platform's current JSON web-service endpoint — `/json/2/<model>/<method>` on the Odoo 19.0 baseline, restated for whichever version DEC-001 confirms — authenticated with a bearer API key issued to the dedicated integration principal `ar-invoice`, scoped to the companies and models this story names, with a recorded key owner, expiry, rotation interval and revocation path under C-021, executing under that principal's access rights and record rules with no privilege escalation, rate-limited and audit-logged per call. The deprecated XML-RPC and JSON-RPC endpoints are deprecated on this baseline and scheduled for removal in the following major series, so no criterion, test or demonstration here is written against them. The evidence is presented by reading `account.move` (state, sequence name, `amount_total`, `amount_residual`, `invoice_date_due`) and its `account.move.line` records **over that same C-023 surface under the `ar-invoice` principal**, so acceptance never depends on a graphical session and no evidence is read over a deprecated transport

---

## Constraints

The constraint identifiers below are the Epic's own, restated in the terms of this story rather than renumbered, so one constraint set reads across the whole ticket tree.

### License and Compliance

- [ ] **C-001 — AGPL-3.0 compatibility**: any module delivering the invoice completeness checks, the credit-control gate and the override record is distributed under an AGPL-3.0 compatible licence, matching the Community-edition accounting add-ons already present in this repository
- [ ] **C-002 — Existing licence respected**: extension of `account` — the "Invoicing" application, version 1.4, category `Accounting/Accounting`, licence LGPL-3 — and of `account_payment` (version 2.0, LGPL-3) respects those licences, and an AGPL-3 extension of LGPL-3 code is licence-checked before it is written
- [ ] **C-005 / C-006 — Odoo and OCA coding standards**: Python follows the Odoo and OCA module guidelines including PEP 8, and static analysis reports zero violations under the repository's lint configuration at `ruff.toml`
- [ ] **C-012 — Build on the existing models**: the invoice, its lines, its tax and its receivable are expressed on `account.move`, `account.move.line`, `account.tax`, `account.journal` and `res.partner` rather than on parallel structures, so one ledger and one audit trail exist
- [ ] **C-014 — Access rights and company isolation**: the role that raises an invoice is distinguishable from the role that approves a credit-limit override and from the role that administers the lock date, and a role restricted to `US-01` can neither read nor post receivable lines of Global Europe SARL (`NL-01`)
- [ ] **C-018 — External text is context-encoded**: a customer name, an invoice reference or a memo field rendered into a customer-facing invoice document is emitted as escaped text rather than as markup
- [ ] **C-019 — Data access discipline**: reads of the receivable balance, the residual and the credit exposure are expressed through the Odoo ORM or parameterized SQL, with no string-concatenated query construction
- [ ] **C-020 — Failure messages disclose nothing**: the incomplete-line and locked-period refusals name the rejected document, the check that failed and the remedial action, and disclose no stack trace, SQL, file-system path or credential
- [ ] **C-021 — No credentials in source**: no credential, endpoint secret or signing certificate appears in module source, fixtures, logs or exports produced by this story

### Accounting Standards Compliance

- [ ] **ASC 606 and IFRS 15 — revenue recognition timing**: revenue reaches Revenue 4000 in the period the performance obligation is satisfied, which is why the invoice's accounting date governs the period rather than the date the document was keyed (AR-INV-BR-010). Where the invoice date and the satisfaction of the obligation fall in different periods, the cutoff entry belongs to the period-close story `STORY-001-07-05` and not to this one
- [ ] **ISO 4217 minor units**: every amount asserted in this story is rounded half-up to its currency's decimal precision — 2 decimal places at a 0.01 rounding precision for USD and EUR — and the currency code is stated with the amount
- [ ] **Debits equal credits**: the double-entry identity is asserted numerically on every posted invoice entry, with both totals stated and their difference asserted at `0.00` in the company's functional currency (C-009, SM-006)
- [ ] **Output tax is a liability, not revenue**: the tax amount reaches Tax Payable 2200 and no part of it reaches Revenue 4000, so the statutory return of FEATURE-001-05 ties to the tax control account rather than to a revenue balance

### Dependency and Edition Considerations

- [ ] **C-003 — Edition source is an open decision (DEC-002), not a prohibition**: the blanket ban on Enterprise dependencies carried by the superseded backlog is withdrawn. The choice between an Odoo Enterprise subscription and the OCA add-on path plus bespoke development for the residual gap is owned by the CFO / Finance Director with the Group Controller and is recorded in the Epic's [Open Decisions Register](../../EPIC-001-enterprise-accounting-odoo.md#appendix-b-open-decisions-register)
- [ ] **This story is not gated by DEC-002**: `account.move`, `account.move.line`, `account.tax`, `account.journal` and the `res.partner` credit fields are all present in this repository under LGPL-3, so customer invoicing can be delivered and demonstrated before the edition decision is confirmed. What DEC-002 affects is how the **Profit & Loss** and **Aged Receivable** presentations that consume this posting are rendered, which is FEATURE-001-07 and `STORY-001-03-05`
- [ ] **C-004 — OCA ecosystem compatibility**: whichever edition path is confirmed, the posted invoice, its lines and its tax triple stay consumable by the OCA add-ons named in the Epic without restatement
- [ ] **Enterprise modules are target capabilities, not installed dependencies**: `account_accountant`, `account_reports`, `account_asset`, `account_budget` and `account_consolidation` are absent from this repository's `addons/`, and no module delivered by this story declares a dependency on any of them while DEC-002 is open

- [ ] **C-023 to C-029 — the interface, artifact, resilience and ceiling contracts, stated for this story.** **C-023 applies**: the headless route runs over the platform's current JSON web-service endpoint under a bearer API key held by the dedicated integration principal `ar-invoice`, scoped per company and per model, with its key lifecycle under C-021, executing under access rights and record rules with no privilege escalation, rate-limited and audit-logged, and the deprecated XML-RPC and JSON-RPC transports excluded from every criterion, test and demonstration. **C-024 applies to the invoice a customer is sent**: where the invoice reaches the customer as a portal link, that link resolves through an authenticated portal session or a token scoped to that one invoice and company, short-lived, revocable, invalidated on settlement, credit or erasure, kept out of any query string a referrer or log retains, and answered by one cause-free denial with the attempt recorded; where it is sent as an attachment, C-025 governs it. **C-025 applies** to the generated invoice PDF and every register export: authorized on the parent invoice, system-named from its sequence, published atomically, audited on download and retained under the sales-invoice evidence retention period with its legal hold. **C-026 applies** to the issue history — the sequence consumed, the amounts and tax triple as issued, the recipient address and the acting principal, appended and snapshotted so a later master-data change does not rewrite what was issued. **C-027 applies** to the delivery of an invoice over mail or a customer channel: declared timeouts, bounded retry with backoff and jitter, a breaker, a parked terminal state with an operator alert, and a transactional outbox coupling the posting to the send. **C-028 applies**: a unique constraint over company and invoice sequence gives the issue its identity, so a replay consumes no second sequence number and creates no second entry, preconditions are revalidated inside the lock before the commit, and the balance and sequence refusals are not overridable by the issuing role. **C-029 applies** to every invoice register and export, each with its declared maxima, defaults, asynchronous threshold, cancellation and atomic publication

### Version Compatibility

- [ ] **C-010 — Platform version target is open decision DEC-001**: the programme request names Odoo 17, the superseded backlog named 18.0, and this repository is **Odoo 19.0 Community** (`odoo/release.py` declares `version_info = (19, 0, 0, FINAL, 0, '')`). The target is confirmed with stakeholders before development rather than chosen inside this story
- [ ] **C-011 — Language and database versions follow the confirmed target**: the 19.0 baseline present here declares `MIN_PY_VERSION = (3, 10)`, `MAX_PY_VERSION = (3, 13)` and `MIN_PG_VERSION = 13` in `odoo/release.py`; an earlier platform target carries a different supported matrix
- [ ] **Impact if DEC-001 resolves away from 19.0**: the `account.move`, `account.move.line` and `res.partner` field names cited in [Technical Discovery Notes](#technical-discovery-notes) are restated for the confirmed release, the lock-date behaviour is re-verified because lock-date administration differs across the three candidates, and the credit-limit field surface is re-checked because the company-level switch behind it was introduced at a stated release

---

## Technical Discovery Notes

> **Purpose:** these notes direct the codebase analysis that precedes implementation. They record what to investigate and what the outcome must prove; they do not choose the implementation. Naming an account code, a journal type or a report name is a business outcome required by the parent Feature's artifact register, not an implementation decision.

### Codebase Analysis Areas

| Area | Files/Modules to Examine | Analysis Focus |
|------|--------------------------|----------------|
| Invoice state and the posting entry points | `addons/account/models/account_move.py` | The `state` field and its Draft, Posted and Cancelled values, the confirmation entry point and the internal posting method behind it. Which completeness checks run before the state changes, which of them raise and which warn, and what the returned message contains for an invoice whose line lacks an income account or a unit price (Scenario 3) |
| Sequence assignment | `addons/account/models/account_move.py` | The sequence mixin the model inherits and its journal-scoped sequence index. Establish the exact point at which a **Sales**-journal number is consumed, whether a refused confirmation leaves a gap, and how the number is presented on the posted document |
| Balance enforcement | `addons/account/models/account_move.py` | The balance check that groups journal items by move and by currency decimal places and raises when the rounded sum of line balances is non-zero. Determine which write paths run inside that check, so the debits-equal-credits assertion of Scenarios 1, 5 and 6 is tested on the path the implementation actually takes |
| Totals, residual and due date | `addons/account/models/account_move.py` and `addons/account/models/account_move_line.py` | `amount_total`, `amount_residual`, `invoice_date_due` and `invoice_payment_term_id` on the document, and `amount_residual` and `date_maturity` on the line. How is the residual initialised at posting, how does a payment term produce the maturity date behind the 2025-03-12 due date, and how does a multi-instalment term distribute maturities across lines |
| Tax computation and the base amount | `addons/account/models/account_tax.py` and `addons/account/models/account_move_line.py` | The tax relation on the line and the field that carries the taxable base on the tax line. Where the base amount is stored so the tax code, base amount and tax amount are readable as three separate values (Scenario 2), and how the company tax-rounding method changes the result on a multi-line document |
| Credit-limit control | `addons/account/models/partner.py` and `addons/account/models/account_move.py` | The partner credit fields — the limit, the per-partner override flag, the visibility flag and the Days Sales Outstanding computation — together with the invoice-side warning field, its compute method and the message builder behind it. In this baseline the shipped control is a **Draft-state warning on an `out_invoice`, gated by a company-level switch, and not a block**; determine what an override record must add so Scenario 6 is satisfied without weakening the shipped warning |
| Lock-date re-dating | `addons/account/models/account_move.py` and `addons/account/models/company.py` | `_post` resolves the violated lock dates and re-dates the move through `_get_accounting_date` before the state becomes Posted, so a first confirmation is moved rather than refused; `_check_fiscal_lock_dates` raises only for an operation on an already **posted** entry. Confirm which lock applies to a **Sales**-journal document, how the resulting accounting date depends on the journal's sequence reset, where the date change is recorded, and how an exception is evidenced to the External Auditor (Scenario 4) |
| Rounding levers | `odoo/addons/base/models/res_currency.py` and `addons/account/models/company.py` | The currency rounding factor and the decimal precision derived from it — 0.01 giving 2 decimal places for USD and EUR — and the company tax-calculation rounding method. Establish which method each company files under, because rounding once per tax and once per line can differ by one minor unit on a multi-line document |
| Multi-company isolation | `addons/account/models/account_move.py`, `addons/account/models/account_journal.py` and the security definitions of `addons/account/` | How the company on the document, its journal and its accounts are constrained to one another, and which record rules keep a role restricted to `US-01` from reading or posting the receivable lines of Global Europe SARL (`NL-01`) — C-014 and D-007 |

### Relevant Existing Modules

| Module | Path | Relevance to this story |
|--------|------|------------------------|
| `account` | `addons/account/` | "Invoicing", version 1.4, category `Accounting/Accounting`, licence LGPL-3. Supplies `account.move` in its `out_invoice` form, `account.move.line` with the residual and maturity fields, `account.journal` for the **Sales** journal, `account.payment.term` for the due date, `account.tax` for the output tax carried on each line, and the `res.partner` credit fields the credit-control gate reads |
| `account_payment` | `addons/account_payment/` | "Payment - Account", version 2.0, licence LGPL-3. Not exercised by this story, which posts the receivable rather than settling it, but named because `STORY-001-03-02` allocates receipts against the residual this story initialises |
| `base` | `odoo/addons/base/` | `res.company` for the company whose books carry the entry, its functional currency and its lock dates; `res.currency` for the decimal precision and the 0.01 rounding increment every amount is rounded at; `res.partner` for the customer, its payment term and its credit limit |
| `account_financial_report_ce` | `addons/account_financial_report_ce/` | Version 19.0.1.1.0, AGPL-3, present from a prior programme phase. Where the Accounts Receivable 1200 and Revenue 4000 balances produced by this posting surface for the close reconciliation owned by FEATURE-001-07 — examined for its report-to-ledger tie-out pattern rather than extended here |
| `account_payment_followup` | `addons/account_payment_followup/` | Version 19.0.1.0.0, AGPL-3, present from a prior programme phase. Consumes the due date and the residual this story writes; named so the due-date derivation is verified against what the ladder of `STORY-001-03-04` measures from (D-003) |
| Enterprise accounting modules | absent from `addons/` | `account_accountant`, `account_reports`, `account_asset`, `account_budget` and `account_consolidation` are named in the Epic as target capabilities and are **not present** in this repository. No module delivered by this story depends on them while DEC-002 is open |

### OCA Module Compatibility

| OCA Repository | Module | Compatibility consideration |
|----------------|--------|-----------------------------|
| [OCA/account-invoicing](https://github.com/OCA/account-invoicing) | Invoicing workflow extensions | Determine whether an existing extension already supplies the invoice completeness checks and the line-level validation messages this story specifies, so bespoke code covers only the residual |
| [OCA/account-payment](https://github.com/OCA/account-payment) | Payment and credit-control extensions | Determine whether the credit-limit gate and its override record are expressible through an existing extension, and whether that extension's exposure computation agrees with the partner credit fields in `addons/account/models/partner.py` |
| [OCA/account-financial-reporting](https://github.com/OCA/account-financial-reporting) | `account_financial_report` | Under the OCA path of DEC-002 it renders the General Ledger, Trial Balance and Aged Partner Balance that consume this posting; determine whether it reads the tax code, base amount and tax amount as posted here without restating them |

### Discovery versus Prescription

This story states WHAT the Accounts Receivable Specialist needs and WHY. It does not prescribe HOW it is built. Not specified here: new model names, field definitions or schema decisions; whether a capability extends an existing model or adds a new one (D-005); view architecture or form layout; the report engine behind any customer-facing document; and module structure. Deferred to agent discovery: **D-003** (the residual gap left by the Community-edition add-ons already present), **D-005** (model extension approach), **D-007** (company isolation, record rules and the access-right groups implied by the personas) and **D-009** (the deterministic and hostile-input fixture sets, held apart from one another).

---

## Dependencies

### Story Dependencies

| Dependency Type | Story / Feature | Title | Relationship |
|-----------------|-----------------|-------|--------------|
| Parent Feature | [FEATURE-001-03](../FEATURE-001-03-accounts-receivable-customer-invoices.md) | Accounts Receivable & Customer Invoices | This story is story 1 of the 5 in this feature and delivers its capability CAP-001 |
| Parent Epic | [EPIC-001](../../EPIC-001-enterprise-accounting-odoo.md) | Enterprise Accounting in Odoo | Contributes the receivable and revenue postings the Epic's report, close and consolidation outcomes are computed from |
| Blocks | [STORY-001-03-02](./STORY-001-03-02-register-customer-payments.md) | Register Customer Payments and Allocations | A receipt allocates against a posted invoice: without the residual this story initialises there is nothing to reduce and no allocation to prove |
| Blocks | [STORY-001-03-03](./STORY-001-03-03-manage-customer-credit-notes.md) | Manage Customer Credit Notes and Refunds | A credit note reverses a posted invoice, so the invoice must exist as a posted entry across Accounts Receivable 1200, Revenue 4000 and Tax Payable 2200 first |
| Blocks | [STORY-001-03-04](./STORY-001-03-04-configure-payment-followups.md) | Configure Automated Payment Follow-Ups | The follow-up ladder measures days overdue from the due date this story derives from the payment term, and acts on the residual it initialises |
| Blocks | [STORY-001-03-05](./STORY-001-03-05-report-aged-receivables.md) | Generate Aged Receivables Report | An aging bucket is an age applied to an open residual; with no posted invoice there is no residual to age and no Accounts Receivable 1200 balance to tie the report to |
| Blocked By | — | — | Nothing inside FEATURE-001-03. The accounts, the **Sales** journal, the open period and the output tax code it posts against are satisfiable as demo data in a test company, which is what keeps this story Independent |
| Related | [FEATURE-001-01](../FEATURE-001-01-chart-of-accounts-fiscal-year.md) | Chart of Accounts & Fiscal Year | Supplies Accounts Receivable 1200, Revenue 4000 and Tax Payable 2200, the **Sales** journal per company, the fiscal year and its open periods, and the journal-entry lock date that Scenario 4 is refused against — the sequencing prerequisite recorded as ORD-001 |
| Related | [STORY-001-05-01](../FEATURE-001-05/STORY-001-05-01-configure-tax-codes-fiscal-positions.md) | Configure Tax Codes and Fiscal Positions | Supplies the output tax codes and the fiscal positions that select them, so the tax code, base amount and tax amount of Scenario 2 can be asserted rather than assumed — the sequencing prerequisite recorded as ORD-002 |
| Related | [STORY-001-07-02](../FEATURE-001-07/STORY-001-07-02-generate-profit-loss.md) | Generate Profit & Loss Statement | The downstream consumer of Revenue 4000: the revenue this story recognises is the revenue that statement presents, and the statement line ties to the posted invoice lines behind it (ORD-004) |

### External Dependencies

| Dependency | Type | Notes |
|------------|------|-------|
| ISO 4217 | Standard | Currency codes and minor units, the source of the 2-decimal precision and the 0.01 rounding increment every amount in this story is rounded half-up to |
| ASC 606 and IFRS 15 | Accounting standard | Revenue from Contracts with Customers: the timing rule behind AR-INV-BR-010, under which revenue reaches Revenue 4000 in the period the performance obligation is satisfied. Cutoff entries where invoice date and satisfaction fall in different periods belong to the period-close story, not to this one |
| Customer master data | Master data | Each customer's payment term, credit limit, currency and tax registration are confirmed and loaded before the invoices that derive their due date and their credit exposure from them are raised |
| Output tax configuration | Internal platform prerequisite | The output tax codes and fiscal positions delivered by `STORY-001-05-01`; until they exist, a tax code can be named in a criterion but not asserted against a posted line (ORD-002) |
| Statutory invoice numbering | Statutory requirement | The jurisdictions of the in-scope entities require an unbroken invoice sequence per journal, which is why AR-INV-BR-002 forbids a refused confirmation from consuming a number |
| Group credit policy sign-off | Governance | The credit limit per customer and the authority to override it are approved by the Credit Controller with the Chief Accountant before the gate of Scenario 6 is released |

### Integration Points

| Odoo Model/Module | Integration Type | Purpose |
|-------------------|------------------|---------|
| `account.move` | Write and extend | The customer invoice itself as `move_type = out_invoice`: its state transition from Draft to Posted, its **Sales**-journal sequence number, its `amount_total`, its `amount_residual` at posting and its derived due date |
| `account.move.line` | Write and read | The receivable, revenue and tax journal items of the posted entry, including the residual and maturity values that allocation and aging are later computed from, and the base amount that keeps the tax triple readable |
| `account.tax` | Read | The output tax code carried on each invoice line and the tax amount it computes on the stated base amount, consumed from the configuration of `STORY-001-05-01` rather than defined here |
| `res.partner` | Read and extend | The customer, its payment term, its credit limit and its open receivable balance; extended by the Credit Controller override the credit-control gate records |
| `account.journal` | Read | The **Sales** journal of the company whose books carry the entry, and the sequence it assigns at posting |
| `account.payment.term` | Read | The payment term that produces the due date of 2025-03-12 from an invoice date of 2025-02-10 under Net 30, including the multi-instalment case |
| `res.company` | Read | The company whose books carry the entry — `US-01` or Global Europe SARL (`NL-01`) — its functional currency, its journal-entry lock date and its tax-rounding method |
| `res.currency` | Read | The decimal precision and the 0.01 rounding increment every amount is rounded half-up to, and the rate and rate date recorded when the invoice currency differs from the functional currency |

---

## Estimation

| Dimension | Rating | Justification |
|-----------|--------|---------------|
| **Effort** | Medium | The delivered surface is one document lifecycle — Draft to Posted — with its completeness checks, its due-date derivation, its residual initialisation, its two refusal paths and its credit-limit control, all expressed on `account.move` and `account.move.line`, which this repository already provides under LGPL-3 rather than requiring new machinery |
| **Complexity** | Medium | Three behaviours each carry an accounting consequence: the entry must balance to `0.00` in the company's functional currency after half-up rounding at the currency's 0.01 rounding precision; the tax code, base amount and tax amount must stay separate journal-item values; and a refusal must leave no entry and consume no sequence number. None of them requires a new report engine, a new posting engine or an external integration |
| **Uncertainty** | Low | The behaviour can be inspected before development starts: `addons/account/models/account_move.py` holds the state field, the posting entry points, the sequence mixin, the balance check and the lock-date check, and `addons/account/models/partner.py` holds the credit-limit fields. The one open question is the shape of the Credit Controller override, because the shipped control is a Draft-state warning rather than a block — recorded in [Open Questions](#open-questions) |
| **Story Points** | **5** | Fibonacci scale (1, 2, 3, 5, 8, 13). Above a **3** because the story delivers a posting path with two refusal paths, a residual and due-date derivation, a tax triple and a credit-control gate across two companies and two currencies rather than one field or one screen. Below an **8** because receipt allocation, credit notes, the dunning ladder and the Aged Receivable report are the other four stories of this feature — `STORY-001-03-02` through `STORY-001-03-05` — and no report engine or external integration is built here |

---

## Test Requirements

### Coverage Requirement

| Metric | Requirement | Notes |
|--------|-------------|-------|
| **Minimum Test Coverage** | **80%** | Mandatory for all new functionality delivered by this story (C-007) |
| Unit Test Coverage | 80%+ | Completeness checks, due-date derivation, residual initialisation, tax computation and rounding, credit-exposure computation |
| Integration Test Coverage | 80%+ | Draft invoice through to a posted, balanced entry in a named company, and the two refusal paths that leave the ledger untouched |
| Assertion style | Numeric | Every amount is asserted to the minor unit, and every balanced-entry assertion compares total debits with total credits at a stated difference of `0.00` in the company's functional currency (C-009) |
| Traceability | 1 test : 1 criterion | Each acceptance test maps to exactly one Given/When/Then criterion in this file (C-008) |

### Unit Test Scenarios

| Acceptance Scenario | Unit test focus | Key assertions |
|---------------------|-----------------|----------------|
| Scenario 1 | Posting a complete invoice and initialising its receivable | State moves Draft to Posted; a **Sales**-journal sequence number is present; the entry holds debit Accounts Receivable 1200 13,446.00 USD, credit Revenue 4000 12,450.00 USD and credit Tax Payable 2200 996.00 USD; total debits equal total credits at a difference of 0.00 USD; `amount_residual` equals `amount_total` at 13,446.00 USD; the due date reads 2025-03-12 — each amount rounded half-up to 2 decimal places per the USD 0.01 rounding precision |
| Scenario 2 | Tax triple and tax arithmetic | The tax summary yields tax code `ST-CA-0800`, base amount 12,450.00 USD and tax amount 996.00 USD as three separate values; 12,450.00 USD at 8% rounds half-up to 996.00 USD at the USD 0.01 rounding precision; the Tax Payable 2200 journal item equals 996.00 USD; the Revenue 4000 journal item equals 12,450.00 USD and carries no part of the tax |
| Scenario 3 | Completeness refusal at line level | The invoice state stays Draft; the created-entry count for the attempt is 0; the **Sales**-journal sequence high-water mark of `US-01` is unchanged; the message names line 2 and both missing elements; the values on lines 1 and 3 are unchanged after the refusal |
| Scenario 4 | Lock-date re-dating | Confirmation posts rather than raising; the posted accounting date equals 2025-04-30 and not 2025-03-15; the invoice date remains 2025-03-15; the recorded date change contains the lock date 2025-03-31 and the company name Global Europe SARL; the Accounts Receivable 1200 movement of that company for 2025-03-01 to 2025-03-31 equals 0.00 EUR while the movement for 2025-04-01 to 2025-04-30 carries the invoice; total debits equal total credits at 0.00 EUR |
| Scenario 5 | Zero-amount line and half-up rounding at the minor unit | The 0.00 EUR line is present on the posted document and contributes 0.00 EUR to the entry; 69.9993 EUR rounds half-up to 70.00 EUR at the EUR 0.01 rounding precision; the entry holds debit Accounts Receivable 1200 403.33 EUR against credit Revenue 4000 333.33 EUR and credit Tax Payable 2200 70.00 EUR with total debits equal to total credits at a difference of 0.00 EUR; `amount_total` and `amount_residual` both read 403.33 EUR |
| Scenario 6 | Credit exposure and warning content | The warning states 25,000.00 USD, 31,446.00 USD and 6,446.00 USD as three separate values; with no override the state stays Draft, the created-entry count is 0, and the customer's open receivable still reads 18,000.00 USD |
| Scenario 7 | Release under a recorded override | With an override recorded the invoice posts with tax code `ST-CA-0800`, a base amount of 12,450.00 USD and a tax amount of 996.00 USD held as three separate values and with total debits of 13,446.00 USD equal to total credits of 13,446.00 USD; the override record carries author, timestamp and the authorised excess of 6,446.00 USD and admits no edit or deletion; the customer's open receivable then reads 31,446.00 USD; the credit limit on the partner record remains 25,000.00 USD — each amount rounded half-up to 2 decimal places per the USD 0.01 rounding precision |

### Integration Test Considerations

- [ ] Post the Scenario 1 invoice in the **Sales** journal of `US-01` and assert the posted entry line by line, with total debits of 13,446.00 USD compared to total credits of 13,446.00 USD at a difference of 0.00 USD, each amount rounded half-up to 2 decimal places per the USD 0.01 rounding precision.
- [ ] Run a Trial Balance for `US-01` immediately after that posting and assert that the movement on Accounts Receivable 1200 is 13,446.00 USD, on Revenue 4000 is 12,450.00 USD and on Tax Payable 2200 is 996.00 USD, so the entry ties to the ledger presentation the close reads (SM-006).
- [ ] Assert that the sum of open invoice residuals for `US-01` equals the Accounts Receivable 1200 balance at a difference of 0.00 USD, which is the sub-ledger tie-out `STORY-001-03-05` inherits (SM-001).
- [ ] Post an invoice against a multi-instalment payment term and assert one maturity date per instalment, each derived from the invoice date, with the sum of the instalment amounts equal to `amount_total` at a difference of 0.00 USD.
- [ ] Post the Scenario 5 invoice in the **Sales** journal of Global Europe SARL (`NL-01`) in EUR and assert the 70.00 EUR tax amount, the retained 0.00 EUR line and total debits of 403.33 EUR equal to total credits of 403.33 EUR at a difference of 0.00 EUR.
- [ ] Post an invoice whose currency differs from the company's functional currency and assert that the transaction amount, the converted amount, the rate and the rate date are each recorded, with both amounts rounded half-up at their own currency's 0.01 rounding precision.
- [ ] Apply a journal-entry lock date of 2025-03-31 to Global Europe SARL, confirm an invoice dated 2025-03-15, and assert the posted accounting date of 2025-04-30, the invoice date left at 2025-03-15, the recorded date change, an Accounts Receivable 1200 movement of 0.00 EUR over 2025-03-01 to 2025-03-31 and the same movement present over 2025-04-01 to 2025-04-30.
- [ ] Confirm a 50-line invoice carrying output tax in `US-01` and assert the posting completes in under 3 seconds, matching the parent Feature's §4.4 budget, with the query count held constant as the line count grows from 5 to 50.
- [ ] Assert company isolation: a role restricted to `US-01` can neither read nor post the receivable lines of Global Europe SARL, and an invoice cannot pair a journal of one company with an account of another (C-014, D-007).
- [ ] Submit the **hostile** fixture set on the customer-facing document path — an over-long customer name, an invoice reference carrying a control character, and a line label carrying a script payload alongside a formula-leading prefix — and assert for every member the single outcome of **rejection**: a named error identifying the failing check, no `account.move` and no `account.move.line` created, no stack trace, file-system path or credential disclosed, and the service still answering the next request (C-020, C-022).

### Acceptance Test Mapping

| BDD Scenario | Test Method Name | Test Type |
|--------------|------------------|-----------|
| Scenario 1: Post a customer invoice with a balanced journal entry | `test_post_customer_invoice_balanced_entry_and_residual` | Acceptance |
| Scenario 2: Tax code, base amount and tax amount are reported as three separate values | `test_invoice_tax_summary_reports_code_base_and_tax_separately` | Acceptance |
| Scenario 3: An invoice carrying an incomplete line is not posted | `test_incomplete_invoice_line_blocks_posting_and_keeps_sequence` | Acceptance |
| Scenario 4: Confirming into a locked fiscal period moves the accounting date into the first open period | `test_locked_period_redates_invoice_to_first_open_period` | Acceptance |
| Scenario 5: A zero-amount line and foreign-currency tax rounding | `test_zero_amount_line_and_eur_tax_rounds_half_up_to_two_decimals` | Acceptance |
| Scenario 6: A credit-limit breach is surfaced before the invoice posts | `test_credit_limit_breach_warns_and_holds_invoice_in_draft` | Acceptance |
| Scenario 7: An invoice released by a recorded credit override posts with its entry balanced | `test_credit_override_releases_invoice_and_entry_balances` | Acceptance |

---

## Definition of Done

### Implementation Checklist

- [ ] All 7 acceptance criteria scenarios pass
- [ ] **80% minimum test coverage achieved** for the functionality delivered by this story (C-007)
- [ ] Unit tests written and passing, with every amount asserted to the minor unit (C-009)
- [ ] Integration tests written and passing, covering a Draft invoice through to a posted balanced entry in a named company and both refusal paths
- [ ] Every posted invoice carries a customer, a payment term, a currency, at least one line, an income account and a tax code on every line; the count of posted invoices missing any one of those is 0
- [ ] `amount_residual` equals `amount_total` on 100% of invoices at the moment they post, at a difference of `0.00` in the invoice currency
- [ ] A refused confirmation creates no journal entry and consumes no **Sales**-journal sequence number, proven by an unchanged entry count and an unchanged sequence high-water mark
- [ ] A 50-line customer invoice carrying output tax confirms and posts in under 3 seconds in `US-01`
- [ ] Static analysis reports zero violations for the delivered modules under the repository's `ruff.toml` configuration (C-006)

### Accounting Reconciliation Gate

- [ ] **Debits equal credits.** Every posted customer invoice entry carries total debits equal to total credits, both totals stated and their difference asserted at `0.00` in the company's functional currency — 13,446.00 USD against 13,446.00 USD for the Scenario 1 and Scenario 6 invoices in `US-01`, and 403.33 EUR against 403.33 EUR for the Scenario 5 invoice in Global Europe SARL (`NL-01`) — each amount rounded half-up to 2 decimal places per that currency's 0.01 rounding precision
- [ ] **Tax amounts match.** The tax amount posted to **Tax Payable 2200** equals the base amount multiplied by the rate configured on the tax code, rounded half-up to 2 decimal places at the currency's 0.01 rounding precision — 996.00 USD from a base of 12,450.00 USD at tax code `ST-CA-0800`, and 70.00 EUR from a base of 333.33 EUR at tax code `VAT-21-S` — with the company's tax-rounding method stated alongside the figure, and the same amount reconciles to the tax line of the **VAT/Tax Return** for the same date range at a difference of `0.00` in the filing entity's functional currency (SM-010)
- [ ] **Report lines tie to the AR sub-ledger.** The sum of open invoice residuals equals the **Accounts Receivable 1200** balance in the **Trial Balance** for the same as-of date at a difference of `0.00 USD` in `US-01`, and that same total is what the **Aged Receivable** report of `STORY-001-03-05` presents for that as-of date; the Revenue 4000 movement posted here equals the revenue presented by the **Profit & Loss** statement of `STORY-001-07-02` for the same date range at a difference of `0.00 USD` (SM-001, ORD-004)
- [ ] **Base and tax stay separate.** The revenue line and the tax line remain separate journal items, so the tax code, the base amount and the tax amount are readable from the ledger without reconstruction; the count of posted invoice tax lines carrying a null tax code or a null base amount is 0
- [ ] **Zero-value lines are present, not absent.** A 0.00 line is retained on the posted document and contributes 0.00 to the entry rather than being dropped, and the entry still balances at a difference of `0.00` in the invoice currency
- [ ] **The tie-out worksheet is retained.** The reconciliation of the posted entry to the Trial Balance, and of the residual total to Accounts Receivable 1200, is retained as close evidence readable by the External Auditor without a data request

### Compliance Checklist

- [ ] AGPL-3.0 licence compliance verified for delivered modules, and the LGPL-3 licence of the `account` and `account_payment` code being extended is respected (C-001, C-002)
- [ ] Code follows Odoo and OCA coding standards including PEP 8 (C-005)
- [ ] The edition decision DEC-002 is cited rather than pre-empted, and no delivered module declares a dependency on an Enterprise module absent from this repository (C-003)
- [ ] Access rights separate the role that raises an invoice from the role that records a credit-limit override and from the role that administers the lock date, and company isolation between `US-01` and Global Europe SARL (`NL-01`) is proven by test (C-014, D-007)
- [ ] Revenue recognition timing is signed off against ASC 606 and IFRS 15 by the Chief Accountant, and the accounts each invoice line posts to are approved before release (AR-INV-BR-010)
- [ ] Code reviewed and approved, with the accounting behaviour reviewed by the Chief Accountant rather than by the delivery team alone

### Documentation Checklist

- [ ] Docstrings complete for the public methods and models delivered by this story
- [ ] The customer-invoicing runbook is published: the line-to-account mapping, the completeness checks and their message wording, the due-date derivation per payment term, the lock-date refusal path and the credit-limit override path
- [ ] Finance-facing procedure notes updated for the Accounts Receivable Specialist and the Credit Controller, stating what each role does when a confirmation is refused and when an override is requested
- [ ] Every credit-limit override is recorded with its author, its timestamp and the authorised excess amount, readable by the External Auditor without a data request

### Quality Checklist

- [ ] No critical or high-severity defect open against the invoice posting path
- [ ] The posting path holds its stated budgets: under 3 seconds for a 50-line invoice, with no repeated per-record query pattern and a query count that stays constant as the line count grows from 5 to 50
- [ ] No credential, endpoint secret or signing certificate appears in module source, fixtures, logs or exports (C-021)
- [ ] Hostile input on the customer-facing document path is **rejected** with a named error, no journal entry created, and the service still available — rejection being the only outcome those tests admit (C-020, C-022)
- [ ] Legitimate customer-supplied text that contains markup or a formula-leading character is **accepted**, stored verbatim, rendered inert on the invoice PDF, the invoice form, the customer statement, the Aged Receivable report and a dunning email body (C-018), and neutralized on every CSV and XLSX export (C-017) — asserted by its own tests, because a test that passes on either rejection or neutralization proves neither
- [ ] The deterministic fixtures are held apart from the hostile-input fixtures, so a hostile record cannot be mistaken for sample data (D-009)
- [ ] The demonstration in [Demonstration Path](#demonstration-path) has been given to the Finance Controller and the Product Owner, including the two refusals and the credit-limit gate, and the walkthrough is recorded against this story

---

## Workflow Diagram

```mermaid
graph TD
    A["FEATURE-001-01 delivers Accounts Receivable 1200, Revenue 4000,<br/>Tax Payable 2200, the Sales journal per company<br/>and an open fiscal period (ORD-001)"]
    B["STORY-001-05-01 delivers the output tax code<br/>and the fiscal position that selects it (ORD-002)"]
    C["Accounts Receivable Specialist creates account.move<br/>move_type = out_invoice in the Sales journal"]
    D["Customer, payment term, currency<br/>and invoice lines entered<br/>each line: income account + tax code"]
    E{"Completeness check<br/>at confirmation"}
    F["Refused: stays Draft, no entry,<br/>no sequence consumed,<br/>message names the line (Scenario 3)"]
    G{"Accounting date<br/>after the company<br/>lock date?"}
    H["Re-dated: posts at 2025-04-30 with the<br/>change recorded, naming the lock date<br/>and the company (Scenario 4)"]
    I{"Projected balance<br/>above the credit limit?"}
    J["Warning states limit, projected balance<br/>and excess, invoice held in Draft<br/>(Scenario 6); Credit Controller records<br/>an override to release it (Scenario 7)"]
    K["Posted: Sales-journal sequence assigned"]
    L["Journal entry:<br/>debit Accounts Receivable 1200<br/>credit Revenue 4000<br/>credit Tax Payable 2200<br/>total debits = total credits"]
    M["amount_residual = amount_total<br/>due date derived from the payment term"]
    N["STORY-001-03-02 allocates receipts<br/>against the residual"]
    O["STORY-001-03-03 credits the invoice<br/>by credit note"]
    P["STORY-001-03-04 ladders the overdue residual"]
    Q["STORY-001-03-05 ages the residual and ties<br/>to Accounts Receivable 1200"]
    R["STORY-001-07-02 presents Revenue 4000<br/>in the Profit & Loss statement (ORD-004)"]

    A --> C
    B --> D
    C --> D
    D --> E
    E -->|incomplete| F
    E -->|complete| G
    G -->|"on or before"| H
    G -->|after| I
    I -->|yes| J
    I -->|no| K
    J --> K
    K --> L
    L --> M
    M --> N
    M --> O
    M --> P
    M --> Q
    L --> R
```

---

## References

### Accounting Standards

- **ASC 606 / IFRS 15** — Revenue from Contracts with Customers: the timing rule under which the revenue credited to Revenue 4000 belongs to the period the performance obligation is satisfied (AR-INV-BR-010)
- **ISO 4217** — currency codes and minor units: the source of the 2-decimal precision and the 0.01 rounding increment applied half-up to every USD and EUR amount asserted in this story
- **Double-entry identity** — total debits equal total credits on every posted entry, asserted numerically with both totals stated (C-009, SM-006)
- **Statutory invoice numbering** — an unbroken sequence per journal, which is why a refused confirmation consumes no number (AR-INV-BR-002)

### OCA Modules (Reference)

- [OCA/account-invoicing](https://github.com/OCA/account-invoicing) — invoicing workflow extensions, examined for existing completeness checks and line-level validation patterns
- [OCA/account-payment](https://github.com/OCA/account-payment) — payment and credit-control extensions, examined for an existing credit-limit gate and exposure computation
- [OCA/account-financial-reporting](https://github.com/OCA/account-financial-reporting) — `account_financial_report`, examined for how the General Ledger, Trial Balance and Aged Partner Balance consume the posting this story produces under the OCA path of DEC-002

### Source Code References

All paths below were read in this repository at the Odoo 19.0 Community baseline and are cited so the implementing agent starts from verified ground rather than from assumption.

- `odoo/release.py` — `version_info = (19, 0, 0, FINAL, 0, '')`, with `MIN_PY_VERSION = (3, 10)`, `MAX_PY_VERSION = (3, 13)` and `MIN_PG_VERSION = 13` behind C-010 and C-011
- `addons/account/__manifest__.py` — "Invoicing", version 1.4, category `Accounting/Accounting`, licence LGPL-3
- `addons/account/models/account_move.py` — the invoice state field, the confirmation and posting entry points, the journal-scoped sequence mixin, `amount_total`, `amount_residual`, `invoice_date_due`, `invoice_payment_term_id`, the partner credit-warning field with its compute method and message builder, the balance check that raises when the rounded sum of line balances is non-zero, and the fiscal lock-date check with the context key that bypasses it
- `addons/account/models/account_move_line.py` — the tax relation on the line, the field carrying the taxable base on the tax line, and the residual and maturity fields that allocation and aging are computed from
- `addons/account/models/account_tax.py` — tax type, computation method, rate and the distribution that routes output tax to its control account
- `addons/account/models/partner.py` — `credit_limit`, the per-partner override flag, the credit-limit visibility flag, the Days Sales Outstanding computation and the company-dependent customer payment term
- `addons/account/models/company.py` — the lock-date set whose violations the posting check reads, and the tax-calculation rounding method
- `addons/account/models/account_journal.py` — the journal type set whose labels include Sales and Bank
- `odoo/addons/base/models/res_currency.py` — the rounding factor with its shipped default of 0.01 and the decimal precision derived from it, giving 2 decimal places for USD and EUR
- `addons/account_payment/__manifest__.py` — "Payment - Account", version 2.0, licence LGPL-3
- `addons/account_payment_followup/__manifest__.py` — "Payment Follow-ups", version 19.0.1.0.0, licence AGPL-3, depending on `account` and `mail`; consumes the due date and residual this story writes (D-003)
- `addons/account_financial_report_ce/__manifest__.py` — "Financial Reports for Community Edition", version 19.0.1.1.0, licence AGPL-3, depending on `account` and `analytic`; where the Accounts Receivable 1200 and Revenue 4000 balances surface at close
- `ruff.toml` — the static-analysis configuration in force under C-006

### Ticket References

- [EPIC-001: Enterprise Accounting in Odoo](../../EPIC-001-enterprise-accounting-odoo.md) — programme objective, success metrics, constraint set, ordering rules and the [Open Decisions Register](../../EPIC-001-enterprise-accounting-odoo.md#appendix-b-open-decisions-register)
- [FEATURE-001-03: Accounts Receivable & Customer Invoices](../FEATURE-001-03-accounts-receivable-customer-invoices.md) — parent feature, its deterministic artifact register and its capability CAP-001
- [FEATURE-001-01: Chart of Accounts & Fiscal Year](../FEATURE-001-01-chart-of-accounts-fiscal-year.md) — the accounts, the **Sales** journal, the fiscal periods and the lock dates this story posts against
- [FEATURE-001-05: Tax Configuration & Compliance](../FEATURE-001-05-tax-configuration-compliance.md) and [STORY-001-05-01: Configure Tax Codes and Fiscal Positions](../FEATURE-001-05/STORY-001-05-01-configure-tax-codes-fiscal-positions.md) — the output tax codes and fiscal positions consumed here
- Sibling stories: [STORY-001-03-02](./STORY-001-03-02-register-customer-payments.md), [STORY-001-03-03](./STORY-001-03-03-manage-customer-credit-notes.md), [STORY-001-03-04](./STORY-001-03-04-configure-payment-followups.md), [STORY-001-03-05](./STORY-001-03-05-report-aged-receivables.md)
- Downstream consumer: [STORY-001-07-02: Generate Profit & Loss Statement](../FEATURE-001-07/STORY-001-07-02-generate-profit-loss.md)

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-08-13 | Enterprise Accounting Team | Initial story creation. Given/When/Then criteria covering a balanced happy-path posting, the tax code / base amount / tax amount triple, an incomplete-line refusal, a locked-period refusal, a zero-amount line with half-up foreign-currency tax rounding, and a credit-limit breach with a recorded override — six at that revision, seven from version 1.2, where the release under an override became its own criterion; monetary precision, the rounding rule and the debit and credit totals stated on every assertion; business rules AR-INV-BR-001 to AR-INV-BR-010, seven sub-tasks with assignee handles, four edge cases, a Fibonacci estimate of 5, the INVEST table and the demonstration path added to the template structure; nested relative links adopted in place of the template's flat convention; the platform version and edition questions carried forward as DEC-001 and DEC-002 rather than settled |
| 1.1 | 2026-08-13 | Enterprise Accounting Team | Review remediation. **Lock-date contract corrected.** Scenario 4 asserted that confirming into a locked period is refused and stated explicitly that "the refusal does not silently re-date the document into an open period" — which is the opposite of what the platform does. `account.move._post` resolves the violated lock dates and moves the accounting date through `_get_accounting_date` before the state becomes Posted, so for a Sales-journal document dated 2025-03-15 against a lock at 2025-03-31 the invoice posts at **2025-04-30**, the last day of the first open period, with the invoice date left at 2025-03-15 as issued. The criterion now asserts the posted accounting date and the recorded date change, the business-rule row, the codebase-analysis row, the test traceability, the acceptance-test name and the workflow diagram node are realigned, and the closed period is still proved untouched at 0.00 EUR. **Single-trigger criteria.** Scenario 6 asserted the credit-limit warning, the no-override refusal and the post-override successful posting under one **When**. The release under an override is now Scenario 7, taking the story from six criteria to seven, still inside the 4-to-8 bound; Scenario 6 keeps the warning and the Draft hold and additionally asserts the open receivable still reading 18,000.00 USD, so the warning is shown to be raised on a projection. Test traceability, the acceptance-test mapping, the workflow diagram and the Credit Controller persona row are split to match. **Governed tax vocabulary.** The story-local codes `S-8` and `S-21` belonged to no governed set. They are replaced by `ST-CA-0800` and `VAT-21-S`; FEATURE-001-05 now carries `ST-CA-0800` at 8.00% alongside `ST-CA-0725` at the 7.25% state base rate, because a Californian jurisdiction with district add-ons resolves to more than one combined rate; and the parent Feature publishes the authoritative fixture table this story consumes as AR-TAX-2 and AR-TAX-3. The naming-alignment open question is **closed** and the two artifact rows now describe governed codes rather than story-local shorthand. No rate, base amount or tax amount changed: 12,450.00 USD at 8.00% still yields 996.00 USD, and 333.33 EUR at 21% still yields 70.00 EUR. **Security outcomes made deterministic.** One hostile-input item required an input to be escaped, exported-neutralized, rejected with a named error and to create no journal entry all at once — four outcomes for one fixture, so a test could pass on any and prove none. The C-022 set is now rejection-only, and the accepted-value protections are asserted by their own items with their own fixtures: `Fell & Sons <Holdings>` and `-Reserved- Freight Recovery` rendered inert on five named surfaces (C-018) and neutralized on every CSV and XLSX export with a preserving round trip (C-017). **Entity register alignment.** Company `NL-01` is named **Global Europe SARL**, the legal name the Epic's canonical legal-entity register (Appendix E.4) binds to that code, in place of the divergent **Northwind Group NV**; the customer **Northwind Trading** is a different party and is unchanged. **Rule identifiers namespaced.** The ten story-local business rules are carried as `AR-INV-BR-001` to `AR-INV-BR-010`, so no rule identifier collides with the sibling payment story's set and the retired `BR-001` to `BR-005` bank stories keep their identifiers for Appendix C traceability alone. Demonstrability heading normalized to `## Demonstration Path` with its in-document anchor updated to match |
| 1.2 | 2026-08-15 | Enterprise Accounting Team | Review remediation. **Criteria count corrected to seven.** The file already carried a seventh criterion — the release of a credit-limit-blocked invoice under a recorded override — while its coverage distribution, its INVEST Testable row, its test sub-task, its Definition of Done and its persona table still claimed six; all now read seven, and the coverage table gains the row for it. Two coverage classes were also stale and are corrected: Scenario 4 is a **re-dating** branch under the Epic's [§7.8](../../EPIC-001-enterprise-accounting-odoo.md#78-lock-date-behaviour-contract) row L-1 rather than a refusal, and Scenario 6 is the **error-handling** case, being a blocked posting with a named warning and 0 entries created. **One trigger per criterion:** Scenario 7's `When` carried two acts — the Credit Controller recording an override and the Specialist confirming — so the override is now a Given, recorded with its author, its timestamp and the `$6,446.00 USD` excess it authorised, and the `When` is the single act of confirming. **Every line carries a tax code:** the zero-amount line of Scenario 5 was confirmed with no tax code against this story's own AR-INV-BR-003, and now carries the governed output code **`VAT-21-S`** on a base amount of `0.00 EUR` for a tax amount of `0.00 EUR`, with the reason a zero-rate code is not used stated against the register [TAX-REG-001](../FEATURE-001-05-tax-configuration-compliance.md#111-authoritative-tax-code-register-tax-reg-001), whose `VAT-00-ZR` and `VAT-00-EX` require a non-zero base. **The multi-company assertion is now true:** Scenario 4 claimed no journal item was readable in *either* company when **Global Europe SARL** had just posted one, and now asserts 0 journal items added to `US-01` with `0.00 USD` of movement on its three accounts, the entry readable in the company that posted it, and a role restricted to `US-01` able to read neither the entry nor the invoice. No fixture amount, no total and no estimate changed: the invoice still posts `$13,446.00 USD` against `$13,446.00 USD` |
| 1.3 | 2026-08-16 | Blitzy Platform — Finance Transformation Programme | Code-review remediation of the inherited contract set, with no change to the invoice figures, the sequence behaviour or the estimate. The headless route moves onto the C-023 contract — the platform's current JSON web-service endpoint under a bearer API key held by the dedicated integration principal `ar-invoice`, scoped per company and model, with its key lifecycle, no privilege escalation, a rate limit and a per-call audit — and the deprecated XML-RPC and JSON-RPC transports are excluded from every criterion, test and demonstration. C-023 to C-029 are restated for this story: an invoice reaching a customer as a portal link is bound to the C-024 token contract while one sent as an attachment is bound to C-025, the issue history becomes append-only evidence with snapshot values, invoice delivery becomes a bounded breaker-protected outbox-coupled dispatch, the issue gains a database-enforced identity so a replay consumes no second sequence number, and every register export carries its ceilings |
| 1.4 | 2026-08-16 | Blitzy Platform — Finance Transformation Programme | Residual demonstrability wording closed against MJ-01. The headless-demonstration bullet already stated the C-023 surface and the `ar-invoice` principal, but its trailing clause still read "over the public API by XML-RPC or JSON-RPC" and so contradicted its own lead; the read-back of the posted records now happens **over that same C-023 surface under the `ar-invoice` principal**, and the deprecated XML-RPC and JSON-RPC transports are excluded from every acceptance path. No acceptance criterion, edge case, estimate or fixture amount changed |
| 1.5 | 2026-08-16 | Blitzy Platform — Finance Transformation Programme | Metadata correction of the `Last Updated` field, which still read **2026-08-15** while revision **1.4** of **2026-08-16** was already recorded above it, so a reader comparing the field with the history was given two dates for one state of the file and could not tell which revision the field described. The field now carries the date of the newest revision row, and this row records the correction so the discrepancy is visible in the history rather than silently overwritten. No acceptance criterion, edge case, estimate, fixture amount, constraint or link in this file changed |
| 1.6 | 2026-08-16 | Blitzy Platform — Finance Transformation Programme | QA remediation of finding `F-VOCAB-01`, with no change to any amount, tax code, base or tax amount, account, company, date, journal entry, scenario count or estimate. One occurrence in this file were written as `Tax Report (VAT Return)`, a form the Epic's [canonical report-label register](../../EPIC-001-enterprise-accounting-odoo.md#e7-canonical-report-display-labels) does not publish and its compatibility note does not admit, which under rule **R-E6** made one report read as two. Every one of them now reads **VAT/Tax Return**, the label E.7 publishes for the report that states tax base and tax amount per tax code for a company and a tax period. |
| 1.7 | 2026-08-16 | Blitzy Platform — Finance Transformation Programme | QA schema remediation of section order. The unchanged Estimation block now follows Dependencies and precedes Test Requirements, matching the canonical story schema published in `tickets/README.md`. No criterion, amount, account, estimate or link changed. |

---

## Notes

### Business Context

Today a customer invoice in this group is produced as a document and recorded in the ledger as an afterthought, which is why the receivable position has to be reconstructed at month end from a spreadsheet rather than read from the books. Three figures are unavailable between reconstructions: what the group is owed, what it earned in the period, and what output tax it owes. This story closes that gap at its source — the moment of confirmation — by making the invoice both the customer document and the journal entry, so the receivable, the revenue and the tax liability come into existence together and balance to `0.00` in the company's functional currency.

Its value is realised through the stories it blocks rather than only in itself. `STORY-001-03-02` needs the residual to allocate against, `STORY-001-03-03` needs the posted entry to reverse, `STORY-001-03-04` needs the derived due date to measure days overdue from, and `STORY-001-03-05` needs the open residual to age and the Accounts Receivable 1200 balance to tie to. That is also why the controls sit here and not downstream: a period lock that refuses a posting protects a reported result, and a credit-limit warning raised before the receivable exists is a decision, while the same warning raised afterwards is a report.

### Persona Usage Patterns

| Persona | Usage pattern in this story |
|---------|----------------------------|
| **Accounts Receivable Specialist** (primary) | Raises the invoice, enters its lines, confirms it, and resolves the incomplete-line refusal and the credit-limit block. The actor whose confirmation is the trigger of all seven acceptance criteria |
| **Chief Accountant** (secondary) | Approves the line-to-account mapping and the accounts the entry posts to, verifies that total debits equal total credits at a difference of `0.00` in the company's functional currency, administers the journal-entry lock date behind Scenario 4, and signs off the ASC 606 and IFRS 15 timing rule |
| **Tax Accountant** (secondary) | Owns the output tax codes and fiscal positions this story consumes from `STORY-001-05-01`; verifies that the tax code, base amount and tax amount are recorded as three separate values and that the tax reaches Tax Payable 2200 rather than Revenue 4000 |
| **Credit Controller** (secondary) | Reviews the credit-limit warning of Scenario 6 and records the override of Scenario 7 that allows the invoice to post, with author, timestamp and the authorised excess retained |
| **Treasury Analyst** (secondary) | Reads the posted receivable and the customer's projected balance of 31,446.00 USD as exposure against the 25,000.00 USD limit, and takes the due dates this story derives as the collections forecast feeding the cash position |
| **External Auditor** (secondary) | Traces a posted invoice to its journal items and its tax triple, and reads the credit-limit override and any lock-date exception as control evidence without raising a data request |
| **Finance Controller** and **Product Owner** | Witness the demonstration described in [Demonstration Path](#demonstration-path) and accept the story |

### Deterministic Artifact Set

The general ledger accounts, the journal and the rounding rule used above are inherited unchanged from the parent Feature's fixed artifact register, so the five stories of FEATURE-001-03 read on one vocabulary: **Accounts Receivable 1200**, **Revenue 4000** and **Tax Payable 2200**; the **Sales** journal; the entities of the Epic's canonical legal-entity register ([Appendix E.4](../../EPIC-001-enterprise-accounting-odoo.md#e4-canonical-legal-entity-register)) — **Global Holdings Inc.** (`US-01`, United States parent, functional currency USD, also the group presentation currency), **Global Europe SARL** (`NL-01`, Netherlands operating subsidiary, EUR) and **Global UK Ltd** (`GB-01`, United Kingdom operating subsidiary, GBP, incorporated 2025-04-01); and rounding half-up to 2 decimal places at each currency's 0.01 rounding precision. No alternative account code and no alternative company identity is introduced by this story: every code resolves through the Epic's [canonical account register](../../EPIC-001-enterprise-accounting-odoo.md#e2-canonical-group-chart-of-accounts) and every entity code through Appendix E.4.

The worked data set below is story-local: it instantiates the receivable-side archetype the programme request supplies — a Draft document with three lines totalling 12,450.00 USD, confirmed by a named finance role, producing a balanced entry — which is the mirror image of the payable-side archetype carried by FEATURE-001-02 across Expense 6100 and Accounts Payable 2000. The parent Feature's own worked invoice `INV/2025/0001` (a base of 8,750.00 USD at 7.25% giving a tax amount of 634.38 USD and a debit to Accounts Receivable 1200 of 9,384.38 USD, each amount rounded half-up to 2 decimal places per the USD 0.01 rounding precision) exercises the same posting shape and the same rounding rule at different figures; both are kept because the feature-level tie-out chain is stated against `INV/2025/0001` while the archetype figures make the payable-to-receivable parallel explicit.

| Story-local artifact | Value | Alignment with the parent Feature's register |
|----------------------|-------|---------------------------------------------|
| Company **Global Holdings Inc.** (`US-01`) | The United States parent of the Epic register, functional currency USD, which is also the group presentation currency | Inherited unchanged from Appendix E.4; the books affected by Scenarios 1, 2, 3 and 6 |
| Company **Global Europe SARL** (`NL-01`) | The legal entity the Epic register holds against entity code `NL-01`, the Netherlands operating subsidiary, functional currency EUR | The named legal entity for register code `NL-01`; the books affected by Scenarios 4 and 5. Naming it is what satisfies the requirement that a multi-company clause identify the company whose books are affected |
| Customer **Northwind Trading** | A USD-billed customer of `US-01` with a Net 30 payment term and a credit limit of 25,000.00 USD, rounded half-up to 2 decimal places per the USD 0.01 rounding precision | New at story level; the register fixes companies, accounts, journals and reports rather than customer names |
| Customer **Atlantia SRL** | A EUR-billed customer of Global Europe SARL (`NL-01`) | New at story level, on the same basis |
| Output tax code **`ST-CA-0800`** | The Californian output sales-tax code including a district add-on, 8.00%, posting to Tax Payable 2200 | A governed code. [FEATURE-001-05](../FEATURE-001-05-tax-configuration-compliance.md) carries it alongside `ST-CA-0725` at the state base rate of 7.25%, because a jurisdiction with district add-ons resolves to more than one combined rate; the parent Feature's authoritative output-tax fixture table records this story's use of it as fixture **AR-TAX-2** |
| Output tax code **`VAT-21-S`** | The Netherlands standard-rate output code, 21%, posting to Tax Payable 2200 | A governed code, carried by [FEATURE-001-05](../FEATURE-001-05-tax-configuration-compliance.md) at the same 21%; the parent Feature's authoritative output-tax fixture table records this story's use of it as fixture **AR-TAX-3** |
| Journal-entry lock date | 2025-03-31 on Global Europe SARL | Consumes the lock-date administration delivered by FEATURE-001-01 rather than defining a second control |
| Worked dates | Invoice date 2025-02-10 with Net 30 giving a due date of 2025-03-12; an accounting date of 2025-03-15 re-dated on posting to 2025-04-30 under Epic §7.8 L-1; a Scenario 5 accounting date of 2025-04-30 | Chosen so the locked-period re-dating and the successful EUR posting sit on opposite sides of the 2025-03-31 lock date without contradicting each other |

### Open Questions

| Question | Status | Owner |
|----------|--------|-------|
| Platform version target — Odoo 17 as requested, 18.0 as the superseded backlog named, or 19.0 as this repository is | Open, recorded as **DEC-001** in the Epic's [Open Decisions Register](../../EPIC-001-enterprise-accounting-odoo.md#appendix-b-open-decisions-register). It changes the `account.move` and `account.move.line` field surface, the lock-date administration behind Scenario 4 and the credit-limit field surface behind Scenario 6, so it is confirmed before development rather than assumed here (AAP §0.8.3) | Group Controller with IT Operations |
| Edition source for the Enterprise-only capability set | Open, recorded as **DEC-002**. It does not gate this story, because every model it posts to is present under LGPL-3; it gates how the **Profit & Loss** and **Aged Receivable** presentations that consume this posting are rendered | CFO / Finance Director with Group Controller |
| Whether the credit-limit gate blocks posting or warns and records an override | Open. In this baseline the shipped control is a Draft-state warning on an `out_invoice`, gated by a company-level switch, and it does not block. Scenario 6 requires the warning **and** a recorded override before posting; whether the override is per invoice, per customer for a stated window, or per amount band is confirmed with the Credit Controller before development | Credit Controller with the Chief Accountant |
| Output tax-code naming alignment with FEATURE-001-05 | **Closed.** This story previously used the story-local names `S-8` and `S-21`, which belonged to no governed set, so a reader could not tell whether they denoted the codes FEATURE-001-05 configures or something else. It now uses the governed names `ST-CA-0800` and `VAT-21-S`, FEATURE-001-05 carries `ST-CA-0800` in its governed set alongside `ST-CA-0725`, and the parent Feature publishes an authoritative output-tax fixture table that records which fixture each story uses. No rate, base amount or tax amount changed in the closing: 12,450.00 USD at 8.00% still yields 996.00 USD, and 333.33 EUR at 21% still yields 70.00 EUR | Tax Accountant with the Product Owner |
| Which tax-calculation rounding method each company files under — once per tax or once per line | Open. The two can differ by one minor unit on a multi-line invoice, which is enough to fail the debits-equal-credits check, so the method is fixed per company and stated alongside every tax figure in the reconciliation worksheet | Tax Accountant with the Chief Accountant |
| Revenue-recognition cutoff where the invoice date and the satisfaction of the performance obligation fall in different periods | Open at programme level. This story recognises revenue on the invoice's accounting date under AR-INV-BR-010; the deferral and cutoff entries that move revenue between periods belong to the period-close story `STORY-001-07-05` and are not authored here (SM-015) | Chief Accountant with the Financial Reporting Manager |
