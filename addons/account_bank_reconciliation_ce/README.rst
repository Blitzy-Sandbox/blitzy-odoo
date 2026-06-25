.. Copyright 2024 Enterprise Accounting Team
.. License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

=======================================
Bank Reconciliation (Community Edition)
=======================================

.. |badge-license| replace:: License: AGPL-3
.. |badge-odoo| replace:: Odoo: 19.0 Community Edition
.. |badge-python| replace:: Python: 3.10 - 3.13
.. |badge-status| replace:: Development Status: Beta
.. |badge-maintainer| replace:: Maintainer: OCA

|badge-license| |badge-odoo| |badge-python| |badge-status| |badge-maintainer|

**Module:** ``account_bank_reconciliation_ce``

**Version:** 19.0.1.0.0

**License:** AGPL-3.0 or later (https://www.gnu.org/licenses/agpl)

**Author:** Enterprise Accounting Team, Odoo Community Association (OCA)

**Category:** Accounting/Reconciliation

This addon delivers smart bank reconciliation for Odoo 19.0 Community Edition -
multi-format bank statement import, an algorithmic matching engine with
configurable confidence scoring, configurable reconciliation rules, manual
reconciliation workflows, and partial reconciliation with write-off handling -
with zero dependencies on Odoo Enterprise modules. It is published under the
GNU Affero General Public License v3.0 or later and follows the Odoo Community
Association (OCA) coding standards.

.. contents::
   :local:


Description
===========

``account_bank_reconciliation_ce`` is an AGPL-3.0 licensed Odoo Community
Edition addon that closes the Community/Enterprise feature gap for bank
reconciliation. It enables finance teams to import bank statements, match them
against open journal items, and reconcile them directly inside Odoo using only
the core ``account`` module; no Odoo Enterprise addon is required, imported, or
permitted by this module
(Source: ``addons/account_bank_reconciliation_ce/__manifest__.py:depends``).

The module implements FEATURE-002 (Bank Reconciliation) of EPIC-001
"Enterprise Accounting Capabilities" and delivers five user stories
(BR-001 through BR-005). It is strictly Community Edition: it depends solely on
the core ``account`` module, carries zero Odoo Enterprise dependencies, and
**explicitly excludes** the Enterprise ``account_accountant`` module along with
the other Enterprise accounting modules
(Source: ``addons/account_bank_reconciliation_ce/__manifest__.py:depends``).
Together the five stories provide the capabilities that Accountants and
Bookkeepers need for efficient, accurate bank reconciliation:

* Import bank statements in CSV, OFX, QIF, and CAMT.053 (ISO 20022 XML)
  formats with duplicate detection and automatic format detection.
* Score statement lines against open journal items with a configurable,
  weighted confidence algorithm.
* Define regex- and amount-based reconciliation rules that additively extend
  the core ``account.reconcile.model``.
* Review and confirm proposed matches through a guided manual reconciliation
  workflow.
* Handle partial reconciliation with write-off entries and multi-currency
  difference handling.

Architecturally the module parallels the pattern established by the peer
``account_financial_report_ce`` and ``account_budget_management`` addons
shipped with this repository: OCA-conformant packaging, ``_inherit``-only
extension of core models, XML-driven data definitions, ``TransientModel``
wizards for interactive input, and per-module security declarations
(``ir.model.access.csv`` plus ``ir.rule`` multi-company isolation).


Features
========

The module provides the following capabilities out of the box, one per user
story of FEATURE-002:

* **BR-001 Statement Import.** Multi-format bank statement import supporting
  CSV (with configurable column mapping), OFX (parsed via the ``ofxparse``
  Python package), QIF (text parsing), and CAMT.053 (ISO 20022 XML parsed via
  ``lxml.etree``). Provides SHA256-hash duplicate detection, automatic file
  format detection from content signatures and filename extensions, and
  company-scoped batch line creation. Implemented by the
  ``account.bank.statement.import`` model. Sample statements ship at
  ``tests/test_files/`` (``sample.csv``, ``sample.ofx``, ``sample.qif``,
  ``sample_camt053.xml``) and at the repository-level
  ``test_data/bank_statements/`` directory. Performance target: import in
  under 10 seconds for 500 lines
  (Source: ``addons/account_bank_reconciliation_ce/models/bank_statement_import.py:account.bank.statement.import``).

* **BR-002 Algorithmic Matching.** A matching engine that scores each bank
  statement line against candidate journal items using default scoring weights
  for amount, reference, partner, and date proximity, then classifies each
  candidate into High, Medium, Low, or None confidence bands and supports
  one-to-many and many-to-one resolution. Implemented by the
  ``account.reconciliation.matching`` model. Performance target: under
  5 seconds for 1,000 lines, with a matching-accuracy target of at least 95%
  (Source: ``addons/account_bank_reconciliation_ce/models/reconciliation_matching_engine.py:account.reconciliation.matching``).

* **BR-003 Manual Reconciliation.** A guided manual reconciliation workflow
  with backend UI views (``views/bank_reconciliation_views.xml``) and a
  dedicated wizard that loads unreconciled lines, displays match suggestions
  with confidence badges, and supports match, unmatch, partial match, and
  batch confirmation. Implemented by the ``account.reconciliation.wizard``
  ``TransientModel``
  (Source: ``addons/account_bank_reconciliation_ce/wizard/reconciliation_wizard.py:account.reconciliation.wizard``).

* **BR-004 Reconciliation Rules.** Regex- and amount-based reconciliation
  rules with priority ordering, payment-reference matching (contains,
  not-contains, regex, exact), partner-name matching, date-range proximity,
  amount-tolerance percentage, and per-rule confidence gating. The model
  **additively extends** the core ``account.reconcile.model`` via ``_inherit``
  (no new ``_name``, no core modification) and is seeded by
  ``data/reconciliation_data.xml``. Performance target: under 1 second per
  rule evaluation
  (Source: ``addons/account_bank_reconciliation_ce/models/reconciliation_rule.py:account.reconcile.model``).

* **BR-005 Partial Reconciliation.** Partial reconciliation with write-off
  entries, tolerance-based automatic write-off, and multi-currency difference
  handling. The reconciliation-tracking fields extend
  ``account.bank.statement.line`` via ``_inherit``, and the partial workflow
  is driven by the helper ``account.reconciliation.partial.helper``
  ``TransientModel``
  (Source: ``addons/account_bank_reconciliation_ce/models/partial_reconcile_ext.py:account.reconciliation.partial.helper``).

In addition to the models above, the module ships two interactive wizards -
``account.bank.statement.import.wizard`` and ``account.reconciliation.wizard``
(``TransientModel`` records, each with a ``*_views.xml`` definition under
``wizard/``); a Reconciliation Status report
(``report/reconciliation_report.py`` and ``report/reconciliation_report.xml``);
and a backend stylesheet (``static/src/scss/reconciliation.scss``). The test
suite under ``tests/`` targets at least 80% coverage
(Source: ``addons/account_bank_reconciliation_ce/__manifest__.py:summary``).


Installation
============

Prerequisites
-------------

* Odoo 19.0 Community Edition.
* Python 3.10 or newer (3.13 is the explicitly supported runtime target).
* PostgreSQL 13 or newer.
* The Odoo core ``account`` module, which ships with the base distribution
  (Source: ``addons/account_bank_reconciliation_ce/__manifest__.py:depends``).
* The external Python package ``ofxparse``, required for OFX statement import
  (BR-001). Install it with::

    pip install ofxparse

  The dependency is declared in the manifest under ``external_dependencies``
  (Source: ``addons/account_bank_reconciliation_ce/__manifest__.py:external_dependencies``).

Steps
-----

1. Ensure the core ``account`` module is available on your Odoo addons path.
2. Place the ``account_bank_reconciliation_ce`` folder on your Odoo addons
   path.
3. Update the Odoo application list: **Apps -> Update Apps List**.
4. Search for "Bank Reconciliation for Community Edition" in the Apps list and
   click **Install**.

Or install from the command line::

    odoo-bin -d <database_name> -i account_bank_reconciliation_ce --stop-after-init

Post-install Hook
-----------------

On install (and on every subsequent upgrade) the module runs a
``post_init_hook`` that adds every Accounting / Manager, Accounting / User,
and Bank Reconciliation group member to the base Internal User group
(``base.group_user``). This is required because ``ir.attachment`` write
access - needed to upload bank-statement files on the reconciliation wizards -
is gated on membership of ``base.group_user``; without the hook, uploading a
statement file on a pre-existing database with non-internal accounting users
would raise an ``AccessError``. The hook is idempotent and safe to re-run
(Source: ``addons/account_bank_reconciliation_ce/hooks.py:post_init_hook``;
``addons/account_bank_reconciliation_ce/__manifest__.py:post_init_hook``).


Configuration
=============

After installation, a user with the Accounting Manager role should review the
following configuration.

1. Security Groups
------------------

The module declares two dedicated groups - **Bank Reconciliation User**
(``group_bank_reconciliation_user``) and **Bank Reconciliation Manager**
(``group_bank_reconciliation_manager``) - in
``security/bank_reconciliation_security.xml``, together with multi-company
``ir.rule`` record rules that scope reconciliation data to the active
company. Model-level access rights are granted through
``security/ir.model.access.csv``
(Source: ``addons/account_bank_reconciliation_ce/security/bank_reconciliation_security.xml``;
``addons/account_bank_reconciliation_ce/security/ir.model.access.csv``).

2. Menus
--------

The module adds a top-level **Bank Reconciliation** menu to the Accounting
application with entries for statement import, reconciliation, status, and
rules, declared in ``views/menuitem.xml``
(Source: ``addons/account_bank_reconciliation_ce/views/menuitem.xml``).

3. Reconciliation Rules and Matching Defaults
---------------------------------------------

The matching engine scores each candidate using a fixed set of built-in default
weights (the ``DEFAULT_WEIGHTS`` class attribute on the
``account.reconciliation.matching`` model): amount 0.35, reference 0.25, partner
0.25, and date 0.15 (summing to 1.0). These are the weights applied at runtime by
the engine's ``_compute_match_score`` method
(Source: ``addons/account_bank_reconciliation_ce/models/reconciliation_matching_engine.py:account.reconciliation.matching``).

The ``data/reconciliation_data.xml`` file seeds default ``ir.config_parameter``
records (confidence thresholds and per-criterion weight parameters) together with
sample reconciliation rules (loaded with ``noupdate="1"`` so user customisations
are preserved across upgrades). The engine applies its built-in defaults — the
``DEFAULT_WEIGHTS`` above and the confidence-band constants — rather than reading
these seeded parameters, so the documented 0.35 / 0.25 / 0.25 / 0.15 weighting is
authoritative for matching behaviour
(Source: ``addons/account_bank_reconciliation_ce/data/reconciliation_data.xml``).

4. Multi-company Isolation
--------------------------

Every model query is company-scoped, and ``ir.rule`` record rules enforce
multi-company isolation so that users only see reconciliation data for their
allowed companies
(Source: ``addons/account_bank_reconciliation_ce/models/reconciliation_matching_engine.py:account.reconciliation.matching``).


Usage
=====

The typical reconciliation flow runs from statement import through algorithmic
matching, manual review, and partial reconciliation.

BR-001: Import a Statement
--------------------------

Navigate to **Accounting -> Reconciliation -> Import Statement** to open the
import wizard (``account.bank.statement.import.wizard``). Upload a statement
file in CSV, OFX, QIF, or CAMT.053 format; the wizard auto-detects the format
(or you may select it explicitly), maps CSV columns where required, previews
the parsed rows, and performs a batch import that is rolled back on failure.
Heavy parsing and validation are delegated to the
``account.bank.statement.import`` model. Ready-made sample files are available
under ``tests/test_files/`` and ``test_data/bank_statements/``
(Source: ``addons/account_bank_reconciliation_ce/wizard/bank_statement_import_wizard.py:account.bank.statement.import.wizard``).

BR-002: Run the Matching Engine
-------------------------------

Once statement lines are imported, the matching engine scores each line
against open journal items and proposes candidate matches ranked by confidence
score. Each candidate is classified into a High, Medium, Low, or None
confidence band; high-confidence candidates are eligible for
auto-reconciliation, while lower-confidence candidates are surfaced for manual
review
(Source: ``addons/account_bank_reconciliation_ce/models/reconciliation_matching_engine.py:account.reconciliation.matching``).

BR-003: Review and Confirm
--------------------------

Open **Accounting -> Reconciliation -> Reconcile** to launch the
reconciliation wizard (``account.reconciliation.wizard``). The wizard lists
unreconciled lines for the selected journal and date range, shows the engine's
suggestions with confidence badges, and lets you match, unmatch, partially
match, or batch-confirm reconciliations
(Source: ``addons/account_bank_reconciliation_ce/wizard/reconciliation_wizard.py:account.reconciliation.wizard``).

BR-004: Apply Reconciliation Rules
----------------------------------

Configure reconciliation rules - regex or amount based, with priority ordering
and a per-rule confidence threshold - to automate recurring matches. Rules
extend the core ``account.reconcile.model`` and are seeded with sensible
defaults from ``data/reconciliation_data.xml``
(Source: ``addons/account_bank_reconciliation_ce/models/reconciliation_rule.py:account.reconcile.model``).

BR-005: Handle Partials and Write-offs
---------------------------------------

When a statement line only partially matches a journal item, the partial
helper (``account.reconciliation.partial.helper``) creates the partial
reconciliation and, where a residual remains within tolerance, posts a
write-off entry, handling any multi-currency difference
(Source: ``addons/account_bank_reconciliation_ce/models/partial_reconcile_ext.py:account.reconciliation.partial.helper``).


Technical Notes
===============

* **Dependencies.** Depends only on the core ``account`` module; no Odoo
  Enterprise module is required or permitted
  (Source: ``addons/account_bank_reconciliation_ce/__manifest__.py:depends``).
* **External Python packages.** ``ofxparse`` is required for OFX import and is
  declared under ``external_dependencies``; CAMT.053 parsing uses ``lxml``,
  which ships with Odoo
  (Source: ``addons/account_bank_reconciliation_ce/__manifest__.py:external_dependencies``).
* **Post-install hook.** ``post_init_hook`` ensures accounting and bank
  reconciliation group members belong to ``base.group_user`` so that
  ``ir.attachment`` uploads never raise ``AccessError``
  (Source: ``addons/account_bank_reconciliation_ce/hooks.py:post_init_hook``).
* **Assets.** The backend stylesheet
  ``static/src/scss/reconciliation.scss`` is registered on the
  ``web.assets_backend`` bundle
  (Source: ``addons/account_bank_reconciliation_ce/__manifest__.py:assets``).
* **Models.** ``account.bank.statement.import`` (BR-001),
  ``account.reconciliation.matching`` (BR-002),
  ``account.reconcile.model`` extended via ``_inherit`` (BR-004),
  ``account.bank.statement.line`` extended via ``_inherit`` plus the
  ``account.reconciliation.partial.helper`` helper (BR-003 / BR-005), the
  ``account.bank.statement.import.wizard`` and
  ``account.reconciliation.wizard`` wizards, and the
  ``report.account_bank_reconciliation_ce.reconciliation_status`` report
  parser
  (Source: ``addons/account_bank_reconciliation_ce/models``;
  ``addons/account_bank_reconciliation_ce/report/reconciliation_report.py``).
* **Performance and quality targets.** Statement import under 10 seconds for
  500 lines; algorithmic matching under 5 seconds for 1,000 lines; rule
  evaluation under 1 second; matching accuracy of at least 95%; and a minimum
  of 80% test coverage
  (Source: ``addons/account_bank_reconciliation_ce/__manifest__.py:summary``).
* **Platform.** Odoo 19.0 Community Edition; Python 3.10 - 3.13; AGPL-3.0
  licensing; OCA coding standards; zero Enterprise dependencies
  (Source: ``addons/account_bank_reconciliation_ce/__manifest__.py:license``).


Known Issues / Roadmap
======================

* This module is delivered as part of EPIC-001 "Enterprise Accounting
  Capabilities" and is intended for contribution to the Odoo Community
  Association (OCA) in a future release cycle.
* Cross-module integrations with the other EPIC-001 Community Edition addons
  are intentionally avoided to preserve module independence; each addon in
  this repository stands on its own.
* Cross-currency consolidation across subsidiaries is out of scope for this
  release; partial reconciliation follows the company currency of the
  statement line.
* Refer to ``tickets/features/FEATURE-002-bank-reconciliation.md`` and the
  BR-001 through BR-005 story files under
  ``tickets/stories/bank-reconciliation/`` for the canonical feature and
  story specifications.


Changelog
=========

19.0.1.0.0 (2024-12-01)
-----------------------

Initial release. Delivers the five BR stories that constitute FEATURE-002
(Bank Reconciliation) under EPIC-001 (Enterprise Accounting Capabilities).

* **BR-001 Statement Import** - multi-format import (CSV, OFX, QIF,
  CAMT.053) with SHA256 duplicate detection and automatic format detection,
  implemented by ``account.bank.statement.import``.
* **BR-002 Algorithmic Matching** - weighted confidence scoring across
  amount, reference, partner, and date dimensions with High / Medium / Low /
  None classification, implemented by ``account.reconciliation.matching``.
* **BR-003 Manual Reconciliation** - guided review-and-confirm workflow with
  confidence badges, implemented by ``account.reconciliation.wizard`` and
  ``views/bank_reconciliation_views.xml``.
* **BR-004 Reconciliation Rules** - priority-ordered regex and amount rules
  that additively extend ``account.reconcile.model``, seeded from
  ``data/reconciliation_data.xml``.
* **BR-005 Partial Reconciliation** - partial reconciliation with write-off
  and multi-currency handling via the ``account.bank.statement.line``
  extension and the ``account.reconciliation.partial.helper`` helper.
* AGPL-3.0 licensing; depends only on the core ``account`` module; no Odoo
  Enterprise dependencies; additive ``_inherit`` extension only; backend
  assets registered on ``web.assets_backend``.


Bug Tracker
===========

Bugs are tracked in the issue tracker of the repository hosting this module.
In case of trouble, please check existing issues before submitting a new one.
When submitting a new issue, include:

* The module version (``19.0.1.0.0``).
* The Odoo version (19.0 Community Edition) and the Python version in use.
* A minimal reproduction case, including relevant data setup steps, the action
  that triggers the issue, and the observed versus expected result.
* Any stack traces or error messages from the Odoo server log.


Credits
=======

Authors
-------

* Enterprise Accounting Team
* Odoo Community Association (OCA)

Contributors
------------

* Enterprise Accounting Team
* OCA contributors - see module git history

Funding
-------

Development of this module was made possible by contributors aligned with the
Odoo Community Association mission of collaborative Odoo development.

License
-------

This module is distributed under the **GNU Affero General Public License v3.0
or later** (AGPL-3.0-or-later). See the ``LICENSE`` file at the repository
root for the full license text, or visit https://www.gnu.org/licenses/agpl for
an online copy.

The AGPL-3.0 license is chosen to ensure that any modifications or derivative
works remain available to the community under the same terms, consistent with
OCA policy and with the licensing posture of the peer modules
``account_financial_report_ce`` and ``account_budget_management`` already
present in this repository
(Source: ``addons/account_bank_reconciliation_ce/__manifest__.py:license``).


Maintainers
===========

This module is maintained by the Odoo Community Association (OCA).

OCA - the Odoo Community Association - is a nonprofit organisation whose
mission is to support the collaborative development of Odoo features and to
promote its widespread use. To contribute, follow the OCA guidelines at
https://odoo-community.org.

Current maintainer for this module:

* `OCA <https://odoo-community.org>`_
