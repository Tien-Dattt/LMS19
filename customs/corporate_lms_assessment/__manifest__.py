# -*- coding: utf-8 -*-

{
    "name": "Corporate LMS Assessment",
    "version": "19.0.1.0.0",
    "summary": "Corporate LMS assessment foundation",
    "category": "Human Resources/eLearning",
    "author": "Corporate LMS",
    "license": "LGPL-3",
    "depends": [
        "corporate_lms_base",
        "mail",
        "website_slides",
    ],
    "data": [
        "security/ir.model.access.csv",
        "security/assessment_security.xml",
        "views/rubric_views.xml",
        "views/assignment_views.xml",
        "views/question_bank_views.xml",
        "views/exam_views.xml",
        "views/gradebook_views.xml",
        "views/report_views.xml",
    ],
    "demo": [],
    "installable": True,
    "application": False,
}
