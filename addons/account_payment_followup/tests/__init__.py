# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Test package for the Payment Follow-up module.

Imports the shared :mod:`common` test base first so that
:class:`AccountPaymentFollowupTestCommon` is registered with Odoo's test
runner before any of the per-story ``test_pf_*.py`` modules try to
inherit from it.

Per-story test modules cover the five PF stories defined in the AAP:

  * ``test_pf_001`` — Follow-up Level Configuration (PF-001)
  * ``test_pf_002`` — Automated Email Generation (PF-002, includes
    Gate 13 cron reachability and batch_size=500 contract)
  * ``test_pf_003`` — Follow-up Report Generation (PF-003, includes
    PDF/XLSX magic-byte verification and XMLID validation)
  * ``test_pf_004`` — Action History Tracking (PF-004, includes
    BR-003 immutability tests and manager-unlink check)
  * ``test_pf_005`` — Overdue Calculation (PF-005, complete coverage of
    the four model files PF-005 owns)

Plus thematic per-feature acceptance suites that target the wizard,
parser, and email-generation modules with file-name-aligned identifiers:

  * ``test_email_generation`` — PF-002 acceptance & integration tests
    (27 methods covering all 8 BDD scenarios, all 7 BRs, fault
    tolerance, and trigger actions). Mirrors the per-component file
    naming convention used by FEATURE-001's
    ``account_financial_report_ce/tests/test_balance_sheet.py``,
    ``test_aged_partner.py`` etc., providing a high-resolution
    coverage layer on top of the per-story ``test_pf_002.py`` module.
  * ``test_followup_report`` — PF-003 acceptance & integration tests
    (30 methods covering wizard CRUD, all 8 BDD scenarios, all 7 BRs,
    and the SLA performance gate). Mirrors the per-component file
    naming convention used by FEATURE-001's
    ``account_financial_report_ce/tests/test_balance_sheet.py``,
    ``test_aged_partner.py`` etc., providing a high-resolution
    coverage layer on top of the per-story ``test_pf_003.py`` module.
  * ``test_overdue_calculation`` — PF-005 phase-plan acceptance tests
    (35 methods covering the agent-prompt's nine-phase plan: days-
    overdue calculation, level assignment, aging-bucket boundaries,
    disputed-invoice framework, partial-payment residual semantics,
    recalculation triggers, BR-006 credit notes, and performance /
    integration). Mirrors the per-component file naming convention
    used by FEATURE-001's
    ``account_financial_report_ce/tests/test_aged_partner.py``,
    providing a complementary coverage layer alongside
    ``test_pf_005.py``.

The order of imports matters: ``common`` MUST come first so the base
class is available to subclasses; the per-story modules then extend it.
"""

from . import (
    common,
    test_email_generation,
    test_followup_report,
    test_overdue_calculation,
    test_pf_001,
    test_pf_002,
    test_pf_003,
    test_pf_004,
    test_pf_005,
)
