# -*- coding: utf-8 -*-

from odoo import fields, models, _
from odoo.exceptions import AccessError, UserError


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

    def action_generate_submission_feedback_draft(self):
        _check_ai_groups(self, _AI_TRAINING_GROUPS)
        _raise_ai_unavailable()


class ElearningQuestion(models.Model):
    _inherit = "elearning.question"

    def action_generate_question_ai_explanation(self):
        _check_ai_groups(self, _AI_TRAINING_GROUPS)
        _raise_ai_unavailable()
