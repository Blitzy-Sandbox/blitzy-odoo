# User Guide — Enterprise Accounting Parity (Phase 1)

This guide walks a first-time user through the two Odoo 19.0
Community Edition modules delivered in Phase 1 of the Enterprise
Accounting Parity initiative:

- `account_financial_report_ce` — GAAP/IFRS-compliant financial
  reports (Balance Sheet, Profit & Loss, Cash Flow, General Ledger,
  Trial Balance, Aged Receivable/Payable).
- `account_bank_reconciliation_ce` — Bank statement import, smart
  algorithmic matching, rule-based auto-reconciliation, and manual
  reconciliation workflows.

If you have not yet set up your local development environment, start
with [docs/SETUP.md](./SETUP.md) first. This guide assumes Odoo is
running, PostgreSQL is reachable, and you can log into the web
interface at `http://127.0.0.1:8069/` as `admin` / `admin`.

The six sections below follow a linear workflow: install the modules
(§1), navigate to their menus (§2), import sample data (§3), reconcile
transactions (§4), generate financial reports (§5), and produce aging
analyses with custom bucket thresholds (§6).

---

## (1) Installing and upgrading the custom modules

### First-time installation

Both modules are installed with a single invocation of `odoo-bin`.
From the repository root with the Python venv activated:

```bash
cd $REPO_ROOT
source venv/bin/activate

./odoo-bin \
  --addons-path=addons,odoo/addons \
  --db_host=127.0.0.1 --db_port=5432 \
  --db_user=odoo --db_password=odoo \
  -d odoo_dev \
  -i account_financial_report_ce,account_bank_reconciliation_ce \
  --stop-after-init
```

What this does:

- Creates (or re-uses) the `odoo_dev` PostgreSQL database.
- Installs all transitive dependencies, including the core `account`
  and `analytic` modules.
- Registers the security groups `group_bank_reconciliation_user` and
  `group_bank_reconciliation_manager`, which inherit from
  `account.group_account_user` and `account.group_account_manager`
  respectively.
- Runs the post-install hook that grants `base.group_user` to every
  user already belonging to `account.group_account_manager` so that
  binary uploads (attachments, bank statement files) work out of the
  box for administrators.

### Upgrading after code changes

If you modify any XML view, Python model, CSV ACL, or SCSS asset in
either module, reload them with `-u`:

```bash
./odoo-bin \
  --addons-path=addons,odoo/addons \
  --db_host=127.0.0.1 --db_port=5432 \
  --db_user=odoo --db_password=odoo \
  -d odoo_dev \
  -u account_financial_report_ce,account_bank_reconciliation_ce \
  --stop-after-init
```

The `-u` flag is safe to re-run as often as needed — XML view
definitions are replayed on each upgrade (security records with
`noupdate="1"` are intentionally exempted), and data migrations are
idempotent.

### Verifying the installation

After installation, launch the HTTP server and log in:

```bash
./odoo-bin \
  --addons-path=addons,odoo/addons \
  --db_host=127.0.0.1 --db_port=5432 \
  --db_user=odoo --db_password=odoo \
  -d odoo_dev \
  --dev=xml,reload,qweb
```

Then visit `http://127.0.0.1:8069/`, log in with `admin` / `admin`,
and navigate to **Apps**. Use the search bar to look for:

- `Financial Reports (Community)` — displayed with a green check mark
  when `account_financial_report_ce` is installed.
- `Bank Reconciliation (Community)` — displayed with a green check
  mark when `account_bank_reconciliation_ce` is installed.

If either is missing the check mark, click it and press **Install**.

---

## (2) Navigating to Bank Reconciliation via its menu path

The Bank Reconciliation module registers a top-level workflow menu
under the main **Accounting** application. The exact menu path is:

```
Accounting → Bank Reconciliation
```

### Menu hierarchy

The root menu is parented on `account.menu_finance_entries` and is
scoped to `account.group_account_user`, so only full Accounting users
(not read-only users) can see it. The sub-menu structure is:

| Menu Item                 | Purpose                                                 | Access group                          |
|---------------------------|---------------------------------------------------------|---------------------------------------|
| **Import Statements**     | Upload CSV / OFX / QIF / CAMT.053 bank statement files  | `account.group_account_user`          |
| **Reconciliation**        | Main reconciliation wizard (algorithmic + manual match) | `account.group_account_user`          |
| **Reconciliation Status** | Browse all match proposals with confidence scores       | `account.group_account_user`          |
| **Reconciliation Rules**  | Configure matching rules (regex, amount, priority)      | `account.group_account_manager`       |

### Accessing the menu as a non-admin user

If you log in as a user who holds only the **Accounting / Billing**
role (`account.group_account_invoice`), the **Bank Reconciliation**
menu will be hidden because that role does not include the required
`group_account_user` permission. To confirm menu visibility for
regular accounting users:

1. Create a test user: **Settings → Users & Companies → Users → New**.
2. Set **User Type** to `Internal User`.
3. Under **Permissions**, set **Accounting** to `User`.
4. Save, log out, log back in as the new user.
5. Open the Accounting app — the **Bank Reconciliation** menu must
   appear between **Journal Entries** and **Configuration**.

> If the menu is still missing, re-run the module upgrade with `-u`;
> the `group_bank_reconciliation_user` group is extended to imply from
> `account.group_account_user` on every upgrade.

---

## (3) Importing a bank statement using a fixture file

The repository ships with four pre-made statement fixtures in
`test_data/bank_statements/` that cover every format supported by the
Phase 1 import wizard:

| Format       | File                              | Rows | Balance info included |
|--------------|-----------------------------------|------|-----------------------|
| CSV          | `test_data/bank_statements/sample.csv` | 8    | No (computed)         |
| OFX 1.02     | `test_data/bank_statements/sample.ofx` | 8    | Ledger balance only   |
| QIF          | `test_data/bank_statements/sample.qif` | 8    | No                    |
| CAMT.053.001.02 | `test_data/bank_statements/sample.xml` | 8    | OPBD and CLBD         |

All four fixtures describe the same 8 transactions (dates spanning
2024-02-01 to 2024-02-28, credits of 6 862.50 and debits of 1 531.50)
so you can cross-validate that all parsers produce identical results.

### Step-by-step import workflow

1. Ensure a **Bank** journal exists. If not:
   - Navigate to **Accounting → Configuration → Journals**.
   - Click **New**, set **Type** to `Bank`, give it a meaningful name
     (e.g., `My Checking Account`), and save.

2. Open the import wizard:
   - Navigate to **Accounting → Bank Reconciliation → Import
     Statements**.
   - Or, equivalently, from **Accounting → Bank Statements**, use the
     **Import** button in the list view.

3. In the wizard form, fill in:
   - **Journal** — pick the bank journal from step 1.
   - **File Type** — pick one of `CSV`, `OFX`, `QIF`, or `CAMT.053`.
     You can also leave it on **Auto-detect** to have the wizard
     choose based on the file extension and magic headers.
   - **File** — click the upload icon and select the fixture file
     from `test_data/bank_statements/`. For example:
     - CSV: `test_data/bank_statements/sample.csv`
     - OFX: `test_data/bank_statements/sample.ofx`
     - QIF: `test_data/bank_statements/sample.qif`
     - CAMT.053: `test_data/bank_statements/sample.xml`

4. Click **Preview**. The wizard shows the first several parsed rows
   with dates, amounts, references, and partner names. Verify:
   - Row count matches the format's expected transactions (8 for the
     sample fixtures).
   - Date format is recognized (`YYYY-MM-DD`).
   - Credits appear as positive amounts, debits as negative.
   - References such as `REF-0201` or `INV/2024/0201` are captured.

5. Click **Import**. The wizard closes and an
   `account.bank.statement` record is created with 8
   `account.bank.statement.line` rows.

6. Open the new statement:
   - Navigate to **Accounting → Bank Statements**.
   - Click the statement dated `2024-02-28` (CAMT.053 includes the
     closing balance as the statement date).
   - Confirm the line count, total debit, total credit, and (for
     CAMT.053) the opening/closing balances match the fixture.

### CSV column mapping (optional)

The CSV parser auto-detects columns named `Date`, `Label`, `Amount`,
`Reference`, and `Partner`. If your real-world CSV uses different
headers, the wizard displays a **Column Mapping** table where you can
map each source column to the target field. The fixture file uses the
canonical header names so no mapping is required.

### Duplicate-import protection

The import wizard computes a hash over (date, amount, reference) for
every parsed line and rejects an import if an identical hash already
exists on the same journal. Re-importing `sample.csv` on the same
journal will fail with a `UserError` explaining that 8 duplicate lines
were detected.

---

## (4) Running the reconciliation wizard and interpreting match results

Once a statement is imported, the next step is to reconcile each
statement line with the correct journal entries (customer payments,
supplier bills, bank transfers, etc.) already present in the ledger.

### Opening the reconciliation wizard

1. Navigate to **Accounting → Bank Reconciliation → Reconciliation**.
2. The wizard opens in a form view. Fill in the top filter group:
   - **Journal** — the bank journal whose statements you want to
     reconcile (pre-filled if you launched from an active statement).
   - **Statement** — optional; leave empty to reconcile all un-posted
     lines across every imported statement on this journal.
3. Switch to the **Write-Off Settings** page. You will find these
   configurable fields:
   - **Write-Off Account** — account used for small unmatchable
     differences.
   - **Write-Off Tolerance** — percentage; matches whose difference
     is within the tolerance are auto-accepted with a write-off line.
   - **Candidate Date Window (Days)** — default `90`. Restricts the
     matching engine to journal entries dated within this many days
     of each statement line. Reduce to 30 or 15 for high-volume
     bank accounts to speed up matching.
4. Click **Find Matches** (or **Save & Match**). The engine runs the
   matching algorithm for every unreconciled statement line.

### Interpreting confidence scores

The matching engine scores each candidate on a weighted sum of four
signals:

| Signal    | Default weight | Rationale                                                |
|-----------|----------------|----------------------------------------------------------|
| Amount    | 0.35           | Exact amount match is the strongest indicator            |
| Partner   | 0.25           | Partner name/reference alignment (elevated in Phase 1)   |
| Reference | 0.25           | EndToEndId, memo, invoice number similarity              |
| Date      | 0.15           | Proximity in days between statement and journal entry    |

The weighted score produces a confidence percentage and a confidence
tier:

- **High (≥ 95%)** — green badge. Eligible for auto-reconciliation
  when the matching rule allows.
- **Medium (70–94%)** — yellow badge. Requires user confirmation.
- **Low (50–69%)** — orange badge. Flagged for manual review.
- **Below 50%** — discarded; no suggestion is shown.

> The 95% threshold satisfies the FEATURE-002 acceptance criterion
> "≥95% matching accuracy for high-confidence auto-reconciliation".

### Acting on suggestions

For each statement line the wizard shows the top-scored candidate with
its confidence badge:

- Click **Match** to accept the suggestion. An
  `account.partial.reconcile` record is created linking the statement
  line's journal entry to the matched invoice/bill entry. The two
  `account.move.line` rows are marked with a shared
  `full_reconcile_id`.
- Click **Skip** to defer; the line stays unreconciled and will
  reappear on the next engine run.
- Click **Pick Manually** to open a search popup listing every
  unreconciled `account.move.line` on the journal. Filter by amount,
  partner, or date and click a row to reconcile.
- For partial matches (statement amount ≠ journal amount and the
  difference is within tolerance), the wizard prompts for a write-off
  amount and account.

### Audit trail

Every reconciliation action (match, unmatch, partial match, write-off)
is recorded via the standard Odoo mechanisms:

- `account.partial.reconcile` — row-level debit/credit pairing.
- `account.full.reconcile` — aggregate row created when a set of
  partial reconciliations balances to zero.
- `mail.thread` on `account.move` — user, timestamp, and action are
  logged in the chatter for both affected entries.

To inspect the audit trail, open either affected `account.move` and
scroll to the Chatter; you will see messages like `Reconciled with
INV/2024/0201 on 2024-03-05 by Admin User (confidence 98%)`.

### Unmatching

If you reconcile by mistake:

1. Open the statement line.
2. Click the **Unreconcile** button in the form header.
3. The partial reconcile record is deleted and both
   `account.move.line` rows become eligible for matching again. The
   chatter records the unreconciliation event with the reason.

---

## (5) Generating a financial report from the Accounting menu

The Financial Reports module registers a unified wizard and six
dedicated shortcuts under **Accounting → Reporting → Financial
Reports**. Any report can be produced via either entry point:

- **All Financial Reports** — unified wizard; lets you pick the report
  type and any filter at runtime.
- **Financial Statements → Balance Sheet / Profit and Loss / Cash
  Flow Statement** — pre-selects the report type.
- **Ledger Reports → General Ledger / Trial Balance** — pre-selects
  the report type.
- **Aged Reports → Aged Receivable / Aged Payable** — pre-selects the
  report type and enables the aging bucket group (see section 6).

### Worked example: Balance Sheet

1. Navigate to **Accounting → Reporting → Financial Reports →
   Financial Statements → Balance Sheet**. The report wizard opens
   with **Report Type** pre-set to `Balance Sheet`.
2. Fill in:
   - **Company** — defaults to the current user's company.
   - **As of Date** — pick a reporting date, e.g., `2024-03-31`.
   - **Comparison Period** — optional; toggle to show columns for a
     previous period such as `2023-12-31`.
   - **Hide Zero Balance** — toggle on to suppress accounts with
     zero activity.
3. Switch to the **Display Options** tab to refine presentation:
   - **Show Account Codes** — prefixes each line with the GL code.
   - **Group by Account Type** — forces section grouping (Assets /
     Liabilities / Equity).
4. Click **Generate**. The balance sheet renders inside a read-only
   form view with drill-down hyperlinks on each amount.
5. Click any amount to drill down; you are redirected to a filtered
   `account.move.line` list showing only the rows that contribute to
   that balance. Use the breadcrumb **< Back** to return to the
   report.
6. Validate the accounting equation: at the bottom of the report a
   **Validation** badge reads `Assets = Liabilities + Equity ✓` in
   green if the report is consistent, or a red warning if not.

### Exporting to PDF

From the report form view, click **Export PDF**. Odoo renders the
QWeb template via wkhtmltopdf and streams the file to your browser.
Expected performance: under 15 seconds for a ledger of 100 000 lines.

### Exporting to Excel

From the report form view, click **Export Excel**. The module uses
`XlsxWriter` to produce a `.xlsx` file with:

- One worksheet per report section (Assets, Liabilities, Equity).
- Formula-backed subtotals so you can audit the computation.
- Frozen header row for scrolling.
- Expected performance: under 10 seconds for a ledger of 100 000
  lines.

### Other reports

The workflow is identical for the remaining report types:

| Report type                | Key filters                                                | Validation performed                             |
|----------------------------|------------------------------------------------------------|--------------------------------------------------|
| Profit and Loss            | Date range, comparison period                              | Revenue − Expenses = Net Income                  |
| Cash Flow Statement        | Date range, direct vs indirect method                      | Starting cash + Δ = Ending cash                  |
| General Ledger             | Date range, account range, partner filter                  | Opening + transactions = Closing per account     |
| Trial Balance              | Date range, hide-zero toggle                               | Σ Debits = Σ Credits                             |
| Aged Receivable / Payable  | Date, aging bucket thresholds (see §6)                     | Σ buckets = Open balance per partner             |

---

## (6) Generating an aging report and modifying bucket thresholds

Aged Receivable and Aged Payable reports classify open partner
balances into configurable aging buckets. Phase 1 added
**user-configurable bucket thresholds** so you can match your
organization's collection policy.

### Opening the aged receivable wizard

1. Navigate to **Accounting → Reporting → Financial Reports → Aged
   Reports → Aged Receivable** (or **Aged Payable** for AP).
2. The report wizard opens with **Report Type** pre-set to
   `Aged Receivable`.
3. Fill in the **General Options** group:
   - **As of Date** — aging reference point, default = today.
   - **Partners** — optional filter; leave empty to include every
     partner with an open balance.

### Configuring aging buckets

Switch to the **Display Options** tab. You will see a group labeled
**Aging Buckets (Days)** with four Integer fields:

| Field              | Default | Typical uses                                   |
|--------------------|---------|------------------------------------------------|
| **Bucket 1 Days**  | `30`    | "Current / 0–30 days" tier                     |
| **Bucket 2 Days**  | `60`    | "31–60 days" tier                              |
| **Bucket 3 Days**  | `90`    | "61–90 days" tier (cliff where reminders fire) |
| **Bucket 4 Days**  | `120`   | "91–120 days" tier (collections cutoff)        |

Any open balance older than `Bucket 4 Days` falls into the implicit
"120+ days" overflow bucket displayed at the far right of the report.

The thresholds must be strictly increasing; the wizard validates this
on save and raises a helpful error if, for example, you enter
`30, 20, 90, 120`.

### Worked example: custom aging policy

Suppose your AR policy is: **Current / 15 / 30 / 45 / 60+**.

1. Set **Bucket 1 Days** = `15`.
2. Set **Bucket 2 Days** = `30`.
3. Set **Bucket 3 Days** = `45`.
4. Set **Bucket 4 Days** = `60`.
5. Click **Generate**. The aging report renders with five columns:
   - `0–15 days`
   - `16–30 days`
   - `31–45 days`
   - `46–60 days`
   - `61+ days` (overflow)
6. Each partner row shows the open balance distributed across these
   five buckets, plus a **Total Open** column on the right-hand side.
   Partners with a fully-paid history are omitted.
7. Click any partner to drill down to the list of unpaid invoices
   contributing to that partner's open balance.

### Switching report types preserves filters

If you change **Report Type** from `Aged Receivable` to another value
(for example `Balance Sheet`), the **Aging Buckets (Days)** group
disappears from the **Display Options** tab — it is only visible when
`report_type in ('aged_receivable', 'aged_payable')`. Switching back
to an aging report restores the group with the values you last
entered.

### Exporting an aged report

The **Export PDF** and **Export Excel** buttons at the top of the
generated report behave identically to the other financial reports
(§5). The PDF layout renders each bucket as a column with a right-
aligned amount; the Excel export places each bucket on its own sheet
column so you can pivot or chart the data.

---

## (7) Where to go next

- Problems? See the **Troubleshooting** section in
  [docs/SETUP.md](./SETUP.md) for environment fixes.
- Want to automate the workflow? Each wizard exposes a stable Python
  API — see `addons/account_financial_report_ce/wizard/` and
  `addons/account_bank_reconciliation_ce/wizard/` for method names
  and expected arguments.
- Feature specifications and acceptance criteria:
  - `tickets/features/FEATURE-001-financial-reporting.md`
  - `tickets/features/FEATURE-002-bank-reconciliation.md`
  - `tickets/stories/financial-reporting/FR-*.md`
  - `tickets/stories/bank-reconciliation/BR-*.md`
- Epic-level roadmap: `tickets/EPIC-001-enterprise-accounting.md`.

---

*Last updated: as part of the Phase 1 Refine-PR validation pass.*
