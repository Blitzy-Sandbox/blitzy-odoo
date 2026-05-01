# Copyright 2024 Enterprise Accounting Team
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Wizard package for the account_payment_followup module.

Registers TransientModel-based wizards with the Odoo ORM at module install:

    - :mod:`followup_report_wizard` — PF-003 Follow-up Aged Receivables
      report wizard. Collects filter parameters and dispatches PDF/XLSX
      generation through the AbstractModel parser in ``report/``.
"""

from . import followup_report_wizard
