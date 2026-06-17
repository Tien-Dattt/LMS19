# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name': 'Demo Data',
    'version': '1.1',
    'summary': 'Demo Data for E-learning and CRM',
    'sequence': 10,
    'description': """
Demo data for testing and training purposes.
Includes:
- E-learning demo data
- CRM demo data (Leads, Opportunities, Teams, Activities, Meetings)
    """,
    'depends': [
        'crm',
        'calendar',
        'utm',
    ],
    'data': [
        'data/demo_data_elearning_complete_vi.xml',
        ## 'data/demo_data_elearning_vi.xml',
        # 'data/demo_data_crm_complete.xml',
    ],
    'installable': True,
    'application': False,
    'author': 'Odoo S.A.',
    'license': 'LGPL-3',
}
