.. Copyright 2024 Enterprise Accounting Team
.. License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

==================
Payment Follow-ups
==================

:Status: Beta
:License: AGPL-3
:Odoo Version: 19.0
:Module Name: account_payment_followup

This module provides a complete payment follow-up management system for
Odoo 19.0 Community Edition, closing the feature gap with the proprietary
edition for automated accounts-receivable collection workflows. It delivers
a four-level escalation workflow (First Reminder → Second Reminder → Warning
→ Final Notice), automated email generation through scheduled actions,
action history tracking with an immutable audit trail, aged-receivables
reporting, and aging-bucket calculation with multi-currency and
multi-company support.

The module is implemented as an independent Odoo addon following OCA
conventions. It depends only on the core ``account`` and ``mail`` modules
and requires no proprietary licensing.

**Table of contents**

.. contents::
   :local:

Features
========

The ``account_payment_followup`` module provides the following capabilities:

* **Configurable Follow-up Levels (PF-001)**

  * Multi-level escalation workflow with customizable delay periods
    (default: 7 / 14 / 21 / 30 days after due date).
  * Four seeded default levels: First Reminder, Second Reminder, Warning,
    Final Notice.
  * Per-level configuration of email templates, action types (manual
    or automatic), minimum amount thresholds, company scope, and active
    state.

* **Automated Email Generation (PF-002)**

  * Scheduled daily follow-up dispatch via a declarative ``ir.cron``
    record visible in *Settings → Technical → Automation → Scheduled
    Actions*.
  * Batched processing of up to 500 partners per cron run within the
    default cron timeout.
  * QWeb-based email templates with dynamic field substitution for
    partner, invoice, and amount data.
  * Optional PDF invoice attachments per follow-up level.
  * Consolidated communications: one email per partner including all
    overdue invoices.

* **Action History Tracking (PF-004)**

  * Complete, immutable audit trail of every follow-up action.
  * Supported action types include email sent, phone call, letter,
    meeting, payment promise, status change, note, and SMS.
  * Promised-payment-date tracking linked to partner follow-up scheduling.
  * Attachment support for call notes, signed agreements, and
    correspondence.
  * Full integration with Odoo chatter (``mail.thread`` and
    ``mail.activity.mixin``).

* **Follow-up Report Generation (PF-003)**

  * Aged receivables report with filters by follow-up level, partner,
    aging bucket, and date range.
  * Sortable columns with default ordering by total overdue amount
    descending.
  * PDF and Excel (XLSX) export support.
  * Drill-down from summary to invoice-level detail.
  * Effectiveness metrics: recovery rate, average days to payment,
    response rate by level.

* **Overdue Calculation and Aging Buckets (PF-005)**

  * Automatic computation of days overdue per invoice
    (``max(0, today - due_date)``).
  * Aging-bucket classification: Current, 1–30 days, 31–60 days,
    61–90 days, and 90+ days.
  * Highest-applicable-level assignment per partner based on the most
    overdue invoice.
  * Exclusion of disputed invoices from level assignment while retaining
    them in aging reports.
  * Residual-amount-aware calculation that respects partial payments.

* **Multi-Company and Multi-Currency Support**

  * Record-level isolation through ``ir.rule`` declarations on all new
    models.
  * Currency-aware monetary fields that respect company currency and
    invoice currency.

* **Integration With Existing Odoo Features**

  * Uses the standard ``mail.template`` engine — no custom mail stack.
  * Reuses existing ``res.partner`` credit and payment-term data.
  * All extensions of core models use Odoo's ``_inherit`` mechanism with
    additive computed and relational fields only.

Installation
============

This module follows the standard Odoo module installation procedure.

1. Ensure the ``account`` and ``mail`` Odoo modules are installed. These
   are the only module dependencies declared in this module's manifest::

       'depends': ['account', 'mail']

2. Place the ``account_payment_followup`` folder in a directory listed on
   your Odoo ``addons_path``.

3. Update the apps list and install the module through the Apps menu, or
   install it from the command line::

       odoo-bin -d <db_name> -i account_payment_followup --stop-after-init

4. Confirm the module is installed by navigating to *Apps* and verifying
   that **Payment Follow-ups** is listed as installed.

No external Python packages are required beyond those already shipped
with a default Odoo 19.0 Community Edition installation.

Configuration
=============

After installation, a minimal configuration workflow ensures the module
is ready for use.

Follow-up Levels
----------------

* Navigate to *Accounting → Follow-ups → Configuration → Follow-up Levels*.
* Review the four default levels seeded at install time:

  ====================== ========== =============== ==========================================
  Level Name             Sequence   Delay (days)    Description
  ====================== ========== =============== ==========================================
  First Reminder         10         7               Initial friendly reminder
  Second Reminder        20         14              Follow-up reminder
  Warning                30         21              Formal warning notice
  Final Notice           40         30              Final notice before escalation
  ====================== ========== =============== ==========================================

* Customize each level's delay days, associated email template, action
  type (Manual or Automatic), and minimum amount threshold as needed.

Scheduled Action
----------------

* Navigate to *Settings → Technical → Automation → Scheduled Actions* and
  locate **Payment Follow-up: Send Reminders**.
* Verify that the action is active and its execution cadence matches your
  operational needs (default: daily).
* Use *Run Manually* on the scheduled-action form to trigger a dispatch
  outside the normal cadence.

Email Templates
---------------

* Email templates associated with each follow-up level are seeded as
  ``mail.template`` records and may be customized through
  *Settings → Technical → Email → Templates*.
* Template bodies support QWeb dynamic placeholders for partner name,
  overdue amount, invoice list, and company signature.

Usage
=====

Configuring Follow-up Levels (PF-001)
-------------------------------------

Accountants and Credit Controllers configure follow-up levels through
*Accounting → Follow-ups → Configuration → Follow-up Levels*.

* Each level requires: name, sequence, delay in days (non-negative), and
  description.
* Optional per-level fields: email template, action type (manual or
  automatic), minimum amount threshold, company scope, and active flag.
* Levels must have unique sequence numbers per company.
* At least one level must exist before the follow-up automation can run.

Automated Email Generation (PF-002)
-----------------------------------

The daily follow-up dispatch is executed by the scheduled action
**Payment Follow-up: Send Reminders**.

* For each partner with overdue invoices, the system determines the
  applicable follow-up level based on the most overdue invoice.
* When the level's action type is Automatic and an email template is
  configured, a consolidated email is rendered with the partner's
  overdue-invoice details and queued through the standard outgoing mail
  server.
* When the level's action type is Manual, the system flags the partner
  for accountant review rather than sending automatically.
* Every dispatched email produces a corresponding history record
  (see PF-004).
* The cron body processes partners in chunks of up to 500 per run to
  respect default cron timeout boundaries.

To preview a send run without mailing, use a test company or disable the
scheduled action and invoke follow-up processing from the partner form.

Tracking Follow-up Actions (PF-004)
-----------------------------------

The action history provides a permanent audit trail for all follow-up
activity.

* View follow-up history for a partner via the smart button on the
  partner form or through *Accounting → Follow-ups → Follow-up
  Operations → Action History*.
* Record manual actions (phone calls, meetings, notes, letters, payment
  promises, SMS) via the Record Activity button on the partner or
  follow-up line.
* Every history record captures timestamp, action type, responsible user,
  follow-up level, related invoices, and a communication summary.
* Records are immutable once created; corrections must be filed as
  additional history entries.
* Attachments (call notes, signed agreements, correspondence) may be
  stored on any history record.
* Promised payment dates recorded in manual activities are available for
  follow-up scheduling and partner-level reporting.

Generating Reports (PF-003)
---------------------------

The follow-up report surfaces aged receivables with follow-up context.

* Navigate to *Accounting → Follow-ups → Follow-up Operations →
  Follow-up Report* and open the wizard.
* Filters available: follow-up level, partner, aging bucket, date range,
  minimum amount, and company.
* The wizard produces a sortable list of partners with: current
  follow-up level, total overdue amount, oldest overdue date, days since
  oldest overdue, last action taken, and number of overdue invoices.
* Default sort order is total overdue amount descending.
* Export to PDF (QWeb template) or Excel (XLSX) for distribution to
  management or auditors.
* Drill down from each summary row to the underlying invoices.

Overdue Calculation (PF-005)
----------------------------

The module computes overdue state and aging buckets automatically for
every partner with at least one open customer invoice.

* Days overdue is calculated as ``max(0, today − due_date)`` for each
  unpaid invoice.
* Each invoice is classified into an aging bucket: **Current** (not yet
  due), **1–30 days**, **31–60 days**, **61–90 days**, or **90+ days**.
* A partner's follow-up level is the highest applicable level given the
  partner's most overdue invoice.
* Invoices flagged as disputed are excluded from follow-up level
  assignment but still appear in aging reports with a dispute indicator.
* Calculations use residual (unpaid) amounts, correctly accounting for
  partial payments.
* Partners with no overdue invoices are not assigned to any level and do
  not appear in the follow-up report.

Performance & SLA
=================

PF-002 cron timeout budget
--------------------------

The PF-002 scheduled action processes up to ``batch_size`` partners per
run and is sized to fit within Odoo 19's default cron real-time limit
(120 seconds, controlled by the ``limit-time-real-cron`` config option,
which falls back to ``limit-time-real`` when unset). Per AAP section
0.1.2, the design target is **≤ 500 partners per cron run within the
default cron timeout**.

This budget is comfortably met when invoice PDF attachments are
disabled (the seed default for all four follow-up levels):

* **All levels with attach_invoices=False** — ~10 seconds for 500
  partners (well under 120 s; observed 9.86 s in QA Checkpoint 3).

When invoice PDF attachments are enabled per level, the budget depends
on which ``wkhtmltopdf`` build is installed:

* **Patched-QT wkhtmltopdf** (Odoo's official ``odoofin``/``wkhtmltox``
  binaries, version 0.12.5 with the Odoo patches): a single
  ``wkhtmltopdf`` subprocess can render every batched invoice PDF in
  one invocation. The
  ``account.followup.level._batch_render_invoice_attachments`` helper
  engages this fast path and 500 partners with one PDF each fit
  inside the 120 s default.
* **Unpatched wkhtmltopdf** (Linux distribution package, version
  0.12.6 in particular): each invoice PDF requires its own
  ``wkhtmltopdf`` invocation (~1.0 to 1.1 seconds each). 500 partners
  with PDF attachments take roughly 9 minutes which is 4 to 5 times
  the default cron budget. The QA Checkpoint 3 report observed
  556.78 s for this configuration on Ubuntu's stock
  ``wkhtmltopdf 0.12.6`` package.

Defaults and operator opt-in
----------------------------

Because the unpatched-QT wkhtmltopdf binary is the most common Linux
deployment scenario, **all four default follow-up levels ship with
``attach_invoices=False``**. Operators who wish to attach invoice PDFs
to follow-up emails can enable the flag per level under
``Accounting → Follow-ups → Configuration → Follow-up Levels`` after
sizing their cron timeout accordingly. The seed-data ``noupdate="1"``
wrapper preserves operator customisations across module upgrades.

Recommended operator playbook for enabling ``attach_invoices=True``:

1. Confirm whether the wkhtmltopdf binary on the Odoo server is
   patched-QT (Odoo's official build) or unpatched (distribution
   build). Inspect with ``wkhtmltopdf --version`` and
   ``wkhtmltopdf --readme | head`` (Odoo's patches appear in the
   output).
2. **If patched-QT**: enable ``attach_invoices=True`` on the desired
   levels. The batched render path engages and SLA holds.
3. **If unpatched**: estimate the worst-case per-cron load (number of
   partners at the level multiplied by 1.1 s) and choose one of:

   * Raise ``limit-time-real-cron`` in the Odoo configuration to a
     value greater than the worst-case load (e.g. 600 seconds for
     500 partners).
   * Reduce the cron's ``batch_size`` (use the cron action's
     ``code`` field — for example
     ``model.process_followup_emails(batch_size=100)``) so each run
     fits within the existing timeout. The remaining partners are
     processed on subsequent cron runs.
   * Keep ``attach_invoices=False`` and rely on the email body's
     QWeb t-foreach iteration which already lists every overdue
     invoice's number, issue date, due date and amount.

Forward compatibility
---------------------

The ``_batch_render_invoice_attachments`` helper retained from the
PF-002 SLA fix collapses N per-partner ``wkhtmltopdf`` subprocess
calls into a single batch invocation when the binary supports it.
This means that as soon as a deployment upgrades to a patched-QT
build, enabling ``attach_invoices=True`` on Levels 3-4 will
immediately fit within the 120 s default cron timeout — no further
code changes are required.

Other module SLAs
-----------------

* **AM-003 depreciation board**: full schedule render under 2
  seconds for assets with up to 480 periods (QA: 5 ms cold ORM read,
  400× under).
* **BM-004 variance report**: fiscal year render under 3 seconds
  for up to 1,000 budget lines (QA: 2,721 ms cold compute).
* **DR-004 recognition dashboard**: render under 2 seconds for up
  to 1,000 active schedules (QA: 218 ms cold).
* **PF-005 overdue calculation**: under 5 seconds for up to 10,000
  receivable lines (QA: 67.7 ms total).
* **PF-003 report generation**: PDF + XLSX export under 10 seconds
  for 500 partners (QA: 1,341 ms total — note that PF-003 uses
  one ``wkhtmltopdf`` invocation for the entire aggregated report,
  unlike PF-002's per-partner attachment rendering).

Known Issues / Roadmap
======================

This module represents the initial community release and delivers the
five stories defined in FEATURE-006 (PF-001 through PF-005). The
following items are considered out of scope for this release and are
tracked for future enhancement:

* **SMS reminders** — SMS dispatch is not currently integrated. Only
  the history action type ``sms`` is recognized (for manual logging).
  Automated SMS dispatch is planned for a future release.
* **Predictive collection scoring** — No machine-learning based
  prediction of payment likelihood is included.
* **Mobile-first follow-up workflow** — The module uses standard Odoo
  web-client views; no dedicated mobile app is shipped.
* **Live payment-gateway integrations** — Outbound payment links are
  limited to those already provided by the core ``account`` module's
  payment-provider support.

Changelog
=========

19.0.1.0.0 (2024-12-01)
-----------------------

Initial release. Delivers the five PF stories that constitute
FEATURE-006 (Payment Follow-ups) under EPIC-001 (Enterprise Accounting
Capabilities).

* **PF-001 Follow-up Level Configuration** — multi-level escalation
  workflow with customisable delay periods, four seeded default
  levels (First Reminder / Second Reminder / Warning / Final Notice),
  per-level email-template references, action-type selection, minimum
  amount thresholds, company scope, and active flag.
* **PF-002 Automated Email Generation** — declarative ``ir.cron``
  scheduled action *Payment Follow-up: Send Reminders* in
  ``data/followup_cron.xml``; batched processing of up to 500
  partners per run within the default cron timeout; QWeb-based
  email rendering through the standard ``mail.template`` engine
  with optional batched PDF invoice attachments via
  ``_batch_render_invoice_attachments``.
* **PF-003 Follow-up Report Generation** — aged-receivables wizard
  with filters by level, partner, aging bucket, date range, minimum
  amount, and company; sortable result list; PDF and XLSX export;
  drill-down to invoice-level detail.
* **PF-004 Action History Tracking** — immutable audit trail of every
  follow-up action; eight action types (email sent, phone call,
  letter, meeting, payment promise, status change, note, SMS);
  promised-payment-date tracking; attachment support; chatter and
  activity integration via ``mail.thread`` / ``mail.activity.mixin``.
* **PF-005 Overdue Calculation and Aging Buckets** — automatic days-
  overdue computation per invoice; aging-bucket classification
  (Current / 1–30 / 31–60 / 61–90 / 90+); highest-applicable-level
  assignment per partner; disputed-invoice exclusion; residual-amount
  awareness for partial payments.
* AGPL-3.0 licensing; depends only on the core ``account`` and
  ``mail`` modules; no Odoo Enterprise dependencies (R-02); no
  cross-imports between the four new Community Edition modules
  (R-01); additive ``_inherit`` extension only on ``account.move``,
  ``account.move.line``, and ``res.partner`` (R-05); ``ir.cron``
  declared via XML data record (R-06).

Bug Tracker
===========

Bugs and feature requests should be reported through the repository
issue tracker:

https://github.com/odoo/odoo/issues

Please include in your report:

* Odoo server version and database details.
* Steps to reproduce the issue.
* Expected and actual behaviour.
* Relevant log excerpts or tracebacks.
* Whether the issue is reproducible on a freshly installed module.

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

This module is maintained by the OCA.

.. image:: https://odoo-community.org/logo.png
   :alt: Odoo Community Association
   :target: https://odoo-community.org

OCA, or the Odoo Community Association, is a nonprofit organization
whose mission is to support the collaborative development of Odoo
features and promote its widespread use.

License
=======

This module is licensed under the **AGPL-3.0 or later** (Affero General
Public License, version 3) — see the ``LICENSE`` file distributed with
Odoo for the full license text, or visit
https://www.gnu.org/licenses/agpl-3.0.html.

You are free to use, modify, and redistribute this module under the
terms of the AGPL-3.0 or later. Any derivative works distributed or
made available over a network must be licensed under the same terms
and provide source-code access to their users.
