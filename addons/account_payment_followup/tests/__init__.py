# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Test package for the Payment Follow-up module.

Imports the shared :mod:`common` test base first so that
:class:`AccountPaymentFollowupTestCommon` is registered with Odoo's test
runner before any of the per-story ``test_pf_*.py`` modules try to
inherit from it.

Per-story test modules (``test_pf_001`` through ``test_pf_005``) are
appended to the import list below as they are authored. The order of
imports matters: ``common`` MUST come first so the base class is
available to subclasses; the per-story modules then extend it.
"""

from . import (
    common,
    test_pf_005,
)
