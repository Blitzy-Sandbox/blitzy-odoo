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

The order of imports matters: ``common`` MUST come first so the base
class is available to subclasses; the per-story modules then extend it.
"""

from . import (
    common,
    test_pf_001,
    test_pf_002,
    test_pf_003,
    test_pf_004,
    test_pf_005,
)
