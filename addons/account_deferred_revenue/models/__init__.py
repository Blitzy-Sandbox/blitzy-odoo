# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from . import account_deferred_schedule  # noqa: I001 - Net-new model: account.deferred.schedule (foundational; must load first)
from . import account_deferred_line      # Net-new model: account.deferred.line (schedule_id FK)
from . import account_move               # _inherit = 'account.move' (reverse O2M extension)
from . import account_move_line          # _inherit = 'account.move.line' (relational extension)
