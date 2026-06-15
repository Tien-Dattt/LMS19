# -*- coding: utf-8 -*-

from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.tests import TransactionCase, tagged


@tagged("-at_install", "post_install")
class TestCorporateLmsBaseReports(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.training_manager = mail_new_test_user(
            cls.env,
            login="corporate_lms_report_training_manager",
            name="Corporate LMS Report Training Manager",
            email="corporate.lms.report.manager@example.com",
            groups="base.group_user,corporate_lms_base.group_corporate_lms_training_manager",
        )
        cls.learner = mail_new_test_user(
            cls.env,
            login="corporate_lms_report_learner",
            name="Corporate LMS Report Learner",
            email="corporate.lms.report.learner@example.com",
            groups="base.group_user,corporate_lms_base.group_corporate_lms_learner",
        )
        cls.other_learner = mail_new_test_user(
            cls.env,
            login="corporate_lms_report_other_learner",
            name="Corporate LMS Report Other Learner",
            email="corporate.lms.report.other@example.com",
            groups="base.group_user,corporate_lms_base.group_corporate_lms_learner",
        )
        cls.department = cls.env["hr.department"].create({"name": "Report Department"})
        cls.level = cls.env["elearning.employee.level"].create({
            "name": "Report Level",
            "code": "REPORT-LEVEL",
        })
        cls.role_track = cls.env["elearning.role.track"].create({
            "name": "Report Role Track",
            "code": "REPORT-ROLE",
        })
        cls.employee = cls.env["hr.employee"].create({
            "name": "Report Learner Employee",
            "user_id": cls.learner.id,
            "department_id": cls.department.id,
            "employee_level_id": cls.level.id,
            "role_track_id": cls.role_track.id,
        })
        cls.other_employee = cls.env["hr.employee"].create({
            "name": "Other Report Employee",
            "user_id": cls.other_learner.id,
        })
        cls.program = cls.env["elearning.program"].create({
            "name": "Report Program",
            "code": "REPORT-PROGRAM",
            "state": "published",
        })
        cls.own_enrollment = cls.env["elearning.program.partner"].create({
            "program_id": cls.program.id,
            "partner_id": cls.learner.partner_id.id,
            "employee_id": cls.employee.id,
            "state": "in_progress",
            "final_score": 75.0,
        })
        cls.other_enrollment = cls.env["elearning.program.partner"].create({
            "program_id": cls.program.id,
            "partner_id": cls.other_learner.partner_id.id,
            "employee_id": cls.other_employee.id,
            "state": "assigned",
            "final_score": 20.0,
        })

    def test_program_enrollment_report_fields_and_action_exist(self):
        action = self.env.ref("corporate_lms_base.action_report_program_enrollment")
        self.assertEqual(action.res_model, "elearning.program.partner")
        self.assertIn("pivot", action.view_mode)
        for field_name in ("department_id", "employee_level_id", "role_track_id"):
            self.assertIn(field_name, self.env["elearning.program.partner"]._fields)

        self.assertEqual(self.own_enrollment.department_id, self.department)
        self.assertEqual(self.own_enrollment.employee_level_id, self.level)
        self.assertEqual(self.own_enrollment.role_track_id, self.role_track)

    def test_training_manager_sees_all_program_enrollment_report_records(self):
        visible = self.env["elearning.program.partner"].with_user(self.training_manager).search([
            ("id", "in", (self.own_enrollment | self.other_enrollment).ids),
        ])
        self.assertEqual(set(visible.ids), set((self.own_enrollment | self.other_enrollment).ids))

    def test_learner_sees_only_own_program_enrollment_report_records(self):
        visible = self.env["elearning.program.partner"].with_user(self.learner).search([
            ("id", "in", (self.own_enrollment | self.other_enrollment).ids),
        ])
        self.assertEqual(visible, self.own_enrollment)
