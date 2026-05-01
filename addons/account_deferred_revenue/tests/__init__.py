# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Test package for the account_deferred_revenue module (FEATURE-005, Track C).

This package aggregates the per-story test modules listed below. Each module
maps one user story from tickets/stories/deferred-revenue/ to its own file
named ``test_<story_id_lowercase>.py`` per the OCA test naming convention.

Stories covered:
    - DR-001 Deferral Schedule Definition (test_dr_001)
    - DR-002 Automatic Period Allocation (test_dr_002)
    - DR-003 Cut-off Entry Generation (test_dr_003)
    - DR-004 Recognition Dashboard (test_dr_004)

Test classes inherit from
``odoo.addons.account.tests.common.AccountTestInvoicingCommon`` and are
decorated with ``@tagged('post_install', '-at_install')`` so they run after
the full module (including security groups, views, and data files) has
been installed.

Each test module must reach ≥80% line coverage on its corresponding
production code per AAP Rule R-04.
"""

from . import (
    test_dr_001,  # Foundational — DR-001 Deferral Schedule Definition
    test_dr_002,  # Depends on DR-001 — Automatic Period Allocation
    test_dr_003,  # Depends on DR-002 — Cut-off Entry Generation
    test_dr_004,  # Depends on DR-001/002/003 — Recognition Dashboard
)
