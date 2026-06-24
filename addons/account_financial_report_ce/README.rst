.. Copyright 2024 Enterprise Accounting Team
.. License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

=====================================
Financial Reports (Community Edition)
=====================================

.. |badge-license| replace:: License: AGPL-3
.. |badge-odoo| replace:: Odoo: 19.0 Community Edition
.. |badge-python| replace:: Python: 3.10 - 3.13
.. |badge-status| replace:: Development Status: Beta
.. |badge-maintainer| replace:: Maintainer: OCA

|badge-license| |badge-odoo| |badge-python| |badge-status| |badge-maintainer|

**Module:** ``account_financial_report_ce``

**Version:** 19.0.1.1.0

**License:** AGPL-3.0 or later (https://www.gnu.org/licenses/agpl)

**Author:** Enterprise Accounting Team, Odoo Community Association (OCA)

**Category:** Accounting/Reporting

This addon delivers enterprise-grade financial reporting for Odoo 19.0
Community Edition — Balance Sheet, Profit & Loss, Cash Flow Statement,
General Ledger, Trial Balance, and Aged Receivable/Payable reports — with
zero dependencies on Odoo Enterprise modules. It implements FEATURE-001
(Financial Reporting) of EPIC-001 "Enterprise Accounting Capabilities" and
delivers seven user stories (FR-001 through FR-007). The module depends only
on the core ``account`` and ``analytic`` modules, introduces zero Odoo
Enterprise dependencies, and explicitly excludes the Enterprise
``account_reports`` module; it is published under the GNU Affero General
Public License v3.0 or later and follows the Odoo Community Association (OCA)
coding standards
(Source: ``addons/account_financial_report_ce/__manifest__.py``).

.. contents::
   :local:

Description
===========

``account_financial_report_ce`` is an AGPL-3.0 licensed Odoo Community
Edition addon that closes the Community/Enterprise feature gap for statutory
and management financial reporting. It enables finance teams to produce
GAAP/IFRS-aligned financial statements directly inside Odoo using only the
core ``account`` and ``analytic`` modules; no Odoo Enterprise addon is
required, imported, or permitted by this module
(Source: ``addons/account_financial_report_ce/__manifest__.py``).

The suite serves CFOs, Finance Directors, Accountants, Auditors, and Business
Owners with PDF and Excel export and drill-down to source journal entries,
closing the Odoo Community-to-Enterprise reporting gap without Enterprise
licensing
(Source: ``tickets/features/FEATURE-001-financial-reporting.md``).

Architecture
------------

All reports share a common design, documented in the module manifest
(Source: ``addons/account_financial_report_ce/__manifest__.py``):

* Report data is sourced from ``account.move.line`` via ``read_group``
  aggregation for scalable, set-based computation rather than row-level
  iteration.
* Accounts are classified through the ``account.account`` ``account_type``
  field (21 standard account types) to drive statement sectioning.
* Comparative-period analysis renders a base period alongside a prior period.
* Drill-down navigation links each report figure back to its source journal
  entries.
* Multi-company isolation is enforced through ``ir.rule`` record rules scoped
  to ``company_id``.

Every report model inherits a shared abstract base,
``account.financial.report.abstract``
(Source: ``addons/account_financial_report_ce/models/financial_report.py:53``),
which provides the common period, company, and target-move handling together
with the shared PDF and Excel export entry points; a companion line abstract,
``account.financial.report.line.abstract``
(Source: ``addons/account_financial_report_ce/models/financial_report.py:825``),
standardises the per-line presentation fields.

Features and Reports
====================

The module delivers FEATURE-001 (Financial Reporting) as seven user stories.
Each report is implemented as an Odoo model that inherits the shared abstract
base ``account.financial.report.abstract``.

* **FR-001 Balance Sheet** — statement of financial position with
  Assets = Liabilities + Equity validation — model
  ``account.balance.sheet.report``
  (Source: ``addons/account_financial_report_ce/models/balance_sheet.py:62``);
  per-line detail via ``account.balance.sheet.report.line``.
* **FR-002 Profit & Loss** — income statement with Revenue, COGS, Operating
  Expenses, and Net Income sections — model ``account.profit.loss.report``
  (Source: ``addons/account_financial_report_ce/models/profit_loss.py:50``);
  per-line detail via ``account.profit.loss.report.line``.
* **FR-003 Cash Flow Statement** — indirect-method cash flow with operating,
  investing, and financing activity sections — model
  ``account.cash.flow.report``
  (Source: ``addons/account_financial_report_ce/models/cash_flow.py:55``);
  per-line detail via ``account.cash.flow.report.line``.
* **FR-004 General Ledger** — per-account transaction listing with running
  balances — model ``account.general.ledger.report``
  (Source: ``addons/account_financial_report_ce/models/general_ledger.py:33``);
  grouped through ``account.general.ledger.report.account`` and
  ``account.general.ledger.report.line``.
* **FR-005 Trial Balance** — debit/credit equality verification across all
  accounts — model ``account.trial.balance.report``
  (Source: ``addons/account_financial_report_ce/models/trial_balance.py:78``);
  per-line detail via ``account.trial.balance.report.line``.
* **FR-006 Aged Receivable/Payable** — partner aging across 30 / 60 / 90 /
  120+ day buckets — model ``account.aged.partner.balance.report``
  (Source: ``addons/account_financial_report_ce/models/aged_partner_balance.py:70``);
  grouped through ``account.aged.partner.balance.report.partner`` and
  ``account.aged.partner.balance.report.line``.
* **FR-007 Export & Drill-down** — every report renders to PDF through QWeb
  report templates (``report/report_templates.xml`` with per-report
  ``AbstractModel`` parsers such as
  ``report.account_financial_report_ce.report_balance_sheet``,
  Source: ``addons/account_financial_report_ce/report/report_balance_sheet.py:23``)
  and exports to Excel (``.xlsx``) via the ``openpyxl`` external Python
  dependency
  (Source: ``addons/account_financial_report_ce/models/financial_report.py:29``);
  report figures drill down to their source journal items.

Each run is driven by the interactive wizard
``account.financial.report.wizard``, an Odoo ``TransientModel``
(Source: ``addons/account_financial_report_ce/wizard/financial_report_wizard.py:30``).
The reports print through the A4, A4 Landscape, US Letter, and US Letter
Landscape paper formats and ``ir.actions.report`` actions in
``data/report_paperformat.xml`` and are styled by ``static/src/scss/report.scss``
(``web.assets_backend``) and ``static/src/scss/report_print.scss``
(``web.report_assets_common``)
(Source: ``addons/account_financial_report_ce/data/report_paperformat.xml``).

Installation
============

Prerequisites
-------------

* Odoo 19.0 Community Edition.
* Python 3.10 or newer (3.13 is the explicitly supported runtime target)
  (Source: ``addons/account_financial_report_ce/__manifest__.py``).
* PostgreSQL 13 or newer.
* The Odoo core addons ``account`` and ``analytic``, which ship with the base
  distribution
  (Source: ``addons/account_financial_report_ce/__manifest__.py``).
* The ``openpyxl`` Python package, declared as an external dependency and
  required for the Excel (``.xlsx``) export in FR-007
  (Source: ``addons/account_financial_report_ce/__manifest__.py``).

Steps
-----

1. Place the ``account_financial_report_ce`` folder on your Odoo addons path.
2. Install the external Python package ``openpyxl`` (``pip install openpyxl``)
   so that the FR-007 Excel export is available.
3. Update the Odoo application list: **Apps -> Update Apps List**.
4. Search for "Financial Reports for Community Edition" in the Apps list and
   click **Install**.

Or install from the command line::

    odoo-bin -d <database_name> -i account_financial_report_ce --stop-after-init

A clean install registers the report models, the reporting wizard, the
security groups and access rules, the QWeb report templates, and the paper
formats. No field defined by Odoo core or by any other module is redefined.

Configuration
=============

After installation, a user with the Accounting Manager role should review the
following configuration points.

1. Security Groups
------------------

Access rights are granted through ``security/ir.model.access.csv`` and the
record rules declared in ``security/account_financial_report_security.xml``
(Source: ``addons/account_financial_report_ce/security/ir.model.access.csv``).
The module ships two dedicated groups: **Financial Reports User**
(``group_financial_report_user``), which implies
``account.group_account_readonly``, and **Financial Reports Manager**
(``group_financial_report_manager``); both build on the standard accounting
groups ``account.group_account_user`` and ``account.group_account_manager``
(Source: ``addons/account_financial_report_ce/security/account_financial_report_security.xml``).

2. Multi-company Isolation
--------------------------

Each report model and the reporting wizard is scoped by an ``ir.rule`` record
rule on ``company_id`` so that users see only the companies they are allowed
to access
(Source: ``addons/account_financial_report_ce/security/account_financial_report_security.xml``).

3. Menus
--------

The reports are published under **Accounting -> Reporting** through the root
menu ``menu_financial_reports_root`` ("Financial Reports"), whose parent is
``account.menu_finance_reports``; a "Financial Statements" submenu groups the
Balance Sheet, Profit and Loss, and Cash Flow Statement entries, with further
submenus for the Ledger and Aged reports
(Source: ``addons/account_financial_report_ce/views/menuitem.xml``).

4. Paper Formats
----------------

Four paper formats — A4, A4 Landscape, US Letter, and US Letter Landscape —
are provided and bound to the report actions; statement reports default to A4
while the wider Ledger, Trial Balance, and Aged reports default to landscape
(Source: ``addons/account_financial_report_ce/data/report_paperformat.xml``).

Usage
=====

Open **Accounting -> Reporting -> Financial Reports** and choose the desired
report. The ``account.financial.report.wizard`` prompts for the company, the
date range or period, an optional comparison period, and the target moves
(posted only, or all entries); running the wizard renders the report on
screen, from where figures drill down to source journal items and export to
PDF or Excel
(Source: ``addons/account_financial_report_ce/wizard/financial_report_wizard.py:30``).

FR-001: Balance Sheet
---------------------

Produces a statement of financial position that validates
Assets = Liabilities + Equity, classifying accounts through the
``account.account`` ``account_type`` field and supporting comparative periods
and zero-balance hiding — model ``account.balance.sheet.report``
(Source: ``addons/account_financial_report_ce/models/balance_sheet.py:62``).

FR-002: Profit & Loss
---------------------

Produces an income statement broken into Revenue, Cost of Goods Sold,
Operating Expenses, and Net Income, with optional hierarchical grouping and
comparative periods — model ``account.profit.loss.report``
(Source: ``addons/account_financial_report_ce/models/profit_loss.py:50``).

FR-003: Cash Flow Statement
---------------------------

Produces an indirect-method cash flow statement with operating, investing,
and financing activity sections — model ``account.cash.flow.report``
(Source: ``addons/account_financial_report_ce/models/cash_flow.py:55``).

FR-004: General Ledger
----------------------

Lists every posted transaction per account with running balances and an
optional opening (initial) balance — model ``account.general.ledger.report``
(Source: ``addons/account_financial_report_ce/models/general_ledger.py:33``).

FR-005: Trial Balance
---------------------

Lists each account's debit and credit totals and verifies overall
debit/credit equality — model ``account.trial.balance.report``
(Source: ``addons/account_financial_report_ce/models/trial_balance.py:78``).

FR-006: Aged Receivable/Payable
-------------------------------

Ages partner balances across 30 / 60 / 90 / 120+ day buckets for receivables
or payables — model ``account.aged.partner.balance.report``
(Source: ``addons/account_financial_report_ce/models/aged_partner_balance.py:70``).

FR-007: Report Export and Drill-down
------------------------------------

Every report renders to PDF through its QWeb template and exports to Excel
(``.xlsx``) through the ``openpyxl`` dependency; report figures drill down to
the underlying journal items
(Source: ``addons/account_financial_report_ce/models/financial_report.py:29``).

Technical Notes
===============

* **Dependencies:** ``account`` and ``analytic`` only; zero Odoo Enterprise
  modules; the Enterprise ``account_reports`` module is explicitly excluded
  (Source: ``addons/account_financial_report_ce/__manifest__.py``).
* **External Python:** ``openpyxl`` for Excel export
  (Source: ``addons/account_financial_report_ce/__manifest__.py``).
* **Assets:** ``static/src/scss/report.scss`` on ``web.assets_backend`` and
  ``static/src/scss/report_print.scss`` on ``web.report_assets_common``
  (Source: ``addons/account_financial_report_ce/__manifest__.py``).
* **Data sourcing:** ``account.move.line`` aggregated through ``read_group``;
  account classification through the ``account.account`` ``account_type`` field
  (Source: ``addons/account_financial_report_ce/__manifest__.py``).
* **Platform:** Odoo 19.0 API; Python 3.10-3.13; OCA coding standards;
  AGPL-3.0 license
  (Source: ``addons/account_financial_report_ce/__manifest__.py``).

Known Issues / Roadmap
======================

* This module is delivered as part of EPIC-001 "Enterprise Accounting
  Capabilities" and is intended for contribution to the Odoo Community
  Association (OCA) in a future release cycle.
* Cross-module integrations with the other accounting addons in this
  repository are intentionally avoided to preserve module independence; each
  addon stands on its own.
* Refer to ``tickets/features/FEATURE-001-financial-reporting.md`` and the
  FR-001 through FR-007 story files under
  ``tickets/stories/financial-reporting/`` for the canonical feature and story
  specifications.

Changelog
=========

19.0.1.1.0
----------

Initial release. Delivers the seven FR stories that constitute FEATURE-001
(Financial Reporting) under EPIC-001 (Enterprise Accounting Capabilities).

* **FR-001 Balance Sheet** — statement of financial position with
  Assets = Liabilities + Equity validation (model
  ``account.balance.sheet.report``).
* **FR-002 Profit & Loss** — Revenue / COGS / Operating Expenses / Net Income
  income statement (model ``account.profit.loss.report``).
* **FR-003 Cash Flow Statement** — indirect-method statement with operating,
  investing, and financing sections (model ``account.cash.flow.report``).
* **FR-004 General Ledger** — per-account transaction listing with running
  balances (model ``account.general.ledger.report``).
* **FR-005 Trial Balance** — debit/credit equality verification (model
  ``account.trial.balance.report``).
* **FR-006 Aged Receivable/Payable** — 30 / 60 / 90 / 120+ day aging buckets
  (model ``account.aged.partner.balance.report``).
* **FR-007 Report Export and Drill-down** — PDF via QWeb plus Excel (``.xlsx``)
  via ``openpyxl``, with drill-down to source journal entries.
* AGPL-3.0 licensing; depends only on the core ``account`` and ``analytic``
  modules; zero Odoo Enterprise dependencies; the Enterprise ``account_reports``
  module is explicitly excluded.

Bug Tracker
===========

Bugs are tracked in the issue tracker of the repository hosting this module.
In case of trouble, please check existing issues before submitting a new one.
When submitting a new issue, include:

* The module version (``19.0.1.1.0``).
* The Odoo version (19.0 Community Edition) and the Python version in use.
* A minimal reproduction case, including relevant data setup steps, the action
  that triggers the issue, and the observed versus expected result.
* Any stack traces or error messages from the Odoo server log.

Do not report bugs in third-party contributions directly to this module's
tracker; escalate them through the respective contributor's channels.

Credits
=======

Authors
-------

* Enterprise Accounting Team
* Odoo Community Association (OCA)

Contributors
------------

* Enterprise Accounting Team
* OCA contributors — see module git history

Funding
-------

Development of this module was made possible by contributors aligned with the
Odoo Community Association mission of collaborative Odoo development.

License
-------

This module is distributed under the **GNU Affero General Public License
v3.0 or later** (AGPL-3.0-or-later). See the ``LICENSE`` file at the
repository root for the full license text, or visit
https://www.gnu.org/licenses/agpl for an online copy
(Source: ``addons/account_financial_report_ce/__manifest__.py``).

The AGPL-3.0 license ensures that modifications and derivative works remain
available to the community under the same terms, consistent with OCA policy.

Maintainers
===========

This module is maintained by the Odoo Community Association (OCA).

OCA — the Odoo Community Association — is a nonprofit organisation that
supports the collaborative development of Odoo and promotes its widespread
use. To contribute, follow the OCA guidelines at https://odoo-community.org.

Current maintainer for this module:

* `OCA <https://odoo-community.org>`_

To get involved, please read the OCA contribution guidelines and submit pull
requests through the standard OCA review workflow.
