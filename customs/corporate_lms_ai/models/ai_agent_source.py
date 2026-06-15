# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools.mail import html_to_inner_content

from odoo.addons.ai.models.ai_agent import PREPROMPTS
from odoo.addons.ai.utils.llm_api_service import LLMApiService


ELEARNING_SOURCE_TYPES = ("elearning_course", "elearning_slide")
AI_SOURCE_MANAGER_GROUPS = (
    "corporate_lms_base.group_corporate_lms_admin",
    "corporate_lms_base.group_corporate_lms_training_manager",
)
AI_SOURCE_INSTRUCTOR_GROUP = "corporate_lms_base.group_corporate_lms_instructor"


class AIAgent(models.Model):
    _inherit = "ai.agent"

    def _build_rag_context(self, prompt):
        self.ensure_one()
        elearning_sources = self.sources_ids.filtered(lambda source: source.type in ELEARNING_SOURCE_TYPES)
        if not elearning_sources:
            return super()._build_rag_context(prompt)

        accessible_sources = self.sources_ids.filtered(
            lambda source: source.type not in ELEARNING_SOURCE_TYPES or source.user_has_access
        )
        if not accessible_sources:
            return []

        provider = self._get_provider()
        embedding_model = self._get_embedding_model()
        response = LLMApiService(env=self.env, provider=provider).get_embedding(
            input=prompt,
            dimensions=self.env["ai.embedding"]._get_dimensions(),
            model=embedding_model,
        )
        if not response or "data" not in response:
            raise UserError(_("Failed to get embeddings for the prompt."))

        prompt_embedding = response["data"][0]["embedding"]
        similar_embeddings = self.env["ai.embedding"]._get_similar_chunks(
            query_embedding=prompt_embedding,
            sources=accessible_sources,
            embedding_model=embedding_model,
            top_n=5,
        )
        if not similar_embeddings:
            return []

        context = ""
        referenced_attachments = set()
        for embedding in similar_embeddings:
            context += f"{embedding.attachment_id.name}\n{embedding.content}\n\n"
            if embedding.attachment_id and embedding.attachment_id.name:
                referenced_attachments.add(embedding.attachment_id.name)

        referenced_sources = self.env["ai.agent.source"].search([
            ("attachment_id.name", "in", list(referenced_attachments)),
        ])
        accessible_names = referenced_sources.filtered(
            lambda source: source.type not in ELEARNING_SOURCE_TYPES or source.user_has_access
        ).mapped("name")
        if accessible_names:
            context += f"##References:\n{', '.join(accessible_names)}"

        return [f"##Context information:\n\n{context}\n{PREPROMPTS['context']}"] if context else []


class AIAgentSource(models.Model):
    _inherit = "ai.agent.source"

    type = fields.Selection(
        selection_add=[
            ("elearning_course", "eLearning Course"),
            ("elearning_slide", "eLearning Slide"),
        ],
        ondelete={
            "elearning_course": lambda records: records.write({"type": "binary"}),
            "elearning_slide": lambda records: records.write({"type": "binary"}),
        },
    )
    channel_id = fields.Many2one(
        "slide.channel",
        string="Course",
        index=True,
        ondelete="cascade",
    )
    slide_id = fields.Many2one(
        "slide.slide",
        string="Slide",
        index=True,
        ondelete="cascade",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("type") in ELEARNING_SOURCE_TYPES:
                self._check_elearning_source_vals_access(vals)
        sources = super().create(vals_list)
        elearning_sources = sources.filtered(lambda source: source.type in ELEARNING_SOURCE_TYPES)
        if elearning_sources:
            elearning_sources._write_related_sync_status("not_synced")
            self.env.ref("ai.ir_cron_process_sources")._trigger()
        return sources

    def write(self, vals):
        elearning_sources = self.filtered(lambda source: source.type in ELEARNING_SOURCE_TYPES)
        if elearning_sources or vals.get("type") in ELEARNING_SOURCE_TYPES:
            self._check_elearning_source_manage_access(vals=vals)
        result = super().write(vals)
        if {"channel_id", "slide_id"}.intersection(vals):
            self.filtered(lambda source: source.type in ELEARNING_SOURCE_TYPES)._write_related_sync_status("not_synced")
        return result

    def unlink(self):
        self.filtered(lambda source: source.type in ELEARNING_SOURCE_TYPES)._check_elearning_source_manage_access()
        return super().unlink()

    @api.depends_context("uid")
    @api.depends("type", "channel_id", "slide_id", "slide_id.is_published", "channel_id.is_published")
    def _compute_user_has_access(self):
        elearning_sources = self.filtered(lambda source: source.type in ELEARNING_SOURCE_TYPES)
        for source in elearning_sources:
            if source.type == "elearning_course":
                source.user_has_access = source._user_has_elearning_course_access(source.channel_id)
            elif source.type == "elearning_slide":
                source.user_has_access = bool(source.slide_id.is_published) and source._user_has_elearning_course_access(
                    source.slide_id.channel_id
                )
            else:
                source.user_has_access = False
        super(AIAgentSource, self - elearning_sources)._compute_user_has_access()

    @api.model
    def create_from_elearning_courses(self, channel_ids, agent_id):
        channels = self.env["slide.channel"].browse(channel_ids).exists()
        vals_list = []
        for channel in channels:
            self._check_elearning_course_manage_access(channel)
            existing = self.search([
                ("type", "=", "elearning_course"),
                ("channel_id", "=", channel.id),
                ("agent_id", "=", agent_id),
            ], limit=1)
            if existing:
                continue
            vals_list.append({
                "name": channel.name,
                "agent_id": agent_id,
                "type": "elearning_course",
                "channel_id": channel.id,
            })
        return self.create(vals_list) if vals_list else self.browse()

    @api.model
    def create_from_elearning_slides(self, slide_ids, agent_id):
        slides = self.env["slide.slide"].browse(slide_ids).exists()
        vals_list = []
        for slide in slides:
            self._check_elearning_course_manage_access(slide.channel_id)
            existing = self.search([
                ("type", "=", "elearning_slide"),
                ("slide_id", "=", slide.id),
                ("agent_id", "=", agent_id),
            ], limit=1)
            if existing:
                slide.sudo().ai_source_id = existing.id
                continue
            vals_list.append({
                "name": slide.name,
                "agent_id": agent_id,
                "type": "elearning_slide",
                "slide_id": slide.id,
                "channel_id": slide.channel_id.id,
            })
        sources = self.create(vals_list) if vals_list else self.browse()
        for source in sources:
            source.slide_id.sudo().ai_source_id = source.id
        return sources

    def action_sync_elearning_ai_sources(self):
        elearning_sources = self.filtered(lambda source: source.type in ELEARNING_SOURCE_TYPES)
        elearning_sources._check_elearning_source_manage_access()
        elearning_sources.write({
            "status": "processing",
            "is_active": False,
            "error_details": False,
        })
        elearning_sources._write_related_sync_status("not_synced")
        self.env["ai.agent.source"]._cron_process_sources()
        return True

    def action_access_source(self):
        self.ensure_one()
        if self.type == "elearning_course":
            if not self.user_has_access:
                raise AccessError(_("You are not allowed to access this eLearning AI source."))
            if not self.channel_id:
                raise UserError(_("This eLearning course source is not linked to a course."))
            return {
                "type": "ir.actions.act_window",
                "name": _("Course"),
                "res_model": "slide.channel",
                "view_mode": "form",
                "res_id": self.channel_id.id,
            }
        if self.type == "elearning_slide":
            if not self.user_has_access:
                raise AccessError(_("You are not allowed to access this eLearning AI source."))
            if not self.slide_id:
                raise UserError(_("This eLearning slide source is not linked to a slide."))
            return {
                "type": "ir.actions.act_window",
                "name": _("Slide"),
                "res_model": "slide.slide",
                "view_mode": "form",
                "res_id": self.slide_id.id,
            }
        return super().action_access_source()

    def _cron_process_sources(self):
        elearning_sources = self.env["ai.agent.source"].search([
            ("type", "in", ELEARNING_SOURCE_TYPES),
            ("status", "=", "processing"),
        ])
        trigger_embeddings_cron = False
        for source in elearning_sources:
            try:
                content = source._get_elearning_source_content()
                if not content:
                    raise UserError(_("No indexable eLearning content was found for this source."))
                trigger_embeddings_cron |= self._process_source_content(
                    source,
                    content,
                    url=source._get_elearning_source_url(),
                )
                source._write_related_sync_status("synced")
            except Exception as error:
                source.write({
                    "status": "failed",
                    "is_active": False,
                    "error_details": str(error),
                })
                source._write_related_sync_status("error")

        if trigger_embeddings_cron:
            self.env.ref("ai.ir_cron_generate_embedding")._trigger()
        return super()._cron_process_sources()

    def _get_elearning_source_content(self):
        self.ensure_one()
        if self.type == "elearning_course":
            if not self.channel_id:
                return ""
            return self._get_elearning_course_content(self.channel_id)
        if self.type == "elearning_slide":
            if not self.slide_id:
                return ""
            return self._get_elearning_slide_content(self.slide_id)
        return ""

    def _get_elearning_course_content(self, channel):
        parts = [
            _("Course: %s") % channel.name,
            self._field_text(channel, "description_short"),
            self._field_text(channel, "description"),
            self._field_text(channel, "description_html"),
        ]
        slide_field = "slide_content_ids" if "slide_content_ids" in channel._fields else "slide_ids"
        slides = channel[slide_field].filtered(lambda slide: not slide.is_category and slide.is_published)
        for slide in slides:
            slide_content = self._get_elearning_slide_content(slide)
            if slide_content:
                parts.append(slide_content)
        return "\n\n".join(part for part in parts if part)

    def _get_elearning_slide_content(self, slide):
        parts = [
            _("Slide: %s") % slide.name,
            self._field_text(slide, "description"),
            self._field_text(slide, "html_content"),
            self._field_text(slide, "url"),
        ]
        return "\n\n".join(part for part in parts if part)

    def _get_elearning_source_url(self):
        self.ensure_one()
        if self.type == "elearning_course":
            return f"elearning://course/{self.channel_id.id}"
        if self.type == "elearning_slide":
            return f"elearning://slide/{self.slide_id.id}"
        return False

    def _write_related_sync_status(self, status):
        for source in self:
            if source.type == "elearning_course" and source.channel_id and "ai_sync_status" in source.channel_id._fields:
                source.channel_id.sudo().ai_sync_status = status
            elif source.type == "elearning_slide" and source.slide_id and "ai_sync_status" in source.slide_id._fields:
                source.slide_id.sudo().ai_sync_status = status

    def _field_text(self, record, field_name):
        if field_name not in record._fields or not record[field_name]:
            return ""
        field = record._fields[field_name]
        if field.type == "html":
            return html_to_inner_content(record[field_name])
        if field.type in ("char", "text"):
            return str(record[field_name])
        return ""

    def _user_has_elearning_course_access(self, channel):
        if not channel:
            return False
        if self._is_ai_source_manager():
            return True
        if not channel.is_published:
            return False
        if self._is_elearning_course_instructor(channel):
            return True

        partner = self.env.user.partner_id
        if not partner:
            return False

        membership = self.env["slide.channel.partner"].sudo().search_count([
            ("channel_id", "=", channel.id),
            ("partner_id", "=", partner.id),
            ("member_status", "!=", "invited"),
            ("active", "=", True),
        ], limit=1)
        if membership:
            return True

        program_access = self.env["elearning.program.partner"].sudo().search_count([
            ("partner_id", "=", partner.id),
            ("state", "in", ("assigned", "in_progress", "completed")),
            ("program_id.state", "=", "published"),
            ("program_id.line_ids.channel_id", "=", channel.id),
        ], limit=1)
        if program_access:
            return True

        return bool(self.env["elearning.class.student"].sudo().search_count([
            ("partner_id", "=", partner.id),
            ("state", "in", ("invited", "active", "completed")),
            ("class_id.state", "in", ("open", "running", "done")),
            "|",
            ("class_id.channel_id", "=", channel.id),
            ("class_id.program_id.line_ids.channel_id", "=", channel.id),
        ], limit=1))

    def _check_elearning_source_vals_access(self, vals):
        if vals.get("type") == "elearning_course":
            channel = self.env["slide.channel"].browse(vals.get("channel_id")).exists()
        elif vals.get("type") == "elearning_slide":
            slide = self.env["slide.slide"].browse(vals.get("slide_id")).exists()
            channel = slide.channel_id
        else:
            channel = self.env["slide.channel"]
        self._check_elearning_course_manage_access(channel)

    def _check_elearning_source_manage_access(self, vals=None):
        vals = vals or {}
        if self._is_ai_source_manager():
            return
        for source in self:
            channel = source._get_source_manage_channel(vals)
            self._check_elearning_course_manage_access(channel)

    def _get_source_manage_channel(self, vals):
        self.ensure_one()
        if vals.get("slide_id"):
            slide = self.env["slide.slide"].browse(vals["slide_id"]).exists()
            return slide.channel_id
        if vals.get("channel_id"):
            return self.env["slide.channel"].browse(vals["channel_id"]).exists()
        if self.slide_id:
            return self.slide_id.channel_id
        return self.channel_id

    def _check_elearning_course_manage_access(self, channel):
        if self._is_ai_source_manager():
            return
        if channel and self._is_elearning_course_instructor(channel):
            return
        raise AccessError(_("You are not allowed to manage eLearning AI sources for this course."))

    def _is_ai_source_manager(self):
        return self.env.su or any(self.env.user.has_group(group) for group in AI_SOURCE_MANAGER_GROUPS)

    def _is_elearning_course_instructor(self, channel):
        if not self.env.user.has_group(AI_SOURCE_INSTRUCTOR_GROUP) or not channel:
            return False
        if channel.user_id == self.env.user:
            return True
        return bool(self.env["elearning.class"].sudo().search_count([
            ("trainer_ids", "in", [self.env.user.id]),
            ("state", "in", ("open", "running", "done")),
            "|",
            ("channel_id", "=", channel.id),
            ("program_id.line_ids.channel_id", "=", channel.id),
        ], limit=1))


class SlideChannel(models.Model):
    _inherit = "slide.channel"

    def action_create_ai_source_from_course(self):
        self.ensure_one()
        if not self.ai_agent_id:
            raise UserError(_("Set an AI Agent on the course before creating an eLearning AI source."))
        source = self.env["ai.agent.source"].create_from_elearning_courses([self.id], self.ai_agent_id.id)
        if not source:
            source = self.env["ai.agent.source"].search([
                ("type", "=", "elearning_course"),
                ("channel_id", "=", self.id),
                ("agent_id", "=", self.ai_agent_id.id),
            ], limit=1)
        return self._action_open_ai_source(source)

    def _action_open_ai_source(self, source):
        source.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("eLearning AI Source"),
            "res_model": "ai.agent.source",
            "view_mode": "form",
            "res_id": source.id,
        }


class SlideSlide(models.Model):
    _inherit = "slide.slide"

    def action_create_ai_source_from_slide(self):
        self.ensure_one()
        agent = self.channel_id.ai_agent_id
        if not agent:
            raise UserError(_("Set an AI Agent on the course before creating an eLearning AI source."))
        source = self.env["ai.agent.source"].create_from_elearning_slides([self.id], agent.id)
        if not source:
            source = self.ai_source_id
        return self.channel_id._action_open_ai_source(source)
