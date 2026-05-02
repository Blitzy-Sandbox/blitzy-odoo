.. Copyright 2024 Enterprise Accounting Team
.. License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

=====================================
Budget Management (Community Edition)
=====================================

.. |badge-license| replace:: License: AGPL-3
.. |badge-odoo| replace:: Odoo: 19.0 Community Edition
.. |badge-python| replace:: Python: 3.10 - 3.13
.. |badge-status| replace:: Development Status: Beta
.. |badge-maintainer| replace:: Maintainer: OCA

|badge-license| |badge-odoo| |badge-python| |badge-status| |badge-maintainer|

**Module:** ``account_budget_management``

**Version:** 19.0.1.0.0

**License:** AGPL-3.0 or later (https://www.gnu.org/licenses/agpl)

**Author:** Enterprise Accounting Team, Odoo Community Association (OCA)

**Category:** Accounting / Accounting

This addon delivers enterprise-grade budget management capabilities for
Odoo 19.0 Community Edition - budget definition, period allocation,
actual-vs-budget reporting, variance analysis, and threshold alerts - with
zero dependencies on Odoo Enterprise modules. The module is published under
the GNU Affero General Public License v3.0 or later and follows the Odoo
Community Association (OCA) coding standards.

.. contents::
   :local:


Description
===========

``account_budget_management`` is an AGPL-3.0 licensed Odoo Community Edition
addon that closes the Community/Enterprise feature gap for financial planning
and budget control. It enables finance teams to plan, monitor, and analyse
budgets directly inside Odoo using only the core ``account`` and ``analytic``
modules; no Odoo Enterprise addon is required, imported, or permitted by this
module.

The module implements FEATURE-003 of EPIC-001 "Enterprise Accounting
Capabilities" and delivers five user stories (BM-001 through BM-005). Together
these stories provide the capabilities that CFOs, Finance Directors,
Controllers, and Accountants need for proactive budget management:

* Define budgets by general ledger account and analytic dimension
  (departments, projects, cost centers).
* Allocate planned amounts across monthly, quarterly, or annual periods.
* Compare actual posted transactions against planned budgets side by side.
* Analyse variances with favourable / unfavourable classification,
  trend tracking, and drill-down to source journal entries.
* Monitor budget consumption with configurable threshold-based alerts that
  fire automatically via a scheduled action.

Architecturally the module parallels the pattern already established by the
``account_financial_report_ce`` and ``account_bank_reconciliation_ce`` addons
shipped with this repository: OCA-conformant packaging, ``_inherit``-only
extension of core models, XML-driven data definitions, ``TransientModel``
wizards for interactive input, and per-module security declarations
(``ir.model.access.csv`` plus ``ir.rule`` multi-company isolation).


Installation
============

Prerequisites
-------------

* Odoo 19.0 Community Edition
* Python 3.10 or newer (3.13 is the explicitly supported runtime target)
* PostgreSQL 13 or newer
* The Odoo core addons ``account`` and ``analytic``, which ship with the
  base distribution

No additional Python packages are required beyond those already pinned by
the Odoo 19.0 ``requirements.txt`` (``lxml``, ``Babel``, ``python-dateutil``,
``MarkupSafe``, and standard Odoo runtime libraries).

Steps
-----

1. Ensure the required Odoo core modules are available on the addons path.
2. Place the ``account_budget_management`` folder on your Odoo addons path.
3. Update the Odoo application list: **Apps -> Update Apps List**.
4. Search for "Budget Management" in the Apps list and click **Install**.

Or install from the command line::

    odoo-bin -d <database_name> -i account_budget_management --stop-after-init

A clean install exits with return code zero and creates the new database
tables (``budget_budget``, ``budget_budget_line``, ``budget_budget_period``,
``budget_alert``) plus any additive computed or relational fields on
``account.analytic.account``. No field defined by Odoo core or by any other
module is redefined.


Configuration
=============

After installation, a user with the Accounting Manager role should perform
the following configuration steps.

1. Security Groups
------------------

Access rights are granted automatically through ``security/ir.model.access.csv``
and the record rules declared in ``security/budget_security.xml``.
Multi-company isolation is enforced by ``ir.rule`` records scoped to
``company_id``. No additional group assignment is required for typical
deployments; budget users inherit visibility from the standard accounting
groups (Accounting User and Accounting Manager).

2. Default Sequences
--------------------

A dedicated ``ir.sequence`` record for budget references is created on
install from ``data/budget_data.xml``. The reference prefix and padding can
be adjusted under **Settings -> Technical -> Sequences & Identifiers ->
Sequences**.

3. Alert Scheduled Action
-------------------------

The budget threshold evaluation cron is registered from
``data/budget_alert_cron.xml`` as an ``ir.cron`` record. After install it is
reachable from **Settings -> Technical -> Automation -> Scheduled Actions**
under "Budget Alert Threshold Evaluation". Its interval and activation
state may be adjusted to suit the deployment. The cron may also be invoked
manually from this screen using **Run Manually**.

4. Threshold Defaults
---------------------

Budget alerts default to threshold percentages at 75%, 90%, 100%, and 110%
with severity classifications **Warning**, **Alert**, **Critical**, and
**Over-budget** respectively. These thresholds can be overridden per budget
line, and recipients can be configured per threshold.

5. Analytic Dimensions
----------------------

If analytic plans and analytic accounts are not yet configured in the
instance, create them first under **Accounting -> Configuration -> Analytic
Accounting**. The budget line ``analytic_distribution`` field reuses the core
``analytic.mixin`` and therefore respects the same validation rules as other
analytic-enabled documents.


Usage
=====

The module adds a top-level *Budget Management* section to the Accounting
menu. Typical usage flows from budget definition through period allocation,
comparison reporting, variance analysis, and alert monitoring.

BM-001: Budget Definition
-------------------------

**Accounting -> Budget Management -> Budgets** lets a Controller, Finance
Director, or CFO:

* Create a budget record (model ``budget.budget``) with a unique reference,
  responsible user, fiscal period (``date_from`` / ``date_to``), and company.
* Add budget lines (``budget.budget.line``) that link a planned monetary
  amount to a general ledger account (``account.account``) and an optional
  analytic distribution (``analytic.mixin``) spanning one or more
  ``account.analytic.account`` records governed by an
  ``account.analytic.plan``.
* Progress the budget through its state machine:
  **draft -> confirmed -> closed**, with **cancelled** as an alternate
  terminal state reachable from **draft** or **confirmed**. Validation
  rules ensure that every confirmed budget has at least one line and that
  planned amounts are non-negative.
* Duplicate an existing budget to accelerate annual planning cycles.

BM-002: Budget Period Allocation
--------------------------------

Each budget line can be decomposed into period allocations
(``budget.budget.period``). For any budget line a Controller can:

* Select an allocation cadence - **monthly**, **quarterly**, or **annual**.
* Choose a distribution strategy - **equal**, **manual** (per-period entry),
  **percentage**, or **copy from previous budget**.
* Review a running total that flags any discrepancy between the sum of
  period amounts and the line-level annual total.
* Adjust individual period amounts after confirmation; every change is
  timestamped and attributed to the editing user for audit purposes.

BM-003: Actual vs Budget Reporting
----------------------------------

**Accounting -> Budget Management -> Actual vs Budget** delivers
side-by-side comparisons of planned amounts against posted actuals.
Actuals are computed via a single ``read_group`` SQL aggregation against
``account.move.line``, matching the precedent established by
``account_financial_report_ce`` for scalable reporting. Users can:

* Filter by budget, period range, analytic dimension, or GL account.
* View multi-period YTD roll-ups alongside the most recent period.
* Drill down from any report cell to the underlying posted journal items.
* Export the report via the standard Odoo list / pivot view export menu
  (Actions -> Export All for spreadsheet-friendly output, or the print
  menu on the resulting view for PDF). No dedicated PDF / XLSX template
  is bundled with this module; the ``action_print_pdf`` and
  ``action_export_xlsx`` methods on the variance wizard intentionally
  raise a ``UserError`` redirecting the user to the standard export
  flow.

BM-004: Variance Analysis
-------------------------

**Accounting -> Budget Management -> Variance Analysis Wizard** opens a
``TransientModel`` wizard that computes:

* **Absolute variance** - actual minus planned, expressed in the company
  currency.
* **Percentage variance** - absolute variance divided by planned, rendered
  as a percentage.
* **Favourable / unfavourable classification** - derived from the GL account
  type: for revenue accounts, actuals above budget are favourable; for
  expense accounts, actuals below budget are favourable.
* **Trend analysis** across consecutive periods to surface emerging patterns.
* **Free-form explanation notes** attached to each variance line for audit
  trail purposes.

**Performance target:** the fiscal-year variance report renders in under
three seconds for up to one thousand budget lines. This target is achieved
through a single ``read_group`` aggregation rather than row-level iteration
over journal items.

BM-005: Budget Alerts
---------------------

**Accounting -> Budget Management -> Alerts** gives Controllers a
dashboard view of budget consumption events. Behaviour and configuration:

* Each budget line may declare one or more threshold percentages (for
  example 75%, 90%, 100%, 110%), each mapped to a severity level:
  Warning, Alert, Critical, or Over-budget.
* The ``ir.cron`` scheduled action declared in
  ``data/budget_alert_cron.xml`` evaluates budget consumption against
  thresholds on a configurable interval.
* When a threshold is crossed, a ``budget.alert`` record is created with
  the consumption percentage, alert severity, and the list of recipient
  users. An email is dispatched through the standard Odoo mail pipeline
  to those recipients.
* Historical alert records are immutable and form an auditable trail of
  threshold events, supporting both internal review and external audit.
* A kanban dashboard summarises active alerts by severity for at-a-glance
  budget-health monitoring.


Known Issues / Roadmap
======================

* This module is delivered as part of the Phase 2 tranche of EPIC-001
  "Enterprise Accounting Capabilities". It is intended for contribution to
  the Odoo Community Association (OCA) in a future release cycle.
* Additional variance classification strategies (for example zero-based
  budgeting and rolling forecast) are out of scope for this release and
  may be proposed through standard OCA pull-request channels.
* Multi-currency budgets follow the company currency of the budget record;
  cross-currency consolidation across subsidiaries is out of scope for this
  release.
* Cross-module integrations with other Phase 2 modules are intentionally
  avoided to preserve module independence; each addon in this repository
  stands on its own.
* Refer to ``tickets/features/FEATURE-003-budget-management.md`` and the
  BM-001 through BM-005 story files under
  ``tickets/stories/budget-management/`` for the canonical feature and
  story specifications.


Changelog
=========

19.0.1.0.0 (2024-12-01)
-----------------------

Initial release. Delivers the five BM stories that constitute FEATURE-003
(Budget Management) under EPIC-001 (Enterprise Accounting Capabilities).

* **BM-001 Budget Definition** — header / line model pair with analytic
  distribution support, draft -> confirmed -> closed lifecycle plus
  cancelled terminal state, per-company sequence numbering, audit trail
  through ``mail.thread``, and copy / duplicate workflow.
* **BM-002 Budget Period Allocation** — monthly / quarterly / annual
  decomposition of budget lines with equal, manual, percentage, and
  copy-from-previous distribution strategies.
* **BM-003 Actual vs Budget Reporting** — pivot / list / graph views on
  posted journal entries with ``read_group`` SQL aggregation, multi-period
  YTD roll-ups, and drill-down to source moves.
* **BM-004 Variance Analysis** — TransientModel wizard with absolute and
  percentage variance, favourable / unfavourable classification driven by
  account type, and trend analysis. Renders in under three seconds for
  fiscal-year reports of up to 1,000 budget lines.
* **BM-005 Budget Alerts** — threshold-based alert evaluation (default
  75 / 90 / 100 / 110 percent) via the declarative ``ir.cron`` record
  *Budget Alert Threshold Evaluation* in ``data/budget_alert_cron.xml``;
  immutable alert history with kanban dashboard.
* AGPL-3.0 licensing; depends only on the core ``account`` and
  ``analytic`` modules; no Odoo Enterprise dependencies (R-02); no
  cross-imports between the four new Community Edition modules (R-01);
  additive ``_inherit`` extension only (R-05); ``ir.cron`` declared via
  XML data record (R-06); BM-004 and BM-005 fields strictly partitioned
  (R-08).


Bug Tracker
===========

Bugs are tracked in the issue tracker of the repository hosting this module.
In case of trouble, please check existing issues before submitting a new
one. When submitting a new issue, include:

* The module version (``19.0.1.0.0``).
* The Odoo version (19.0 Community Edition) and the Python version in use.
* A minimal reproduction case, including relevant data setup steps, the
  action that triggers the issue, and the observed versus expected result.
* Any stack traces or error messages from the Odoo server log.

Do not report bugs in third-party contributions directly to this module's
tracker; escalate them through the respective contributor's channels.


Credits
=======

Authors
-------

* Odoo Community Association (OCA)

Contributors
------------

* Enterprise Accounting Team
* OCA contributors — see module git history

Funding
-------

Development of this module was made possible by contributors aligned with
the Odoo Community Association mission of collaborative Odoo development.

License
-------

This module is distributed under the **GNU Affero General Public License
v3.0 or later** (AGPL-3.0-or-later). See the ``LICENSE`` file at the
repository root for the full license text, or visit
https://www.gnu.org/licenses/agpl for an online copy.

The AGPL-3.0 license is chosen to ensure that any modifications or
derivative works remain available to the community under the same terms,
consistent with OCA policy and with the licensing posture of peer modules
``account_financial_report_ce`` and ``account_bank_reconciliation_ce``
already present in this repository.


Maintainers
===========

This module is maintained by the Odoo Community Association (OCA).

OCA - the Odoo Community Association - is a nonprofit organisation whose
mission is to support the collaborative development of Odoo features and
to promote its widespread use. Participation in OCA is open to any
individual or organisation interested in the community development of
Odoo modules. To contribute, follow the OCA guidelines at
https://odoo-community.org.

Current maintainer for this module:

* `OCA <https://odoo-community.org>`_

To get involved, please read the OCA contribution guidelines and submit
pull requests through the standard OCA review workflow.
