# -*- coding: utf-8 -*-

from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged


@tagged("-at_install", "post_install")
class TestCorporateLmsAiInstall(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.training_manager = mail_new_test_user(
            cls.env,
            login="corporate_lms_ai_training_manager",
            name="Corporate LMS AI Training Manager",
            email="corporate.lms.ai.manager@example.com",
            groups="base.group_user,corporate_lms_base.group_corporate_lms_training_manager",
        )
        cls.learner = mail_new_test_user(
            cls.env,
            login="corporate_lms_ai_learner",
            name="Corporate LMS AI Learner",
            email="corporate.lms.ai.learner@example.com",
            groups="base.group_user,corporate_lms_base.group_corporate_lms_learner",
        )

    def test_ai_dependency_and_menu_foundation(self):
        self.assertTrue(
            self.env["ir.model"].search([("model", "=", "ai.agent")], limit=1)
        )
        self.assertTrue(
            self.env.ref("corporate_lms_base.menu_corporate_lms_ai", raise_if_not_found=False)
        )

    def test_phase9_ai_draft_fields_are_available(self):
        expected_fields = {
            "elearning.program": ["ai_agent_id", "ai_summary"],
            "slide.channel": [
                "ai_agent_id",
                "ai_course_summary",
                "ai_difficulty_suggestion",
                "ai_sync_status",
            ],
            "slide.slide": [
                "ai_summary",
                "ai_keywords",
                "ai_source_id",
                "ai_sync_status",
            ],
            "elearning.assignment.submission": [
                "ai_feedback_draft",
                "ai_strengths",
                "ai_weaknesses",
            ],
            "elearning.question": ["ai_explanation"],
        }
        for model_name, field_names in expected_fields.items():
            model = self.env[model_name]
            for field_name in field_names:
                self.assertIn(field_name, model._fields)

    def test_phase9_ai_draft_fields_do_not_replace_official_fields(self):
        self.assertIn("feedback", self.env["elearning.assignment.submission"]._fields)
        self.assertIn("score", self.env["elearning.assignment.submission"]._fields)
        self.assertIn("score", self.env["elearning.question"]._fields)
        self.assertIn("passing_score", self.env["elearning.program"]._fields)

    def test_ai_program_action_fallback_and_learner_block(self):
        program = self.env["elearning.program"].create({
            "name": "AI Program",
            "code": "AI-PROGRAM",
            "ai_summary": "<p>Existing draft summary.</p>",
        })

        with self.assertRaises(UserError):
            program.with_user(self.training_manager).action_generate_program_ai_summary()
        self.assertEqual(program.ai_summary, "<p>Existing draft summary.</p>")

        with self.assertRaises(AccessError):
            program.with_user(self.learner).action_generate_program_ai_summary()

    def test_ai_submission_action_does_not_change_official_feedback_or_score(self):
        program = self.env["elearning.program"].create({
            "name": "AI Assignment Program",
            "code": "AI-ASSIGNMENT-PROGRAM",
            "state": "published",
        })
        assignment = self.env["elearning.assignment"].with_user(self.training_manager).create({
            "name": "AI Feedback Assignment",
            "description": "<p>Review this submission.</p>",
            "program_id": program.id,
            "state": "published",
        })
        submission = self.env["elearning.assignment.submission"].with_user(self.training_manager).create({
            "assignment_id": assignment.id,
            "partner_id": self.learner.partner_id.id,
            "text_answer": "<p>Answer.</p>",
            "score": 40.0,
            "feedback": "<p>Official feedback.</p>",
            "ai_feedback_draft": "<p>Existing AI draft.</p>",
        })

        with self.assertRaises(UserError):
            submission.with_user(self.training_manager).action_generate_submission_feedback_draft()

        self.assertEqual(submission.score, 40.0)
        self.assertEqual(submission.feedback, "<p>Official feedback.</p>")
        self.assertEqual(submission.ai_feedback_draft, "<p>Existing AI draft.</p>")

    def test_ai_question_action_does_not_activate_question(self):
        bank = self.env["elearning.question.bank"].with_user(self.training_manager).create({
            "name": "AI Question Bank",
            "owner_id": self.training_manager.id,
        })
        question = self.env["elearning.question"].with_user(self.training_manager).create({
            "bank_id": bank.id,
            "name": "AI generated draft question",
            "question_type": "single",
            "ai_explanation": "<p>Existing draft explanation.</p>",
            "answer_ids": [(0, 0, {"name": "Correct", "is_correct": True})],
        })

        with self.assertRaises(UserError):
            question.with_user(self.training_manager).action_generate_question_ai_explanation()

        self.assertEqual(question.state, "draft")
        self.assertEqual(question.ai_explanation, "<p>Existing draft explanation.</p>")
