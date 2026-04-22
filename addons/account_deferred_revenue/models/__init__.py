# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

# Import order is intentional for Odoo model registry construction:
#   1. account_deferred_schedule.py defines the parent model
#      'account.deferred.schedule' (referenced by account.deferred.line via
#      the schedule_id Many2one comodel), so it MUST be imported before
#      account_deferred_line.py so the parent model registers first.
#   2. account_deferred_line.py declares the child model
#      'account.deferred.line' (referenced by account.move.line via
#      the deferred_line_id Many2one); it must load before account_move_line.
#   3. account_move.py adds '_inherit = account.move' with a reverse
#      One2many to 'account.deferred.schedule' (inverse_name='source_move_id'),
#      so the schedule model must be registered first. It also declares the
#      computed 'has_deferred_schedules' and the smart-button action.
#   4. account_move_line.py adds '_inherit = account.move.line' with
#      Many2one back-references to both 'account.deferred.schedule' and
#      'account.deferred.line'; import last so both deferred models are
#      registered before the inherit.
from . import account_deferred_schedule  # noqa: I001 - parent model must load first
from . import account_deferred_line
from . import account_move
from . import account_move_line
