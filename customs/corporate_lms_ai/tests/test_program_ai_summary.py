# -*- coding: utf-8 -*-

import json
from unittest.mock import patch

from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("-at_install", "post_install")
class TestCorporateLmsProgramAiSummary(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.training_manager = mail_new_test_user(
            cls.env,
            login="corporate_lms_program_ai_summary_manager",
            name="Corporate LMS Program AI Summary Manager",
            email="corporate.lms.program.ai.summary.manager@example.com",
            groups="base.group_user,corporate_lms_base.group_corporate_lms_training_manager",
        )
        cls.learner = mail_new_test_user(
            cls.env,
            login="corporate_lms_program_ai_summary_learner",
            name="Corporate LMS Program AI Summary Learner",
            email="corporate.lms.program.ai.summary.learner@example.com",
            groups="base.group_user,corporate_lms_base.group_corporate_lms_learner",
        )
        cls.level = cls.env["elearning.employee.level"].create({
            "name": "Program AI Junior",
            "code": "PROGRAM-AI-JUNIOR",
        })
        cls.role_track = cls.env["elearning.role.track"].create({
            "name": "Program AI Backend",
            "code": "PROGRAM-AI-BACKEND",
        })
        cls.channel = cls.env["slide.channel"].create({
            "name": "Program AI Course",
            "description": "<p>Course context for the program summary.</p>",
            "channel_type": "training",
            "enroll": "public",
            "visibility": "public",
            "is_published": True,
        })
        cls.agent = cls.env["ai.agent"].create({
            "name": "Program AI Summary Agent",
            "restrict_to_sources": True,
        })
        attachment = cls.env["ir.attachment"].create({
            "name": "Program AI Source",
            "raw": "Indexed source text for the learning program.",
            "mimetype": "text/plain",
        })
        cls.env["ai.agent.source"].create({
            "name": "Program AI Indexed Source",
            "agent_id": cls.agent.id,
            "attachment_id": attachment.id,
            "type": "binary",
            "status": "indexed",
            "is_active": True,
        })
        cls.agent_without_source = cls.env["ai.agent"].create({
            "name": "Program AI Summary Agent Without Source",
            "restrict_to_sources": True,
        })

    def setUp(self):
        super().setUp()
        params = self.env["ir.config_parameter"].sudo()
        params.set_param("corporate_lms_ai.provider", "")
        params.set_param("corporate_lms_ai.model", "")
        params.set_param("corporate_lms_ai.endpoint", "")
        params.set_param("ai.openai_key", "")

    def _create_program(self, **values):
        defaults = {
            "name": "Program AI Summary Program",
            "code": "PROGRAM-AI-SUMMARY",
            "description": "<p>Program description for AI summary.</p>",
            "target_level_ids": [(6, 0, [self.level.id])],
            "target_role_track_ids": [(6, 0, [self.role_track.id])],
            "passing_score": 70.0,
            "line_ids": [(0, 0, {
                "channel_id": self.channel.id,
                "mandatory": True,
                "unlock_policy": "always",
                "weight": 1.0,
            })],
        }
        defaults.update(values)
        return self.env["elearning.program"].with_user(self.training_manager).create(defaults)

    def _program_summary_payload(self):
        return json.dumps({
            "ai_summary": "<p>Generated program summary from selected AI Agent.</p>",
        })

    def test_program_without_ai_agent_raises_user_error(self):
        program = self._create_program(ai_summary="<p>Existing summary.</p>")

        with self.assertRaises(UserError) as error:
            program.with_user(self.training_manager).action_generate_program_ai_summary()

        self.assertIn("Vui lòng chọn AI Agent", str(error.exception))
        self.assertEqual(program.ai_summary, "<p>Existing summary.</p>")

    def test_program_with_ai_agent_calls_agent_service_and_saves_summary(self):
        program = self._create_program(ai_agent_id=self.agent.id)

        with patch(
            "odoo.addons.ai.models.ai_agent.AIAgent._generate_response",
            return_value=[self._program_summary_payload()],
        ) as generate_response:
            program.with_user(self.training_manager).action_generate_program_ai_summary()

        generate_response.assert_called_once()
        prompt = generate_response.call_args.kwargs["prompt"]
        self.assertIn("Program AI Summary Program", prompt)
        self.assertIn("PROGRAM-AI-SUMMARY", prompt)
        self.assertIn("Program AI Junior", prompt)
        self.assertIn("Program AI Backend", prompt)
        self.assertIn("Program AI Course", prompt)
        self.assertEqual(program.ai_summary, "<p>Generated program summary from selected AI Agent.</p>")

    def test_agent_without_valid_source_raises_user_error(self):
        program = self._create_program(
            ai_agent_id=self.agent_without_source.id,
            ai_summary="<p>Existing summary.</p>",
        )

        with self.assertRaises(UserError) as error:
            program.with_user(self.training_manager).action_generate_program_ai_summary()

        self.assertIn("AI Agent chưa được cấu hình mô hình hoặc nguồn dữ liệu hợp lệ", str(error.exception))
        self.assertEqual(program.ai_summary, "<p>Existing summary.</p>")

    def test_failed_generation_keeps_existing_draft_unchanged(self):
        program = self._create_program(
            ai_agent_id=self.agent.id,
            ai_summary="<p>Existing summary.</p>",
        )

        with patch(
            "odoo.addons.ai.models.ai_agent.AIAgent._generate_response",
            side_effect=RuntimeError("provider unavailable"),
        ), self.assertRaises(UserError) as error:
            program.with_user(self.training_manager).action_generate_program_ai_summary()

        self.assertIn("AI could not generate a program summary", str(error.exception))
        self.assertEqual(program.ai_summary, "<p>Existing summary.</p>")
