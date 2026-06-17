# -*- coding: utf-8 -*-

import json
import re

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.mail import html_to_inner_content

from odoo.addons.corporate_lms_ai.models.ai_helpers import (
    AI_MANAGER_GROUPS,
    AI_TRAINING_GROUPS,
    _check_ai_manager_access,
    _get_lms_ai_generation_config,
    _has_ai_manager_access,
)

QUESTION_TYPES = {"single", "multiple", "true_false"}
DIFFICULTIES = {"easy", "medium", "hard"}


class ElearningAIGenerateQuestionWizard(models.TransientModel):
    _name = "elearning.ai.generate.question.wizard"
    _description = "Generate Draft Questions by AI"

    source_type = fields.Selection(
        [
            ("course", "Course"),
            ("slide", "Slide"),
        ],
        default="course",
        required=True,
    )
    channel_id = fields.Many2one("slide.channel", string="Course")
    slide_id = fields.Many2one("slide.slide", string="Slide")
    question_bank_id = fields.Many2one(
        "elearning.question.bank",
        string="Question Bank",
        required=True,
        ondelete="cascade",
    )
    question_count = fields.Integer(default=5, required=True)
    difficulty = fields.Selection(
        [
            ("easy", "Easy"),
            ("medium", "Medium"),
            ("hard", "Hard"),
        ],
        default="medium",
    )

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        if self.env.context.get("active_model") == "elearning.question.bank" and self.env.context.get("active_id"):
            bank = self.env["elearning.question.bank"].browse(self.env.context["active_id"])
            values.setdefault("question_bank_id", bank.id)
            if bank.channel_id:
                values.setdefault("channel_id", bank.channel_id.id)
                values.setdefault("source_type", "course")
        return values

    @api.constrains("question_count")
    def _check_question_count(self):
        for wizard in self:
            if wizard.question_count <= 0:
                raise ValidationError(_("Question count must be greater than zero."))

    @api.constrains("source_type", "channel_id", "slide_id")
    def _check_source(self):
        for wizard in self:
            if wizard.source_type == "course" and not wizard.channel_id:
                raise ValidationError(_("Select a course to generate draft questions."))
            if wizard.source_type == "slide" and not wizard.slide_id:
                raise ValidationError(_("Select a slide to generate draft questions."))

    def action_generate_draft_questions(self):
        self.ensure_one()
        self._check_instructor_permission()
        is_ai_manager = _has_ai_manager_access(self.env, AI_MANAGER_GROUPS)
        if not is_ai_manager:
            self.question_bank_id.check_access("write")
        self._check_source_permission()

        source_context = self._get_source_context()
        agent = self._get_ai_agent()
        _get_lms_ai_generation_config(self, agent)
        prompt = self._build_prompt(source_context)
        try:
            responses = agent._generate_response(
                prompt=prompt,
                extra_system_context=self._get_system_prompt(),
            )
            generated_questions = self._parse_ai_questions("\n".join(responses or []))
        except UserError:
            raise
        except Exception as error:
            raise UserError(_(
                "AI could not generate draft questions. Please check the AI configuration and try again. Details: %s"
            ) % error)

        if not generated_questions:
            raise UserError(_("AI did not return any usable draft questions."))

        Question = self.env["elearning.question"].sudo() if is_ai_manager else self.env["elearning.question"]
        created_questions = Question.browse()
        for question_values in generated_questions[: self.question_count]:
            created_questions |= Question.create({
                "bank_id": self.question_bank_id.id,
                "name": question_values["name"],
                "question_type": question_values["question_type"],
                "difficulty": question_values["difficulty"],
                "score": question_values["score"],
                "state": "draft",
                "answer_ids": [
                    (0, 0, {
                        "name": answer["name"],
                        "is_correct": answer["is_correct"],
                        "feedback": answer.get("feedback"),
                        "sequence": index * 10,
                    })
                    for index, answer in enumerate(question_values["answers"], start=1)
                ],
            })

        return {
            "type": "ir.actions.act_window",
            "name": _("Draft Questions"),
            "res_model": "elearning.question",
            "view_mode": "list,form",
            "domain": [("id", "in", created_questions.ids)],
            "context": {"default_bank_id": self.question_bank_id.id},
        }

    def _check_instructor_permission(self):
        _check_ai_manager_access(
            self,
            AI_TRAINING_GROUPS,
            "Only LMS instructors or training managers can generate AI draft questions.",
        )

    def _get_source_context(self):
        self.ensure_one()
        if self.source_type == "slide":
            slide = self.slide_id.sudo()
            return "\n\n".join(part for part in [
                _("Slide: %s") % slide.name,
                self._field_text(slide, "description"),
                self._field_text(slide, "html_content"),
                self._field_text(slide, "url"),
            ] if part)

        channel = self.channel_id.sudo()
        parts = [
            _("Course: %s") % channel.name,
            self._field_text(channel, "description_short"),
            self._field_text(channel, "description"),
            self._field_text(channel, "description_html"),
        ]
        slides = channel.slide_content_ids.filtered(lambda slide: not slide.is_category and slide.is_published)
        for slide in slides:
            slide_content = "\n\n".join(part for part in [
                _("Slide: %s") % slide.name,
                self._field_text(slide, "description"),
                self._field_text(slide, "html_content"),
            ] if part)
            if slide_content:
                parts.append(slide_content)
        return "\n\n".join(part for part in parts if part)

    def _field_text(self, record, field_name):
        if field_name not in record._fields or not record[field_name]:
            return ""
        field = record._fields[field_name]
        if field.type == "html":
            return html_to_inner_content(record[field_name])
        if field.type in ("char", "text"):
            return str(record[field_name])
        return ""

    def _get_ai_agent(self):
        self.ensure_one()
        channel = (self.slide_id.channel_id if self.source_type == "slide" else self.channel_id).sudo()
        agent = channel.ai_agent_id
        if not agent:
            raise UserError(_("Set an AI Agent on the selected course before generating draft questions."))
        return agent

    def _check_source_permission(self):
        self.ensure_one()
        if _has_ai_manager_access(self.env, AI_MANAGER_GROUPS):
            return

        channel = self.slide_id.channel_id if self.source_type == "slide" else self.channel_id
        bank_channel = self.question_bank_id.channel_id
        if self.question_bank_id.owner_id == self.env.user and (not bank_channel or bank_channel == channel):
            return
        if channel.user_id == self.env.user:
            return
        assigned_class = self.env["elearning.class"].sudo().search_count([
            ("trainer_ids", "in", [self.env.user.id]),
            ("state", "in", ("open", "running", "done")),
            "|",
            ("channel_id", "=", channel.id),
            ("program_id.line_ids.channel_id", "=", channel.id),
        ], limit=1)
        if assigned_class:
            return

        raise AccessError(_("You are not allowed to use this course or slide as AI question context."))

    def _get_system_prompt(self):
        return "\n".join([
            "You generate draft assessment questions for an Odoo Corporate LMS instructor.",
            "Return only valid JSON. Do not include Markdown fences or prose.",
            "Questions are draft helper content. They are not official until reviewed by the instructor.",
        ])

    def _build_prompt(self, source_context):
        self.ensure_one()
        difficulty = self.difficulty or "medium"
        return "\n".join([
            "Create draft LMS assessment questions from the source context.",
            f"Requested question count: {self.question_count}",
            f"Requested difficulty: {difficulty}",
            "Use this JSON shape exactly:",
            '{"questions":[{"question":"...","question_type":"single","difficulty":"medium","score":1.0,'
            '"answers":[{"answer":"...","is_correct":true,"feedback":"..."},{"answer":"...","is_correct":false}]}]}',
            "Allowed question_type values: single, multiple, true_false.",
            "Each question must have at least two answers and at least one correct answer.",
            "For single and true_false questions, exactly one answer must be correct.",
            "Source context:",
            source_context or _("No source text was available."),
        ])

    def _parse_ai_questions(self, raw_response):
        payload = self._json_loads_ai_response(raw_response)
        raw_questions = payload.get("questions") if isinstance(payload, dict) else payload
        if not isinstance(raw_questions, list):
            raise UserError(_("AI response did not contain a questions list."))

        questions = []
        for raw_question in raw_questions:
            question = self._normalize_ai_question(raw_question)
            if question:
                questions.append(question)
        return questions

    def _json_loads_ai_response(self, raw_response):
        cleaned = (raw_response or "").strip()
        if not cleaned:
            raise UserError(_("AI returned an empty response."))
        fence_match = re.search(r"```(?:json)?\s*(.*?)```", cleaned, flags=re.DOTALL | re.IGNORECASE)
        if fence_match:
            cleaned = fence_match.group(1).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as error:
            raise UserError(_("AI returned malformed JSON: %s") % error)

    def _normalize_ai_question(self, raw_question):
        if not isinstance(raw_question, dict):
            raise UserError(_("AI returned an invalid question item."))

        name = raw_question.get("question") or raw_question.get("name") or raw_question.get("text")
        if not name:
            raise UserError(_("AI returned a question without text."))

        question_type = self._normalize_question_type(raw_question.get("question_type") or raw_question.get("type"))
        difficulty = raw_question.get("difficulty") or self.difficulty or "medium"
        if difficulty not in DIFFICULTIES:
            difficulty = self.difficulty or "medium"

        try:
            score = float(raw_question.get("score") or 1.0)
        except (TypeError, ValueError):
            score = 1.0
        if score <= 0:
            score = 1.0

        answers = self._normalize_ai_answers(raw_question.get("answers") or raw_question.get("options") or [])
        correct_answers = [answer for answer in answers if answer["is_correct"]]
        if not correct_answers:
            raise UserError(_("AI returned a question without a correct answer."))
        if question_type in ("single", "true_false") and len(correct_answers) != 1:
            raise UserError(_("AI returned a single choice or true/false question with multiple correct answers."))

        return {
            "name": name,
            "question_type": question_type,
            "difficulty": difficulty,
            "score": score,
            "answers": answers,
        }

    def _normalize_question_type(self, value):
        mapping = {
            "single_choice": "single",
            "multiple_choice": "multiple",
            "truefalse": "true_false",
            "true/false": "true_false",
        }
        question_type = mapping.get(value, value or "single")
        if question_type not in QUESTION_TYPES:
            question_type = "single"
        return question_type

    def _normalize_ai_answers(self, raw_answers):
        if not isinstance(raw_answers, list) or len(raw_answers) < 2:
            raise UserError(_("AI returned a question with fewer than two answers."))

        answers = []
        for raw_answer in raw_answers:
            if isinstance(raw_answer, str):
                answers.append({"name": raw_answer, "is_correct": False})
                continue
            if not isinstance(raw_answer, dict):
                raise UserError(_("AI returned an invalid answer item."))
            name = raw_answer.get("answer") or raw_answer.get("name") or raw_answer.get("text")
            if not name:
                raise UserError(_("AI returned an answer without text."))
            answers.append({
                "name": name,
                "is_correct": bool(raw_answer.get("is_correct", raw_answer.get("correct", False))),
                "feedback": raw_answer.get("feedback"),
            })
        return answers


class ElearningQuestionBank(models.Model):
    _inherit = "elearning.question.bank"

    def action_open_ai_generate_question_wizard(self):
        self.ensure_one()
        _check_ai_manager_access(
            self,
            AI_TRAINING_GROUPS,
            "Only LMS instructors or training managers can generate AI draft questions.",
        )
        if not _has_ai_manager_access(self.env, AI_MANAGER_GROUPS):
            self.check_access("write")
        return {
            "type": "ir.actions.act_window",
            "name": _("Generate Draft Questions by AI"),
            "res_model": "elearning.ai.generate.question.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_question_bank_id": self.id,
                "default_channel_id": self.channel_id.id,
                "default_source_type": "course",
            },
        }
