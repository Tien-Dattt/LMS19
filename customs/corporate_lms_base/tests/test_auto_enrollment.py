# -*- coding: utf-8 -*-

from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.tests import TransactionCase, tagged


@tagged("-at_install", "post_install")
class TestCorporateLmsAutoEnrollment(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Level = cls.env["elearning.employee.level"]
        cls.RoleTrack = cls.env["elearning.role.track"]
        cls.Program = cls.env["elearning.program"]
        cls.Matrix = cls.env["elearning.training.matrix"]
        cls.Enrollment = cls.env["elearning.program.partner"]
        cls.Log = cls.env["elearning.auto.enrollment.log"]
        cls.Channel = cls.env["slide.channel"]

        cls.officer = mail_new_test_user(
            cls.env,
            login="corporate_lms_auto_slides_officer",
            name="Corporate LMS Auto Slides Officer",
            email="corporate.lms.auto.officer@example.com",
            groups="base.group_user,website_slides.group_website_slides_officer",
        )
        cls.hr_officer = mail_new_test_user(
            cls.env,
            login="corporate_lms_auto_hr_officer",
            name="Corporate LMS Auto HR Officer",
            email="corporate.lms.auto.hr@example.com",
            groups=(
                "base.group_user,"
                "hr.group_hr_user,"
                "corporate_lms_base.group_corporate_lms_hr_officer"
            ),
        )

    def _create_user(self, login):
        return mail_new_test_user(
            self.env,
            login=login,
            name=login.replace("_", " ").title(),
            email=f"{login}@example.com",
            groups="base.group_user",
        )

    def _create_course(self, name):
        return self.Channel.with_user(self.officer).create({
            "name": name,
            "channel_type": "training",
            "enroll": "public",
            "visibility": "public",
            "is_published": True,
            "slide_ids": [(0, 0, {
                "name": f"{name} Lesson",
                "slide_category": "document",
                "is_published": True,
                "completion_time": 1.0,
            })],
        })

    def _create_program_with_course(self, state="published"):
        channel = self._create_course(f"Auto Course {state}")
        program = self.Program.create({
            "name": f"Auto Program {state}",
            "code": f"AUTO-{state.upper()}",
            "state": state,
            "line_ids": [(0, 0, {
                "channel_id": channel.id,
                "mandatory": True,
            })],
        })
        return program, channel

    def test_missing_user_partner_is_logged_as_skipped(self):
        level = self.Level.create({"name": "Auto No User Level", "code": "AUTO-NO-USER"})
        program, _channel = self._create_program_with_course()
        self.Matrix.create({
            "name": "Auto No User Matrix",
            "employee_level_id": level.id,
            "program_id": program.id,
        })

        employee = self.env["hr.employee"].create({
            "name": "No User Employee",
            "employee_level_id": level.id,
        })

        log = self.Log.search([("employee_id", "=", employee.id)], limit=1)
        self.assertEqual(log.status, "skipped")
        self.assertEqual(log.message, "skipped_no_user_partner")

    def test_no_matrix_is_logged_as_skipped(self):
        user = self._create_user("corporate_lms_no_matrix_user")
        employee = self.env["hr.employee"].create({
            "name": "No Matrix Employee",
            "user_id": user.id,
        })

        log = self.Log.search([("employee_id", "=", employee.id)], limit=1)
        self.assertEqual(log.status, "skipped")
        self.assertEqual(log.message, "no_matrix_matched")
        self.assertEqual(log.partner_id, user.partner_id)

    def test_draft_program_matrix_is_not_enrolled(self):
        level = self.Level.create({"name": "Auto Draft Level", "code": "AUTO-DRAFT"})
        program, _channel = self._create_program_with_course(state="draft")
        matrix = self.Matrix.create({
            "name": "Auto Draft Matrix",
            "employee_level_id": level.id,
            "program_id": program.id,
        })
        user = self._create_user("corporate_lms_draft_program_user")

        employee = self.env["hr.employee"].create({
            "name": "Draft Program Employee",
            "user_id": user.id,
            "employee_level_id": level.id,
        })

        self.assertFalse(self.Enrollment.search([
            ("program_id", "=", program.id),
            ("partner_id", "=", user.partner_id.id),
        ]))
        log = self.Log.search([("employee_id", "=", employee.id)], limit=1)
        self.assertEqual(log.status, "skipped")
        self.assertEqual(log.message, "program_not_published")
        self.assertEqual(log.matrix_id, matrix)

    def test_auto_enrollment_creates_enrollment_and_course_membership(self):
        level = self.Level.create({"name": "Auto Leader Level", "code": "AUTO-LEADER"})
        role = self.RoleTrack.create({"name": "Auto People Leader", "code": "AUTO-PEOPLE"})
        program, channel = self._create_program_with_course()
        matrix = self.Matrix.create({
            "name": "Auto Leader Matrix",
            "employee_level_id": level.id,
            "role_track_id": role.id,
            "program_id": program.id,
            "deadline_days": 14,
        })
        user = self._create_user("corporate_lms_auto_success_user")

        employee = self.env["hr.employee"].create({
            "name": "Auto Success Employee",
            "user_id": user.id,
            "employee_level_id": level.id,
            "role_track_id": role.id,
        })

        enrollment = self.Enrollment.search([
            ("program_id", "=", program.id),
            ("partner_id", "=", user.partner_id.id),
        ])
        self.assertEqual(len(enrollment), 1)
        self.assertEqual(enrollment.employee_id, employee)
        self.assertEqual(enrollment.source, "matrix")
        self.assertEqual(enrollment.state, "in_progress")
        self.assertEqual(enrollment.deadline_date, employee._get_corporate_lms_deadline_date(matrix))

        membership = self.env["slide.channel.partner"].sudo().search([
            ("channel_id", "=", channel.id),
            ("partner_id", "=", user.partner_id.id),
            ("member_status", "!=", "invited"),
        ])
        self.assertEqual(len(membership), 1)

        log = self.Log.search([("employee_id", "=", employee.id)], limit=1)
        self.assertEqual(log.status, "success")
        self.assertEqual(log.message, "program_enrollment_created")
        self.assertEqual(log.matrix_id, matrix)
        self.assertEqual(log.program_id, program)

    def test_auto_enrollment_is_idempotent(self):
        level = self.Level.create({"name": "Auto Idempotent Level", "code": "AUTO-IDEMP"})
        program, channel = self._create_program_with_course()
        self.Matrix.create({
            "name": "Auto Idempotent Matrix",
            "employee_level_id": level.id,
            "program_id": program.id,
        })
        user = self._create_user("corporate_lms_auto_idempotent_user")
        employee = self.env["hr.employee"].create({
            "name": "Auto Idempotent Employee",
            "user_id": user.id,
            "employee_level_id": level.id,
        })

        employee.action_corporate_lms_auto_enroll()
        employee.action_corporate_lms_auto_enroll()

        self.assertEqual(self.Enrollment.search_count([
            ("program_id", "=", program.id),
            ("partner_id", "=", user.partner_id.id),
            ("state", "in", self.Enrollment._ACTIVE_STATES),
        ]), 1)
        self.assertEqual(self.env["slide.channel.partner"].sudo().search_count([
            ("channel_id", "=", channel.id),
            ("partner_id", "=", user.partner_id.id),
        ]), 1)

    def test_course_access_error_is_logged(self):
        level = self.Level.create({"name": "Auto Restricted Level", "code": "AUTO-RESTRICT"})
        program, channel = self._create_program_with_course()
        channel.with_user(self.officer).write({"enroll": "invite"})
        matrix = self.Matrix.create({
            "name": "Auto Restricted Matrix",
            "employee_level_id": level.id,
            "program_id": program.id,
        })
        user = self._create_user("corporate_lms_auto_restricted_user")
        employee = self.env["hr.employee"].with_context(
            skip_corporate_lms_auto_enrollment=True,
        ).create({
            "name": "Auto Restricted Employee",
            "user_id": user.id,
            "employee_level_id": level.id,
        })

        employee.with_user(self.hr_officer).action_corporate_lms_auto_enroll()

        log = self.Log.search([("employee_id", "=", employee.id)], limit=1)
        self.assertEqual(log.status, "error")
        self.assertIn("course_enrollment_error", log.message)
        self.assertEqual(log.matrix_id, matrix)
        self.assertEqual(log.program_id, program)
        self.assertFalse(self.env["slide.channel.partner"].sudo().search([
            ("channel_id", "=", channel.id),
            ("partner_id", "=", user.partner_id.id),
        ]))
