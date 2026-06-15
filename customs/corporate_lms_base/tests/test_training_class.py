# -*- coding: utf-8 -*-

from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("-at_install", "post_install")
class TestCorporateLmsTrainingClass(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Program = cls.env["elearning.program"]
        cls.ProgramPartner = cls.env["elearning.program.partner"]
        cls.TrainingClass = cls.env["elearning.class"]
        cls.ClassStudent = cls.env["elearning.class.student"]
        cls.Channel = cls.env["slide.channel"]

        cls.slides_officer = mail_new_test_user(
            cls.env,
            login="corporate_lms_class_slides_officer",
            name="Corporate LMS Class Slides Officer",
            email="corporate.lms.class.slides@example.com",
            groups="base.group_user,website_slides.group_website_slides_officer",
        )
        cls.instructor = mail_new_test_user(
            cls.env,
            login="corporate_lms_class_instructor",
            name="Corporate LMS Class Instructor",
            email="corporate.lms.class.instructor@example.com",
            groups="base.group_user,corporate_lms_base.group_corporate_lms_instructor",
        )
        cls.manager = mail_new_test_user(
            cls.env,
            login="corporate_lms_class_manager",
            name="Corporate LMS Class Manager",
            email="corporate.lms.class.manager@example.com",
            groups="base.group_user,corporate_lms_base.group_corporate_lms_manager",
        )
        cls.learner = mail_new_test_user(
            cls.env,
            login="corporate_lms_class_learner",
            name="Corporate LMS Class Learner",
            email="corporate.lms.class.learner@example.com",
            groups="base.group_user,corporate_lms_base.group_corporate_lms_learner",
        )
        cls.other_learner = mail_new_test_user(
            cls.env,
            login="corporate_lms_class_other_learner",
            name="Corporate LMS Class Other Learner",
            email="corporate.lms.class.other@example.com",
            groups="base.group_user,corporate_lms_base.group_corporate_lms_learner",
        )

        cls.channel = cls._create_course("Class Cohort Course")
        cls.program = cls.Program.create({
            "name": "Class Cohort Program",
            "code": "CLASS-COHORT",
            "state": "published",
            "line_ids": [(0, 0, {
                "channel_id": cls.channel.id,
                "mandatory": True,
            })],
        })

    @classmethod
    def _create_course(cls, name):
        return cls.Channel.with_user(cls.slides_officer).create({
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

    def _create_class(self, **values):
        defaults = {
            "name": "Leader Batch",
            "code": "LEADER-BATCH",
            "program_id": self.program.id,
            "trainer_ids": [(6, 0, [self.instructor.id])],
        }
        defaults.update(values)
        return self.TrainingClass.create(defaults)

    def test_class_requires_program_or_course(self):
        with self.assertRaises(ValidationError):
            self.TrainingClass.create({
                "name": "No Content Class",
                "code": "NO-CONTENT",
                "trainer_ids": [(6, 0, [self.instructor.id])],
            })

        course_class = self.TrainingClass.create({
            "name": "Course Only Class",
            "code": "COURSE-ONLY",
            "channel_id": self.channel.id,
            "trainer_ids": [(6, 0, [self.instructor.id])],
        })
        self.assertEqual(course_class.channel_id, self.channel)

    def test_class_trainer_must_be_instructor_or_manager(self):
        with self.assertRaises(ValidationError):
            self._create_class(
                code="BAD-TRAINER",
                trainer_ids=[(6, 0, [self.learner.id])],
            )

        training_class = self._create_class(
            code="GOOD-TRAINERS",
            trainer_ids=[(6, 0, [self.instructor.id, self.manager.id])],
        )
        self.assertEqual(set(training_class.trainer_ids.ids), {self.instructor.id, self.manager.id})

    def test_class_rejects_more_than_max_students(self):
        training_class = self._create_class(code="MAX-STUDENTS", max_students=1)
        self.ClassStudent.create({
            "class_id": training_class.id,
            "partner_id": self.learner.partner_id.id,
            "state": "active",
        })

        with self.assertRaises(ValidationError):
            self.ClassStudent.create({
                "class_id": training_class.id,
                "partner_id": self.other_learner.partner_id.id,
                "state": "invited",
            })

    def test_class_student_is_unique_per_class_and_partner(self):
        training_class = self._create_class(code="UNIQUE-STUDENT")
        self.ClassStudent.create({
            "class_id": training_class.id,
            "partner_id": self.learner.partner_id.id,
        })

        with self.assertRaises(ValidationError):
            self.ClassStudent.create({
                "class_id": training_class.id,
                "partner_id": self.learner.partner_id.id,
            })

    def test_class_student_can_link_program_enrollment(self):
        training_class = self._create_class(code="PROGRAM-PARTNER")
        enrollment = self.ProgramPartner.create({
            "program_id": self.program.id,
            "partner_id": self.learner.partner_id.id,
        })
        student = self.ClassStudent.create({
            "class_id": training_class.id,
            "partner_id": self.learner.partner_id.id,
            "program_partner_id": enrollment.id,
            "state": "active",
        })
        self.assertEqual(student.program_partner_id, enrollment)

    def test_record_rules_limit_instructor_and_learner_visibility(self):
        assigned_class = self._create_class(code="ASSIGNED-CLASS")
        self.ClassStudent.create({
            "class_id": assigned_class.id,
            "partner_id": self.learner.partner_id.id,
        })
        hidden_class = self._create_class(
            code="HIDDEN-CLASS",
            trainer_ids=[(6, 0, [self.manager.id])],
        )

        instructor_classes = self.TrainingClass.with_user(self.instructor).search([
            ("id", "in", (assigned_class | hidden_class).ids),
        ])
        self.assertEqual(instructor_classes, assigned_class)

        learner_classes = self.TrainingClass.with_user(self.learner).search([
            ("id", "in", (assigned_class | hidden_class).ids),
        ])
        self.assertEqual(learner_classes, assigned_class)
