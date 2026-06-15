# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import fields
from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("-at_install", "post_install")
class TestCorporateLmsAssignmentSubmission(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Program = cls.env["elearning.program"]
        cls.ProgramPartner = cls.env["elearning.program.partner"]
        cls.TrainingClass = cls.env["elearning.class"]
        cls.ClassStudent = cls.env["elearning.class.student"]
        cls.Assignment = cls.env["elearning.assignment"]
        cls.Submission = cls.env["elearning.assignment.submission"]
        cls.Gradebook = cls.env["elearning.gradebook"]
        cls.GradebookLine = cls.env["elearning.gradebook.line"]

        cls.training_manager = mail_new_test_user(
            cls.env,
            login="corporate_lms_assignment_training_manager",
            name="Corporate LMS Assignment Training Manager",
            email="corporate.lms.assignment.manager@example.com",
            groups="base.group_user,corporate_lms_base.group_corporate_lms_training_manager",
        )
        cls.instructor = mail_new_test_user(
            cls.env,
            login="corporate_lms_assignment_instructor",
            name="Corporate LMS Assignment Instructor",
            email="corporate.lms.assignment.instructor@example.com",
            groups="base.group_user,corporate_lms_base.group_corporate_lms_instructor",
        )
        cls.learner = mail_new_test_user(
            cls.env,
            login="corporate_lms_assignment_learner",
            name="Corporate LMS Assignment Learner",
            email="corporate.lms.assignment.learner@example.com",
            groups="base.group_user,corporate_lms_base.group_corporate_lms_learner",
        )
        cls.other_learner = mail_new_test_user(
            cls.env,
            login="corporate_lms_assignment_other_learner",
            name="Corporate LMS Assignment Other Learner",
            email="corporate.lms.assignment.other@example.com",
            groups="base.group_user,corporate_lms_base.group_corporate_lms_learner",
        )

        cls.program = cls.Program.create({
            "name": "Assignment Program",
            "code": "ASSIGNMENT-PROGRAM",
            "state": "published",
            "passing_score": 70.0,
        })
        cls.ProgramPartner.create({
            "program_id": cls.program.id,
            "partner_id": cls.learner.partner_id.id,
            "state": "in_progress",
        })
        cls.training_class = cls.TrainingClass.create({
            "name": "Assignment Class",
            "code": "ASSIGNMENT-CLASS",
            "program_id": cls.program.id,
            "trainer_ids": [(6, 0, [cls.instructor.id])],
        })
        cls.ClassStudent.create({
            "class_id": cls.training_class.id,
            "partner_id": cls.learner.partner_id.id,
            "state": "active",
        })

    def _create_assignment(self, **values):
        defaults = {
            "name": "Leadership Case Study",
            "description": "<p>Analyze the case and submit your answer.</p>",
            "program_id": self.program.id,
            "class_id": self.training_class.id,
            "submission_type": "mixed",
            "max_score": 100.0,
            "state": "published",
        }
        defaults.update(values)
        return self.Assignment.with_user(self.training_manager).create(defaults)

    def test_assignment_requires_learning_scope(self):
        with self.assertRaises(ValidationError):
            self.Assignment.with_user(self.training_manager).create({
                "name": "No Scope Assignment",
                "description": "<p>No scope.</p>",
                "state": "draft",
            })

    def test_learner_only_sees_published_assigned_assignments(self):
        visible_assignment = self._create_assignment(name="Visible Assignment")
        draft_assignment = self._create_assignment(name="Draft Assignment", state="draft")
        unassigned_program = self.Program.create({
            "name": "Unassigned Assignment Program",
            "code": "UNASSIGNED-ASSIGNMENT",
            "state": "published",
        })
        hidden_assignment = self._create_assignment(
            name="Hidden Assignment",
            program_id=unassigned_program.id,
            class_id=False,
        )

        visible = self.Assignment.with_user(self.learner).search([
            ("id", "in", (visible_assignment | draft_assignment | hidden_assignment).ids),
        ])

        self.assertEqual(visible, visible_assignment)

    def test_learner_can_submit_then_cannot_edit_until_returned(self):
        assignment = self._create_assignment()
        submission = self.Submission.with_user(self.learner).create({
            "assignment_id": assignment.id,
            "text_answer": "<p>Initial answer</p>",
        })

        submission.with_user(self.learner).action_submit()
        self.assertEqual(submission.state, "submitted")
        self.assertTrue(submission.submitted_at)

        with self.assertRaises(AccessError):
            submission.with_user(self.learner).write({"text_answer": "<p>Edited after submit</p>"})

        submission.with_user(self.instructor).action_return()
        submission.with_user(self.learner).write({"text_answer": "<p>Revised answer</p>"})
        self.assertEqual(submission.text_answer, "<p>Revised answer</p>")

    def test_closed_assignment_blocks_learner_submit(self):
        assignment = self._create_assignment()
        submission = self.Submission.with_user(self.learner).create({
            "assignment_id": assignment.id,
            "text_answer": "<p>Draft answer</p>",
        })
        assignment.with_user(self.training_manager).write({"state": "closed"})

        with self.assertRaises(ValidationError):
            submission.with_user(self.learner).action_submit()

    def test_submission_type_payload_is_validated(self):
        assignment = self._create_assignment(submission_type="url")
        submission = self.Submission.with_user(self.learner).create({
            "assignment_id": assignment.id,
            "text_answer": "<p>This is not a URL submission.</p>",
        })

        with self.assertRaises(ValidationError):
            submission.with_user(self.learner).action_submit()

        submission.with_user(self.learner).write({"external_url": "https://example.com/submission"})
        submission.with_user(self.learner).action_submit()
        self.assertEqual(submission.state, "submitted")

    def test_late_submission_becomes_late(self):
        assignment = self._create_assignment(
            due_date=fields.Datetime.now() - timedelta(days=1),
            submission_type="text",
        )
        submission = self.Submission.with_user(self.learner).create({
            "assignment_id": assignment.id,
            "text_answer": "<p>Submitted after due date.</p>",
        })

        submission.with_user(self.learner).action_submit()
        self.assertEqual(submission.state, "late")

    def test_instructor_grades_submission_and_updates_gradebook(self):
        assignment = self._create_assignment()
        submission = self.Submission.with_user(self.learner).create({
            "assignment_id": assignment.id,
            "text_answer": "<p>Submitted answer</p>",
            "ai_feedback_draft": "<p>Draft AI feedback</p>",
        })
        submission.with_user(self.learner).action_submit()

        submission.with_user(self.instructor).write({
            "score": 82.0,
            "feedback": "<p>Official instructor feedback</p>",
        })
        submission.with_user(self.instructor).action_grade()

        self.assertEqual(submission.state, "graded")
        self.assertEqual(submission.feedback, "<p>Official instructor feedback</p>")
        self.assertNotEqual(submission.feedback, submission.ai_feedback_draft)

        gradebook = self.Gradebook.search([
            ("program_id", "=", self.program.id),
            ("class_id", "=", self.training_class.id),
            ("partner_id", "=", self.learner.partner_id.id),
        ])
        self.assertEqual(len(gradebook), 1)
        line = self.GradebookLine.search([
            ("gradebook_id", "=", gradebook.id),
            ("source_type", "=", "assignment"),
            ("submission_id", "=", submission.id),
        ])
        self.assertEqual(len(line), 1)
        self.assertEqual(line.score, 82.0)
        self.assertEqual(gradebook.final_score, 82.0)

    def test_learner_only_reads_own_submissions(self):
        assignment = self._create_assignment()
        own_submission = self.Submission.with_user(self.learner).create({
            "assignment_id": assignment.id,
            "text_answer": "<p>Own answer</p>",
        })
        other_submission = self.Submission.with_user(self.training_manager).create({
            "assignment_id": assignment.id,
            "partner_id": self.other_learner.partner_id.id,
            "text_answer": "<p>Other answer</p>",
        })

        visible = self.Submission.with_user(self.learner).search([
            ("id", "in", (own_submission | other_submission).ids),
        ])
        self.assertEqual(visible, own_submission)
