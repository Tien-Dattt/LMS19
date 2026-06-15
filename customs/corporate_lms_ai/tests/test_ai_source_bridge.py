# -*- coding: utf-8 -*-

from unittest.mock import patch

from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged("-at_install", "post_install")
class TestCorporateLmsAiSourceBridge(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.training_manager = mail_new_test_user(
            cls.env,
            login="corporate_lms_ai_source_manager",
            name="Corporate LMS AI Source Manager",
            email="corporate.lms.ai.source.manager@example.com",
            groups="base.group_user,corporate_lms_base.group_corporate_lms_training_manager",
        )
        cls.learner = mail_new_test_user(
            cls.env,
            login="corporate_lms_ai_source_learner",
            name="Corporate LMS AI Source Learner",
            email="corporate.lms.ai.source.learner@example.com",
            groups="base.group_user,corporate_lms_base.group_corporate_lms_learner",
        )
        cls.other_learner = mail_new_test_user(
            cls.env,
            login="corporate_lms_ai_source_other_learner",
            name="Corporate LMS AI Source Other Learner",
            email="corporate.lms.ai.source.other@example.com",
            groups="base.group_user,corporate_lms_base.group_corporate_lms_learner",
        )
        cls.agent = cls.env["ai.agent"].create({
            "name": "Corporate LMS Source Agent",
            "restrict_to_sources": True,
        })
        cls.channel = cls.env["slide.channel"].create({
            "name": "AI Source Course",
            "description": "<p>Course source description.</p>",
            "description_short": "<p>Short source description.</p>",
            "channel_type": "training",
            "enroll": "invite",
            "visibility": "members",
            "is_published": True,
            "ai_agent_id": cls.agent.id,
        })
        cls.slide = cls.env["slide.slide"].create({
            "name": "AI Source Slide",
            "channel_id": cls.channel.id,
            "slide_category": "article",
            "html_content": "<p>Slide source content.</p>",
            "description": "<p>Slide source description.</p>",
            "is_published": True,
        })
        cls.channel._action_add_members(cls.learner.partner_id)

    def _create_course_source(self, channel=None):
        channel = channel or self.channel
        return self.env["ai.agent.source"].with_user(self.training_manager).create({
            "name": "Course Source",
            "agent_id": self.agent.id,
            "type": "elearning_course",
            "channel_id": channel.id,
        })

    def _create_slide_source(self, slide=None):
        slide = slide or self.slide
        return self.env["ai.agent.source"].with_user(self.training_manager).create({
            "name": "Slide Source",
            "agent_id": self.agent.id,
            "type": "elearning_slide",
            "slide_id": slide.id,
            "channel_id": slide.channel_id.id,
        })

    def test_create_elearning_source_types(self):
        course_source = self._create_course_source()
        slide_source = self._create_slide_source()

        self.assertEqual(course_source.type, "elearning_course")
        self.assertEqual(course_source.channel_id, self.channel)
        self.assertEqual(slide_source.type, "elearning_slide")
        self.assertEqual(slide_source.slide_id, self.slide)

    def test_learner_course_membership_controls_source_access(self):
        source = self._create_course_source()

        self.assertTrue(source.with_user(self.learner).user_has_access)
        self.assertFalse(source.with_user(self.other_learner).user_has_access)

    def test_slide_source_requires_published_slide(self):
        hidden_slide = self.env["slide.slide"].create({
            "name": "Hidden AI Source Slide",
            "channel_id": self.channel.id,
            "slide_category": "article",
            "html_content": "<p>Hidden content.</p>",
            "is_published": False,
        })
        source = self._create_slide_source(hidden_slide)

        self.assertFalse(source.with_user(self.learner).user_has_access)
        hidden_slide.is_published = True
        self.assertTrue(source.with_user(self.learner).user_has_access)

    def test_processing_hands_content_to_existing_embedding_pipeline(self):
        source = self._create_course_source()

        self.env["ai.agent.source"]._cron_process_sources()

        self.assertTrue(source.attachment_id)
        self.assertEqual(source.channel_id.ai_sync_status, "synced")
        self.assertEqual(source.status, "processing")

    def test_unauthorized_elearning_source_is_not_sent_to_rag_context(self):
        allowed_source = self._create_course_source()
        blocked_channel = self.env["slide.channel"].create({
            "name": "Blocked AI Source Course",
            "channel_type": "training",
            "enroll": "invite",
            "visibility": "members",
            "is_published": True,
            "ai_agent_id": self.agent.id,
        })
        blocked_source = self._create_course_source(blocked_channel)

        allowed_attachment = self.env["ir.attachment"].create({
            "name": "Allowed LMS Source",
            "raw": "Allowed learner content",
            "mimetype": "text/html",
        })
        blocked_attachment = self.env["ir.attachment"].create({
            "name": "Blocked LMS Source",
            "raw": "Blocked learner content",
            "mimetype": "text/html",
        })
        allowed_source.write({
            "attachment_id": allowed_attachment.id,
            "status": "indexed",
            "is_active": True,
        })
        blocked_source.write({
            "attachment_id": blocked_attachment.id,
            "status": "indexed",
            "is_active": True,
        })
        allowed_embedding = self.env["ai.embedding"].create({
            "attachment_id": allowed_attachment.id,
            "content": "Allowed learner content",
            "embedding_model": "text-embedding-3-small",
        })
        blocked_embedding = self.env["ai.embedding"].create({
            "attachment_id": blocked_attachment.id,
            "content": "Blocked learner content",
            "embedding_model": "text-embedding-3-small",
        })
        all_embeddings = allowed_embedding | blocked_embedding

        def _fake_similar_chunks(query_embedding, sources, embedding_model, top_n=5):
            self.assertIn(allowed_source, sources)
            self.assertNotIn(blocked_source, sources)
            return all_embeddings.filtered(lambda embedding: embedding.attachment_id in sources.mapped("attachment_id"))

        with patch(
            "odoo.addons.ai.utils.llm_api_service.LLMApiService.get_embedding",
            return_value={"data": [{"embedding": [0.0] * 1536}]},
        ), patch(
            "odoo.addons.ai.models.ai_embedding.AIEmbedding._get_similar_chunks",
            side_effect=_fake_similar_chunks,
        ):
            messages = self.agent.with_user(self.learner)._build_rag_context("What should I study?")

        context = "\n".join(messages)
        self.assertIn("Allowed learner content", context)
        self.assertNotIn("Blocked learner content", context)

    def test_learner_cannot_trigger_elearning_source_sync(self):
        source = self._create_course_source()

        with self.assertRaises(AccessError):
            source.with_user(self.learner).action_sync_elearning_ai_sources()
