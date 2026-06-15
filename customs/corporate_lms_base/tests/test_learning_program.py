# -*- coding: utf-8 -*-

from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("-at_install", "post_install")
class TestCorporateLmsLearningProgram(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Program = cls.env["elearning.program"]
        cls.ProgramLine = cls.env["elearning.program.line"]
        cls.ProgramPartner = cls.env["elearning.program.partner"]
        cls.Channel = cls.env["slide.channel"]
        cls.Slide = cls.env["slide.slide"]

        cls.officer = mail_new_test_user(
            cls.env,
            login="corporate_lms_slides_officer",
            name="Corporate LMS Slides Officer",
            email="corporate.lms.officer@example.com",
            groups="base.group_user,website_slides.group_website_slides_officer",
        )
        cls.learner = mail_new_test_user(
            cls.env,
            login="corporate_lms_learner_user",
            name="Corporate LMS Learner",
            email="corporate.lms.learner@example.com",
            groups="base.group_user,corporate_lms_base.group_corporate_lms_learner",
        )

        cls.channel_1 = cls._create_course("Required Course 1")
        cls.channel_2 = cls._create_course("Required Course 2")
        cls.optional_channel = cls._create_course("Optional Course")

    @classmethod
    def _create_course(cls, name):
        return cls.Channel.with_user(cls.officer).create({
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

    def _create_program(self):
        return self.Program.create({
            "name": "Leader Onboarding",
            "code": "LEADER-ONBOARDING",
            "state": "published",
            "passing_score": 80.0,
            "line_ids": [
                (0, 0, {
                    "channel_id": self.channel_1.id,
                    "sequence": 10,
                    "mandatory": True,
                    "unlock_policy": "always",
                    "weight": 1.0,
                }),
                (0, 0, {
                    "channel_id": self.channel_2.id,
                    "sequence": 20,
                    "mandatory": True,
                    "unlock_policy": "open_after_previous_completed",
                    "weight": 1.0,
                }),
                (0, 0, {
                    "channel_id": self.optional_channel.id,
                    "sequence": 30,
                    "mandatory": False,
                    "unlock_policy": "manual",
                    "weight": 0.5,
                }),
            ],
        })

    def test_program_line_rejects_duplicate_course_in_same_program(self):
        program = self.Program.create({
            "name": "Duplicate Course Program",
            "code": "DUP-COURSE",
            "state": "draft",
        })
        self.ProgramLine.create({
            "program_id": program.id,
            "channel_id": self.channel_1.id,
        })

        with self.assertRaises(ValidationError):
            self.ProgramLine.create({
                "program_id": program.id,
                "channel_id": self.channel_1.id,
            })

    def test_program_publish_requires_mandatory_course(self):
        program = self.Program.create({
            "name": "Program Without Mandatory Course",
            "code": "NO-MANDATORY",
        })

        with self.assertRaises(ValidationError):
            program.action_publish()

        self.ProgramLine.create({
            "program_id": program.id,
            "channel_id": self.channel_1.id,
            "mandatory": True,
        })
        program.action_publish()
        self.assertEqual(program.state, "published")

    def test_active_program_enrollment_is_unique_per_program_and_partner(self):
        program = self._create_program()
        self.ProgramPartner.create({
            "program_id": program.id,
            "partner_id": self.learner.partner_id.id,
            "state": "assigned",
        })

        with self.assertRaises(ValidationError):
            self.ProgramPartner.create({
                "program_id": program.id,
                "partner_id": self.learner.partner_id.id,
                "state": "in_progress",
            })

        completed = self.ProgramPartner.create({
            "program_id": program.id,
            "partner_id": self.learner.partner_id.id,
            "state": "completed",
        })
        self.assertEqual(completed.state, "completed")

    def test_enroll_required_courses_uses_odoo_membership_api(self):
        program = self._create_program()
        enrollment = self.ProgramPartner.create({
            "program_id": program.id,
            "partner_id": self.learner.partner_id.id,
        })

        enrollment.action_enroll_courses()

        memberships = self.env["slide.channel.partner"].sudo().search([
            ("channel_id", "in", (self.channel_1 | self.channel_2).ids),
            ("partner_id", "=", self.learner.partner_id.id),
            ("member_status", "!=", "invited"),
        ])
        self.assertEqual(set(memberships.mapped("channel_id").ids), set((self.channel_1 | self.channel_2).ids))
        self.assertFalse(self.env["slide.channel.partner"].sudo().search([
            ("channel_id", "=", self.optional_channel.id),
            ("partner_id", "=", self.learner.partner_id.id),
        ]))
        self.assertEqual(enrollment.state, "in_progress")

    def test_program_progress_uses_required_course_completion(self):
        program = self._create_program()
        enrollment = self.ProgramPartner.create({
            "program_id": program.id,
            "partner_id": self.learner.partner_id.id,
        })
        enrollment.action_enroll_courses()

        membership = self.env["slide.channel.partner"].sudo().search([
            ("channel_id", "=", self.channel_1.id),
            ("partner_id", "=", self.learner.partner_id.id),
        ], limit=1)
        membership.write({
            "member_status": "ongoing",
            "completion": 50,
        })
        enrollment.invalidate_recordset(["progress"])
        self.assertEqual(enrollment.progress, 0.0)

        self.channel_1.slide_content_ids.with_user(self.learner).action_mark_completed()
        enrollment.invalidate_recordset(["progress"])
        self.assertEqual(enrollment.progress, 50.0)

        self.optional_channel.sudo()._action_add_members(self.learner.partner_id)
        self.optional_channel.slide_content_ids.with_user(self.learner).action_mark_completed()
        enrollment.invalidate_recordset(["progress"])
        self.assertEqual(enrollment.progress, 50.0)

        self.channel_2.slide_content_ids.with_user(self.learner).action_mark_completed()
        enrollment.invalidate_recordset(["progress"])
        self.assertEqual(enrollment.progress, 100.0)
