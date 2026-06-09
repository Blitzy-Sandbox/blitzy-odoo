.. Copyright 2024 Enterprise Accounting Team
.. License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

================
Deferred Revenue
================

:Status: Beta
:License: AGPL-3
:Odoo Version: 19.0
:Module Name: account_deferred_revenue

This module provides a complete deferred revenue and deferred expense
recognition system for Odoo 19.0 Community Edition, closing the feature
gap with the proprietary edition for ASC 606 / IFRS 15 compliant revenue
recognition. It delivers invoice-driven deferral schedule creation with
automatic revenue/expense account substitution, three allocation
strategies (straight-line, date-based, manual), cut-off entry generation
with single/batch/preview/reversal modes, and a recognition dashboard
with period-based drill-down. It is implemented as an independent Odoo
addon following OCA conventions, depends only on the core ``account``
module, requires no proprietary licensing, and supports multi-currency
and multi-company deployments. Analytic distribution, lock-date
enforcement, and fiscal-year boundary handling are preserved
end-to-end through the schedule-to-recognition pipeline.

**Table of contents**

.. contents::
   :local:

Features
========

The ``account_deferred_revenue`` module delivers four user stories
(DR-001 through DR-004) covering the full deferral lifecycle:

* **Deferral Schedule Definition (DR-001)** — invoice-driven schedule
  creation with automatic revenue/expense account substitution,
  manual schedule creation independent of invoices, source-document
  linkage to ``account.move`` / ``account.move.line``, and preserved
  analytic distribution on every generated recognition entry.
* **Automatic Period Allocation (DR-002)** — three allocation
  strategies: **Straight-line** (equal amounts per period),
  **Date-based** (prorated by calendar days), and **Manual**
  (user-defined per period); preview before activation; automatic
  recalculation on modification with past postings preserved and
  audit-chatter logging; multi-currency support with
  ``amount_currency`` retention; fiscal-year boundary awareness.
* **Cut-off Entry Generation (DR-003)** — ``TransientModel`` wizard
  with **Single**, **Batch**, **Preview**, and **Reversal** modes;
  optional reversing entries auto-posted via
  ``auto_post='at_date'``; ``account.move`` lock-date enforcement
  through the ``account.lock_exception`` registry.
* **Recognition Dashboard (DR-004)** — real-time summary cards
  (*Total Deferred Revenue*, *Total Deferred Expenses*, *Active
  Schedules*, *Next Period Recognition*); period-based view with
  status distribution (**Active** / **Completed** / **On Hold**);
  date-range filters; drill-down to schedule, source invoice, and
  generated journal entries.
* **Multi-Company, Security, and Standards Compliance** —
  record-level ``ir.rule`` isolation by ``company_id``; access
  rights for *Accountant* and *Accounting Manager* groups via
  ``security/ir.model.access.csv``; core model extensions use
  ``_inherit`` with additive computed/relational fields only; ASC
  606 and IFRS 15 *Revenue from Contracts with Customers* alignment.

Installation
============

This module follows the standard Odoo module installation procedure.
Ensure the core ``account`` module is installed (it is the only
declared dependency: ``'depends': ['account']``), place the
``account_deferred_revenue`` folder in a directory listed on your
Odoo ``addons_path``, then update the apps list and install through
the *Apps* menu, or install from the command line::

    odoo-bin -d <db_name> -i account_deferred_revenue --stop-after-init

No external Python packages are required beyond those already
shipped with a default Odoo 19.0 Community Edition installation.

Configuration
=============

The module works out of the box for schedules created from invoices.
Optional configuration tailors behaviour to company-specific
accounting policies:

* **Per-schedule deferral accounts** — the *Deferred Account*
  (balance-sheet liability for revenue, asset for expense) and the
  *Recognition Account* (P&L revenue or expense) are selected
  directly on each ``account.deferred.schedule`` form. The module
  does not store company-level defaults; account selection is
  filtered by account type at the form-field level so that only
  appropriate accounts can be chosen.
* **Recognition method default** — the system parameter
  ``account_deferred_revenue.default_recognition_method`` (visible
  under *Settings → Technical → Parameters → System Parameters*)
  controls the recognition method proposed on newly created
  schedules. Valid values are ``straight_line``, ``date_based``,
  and ``manual``.
* **Maximum recognition span warning** — the system parameter
  ``account_deferred_revenue.max_months_warning`` configures the
  threshold (default 60 months) at which a save-time warning is
  emitted for schedules whose recognition span exceeds the limit.
* **Fiscal configuration** — confirm the company fiscal year and
  any applicable lock dates under *Accounting → Configuration →
  Settings*. These settings drive fiscal-year boundary detection
  in the allocation engine and lock-date enforcement in the
  cut-off wizard.
* **Access rights** — users in the *Accounting / Billing* group
  have read/write/create access to schedules, recognition lines,
  and the cut-off wizard; users in *Accounting / Accounting
  Manager* additionally have full access including unlink and
  administrative operations such as bulk cancellation. Multi-
  company isolation is enforced through ``ir.rule`` records in
  ``security/deferred_security.xml``.

Usage
=====

Creating a Deferral Schedule from an Invoice (DR-001)
-----------------------------------------------------

Invoice-driven schedule creation is the primary workflow. From a
posted customer invoice, select the revenue line to be deferred and
trigger the *Create Deferral Schedule* action. A new
``account.deferred.schedule`` record is created linked to the source
invoice and invoice line; the original revenue account on the
invoice line is substituted with the configured deferred revenue
liability account (the total remains on the invoice but is held in
the liability account pending recognition); the schedule total
equals the invoice line amount (or sum of selected lines when
invoked at invoice level); the partner is inherited from the source
invoice and the ``analytic_distribution`` is preserved unchanged and
forwarded to every generated recognition entry. For deferred
expenses, the same workflow applies in reverse on vendor bills —
the original expense account is substituted with the configured
deferred expense asset account.

Manual schedule creation is supported independently of any invoice:
navigate to *Accounting → Deferred Revenue → Deferred Schedules*, use
the *New* action, and enter the partner, total amount, reference
document, deferred account, and recognition account directly.

Configuring Recognition Periods (DR-001)
----------------------------------------

Recognition parameters are configured on the deferral schedule form:

* **Start Date** and **End Date** (or number of periods) — the
  system computes the complementary value.
* **Recognition Method** — **Straight-line**, **Date-based**, or
  **Manual** (see *Automatic Period Allocation* below).
* **Deferred Account** — balance-sheet account holding the
  unrecognised amount (liability for revenue, asset for expense).
* **Recognition Account** — P&L account credited (revenue) or
  debited (expense) when each period is recognised.

Save-time validations: end date must be on or after start date;
start date must not fall within a locked accounting period;
recognition periods longer than sixty months emit a warning; and
fiscal-year settings are respected when validating period dates.

Automatic Period Allocation (DR-002)
------------------------------------

Once the recognition parameters are saved, the allocation schedule
is computed automatically and displayed as a preview before
activation. Supported methods:

* **Straight-line** — equal amounts per period, computed as
  ``total_amount / number_of_periods``. Example: a schedule of
  $12,000 over twelve months yields $1,000 recognised each month.
* **Date-based** — amounts prorated by the number of calendar days
  in each period, computed as
  ``total_amount × (days_in_period / total_days)``. The first and
  last periods are automatically prorated when the schedule starts
  or ends mid-month, and full intermediate periods receive amounts
  proportional to their calendar length.
* **Manual** — the user enters the amount for each period
  individually; validation enforces that the sum of all period
  amounts equals the schedule total.

Preview, activation, and modification semantics: no journal entries
are posted until the schedule is explicitly activated. When an
active schedule is modified, periods that have already been
recognised (posted) are preserved unchanged; future periods are
recalculated from the remaining balance; the modification is
logged to the schedule's audit chatter. Multi-currency schedules
store recognition amounts in the original transaction currency;
company-currency equivalents are computed at posting time using
the applicable exchange rate on each recognition date.

Generating Cut-off Entries (DR-003)
-----------------------------------

The cut-off wizard converts pending recognitions into posted
journal entries for period close. Open a schedule and click
*Generate Cut-off*, or open the wizard directly from *Accounting
→ Deferred Revenue → Cut-off Entries* for batch processing.

* **Single** mode — one schedule, one period; debits the deferred
  account and credits the recognition account (reversed for
  deferred expenses), dated on the period end date, and references
  the originating schedule on the line items.
* **Batch** mode — processes every schedule with recognition due
  for the selected period, producing one consolidated journal
  entry per journal with line items grouped by account. A
  processed-schedules summary is returned on completion.
* **Preview** mode — returns a non-persistent summary of entries
  with per-account debit/credit totals and per-journal impact; no
  posting occurs.
* **Reversal** option — reversing journal entries dated the first
  day of the next period, exactly offsetting the cut-off amounts
  and linked to the originating entries. The *Auto-post* flag
  maps to ``auto_post='at_date'``.

Lock-date enforcement: the wizard consults ``account.move`` lock
dates and the ``account.lock_exception`` registry before posting.
If the target date falls in a locked period and no active
exception covers the user, journal, or date, the wizard blocks
the operation with an error identifying the violated constraint
and advising on the next available posting date; no entries are
created when a lock violation is detected.

Reviewing the Recognition Dashboard (DR-004)
--------------------------------------------

The dashboard at *Accounting → Deferred Revenue → Recognition
Dashboard* surfaces the recognition status of every active
schedule for CFOs and finance directors.

* **Summary cards** — *Total Deferred Revenue*, *Total Deferred
  Expenses*, *Active Schedules*, and *Next Period Recognition*
  in the company currency, updated in real time as schedules
  are modified or recognitions are posted.
* **Period-based view** — use the period selector to view
  scheduled recognition amounts for any past, current, or future
  period; contributing schedules are listed with their
  per-schedule amount and percentage of the total.
* **Status distribution** — schedules grouped as **Active**,
  **Completed** (fully recognised), or **On Hold** (temporarily
  suspended).
* **Filters and drill-down** — apply date range, company, and
  status filters (session-persistent with a one-click *Clear
  Filters* action); clicking any schedule entry navigates to
  the schedule detail view, from which the source invoice and
  all generated recognition entries are reachable via smart
  buttons.

Known Issues / Roadmap
======================

This initial community release delivers DR-001 through DR-004. The
following items are out of scope and tracked for future enhancement:

* **Declining-balance / usage-based recognition** — only
  straight-line, date-based, and manual methods are supported.
* **Milestone-based performance-obligation recognition** —
  automated milestone triggers driven by external events (delivery
  confirmations, acceptance receipts) are not yet integrated;
  manual entry per milestone is the current workaround.
* **Contract-combination recognition** — ASC 606 contract
  combination is not automatically detected; combined contracts
  must be entered as a single schedule.
* **Predictive recognition forecasting** — no machine-learning
  based forecasting of recognition amounts or fulfilment risk.

Changelog
=========

19.0.1.0.0 (2024-12-01)
-----------------------

Initial release. Delivers the four DR stories that constitute
FEATURE-005 (Deferred Revenue) under EPIC-001 (Enterprise Accounting
Capabilities).

* **DR-001 Deferral Schedule Definition** — invoice-driven schedule
  creation with automatic revenue / expense account substitution,
  manual schedule creation independent of invoices, source-document
  linkage, and analytic-distribution preservation through every
  generated recognition entry.
* **DR-002 Automatic Period Allocation** — straight-line, date-based,
  and manual allocation strategies; preview before activation;
  recalculation on modification with past postings preserved and
  audit-chatter logging; multi-currency support; fiscal-year
  boundary awareness.
* **DR-003 Cut-off Entry Generation** — TransientModel wizard with
  Single, Batch, Preview, and Reversal modes; optional reversing
  entries auto-posted via ``auto_post='at_date'``;
  ``account.lock_exception`` registry awareness for lock-date
  enforcement.
* **DR-004 Recognition Dashboard** — real-time summary cards
  (Total Deferred Revenue, Total Deferred Expenses, Active
  Schedules, Next Period Recognition); period-based view with
  status distribution; date-range filters; drill-down to schedule,
  source invoice, and generated journal entries.
* AGPL-3.0 licensing; depends only on the core ``account`` module;
  no Odoo Enterprise dependencies (R-02); no cross-imports to other
  new Community Edition modules (R-01); additive ``_inherit``
  extension only on ``account.move`` and ``account.move.line``
  (R-05); ASC 606 / IFRS 15 alignment.

Bug Tracker
===========

Bugs and feature requests should be reported through the repository
issue tracker at https://github.com/odoo/odoo/issues. Please include
the Odoo server version, steps to reproduce, expected and actual
behaviour, and relevant log excerpts or tracebacks.

Credits
=======

Authors
-------

* Enterprise Accounting Team
* Odoo Community Association (OCA)

Contributors
------------

* OCA contributors — see module git history

Maintainers
-----------

This module is maintained by the OCA. OCA, or the Odoo Community
Association, is a nonprofit organization whose mission is to support
the collaborative development of Odoo features and promote its
widespread use.

License
=======

This module is licensed under the **AGPL-3.0 or later** (Affero
General Public License, version 3) — see the ``LICENSE`` file
distributed with Odoo for the full text, or visit
https://www.gnu.org/licenses/agpl-3.0.html. Any derivative works
distributed or made available over a network must be licensed under
the same terms and provide source-code access to their users.
