================
Asset Management
================

.. |badge1| image:: https://img.shields.io/badge/licence-AGPL--3-blue.svg
    :target: https://www.gnu.org/licenses/agpl
    :alt: License: AGPL-3

.. |badge2| image:: https://img.shields.io/badge/status-beta-yellow.svg
    :target: https://odoo-community.org/page/development-status
    :alt: Development Status: Beta

.. |badge3| image:: https://img.shields.io/badge/odoo-19.0-a24689.svg
    :target: https://www.odoo.com/documentation/19.0/
    :alt: Odoo 19.0

.. |badge4| image:: https://img.shields.io/badge/python-3.10%20%7C%203.13-blue.svg
    :target: https://www.python.org
    :alt: Python 3.10 / 3.13

|badge1| |badge2| |badge3| |badge4|

Fixed-asset lifecycle management for Odoo 19.0 Community Edition — AGPL-3 licensed.


Overview
========

This module delivers a complete fixed-asset management solution for Odoo 19.0
Community Edition, closing the Community/Enterprise gap for Accountants and
Bookkeepers who need to track, depreciate, modify, and dispose of fixed assets
without introducing any Odoo Enterprise dependency. It is an independent
AGPL-3 addon that integrates additively with the existing core ``account``
module through the standard Odoo inheritance mechanism.

The module delivers six user stories — **AM-001 Asset Registration**,
**AM-002 Depreciation Configuration**, **AM-003 Depreciation Board**,
**AM-004 Automatic Depreciation Entries**, **AM-005 Asset Modification
(Revaluation / Impairment)**, and **AM-006 Asset Disposal (Sale / Scrap /
Write-off)** — providing end-to-end coverage of the asset lifecycle, from
acquisition through period-by-period depreciation to final disposition with
gain or loss recognition.

Calculations and workflows are aligned with the relevant accounting standards
(US GAAP ASC 360, IFRS IAS 16 Property, Plant and Equipment, and IFRS IAS 36
Impairment of Assets) so that Community Edition users can produce accurate,
compliant asset accounting records and audit trails.


Features
========

The module provides the following capabilities out of the box:

* **Asset registration with vendor and invoice linkage (AM-001).** Capture
  acquisition details — name, acquisition date, acquisition cost, vendor,
  source vendor bill, asset category, useful life, and asset / depreciation /
  accumulated-depreciation account assignments — with auto-generated unique
  asset references produced by a dedicated ``ir.sequence`` record. Assets
  follow a draft → open → close state machine with chatter and activity
  tracking.

* **Multiple depreciation methods (AM-002).** Configure any of the following
  methods per asset (or as a default on the asset category):

  * **Straight-line**, with useful life expressed in years or months.
  * **Declining balance**, with a configurable declining factor and an
    optional switch to straight-line when straight-line would yield a higher
    expense in a given period.
  * **Units of production**, based on actual usage against total expected
    units.

  Salvage value, depreciation start date, and proration of the first period
  for mid-period acquisitions are all supported.

* **Depreciation board (AM-003).** View the complete depreciation schedule
  for any asset — period index, depreciation date, depreciation amount,
  cumulative depreciation, and net book value — in tree, kanban, and graph
  layouts. Filters, sort controls, and CSV / XLSX export are provided. The
  board is designed to render the full schedule in under two seconds for
  assets with up to 480 periods.

* **Automatic depreciation entries via scheduled action (AM-004).** A
  scheduled ``ir.cron`` record, registered as XML data and reachable from
  **Settings → Technical → Automation → Scheduled Actions**, posts
  depreciation journal entries according to each asset's schedule. The cron
  is idempotent on re-runs, supports batched processing, supports
  draft-versus-auto-post modes, prorates mid-period starts, and is
  fault-tolerant on a per-asset basis so that a failure on one asset does
  not block the remaining batch.

* **Asset revaluation and impairment (AM-005).** A dedicated wizard lets you
  record value increases under the IAS 16 revaluation model, impairment
  losses per IAS 36 / ASC 360, impairment reversals, useful-life
  adjustments, and salvage-value changes. The wizard automatically generates
  the corresponding adjustment journal entries and recalculates the
  remaining depreciation schedule. Every modification is written to the
  asset's immutable audit trail via the standard Odoo chatter.

* **Asset disposal by sale, scrap, or write-off (AM-006).** A disposal
  wizard calculates the gain or loss on disposal against the current net
  book value, posts catch-up depreciation through the disposal date,
  supports partial disposals, and transitions the asset to the close state
  after posting the disposal journal entry. Sale proceeds, scrap value, and
  full write-off are each handled with the appropriate debit / credit
  treatment.

* **Multi-company isolation.** Every new model is scoped by ``company_id``
  through ``ir.rule`` record rules, so databases running multiple companies
  keep asset portfolios strictly segregated.

* **AGPL-3 licensed with zero Odoo Enterprise dependencies.** The module
  depends solely on the core ``account`` module. It is safe to deploy on any
  Odoo 19.0 Community Edition installation.


Installation
============

1. Copy or clone the ``account_asset_management`` folder into your Odoo
   ``addons`` path.
2. Update the Odoo apps list (**Apps → Update Apps List**, developer mode
   required).
3. Search for **Asset Management** in the Apps menu and click **Install**.
4. Alternatively, install the module from the command line::

       ./odoo-bin -d <database> -i account_asset_management --stop-after-init

The module declares ``account`` as its only dependency, which is resolved
automatically by the Odoo module loader.


Configuration
=============

After installation, perform the following one-time setup steps:

1. **Create asset categories.** Navigate to **Accounting → Configuration →
   Asset Categories** and create at least one category per type of asset you
   will register (for example, *Buildings*, *IT Equipment*, *Vehicles*).
   Each category stores the default depreciation method, useful life,
   salvage value, and the asset / depreciation-expense / accumulated-
   depreciation accounts that will be proposed when assets of that category
   are created.

2. **Review the depreciation scheduled action.** Navigate to **Settings →
   Technical → Automation → Scheduled Actions** and locate the
   *Asset Management: Post Depreciation Entries* job. The cron is enabled by
   default and runs daily. Administrators can adjust the interval, next
   execution date, or temporarily disable the job from this screen.

3. **Assign access to users.** Two security groups are provided and can be
   assigned from **Settings → Users & Companies → Users**:

   * **Asset User** — read, write, and create assets and depreciation
     schedules; run the modification and disposal wizards.
   * **Asset Manager** — full access, including unlink, plus permission to
     run the scheduled depreciation job manually.

4. **(Optional) Review multi-company record rules.** Navigate to **Settings
   → Technical → Security → Record Rules** to verify that the supplied
   rules scope each asset record to its ``company_id``. No additional
   configuration is needed for single-company databases.


Usage
=====

Typical end-to-end workflow, from acquisition to disposal:

1. **Navigate** to **Accounting → Assets**.
2. **Select or create a category** under
   **Accounting → Configuration → Asset Categories** with default
   depreciation method, useful life, salvage value, and account
   assignments.
3. **Create an asset** from **Accounting → Assets → Assets** (or directly
   from a posted vendor bill via the *Create Asset* smart action when the
   vendor bill line references an asset-type account). Fill in the
   acquisition date, acquisition cost, category, and any vendor reference.
4. **Configure depreciation** on the asset form — method, useful life (or
   declining factor / total expected units for non-straight-line methods),
   salvage value, and depreciation start date — then **Confirm** the asset
   to transition it from draft to open and post the acquisition journal
   entry.
5. **Review the depreciation board** from the *Depreciation Board* tab or
   the **Accounting → Assets → Depreciation Board** menu to visualise the
   projected schedule across the asset's useful life.
6. **Let the cron run** daily (or run it manually from **Settings →
   Technical → Automation → Scheduled Actions**) to post each depreciation
   journal entry as its scheduled date arrives. Entries are created with
   the usual balanced debit / credit lines and are reconcilable through the
   standard Odoo accounting flow.
7. **Adjust the asset if needed** using the **Modify Asset** action to
   launch the modification wizard: choose revaluation, impairment,
   impairment reversal, useful-life change, or salvage-value change; the
   wizard posts the adjustment entry and rebuilds the remaining schedule.
8. **Dispose of the asset** at end of life using the **Dispose Asset**
   action to launch the disposal wizard: choose sale (with proceeds),
   scrapping, or write-off; the wizard posts catch-up depreciation, records
   the gain or loss, and transitions the asset to the close state.

All asset transactions generate standard journal entries in the general
ledger and appear in the Balance Sheet and Profit & Loss reports without
any additional reporting configuration.


Known Issues / Roadmap
======================

None at time of release. Please report issues via the OCA project tracker
(see the *Bug Tracker* section below).


Bug Tracker
===========

Bugs are tracked on `GitHub Issues
<https://github.com/OCA/account-financial-tools/issues>`_. In case of
trouble, please check there to see if your issue has already been reported.
If you spot a new one, please help smashing it by providing a detailed and
welcomed `feedback
<https://github.com/OCA/account-financial-tools/issues/new?body=module:%20account_asset_management%0Aversion:%2019.0.1.0.0%0A%0A**Steps%20to%20reproduce**%0A-%20...%0A%0A**Current%20behavior**%0A%0A**Expected%20behavior**>`_.

Do not contact contributors directly about support or help with technical
issues.


Credits
=======

Authors
-------

* Enterprise Accounting Team
* Odoo Community Association (OCA)

Contributors
------------

Contributions are welcome. Please submit pull requests through the OCA
project tracker. Contributors will be acknowledged in this section as
patches are merged.

Maintainers
-----------

This module is maintained by the Odoo Community Association (OCA).

.. image:: https://odoo-community.org/logo.png
   :alt: Odoo Community Association
   :target: https://odoo-community.org

OCA, or the Odoo Community Association, is a nonprofit organization whose
mission is to support the collaborative development of Odoo features and
promote its widespread use.

To contribute to this module, please visit https://odoo-community.org.


License Notice
==============

This module is licensed under the AGPL-3.0 or later (GNU Affero General
Public License v3 or later). A copy of the license is distributed with the
source code and is also available online at
`https://www.gnu.org/licenses/agpl <https://www.gnu.org/licenses/agpl>`_.

You are free to use, study, modify, and distribute this module under the
terms of the AGPL-3.0. Any derivative work that is conveyed to third
parties — including over a network — must also be made available under the
same license.
