# -*- coding: utf-8 -*-

import json
from unittest.mock import patch

from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged


@tagged("-at_install", "post_install")
class TestCorporateLmsAiFeedbackWorkflow(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.training_manager = mail_new_test_user(
            cls.env,
            login="corporate_lms_ai_feedback_training_manager",
            name="Corporate LMS AI Feedback Training Manager",
            email="corporate.lms.ai.feedback.manager@example.com",
            groups="base.group_user,corporate_lms_base.group_corporate_lms_training_manager",
        )
        cls.instructor = mail_new_test_user(
            cls.env,
            login="corporate_lms_ai_feedback_instructor",
            name="Corporate LMS AI Feedback Instructor",
            email="corporate.lms.ai.feedback.instructor@example.com",
            groups="base.group_user,corporate_lms_base.group_corporate_lms_instructor",
        )
        cls.learner = mail_new_test_user(
            cls.env,
            login="corporate_lms_ai_feedback_learner",
            name="Corporate LMS AI Feedback Learner",
            email="corporate.lms.ai.feedback.learner@example.com",
            groups="base.group_user,corporate_lms_base.group_corporate_lms_learner",
        )
        cls.agent = cls.env["ai.agent"].create({
            "name": "Corporate LMS Feedback Agent",
            "restrict_to_sources": True,
        })
        cls.channel = cls.env["slide.channel"].create({
            "name": "AI Feedback Course",
            "description": "<p>Course context for feedback.</p>",
            "channel_type": "training",
            "enroll": "public",
            "visibility": "public",
            "is_published": True,
            "ai_agent_id": cls.agent.id,
        })
        cls.training_class = cls.env["elearning.class"].with_user(cls.training_manager).create({
            "name": "AI Feedback Class",
            "code": "AI-FEEDBACK-CLASS",
            "channel_id": cls.channel.id,
            "trainer_ids": [(6, 0, [cls.instructor.id])],
            "state": "running",
        })
        cls.rubric = cls.env["elearning.rubric"].with_user(cls.training_manager).create({
            "name": "AI Feedback Rubric",
            "criteria_ids": [
                (0, 0, {
                    "name": "Clarity",
                    "description": "Clear explanation.",
                    "max_score": 40.0,
                }),
                (0, 0, {
                    "name": "Application",
                    "description": "Applies the concept.",
                    "max_score": 60.0,
                }),
            ],
        })
        cls.assignment = cls.env["elearning.assignment"].with_user(cls.training_manager).create({
            "name": "AI Feedback Assignment",
            "description": "<p>Explain how the course concept applies at work.</p>",
            "channel_id": cls.channel.id,
            "class_id": cls.training_class.id,
            "rubric_id": cls.rubric.id,
            "state": "published",
        })

    def _ai_payload(self):
        return json.dumps({
            "ai_feedback_draft": "<p>Draft feedback from AI.</p>",
            "ai_strengths": "<p>Strong practical example.</p>",
            "ai_weaknesses": "<p>Needs more detail on risks.</p>",
        })

    def _create_submission(self, **values):
        defaults = {
            "assignment_id": self.assignment.id,
            "partner_id": self.learner.partner_id.id,
            "text_answer": "<p>Learner answer with an applied example.</p>",
            "external_url": "https://example.com/work-sample",
            "score": 42.0,
            "feedback": "<p>Official feedback remains.</p>",
        }
        defaults.update(values)
        return self.env["elearning.assignment.submission"].with_user(self.training_manager).create(defaults)

    def test_ai_feedback_draft_generated_without_changing_official_fields(self):
        submission = self._create_submission()

        with patch(
            "odoo.addons.ai.models.ai_agent.AIAgent._generate_response",
            return_value=[self._ai_payload()],
        ):
            submission.with_user(self.instructor).action_generate_ai_feedback_draft()

        self.assertEqual(submission.ai_feedback_draft, "<p>Draft feedback from AI.</p>")
        self.assertEqual(submission.ai_strengths, "<p>Strong practical example.</p>")
        self.assertEqual(submission.ai_weaknesses, "<p>Needs more detail on risks.</p>")
        self.assertEqual(submission.feedback, "<p>Official feedback remains.</p>")
        self.assertEqual(submission.score, 42.0)

    def test_instructor_can_copy_draft_to_official_feedback_manually(self):
        submission = self._create_submission(ai_feedback_draft="<p>Reviewed draft feedback.</p>")

        submission.with_user(self.instructor).action_copy_ai_feedback_to_feedback()

        self.assertEqual(submission.feedback, "<p>Reviewed draft feedback.</p>")
        self.assertEqual(submission.score, 42.0)

    def test_learner_cannot_generate_or_copy_ai_feedback(self):
        submission = self._create_submission(ai_feedback_draft="<p>Draft feedback.</p>")

        with self.assertRaises(AccessError):
            submission.with_user(self.learner).action_generate_ai_feedback_draft()
        with self.assertRaises(AccessError):
            submission.with_user(self.learner).action_copy_ai_feedback_to_feedback()

    def test_ai_feedback_failure_is_readable_and_preserves_official_fields(self):
        submission = self._create_submission(ai_feedback_draft="<p>Existing draft.</p>")

        with patch(
            "odoo.addons.ai.models.ai_agent.AIAgent._generate_response",
            side_effect=RuntimeError("provider unavailable"),
        ), self.assertRaises(UserError) as error:
            submission.with_user(self.instructor).action_generate_ai_feedback_draft()

        self.assertIn("AI could not generate a feedback draft", str(error.exception))
        self.assertEqual(submission.ai_feedback_draft, "<p>Existing draft.</p>")
        self.assertEqual(submission.feedback, "<p>Official feedback remains.</p>")
        self.assertEqual(submission.score, 42.0)
