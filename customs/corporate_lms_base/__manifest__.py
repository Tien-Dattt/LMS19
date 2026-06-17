# -*- coding: utf-8 -*-

{
    "name": "Corporate LMS Base",
    "version": "19.0.1.0.0",
    "summary": "Corporate LMS foundation for Odoo eLearning",
    "category": "Human Resources/eLearning",
    "author": "Corporate LMS",
    "license": "LGPL-3",
    "depends": [
        "base",
        "mail",
        "hr",
        "website_slides",
    ],
    "data": [
        "security/corporate_lms_security.xml",
        "security/ir.model.access.csv",
        "security/program_security.xml",
        "security/class_security.xml",
        "data/auto_enrollment_data.xml",
        "views/corporate_lms_menus.xml",
        "views/employee_level_views.xml",
        "views/role_track_views.xml",
        "views/learning_program_views.xml",
        "views/program_enrollment_views.xml",
        "views/training_class_views.xml",
        "views/auto_enrollment_log_views.xml",
        "views/training_matrix_views.xml",
        "views/hr_employee_views.xml",
        "views/report_views.xml",
    ],
    "demo": [
        "demo/leader_onboarding_demo.xml",
        "demo/python_developer_onboarding_demo.xml",
    ],
    "installable": True,
    "application": False,
}
