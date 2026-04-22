---
review_id: "cr-2026-04-21-archaeology"
generated_at: "2026-04-21T00:00:00Z"
base_commit: "b58d620c4fb"
head_commit: "5a7e83629bc"
archaeology_commits: 174
files_in_scope: 137
insertions: 61375
deletions: 2022
overall_status: "OPEN"
phases:
  - id: 1
    domain: "Infrastructure/DevOps"
    reviewer: "Blitzy DevOps Reviewer Agent"
    status: "OPEN"
    files_in_scope: 0
    findings_total: 0
    findings_addressed: 0
    blockers: []
  - id: 2
    domain: "Security"
    reviewer: "Blitzy Security Reviewer Agent"
    status: "OPEN"
    files_in_scope: 0
    findings_total: 0
    findings_addressed: 0
    blockers: []
  - id: 3
    domain: "Backend Architecture"
    reviewer: "Blitzy Backend Architect Agent"
    status: "OPEN"
    files_in_scope: 0
    findings_total: 0
    findings_addressed: 0
    blockers: []
  - id: 4
    domain: "QA/Test Integrity"
    reviewer: "Blitzy QA Integrity Agent"
    status: "OPEN"
    files_in_scope: 0
    findings_total: 0
    findings_addressed: 0
    blockers: []
  - id: 5
    domain: "Business/Domain"
    reviewer: "Blitzy Business Analyst Agent"
    status: "OPEN"
    files_in_scope: 0
    findings_total: 0
    findings_addressed: 0
    blockers: []
  - id: 6
    domain: "Frontend"
    reviewer: "Blitzy Frontend Reviewer Agent"
    status: "OPEN"
    files_in_scope: 0
    findings_total: 0
    findings_addressed: 0
    blockers: []
  - id: 7
    domain: "Other SME"
    reviewer: "Blitzy Documentation and Compliance SME Agent"
    status: "OPEN"
    files_in_scope: 0
    findings_total: 0
    findings_addressed: 0
    blockers: []
---

# CODE_REVIEW.md — Segmented PR Review (Archaeology + Retrospective)

> **Review scope**: every change merged into `origin/pdlc` that is not present on
> `origin/19.0`. **174 commits** across **137 files** (**+61,375 / −2,022 LOC**).
> Reviewed as if the merged content were authored during the current run per
> the user's *"treat all identified changes as if they were changes that were
> actively made during this run"* directive.

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Archaeology Report](#2-archaeology-report)
   - 2.1 [Commit Inventory](#21-commit-inventory)
   - 2.2 [File Inventory](#22-file-inventory)
   - 2.3 [Scope Statistics](#23-scope-statistics)
3. [Phase 1 — Infrastructure / DevOps](#3-phase-1--infrastructure--devops)
4. [Phase 2 — Security](#4-phase-2--security)
5. [Phase 3 — Backend Architecture](#5-phase-3--backend-architecture)
6. [Phase 4 — QA / Test Integrity](#6-phase-4--qa--test-integrity)
7. [Phase 5 — Business / Domain](#7-phase-5--business--domain)
8. [Phase 6 — Frontend](#8-phase-6--frontend)
9. [Phase 7 — Other SME (Documentation and Compliance)](#9-phase-7--other-sme-documentation-and-compliance)
10. [Consolidated Remediation Ledger](#10-consolidated-remediation-ledger)
11. [References](#11-references)

---

## 1. Executive Summary

| Field | Value |
|-------|-------|
| **Scope** | 174 commits (172 by `Blitzy Agent <agent@blitzy.com>` + 2 `blitzy[bot]` merges) across 137 files |
| **Base commit** | `b58d620c4fb` (tip of `origin/19.0`, Odoo 19.0 Community Edition) |
| **Head commit** | `5a7e83629bc` (tip of `origin/pdlc`, PR #3 merge commit) |
| **Merge commits** | `2c52c6b3aaf` (PR #2, 2026-02-02), `5a7e83629bc` (PR #3, 2026-04-17) |
| **Contributing branches** | `blitzy-4490115e-...` (scaffold + tickets via PR #2), `blitzy-ebbf6c96-...` (production impl via PR #3) |
| **Total change volume** | **137 files**, **+61,375 insertions**, **−2,022 deletions**, **+59,353 net LOC** |
| **Review Timeline** | Archaeology scaffold generated on 2026-04-21; per-phase reviews scheduled across subsequent checkpoints |
| **Review depth** | 7 sequential phases covering 7 engineering domains |
| **Verdict** | **OPEN** — 7 phase reviews scheduled across Checkpoints 2–5; no findings recorded yet at this scaffold milestone. Per-phase disposition will be recorded incrementally as each reviewer Agent completes its domain analysis, remediation, and verification. |

### 1.1 Headline Findings

At this scaffold milestone (Checkpoint 1), no per-phase findings have been
recorded. The archaeology (scope, commit inventory, file inventory, domain
assignment) is complete; the seven phase reviews themselves are deferred to
subsequent checkpoints per the Checkpoint Instructions. The observations below
are baseline metrics drawn from the merged-scope archaeology, not phase-review
findings:

- The merged scope covers **174 commits** (172 by `Blitzy Agent
  <agent@blitzy.com>` + 2 `blitzy[bot]` merges) touching **137 files**,
  **+61,375 insertions**, and **−2,022 deletions** between `origin/19.0`
  (`b58d620c4fb`) and `origin/pdlc` (`5a7e83629bc`).
- Every changed file has been assigned to exactly one of the seven review
  domains per the AAP §0.10.4 domain-assignment matrix — see
  [§2.2 File Inventory](#22-file-inventory).
- Per-phase analyses, findings, remediation logs, verification evidence, and
  dispositions will be populated in their respective sections (§3 through §9)
  as each subsequent checkpoint brings the corresponding source artifacts onto
  the working tree.

### 1.2 Review Pipeline

```mermaid
%%{init: {'theme':'base','themeVariables':{'primaryColor':'#F2F0FE','primaryTextColor':'#333333','primaryBorderColor':'#5B39F3','lineColor':'#999999','secondaryColor':'#F4EFF6'}}}%%
flowchart LR
    A[Archaeology Report] --> B[Phase 1: Infra/DevOps]
    B --> C[Phase 2: Security]
    C --> D[Phase 3: Backend Arch]
    D --> E[Phase 4: QA/Tests]
    E --> F[Phase 5: Business/Domain]
    F --> G[Phase 6: Frontend]
    G --> H[Phase 7: Other SME]
    H --> I[Consolidated Ledger]
    I --> J{Overall Disposition}
    J -->|All APPROVED| K[PR Ready]
    J -->|Any BLOCKED| L[Remediation Queue]
```

### 1.3 Phase Disposition Snapshot

| Phase | Domain | Reviewer Agent | Files | Findings | Addressed | Status |
|------:|--------|----------------|------:|---------:|----------:|:------:|
| 1 | Infrastructure / DevOps | Blitzy DevOps Reviewer Agent | 0 | 0 | 0 | **OPEN** |
| 2 | Security | Blitzy Security Reviewer Agent | 0 | 0 | 0 | **OPEN** |
| 3 | Backend Architecture | Blitzy Backend Architect Agent | 0 | 0 | 0 | **OPEN** |
| 4 | QA / Test Integrity | Blitzy QA Integrity Agent | 0 | 0 | 0 | **OPEN** |
| 5 | Business / Domain | Blitzy Business Analyst Agent | 0 | 0 | 0 | **OPEN** |
| 6 | Frontend | Blitzy Frontend Reviewer Agent | 0 | 0 | 0 | **OPEN** |
| 7 | Other SME (Documentation & Compliance) | Blitzy Documentation and Compliance SME Agent | 0 | 0 | 0 | **OPEN** |
| **Total** | — | — | **0** | **0** | **0** | **OPEN** |

*All seven phase reviews are OPEN at this scaffold milestone (Checkpoint 1).
`Files`, `Findings`, `Addressed`, and `Status` columns will be populated
incrementally as each subsequent checkpoint conducts the corresponding
per-phase review. No phase may transition to `APPROVED` until every addressable
finding is fixed and verified per AAP §0.10.3, and no phase may transition to
`BLOCKED` without an explicit rationale plus remediation steps.*

---

## 2. Archaeology Report

### 2.1 Commit Inventory

#### 2.1.1 Branch Attribution Summary

> **Note on the `blitzy-894f4afa-…` row:** The Carbon UI branch is included in
> this table **for archaeology completeness only**. Per AAP §0.8.2 it is
> **explicitly out of scope** for the Segmented PR Review — its 80 commits and
> 445 files under `addons/carbon_ui/` never reach `origin/pdlc` and are
> excluded from every downstream scope total (174 commits, 137 files,
> +61,375/−2,022 LOC). The row is informational-only and does not contribute
> to any phase's `files_in_scope` counter.

| Branch (origin/) | Commits not on 19.0 | Primary Scope | Merged to pdlc? |
|------------------|--------------------:|---------------|-----------------|
| `blitzy-226b0e2b-67da-4341-b2ee-58a436783f1b` | 49 | Early ticket-corpus exploration | Indirectly via PR #2 ancestry |
| `blitzy-4490115e-a8c5-4578-b273-3dbcba531e6d` | 134 | Accounting modules scaffold + story corpus | **Yes**, via PR #2 (merge `2c52c6b3aaf`) |
| `blitzy-894f4afa-8754-43b4-96e7-e9a811392193` | 80 | Carbon UI module (`addons/carbon_ui/`, 445 files) | **No** — out of scope per AAP §0.8.2 (informational row only) |
| `blitzy-ebbf6c96-1347-4c7f-bd3d-8b4d79737619` | 173 | FEATURE-001 + FEATURE-002 production implementation | **Yes**, via PR #3 (merge `5a7e83629bc`) |

Commits reaching `origin/pdlc` decompose as:

- **49** commits from the PR #2 merge leg (scaffold + tickets, dated 2026-02-02)
- **123** commits from the PR #3 merge leg (production modules + refine PRs, dated 2026-02-12 through 2026-04-17)
- **2** `blitzy[bot]` merge commits (PR #2 `2c52c6b3aaf`, PR #3 `5a7e83629bc`)
- **Total: 174 commits**

#### 2.1.2 Merge Commit Spotlight

| SHA | Author | Date | Subject | Parents |
|-----|--------|------|---------|---------|
| `2c52c6b3aaf` | `blitzy[bot]` | 2026-02-02 | Merge pull request #2 | `7bd7718bcd4` (`origin/19.0`) + `6f675489078` (blitzy-4490115e) |
| `5a7e83629bc` | `blitzy[bot]` | 2026-04-17 | Merge pull request #3 | `2c52c6b3aaf` (pdlc after PR #2) + `58f003542d0` (blitzy-ebbf6c96) |

#### 2.1.3 Full Commit Log (174 rows)

Generated via `git log origin/19.0..origin/pdlc --pretty=format:"%h|%ae|%ci|%s"`.
Commit author `Blitzy Agent` maps to `agent@blitzy.com`; `blitzy[bot]` maps to
the GitHub bot account. Branch column maps each commit to the merge leg that
introduced it (`4490115e` = PR #2 leg; `ebbf6c96` = PR #3 leg).

| SHA | Author | Date | Subject | Branch |
|-----|--------|------|---------|--------|
| `5a7e83629bc` | blitzy[bot] | 2026-04-17 | Merge pull request #3 | PR #3 merge |
| `58f003542d0` | Blitzy Agent | 2026-04-17 | Adding Blitzy Technical Specifications | ebbf6c96 |
| `ee088c56f17` | Blitzy Agent | 2026-04-17 | Adding Blitzy Project Guide: Project Status and Human Tasks Remaining | ebbf6c96 |
| `8d128ff9d57` | Blitzy Agent | 2026-04-17 | Refine PR: remediate security defects, navigation mismatch, and code-quality ... | ebbf6c96 |
| `e9255951023` | Blitzy Agent | 2026-04-16 | Adding Blitzy Technical Specifications | ebbf6c96 |
| `01ae2c51e92` | Blitzy Agent | 2026-04-16 | Adding Blitzy Project Guide: Project Status and Human Tasks Remaining | ebbf6c96 |
| `14e7269e542` | Blitzy Agent | 2026-04-16 | Refine PR: production-ready Phase 1 accounting modules | ebbf6c96 |
| `2a7b64e91aa` | Blitzy Agent | 2026-02-13 | Adding Blitzy Technical Specifications | ebbf6c96 |
| `561f610d745` | Blitzy Agent | 2026-02-13 | Adding Blitzy Project Guide: Project Status and Human Tasks Remaining | ebbf6c96 |
| `e7fff5e93dc` | Blitzy Agent | 2026-02-13 | Create account_bank_reconciliation_ce module entry point with AGPL-3.0 header... | ebbf6c96 |
| `c0a13765a6b` | Blitzy Agent | 2026-02-13 | Complete tests/__init__.py for account_bank_reconciliation_ce module | ebbf6c96 |
| `8bd74b4dd1a` | Blitzy Agent | 2026-02-13 | Complete report/__init__.py with encoding declaration, copyright header, and ... | ebbf6c96 |
| `7a78aee4780` | Blitzy Agent | 2026-02-13 | fix: resolve all ruff linting errors and ensure test suite passes | ebbf6c96 |
| `4d22fc406fd` | Blitzy Agent | 2026-02-13 | Register 7 new test modules (FR-001 through FR-007) in tests/__init__.py | ebbf6c96 |
| `abfd3576a2d` | Blitzy Agent | 2026-02-13 | fix: resolve test failures in bank reconciliation module | ebbf6c96 |
| `e65d81b0ba3` | Blitzy Agent | 2026-02-13 | feat(bank-reconciliation): implement comprehensive BR-001 statement import tests | ebbf6c96 |
| `0539cb160aa` | Blitzy Agent | 2026-02-13 | fix: resolve matching engine sign scoring and accuracy test data issues | ebbf6c96 |
| `a36fd41dd6d` | Blitzy Agent | 2026-02-13 | feat(bank-reconciliation): implement comprehensive BR-002 matching engine tes... | ebbf6c96 |
| `472d1187a3b` | Blitzy Agent | 2026-02-13 | fix(account_bank_reconciliation_ce): resolve reconciliation logic, ruff error... | ebbf6c96 |
| `2dce7bea85b` | Blitzy Agent | 2026-02-13 | feat(bank-reconciliation): Implement BR-003 manual reconciliation test suite | ebbf6c96 |
| `5ff92a05e0e` | Blitzy Agent | 2026-02-13 | feat(BR-004): Implement comprehensive test suite for configurable reconciliat... | ebbf6c96 |
| `0b0c7465f08` | Blitzy Agent | 2026-02-13 | fix: resolve partial reconciliation amount_currency bug, test robustness, and... | ebbf6c96 |
| `a2a173784ef` | Blitzy Agent | 2026-02-13 | Implement comprehensive BR-005 partial reconciliation test suite | ebbf6c96 |
| `ccfaa4a24a1` | Blitzy Agent | 2026-02-13 | Complete wizard __init__.py for account_bank_reconciliation_ce module | ebbf6c96 |
| `faf3fc80035` | Blitzy Agent | 2026-02-13 | feat(bank-reconciliation): implement complete reconciliation status report pa... | ebbf6c96 |
| `ebd6cde3682` | Blitzy Agent | 2026-02-13 | fix(account_financial_report_ce): resolve all test failures and security issues | ebbf6c96 |
| `6ac8b2eac0e` | Blitzy Agent | 2026-02-13 | Expand financial reports test suite to comprehensive ≥80% coverage target | ebbf6c96 |
| `f937ef6535a` | Blitzy Agent | 2026-02-13 | fix: resolve test failures across both accounting modules | ebbf6c96 |
| `b74ba20b9e6` | Blitzy Agent | 2026-02-13 | fix: resolve assertAlmostEqual syntax errors in test_balance_sheet.py | ebbf6c96 |
| `19937f74054` | Blitzy Agent | 2026-02-13 | feat(FR-001): Add comprehensive Balance Sheet report test suite | ebbf6c96 |
| `ba19218ef27` | Blitzy Agent | 2026-02-13 | fix(account_financial_report_ce): fix test_profit_loss test failures and regi... | ebbf6c96 |
| `df1c725947b` | Blitzy Agent | 2026-02-13 | Add dedicated FR-002 Profit & Loss test suite (test_profit_loss.py) | ebbf6c96 |
| `19f9665d783` | Blitzy Agent | 2026-02-13 | fix: Odoo 19.0 compatibility and cash flow logic corrections | ebbf6c96 |
| `00e89dc3566` | Blitzy Agent | 2026-02-13 | Fix unused imports: use timedelta for pre_period_date, add UserError negative... | ebbf6c96 |
| `cb8763f8065` | Blitzy Agent | 2026-02-13 | Add dedicated Cash Flow Statement test module for FR-003 acceptance criteria | ebbf6c96 |
| `cb2c2022b28` | Blitzy Agent | 2026-02-13 | fix(tests): register test_general_ledger in __init__.py and fix test failures | ebbf6c96 |
| `799dc84db49` | Blitzy Agent | 2026-02-13 | Add FR-004 General Ledger test suite (test_general_ledger.py) | ebbf6c96 |
| `6b60fb8228a` | Blitzy Agent | 2026-02-13 | fix(test_trial_balance): Odoo 19.0 compatibility and test correctness fixes | ebbf6c96 |
| `41d236a0852` | Blitzy Agent | 2026-02-13 | Add dedicated Trial Balance test module for FR-005 acceptance criteria | ebbf6c96 |
| `7ea3addcd79` | Blitzy Agent | 2026-02-13 | feat(test_aged_partner): Complete FR-006 Aged Partner Balance test suite | ebbf6c96 |
| `a4d3efcc580` | Blitzy Agent | 2026-02-13 | Add FR-006 Aged Partner Balance report tests (test_aged_partner.py) | ebbf6c96 |
| `8c5b5e00014` | Blitzy Agent | 2026-02-13 | fix(account_financial_report_ce): fix test_export.py for Odoo 19.0 compatibility | ebbf6c96 |
| `5427d8aaf2e` | Blitzy Agent | 2026-02-13 | feat: add FR-007 export and drill-down test suite for financial reports | ebbf6c96 |
| `d74eed263ff` | Blitzy Agent | 2026-02-13 | feat(bank_reconciliation): implement shared test fixtures for Bank Reconcilia... | ebbf6c96 |
| `901d48306da` | Blitzy Agent | 2026-02-13 | Complete account_bank_reconciliation_ce module manifest | ebbf6c96 |
| `38e95fd76d6` | Blitzy Agent | 2026-02-13 | feat(bank-reconciliation): complete bank statement import wizard (BR-001) | ebbf6c96 |
| `48cb053f32e` | Blitzy Agent | 2026-02-13 | fix(account_financial_report_ce): resolve XML load order and ACL permission i... | ebbf6c96 |
| `b23cccf12b6` | Blitzy Agent | 2026-02-13 | Complete models package __init__.py for account_bank_reconciliation_ce module | ebbf6c96 |
| `b8b9c0b9bb1` | Blitzy Agent | 2026-02-13 | fix(reconciliation_wizard): pass journal_id.id instead of recordset to find_m... | ebbf6c96 |
| `9c92bcfebcf` | Blitzy Agent | 2026-02-13 | feat(bank-reconciliation): rewrite reconciliation wizard for BR-003 compliance | ebbf6c96 |
| `6917142f006` | Blitzy Agent | 2026-02-13 | Enhance demo_data.xml with wizard presets for all 6 financial report types | ebbf6c96 |
| `0de717aa4ec` | Blitzy Agent | 2026-02-13 | Refine interactive report SCSS with production-quality styling for all 6 fina... | ebbf6c96 |
| `1a1645a4268` | Blitzy Agent | 2026-02-13 | Optimize print layout for professional PDF export across all 6 financial repo... | ebbf6c96 |
| `699c2134ea2` | Blitzy Agent | 2026-02-13 | Verify and refine paper format bindings for financial reports | ebbf6c96 |
| `0e1739e8cb5` | Blitzy Agent | 2026-02-13 | Restructure ACL entries for role-based access control in financial report module | ebbf6c96 |
| `75e3235b6eb` | Blitzy Agent | 2026-02-13 | Enhance financial report security: fix group hierarchy and add multi-company ... | ebbf6c96 |
| `c04a90d723c` | Blitzy Agent | 2026-02-13 | fix: reconcile wizard XML views with Python model fields and Odoo 19.0 API | ebbf6c96 |
| `bb12e974d5d` | Blitzy Agent | 2026-02-13 | fix(wizard-views): correct model refs, field names, visibility rules, and win... | ebbf6c96 |
| `6cdc23cc684` | Blitzy Agent | 2026-02-13 | fix: add field existence checks in wizard action_generate_report | ebbf6c96 |
| `c0e067c8cce` | Blitzy Agent | 2026-02-13 | Complete FinancialReportWizard TransientModel: production-quality wizard-to-r... | ebbf6c96 |
| `41145b7d885` | Blitzy Agent | 2026-02-13 | Verify and restore wizard __init__.py import chain | ebbf6c96 |
| `f335ea9dc08` | Blitzy Agent | 2026-02-13 | feat(FR-001): enhance Balance Sheet QWeb template with hierarchy, variance an... | ebbf6c96 |
| `83fce84db64` | Blitzy Agent | 2026-02-13 | fix(profit_loss): add missing 'section' field to ProfitLossReportLine model a... | ebbf6c96 |
| `f8e292cfc56` | Blitzy Agent | 2026-02-13 | Refine FR-002 Profit & Loss QWeb report template to production quality | ebbf6c96 |
| `b68b98f4187` | Blitzy Agent | 2026-02-13 | feat(FR-003): Complete Cash Flow Statement QWeb report template | ebbf6c96 |
| `d10232c19c2` | Blitzy Agent | 2026-02-13 | Refine General Ledger QWeb report template and model ordering | ebbf6c96 |
| `7fc430f7bd6` | Blitzy Agent | 2026-02-13 | Refine FR-004 General Ledger QWeb template to production quality | ebbf6c96 |
| `93c0b3fa88c` | Blitzy Agent | 2026-02-13 | fix(trial_balance): add closing_debit/closing_credit alias fields for QWeb te... | ebbf6c96 |
| `221a849ded7` | Blitzy Agent | 2026-02-13 | Enhance FR-005 Trial Balance QWeb template to production quality | ebbf6c96 |
| `413c85a66ea` | Blitzy Agent | 2026-02-13 | Refine FR-006 Aged Partner Balance QWeb report template | ebbf6c96 |
| `0686c00523f` | Blitzy Agent | 2026-02-13 | fix: resolve template-model field mismatches across all financial report models | ebbf6c96 |
| `ff22ce35e68` | Blitzy Agent | 2026-02-13 | Complete Balance Sheet report parser _get_report_values (FR-001) | ebbf6c96 |
| `87d7e8ce4ea` | Blitzy Agent | 2026-02-13 | Complete P&L report parser _get_report_values with full template context | ebbf6c96 |
| `79f1ca54b9f` | Blitzy Agent | 2026-02-13 | Complete Cash Flow Statement report parser (_get_report_values) for FR-003 | ebbf6c96 |
| `ef29e9b2111` | Blitzy Agent | 2026-02-13 | Complete General Ledger report parser _get_report_values (FR-004) | ebbf6c96 |
| `1aef9846fdf` | Blitzy Agent | 2026-02-13 | fix: resolve ruff linting issues across financial report module | ebbf6c96 |
| `f0f50810a6d` | Blitzy Agent | 2026-02-13 | Complete Trial Balance report parser (FR-005): full QWeb rendering context | ebbf6c96 |
| `f0c8c456540` | Blitzy Agent | 2026-02-13 | feat(aged_partner_balance): complete report parser, template, and model for F... | ebbf6c96 |
| `a5b041062c4` | Blitzy Agent | 2026-02-13 | Complete Aged Partner Balance report parser (FR-006) | ebbf6c96 |
| `8b251dd9b77` | Blitzy Agent | 2026-02-13 | fix(report_templates): align paperformat references with data/report_paperfor... | ebbf6c96 |
| `e24c84123f6` | Blitzy Agent | 2026-02-13 | Complete ir.actions.report definitions in report_templates.xml | ebbf6c96 |
| `0547205ccf0` | Blitzy Agent | 2026-02-13 | fix(balance_sheet): Convert Line.new() to fields.Command.create() for DB pers... | ebbf6c96 |
| `d65bba0e2bf` | Blitzy Agent | 2026-02-13 | feat(FR-001): Complete Balance Sheet report to production-grade implementation | ebbf6c96 |
| `8b4546c9208` | Blitzy Agent | 2026-02-13 | fix(cash_flow): add config=False to report_action call in action_print_pdf | ebbf6c96 |
| `9f8049dc95e` | Blitzy Agent | 2026-02-13 | feat(FR-003): Complete cash_flow.py — production-grade Cash Flow Statement | ebbf6c96 |
| `041eb162c09` | Blitzy Agent | 2026-02-13 | fix(profit_loss): pass config=False to report_action to prevent layout config... | ebbf6c96 |
| `b5b5cfb4b67` | Blitzy Agent | 2026-02-13 | feat(FR-002): Complete Profit & Loss report model to production-grade | ebbf6c96 |
| `8a9dff4a6e1` | Blitzy Agent | 2026-02-13 | feat: Complete general_ledger.py production implementation and bank reconcili... | ebbf6c96 |
| `8278a68c3a8` | Blitzy Agent | 2026-02-13 | feat(general_ledger): production-grade FR-004 enhancements | ebbf6c96 |
| `580a028a21a` | Blitzy Agent | 2026-02-13 | fix(trial_balance): remove unused api import and simplify boolean return | ebbf6c96 |
| `a5c02853b07` | Blitzy Agent | 2026-02-13 | feat(FR-005): Complete trial balance report with 6-column layout, hierarchy, ... | ebbf6c96 |
| `7a251a0c9a1` | Blitzy Agent | 2026-02-13 | fix(account_financial_report_ce): fix import order and linting issues | ebbf6c96 |
| `4170bc8f8ee` | Blitzy Agent | 2026-02-13 | feat(FR-006): production-grade aged partner balance with search_read optimiza... | ebbf6c96 |
| `0074c538d50` | Blitzy Agent | 2026-02-13 | fix: refactor all report models to use fields.Command for ORM-safe One2many p... | ebbf6c96 |
| `c7765e899fb` | Blitzy Agent | 2026-02-13 | Complete FinancialReportAbstract: production-grade base class for financial r... | ebbf6c96 |
| `d07bd72667a` | Blitzy Agent | 2026-02-13 | chore(manifest): update account_financial_report_ce manifest for production r... | ebbf6c96 |
| `944b6d3aa51` | Blitzy Agent | 2026-02-13 | Create sample CSV bank statement test file for BR-001 import testing | ebbf6c96 |
| `b4ca0212e97` | Blitzy Agent | 2026-02-13 | Add sample OFX 1.x SGML bank statement file for BR-001 import testing | ebbf6c96 |
| `0cab97025bb` | Blitzy Agent | 2026-02-13 | Add sample QIF bank statement test file for BR-001 import testing | ebbf6c96 |
| `09d83bd0b2f` | Blitzy Agent | 2026-02-13 | Create sample CAMT.053.001.02 XML test fixture for bank statement import testing | ebbf6c96 |
| `f4e0d93675a` | Blitzy Agent | 2026-02-13 | feat(bank-reconciliation): add comprehensive demo data for Bank Reconciliatio... | ebbf6c96 |
| `d1820b971a3` | Blitzy Agent | 2026-02-13 | feat(bank-reconciliation): add SCSS stylesheet for reconciliation UI | ebbf6c96 |
| `52e0987f238` | Blitzy Agent | 2026-02-13 | Validate reconciliation_report.xml: fix table name length, add report parser ... | ebbf6c96 |
| `7b63302fdf2` | Blitzy Agent | 2026-02-13 | Create QWeb report template for Bank Reconciliation Status Report | ebbf6c96 |
| `c2b84a27825` | Blitzy Agent | 2026-02-13 | fix: register views/menuitem.xml in __manifest__.py data list | ebbf6c96 |
| `3d0ca12f1fd` | Blitzy Agent | 2026-02-13 | Create Bank Reconciliation CE module menu items (views/menuitem.xml) | ebbf6c96 |
| `e9e0dca5d65` | Blitzy Agent | 2026-02-13 | fix: bank_reconciliation_views.xml validation fixes and manifest update | ebbf6c96 |
| `065a4b24b80` | Blitzy Agent | 2026-02-12 | feat(bank_reconciliation_ce): add tree/form/search views and window actions f... | ebbf6c96 |
| `4061081c34e` | Blitzy Agent | 2026-02-12 | fix(account_bank_reconciliation_ce): complete wizard infrastructure and fix O... | ebbf6c96 |
| `47b557fb9d6` | Blitzy Agent | 2026-02-12 | Create bank reconciliation wizard views XML (FEATURE-002 BR-003) | ebbf6c96 |
| `a0d7650a3a3` | Blitzy Agent | 2026-02-12 | fix(account_bank_reconciliation_ce): complete wizard views and manifest data ... | ebbf6c96 |
| `c1ee7d7957a` | Blitzy Agent | 2026-02-12 | feat(bank-reconciliation): add bank statement import wizard XML views | ebbf6c96 |
| `d105ef72201` | Blitzy Agent | 2026-02-12 | feat: add default configuration data for Bank Reconciliation CE module | ebbf6c96 |
| `b3b48a49484` | Blitzy Agent | 2026-02-12 | Create ir.model.access.csv with full ACL matrix for Bank Reconciliation CE mo... | ebbf6c96 |
| `18049e4ee4d` | Blitzy Agent | 2026-02-12 | Create bank_reconciliation_security.xml with security groups and multi-compan... | ebbf6c96 |
| `8641274787d` | Blitzy Agent | 2026-02-12 | fix(account_bank_reconciliation_ce): add bank_statement_import to models init... | ebbf6c96 |
| `92e19ff9a9c` | Blitzy Agent | 2026-02-12 | feat(bank-reconciliation): implement bank statement import model (BR-001) | ebbf6c96 |
| `1ba79df159c` | Blitzy Agent | 2026-02-12 | fix: add reconciliation_matching_engine import and ACL entries | ebbf6c96 |
| `62065ec79b3` | Blitzy Agent | 2026-02-12 | feat(bank-reconciliation): implement algorithmic matching engine for BR-002 | ebbf6c96 |
| `89932fd4bbd` | Blitzy Agent | 2026-02-12 | fix(account_bank_reconciliation_ce): add reconciliation_rule import to models... | ebbf6c96 |
| `bf4fc3e00f9` | Blitzy Agent | 2026-02-12 | feat(bank-reconciliation): add extended reconciliation rule model (BR-004) | ebbf6c96 |
| `a5c1c6d7c39` | Blitzy Agent | 2026-02-12 | chore: add in-scope bank reconciliation module structure files | ebbf6c96 |
| `6264fee1c99` | Blitzy Agent | 2026-02-12 | fix: resolve all test failures in account_financial_report_ce and fix partial... | ebbf6c96 |
| `7d60f2a9814` | Blitzy Agent | 2026-02-12 | Add partial reconciliation extension model for bank reconciliation (BR-003, B... | ebbf6c96 |
| `2c52c6b3aaf` | blitzy[bot] | 2026-02-02 | Merge pull request #2 | PR #2 merge |
| `6f675489078` | Blitzy Agent | 2026-02-02 | Adding Blitzy Technical Specifications | 4490115e |
| `afc533df728` | Blitzy Agent | 2026-02-02 | Adding Blitzy Project Guide: Project Status and Human Tasks Remaining | 4490115e |
| `95e9ff2ce39` | Blitzy Agent | 2026-02-02 | feat: Add account_financial_report_ce module scaffold | 4490115e |
| `343b9f63c70` | Blitzy Agent | 2026-02-02 | Adding Blitzy Technical Specifications | 4490115e |
| `b97f9efa46e` | Blitzy Agent | 2026-02-02 | Adding Blitzy Project Guide: Project Status and Human Tasks Remaining | 4490115e |
| `d60847f961a` | Blitzy Agent | 2026-02-02 | Add missing AGPL-3.0 Constraints section to AM-006-asset-disposal.md | 4490115e |
| `45488098215` | Blitzy Agent | 2026-02-02 | Add FR-007 Report Export & Drill-down user story | 4490115e |
| `0a5b52d247a` | Blitzy Agent | 2026-02-02 | Add FR-006 Aged Receivable/Payable Reports user story | 4490115e |
| `587839915dd` | Blitzy Agent | 2026-02-02 | Add FR-005 Trial Balance Report user story | 4490115e |
| `4f495c97ad1` | Blitzy Agent | 2026-02-02 | Add FR-004: General Ledger Report user story | 4490115e |
| `ddb00a19978` | Blitzy Agent | 2026-02-02 | Add FR-003 Cash Flow Statement user story | 4490115e |
| `cd035e7e57d` | Blitzy Agent | 2026-02-02 | Add FR-002: Profit & Loss Statement user story | 4490115e |
| `0b81b80bb4b` | Blitzy Agent | 2026-02-02 | Add FR-001 Balance Sheet Report user story | 4490115e |
| `22444618c94` | Blitzy Agent | 2026-02-02 | Add BR-005 Partial Reconciliation user story documentation | 4490115e |
| `3f4449ad9da` | Blitzy Agent | 2026-02-02 | Add BR-003 Manual Reconciliation user story | 4490115e |
| `6dfc2231375` | Blitzy Agent | 2026-02-02 | Add BR-004 Reconciliation Rules user story documentation | 4490115e |
| `c3827c73b04` | Blitzy Agent | 2026-02-02 | Add BR-002 Algorithmic Matching user story for bank reconciliation | 4490115e |
| `66cb362d954` | Blitzy Agent | 2026-02-02 | Add BR-001 Statement Import user story | 4490115e |
| `2993e947a47` | Blitzy Agent | 2026-02-02 | Add BM-005: Budget Alerts user story documentation | 4490115e |
| `84ae2372623` | Blitzy Agent | 2026-02-02 | Create BM-004: Variance Analysis user story documentation | 4490115e |
| `1444a15e811` | Blitzy Agent | 2026-02-02 | Add BM-003: Actual vs Budget Reporting user story | 4490115e |
| `6dfbcbd2705` | Blitzy Agent | 2026-02-02 | Add BM-002 Budget Period Allocation user story | 4490115e |
| `e5a8719bad0` | Blitzy Agent | 2026-02-02 | Add BM-001 Budget Definition user story | 4490115e |
| `dcdee1e850e` | Blitzy Agent | 2026-02-02 | Add AM-006 Asset Disposal user story documentation | 4490115e |
| `98fb9c73574` | Blitzy Agent | 2026-02-02 | Add AM-005 Asset Modification user story documentation | 4490115e |
| `e036ba6757f` | Blitzy Agent | 2026-02-02 | Create AM-004: Automatic Depreciation Entries user story | 4490115e |
| `058a0f66dd2` | Blitzy Agent | 2026-02-02 | Add AM-003: Depreciation Board user story | 4490115e |
| `9a8dda51dba` | Blitzy Agent | 2026-02-02 | Add AM-002 Depreciation Configuration user story | 4490115e |
| `a8bb3b84b17` | Blitzy Agent | 2026-02-02 | Add AM-001 Asset Registration user story | 4490115e |
| `9df8213d37f` | Blitzy Agent | 2026-02-02 | Add DR-004 Recognition Dashboard user story | 4490115e |
| `153aac95d7a` | Blitzy Agent | 2026-02-02 | Add DR-003 Cut-off Entry Generation user story | 4490115e |
| `aaf98760a13` | Blitzy Agent | 2026-02-02 | Add user story DR-002: Automatic Period Allocation | 4490115e |
| `58ff75a34f7` | Blitzy Agent | 2026-02-02 | Create user story DR-001: Deferral Schedule Definition | 4490115e |
| `1773362fd56` | Blitzy Agent | 2026-02-02 | Add PF-003: Follow-up Report Generation user story | 4490115e |
| `8bc9d81b18d` | Blitzy Agent | 2026-02-02 | Add PF-004: Action History Tracking user story | 4490115e |
| `dd100813487` | Blitzy Agent | 2026-02-02 | Add PF-002 user story: Automated Email Generation for payment follow-ups | 4490115e |
| `ec7f8bb3ef9` | Blitzy Agent | 2026-02-02 | Add PF-001: Follow-up Level Configuration user story | 4490115e |
| `2765d641c3f` | Blitzy Agent | 2026-02-02 | Add PF-005 Overdue Calculation user story | 4490115e |
| `f4d1e61c223` | Blitzy Agent | 2026-02-02 | Create FEATURE-006 Payment Follow-ups feature specification | 4490115e |
| `01f85b4e8e2` | Blitzy Agent | 2026-02-02 | Add FEATURE-005: Deferred Revenue/Expenses feature specification | 4490115e |
| `c585446c4dc` | Blitzy Agent | 2026-02-02 | Add FEATURE-004 Asset Management feature specification | 4490115e |
| `ce0a9aafb09` | Blitzy Agent | 2026-02-02 | Add FEATURE-003 Budget Management feature specification | 4490115e |
| `b9252a0566c` | Blitzy Agent | 2026-02-02 | Create FEATURE-002: Bank Reconciliation feature specification | 4490115e |
| `7014912eade` | Blitzy Agent | 2026-02-02 | Create FEATURE-001 Financial Reporting specification | 4490115e |
| `e76e14505c8` | Blitzy Agent | 2026-02-02 | Add user story template with BDD and INVEST principles | 4490115e |
| `7bbc574852a` | Blitzy Agent | 2026-02-02 | Create reusable feature specification template | 4490115e |
| `34fc5a33fee` | Blitzy Agent | 2026-02-02 | Create reusable epic documentation template | 4490115e |
| `fcc1c553dd8` | Blitzy Agent | 2026-02-02 | Create tickets/README.md - Epic navigation index for enterprise accounting do... | 4490115e |
| `c78ed92a1fc` | Blitzy Agent | 2026-02-02 | Add EPIC-001: Enterprise Accounting Capabilities master epic document | 4490115e |

### 2.2 File Inventory

#### 2.2.1 Domain Distribution

| Domain | Files | Net Lines | Primary File Patterns |
|--------|-----:|---------:|-----------------------|
| Business / Domain | 54 | +22,765 | views XML, report XML, tickets/**/*.md |
| QA / Test Integrity | 25 | +16,618 | tests/**, test_data/** |
| Backend Architecture | 21 | +14,626 | models/*.py, report/*.py, wizard/*.py |
| Infrastructure / DevOps | 17 | +1,232 | __manifest__.py, __init__.py, hooks.py, data/*.xml, demo/*.xml |
| Other SME (Documentation) | 13 | +4,166 / −2,022 | docs/*.md, blitzy/*.md, tickets/templates/*.md, mkdocs removals |
| Security | 4 | +269 | security/*.xml, ir.model.access.csv |
| Frontend | 3 | +1,699 | static/src/scss/*.scss |
| **Total** | **137** | **+61,375 / −2,022** | — |

```mermaid
%%{init: {'theme':'base','themeVariables':{'primaryColor':'#F2F0FE','primaryTextColor':'#333333','primaryBorderColor':'#5B39F3','lineColor':'#999999','secondaryColor':'#F4EFF6'}}}%%
pie showData title File Count by Domain
    "Business/Domain" : 54
    "QA/Test Integrity" : 25
    "Backend Architecture" : 21
    "Infrastructure/DevOps" : 17
    "Other SME" : 13
    "Security" : 4
    "Frontend" : 3
```

#### 2.2.2 Per-Module Totals

| Path Prefix | Files | Notes |
|-------------|-----:|-------|
| `addons/account_financial_report_ce/` | 44 | FEATURE-001 — 6 reports + abstract base + unified wizard |
| `addons/account_bank_reconciliation_ce/` | 35 | FEATURE-002 — import + matching + rules + partial + manual |
| `tickets/` | 43 | EPIC-001 + 6 feature specs + 32 stories + 3 templates + README |
| `test_data/` | 5 | Bank statement samples (CSV/OFX/QIF/CAMT.053) + FR journal CSV |
| `docs/` | 3 | `SETUP.md`, `USER_GUIDE.md` (added); `index.md` (deleted) |
| `blitzy/documentation/` | 2 | `Project Guide.md`, `Technical Specifications.md` |
| Repository root (deletions) | 2 | `catalog-info.yaml`, `mkdocs.yml` — Backstage/MkDocs removal |
| `doc/` (deletions) | 3 | `doc/index.md`, `doc/project-guide.md`, `doc/technical-specifications.md` |
| **Total** | **137** | **131 Added + 6 Deleted** |

#### 2.2.3 Full File Inventory (137 rows)

Generated via `git diff origin/19.0..origin/pdlc --name-status` joined with
`git diff --numstat` for line counts. Status codes: `A` = Added, `D` = Deleted.

| Path | Status | Domain | Net Lines |
|------|:------:|--------|----------:|
| `addons/account_bank_reconciliation_ce/__init__.py` | A | Infrastructure/DevOps | +7 |
| `addons/account_bank_reconciliation_ce/__manifest__.py` | A | Infrastructure/DevOps | +76 |
| `addons/account_bank_reconciliation_ce/data/reconciliation_data.xml` | A | Infrastructure/DevOps | +234 |
| `addons/account_bank_reconciliation_ce/demo/demo_data.xml` | A | Infrastructure/DevOps | +417 |
| `addons/account_bank_reconciliation_ce/hooks.py` | A | Infrastructure/DevOps | +66 |
| `addons/account_bank_reconciliation_ce/models/__init__.py` | A | Infrastructure/DevOps | +9 |
| `addons/account_bank_reconciliation_ce/models/bank_statement_import.py` | A | Backend Architecture | +1379 |
| `addons/account_bank_reconciliation_ce/models/partial_reconcile_ext.py` | A | Backend Architecture | +802 |
| `addons/account_bank_reconciliation_ce/models/reconciliation_matching_engine.py` | A | Backend Architecture | +949 |
| `addons/account_bank_reconciliation_ce/models/reconciliation_rule.py` | A | Backend Architecture | +668 |
| `addons/account_bank_reconciliation_ce/report/__init__.py` | A | Infrastructure/DevOps | +4 |
| `addons/account_bank_reconciliation_ce/report/reconciliation_report.py` | A | Backend Architecture | +567 |
| `addons/account_bank_reconciliation_ce/report/reconciliation_report.xml` | A | Business/Domain | +675 |
| `addons/account_bank_reconciliation_ce/security/bank_reconciliation_security.xml` | A | Security | +89 |
| `addons/account_bank_reconciliation_ce/security/ir.model.access.csv` | A | Security | +12 |
| `addons/account_bank_reconciliation_ce/static/src/scss/reconciliation.scss` | A | Frontend | +748 |
| `addons/account_bank_reconciliation_ce/tests/__init__.py` | A | Infrastructure/DevOps | +12 |
| `addons/account_bank_reconciliation_ce/tests/common.py` | A | QA/Test Integrity | +470 |
| `addons/account_bank_reconciliation_ce/tests/test_candidate_date_window.py` | A | QA/Test Integrity | +300 |
| `addons/account_bank_reconciliation_ce/tests/test_files/sample.csv` | A | QA/Test Integrity | +6 |
| `addons/account_bank_reconciliation_ce/tests/test_files/sample.ofx` | A | QA/Test Integrity | +82 |
| `addons/account_bank_reconciliation_ce/tests/test_files/sample.qif` | A | QA/Test Integrity | +31 |
| `addons/account_bank_reconciliation_ce/tests/test_files/sample_camt053.xml` | A | QA/Test Integrity | +257 |
| `addons/account_bank_reconciliation_ce/tests/test_manual_reconciliation.py` | A | QA/Test Integrity | +1410 |
| `addons/account_bank_reconciliation_ce/tests/test_matching_engine.py` | A | QA/Test Integrity | +1036 |
| `addons/account_bank_reconciliation_ce/tests/test_partial_reconciliation.py` | A | QA/Test Integrity | +1319 |
| `addons/account_bank_reconciliation_ce/tests/test_reconciliation_rules.py` | A | QA/Test Integrity | +899 |
| `addons/account_bank_reconciliation_ce/tests/test_statement_import.py` | A | QA/Test Integrity | +1191 |
| `addons/account_bank_reconciliation_ce/views/bank_reconciliation_views.xml` | A | Business/Domain | +536 |
| `addons/account_bank_reconciliation_ce/views/menuitem.xml` | A | Business/Domain | +103 |
| `addons/account_bank_reconciliation_ce/wizard/__init__.py` | A | Infrastructure/DevOps | +4 |
| `addons/account_bank_reconciliation_ce/wizard/bank_statement_import_wizard.py` | A | Backend Architecture | +612 |
| `addons/account_bank_reconciliation_ce/wizard/bank_statement_import_wizard_views.xml` | A | Business/Domain | +242 |
| `addons/account_bank_reconciliation_ce/wizard/reconciliation_wizard.py` | A | Backend Architecture | +902 |
| `addons/account_bank_reconciliation_ce/wizard/reconciliation_wizard_views.xml` | A | Business/Domain | +388 |
| `addons/account_financial_report_ce/__init__.py` | A | Infrastructure/DevOps | +4 |
| `addons/account_financial_report_ce/__manifest__.py` | A | Infrastructure/DevOps | +84 |
| `addons/account_financial_report_ce/data/report_paperformat.xml` | A | Infrastructure/DevOps | +105 |
| `addons/account_financial_report_ce/demo/demo_data.xml` | A | Infrastructure/DevOps | +167 |
| `addons/account_financial_report_ce/models/__init__.py` | A | Infrastructure/DevOps | +14 |
| `addons/account_financial_report_ce/models/aged_partner_balance.py` | A | Backend Architecture | +616 |
| `addons/account_financial_report_ce/models/balance_sheet.py` | A | Backend Architecture | +1286 |
| `addons/account_financial_report_ce/models/cash_flow.py` | A | Backend Architecture | +1185 |
| `addons/account_financial_report_ce/models/financial_report.py` | A | Backend Architecture | +891 |
| `addons/account_financial_report_ce/models/general_ledger.py` | A | Backend Architecture | +614 |
| `addons/account_financial_report_ce/models/profit_loss.py` | A | Backend Architecture | +1051 |
| `addons/account_financial_report_ce/models/trial_balance.py` | A | Backend Architecture | +1047 |
| `addons/account_financial_report_ce/report/__init__.py` | A | Infrastructure/DevOps | +11 |
| `addons/account_financial_report_ce/report/aged_partner_balance_report.xml` | A | Business/Domain | +456 |
| `addons/account_financial_report_ce/report/balance_sheet_report.xml` | A | Business/Domain | +305 |
| `addons/account_financial_report_ce/report/cash_flow_report.xml` | A | Business/Domain | +655 |
| `addons/account_financial_report_ce/report/general_ledger_report.xml` | A | Business/Domain | +338 |
| `addons/account_financial_report_ce/report/profit_loss_report.xml` | A | Business/Domain | +488 |
| `addons/account_financial_report_ce/report/report_aged_partner_balance.py` | A | Backend Architecture | +208 |
| `addons/account_financial_report_ce/report/report_balance_sheet.py` | A | Backend Architecture | +177 |
| `addons/account_financial_report_ce/report/report_cash_flow.py` | A | Backend Architecture | +212 |
| `addons/account_financial_report_ce/report/report_general_ledger.py` | A | Backend Architecture | +341 |
| `addons/account_financial_report_ce/report/report_profit_loss.py` | A | Backend Architecture | +150 |
| `addons/account_financial_report_ce/report/report_templates.xml` | A | Business/Domain | +91 |
| `addons/account_financial_report_ce/report/report_trial_balance.py` | A | Backend Architecture | +373 |
| `addons/account_financial_report_ce/report/trial_balance_report.xml` | A | Business/Domain | +506 |
| `addons/account_financial_report_ce/security/account_financial_report_security.xml` | A | Security | +133 |
| `addons/account_financial_report_ce/security/ir.model.access.csv` | A | Security | +35 |
| `addons/account_financial_report_ce/static/src/scss/report.scss` | A | Frontend | +378 |
| `addons/account_financial_report_ce/static/src/scss/report_print.scss` | A | Frontend | +573 |
| `addons/account_financial_report_ce/tests/__init__.py` | A | Infrastructure/DevOps | +14 |
| `addons/account_financial_report_ce/tests/test_aged_partner.py` | A | QA/Test Integrity | +726 |
| `addons/account_financial_report_ce/tests/test_aging_bucket_wizard.py` | A | QA/Test Integrity | +416 |
| `addons/account_financial_report_ce/tests/test_balance_sheet.py` | A | QA/Test Integrity | +1204 |
| `addons/account_financial_report_ce/tests/test_cash_flow.py` | A | QA/Test Integrity | +1082 |
| `addons/account_financial_report_ce/tests/test_export.py` | A | QA/Test Integrity | +928 |
| `addons/account_financial_report_ce/tests/test_financial_reports.py` | A | QA/Test Integrity | +1554 |
| `addons/account_financial_report_ce/tests/test_general_ledger.py` | A | QA/Test Integrity | +1028 |
| `addons/account_financial_report_ce/tests/test_profit_loss.py` | A | QA/Test Integrity | +1132 |
| `addons/account_financial_report_ce/tests/test_trial_balance.py` | A | QA/Test Integrity | +1040 |
| `addons/account_financial_report_ce/views/menuitem.xml` | A | Business/Domain | +89 |
| `addons/account_financial_report_ce/wizard/__init__.py` | A | Infrastructure/DevOps | +4 |
| `addons/account_financial_report_ce/wizard/financial_report_wizard.py` | A | Backend Architecture | +596 |
| `addons/account_financial_report_ce/wizard/financial_report_wizard_views.xml` | A | Business/Domain | +271 |
| `blitzy/documentation/Project Guide.md` | A | Other SME | +730 |
| `blitzy/documentation/Technical Specifications.md` | A | Other SME | +769 |
| `catalog-info.yaml` | D | Other SME | −29 |
| `doc/index.md` | D | Other SME | −5 |
| `doc/project-guide.md` | D | Other SME | −502 |
| `doc/technical-specifications.md` | D | Other SME | −1474 |
| `docs/SETUP.md` | A | Other SME | +538 |
| `docs/USER_GUIDE.md` | A | Other SME | +489 |
| `docs/index.md` | D | Other SME | −3 |
| `mkdocs.yml` | D | Other SME | −9 |
| `test_data/bank_statements/sample.csv` | A | QA/Test Integrity | +9 |
| `test_data/bank_statements/sample.ofx` | A | QA/Test Integrity | +111 |
| `test_data/bank_statements/sample.qif` | A | QA/Test Integrity | +49 |
| `test_data/bank_statements/sample.xml` | A | QA/Test Integrity | +313 |
| `test_data/financial_reports/sample_journal_entries.csv` | A | QA/Test Integrity | +25 |
| `tickets/EPIC-001-enterprise-accounting.md` | A | Business/Domain | +588 |
| `tickets/README.md` | A | Business/Domain | +362 |
| `tickets/features/FEATURE-001-financial-reporting.md` | A | Business/Domain | +558 |
| `tickets/features/FEATURE-002-bank-reconciliation.md` | A | Business/Domain | +551 |
| `tickets/features/FEATURE-003-budget-management.md` | A | Business/Domain | +489 |
| `tickets/features/FEATURE-004-asset-management.md` | A | Business/Domain | +471 |
| `tickets/features/FEATURE-005-deferred-revenue.md` | A | Business/Domain | +532 |
| `tickets/features/FEATURE-006-payment-followups.md` | A | Business/Domain | +475 |
| `tickets/stories/asset-management/AM-001-asset-registration.md` | A | Business/Domain | +252 |
| `tickets/stories/asset-management/AM-002-depreciation-configuration.md` | A | Business/Domain | +367 |
| `tickets/stories/asset-management/AM-003-depreciation-board.md` | A | Business/Domain | +363 |
| `tickets/stories/asset-management/AM-004-automatic-depreciation-entries.md` | A | Business/Domain | +437 |
| `tickets/stories/asset-management/AM-005-asset-modification.md` | A | Business/Domain | +397 |
| `tickets/stories/asset-management/AM-006-asset-disposal.md` | A | Business/Domain | +444 |
| `tickets/stories/bank-reconciliation/BR-001-statement-import.md` | A | Business/Domain | +297 |
| `tickets/stories/bank-reconciliation/BR-002-algorithmic-matching.md` | A | Business/Domain | +308 |
| `tickets/stories/bank-reconciliation/BR-003-manual-reconciliation.md` | A | Business/Domain | +283 |
| `tickets/stories/bank-reconciliation/BR-004-reconciliation-rules.md` | A | Business/Domain | +337 |
| `tickets/stories/bank-reconciliation/BR-005-partial-reconciliation.md` | A | Business/Domain | +295 |
| `tickets/stories/budget-management/BM-001-budget-definition.md` | A | Business/Domain | +565 |
| `tickets/stories/budget-management/BM-002-budget-period-allocation.md` | A | Business/Domain | +704 |
| `tickets/stories/budget-management/BM-003-actual-vs-budget-reporting.md` | A | Business/Domain | +646 |
| `tickets/stories/budget-management/BM-004-variance-analysis.md` | A | Business/Domain | +786 |
| `tickets/stories/budget-management/BM-005-budget-alerts.md` | A | Business/Domain | +676 |
| `tickets/stories/deferred-revenue/DR-001-deferral-schedule-definition.md` | A | Business/Domain | +369 |
| `tickets/stories/deferred-revenue/DR-002-automatic-period-allocation.md` | A | Business/Domain | +331 |
| `tickets/stories/deferred-revenue/DR-003-cutoff-entry-generation.md` | A | Business/Domain | +397 |
| `tickets/stories/deferred-revenue/DR-004-recognition-dashboard.md` | A | Business/Domain | +403 |
| `tickets/stories/financial-reporting/FR-001-balance-sheet-report.md` | A | Business/Domain | +388 |
| `tickets/stories/financial-reporting/FR-002-profit-loss-statement.md` | A | Business/Domain | +513 |
| `tickets/stories/financial-reporting/FR-003-cash-flow-statement.md` | A | Business/Domain | +376 |
| `tickets/stories/financial-reporting/FR-004-general-ledger-report.md` | A | Business/Domain | +270 |
| `tickets/stories/financial-reporting/FR-005-trial-balance-report.md` | A | Business/Domain | +331 |
| `tickets/stories/financial-reporting/FR-006-aged-reports.md` | A | Business/Domain | +299 |
| `tickets/stories/financial-reporting/FR-007-report-export-drilldown.md` | A | Business/Domain | +317 |
| `tickets/stories/payment-followups/PF-001-followup-level-configuration.md` | A | Business/Domain | +391 |
| `tickets/stories/payment-followups/PF-002-automated-email-generation.md` | A | Business/Domain | +499 |
| `tickets/stories/payment-followups/PF-003-followup-report-generation.md` | A | Business/Domain | +547 |
| `tickets/stories/payment-followups/PF-004-action-history-tracking.md` | A | Business/Domain | +578 |
| `tickets/stories/payment-followups/PF-005-overdue-calculation.md` | A | Business/Domain | +430 |
| `tickets/templates/epic-template.md` | A | Other SME | +633 |
| `tickets/templates/feature-template.md` | A | Other SME | +647 |
| `tickets/templates/story-template.md` | A | Other SME | +360 |

### 2.3 Scope Statistics

- **Files changed**: 137 (131 Added, 6 Deleted)
- **Insertions**: 61,375
- **Deletions**: 2,022
- **Net LOC**: +59,353
- **Commits**: 174 (172 by `Blitzy Agent`, 2 merges by `blitzy[bot]`)
- **Commit date range**: 2026-02-02 14:20:20 -0500 → 2026-04-17 20:31:18 +0000
- **Contributing branches**: 2 (`blitzy-4490115e-...`, `blitzy-ebbf6c96-...`)
- **Merge commits**: 2 (`2c52c6b3aaf` = PR #2, `5a7e83629bc` = PR #3)
- **Refine PR HEAD**: `8d128ff9d57` (2026-04-17 — final remediation of defects identified in internal review)

Sourced statistics from the prior validated run, cited as reported per
AAP §0.7.2 labelling (not re-executed during this archaeology run):

- `blitzy/documentation/Project Guide.md` reports **371 of 371 tests passing** on the `test_phase1` database in **132.41 seconds** with **185,961 queries** across both accounting modules.
- FR module: 260 tests / 81,122 queries / 56.54 s
- BR module: 211 tests / 104,839 queries / 75.77 s
- `ruff check --no-fix` → *All checks passed!* on `8d128ff9d57`

```mermaid
%%{init: {'theme':'base','themeVariables':{'primaryColor':'#F2F0FE','primaryTextColor':'#333333','primaryBorderColor':'#5B39F3','lineColor':'#999999','secondaryColor':'#F4EFF6'}}}%%
pie showData title Phase Review Status — Scaffold Milestone (Checkpoint 1)
    "OPEN (pending review)" : 7
    "APPROVED" : 0
    "BLOCKED" : 0
```

*At this scaffold milestone, no findings have yet been identified. The
finding disposition pie chart will be re-rendered with real finding counts
as each per-phase review (§§3–9) is conducted during Checkpoints 2–5.*

---

## 3. Phase 1 — Infrastructure / DevOps

- **Reviewer**: Blitzy DevOps Reviewer Agent
- **Domain scope**: Reviews `__manifest__.py`, `__init__.py`, `hooks.py`, `data/*.xml`, and `demo/*.xml` files for module composition, install-time hooks, demo-data shape, and paper-format registration across both new accounting modules.
- **Status**: `OPEN`
- **Files in scope**: 0 (at scaffold milestone)

### 3.1 Files in Scope

*To be populated during Phase 1 review. The Infrastructure/DevOps file
slice will enter the working tree when the
`addons/account_financial_report_ce/**` and
`addons/account_bank_reconciliation_ce/**` artifacts are imported during
subsequent checkpoints.*

### 3.2 Findings

*No findings recorded at this scaffold milestone. Findings, with source
citations in `path:line` format per AAP §0.9.7, will be populated during
Phase 1 review.*

### 3.3 Remediation Log

*No remediations recorded at this scaffold milestone. Remediation commits
authored by `Blitzy Agent <agent@blitzy.com>` will be logged during
Phase 1 review per AAP §0.9.4.*

### 3.4 Verification Evidence

*No verification evidence recorded at this scaffold milestone. The
Phase 1 verification command per AAP §0.9.5 (manifest parse check via
`ast.parse`) will be executed during Phase 1 review once the source
artifacts are on disk.*

### 3.5 Disposition — `OPEN`

Phase 1 Infrastructure/DevOps review has not yet been conducted. The
phase will transition to `APPROVED` only after all addressable findings
are fixed and verified per AAP §0.10.3, or to `BLOCKED` with explicit
rationale and remediation steps per AAP §0.11 if blockers remain after
remediation is attempted.

---

## 4. Phase 2 — Security

- **Reviewer**: Blitzy Security Reviewer Agent
- **Domain scope**: Reviews `security/*.xml` and `security/ir.model.access.csv` files for role-based groups, access-control lists, and record-rule multi-company isolation.
- **Status**: `OPEN`
- **Files in scope**: 0 (at scaffold milestone)

### 4.1 Files in Scope

*To be populated during Phase 2 review. The Security file slice
(`addons/*/security/*.xml`, `addons/*/security/ir.model.access.csv`) will
enter the working tree during subsequent checkpoints.*

### 4.2 Findings

*No findings recorded at this scaffold milestone. Findings, with source
citations in `path:line` format per AAP §0.9.7, will be populated during
Phase 2 review.*

### 4.3 Remediation Log

*No remediations recorded at this scaffold milestone. Remediation commits
authored by `Blitzy Agent <agent@blitzy.com>` will be logged during
Phase 2 review per AAP §0.9.4.*

### 4.4 Verification Evidence

*No verification evidence recorded at this scaffold milestone. The
Phase 2 verification commands per AAP §0.9.5 (`grep` scans for `sudo()`
usage, `groups=` attributes on security XML records, and ACL row
completeness) will be executed during Phase 2 review once the source
artifacts are on disk.*

### 4.5 Disposition — `OPEN`

Phase 2 Security review has not yet been conducted. The phase will
transition to `APPROVED` only after all addressable findings are fixed
and verified per AAP §0.10.3, or to `BLOCKED` with explicit rationale
and remediation steps per AAP §0.11 if blockers remain after remediation
is attempted.

---

## 5. Phase 3 — Backend Architecture

- **Reviewer**: Blitzy Backend Architect Agent
- **Domain scope**: Reviews `models/**/*.py`, `report/*.py`, and `wizard/*.py` files for ORM model design, inheritance correctness, report parsers, transient wizard state, and algorithmic domain logic.
- **Status**: `OPEN`
- **Files in scope**: 0 (at scaffold milestone)

### 5.1 Files in Scope

*To be populated during Phase 3 review. The Backend Architecture file
slice (`addons/*/models/**/*.py`, `addons/*/report/*.py`,
`addons/*/wizard/*.py`) will enter the working tree during subsequent
checkpoints.*

### 5.2 Findings

*No findings recorded at this scaffold milestone. Findings, with source
citations in `path:line` format per AAP §0.9.7, will be populated during
Phase 3 review.*

### 5.3 Remediation Log

*No remediations recorded at this scaffold milestone. Remediation commits
authored by `Blitzy Agent <agent@blitzy.com>` will be logged during
Phase 3 review per AAP §0.9.4.*

### 5.4 Verification Evidence

*No verification evidence recorded at this scaffold milestone. The
Phase 3 verification command per AAP §0.9.5 (`python -m py_compile` over
every `.py` file in the Backend Architecture scope) will be executed
during Phase 3 review once the source artifacts are on disk.*

### 5.5 Disposition — `OPEN`

Phase 3 Backend Architecture review has not yet been conducted. The phase
will transition to `APPROVED` only after all addressable findings are
fixed and verified per AAP §0.10.3, or to `BLOCKED` with explicit
rationale and remediation steps per AAP §0.11 if blockers remain after
remediation is attempted.

---

## 6. Phase 4 — QA / Test Integrity

- **Reviewer**: Blitzy QA Integrity Agent
- **Domain scope**: Reviews `tests/**/*` in both modules plus all `test_data/**/*` files for test coverage, determinism, BDD alignment with user stories, fixture quality, and suite runtime.
- **Status**: `OPEN`
- **Files in scope**: 0 (at scaffold milestone)

### 6.1 Files in Scope

*To be populated during Phase 4 review. The QA/Test Integrity file slice
(`addons/*/tests/**/*`, plus the top-level `test_data/**/*` fixtures
already on disk at this scaffold milestone) will be enumerated in full
during Phase 4 review.*

### 6.2 Findings

*No findings recorded at this scaffold milestone. Findings, with source
citations in `path:line` format per AAP §0.9.7, will be populated during
Phase 4 review.*

### 6.3 Remediation Log

*No remediations recorded at this scaffold milestone. Remediation commits
authored by `Blitzy Agent <agent@blitzy.com>` will be logged during
Phase 4 review per AAP §0.9.4.*

### 6.4 Verification Evidence

*No verification evidence recorded at this scaffold milestone. The Phase 4
verification command per AAP §0.9.5 (the Odoo test runner invocation
`odoo-bin --test-enable --stop-after-init -d <db> -i
account_financial_report_ce,account_bank_reconciliation_ce --log-level=test
--without-demo=False`) is captured for the operator; it is not executed
during documentation authoring per AAP §0.7.2.*

### 6.5 Disposition — `OPEN`

Phase 4 QA / Test Integrity review has not yet been conducted. The phase
will transition to `APPROVED` only after all addressable findings are
fixed and verified per AAP §0.10.3, or to `BLOCKED` with explicit
rationale and remediation steps per AAP §0.11 if blockers remain after
remediation is attempted.

---

## 7. Phase 5 — Business / Domain

- **Reviewer**: Blitzy Business Analyst Agent
- **Domain scope**: Cross-references code behavior against the merged user stories and feature specifications; also reviews view XML, wizard view XML, report XML templates, and ticket `.md` files.
- **Status**: `OPEN`
- **Files in scope**: 0 (at scaffold milestone)

### 7.1 Files in Scope

*To be populated during Phase 5 review. The Business/Domain file slice
(`addons/*/views/*.xml`, `addons/*/wizard/*_views.xml`,
`addons/*/report/*_report.xml`, `addons/*/report/report_templates.xml`,
plus the `tickets/**/*.md` corpus — some of which is already on disk at
this scaffold milestone) will be enumerated in full during Phase 5
review.*

### 7.2 Findings

*No findings recorded at this scaffold milestone. Findings, with source
citations in `path:line` format per AAP §0.9.7, will be populated during
Phase 5 review.*

### 7.3 Remediation Log

*No remediations recorded at this scaffold milestone. Remediation commits
authored by `Blitzy Agent <agent@blitzy.com>` will be logged during
Phase 5 review per AAP §0.9.4.*

### 7.4 Verification Evidence

*No verification evidence recorded at this scaffold milestone. Phase 5
verification is citation-based per AAP §0.9.5 (cross-reference of
acceptance criteria in `tickets/stories/*.md` against implementation);
citations will be populated during Phase 5 review.*

### 7.5 Disposition — `OPEN`

Phase 5 Business / Domain review has not yet been conducted. The phase
will transition to `APPROVED` only after all addressable findings are
fixed and verified per AAP §0.10.3, or to `BLOCKED` with explicit
rationale and remediation steps per AAP §0.11 if blockers remain after
remediation is attempted.

---

## 8. Phase 6 — Frontend

- **Reviewer**: Blitzy Frontend Reviewer Agent
- **Domain scope**: Reviews SCSS files for visual hierarchy (reconciliation UI + report interactive view) and print layout (PDF export).
- **Status**: `OPEN`
- **Files in scope**: 0 (at scaffold milestone)

### 8.1 Files in Scope

*To be populated during Phase 6 review. The Frontend file slice
(`addons/*/static/src/scss/*.scss`) will enter the working tree during
subsequent checkpoints.*

### 8.2 Findings

*No findings recorded at this scaffold milestone. Findings, with source
citations in `path:line` format per AAP §0.9.7, will be populated during
Phase 6 review.*

### 8.3 Remediation Log

*No remediations recorded at this scaffold milestone. Remediation commits
authored by `Blitzy Agent <agent@blitzy.com>` will be logged during
Phase 6 review per AAP §0.9.4.*

### 8.4 Verification Evidence

*No verification evidence recorded at this scaffold milestone. The Phase 6
verification commands per AAP §0.9.5 (SCSS readability check via
`pathlib.Path.read_text()` and bracket-balance sanity check) will be
executed during Phase 6 review once the source artifacts are on disk.*

### 8.5 Disposition — `OPEN`

Phase 6 Frontend review has not yet been conducted. The phase will
transition to `APPROVED` only after all addressable findings are fixed
and verified per AAP §0.10.3, or to `BLOCKED` with explicit rationale
and remediation steps per AAP §0.11 if blockers remain after remediation
is attempted.

---

## 9. Phase 7 — Other SME (Documentation and Compliance)

- **Reviewer**: Blitzy Documentation and Compliance SME Agent
- **Domain scope**: Reviews Markdown documentation (developer setup, end-user guide, project guide, technical specifications, ticket templates), compliance artifacts, and the removal of pre-existing MkDocs / Backstage scaffolding from the upstream Odoo fork.
- **Status**: `OPEN`
- **Files in scope**: 0 (at scaffold milestone)

### 9.1 Files in Scope

*To be populated during Phase 7 review. The Other SME file slice
(`docs/**/*.md`, `blitzy/**/*.md`, `tickets/templates/*.md`, and any
root-level Markdown — some of which is already on disk at this scaffold
milestone) will be enumerated in full during Phase 7 review.*

### 9.2 Findings

*No findings recorded at this scaffold milestone. Findings, with source
citations in `path:line` format per AAP §0.9.7, will be populated during
Phase 7 review.*

### 9.3 Remediation Log

*No remediations recorded at this scaffold milestone. Remediation commits
authored by `Blitzy Agent <agent@blitzy.com>` will be logged during
Phase 7 review per AAP §0.9.4.*

### 9.4 Verification Evidence

*No verification evidence recorded at this scaffold milestone. The Phase 7
verification command per AAP §0.9.5 (Markdown fence-balance validator)
will be executed during Phase 7 review over the full Markdown corpus.*

### 9.5 Disposition — `OPEN`

Phase 7 Other SME (Documentation and Compliance) review has not yet been
conducted. The phase will transition to `APPROVED` only after all
addressable findings are fixed and verified per AAP §0.10.3, or to
`BLOCKED` with explicit rationale and remediation steps per AAP §0.11 if
blockers remain after remediation is attempted.

---


## 10. Consolidated Remediation Ledger

At this scaffold milestone (Checkpoint 1), no findings have yet been
recorded and no remediations have yet been applied. The ledger below
tracks, one row per remediation, every in-place change committed during
the per-phase reviews (§§3–9) across subsequent checkpoints. Each row
references the originating finding ID (`Pn-Fm`), the remediation commit
SHA authored by `Blitzy Agent <agent@blitzy.com>`, and a short
description per AAP §0.9.4.

### 10.1 Remediation Summary

| ID | Phase | Severity | Finding | Resolving Commit | Final Status |
|----|:-----:|:--------:|---------|------------------|:------------:|

*(The ledger header is shown above with no data rows. Rows will be
appended by each phase Agent as it records its remediations during
Checkpoints 2–5.)*

---

## 11. References

### 11.1 Git commits

- **Base commit**: `b58d620c4fb` (tip of `origin/19.0`, Odoo 19.0 CE)
- **Head commit**: `5a7e83629bc` (tip of `origin/pdlc`, PR #3 merge)
- **PR #2 merge**: `2c52c6b3aaf` (2026-02-02, merges `blitzy-4490115e-...`)
- **PR #3 merge**: `5a7e83629bc` (2026-04-17, merges `blitzy-ebbf6c96-...`)
- **Second Refine PR commit**: `8d128ff9d57` (2026-04-17, *"remediate security defects, navigation mismatch, and code-quality issues"*)
- **First Refine PR commit**: `14e7269e542` (2026-04-16, *"production-ready Phase 1 accounting modules"*)
- **Total commits between base and head**: 174

### 11.2 Source-code references (in-scope file map)

#### 11.2.1 Infrastructure / DevOps (17 files)

- `addons/account_bank_reconciliation_ce/__init__.py`
- `addons/account_bank_reconciliation_ce/__manifest__.py`
- `addons/account_bank_reconciliation_ce/hooks.py`
- `addons/account_bank_reconciliation_ce/data/reconciliation_data.xml`
- `addons/account_bank_reconciliation_ce/demo/demo_data.xml`
- `addons/account_bank_reconciliation_ce/models/__init__.py`
- `addons/account_bank_reconciliation_ce/report/__init__.py`
- `addons/account_bank_reconciliation_ce/tests/__init__.py`
- `addons/account_bank_reconciliation_ce/wizard/__init__.py`
- `addons/account_financial_report_ce/__init__.py`
- `addons/account_financial_report_ce/__manifest__.py`
- `addons/account_financial_report_ce/data/report_paperformat.xml`
- `addons/account_financial_report_ce/demo/demo_data.xml`
- `addons/account_financial_report_ce/models/__init__.py`
- `addons/account_financial_report_ce/report/__init__.py`
- `addons/account_financial_report_ce/tests/__init__.py`
- `addons/account_financial_report_ce/wizard/__init__.py`

#### 11.2.2 Security (4 files)

- `addons/account_bank_reconciliation_ce/security/bank_reconciliation_security.xml`
- `addons/account_bank_reconciliation_ce/security/ir.model.access.csv`
- `addons/account_financial_report_ce/security/account_financial_report_security.xml`
- `addons/account_financial_report_ce/security/ir.model.access.csv`

#### 11.2.3 Backend Architecture (21 files)

FR:

- `addons/account_financial_report_ce/models/financial_report.py`
- `addons/account_financial_report_ce/models/balance_sheet.py`
- `addons/account_financial_report_ce/models/profit_loss.py`
- `addons/account_financial_report_ce/models/cash_flow.py`
- `addons/account_financial_report_ce/models/general_ledger.py`
- `addons/account_financial_report_ce/models/trial_balance.py`
- `addons/account_financial_report_ce/models/aged_partner_balance.py`
- `addons/account_financial_report_ce/report/balance_sheet_report.py`
- `addons/account_financial_report_ce/report/profit_loss_report.py`
- `addons/account_financial_report_ce/report/cash_flow_report.py`
- `addons/account_financial_report_ce/report/general_ledger_report.py`
- `addons/account_financial_report_ce/report/trial_balance_report.py`
- `addons/account_financial_report_ce/report/aged_partner_balance_report.py`
- `addons/account_financial_report_ce/wizard/financial_report_wizard.py`

BR:

- `addons/account_bank_reconciliation_ce/models/bank_statement.py`
- `addons/account_bank_reconciliation_ce/models/bank_statement_line.py`
- `addons/account_bank_reconciliation_ce/models/bank_statement_import.py`
- `addons/account_bank_reconciliation_ce/models/reconciliation_matching_engine.py`
- `addons/account_bank_reconciliation_ce/models/reconciliation_rule.py`
- `addons/account_bank_reconciliation_ce/models/partial_reconcile_ext.py`
- `addons/account_bank_reconciliation_ce/report/reconciliation_status_report.py`
- `addons/account_bank_reconciliation_ce/wizard/reconciliation_wizard.py`
- `addons/account_bank_reconciliation_ce/wizard/bank_statement_import_wizard.py`

#### 11.2.4 QA / Test Integrity (25 files)

FR test modules:

- `addons/account_financial_report_ce/tests/common.py`
- `addons/account_financial_report_ce/tests/test_balance_sheet.py`
- `addons/account_financial_report_ce/tests/test_profit_loss.py`
- `addons/account_financial_report_ce/tests/test_cash_flow.py`
- `addons/account_financial_report_ce/tests/test_general_ledger.py`
- `addons/account_financial_report_ce/tests/test_trial_balance.py`
- `addons/account_financial_report_ce/tests/test_aged_partner.py`
- `addons/account_financial_report_ce/tests/test_export.py`

BR test modules:

- `addons/account_bank_reconciliation_ce/tests/common.py`
- `addons/account_bank_reconciliation_ce/tests/test_statement_import.py`
- `addons/account_bank_reconciliation_ce/tests/test_matching_engine.py`
- `addons/account_bank_reconciliation_ce/tests/test_manual_reconciliation.py`
- `addons/account_bank_reconciliation_ce/tests/test_reconciliation_rules.py`
- `addons/account_bank_reconciliation_ce/tests/test_partial_reconciliation.py`
- `addons/account_bank_reconciliation_ce/tests/test_candidate_date_window.py`

In-module test fixtures:

- `addons/account_bank_reconciliation_ce/tests/test_files/sample_statement.csv`
- `addons/account_bank_reconciliation_ce/tests/test_files/sample_statement.ofx`
- `addons/account_bank_reconciliation_ce/tests/test_files/sample_statement.qif`

Top-level fixtures:

- `test_data/bank_statements/sample.csv`
- `test_data/bank_statements/sample.ofx`
- `test_data/bank_statements/sample.qif`
- `test_data/bank_statements/sample_camt053.xml`
- `test_data/financial_reports/sample_journal_entries.csv`

#### 11.2.5 Business / Domain (54 files)

EPIC + features:

- `tickets/README.md`
- `tickets/EPIC-001-enterprise-accounting.md`
- `tickets/features/FEATURE-001-financial-reporting.md`
- `tickets/features/FEATURE-002-bank-reconciliation.md`
- `tickets/features/FEATURE-003-budget-management.md`
- `tickets/features/FEATURE-004-asset-management.md`
- `tickets/features/FEATURE-005-deferred-revenue.md`
- `tickets/features/FEATURE-006-payment-followups.md`

Stories — financial-reporting:

- `tickets/stories/financial-reporting/FR-001-balance-sheet.md`
- `tickets/stories/financial-reporting/FR-002-profit-loss.md`
- `tickets/stories/financial-reporting/FR-003-cash-flow.md`
- `tickets/stories/financial-reporting/FR-004-general-ledger.md`
- `tickets/stories/financial-reporting/FR-005-trial-balance.md`
- `tickets/stories/financial-reporting/FR-006-aged-partner-balance.md`
- `tickets/stories/financial-reporting/FR-007-export-drilldown.md`

Stories — bank-reconciliation:

- `tickets/stories/bank-reconciliation/BR-001-statement-import.md`
- `tickets/stories/bank-reconciliation/BR-002-algorithmic-matching.md`
- `tickets/stories/bank-reconciliation/BR-003-manual-reconciliation.md`
- `tickets/stories/bank-reconciliation/BR-004-reconciliation-rules.md`
- `tickets/stories/bank-reconciliation/BR-005-partial-reconciliation.md`

Stories — deferred features (20 docs-only):

- `tickets/stories/asset-management/AM-001-*.md` through `AM-006-*.md` (6)
- `tickets/stories/budget-management/BM-001-*.md` through `BM-005-*.md` (5)
- `tickets/stories/deferred-revenue/DR-001-*.md` through `DR-004-*.md` (4)
- `tickets/stories/payment-followups/PF-001-*.md` through `PF-005-*.md` (5)

View / report XML:

- `addons/account_bank_reconciliation_ce/views/bank_reconciliation_views.xml`
- `addons/account_bank_reconciliation_ce/views/menuitem.xml`
- `addons/account_financial_report_ce/views/menuitem.xml`
- `addons/account_bank_reconciliation_ce/wizard/reconciliation_wizard_views.xml`
- `addons/account_bank_reconciliation_ce/wizard/bank_statement_import_wizard_views.xml`
- `addons/account_financial_report_ce/wizard/financial_report_wizard_views.xml`
- `addons/account_bank_reconciliation_ce/report/reconciliation_report.xml`
- `addons/account_financial_report_ce/report/report_templates.xml`
- `addons/account_financial_report_ce/report/balance_sheet_report.xml`
- `addons/account_financial_report_ce/report/profit_loss_report.xml`
- `addons/account_financial_report_ce/report/cash_flow_report.xml`
- `addons/account_financial_report_ce/report/general_ledger_report.xml`
- `addons/account_financial_report_ce/report/trial_balance_report.xml`
- `addons/account_financial_report_ce/report/aged_partner_balance_report.xml`

#### 11.2.6 Frontend (3 files)

- `addons/account_bank_reconciliation_ce/static/src/scss/reconciliation.scss`
- `addons/account_financial_report_ce/static/src/scss/report.scss`
- `addons/account_financial_report_ce/static/src/scss/report_print.scss`

#### 11.2.7 Other SME — Documentation and Compliance (13 files)

Added (7):

- `blitzy/documentation/Project Guide.md`
- `blitzy/documentation/Technical Specifications.md`
- `docs/SETUP.md`
- `docs/USER_GUIDE.md`
- `tickets/templates/epic-template.md`
- `tickets/templates/feature-template.md`
- `tickets/templates/story-template.md`

Deleted (6, from upstream pre-Blitzy fork):

- `catalog-info.yaml` (Backstage TechDocs catalog entry)
- `mkdocs.yml` (MkDocs site generator config)
- `doc/index.md`, `doc/project-guide.md`, `doc/technical-specifications.md`
- `docs/index.md`

### 11.3 Documentation cross-references

- [`./PROJECT_GUIDE.md`](./PROJECT_GUIDE.md) — root-level project guide (referenced per AAP §0.5)
- [`./blitzy/documentation/Project Guide.md`](./blitzy/documentation/Project%20Guide.md) — historical project-status artifact (730 lines)
- [`./blitzy/documentation/Technical Specifications.md`](./blitzy/documentation/Technical%20Specifications.md) — historical Phase-1 technical spec (769 lines)
- [`./docs/SETUP.md`](./docs/SETUP.md) — developer environment setup guide (538 lines)
- [`./docs/USER_GUIDE.md`](./docs/USER_GUIDE.md) — end-user workflow guide (489 lines)
- [`./tickets/README.md`](./tickets/README.md) — ticket corpus index
- [`./tickets/EPIC-001-enterprise-accounting.md`](./tickets/EPIC-001-enterprise-accounting.md) — master epic

### 11.4 Rules applied

- User-provided **Segmented PR Review** rule — YAML frontmatter schema, 7 domain phases, disposition vocabulary (`OPEN`/`IN_REVIEW`/`BLOCKED`/`APPROVED`), reviewer Agent naming, `CODE_REVIEW.md` / `PROJECT_GUIDE.md` cross-link obligation
- User-provided **Executive Presentation** rule — referenced for the parallel deliverable `blitzy-deck/executive-summary.html` (not authored in this file)

### 11.5 Commands used for archaeology

```bash
# Commit inventory
git log origin/19.0..origin/pdlc --pretty=format:"%h|%ae|%ci|%s"

# File inventory
git diff origin/19.0..origin/pdlc --name-status
git diff origin/19.0..origin/pdlc --numstat
git diff origin/19.0..origin/pdlc --shortstat

# Merge analysis
git log origin/19.0..origin/pdlc --merges --pretty=format:"%h|%s|%ci"
git show --pretty="%h -> parents: %p" 2c52c6b3aaf --no-patch
git show --pretty="%h -> parents: %p" 5a7e83629bc --no-patch

# Branch attribution
git log origin/19.0..6f675489078 --pretty=format:"%h"       # PR #2 leg (49 commits)
git log 2c52c6b3aaf..58f003542d0 --pretty=format:"%h"        # PR #3 leg (123 commits)

# Source content retrieval (working branch lacks merged files)
git show origin/pdlc:"blitzy/documentation/Project Guide.md"
git show origin/pdlc:addons/account_financial_report_ce/__manifest__.py
git show origin/pdlc:addons/account_bank_reconciliation_ce/__manifest__.py
git show origin/pdlc:addons/account_bank_reconciliation_ce/models/reconciliation_matching_engine.py
```

### 11.6 YAML Frontmatter Validation

```bash
python -c "import yaml,pathlib; yaml.safe_load(pathlib.Path('CODE_REVIEW.md').read_text().split('---',2)[1])"
```

Expected: exits 0. Frontmatter parses as a dict with keys
`review_id`, `generated_at`, `base_commit`, `head_commit`,
`archaeology_commits`, `files_in_scope`, `insertions`, `deletions`,
`overall_status`, `phases` (list of 7 entries each with
`id`/`domain`/`reviewer`/`status`/`files_in_scope`/`findings_total`/
`findings_addressed`/`blockers`).

### 11.7 Document Authorship and Contract

This `CODE_REVIEW.md` was scaffolded by the Blitzy Platform on 2026-04-21
as part of a retrospective archaeology + Segmented PR Review of the 174
commits merged into `origin/pdlc`. At this Checkpoint 1 Foundations
milestone, the document captures (a) the archaeology inventory (§2) and
(b) the seven OPEN phase-section scaffolds (§§3–9) that will be populated
incrementally during Checkpoints 2–5. Per the user's *"treat all identified
changes as if they were changes that were actively made during this run"*
directive, every merged commit is in scope for review; each phase Agent
will audit its assigned file slice as the source artifacts are imported
in subsequent checkpoints.

`overall_status` is `OPEN` until every `phases[*].status` has transitioned
to `APPROVED` or `BLOCKED` per AAP §0.10.3. No remediations or
dispositions have been recorded at this scaffold milestone; §10 begins
with an empty ledger that will accrue one row per in-place fix committed
by the phase Agents.

<!-- END OF CODE_REVIEW.md -->
