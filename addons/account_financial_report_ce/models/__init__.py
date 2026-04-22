# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

# Import order is critical: financial_report defines the abstract base model
# 'account.financial.report.abstract' that all other report models inherit from.
# It MUST be imported first to ensure the base is registered in the ORM registry
# before any child models attempt to inherit it.
from . import financial_report  # noqa: I001 - must load base model first
from . import aged_partner_balance
from . import balance_sheet
from . import cash_flow
from . import general_ledger
from . import profit_loss
from . import trial_balance
