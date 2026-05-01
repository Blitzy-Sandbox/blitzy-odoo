# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Test package for the Payment Follow-up module.

Imports the shared :mod:`common` test base first so that
:class:`AccountPaymentFollowupTestCommon` is registered with Odoo's test
runner before any of the per-story ``test_pf_*.py`` modules try to
inherit from it.

Per-story test modules (``test_pf_001`` through ``test_pf_005``) will be
appended to the ``from . import (...)`` tuple as they are authored in
subsequent checkpoints. Importing only ``common`` at this stage keeps
the package valid Python and discoverable by Odoo's module loader
without referencing files that have not yet been created.
"""

from . import common
