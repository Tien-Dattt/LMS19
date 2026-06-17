# -*- coding: utf-8 -*-

import json
import re

from odoo import fields, models, _
from odoo.exceptions import UserError
from odoo.tools.mail import html_to_inner_content

from .ai_helpers import (
    AI_MANAGER_GROUPS,
    AI_TRAINING_GROUPS,
    _check_ai_manager_access,
    _get_lms_ai_generation_config,
    _has_ai_manager_access,
    _raise_ai_unavailable,
)

_AI_SYNC_SELECTION = [
    ("not_synced", "Not Synced"),
    ("synced", "Synced"),
    ("error", "Error"),
]


class ElearningProgram(models.Model):
    _inherit = "elearning.program"

    ai_agent_id = fields.Many2one(
        "ai.agent",
        string="AI Agent",
        help="AI Agent used to generate draft summaries for this learning program.",
    )
    ai_summary = fields.Html(
        string="AI Summary",
        help="Draft/helper summary. It must be reviewed before official use.",
    )

    def action_generate_program_ai_summary(self):
        _check_ai_manager_access(self, AI_MANAGER_GROUPS)
        for program in self:
            agent = program._get_program_ai_agent()
            prompt = program._build_program_summary_prompt()
            try:
                responses = agent._generate_response(
                    prompt=prompt,
                    extra_system_context=program._get_program_summary_system_prompt(),
                )
                ai_summary = program._parse_program_summary_ai_response("\n".join(responses or []))
            except UserError:
                raise
            except Exception as error:
                raise UserError(_(
                    "AI could not generate a program summary. Please check the selected AI Agent and try again. Details: %s"
                ) % error)
            program.sudo().write({"ai_summary": ai_summary})
        return True

    def _get_program_ai_agent(self):
        self.ensure_one()
        agent = self.ai_agent_id
        if not agent:
            raise UserError(_("Vui lòng chọn AI Agent cho chương trình trước khi tạo tóm tắt bằng AI."))
        if not agent.llm_model:
            raise UserError(_("AI Agent chưa được cấu hình mô hình hoặc nguồn dữ liệu hợp lệ."))
        if agent.restrict_to_sources:
            valid_sources = agent.sources_ids.filtered(lambda source: source.status == "indexed" and source.is_active)
            if not valid_sources:
                raise UserError(_("AI Agent chưa được cấu hình mô hình hoặc nguồn dữ liệu hợp lệ."))
        return agent.with_user(self.env.user)

    def _get_program_summary_system_prompt(self):
        return "\n".join([
            "You draft learning program helper content for an Odoo Corporate LMS training manager.",
            "Return a concise HTML summary with Vietnamese or valid JSON with an ai_summary key.",
            "The generated text is draft helper content only.",
            "Do not decide official score, pass/fail, certificates, permissions, or learner access.",
        ])

    def _build_program_summary_prompt(self):
        self.ensure_one()
        target_levels = ", ".join(self.target_level_ids.mapped("name")) or _("Not specified")
        target_role_tracks = ", ".join(self.target_role_track_ids.mapped("name")) or _("Not specified")
        parts = [
            _("Program: %s") % self.name,
            _("Code: %s") % (self.code or ""),
            _("Description: %s") % self._program_html_to_text(self.description),
            _("Target levels: %s") % target_levels,
            _("Target role tracks: %s") % target_role_tracks,
            _("Passing score: %s") % self.passing_score,
            "",
            _("Course lines:"),
        ]
        unlock_labels = dict(self.env["elearning.program.line"]._fields["unlock_policy"].selection)
        for line in self.line_ids.sorted(lambda item: (item.sequence, item.id)):
            channel = line.channel_id
            parts.append("- %s | %s | %s | %s=%s" % (
                channel.display_name,
                _("Mandatory") if line.mandatory else _("Optional"),
                unlock_labels.get(line.unlock_policy, line.unlock_policy),
                _("Weight"),
                line.weight,
            ))
            course_description = self._program_html_to_text(channel.description)
            if course_description:
                parts.append("  %s" % course_description)
        return "\n".join([
            "Generate a draft AI summary for this learning program.",
            "Use this JSON shape if possible:",
            '{"ai_summary":"..."}',
            "Do not change official completion, scoring, pass/fail, certificates, permissions, or learner access.",
            "",
            "\n".join(part for part in parts if part is not False),
        ])

    def _parse_program_summary_ai_response(self, raw_response):
        cleaned = (raw_response or "").strip()
        if not cleaned:
            raise UserError(_("AI returned an empty program summary response."))
        fence_match = re.search(r"```(?:json)?\s*(.*?)```", cleaned, flags=re.DOTALL | re.IGNORECASE)
        if fence_match:
            cleaned = fence_match.group(1).strip()
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            return cleaned
        if isinstance(payload, list):
            payload = payload[0] if payload else {}
        if not isinstance(payload, dict):
            raise UserError(_("AI response did not contain a program summary."))
        summary = payload.get("ai_summary") or payload.get("program_summary") or payload.get("summary")
        if not summary:
            raise UserError(_("AI response did not contain a program summary."))
        return str(summary)

    def _program_html_to_text(self, value):
        if not value:
            return ""
        return html_to_inner_content(value).strip()


class SlideChannel(models.Model):
    _inherit = "slide.channel"

    ai_agent_id = fields.Many2one(
        "ai.agent",
        string="AI Agent",
        help="Optional AI agent for draft/helper LMS content generation.",
    )
    ai_course_summary = fields.Html(
        string="AI Course Summary",
        help="Draft/helper course summary. It must be reviewed before official use.",
    )
    ai_difficulty_suggestion = fields.Char(
        string="AI Difficulty Suggestion",
        help="Draft/helper difficulty suggestion. It must be reviewed before official use.",
    )
    ai_sync_status = fields.Selection(
        _AI_SYNC_SELECTION,
        default="not_synced",
        string="AI Sync Status",
    )

    def action_generate_course_ai_summary(self):
        _check_ai_manager_access(self, AI_TRAINING_GROUPS)
        for channel in self:
            agent = channel.ai_agent_id
            if not agent:
                raise UserError(_("Set an AI Agent on the course before generating a course AI summary."))
            _get_lms_ai_generation_config(channel, agent)
            prompt = channel._build_course_summary_prompt()
            try:
                responses = agent.sudo()._generate_response(
                    prompt=prompt,
                    extra_system_context=channel._get_course_summary_system_prompt(),
                )
                values = channel._parse_course_summary_ai_response("\n".join(responses or []))
            except UserError:
                raise
            except Exception as error:
                raise UserError(_(
                    "AI could not generate a course summary. Please check the AI configuration and try again. Details: %s"
                ) % error)
            channel.sudo().write(values)
        return True

    def _get_course_summary_system_prompt(self):
        return "\n".join([
            "You draft course helper content for an Odoo Corporate LMS instructor.",
            "Return only valid JSON. Do not include Markdown fences or prose.",
            "The generated text is draft helper content only.",
            "Do not decide official score, pass/fail, certificates, permissions, or learner access.",
        ])

    def _build_course_summary_prompt(self):
        self.ensure_one()
        parts = [
            _("Course: %s") % self.name,
            self._course_field_text("description_short"),
            self._course_field_text("description"),
            self._course_field_text("description_html"),
        ]
        slide_field = "slide_content_ids" if "slide_content_ids" in self._fields else "slide_ids"
        for slide in self[slide_field].filtered(lambda item: not item.is_category and item.is_published):
            slide_parts = [
                _("Slide: %s") % slide.name,
                self._record_field_text(slide, "description"),
                self._record_field_text(slide, "html_content"),
            ]
            parts.append("\n".join(part for part in slide_parts if part))
        return "\n".join([
            "Generate draft helper fields for this course.",
            "Use this JSON shape exactly:",
            '{"ai_course_summary":"...","ai_difficulty_suggestion":"..."}',
            "Do not change official completion, scoring, pass/fail, certificates, permissions, or learner access.",
            "",
            "\n\n".join(part for part in parts if part),
        ])

    def _parse_course_summary_ai_response(self, raw_response):
        cleaned = (raw_response or "").strip()
        if not cleaned:
            raise UserError(_("AI returned an empty course summary response."))
        fence_match = re.search(r"```(?:json)?\s*(.*?)```", cleaned, flags=re.DOTALL | re.IGNORECASE)
        if fence_match:
            cleaned = fence_match.group(1).strip()
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            payload = {"ai_course_summary": cleaned}
        if isinstance(payload, list):
            payload = payload[0] if payload else {}
        if not isinstance(payload, dict):
            raise UserError(_("AI response did not contain a course summary."))

        summary = payload.get("ai_course_summary") or payload.get("course_summary") or payload.get("summary")
        difficulty = (
            payload.get("ai_difficulty_suggestion")
            or payload.get("difficulty_suggestion")
            or payload.get("difficulty")
        )
        if not summary:
            raise UserError(_("AI response did not contain a course summary."))

        values = {"ai_course_summary": str(summary)}
        if difficulty:
            values["ai_difficulty_suggestion"] = str(difficulty)
        return values

    def _course_field_text(self, field_name):
        return self._record_field_text(self, field_name)

    def _record_field_text(self, record, field_name):
        if field_name not in record._fields or not record[field_name]:
            return ""
        field = record._fields[field_name]
        if field.type == "html":
            return html_to_inner_content(record[field_name]).strip()
        if field.type in ("char", "text"):
            return str(record[field_name]).strip()
        return ""


class SlideSlide(models.Model):
    _inherit = "slide.slide"

    ai_summary = fields.Html(
        string="AI Summary",
        help="Draft/helper lesson summary. It must be reviewed before official use.",
    )
    ai_keywords = fields.Char(
        string="AI Keywords",
        help="Draft/helper keywords. They must be reviewed before official use.",
    )
    ai_source_id = fields.Many2one(
        "ai.agent.source",
        string="AI Source",
        help="Optional AI source reference for later LMS source bridge workflows.",
    )
    ai_sync_status = fields.Selection(
        _AI_SYNC_SELECTION,
        default="not_synced",
        string="AI Sync Status",
    )

    def action_generate_slide_ai_summary(self):
        _check_ai_manager_access(self, AI_TRAINING_GROUPS)
        _raise_ai_unavailable()


class ElearningAssignmentSubmission(models.Model):
    _inherit = "elearning.assignment.submission"

    def action_generate_ai_feedback_draft(self):
        _check_ai_manager_access(self, AI_TRAINING_GROUPS)
        for submission in self:
            is_ai_manager = _has_ai_manager_access(submission.env, AI_MANAGER_GROUPS)
            if not is_ai_manager:
                submission.check_access("write")
            work_submission = submission.sudo() if is_ai_manager else submission
            agent = work_submission._get_feedback_ai_agent()
            _get_lms_ai_generation_config(work_submission, agent)
            prompt = work_submission._build_feedback_prompt()
            try:
                responses = agent._generate_response(
                    prompt=prompt,
                    extra_system_context=work_submission._get_feedback_system_prompt(),
                )
                values = work_submission._parse_feedback_ai_response("\n".join(responses or []))
            except UserError:
                raise
            except Exception as error:
                raise UserError(_(
                    "AI could not generate a feedback draft. Please check the AI configuration and try again. Details: %s"
                ) % error)
            work_submission.write(values)
        return True

    def action_generate_submission_feedback_draft(self):
        return self.action_generate_ai_feedback_draft()

    def action_copy_ai_feedback_to_feedback(self):
        _check_ai_manager_access(self, AI_TRAINING_GROUPS)
        for submission in self:
            is_ai_manager = _has_ai_manager_access(submission.env, AI_MANAGER_GROUPS)
            if not is_ai_manager:
                submission.check_access("write")
            work_submission = submission.sudo() if is_ai_manager else submission
            if not work_submission.ai_feedback_draft:
                raise UserError(_("Generate an AI feedback draft before copying it to official feedback."))
            work_submission.write({"feedback": work_submission.ai_feedback_draft})
        return True

    def _get_feedback_ai_agent(self):
        self.ensure_one()
        assignment = self.assignment_id
        agent = assignment.channel_id.ai_agent_id
        if not agent and assignment.class_id.channel_id:
            agent = assignment.class_id.channel_id.ai_agent_id
        if not agent and assignment.program_id:
            channel = assignment.program_id.line_ids.mapped("channel_id").filtered("ai_agent_id")[:1]
            agent = channel.ai_agent_id
        if not agent:
            raise UserError(_("Set an AI Agent on the related course before generating feedback drafts."))
        return agent.sudo()

    def _get_feedback_system_prompt(self):
        return "\n".join([
            "You draft assignment feedback for an Odoo Corporate LMS instructor.",
            "Return only valid JSON. Do not include Markdown fences or prose.",
            "The generated text is draft helper content only.",
            "Do not decide official score, pass/fail, certificates, permissions, or learner access.",
        ])

    def _build_feedback_prompt(self):
        self.ensure_one()
        assignment = self.assignment_id
        return "\n".join([
            "Draft assignment feedback from the submission context.",
            "Use this JSON shape exactly:",
            '{"ai_feedback_draft":"...","ai_strengths":"...","ai_weaknesses":"..."}',
            "Do not provide an official score.",
            "",
            "Assignment:",
            self._assignment_context(assignment),
            "",
            "Rubric:",
            self._rubric_context(assignment.rubric_id),
            "",
            "Learner submission:",
            self._submission_context(),
        ])

    def _assignment_context(self, assignment):
        return "\n".join(part for part in [
            _("Name: %s") % (assignment.name or ""),
            _("Description: %s") % self._html_to_text(assignment.description),
            _("Maximum score: %s") % assignment.max_score,
        ] if part)

    def _rubric_context(self, rubric):
        if not rubric:
            return _("No rubric configured.")
        parts = [
            _("Rubric: %s") % rubric.name,
            _("Description: %s") % self._html_to_text(rubric.description),
            _("Maximum score: %s") % rubric.max_score,
        ]
        for criteria in rubric.criteria_ids.sorted(lambda item: (item.sequence, item.id)):
            parts.append("%s (%s): %s" % (
                criteria.name,
                criteria.max_score,
                criteria.description or "",
            ))
        return "\n".join(part for part in parts if part)

    def _submission_context(self):
        self.ensure_one()
        parts = [
            _("Learner: %s") % self.partner_id.display_name,
            _("State: %s") % dict(self._fields["state"].selection).get(self.state, self.state),
            _("Text answer: %s") % self._html_to_text(self.text_answer),
        ]
        if self.external_url:
            parts.append(_("External URL: %s") % self.external_url)
        attachments = self._attachment_metadata_context()
        if attachments:
            parts.append(_("Attachments metadata:"))
            parts.extend(attachments)
        return "\n".join(part for part in parts if part)

    def _attachment_metadata_context(self):
        self.ensure_one()
        lines = []
        for attachment in self.attachment_ids.sudo():
            metadata = [
                _("name=%s") % attachment.name,
            ]
            if "mimetype" in attachment._fields and attachment.mimetype:
                metadata.append(_("mimetype=%s") % attachment.mimetype)
            if "file_size" in attachment._fields and attachment.file_size:
                metadata.append(_("file_size=%s") % attachment.file_size)
            if "url" in attachment._fields and attachment.url:
                metadata.append(_("url=%s") % attachment.url)
            lines.append("- " + ", ".join(metadata))
        return lines

    def _html_to_text(self, value):
        if not value:
            return ""
        return html_to_inner_content(value).strip()

    def _parse_feedback_ai_response(self, raw_response):
        payload = self._json_loads_feedback_response(raw_response)
        if isinstance(payload, list):
            payload = payload[0] if payload else {}
        if not isinstance(payload, dict):
            raise UserError(_("AI response did not contain feedback fields."))

        feedback = payload.get("ai_feedback_draft") or payload.get("feedback_draft") or payload.get("feedback")
        strengths = payload.get("ai_strengths") or payload.get("strengths") or ""
        weaknesses = payload.get("ai_weaknesses") or payload.get("weaknesses") or ""
        if not feedback:
            raise UserError(_("AI response did not contain a feedback draft."))

        return {
            "ai_feedback_draft": str(feedback),
            "ai_strengths": str(strengths),
            "ai_weaknesses": str(weaknesses),
        }

    def _json_loads_feedback_response(self, raw_response):
        cleaned = (raw_response or "").strip()
        if not cleaned:
            raise UserError(_("AI returned an empty feedback draft response."))
        fence_match = re.search(r"```(?:json)?\s*(.*?)```", cleaned, flags=re.DOTALL | re.IGNORECASE)
        if fence_match:
            cleaned = fence_match.group(1).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as error:
            raise UserError(_("AI returned malformed feedback draft JSON: %s") % error)


class ElearningQuestion(models.Model):
    _inherit = "elearning.question"

    def action_generate_question_ai_explanation(self):
        _check_ai_manager_access(self, AI_TRAINING_GROUPS)
        _raise_ai_unavailable()
