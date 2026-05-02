# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

# Both the AAP-mandated story-named test files (test_pf_<NNN>.py per
# AAP §0.5.1.4 / §0.7.2 — "Deterministic test naming. tests/test_<story_id_lowercase>.py
# — e.g., test_am_001.py, test_bm_004.py, test_dr_003.py, test_pf_002.py.")
# AND the descriptive-named test files are imported here so that Odoo's
# ``post_install`` test runner discovers every ``TransactionCase`` subclass
# in this package. The two file-name conventions cover overlapping but not
# byte-identical scenarios (see QA Checkpoint 10 finding for full rationale).
# Registering both ensures ≥80% module aggregate coverage and surfaces all
# scenarios mapped to the BDD acceptance criteria of PF-001..PF-005.
from . import (
    common,
    test_action_history,
    test_email_generation,
    test_followup_level,
    test_followup_report,
    test_overdue_calculation,
    test_pf_001,
    test_pf_002,
    test_pf_003,
    test_pf_004,
    test_pf_005,
)
