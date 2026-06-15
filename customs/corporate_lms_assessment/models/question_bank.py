# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


_ANSWER_REVIEW_GROUPS = (
    "corporate_lms_base.group_corporate_lms_admin,"
    "corporate_lms_base.group_corporate_lms_training_manager,"
    "corporate_lms_base.group_corporate_lms_instructor"
)
_SINGLE_ANSWER_TYPES = ("single", "single_choice", "true_false")
_MULTIPLE_ANSWER_TYPES = ("multiple", "multiple_choice")


class ElearningQuestionBank(models.Model):
    _name = "elearning.question.bank"
    _description = "Question Bank"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name, id"

    name = fields.Char(required=True, tracking=True, translate=True)
    description = fields.Text(translate=True)
    owner_id = fields.Many2one(
        "res.users",
        default=lambda self: self.env.user,
        required=True,
        ondelete="restrict",
        tracking=True,
    )
    program_id = fields.Many2one(
        "elearning.program",
        ondelete="restrict",
        tracking=True,
    )
    channel_id = fields.Many2one(
        "slide.channel",
        string="Course",
        ondelete="restrict",
        tracking=True,
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("active", "Active"),
            ("archived", "Archived"),
        ],
        default="draft",
        required=True,
        tracking=True,
    )
    question_ids = fields.One2many(
        "elearning.question",
        "bank_id",
        string="Questions",
        copy=True,
    )
    exam_ids = fields.One2many(
        "elearning.exam",
        "question_bank_id",
        string="Exams",
        copy=False,
    )
    active = fields.Boolean(default=True)

    def action_activate(self):
        self.write({"state": "active"})
        return True

    def action_archive(self):
        self.write({"state": "archived"})
        return True


class ElearningQuestion(models.Model):
    _name = "elearning.question"
    _description = "Question"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "bank_id, id"

    bank_id = fields.Many2one(
        "elearning.question.bank",
        required=True,
        ondelete="cascade",
        index=True,
        tracking=True,
    )
    name = fields.Text(required=True, translate=True)
    question_type = fields.Selection(
        [
            ("single", "Single Choice"),
            ("multiple", "Multiple Choice"),
            ("true_false", "True/False"),
        ],
        default="single",
        required=True,
        tracking=True,
    )
    difficulty = fields.Selection(
        [
            ("easy", "Easy"),
            ("medium", "Medium"),
            ("hard", "Hard"),
        ],
        default="medium",
        required=True,
        tracking=True,
    )
    score = fields.Float(default=1.0, required=True, tracking=True)
    ai_explanation = fields.Html(string="AI Explanation")
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("active", "Active"),
            ("archived", "Archived"),
        ],
        default="draft",
        required=True,
        tracking=True,
    )
    answer_ids = fields.One2many(
        "elearning.answer",
        "question_id",
        string="Answers",
        copy=True,
    )
    active = fields.Boolean(default=True)

    @api.model_create_multi
    def create(self, vals_list):
        questions = super(
            ElearningQuestion,
            self.with_context(corporate_lms_skip_question_answer_check=True),
        ).create(vals_list)
        questions._check_active_choice_questions_have_correct_answer()
        return questions

    def write(self, vals):
        if "answer_ids" in vals:
            result = super(
                ElearningQuestion,
                self.with_context(corporate_lms_skip_question_answer_check=True),
            ).write(vals)
        else:
            result = super().write(vals)
        if {"state", "question_type", "answer_ids"}.intersection(vals):
            self._check_active_choice_questions_have_correct_answer()
        if "score" in vals:
            self._check_score()
        return result

    def action_activate(self):
        self.write({"state": "active"})
        return True

    def action_archive(self):
        self.write({"state": "archived"})
        return True

    @api.constrains("score")
    def _check_score(self):
        for question in self:
            if question.score < 0:
                raise ValidationError(_("Question score must be zero or greater."))

    @api.constrains("state", "question_type", "answer_ids")
    def _check_active_choice_questions_have_correct_answer(self):
        for question in self:
            if question.state != "active":
                continue
            correct_answers = question.answer_ids.filtered("is_correct")
            if not correct_answers:
                raise ValidationError(_("An active choice question must have a correct answer."))
            if question.question_type in _SINGLE_ANSWER_TYPES and len(correct_answers) != 1:
                raise ValidationError(_("Single choice and true/false questions must have exactly one correct answer."))


class ElearningAnswer(models.Model):
    _name = "elearning.answer"
    _description = "Answer"
    _order = "question_id, sequence, id"

    question_id = fields.Many2one(
        "elearning.question",
        required=True,
        ondelete="cascade",
        index=True,
    )
    name = fields.Char(required=True, translate=True)
    is_correct = fields.Boolean(groups=_ANSWER_REVIEW_GROUPS)
    sequence = fields.Integer(default=10)
    feedback = fields.Text(translate=True, groups=_ANSWER_REVIEW_GROUPS)

    @api.model_create_multi
    def create(self, vals_list):
        answers = super().create(vals_list)
        if not self.env.context.get("corporate_lms_skip_question_answer_check"):
            answers.mapped("question_id")._check_active_choice_questions_have_correct_answer()
        return answers

    def write(self, vals):
        questions = self.mapped("question_id")
        result = super().write(vals)
        if (
            not self.env.context.get("corporate_lms_skip_question_answer_check")
            and {"question_id", "is_correct"}.intersection(vals)
        ):
            (questions | self.mapped("question_id"))._check_active_choice_questions_have_correct_answer()
        return result

    def unlink(self):
        questions = self.mapped("question_id")
        result = super().unlink()
        if not self.env.context.get("corporate_lms_skip_question_answer_check"):
            questions._check_active_choice_questions_have_correct_answer()
        return result
