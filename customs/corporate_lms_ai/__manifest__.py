# -*- coding: utf-8 -*-

{
    "name": "Corporate LMS AI",
    "version": "19.0.1.0.0",
    "summary": "Corporate LMS AI foundation",
    "category": "Human Resources/eLearning",
    "author": "Corporate LMS",
    "license": "LGPL-3",
    "depends": [
        "corporate_lms_base",
        "corporate_lms_assessment",
        "ai",
        "website_slides",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/ai_field_views.xml",
        "views/ai_source_views.xml",
        "views/ai_question_wizard_views.xml",
    ],
    "demo": [],
    "installable": True,
    "application": False,
}
