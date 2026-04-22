# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

# Wizard modules are imported in alphabetical order:
#
#   * cutoff_wizard.py — DR-003 cut-off entry generation wizard
#     (``account.deferred.cutoff.wizard``).  TransientModel that posts
#     journal entries for all qualifying recognition lines through a
#     chosen cut-off date and optionally creates a reversal entry for
#     the next period.
#
#   * recognition_dashboard_wizard.py — DR-004 recognition dashboard
#     (``account.deferred.recognition.dashboard.wizard``).
#     Read-only TransientModel that aggregates deferred revenue and
#     expense data via efficient ``read_group`` SQL aggregation and
#     exposes four summary cards plus three JSON chart payloads.
from . import cutoff_wizard, recognition_dashboard_wizard
