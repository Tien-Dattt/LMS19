# -*- coding: utf-8 -*-

from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("-at_install", "post_install")
class TestCorporateLmsRubricGradebook(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Rubric = cls.env["elearning.rubric"]
        cls.Criteria = cls.env["elearning.rubric.criteria"]
        cls.Program = cls.env["elearning.program"]
        cls.ProgramPartner = cls.env["elearning.program.partner"]
        cls.TrainingClass = cls.env["elearning.class"]
        cls.Gradebook = cls.env["elearning.gradebook"]
        cls.GradebookLine = cls.env["elearning.gradebook.line"]

        cls.training_manager = mail_new_test_user(
            cls.env,
            login="corporate_lms_gradebook_training_manager",
            name="Corporate LMS Gradebook Training Manager",
            email="corporate.lms.gradebook.manager@example.com",
            groups="base.group_user,corporate_lms_base.group_corporate_lms_training_manager",
        )
        cls.instructor = mail_new_test_user(
            cls.env,
            login="corporate_lms_gradebook_instructor",
            name="Corporate LMS Gradebook Instructor",
            email="corporate.lms.gradebook.instructor@example.com",
            groups="base.group_user,corporate_lms_base.group_corporate_lms_instructor",
        )
        cls.learner = mail_new_test_user(
            cls.env,
            login="corporate_lms_gradebook_learner",
            name="Corporate LMS Gradebook Learner",
            email="corporate.lms.gradebook.learner@example.com",
            groups="base.group_user,corporate_lms_base.group_corporate_lms_learner",
        )
        cls.other_learner = mail_new_test_user(
            cls.env,
            login="corporate_lms_gradebook_other_learner",
            name="Corporate LMS Gradebook Other Learner",
            email="corporate.lms.gradebook.other@example.com",
            groups="base.group_user,corporate_lms_base.group_corporate_lms_learner",
        )

        cls.program = cls.Program.create({
            "name": "Gradebook Program",
            "code": "GRADEBOOK-PROGRAM",
            "state": "published",
            "passing_score": 70.0,
        })
        cls.training_class = cls.TrainingClass.create({
            "name": "Gradebook Class",
            "code": "GRADEBOOK-CLASS",
            "program_id": cls.program.id,
            "trainer_ids": [(6, 0, [cls.instructor.id])],
        })

    def _create_gradebook(self, partner=None, **values):
        defaults = {
            "program_id": self.program.id,
            "class_id": self.training_class.id,
            "partner_id": (partner or self.learner.partner_id).id,
            "line_ids": [
                (0, 0, {
                    "source_type": "manual",
                    "score": 40.0,
                    "weight": 1.0,
                    "note": "Manual project score",
                }),
                (0, 0, {
                    "source_type": "manual",
                    "score": 15.0,
                    "weight": 2.0,
                    "note": "Manual case score",
                }),
            ],
        }
        defaults.update(values)
        return self.Gradebook.with_user(self.training_manager).create(defaults)

    def test_rubric_max_score_is_sum_of_criteria(self):
        rubric = self.Rubric.create({
            "name": "Leadership Case Rubric",
            "criteria_ids": [
                (0, 0, {"name": "Analysis", "max_score": 30.0, "sequence": 10}),
                (0, 0, {"name": "Action Plan", "max_score": 40.0, "sequence": 20}),
            ],
        })
        self.assertEqual(rubric.max_score, 70.0)

        with self.assertRaises(ValidationError):
            self.Criteria.create({
                "rubric_id": rubric.id,
                "name": "Invalid",
                "max_score": -1.0,
            })

    def test_gradebook_final_score_is_sum_of_weighted_scores(self):
        gradebook = self._create_gradebook()

        self.assertEqual(gradebook.line_ids[0].weighted_score, 40.0)
        self.assertEqual(gradebook.line_ids[1].weighted_score, 30.0)
        self.assertEqual(gradebook.final_score, 70.0)
        self.assertFalse(gradebook.passed)

    def test_finalize_sets_passed_and_updates_program_enrollment(self):
        enrollment = self.ProgramPartner.create({
            "program_id": self.program.id,
            "partner_id": self.learner.partner_id.id,
            "state": "in_progress",
        })
        gradebook = self._create_gradebook()

        gradebook.action_finalize()

        self.assertEqual(gradebook.state, "locked")
        self.assertTrue(gradebook.passed)
        self.assertEqual(enrollment.final_score, 70.0)
        self.assertEqual(enrollment.state, "completed")

    def test_failed_gradebook_updates_program_enrollment_as_failed(self):
        enrollment = self.ProgramPartner.create({
            "program_id": self.program.id,
            "partner_id": self.other_learner.partner_id.id,
            "state": "in_progress",
        })
        gradebook = self._create_gradebook(
            partner=self.other_learner.partner_id,
            line_ids=[(0, 0, {
                "source_type": "manual",
                "score": 60.0,
                "weight": 1.0,
            })],
        )

        gradebook.action_finalize()

        self.assertFalse(gradebook.passed)
        self.assertEqual(gradebook.state, "locked")
        self.assertEqual(enrollment.final_score, 60.0)
        self.assertEqual(enrollment.state, "failed")

    def test_instructor_can_adjust_manual_line_for_assigned_class(self):
        gradebook = self._create_gradebook()
        line = gradebook.line_ids[0]

        line.with_user(self.instructor).write({"score": 45.0})

        gradebook.invalidate_recordset(["final_score", "passed"])
        self.assertEqual(line.weighted_score, 45.0)
        self.assertEqual(gradebook.final_score, 75.0)

    def test_locked_gradebook_blocks_instructor_line_edits(self):
        gradebook = self._create_gradebook()
        line = gradebook.line_ids[0]
        gradebook.action_finalize()

        with self.assertRaises(AccessError):
            line.with_user(self.instructor).write({"score": 50.0})

        line.with_user(self.training_manager).write({"score": 50.0})
        self.assertEqual(line.score, 50.0)

    def test_learner_only_reads_own_gradebooks(self):
        own_gradebook = self._create_gradebook()
        other_gradebook = self._create_gradebook(
            partner=self.other_learner.partner_id,
            line_ids=[(0, 0, {
                "source_type": "manual",
                "score": 80.0,
                "weight": 1.0,
            })],
        )

        visible = self.Gradebook.with_user(self.learner).search([
            ("id", "in", (own_gradebook | other_gradebook).ids),
        ])
        self.assertEqual(visible, own_gradebook)
