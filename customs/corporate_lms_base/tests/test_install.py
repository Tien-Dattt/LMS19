# -*- coding: utf-8 -*-

from odoo.tests import TransactionCase, tagged


@tagged("-at_install", "post_install")
class TestCorporateLmsBaseInstall(TransactionCase):
    def test_security_groups_exist(self):
        group_xmlids = [
            "corporate_lms_base.group_corporate_lms_admin",
            "corporate_lms_base.group_corporate_lms_training_manager",
            "corporate_lms_base.group_corporate_lms_hr_officer",
            "corporate_lms_base.group_corporate_lms_instructor",
            "corporate_lms_base.group_corporate_lms_manager",
            "corporate_lms_base.group_corporate_lms_learner",
        ]
        for xmlid in group_xmlids:
            self.assertTrue(self.env.ref(xmlid, raise_if_not_found=False), xmlid)

    def test_menu_structure_exists(self):
        menu_xmlids = [
            "corporate_lms_base.menu_corporate_lms_root",
            "corporate_lms_base.menu_corporate_lms_configuration",
            "corporate_lms_base.menu_corporate_lms_programs",
            "corporate_lms_base.menu_corporate_lms_classes",
            "corporate_lms_base.menu_corporate_lms_assessments",
            "corporate_lms_base.menu_corporate_lms_reports",
            "corporate_lms_base.menu_corporate_lms_ai",
        ]
        for xmlid in menu_xmlids:
            self.assertTrue(self.env.ref(xmlid, raise_if_not_found=False), xmlid)
