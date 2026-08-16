# Enterprise Accounting Documentation

[![Documentation Status](https://img.shields.io/badge/status-draft-yellow.svg)](EPIC-001-enterprise-accounting-odoo.md)
[![Total Stories](https://img.shields.io/badge/stories-41-blue.svg)](#story-directory-structure)
[![Features](https://img.shields.io/badge/features-9-green.svg)](#feature-index)

> **Enterprise-grade accounting in Odoo for multi-entity financial operations, compliance reporting and real-time financial visibility**

This directory contains the epic, feature and user story documentation for implementing enterprise-grade accounting capabilities in Odoo that support multi-entity financial operations, compliance reporting, and real-time visibility into organizational financial health for finance teams and executive stakeholders. The documentation follows INVEST principles and BDD (Behavior-Driven Development) acceptance criteria in Given/When/Then form.

---

## Table of Contents

- [Overview](#overview)
- [Quick Start Guide](#quick-start-guide)
- [Epic Documentation](#epic-documentation)
- [Feature Index](#feature-index)
- [Story Directory Structure](#story-directory-structure)
- [Templates](#templates)
- [Constraints Summary](#constraints-summary)
- [Target Users](#target-users)
- [Documentation Statistics](#documentation-statistics)
- [Contributing](#contributing)
- [References](#references)

---

## Overview

This documentation suite defines the requirements for turning Odoo's invoicing layer into a full accounting platform for a multi-entity group: a governed chart of accounts and fiscal calendar, accounts payable and accounts receivable with balanced posting, bank and cash reconciliation, tax determination and statutory filing, intercompany accounting with group consolidation, statutory and management reporting under a controlled period close, fixed-asset depreciation, and budget-versus-actual analysis. The epic encompasses nine features decomposed into forty-one user stories, each with BDD-style acceptance criteria.

### Documentation Purpose

| Audience | Purpose |
|----------|---------|
| **Product Managers** | Understand feature scope, priorities, and success metrics |
| **Developers** | Implementation requirements via user stories and acceptance criteria |
| **QA Engineers** | Testable acceptance criteria in Given/When/Then format |
| **Stakeholders** | Business value and feature overview |

### Documentation Structure

```text
tickets/
├── README.md                                                # This file - navigation index
├── EPIC-001-enterprise-accounting-odoo.md                   # Master epic document
├── EPIC-001/                                                # Feature specifications (9) + story directories (9)
│   ├── FEATURE-001-01-chart-of-accounts-fiscal-year.md
│   ├── FEATURE-001-01/                                      # 5 stories
│   ├── FEATURE-001-02-accounts-payable-vendor-bills.md
│   ├── FEATURE-001-02/                                      # 5 stories
│   ├── FEATURE-001-03-accounts-receivable-customer-invoices.md
│   ├── FEATURE-001-03/                                      # 5 stories
│   ├── FEATURE-001-04-bank-reconciliation-cash-management.md
│   ├── FEATURE-001-04/                                      # 4 stories
│   ├── FEATURE-001-05-tax-configuration-compliance.md
│   ├── FEATURE-001-05/                                      # 4 stories
│   ├── FEATURE-001-06-multi-company-consolidation.md
│   ├── FEATURE-001-06/                                      # 5 stories
│   ├── FEATURE-001-07-financial-reporting-period-close.md
│   ├── FEATURE-001-07/                                      # 5 stories
│   ├── FEATURE-001-08-fixed-assets-depreciation.md
│   ├── FEATURE-001-08/                                      # 4 stories
│   ├── FEATURE-001-09-budgeting-variance-analysis.md
│   └── FEATURE-001-09/                                      # 4 stories
└── templates/                                               # Reusable templates (3)
```

The tree self-documents its Epic → Feature → Story hierarchy through a fixed naming convention: `EPIC-001-slug.md` at the root of `tickets/`, `EPIC-001/FEATURE-001-NN-slug.md` for each feature, and `EPIC-001/FEATURE-001-NN/STORY-001-NN-SS-slug.md` for each story, where `NN` is the feature number and `SS` is the story number within that feature. Both numbers are zero-padded and every slug is kebab-case.

---

## Quick Start Guide

### Finding Documentation

1. **Start with the Epic**: Read [EPIC-001-enterprise-accounting-odoo.md](EPIC-001-enterprise-accounting-odoo.md) for complete context, quantified business value, module scope, dependencies, and constraints.

2. **Explore Features**: The nine feature specifications live in `EPIC-001/` as `FEATURE-001-NN-slug.md`. The [Feature Index](#feature-index) links every one of them with its story count, priority and Odoo module scope.

3. **Review User Stories**: The forty-one story files live in `EPIC-001/FEATURE-001-NN/` as `STORY-001-NN-SS-slug.md`, one directory per feature. The [Story Directory Structure](#story-directory-structure) links every one of them with its title and primary finance persona.

4. **Use Templates**: Create new documentation using standardized [templates/](#templates).

### Understanding the Format

All user stories follow this structure:

```markdown
# STORY-001-NN-SS: [Action + Object + Outcome]

## Metadata

| Attribute | Value |
|-----------|-------|
| **Story ID** | `STORY-001-NN-SS` |
| **Parent Feature** | [FEATURE-001-NN: Feature Name](../FEATURE-001-NN-slug.md) |
| **Parent Epic** | [EPIC-001](../../EPIC-001-enterprise-accounting-odoo.md) |
| **Primary Persona** | [named finance role] |
| **Estimate** | [Fibonacci: 1, 2, 3, 5, 8 or 13] story points |

## User Story

**As a** [named finance role]
**I want** [capability, stated against a specific Odoo object]
**So that** [measurable finance outcome]

## Acceptance Criteria

### Scenario 1: [Scenario Name]

- **Given** [precondition, naming the company and the accounting period]
- **When** [one action]
- **Then** [asserted outcome: currency, amount and rounding on every monetary
  value, and total debits equal to total credits on every journal entry]

## Sub-Tasks

- [ ] @functional-consultant [configuration task]
- [ ] @developer [implementation task]
- [ ] @qa-engineer [test task]
- [ ] @finance-sme [reconciliation sign-off]

## Edge Cases

- [3 to 5 accounting edge cases: zero-amount line, locked fiscal period,
  foreign-currency rounding, intercompany elimination]

## Estimation

- Effort, Complexity and Uncertainty, plus a Fibonacci point value

## Definition of Done

- [ ] Accounting reconciliation gate: debits equal credits, tax amounts
      reconcile, report lines tie to the sub-ledger
```

Each story carries 4 to 8 Given/When/Then acceptance criteria, `@assignee` sub-tasks across the Functional Consultant, Developer, QA and Finance SME roles, 3 to 5 accounting edge cases, its Odoo dependencies, estimation guidance (Effort, Complexity and Uncertainty plus a Fibonacci point value), and a Definition of Done whose accounting-reconciliation gate asserts that debits equal credits, that tax amounts reconcile, and that report lines tie to the sub-ledger.

### Navigation Tips

- **By Feature**: Use the [Feature Index](#feature-index) table to find stories by accounting sub-domain
- **By Persona**: The [Target Users](#target-users) section maps the named finance roles to relevant features
- **By Priority**: Features marked **Critical** should be implemented first

---

## Epic Documentation

### Master Epic

| Document | Description |
|----------|-------------|
| **[EPIC-001: Implement Enterprise-Grade Accounting in Odoo to Deliver Multi-Entity Financial Operations, Compliance Reporting, and Real-Time Financial Visibility](EPIC-001-enterprise-accounting-odoo.md)** | Complete epic specification including business context, success metrics, feature overview, Odoo module scope, constraints, out-of-scope items, dependencies, discovery notes, references, and the Epic-level Definition of Done |

The epic document serves as the authoritative source for:

- Business problem statement and value proposition
- Success metrics and KPIs, including the close-cycle, reporting-SLA and audit-adjustment targets
- Feature-to-story mapping and the decomposition bounds this tree is held to
- Odoo module scope, in and out, per feature
- Implementation constraints (license, dependencies, coding standards, test coverage, security)
- **Platform version and edition lock-in** — the Odoo version target (DEC-001) and the Enterprise-versus-OCA edition source (DEC-002) are recorded as epic dependencies, not resolved here
- Country localization, data migration, banking and tax-authority integration, and master-data dependencies
- Codebase discovery notes for implementing agents
- **Open decisions register** — DEC-001 through DEC-011, each with a named owner and a gate. Ten are **open** and awaiting stakeholder confirmation; **DEC-003** (disposition of the superseded flat-layout backlog) is **decided and closed** — remove — because the repository already reflects it, and the register keeps the row with its chosen option rather than dropping it
- External references (OCA repositories, official Odoo documentation, accounting standards, data formats)

---

## Feature Index

| Feature ID | Feature Name | Stories | Priority | Description |
|------------|--------------|:-------:|:--------:|-------------|
| [FEATURE-001-01](EPIC-001/FEATURE-001-01-chart-of-accounts-fiscal-year.md) | **Chart of Accounts & Fiscal Year** | 5 | 🔴 Critical | Chart of accounts hierarchy, IFRS/GAAP taxonomy mapping, fiscal year and periods, period lock dates; `account`, `l10n_*` |
| [FEATURE-001-02](EPIC-001/FEATURE-001-02-accounts-payable-vendor-bills.md) | **Accounts Payable & Vendor Bills** | 5 | 🔴 Critical | Vendor bill capture, three-way match, posting, batch payments, credit notes; `account`, `account_payment` |
| [FEATURE-001-03](EPIC-001/FEATURE-001-03-accounts-receivable-customer-invoices.md) | **Accounts Receivable & Customer Invoices** | 5 | 🔴 Critical | Invoicing, payment registration, credit notes, dunning, aged receivables; `account`, `account_payment` |
| [FEATURE-001-04](EPIC-001/FEATURE-001-04-bank-reconciliation-cash-management.md) | **Bank Reconciliation & Cash Management** | 4 | 🔴 Critical | Statement import, automatic and manual matching, cash registers; `account`, `account_payment` |
| [FEATURE-001-05](EPIC-001/FEATURE-001-05-tax-configuration-compliance.md) | **Tax Configuration & Compliance** | 4 | 🔴 Critical | Tax codes, fiscal positions, VAT return, e-invoicing submission; `account`, `l10n_*` |
| [FEATURE-001-06](EPIC-001/FEATURE-001-06-multi-company-consolidation.md) | **Multi-Company & Intercompany Consolidation** | 5 | 🟠 High | Company hierarchy, intercompany postings, consolidation rules, eliminations, consolidated statements; `account`, `account_consolidation` |
| [FEATURE-001-07](EPIC-001/FEATURE-001-07-financial-reporting-period-close.md) | **Financial Reporting & Period Close** | 5 | 🔴 Critical | Balance Sheet, P&L, Cash Flow, General Ledger and Trial Balance, period close with deferred revenue/expense cutoff; `account`, `account_reports` |
| [FEATURE-001-08](EPIC-001/FEATURE-001-08-fixed-assets-depreciation.md) | **Fixed Assets & Depreciation** | 4 | 🟠 High | Asset registration, depreciation methods and board, automated entries, disposal with gain/loss; `account`, `account_asset` |
| [FEATURE-001-09](EPIC-001/FEATURE-001-09-budgeting-variance-analysis.md) | **Budgeting & Variance Analysis** | 4 | 🟠 High | Budget definition by analytic account, period allocation, budget-vs-actual, variance analysis and alerts; `account`, `account_budget` |

**Total:** 9 features indexing 41 user stories (5 + 5 + 5 + 4 + 4 + 5 + 5 + 4 + 4).

### Priority Legend

| Priority | Meaning | Implementation Phase |
|----------|---------|---------------------|
| 🔴 **Critical** | Core functionality; a closed, compliant period is impossible without it | Phase 1 |
| 🟠 **High** | Important features; consumes the posted record that critical features create | Phase 2-3 |

Six features are Critical — FEATURE-001-01, FEATURE-001-02, FEATURE-001-03, FEATURE-001-04, FEATURE-001-05 and FEATURE-001-07 — because they govern where and when entries post, create and settle the balances, determine the filing position, and publish and lock the result. Three features are High — FEATURE-001-06, FEATURE-001-08 and FEATURE-001-09 — because they consume that posted record rather than create it. No feature in this epic is Medium or Low; all nine are required for the full release.

---

## Story Directory Structure

Story files are grouped one directory per feature under `EPIC-001/`. The persona named in each row is the story's WHO; the full role definitions are in [Target Users](#target-users).

### FEATURE-001-01 Chart of Accounts & Fiscal Year (5 Stories)

| Story ID | Title | Primary Persona |
|----------|-------|-----------------|
| [STORY-001-01-01](EPIC-001/FEATURE-001-01/STORY-001-01-01-configure-coa-hierarchy.md) | Configure Multi-Level Chart of Accounts Hierarchy | Chief Accountant |
| [STORY-001-01-02](EPIC-001/FEATURE-001-01/STORY-001-01-02-map-accounts-ifrs-gaap-taxonomy.md) | Map Accounts to IFRS and GAAP Reporting Taxonomy | Financial Reporting Manager |
| [STORY-001-01-03](EPIC-001/FEATURE-001-01/STORY-001-01-03-define-fiscal-year-periods.md) | Define Fiscal Year and Accounting Periods | Chief Accountant |
| [STORY-001-01-04](EPIC-001/FEATURE-001-01/STORY-001-01-04-import-legacy-coa.md) | Import Legacy Chart of Accounts and Opening Balances | Chief Accountant |
| [STORY-001-01-05](EPIC-001/FEATURE-001-01/STORY-001-01-05-configure-period-lock-dates.md) | Configure Period Lock Dates and Closing Controls | Group Controller |

### FEATURE-001-02 Accounts Payable & Vendor Bills (5 Stories)

| Story ID | Title | Primary Persona |
|----------|-------|-----------------|
| [STORY-001-02-01](EPIC-001/FEATURE-001-02/STORY-001-02-01-capture-vendor-bills.md) | Capture and Digitize Vendor Bills | Accounts Payable Clerk |
| [STORY-001-02-02](EPIC-001/FEATURE-001-02/STORY-001-02-02-three-way-match.md) | Perform Three-Way Match Across Purchase Order, Receipt and Bill | Accounts Payable Clerk |
| [STORY-001-02-03](EPIC-001/FEATURE-001-02/STORY-001-02-03-post-vendor-bill-entries.md) | Post Vendor Bill Journal Entries | Chief Accountant |
| [STORY-001-02-04](EPIC-001/FEATURE-001-02/STORY-001-02-04-batch-vendor-payments.md) | Schedule and Batch Vendor Payments | Treasury Analyst |
| [STORY-001-02-05](EPIC-001/FEATURE-001-02/STORY-001-02-05-manage-vendor-credit-notes.md) | Manage Vendor Credit Notes and Refunds | Accounts Payable Clerk |

### FEATURE-001-03 Accounts Receivable & Customer Invoices (5 Stories)

| Story ID | Title | Primary Persona |
|----------|-------|-----------------|
| [STORY-001-03-01](EPIC-001/FEATURE-001-03/STORY-001-03-01-generate-customer-invoices.md) | Generate and Post Customer Invoices | Accounts Receivable Specialist |
| [STORY-001-03-02](EPIC-001/FEATURE-001-03/STORY-001-03-02-register-customer-payments.md) | Register Customer Payments and Allocations | Accounts Receivable Specialist |
| [STORY-001-03-03](EPIC-001/FEATURE-001-03/STORY-001-03-03-manage-customer-credit-notes.md) | Manage Customer Credit Notes and Refunds | Accounts Receivable Specialist |
| [STORY-001-03-04](EPIC-001/FEATURE-001-03/STORY-001-03-04-configure-payment-followups.md) | Configure Automated Payment Follow-Ups | Accounts Receivable Specialist |
| [STORY-001-03-05](EPIC-001/FEATURE-001-03/STORY-001-03-05-report-aged-receivables.md) | Generate Aged Receivables Report | Financial Reporting Manager |

### FEATURE-001-04 Bank Reconciliation & Cash Management (4 Stories)

| Story ID | Title | Primary Persona |
|----------|-------|-----------------|
| [STORY-001-04-01](EPIC-001/FEATURE-001-04/STORY-001-04-01-import-bank-statements.md) | Import Bank Statements in CSV, OFX, QIF and CAMT.053 | Treasury Analyst |
| [STORY-001-04-02](EPIC-001/FEATURE-001-04/STORY-001-04-02-auto-match-statement-lines.md) | Auto-Match Statement Lines with Reconciliation Rules | Treasury Analyst |
| [STORY-001-04-03](EPIC-001/FEATURE-001-04/STORY-001-04-03-manual-reconciliation.md) | Manually Reconcile Unmatched and Partial Lines | Chief Accountant |
| [STORY-001-04-04](EPIC-001/FEATURE-001-04/STORY-001-04-04-manage-cash-registers.md) | Manage Cash Registers and Petty Cash | Treasury Analyst |

### FEATURE-001-05 Tax Configuration & Compliance (4 Stories)

| Story ID | Title | Primary Persona |
|----------|-------|-----------------|
| [STORY-001-05-01](EPIC-001/FEATURE-001-05/STORY-001-05-01-configure-tax-codes-fiscal-positions.md) | Configure Tax Codes and Fiscal Positions | Tax Accountant |
| [STORY-001-05-02](EPIC-001/FEATURE-001-05/STORY-001-05-02-compute-transaction-tax.md) | Compute Tax on Transactions with Base and Tax Split | Tax Accountant |
| [STORY-001-05-03](EPIC-001/FEATURE-001-05/STORY-001-05-03-generate-vat-return.md) | Generate VAT Return Report | Tax Accountant |
| [STORY-001-05-04](EPIC-001/FEATURE-001-05/STORY-001-05-04-submit-einvoicing.md) | Submit E-Invoicing to Tax-Authority Endpoints | Tax Accountant |

### FEATURE-001-06 Multi-Company & Intercompany Consolidation (5 Stories)

| Story ID | Title | Primary Persona |
|----------|-------|-----------------|
| [STORY-001-06-01](EPIC-001/FEATURE-001-06/STORY-001-06-01-configure-company-hierarchy.md) | Configure Company Hierarchy and Currencies | Group Controller |
| [STORY-001-06-02](EPIC-001/FEATURE-001-06/STORY-001-06-02-post-intercompany-transactions.md) | Post Intercompany Transactions | Consolidation Accountant |
| [STORY-001-06-03](EPIC-001/FEATURE-001-06/STORY-001-06-03-define-consolidation-rules.md) | Define Consolidation Rules | Group Controller |
| [STORY-001-06-04](EPIC-001/FEATURE-001-06/STORY-001-06-04-eliminate-intercompany-balances.md) | Eliminate Intercompany Balances | Consolidation Accountant |
| [STORY-001-06-05](EPIC-001/FEATURE-001-06/STORY-001-06-05-generate-consolidated-financials.md) | Generate Consolidated Financial Statements | Financial Reporting Manager |

### FEATURE-001-07 Financial Reporting & Period Close (5 Stories)

| Story ID | Title | Primary Persona |
|----------|-------|-----------------|
| [STORY-001-07-01](EPIC-001/FEATURE-001-07/STORY-001-07-01-generate-balance-sheet.md) | Generate Balance Sheet | Financial Reporting Manager |
| [STORY-001-07-02](EPIC-001/FEATURE-001-07/STORY-001-07-02-generate-profit-loss.md) | Generate Profit & Loss Statement | Financial Reporting Manager |
| [STORY-001-07-03](EPIC-001/FEATURE-001-07/STORY-001-07-03-generate-cash-flow-statement.md) | Generate Cash Flow Statement | Financial Reporting Manager |
| [STORY-001-07-04](EPIC-001/FEATURE-001-07/STORY-001-07-04-generate-general-ledger-trial-balance.md) | Generate General Ledger and Trial Balance | Chief Accountant |
| [STORY-001-07-05](EPIC-001/FEATURE-001-07/STORY-001-07-05-execute-period-close-deferrals.md) | Execute Period-End Close with Deferred Revenue and Expense Cutoff | Chief Accountant |

### FEATURE-001-08 Fixed Assets & Depreciation (4 Stories)

| Story ID | Title | Primary Persona |
|----------|-------|-----------------|
| [STORY-001-08-01](EPIC-001/FEATURE-001-08/STORY-001-08-01-register-fixed-assets.md) | Register Fixed Assets with Acquisition Detail | Fixed-Asset Accountant |
| [STORY-001-08-02](EPIC-001/FEATURE-001-08/STORY-001-08-02-configure-depreciation-methods.md) | Configure Depreciation Methods and Projected Board | Fixed-Asset Accountant |
| [STORY-001-08-03](EPIC-001/FEATURE-001-08/STORY-001-08-03-post-depreciation-entries.md) | Post Automated Depreciation Entries | Chief Accountant |
| [STORY-001-08-04](EPIC-001/FEATURE-001-08/STORY-001-08-04-dispose-assets.md) | Dispose of Assets with Gain or Loss Recognition | Fixed-Asset Accountant |

### FEATURE-001-09 Budgeting & Variance Analysis (4 Stories)

| Story ID | Title | Primary Persona |
|----------|-------|-----------------|
| [STORY-001-09-01](EPIC-001/FEATURE-001-09/STORY-001-09-01-define-budgets.md) | Define Budgets by Account and Analytic Dimension | FP&A Analyst |
| [STORY-001-09-02](EPIC-001/FEATURE-001-09/STORY-001-09-02-allocate-budget-periods.md) | Allocate Budget Amounts Across Periods | FP&A Analyst |
| [STORY-001-09-03](EPIC-001/FEATURE-001-09/STORY-001-09-03-report-budget-vs-actual.md) | Report Budget vs. Actual | FP&A Analyst |
| [STORY-001-09-04](EPIC-001/FEATURE-001-09/STORY-001-09-04-analyze-variances.md) | Analyse Variances and Configure Threshold Alerts | Group Controller |

---

## Templates

Reusable templates for creating consistent documentation:

| Template | Purpose | Usage |
|----------|---------|-------|
| [epic-template.md](templates/epic-template.md) | Create new epic documents | Use when defining a new major initiative with multiple features |
| [feature-template.md](templates/feature-template.md) | Create feature specifications | Use when decomposing an epic into feature areas |
| [story-template.md](templates/story-template.md) | Create user stories with BDD acceptance criteria | Use when defining individual user stories within a feature |

### Template Standards

What the three retained templates supply, and what this backlog adds on top of them:

| Requirement | Supplied by the retained template | Added by this backlog |
|-------------|-----------------------------------|-----------------------|
| **INVEST Principles**: Independent, Negotiable, Valuable, Estimable, Small, Testable | Yes — the story template carries an INVEST compliance section | Each story states its compliance per principle rather than asserting the set |
| **BDD Format**: Given/When/Then acceptance criteria | Yes — the story template's scenario skeleton | The coverage distribution and the accounting-determinism rules below |
| **Business Value**: explicit "So that" clause | Yes — the "As a / I want / So that" skeleton | The measurable finance outcome the clause has to state |
| **Persona Focus**: a named finance role as the story's WHO | **No.** `story-template.md` offers a generic role placeholder and carries no persona field and no enforcement | This backlog supersedes that gap: every story carries a **Primary Persona** metadata row drawn from the twelve named roles in [Target Users](#target-users), and the epic's [§3.2 persona notes](EPIC-001-enterprise-accounting-odoo.md#32-persona-notes) publish the primary-persona census that proves it |

The three template files are retained unmodified and remain the authoritative source for section ordering. Two pieces of counting guidance inside them are **superseded for this backlog** by the bounds the epic sets in [§5.3 of EPIC-001](EPIC-001-enterprise-accounting-odoo.md#53-feature-and-story-decomposition-guidelines), and the templates are not edited to reflect that:

| Template guidance | Superseded by, for this backlog |
|-------------------|--------------------------------|
| `epic-template.md` and `feature-template.md`: 3-7 stories per feature | **2 to 5 stories per feature** — this backlog uses 4 or 5 |
| `story-template.md`: 3-6 acceptance criteria scenarios per story | **4 to 8 acceptance criteria per story**, with the coverage distribution in [Acceptance Criteria Constraint](#acceptance-criteria-constraint) |
| `story-template.md`: generic persona options | The twelve named finance roles in [Target Users](#target-users) |

---

## Constraints Summary

All implementations under this epic must adhere to the following constraints. The identifiers below are this index's own summary IDs; each row cites the authoritative constraint in [§7 of EPIC-001](EPIC-001-enterprise-accounting-odoo.md#7-constraints), whose register runs from C-001 to C-022.

| Constraint ID | Requirement | Description |
|---------------|-------------|-------------|
| **C-001** | 🔒 **AGPL-3.0 Compatible License** | New modules are distributed under an AGPL-3.0 compatible license for free redistribution, and integration with the `account` module respects its LGPL-3 license (epic C-001, C-002) |
| **C-002** | ❓ **Edition Lock-In — Open Decision** | Four in-scope modules (`account_reports`, `account_asset`, `account_budget`, `account_consolidation`) are Enterprise capabilities and are absent from this Community repository. The delivery path — an Odoo Enterprise subscription versus OCA community add-ons such as `account_financial_report`, `account_reconcile_oca` and `mis_builder` — is decision **DEC-002**, flagged for stakeholder confirmation and gated before FEATURE-001-06, FEATURE-001-07, FEATURE-001-08 and FEATURE-001-09 enter development. This is an open choice, not a prohibition on Enterprise (epic C-003, C-004) |
| **C-003** | 📏 **OCA and Odoo Coding Standards** | Follow Odoo and OCA development guidelines, including PEP 8, and pass static analysis with the repository's `ruff.toml` configuration (epic C-005, C-006) |
| **C-004** | ✅ **80% Test Coverage** | Minimum test coverage for all new functionality, with accounting assertions tested numerically: debits equal credits, tax amounts reconcile to tax control accounts, report lines tie to sub-ledger totals (epic C-007, C-008, C-009) |
| **C-005** | ❓ **Platform Version Target — Open Decision** | Three platform targets are on record and they are mutually exclusive: the programme request names **Odoo 17**, the prior superseded backlog targeted **Odoo 18.0**, and this repository is **Odoo 19.0 Community** (`version_info = (19, 0, 0, FINAL, 0, '')` in `odoo/release.py`). Odoo 19.0 Community is therefore the baseline present here, while the programme target is decision **DEC-001**, flagged for stakeholder confirmation. Every version-bearing statement in the tree — including the documentation URLs in [References](#references) — cites the 19.0 baseline and is restated if DEC-001 confirms another version (epic C-010, C-011) |
| **C-006** | 🗂️ **Nested Naming Convention** | Ticket files follow `EPIC-001-slug.md`, `EPIC-001/FEATURE-001-NN-slug.md` and `EPIC-001/FEATURE-001-NN/STORY-001-NN-SS-slug.md`, with zero-padded numbers, kebab-case slugs, and relative links that resolve inside `tickets/` |

### Acceptance Criteria Constraint

Every user story carries **4 to 8 Given/When/Then acceptance criteria**, and those criteria must cover, at minimum:

| Coverage category | What the criterion asserts |
|-------------------|----------------------------|
| Valid input | The happy-path posting or report succeeds with its expected values |
| Invalid or incomplete input | A rejected entry — for example an unbalanced journal entry or a missing tax code |
| Error handling | The Odoo validation message raised, or the posting blocked, and the state left unchanged |
| Accounting edge case | A zero-amount line, a locked fiscal period, foreign-currency rounding, or an intercompany elimination |

Each criterion is written to these accounting-determinism rules:

- Monetary assertions state the **currency**, the **amount** and the **rounding** applied (for example `USD 12,450.00` rounded to 2 decimal places, half-up).
- Journal-entry criteria assert that **total debits equal total credits** — a difference of 0.00 in the company currency.
- Tax criteria separate the **tax code**, the **base amount** and the **tax amount**.
- Report criteria name the **report**, a **date-range parameter** and at least one **expected line value**.
- Multi-company criteria name the **company** whose books are affected.
- Account codes, journal types and report names are cited deterministically (for example Accounts Payable `2000`, Expense `6100`, journal type `purchase`, report **Trial Balance**).

Acceptance criteria must contain **zero occurrences** of the following vague qualifiers, because each one admits more than one pass-or-fail reading:

```text
approximately, several, various, adequate, appropriate, properly, correctly,
efficiently, quickly, easily, user-friendly, reasonable, sufficient
```

Every user story must also include these inherited compliance constraints as acceptance criteria:

```markdown
- Module distributed under an AGPL-3.0 compatible license
- No undeclared dependency on an Odoo Enterprise edition module; the edition source is DEC-002
- Implementation follows Odoo and OCA coding standards
- Implementation achieves minimum 80% test coverage
```

---

## Target Users

### User Persona Definitions

Every persona below is a named finance role. The WHO of each user story is drawn from this list; the generic word "user" is not a persona.

| Persona | Role Description | Primary Responsibilities |
|---------|------------------|-------------------------|
| **Chief Accountant** | Owns the general ledger, the chart of accounts and the integrity of every posted entry | Account hierarchy governance, fiscal calendar, lock dates, balanced postings, period close |
| **Financial Reporting Manager** | Produces statutory and management statements for each entity and for the group | Named statements with date-range parameters, sub-ledger tie-out, comparative periods, aged receivables |
| **Accounts Payable Clerk** | Captures vendor bills, runs three-way match and prepares payment runs | Bill capture, purchase-order and receipt matching, vendor credit notes |
| **Accounts Receivable Specialist** | Issues customer invoices, allocates receipts and manages collections | Invoice posting, payment allocation, customer credit notes, dunning ladder |
| **Treasury Analyst** | Owns bank and cash positions and statement reconciliation | Statement import, automatic and manual matching, cash register control, payment batches |
| **Tax Accountant** | Determines tax on transactions and files statutory returns | Tax codes, fiscal positions, base-and-tax split, VAT return, e-invoicing submission |
| **Group Controller** | Governs group accounting policy and approves the consolidated result | Company hierarchy, intercompany policy, lock-date approval, consolidated statements, variance thresholds |
| **Consolidation Accountant** | Executes consolidation runs, eliminations and currency translation | Consolidation rules, intercompany elimination proof, translation differences |
| **Fixed-Asset Accountant** | Maintains the asset register and depreciation schedules | Asset registration, depreciation methods and board, disposal gain or loss |
| **FP&A Analyst** | Builds budgets and explains variances to management | Budget definition, period allocation, budget-versus-actual reporting |
| **External Auditor** | Tests balances and controls and issues the audit opinion | Immutable audit trail, drill-down from statement line to journal item, elimination and reconciliation evidence |
| **CFO / Finance Director** | Executive stakeholder accountable for financial health and compliance | Group financial position, close status, cash and receivables health, compliance status |

### Feature-to-Persona Mapping

| Feature | Chief Accountant | Financial Reporting Manager | AP Clerk | AR Specialist | Treasury Analyst | Tax Accountant | Group Controller | Consolidation Accountant | Fixed-Asset Accountant | FP&A Analyst | External Auditor | CFO / Finance Director |
|---------|:----------------:|:---------------------------:|:--------:|:-------------:|:----------------:|:--------------:|:----------------:|:------------------------:|:----------------------:|:------------:|:----------------:|:---------------------:|
| FEATURE-001-01 Chart of Accounts & Fiscal Year | ✅ | ✅ | | | | | ✅ | | | | ✅ | |
| FEATURE-001-02 Accounts Payable & Vendor Bills | ✅ | | ✅ | | ✅ | | | | | | | |
| FEATURE-001-03 Accounts Receivable & Customer Invoices | | ✅ | | ✅ | | | | | | | | |
| FEATURE-001-04 Bank Reconciliation & Cash Management | ✅ | | | | ✅ | | | | | | | |
| FEATURE-001-05 Tax Configuration & Compliance | | | | | | ✅ | | | | | | |
| FEATURE-001-06 Multi-Company & Intercompany Consolidation | | ✅ | | | | | ✅ | ✅ | | | ✅ | ✅ |
| FEATURE-001-07 Financial Reporting & Period Close | ✅ | ✅ | | | | | ✅ | | | | ✅ | ✅ |
| FEATURE-001-08 Fixed Assets & Depreciation | ✅ | | | | | | | | ✅ | | | |
| FEATURE-001-09 Budgeting & Variance Analysis | | | | | | | ✅ | | | ✅ | | ✅ |

---

## Documentation Statistics

### File Inventory

| Category | Count | Status |
|----------|:-----:|:------:|
| README (this file) | 1 | ✅ |
| Epic Documents | 1 | ✅ |
| Feature Specifications | 9 | 📝 |
| User Stories | 41 | 📝 |
| Templates | 3 | 📝 |
| **Total** | **55** | |

### Story Distribution

```text
FEATURE-001-01  Chart of Accounts & Fiscal Year             ██████████████████████████████░░░  5 (12%)
FEATURE-001-02  Accounts Payable & Vendor Bills             ██████████████████████████████░░░  5 (12%)
FEATURE-001-03  Accounts Receivable & Customer Invoices     ██████████████████████████████░░░  5 (12%)
FEATURE-001-04  Bank Reconciliation & Cash Management       ████████████████████████░░░░░░░░░  4 (10%)
FEATURE-001-05  Tax Configuration & Compliance              ████████████████████████░░░░░░░░░  4 (10%)
FEATURE-001-06  Multi-Company & Intercompany Consolidation  ██████████████████████████████░░░  5 (12%)
FEATURE-001-07  Financial Reporting & Period Close          ██████████████████████████████░░░  5 (12%)
FEATURE-001-08  Fixed Assets & Depreciation                 ████████████████████████░░░░░░░░░  4 (10%)
FEATURE-001-09  Budgeting & Variance Analysis               ████████████████████████░░░░░░░░░  4 (10%)
                                                                                             Total: 41
```

### Priority Distribution

| Priority | Features | Stories |
|----------|:--------:|:-------:|
| 🔴 Critical | 6 | 21 |
| 🟠 High | 3 | 18 |
| 🟡 Medium | 0 | 2 |
| **Total** | **9** | **41** |

Story priority is set per story and does not simply inherit its feature's priority: a Critical feature can carry a High story where that story consumes rather than creates the posted record, which is why the story column reads 21 / 18 / 2 while the feature column reads 6 / 3 / 0. The two Medium stories are [STORY-001-08-04](EPIC-001/FEATURE-001-08/STORY-001-08-04-dispose-assets.md) (asset disposal) and [STORY-001-09-04](EPIC-001/FEATURE-001-09/STORY-001-09-04-analyze-variances.md) (variance analysis and threshold alerts); each is a metadata value in its own file, and this table is the count of those values.

---

## Contributing

### Adding New Documentation

1. **New Stories**: Copy [templates/story-template.md](templates/story-template.md), follow the BDD format, and save the file as `EPIC-001/FEATURE-001-NN/STORY-001-NN-SS-slug.md` inside its parent feature's story directory, then add it to that feature's User Stories Index and to the [Story Directory Structure](#story-directory-structure) above.
2. **New Features**: Copy [templates/feature-template.md](templates/feature-template.md), save the file as `EPIC-001/FEATURE-001-NN-slug.md`, create the sibling `EPIC-001/FEATURE-001-NN/` directory for its stories, then add it to the epic's Features Index and to the [Feature Index](#feature-index) above.
3. **New Epics**: Copy [templates/epic-template.md](templates/epic-template.md) for major initiatives, saving the file as `EPIC-NUM-slug.md` at the root of `tickets/` alongside a sibling `EPIC-NUM/` directory that holds its features.

### Documentation Standards

- Use ATX-style headers (`#`, `##`, `###`)
- Format tables with pipe delimiters and header separators
- Use relative links for cross-references within `tickets/`
- Include Mermaid diagrams for complex workflows
- Follow markdown linting rules

### Review Checklist

Before submitting documentation changes:

- [ ] User story follows "As a / I want / So that" format
- [ ] The WHO is a named finance role from [Target Users](#target-users), never the generic word "user"
- [ ] Story satisfies INVEST: Independent, Negotiable, Valuable, Estimable, Small, Testable
- [ ] Acceptance criteria use Given/When/Then format
- [ ] 4-8 acceptance criteria per story, covering at least one valid input, one invalid or incomplete input, one error-handling case and one accounting edge case
- [ ] Zero forbidden vague qualifiers in any acceptance criterion (see [Acceptance Criteria Constraint](#acceptance-criteria-constraint))
- [ ] Every monetary assertion states currency, amount and rounding
- [ ] Every journal-entry criterion asserts that total debits equal total credits
- [ ] Tax criteria split tax code, base amount and tax amount; report criteria name the report, a date-range parameter and one expected line value; multi-company criteria name the affected company
- [ ] Estimate is a Fibonacci value (1, 2, 3, 5, 8, 13) with Effort, Complexity and Uncertainty recorded
- [ ] Story is demonstrable in the Odoo user interface, or through its public API, to the Finance Controller and Product Owner
- [ ] No UI/implementation details in criteria
- [ ] Constraints section includes all C-001 through C-006 requirements
- [ ] File name follows the `EPIC-001` / `FEATURE-001-NN` / `STORY-001-NN-SS` convention, and links to related stories and features resolve

---

## References

### External Resources

| Resource | URL |
|----------|-----|
| Odoo Developer Documentation | <https://www.odoo.com/documentation/19.0/developer.html> |
| Odoo Accounting User Documentation | <https://www.odoo.com/documentation/19.0/applications/finance/accounting.html> |
| Odoo Editions Comparison (Community versus Enterprise) | <https://www.odoo.com/page/editions> |
| OCA Contribution and Development Guidelines | <https://github.com/OCA/odoo-community.org/blob/master/website/Contribution/CONTRIBUTING.rst> — the maintained GitHub-hosted source, cited here and in [§11.2 of EPIC-001](EPIC-001-enterprise-accounting-odoo.md#112-official-odoo-documentation); the former `odoo-community.org/page/development-guidelines` page is no longer served and is not cited anywhere in this tree |
| Odoo Contributing Guidelines | [CONTRIBUTING.md](../CONTRIBUTING.md) |
| OCA Account Financial Reporting | <https://github.com/OCA/account-financial-reporting> |
| OCA Account Reconcile | <https://github.com/OCA/account-reconcile> |
| OCA MIS Builder | <https://github.com/OCA/mis-builder> |

Documentation URLs cite the 19.0 series because that is the repository baseline. If DEC-001 confirms another platform version (see **C-005** in [Constraints Summary](#constraints-summary)), every URL and API reference is restated for that version.

### Accounting Standards

| Standard | Application |
|----------|-------------|
| **GAAP** (US Generally Accepted Accounting Principles) | Balance Sheet, Profit & Loss and Cash Flow Statement presentation (FEATURE-001-07) |
| **IFRS** (International Financial Reporting Standards) | Group statement presentation and the reporting taxonomy accounts are mapped to (FEATURE-001-01, FEATURE-001-07) |
| **ASC 606 / IFRS 15** | Revenue recognition and deferred revenue within the period close (FEATURE-001-07) |
| **ASC 340-10 / IAS 1** | Prepaid and deferred expense recognition and its statement presentation (FEATURE-001-07) |
| **IAS 16 / ASC 360** | Fixed-asset capitalization, depreciation and disposal (FEATURE-001-08) |
| **IAS 21** | Foreign-currency translation and translation differences (FEATURE-001-06) |
| **IFRS 10 / ASC 810** | Consolidated financial statements and intercompany elimination (FEATURE-001-06) |
| **ISO 20022 / CAMT.053, OFX, QIF** | Bank statement import formats, alongside per-bank CSV mapping (FEATURE-001-04) |
| **EN 16931 / UBL 2.1 / PEPPOL BIS Billing 3.0** | Electronic invoice semantic model and delivery profile (FEATURE-001-05) |

---

- **Document Status:** Draft
- **Last Updated:** 2026-08-15
- **Maintained By:** Blitzy Platform — Finance Transformation Programme
