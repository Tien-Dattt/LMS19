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

        root_menu = self.env.ref("corporate_lms_base.menu_corporate_lms_root")
        elearning_menu = self.env.ref("website_slides.website_slides_menu_root")
        self.assertEqual(root_menu.parent_id, elearning_menu)
        self.assertFalse(root_menu.web_icon)
        self.assertFalse(root_menu.web_icon_data)

        corporate_menu_ids = self.env["ir.model.data"].search([
            ("module", "=", "corporate_lms_base"),
            ("model", "=", "ir.ui.menu"),
        ]).mapped("res_id")
        corporate_menus = self.env["ir.ui.menu"].browse(corporate_menu_ids).exists()
        self.assertFalse(corporate_menus.filtered(lambda menu: not menu.parent_id))
