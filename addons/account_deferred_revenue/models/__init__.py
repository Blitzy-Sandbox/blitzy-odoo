# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

# Import order is intentional for Odoo model registry construction:
#   1. account_deferred_schedule.py defines the parent model
#      'account.deferred.schedule' (referenced by account.deferred.line via
#      the schedule_id Many2one Comodel), so it MUST be imported before
#      account_deferred_line.py so the parent model registers first.
#   2. account_move_line.py adds '_inherit = account.move.line' computed /
#      relational fields that back-reference to deferred records; import
#      last so both deferred models are registered before the inherit.
from . import account_deferred_schedule  # noqa: I001 - parent model must load first
from . import account_deferred_line
from . import account_move_line
