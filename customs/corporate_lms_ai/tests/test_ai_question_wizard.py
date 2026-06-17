# -*- coding: utf-8 -*-

import json
from unittest.mock import patch

from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("-at_install", "post_install")
class TestCorporateLmsAiQuestionWizard(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Wizard = cls.env["elearning.ai.generate.question.wizard"]
        cls.Question = cls.env["elearning.question"]
        cls.SlideQuestion = cls.env["slide.question"]
        cls.Exam = cls.env["elearning.exam"]

        cls.training_manager = mail_new_test_user(
            cls.env,
            login="corporate_lms_ai_question_training_manager",
            name="Corporate LMS AI Question Training Manager",
            email="corporate.lms.ai.question.manager@example.com",
            groups="base.group_user,corporate_lms_base.group_corporate_lms_training_manager",
        )
        cls.instructor = mail_new_test_user(
            cls.env,
            login="corporate_lms_ai_question_instructor",
            name="Corporate LMS AI Question Instructor",
            email="corporate.lms.ai.question.instructor@example.com",
            groups="base.group_user,corporate_lms_base.group_corporate_lms_instructor",
        )
        cls.learner = mail_new_test_user(
            cls.env,
            login="corporate_lms_ai_question_learner",
            name="Corporate LMS AI Question Learner",
            email="corporate.lms.ai.question.learner@example.com",
            groups="base.group_user,corporate_lms_base.group_corporate_lms_learner",
        )
        cls.agent = cls.env["ai.agent"].create({
            "name": "Corporate LMS Question Agent",
            "restrict_to_sources": True,
        })
        params = cls.env["ir.config_parameter"].sudo()
        params.set_param("corporate_lms_ai.provider", "openai")
        params.set_param("corporate_lms_ai.model", "gpt-4o")
        params.set_param("corporate_lms_ai.endpoint", "https://api.openai.com/v1")
        params.set_param("ai.openai_key", "test-openai-key")
        cls.channel = cls.env["slide.channel"].create({
            "name": "AI Question Course",
            "description": "<p>Course context for generated questions.</p>",
            "channel_type": "training",
            "enroll": "public",
            "visibility": "public",
            "is_published": True,
            "ai_agent_id": cls.agent.id,
        })
        cls.slide = cls.env["slide.slide"].create({
            "name": "AI Question Slide",
            "channel_id": cls.channel.id,
            "slide_category": "article",
            "html_content": "<p>Slide context for generated questions.</p>",
            "is_published": True,
        })
        cls.bank = cls.env["elearning.question.bank"].with_user(cls.training_manager).create({
            "name": "AI Generated Question Bank",
            "owner_id": cls.instructor.id,
            "channel_id": cls.channel.id,
            "state": "active",
        })

    def _payload(self, count=2):
        questions = []
        for index in range(1, count + 1):
            questions.append({
                "question": f"Generated draft question {index}?",
                "question_type": "single",
                "difficulty": "medium",
                "score": 1.0,
                "answers": [
                    {"answer": "Correct answer", "is_correct": True, "feedback": "Good choice"},
                    {"answer": "Incorrect answer", "is_correct": False},
                ],
        })
        return json.dumps({"questions": questions})

    def setUp(self):
        super().setUp()
        params = self.env["ir.config_parameter"].sudo()
        params.set_param("corporate_lms_ai.provider", "openai")
        params.set_param("corporate_lms_ai.model", "gpt-4o")
        params.set_param("corporate_lms_ai.endpoint", "https://api.openai.com/v1")
        params.set_param("ai.openai_key", "test-openai-key")

    def _create_wizard(self, **values):
        defaults = {
            "source_type": "course",
            "channel_id": self.channel.id,
            "question_bank_id": self.bank.id,
            "question_count": 2,
            "difficulty": "medium",
        }
        defaults.update(values)
        return self.Wizard.with_user(self.instructor).create(defaults)

    def test_wizard_creates_draft_questions_and_answers_only(self):
        wizard = self._create_wizard()
        slide_question_count = self.SlideQuestion.search_count([])

        with patch(
            "odoo.addons.ai.models.ai_agent.AIAgent._generate_response",
            return_value=[self._payload()],
        ):
            wizard.action_generate_draft_questions()

        questions = self.Question.search([
            ("bank_id", "=", self.bank.id),
            ("name", "ilike", "Generated draft question"),
        ])
        self.assertEqual(len(questions), 2)
        self.assertEqual(set(questions.mapped("state")), {"draft"})
        self.assertTrue(all(questions.mapped("answer_ids")))
        self.assertEqual(self.SlideQuestion.search_count([]), slide_question_count)

    def test_draft_questions_are_not_used_in_published_exam_until_active(self):
        wizard = self._create_wizard(question_count=1)
        with patch(
            "odoo.addons.ai.models.ai_agent.AIAgent._generate_response",
            return_value=[self._payload(count=1)],
        ):
            wizard.action_generate_draft_questions()

        question = self.Question.search([
            ("bank_id", "=", self.bank.id),
            ("name", "ilike", "Generated draft question"),
        ], limit=1)
        exam = self.Exam.with_user(self.training_manager).create({
            "name": "AI Draft Question Exam",
            "channel_id": self.channel.id,
            "question_bank_id": self.bank.id,
            "question_count": 1,
            "state": "draft",
        })

        with self.assertRaises(ValidationError):
            exam.action_publish()

        question.with_user(self.training_manager).action_activate()
        exam.action_publish()
        self.assertEqual(exam.state, "published")

    def test_learner_cannot_use_question_generation_wizard(self):
        with self.assertRaises(AccessError):
            self.Wizard.with_user(self.learner).create({
                "source_type": "course",
                "channel_id": self.channel.id,
                "question_bank_id": self.bank.id,
                "question_count": 1,
            })

    def test_ai_failure_shows_friendly_error(self):
        wizard = self._create_wizard(question_count=1)

        with patch(
            "odoo.addons.ai.models.ai_agent.AIAgent._generate_response",
            side_effect=RuntimeError("provider unavailable"),
        ), self.assertRaises(UserError) as error:
            wizard.action_generate_draft_questions()

        self.assertIn("AI could not generate draft questions", str(error.exception))
        questions = self.Question.search([
            ("bank_id", "=", self.bank.id),
            ("name", "ilike", "Generated draft question"),
        ])
        self.assertFalse(questions)
