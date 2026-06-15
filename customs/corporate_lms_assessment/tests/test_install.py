# -*- coding: utf-8 -*-

from odoo.tests import TransactionCase, tagged


@tagged("-at_install", "post_install")
class TestCorporateLmsAssessmentInstall(TransactionCase):
    def test_assessment_module_and_menu_foundation(self):
        module = self.env["ir.module.module"].search(
            [("name", "=", "corporate_lms_assessment")],
            limit=1,
        )
        self.assertEqual(module.state, "installed")
        self.assertTrue(
            self.env.ref(
                "corporate_lms_base.menu_corporate_lms_assessments",
                raise_if_not_found=False,
            )
        )
