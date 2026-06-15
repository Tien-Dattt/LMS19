# -*- coding: utf-8 -*-

import json
import re

from odoo import fields, models, _
from odoo.exceptions import AccessError, UserError
from odoo.tools.mail import html_to_inner_content


_AI_TRAINING_GROUPS = (
    "corporate_lms_base.group_corporate_lms_admin",
    "corporate_lms_base.group_corporate_lms_training_manager",
    "corporate_lms_base.group_corporate_lms_instructor",
)
_AI_MANAGER_GROUPS = (
    "corporate_lms_base.group_corporate_lms_admin",
    "corporate_lms_base.group_corporate_lms_training_manager",
)
_AI_SYNC_SELECTION = [
    ("not_synced", "Not Synced"),
    ("synced", "Synced"),
    ("error", "Error"),
]


def _check_ai_groups(record, groups):
    if record.env.su:
        return
    if not any(record.env.user.has_group(group) for group in groups):
        raise AccessError(_("You are not allowed to run Corporate LMS AI actions."))


def _raise_ai_unavailable():
    raise UserError(_("AI generation is not configured for Corporate LMS yet. The existing draft fields were left unchanged."))


class ElearningProgram(models.Model):
    _inherit = "elearning.program"

    ai_summary = fields.Html(
        string="AI Summary",
        help="Draft/helper summary. It must be reviewed before official use.",
    )

    def action_generate_program_ai_summary(self):
        _check_ai_groups(self, _AI_MANAGER_GROUPS)
        _raise_ai_unavailable()


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
        _check_ai_groups(self, _AI_TRAINING_GROUPS)
        _raise_ai_unavailable()


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
        _check_ai_groups(self, _AI_TRAINING_GROUPS)
        _raise_ai_unavailable()


class ElearningAssignmentSubmission(models.Model):
    _inherit = "elearning.assignment.submission"

    def action_generate_ai_feedback_draft(self):
        _check_ai_groups(self, _AI_TRAINING_GROUPS)
        for submission in self:
            submission.check_access("write")
            agent = submission._get_feedback_ai_agent()
            prompt = submission._build_feedback_prompt()
            try:
                responses = agent._generate_response(
                    prompt=prompt,
                    extra_system_context=submission._get_feedback_system_prompt(),
                )
                values = submission._parse_feedback_ai_response("\n".join(responses or []))
            except UserError:
                raise
            except Exception as error:
                raise UserError(_(
                    "AI could not generate a feedback draft. Please check the AI configuration and try again. Details: %s"
                ) % error)
            submission.write(values)
        return True

    def action_generate_submission_feedback_draft(self):
        return self.action_generate_ai_feedback_draft()

    def action_copy_ai_feedback_to_feedback(self):
        _check_ai_groups(self, _AI_TRAINING_GROUPS)
        for submission in self:
            submission.check_access("write")
            if not submission.ai_feedback_draft:
                raise UserError(_("Generate an AI feedback draft before copying it to official feedback."))
            submission.write({"feedback": submission.ai_feedback_draft})
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
        _check_ai_groups(self, _AI_TRAINING_GROUPS)
        _raise_ai_unavailable()
