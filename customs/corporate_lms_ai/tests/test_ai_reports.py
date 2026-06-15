# -*- coding: utf-8 -*-

from lxml import etree

from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.tests import TransactionCase, tagged


@tagged("-at_install", "post_install")
class TestCorporateLmsAiReports(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.training_manager = mail_new_test_user(
            cls.env,
            login="corporate_lms_ai_report_training_manager",
            name="Corporate LMS AI Report Training Manager",
            email="corporate.lms.ai.report.manager@example.com",
            groups="base.group_user,corporate_lms_base.group_corporate_lms_training_manager",
        )
        cls.learner = mail_new_test_user(
            cls.env,
            login="corporate_lms_ai_report_learner",
            name="Corporate LMS AI Report Learner",
            email="corporate.lms.ai.report.learner@example.com",
            groups="base.group_user,corporate_lms_base.group_corporate_lms_learner",
        )
        cls.agent = cls.env["ai.agent"].create({
            "name": "Corporate LMS AI Report Agent",
            "restrict_to_sources": True,
        })
        cls.channel = cls.env["slide.channel"].create({
            "name": "AI Report Course",
            "description": "<p>Report source content that should not be displayed by the report.</p>",
            "channel_type": "training",
            "enroll": "invite",
            "visibility": "members",
            "is_published": True,
            "ai_agent_id": cls.agent.id,
        })
        cls.slide = cls.env["slide.slide"].create({
            "name": "AI Report Slide",
            "channel_id": cls.channel.id,
            "slide_category": "article",
            "html_content": "<p>Slide source content that should not be displayed by the report.</p>",
            "is_published": True,
        })
        cls.source = cls.env["ai.agent.source"].with_user(cls.training_manager).create({
            "name": "AI Report Source",
            "agent_id": cls.agent.id,
            "type": "elearning_slide",
            "channel_id": cls.channel.id,
            "slide_id": cls.slide.id,
            "status": "processing",
        })

    def test_ai_source_sync_report_action_and_metadata_fields(self):
        action = self.env.ref("corporate_lms_ai.action_report_ai_source_sync")
        self.assertEqual(action.res_model, "ai.agent.source")
        self.assertIn("pivot", action.view_mode)

        data = self.source.with_user(self.training_manager).read([
            "type",
            "channel_id",
            "slide_id",
            "status",
            "user_has_access",
            "write_date",
        ])[0]
        self.assertEqual(data["type"], "elearning_slide")
        self.assertEqual(data["status"], "processing")
        self.assertTrue(data["channel_id"])
        self.assertTrue(data["slide_id"])

    def test_ai_source_sync_report_view_does_not_expose_content_fields(self):
        forbidden_fields = {"attachment_id", "url", "error_details", "index_content", "content"}
        view = self.env.ref("corporate_lms_ai.view_report_ai_source_sync_list")
        tree = etree.fromstring(view.arch_db.encode())
        field_names = {node.get("name") for node in tree.xpath(".//field[@name]")}

        self.assertFalse(forbidden_fields.intersection(field_names))
        self.assertIn("user_has_access", field_names)
        self.assertIn("write_date", field_names)

    def test_unauthorized_learner_report_metadata_does_not_include_source_content(self):
        data = self.env["ai.agent.source"].with_user(self.learner).search_read([
            ("id", "=", self.source.id),
        ], ["type", "channel_id", "slide_id", "status", "user_has_access"])

        self.assertEqual(len(data), 1)
        self.assertFalse(data[0]["user_has_access"])
        self.assertNotIn("Report source content", str(data[0]))
        self.assertNotIn("Slide source content", str(data[0]))
