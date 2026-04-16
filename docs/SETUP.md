# Development Environment Setup Guide

This guide walks a first-time contributor through setting up a working
development environment for the Odoo 19.0 Community Edition codebase
that hosts the `account_financial_report_ce` and
`account_bank_reconciliation_ce` custom modules.

Follow the six sections in order. Each section lists the prerequisites
it assumes, the exact commands you should run, and the expected output.

> Repository root in this guide is referred to as `$REPO_ROOT`. Replace it
> with the absolute path to your local checkout, e.g.
> `/home/<you>/odoo` or `/tmp/blitzy/blitzy-odoo/<branch>`.

---

## (a) Prerequisites

Before you can build and run the stack you must have the following
software installed on your workstation.

### Operating system

- **Linux** (Ubuntu 22.04 / 24.04 LTS recommended) or **macOS** 13+.
- **Windows** users should work inside **WSL 2** running Ubuntu 22.04+.

### System packages

The commands below are for Ubuntu/Debian. Use the equivalent package
manager (Homebrew, dnf, etc.) on other platforms.

```bash
sudo apt-get update
sudo apt-get install -y \
    build-essential \
    python3 python3-dev python3-venv python3-pip \
    postgresql-client \
    libxml2-dev libxslt1-dev \
    libldap2-dev libsasl2-dev \
    libjpeg-dev libpq-dev \
    libssl-dev libffi-dev \
    node-less \
    git curl wget unzip \
    wkhtmltopdf
```

### Required versions

| Tool         | Minimum       | Recommended   | Notes                                              |
|--------------|---------------|---------------|----------------------------------------------------|
| Python       | 3.10          | 3.12          | Upper bound 3.13 (see `odoo/release.py`)           |
| PostgreSQL   | 13            | 16            | Required for all Odoo 19 databases                 |
| Node.js      | 18 LTS        | 20 LTS        | Only needed for frontend asset rebuilding          |
| wkhtmltopdf  | 0.12.6        | 0.12.6        | Required for QWeb-to-PDF report rendering          |
| Git          | 2.30          | 2.43+         | Used for branch management and commit workflow     |
| Docker       | 24.0          | 26.0+         | Optional, used in section (c) for PostgreSQL       |

Verify everything is installed:

```bash
python3 --version        # >= 3.10
psql --version           # >= 13
wkhtmltopdf --version    # 0.12.6
node --version           # >= 18 (optional)
docker --version         # optional, required only for container-based PG
```

### Repository layout

Clone (or change into) the repository:

```bash
git clone <remote-url> $REPO_ROOT
cd $REPO_ROOT
```

Confirm you are on the working branch:

```bash
git status
git branch --show-current
```

---

## (b) Activating the Python venv

All Python dependencies (Odoo itself plus the `requirements.txt` pins)
are installed inside a project-local virtual environment under
`$REPO_ROOT/venv/`.

### Create the venv (first time only)

If `venv/` does not already exist, create it with the system Python:

```bash
cd $REPO_ROOT
python3 -m venv venv
```

### Activate the venv

Every shell that runs Odoo or the test suite must activate the venv
first:

```bash
cd $REPO_ROOT
source venv/bin/activate
```

Your prompt should now be prefixed with `(venv)`. Verify the Python
interpreter points to the in-project venv:

```bash
which python3              # .../$REPO_ROOT/venv/bin/python3
python3 --version          # 3.12.x (or 3.10 / 3.11 / 3.13)
```

### Install Python dependencies

With the venv active, upgrade packaging tooling and install the
requirements plus Odoo in editable mode:

```bash
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
pip install -e .
```

This installs `psycopg2`, `openpyxl`, `XlsxWriter`, `ofxparse`, `lxml`,
`reportlab`, `Babel`, `freezegun`, and every other dependency required
by the Phase 1 modules.

### Deactivating

When you are finished in a shell, leave the venv with:

```bash
deactivate
```

---

## (c) Starting the PostgreSQL Docker container

The two in-scope modules require a reachable PostgreSQL cluster.
The canonical local-development approach is to run PostgreSQL 16 in a
Docker container so you do not have to pollute the host system.

> If you prefer the system PostgreSQL service (`pg_ctlcluster 16 main
> start`) with a superuser role matching your OS user, see the
> **Alternative** subsection at the end of this section — Odoo works
> equivalently in either mode.

### Pull and start the container

```bash
docker pull postgres:16

docker run -d \
  --name odoo-postgres \
  -e POSTGRES_USER=odoo \
  -e POSTGRES_PASSWORD=odoo \
  -e POSTGRES_DB=postgres \
  -p 5432:5432 \
  -v odoo-pg-data:/var/lib/postgresql/data \
  postgres:16
```

Flags used:

- `-e POSTGRES_USER=odoo` — creates an `odoo` superuser that Odoo
  connects as by default.
- `-e POSTGRES_PASSWORD=odoo` — password matching the default Odoo
  configuration.
- `-p 5432:5432` — exposes PostgreSQL on the host's port 5432.
- `-v odoo-pg-data:/var/lib/postgresql/data` — persists the cluster in
  a named Docker volume across container restarts.

### Verify the container is healthy

```bash
docker ps --filter name=odoo-postgres
docker logs odoo-postgres | tail -n 20
psql -h 127.0.0.1 -p 5432 -U odoo -d postgres -c "SELECT version();"
# Enter password "odoo" when prompted
```

You should see a `PostgreSQL 16.x on ...` banner. If `psql` is not
installed on the host, you can still verify by executing inside the
container:

```bash
docker exec -it odoo-postgres psql -U odoo -d postgres -c "SELECT 1;"
```

### Stopping and restarting

```bash
docker stop odoo-postgres       # graceful shutdown
docker start odoo-postgres      # resume (data is preserved)
docker rm -f odoo-postgres      # permanent removal (volume survives)
docker volume rm odoo-pg-data   # wipe data (destructive)
```

### Alternative: system PostgreSQL service

If you prefer not to use Docker, install PostgreSQL 16 via `apt-get
install postgresql-16`, start it with `sudo pg_ctlcluster 16 main
start`, and create an `odoo` role:

```bash
sudo -u postgres createuser --superuser --createdb odoo
sudo -u postgres psql -c "ALTER USER odoo WITH PASSWORD 'odoo';"
```

From Odoo's perspective the two approaches are identical — both expose
a PostgreSQL 16 cluster on `127.0.0.1:5432` with an `odoo` superuser.

---

## (d) Running the Odoo dev server

With the venv activated (section b) and PostgreSQL running (section c),
you can now launch the Odoo application server.

### One-time: install the Phase 1 modules into a fresh database

This command creates the database `odoo_dev` and installs both
in-scope modules plus all their transitive dependencies (`account`,
`analytic`, `base`, etc.):

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

Expected final lines in the log (no `EvalError`, no `UncaughtPromiseError`):

```
INFO odoo_dev odoo.modules.loading: Modules loaded.
INFO odoo_dev odoo.modules.registry: Registry loaded in <N>s
```

### Upgrading modules after code changes

Whenever you edit Python, XML, CSV, or SCSS files inside the two
modules, reload them with `-u`:

```bash
./odoo-bin \
  --addons-path=addons,odoo/addons \
  --db_host=127.0.0.1 --db_port=5432 \
  --db_user=odoo --db_password=odoo \
  -d odoo_dev \
  -u account_financial_report_ce,account_bank_reconciliation_ce \
  --stop-after-init
```

### Launching the HTTP server for browser-based testing

To interact with the running Odoo instance in a browser:

```bash
./odoo-bin \
  --addons-path=addons,odoo/addons \
  --db_host=127.0.0.1 --db_port=5432 \
  --db_user=odoo --db_password=odoo \
  -d odoo_dev \
  --dev=xml,reload,qweb
```

Then open `http://127.0.0.1:8069/` and log in with
`admin` / `admin` (default for a freshly created database).

`--dev=xml,reload,qweb` reloads XML views, Python code, and QWeb
templates on disk changes, which is ideal during active development.

### Tailing logs in another shell

```bash
tail -f $REPO_ROOT/odoo.log   # if you launched with --logfile=odoo.log
# otherwise the log is printed to stdout in the foreground shell
```

---

## (e) Running the module test suite

The test suites are invoked directly by the Odoo test runner. All
tests are decorated with `@tagged('post_install', '-at_install')` and
are tagged with the module name so they can be selected with
`--test-tags`.

### Full test run for both modules

```bash
cd $REPO_ROOT
source venv/bin/activate

./odoo-bin \
  --addons-path=addons,odoo/addons \
  --db_host=127.0.0.1 --db_port=5432 \
  --db_user=odoo --db_password=odoo \
  -d test_phase1 \
  -i account_financial_report_ce,account_bank_reconciliation_ce \
  --test-enable \
  --test-tags=/account_financial_report_ce,/account_bank_reconciliation_ce \
  --stop-after-init --no-http
```

The first invocation creates the `test_phase1` database and installs
both modules. Subsequent runs can reuse the database by switching from
`-i` to `-u`.

### Running one module at a time

```bash
# Financial reporting only
./odoo-bin \
  --addons-path=addons,odoo/addons \
  --db_host=127.0.0.1 --db_port=5432 \
  --db_user=odoo --db_password=odoo \
  -d test_phase1 \
  --test-enable \
  --test-tags=/account_financial_report_ce \
  -u account_financial_report_ce \
  --stop-after-init --no-http

# Bank reconciliation only
./odoo-bin \
  --addons-path=addons,odoo/addons \
  --db_host=127.0.0.1 --db_port=5432 \
  --db_user=odoo --db_password=odoo \
  -d test_phase1 \
  --test-enable \
  --test-tags=/account_bank_reconciliation_ce \
  -u account_bank_reconciliation_ce \
  --stop-after-init --no-http
```

### Running a single test class or method

Odoo's `--test-tags` accepts `<module>.<TestClass>.<method>` selectors:

```bash
./odoo-bin \
  --addons-path=addons,odoo/addons \
  --db_host=127.0.0.1 --db_port=5432 \
  --db_user=odoo --db_password=odoo \
  -d test_phase1 \
  --test-enable \
  --test-tags=/account_financial_report_ce:TestAgingBucketValsForAgedReports \
  -u account_financial_report_ce \
  --stop-after-init --no-http
```

### Expected baseline

As of this guide's publication the baseline is **351 tests, 0
failures, 0 errors**:

- `account_financial_report_ce`: 244+ tests (plus aging bucket tests)
- `account_bank_reconciliation_ce`: 199+ tests (plus date-window tests)

Any new failing test indicates a regression introduced by your code.

### Interpreting test output

Look for the summary lines near the end of the log:

```
INFO test_phase1 odoo.modules.module: odoo.addons.account_financial_report_ce.tests.test_<...> ran X tests in Ys
...
INFO test_phase1 odoo.tests.stats: Tests passed: NNN - Tests failed: 0 - Tests errored: 0
```

Exit code `0` means every selected test passed.

---

## (f) Manual testing steps for bank statement import and financial reports

This section walks you through exercising both features end-to-end in
a browser using the sample fixtures checked into
`test_data/bank_statements/` and `test_data/financial_reports/`.

### Prerequisites for manual testing

1. The Odoo HTTP server is running (section d) on
   `http://127.0.0.1:8069/`.
2. You are logged in as `admin` / `admin`.
3. The `test_data/` directory is populated with these files:
   - `test_data/bank_statements/sample.csv`
   - `test_data/bank_statements/sample.ofx`
   - `test_data/bank_statements/sample.qif`
   - `test_data/bank_statements/sample.xml` (CAMT.053)
   - `test_data/financial_reports/sample_journal_entries.csv`

### Manual test 1: Import a CSV bank statement

1. Navigate to **Accounting → Bank Reconciliation → Import Statements**
   (the menu item is added by `account_bank_reconciliation_ce`).
2. Click **New** to open the import wizard.
3. In **Journal**, pick an existing Bank journal (or create one via
   **Accounting → Configuration → Journals**).
4. Set **File Type** to `CSV`.
5. In **File**, upload `test_data/bank_statements/sample.csv`.
6. Click **Preview** and verify the wizard displays 8 transaction
   rows spanning `2024-02-01` through `2024-02-28`.
7. Click **Import**. The wizard closes and creates an
   `account.bank.statement` with 8 statement lines.
8. Open the new statement from **Accounting → Bank Statements** and
   verify the totals match the CSV (credits 6862.50, debits 1531.50,
   difference 5331.00).

### Manual test 2: Import an OFX bank statement

1. Repeat step 1–4 of manual test 1, but set **File Type** to `OFX`.
2. Upload `test_data/bank_statements/sample.ofx`.
3. The OFX parser should auto-detect the currency (`USD`) and bank
   account number (`1234567890`).
4. After import, the new statement carries 8 lines with the same
   totals as the CSV test.

### Manual test 3: Import a QIF bank statement

1. Repeat step 1–4 of manual test 1, but set **File Type** to `QIF`.
2. Upload `test_data/bank_statements/sample.qif`.
3. QIF does not carry currency metadata; confirm the wizard falls
   back to the journal's default currency.
4. 8 statement lines should be created with the amounts and
   references matching the CSV/OFX fixtures.

### Manual test 4: Import a CAMT.053 bank statement

1. Repeat step 1–4 of manual test 1, but set **File Type** to
   `CAMT.053`.
2. Upload `test_data/bank_statements/sample.xml`.
3. The XML parser should read the opening balance (`10000.00`) and
   closing balance (`15331.00`) from the `<Bal>` elements.
4. Confirm 8 entries are parsed with CRDT entries as positive amounts
   and DBIT entries as negative amounts.
5. Confirm the statement's balance equation is validated:
   `10000.00 + 6862.50 − 1531.50 = 15331.00`.

### Manual test 5: Run the reconciliation wizard

1. After importing any of the above statements, navigate to
   **Accounting → Bank Reconciliation → Reconciliation Wizard**.
2. In the wizard, confirm that **Candidate Date Window (Days)** is
   visible on the **Write-Off Settings** page with default value `90`.
3. Adjust the value to something like `30` and submit; verify only
   candidate move lines dated within 30 days of the statement line
   are considered.
4. Review the confidence badges on the matching suggestions —
   high-confidence matches (≥95%) are eligible for auto-reconciliation,
   medium (70–94%) require review, and low (50–69%) are flagged.
5. Click **Match** on a suggestion and confirm an
   `account.partial.reconcile` record is created.

### Manual test 6: Generate a financial report

1. Navigate to **Accounting → Reporting → Financial Reports**.
2. Click **New** to open the unified report wizard.
3. Select **Report Type** → `Balance Sheet`.
4. Pick a date range that covers the fixture's January–March 2024
   entries, e.g., `2024-01-01` → `2024-03-31`.
5. Click **Generate**. The balance sheet renders with Assets =
   Liabilities + Equity validation.
6. Click **Export PDF** to download a QWeb-rendered PDF. Verify the
   file opens cleanly in any PDF viewer.
7. Click **Export Excel** to download a `.xlsx` spreadsheet and open
   it with LibreOffice Calc or Microsoft Excel.

### Manual test 7: Generate an aging report and modify bucket thresholds

1. In the financial report wizard (from manual test 6), change
   **Report Type** to `Aged Receivable` (or `Aged Payable`).
2. Switch to the **Display Options** tab.
3. Confirm the **Aging Buckets (Days)** group is visible with four
   fields defaulting to `30`, `60`, `90`, `120`.
4. Change the bucket thresholds, e.g., `15`, `30`, `60`, `90`.
5. Click **Generate**. The aging report renders with the new buckets
   and each partner's open balance is classified accordingly.
6. Switch **Report Type** back to `Balance Sheet` — confirm the
   **Aging Buckets (Days)** group disappears from the Display Options
   tab (governed by `invisible="report_type not in
   ('aged_receivable', 'aged_payable')"`).

### Optional: Using the sample journal entries CSV

`test_data/financial_reports/sample_journal_entries.csv` contains 24
pre-balanced journal lines (total debit = total credit = 34,568.25)
across twelve journal entries spanning Sales, Purchases, Bank, and
Payroll journals. You can:

- Import them via **Accounting → Configuration → Import** (Odoo's
  built-in CSV importer, mapping the columns to `account.move` and
  `account.move.line` fields).
- Use them to manually seed your dev database with realistic data so
  the financial reports in manual test 6 and the aging report in
  manual test 7 produce meaningful output.

---

## Troubleshooting

| Symptom                                                             | Fix                                                                                                |
|---------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------|
| `psycopg2.OperationalError: FATAL: role "odoo" does not exist`      | Re-run the `createuser` command in section (c) or recreate the Docker container.                    |
| `ModuleNotFoundError: No module named 'ofxparse'`                   | You forgot to activate the venv; run `source venv/bin/activate` and retry.                          |
| `ERROR: could not connect to server: Connection refused`            | PostgreSQL is not running — `docker start odoo-postgres` or `sudo pg_ctlcluster 16 main start`.     |
| `EvalError: context_today is not defined` in the browser console    | You are running an old cache — hard-refresh with Ctrl+Shift+R and ensure `-u` was run after pulls.  |
| `AccessError` when uploading a bank statement as admin              | Ensure the post-install hook ran (re-install the module with `-i`); see Directive 4 documentation.  |
| Aging buckets not visible in the report wizard                      | Switch **Report Type** to `Aged Receivable` or `Aged Payable` — the group is invisible otherwise.   |

---

## Further reading

- Odoo 19 Developer Documentation — `https://www.odoo.com/documentation/18.0/`
- OCA Coding Standards — `https://github.com/OCA/odoo-community.org`
- Module feature specifications:
  `tickets/features/FEATURE-001-financial-reporting.md`
  `tickets/features/FEATURE-002-bank-reconciliation.md`
- Story-level acceptance criteria:
  `tickets/stories/financial-reporting/FR-*.md`
  `tickets/stories/bank-reconciliation/BR-*.md`
- User-facing workflow reference: `docs/USER_GUIDE.md`
