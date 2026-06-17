# -*- coding: utf-8 -*-

import json
from unittest.mock import patch

from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged


@tagged("-at_install", "post_install")
class TestCorporateLmsAiDraftHardening(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = cls.env.ref("base.user_admin")
        cls.training_manager = mail_new_test_user(
            cls.env,
            login="corporate_lms_ai_draft_hardening_manager",
            name="Corporate LMS AI Draft Hardening Manager",
            email="corporate.lms.ai.draft.hardening.manager@example.com",
            groups="base.group_user,corporate_lms_base.group_corporate_lms_training_manager",
        )
        cls.learner = mail_new_test_user(
            cls.env,
            login="corporate_lms_ai_draft_hardening_learner",
            name="Corporate LMS AI Draft Hardening Learner",
            email="corporate.lms.ai.draft.hardening.learner@example.com",
            groups="base.group_user,corporate_lms_base.group_corporate_lms_learner",
        )
        cls.agent = cls.env["ai.agent"].create({
            "name": "Corporate LMS Draft Hardening Agent",
            "restrict_to_sources": True,
        })
        cls.channel = cls.env["slide.channel"].create({
            "name": "AI Draft Hardening Course",
            "description": "<p>Course content for AI draft hardening.</p>",
            "channel_type": "training",
            "enroll": "public",
            "visibility": "public",
            "is_published": True,
            "ai_agent_id": cls.agent.id,
        })
        cls.channel_without_agent = cls.env["slide.channel"].create({
            "name": "AI Draft Hardening Course Without Agent",
            "channel_type": "training",
            "enroll": "public",
            "visibility": "public",
            "is_published": True,
        })
        cls.slide = cls.env["slide.slide"].create({
            "name": "AI Draft Hardening Slide",
            "channel_id": cls.channel.id,
            "slide_category": "article",
            "html_content": "<p>Slide content for AI draft hardening.</p>",
            "is_published": True,
        })
        cls.program = cls.env["elearning.program"].with_user(cls.training_manager).create({
            "name": "AI Draft Hardening Program",
            "code": "AI-DRAFT-HARDENING",
        })
        cls.assignment = cls.env["elearning.assignment"].with_user(cls.training_manager).create({
            "name": "AI Draft Hardening Assignment",
            "description": "<p>Draft hardening assignment.</p>",
            "channel_id": cls.channel.id,
            "state": "published",
        })
        cls.submission = cls.env["elearning.assignment.submission"].with_user(cls.training_manager).create({
            "assignment_id": cls.assignment.id,
            "partner_id": cls.learner.partner_id.id,
            "text_answer": "<p>Draft hardening learner answer.</p>",
            "score": 55.0,
            "feedback": "<p>Official feedback remains unchanged.</p>",
        })
        cls.bank = cls.env["elearning.question.bank"].with_user(cls.training_manager).create({
            "name": "AI Draft Hardening Bank",
            "owner_id": cls.training_manager.id,
            "channel_id": cls.channel.id,
            "state": "active",
        })
        cls.question = cls.env["elearning.question"].with_user(cls.training_manager).create({
            "bank_id": cls.bank.id,
            "name": "Draft hardening question",
            "question_type": "single",
            "answer_ids": [
                (0, 0, {"name": "Correct", "is_correct": True}),
                (0, 0, {"name": "Wrong", "is_correct": False}),
            ],
        })

    def _set_ai_config(self):
        params = self.env["ir.config_parameter"].sudo()
        params.set_param("corporate_lms_ai.provider", "openai")
        params.set_param("corporate_lms_ai.model", "gpt-4o")
        params.set_param("corporate_lms_ai.endpoint", "https://api.openai.com/v1")
        params.set_param("ai.openai_key", "test-openai-key")

    def _clear_ai_config(self):
        params = self.env["ir.config_parameter"].sudo()
        params.set_param("corporate_lms_ai.provider", "")
        params.set_param("corporate_lms_ai.model", "")
        params.set_param("corporate_lms_ai.endpoint", "")
        params.set_param("ai.openai_key", "")

    def _course_summary_payload(self):
        return json.dumps({
            "ai_course_summary": "<p>Generated course summary.</p>",
            "ai_difficulty_suggestion": "Intermediate",
        })

    def _feedback_payload(self):
        return json.dumps({
            "ai_feedback_draft": "<p>Generated feedback draft.</p>",
            "ai_strengths": "<p>Clear example.</p>",
            "ai_weaknesses": "<p>Add more evidence.</p>",
        })

    def _question_payload(self):
        return json.dumps({
            "questions": [{
                "question": "Generated hardening draft question?",
                "question_type": "single",
                "difficulty": "medium",
                "score": 1.0,
                "answers": [
                    {"answer": "Correct answer", "is_correct": True},
                    {"answer": "Incorrect answer", "is_correct": False},
                ],
            }],
        })

    def test_system_admin_can_run_ai_draft_actions_without_ai_permission_block(self):
        self._set_ai_config()

        with patch(
            "odoo.addons.ai.models.ai_agent.AIAgent._generate_response",
            return_value=[self._course_summary_payload()],
        ):
            self.channel.with_user(self.admin).action_generate_course_ai_summary()
        self.assertEqual(self.channel.ai_course_summary, "<p>Generated course summary.</p>")
        self.assertEqual(self.channel.ai_difficulty_suggestion, "Intermediate")

        with patch(
            "odoo.addons.ai.models.ai_agent.AIAgent._generate_response",
            return_value=[self._feedback_payload()],
        ):
            self.submission.with_user(self.admin).action_generate_ai_feedback_draft()
        self.assertEqual(self.submission.ai_feedback_draft, "<p>Generated feedback draft.</p>")
        self.assertEqual(self.submission.feedback, "<p>Official feedback remains unchanged.</p>")
        self.assertEqual(self.submission.score, 55.0)

        wizard = self.env["elearning.ai.generate.question.wizard"].with_user(self.admin).create({
            "source_type": "course",
            "channel_id": self.channel.id,
            "question_bank_id": self.bank.id,
            "question_count": 1,
        })
        with patch(
            "odoo.addons.ai.models.ai_agent.AIAgent._generate_response",
            return_value=[self._question_payload()],
        ):
            wizard.action_generate_draft_questions()
        generated_question = self.env["elearning.question"].search([
            ("bank_id", "=", self.bank.id),
            ("name", "=", "Generated hardening draft question?"),
        ], limit=1)
        self.assertTrue(generated_question)
        self.assertEqual(generated_question.state, "draft")

        self.channel.with_user(self.admin).action_create_ai_source_from_course()
        source_count = self.env["ai.agent.source"].search_count([
            ("type", "=", "elearning_course"),
            ("channel_id", "=", self.channel.id),
            ("agent_id", "=", self.agent.id),
        ])
        self.assertEqual(source_count, 1)

        with self.assertRaises(UserError):
            self.program.with_user(self.admin).action_generate_program_ai_summary()
        with self.assertRaises(UserError):
            self.slide.with_user(self.admin).action_generate_slide_ai_summary()
        with self.assertRaises(UserError):
            self.question.with_user(self.admin).action_generate_question_ai_explanation()

    def test_unauthorized_user_is_blocked_from_ai_draft_actions(self):
        with self.assertRaises(AccessError):
            self.channel.with_user(self.learner).action_generate_course_ai_summary()
        with self.assertRaises(AccessError):
            self.channel.with_user(self.learner).action_create_ai_source_from_course()
        with self.assertRaises(AccessError):
            self.submission.with_user(self.learner).action_generate_ai_feedback_draft()

    def test_missing_ai_agent_raises_expected_error(self):
        with self.assertRaises(UserError) as error:
            self.channel_without_agent.with_user(self.training_manager).action_create_ai_source_from_course()
        self.assertIn("Set an AI Agent on the course", str(error.exception))

    def test_missing_ai_config_raises_expected_error_and_preserves_course_drafts(self):
        self._clear_ai_config()
        self.channel.write({
            "ai_course_summary": "<p>Existing course draft.</p>",
            "ai_difficulty_suggestion": "Existing difficulty",
        })

        with self.assertRaises(UserError) as error:
            self.channel.with_user(self.training_manager).action_generate_course_ai_summary()

        self.assertIn("Configure the Corporate LMS AI provider", str(error.exception))
        self.assertEqual(self.channel.ai_course_summary, "<p>Existing course draft.</p>")
        self.assertEqual(self.channel.ai_difficulty_suggestion, "Existing difficulty")

    def test_create_ai_source_from_course_does_not_duplicate_sources(self):
        self.channel.with_user(self.training_manager).action_create_ai_source_from_course()
        self.channel.with_user(self.training_manager).action_create_ai_source_from_course()

        source_count = self.env["ai.agent.source"].search_count([
            ("type", "=", "elearning_course"),
            ("channel_id", "=", self.channel.id),
            ("agent_id", "=", self.agent.id),
        ])
        self.assertEqual(source_count, 1)
