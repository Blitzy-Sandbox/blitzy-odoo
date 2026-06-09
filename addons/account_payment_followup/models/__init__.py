# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

# Import order is critical: the three net-new models (account.followup.level,
# account.followup.line, account.followup.history) MUST be imported first so
# their External IDs (model_account_followup_level, etc.) are registered in
# the ORM Registry before the _inherit extensions on res.partner, account.move,
# and account.move.line attempt to reference them via Many2one/One2many fields.
from . import account_followup_level  # noqa: I001 - dependency-ordered, not alphabetical
from . import account_followup_line
from . import account_followup_history
from . import res_partner
from . import account_move
from . import account_move_line
