# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    'name': 'Bank Reconciliation for Community Edition',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Reconciliation',
    'summary': (
        'Bank statement import (CSV, OFX, QIF, CAMT.053), algorithmic '
        'matching engine, configurable reconciliation rules, manual '
        'reconciliation workflows, and partial reconciliation with write-offs.'
    ),
    'author': 'Enterprise Accounting Team',
    'website': 'https://github.com/odoo/odoo',
    'license': 'AGPL-3',
    'depends': [
        'account',
    ],
    'data': [
        'security/bank_reconciliation_security.xml',
        'security/ir.model.access.csv',
        'data/reconciliation_data.xml',
        'report/reconciliation_report.xml',
        'wizard/bank_statement_import_wizard_views.xml',
        'wizard/reconciliation_wizard_views.xml',
        'views/bank_reconciliation_views.xml',
        'views/menuitem.xml',
    ],
    'demo': [
    ],
    'external_dependencies': {
        'python': ['ofxparse'],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
