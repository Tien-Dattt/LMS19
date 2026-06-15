# -*- coding: utf-8 -*-

from random import sample

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError


class ElearningExam(models.Model):
    _name = "elearning.exam"
    _description = "Exam"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name, id"

    name = fields.Char(required=True, tracking=True, translate=True)
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
    class_id = fields.Many2one(
        "elearning.class",
        string="Class",
        ondelete="restrict",
        tracking=True,
    )
    question_bank_id = fields.Many2one(
        "elearning.question.bank",
        required=True,
        ondelete="restrict",
        tracking=True,
    )
    question_count = fields.Integer(default=1, required=True, tracking=True)
    randomize_questions = fields.Boolean(default=True, tracking=True)
    randomize_answers = fields.Boolean(default=True, tracking=True)
    time_limit_minutes = fields.Integer(tracking=True)
    attempt_limit = fields.Integer(default=1, required=True, tracking=True)
    passing_score = fields.Float(default=70.0, required=True, tracking=True)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("published", "Published"),
            ("closed", "Closed"),
        ],
        default="draft",
        required=True,
        tracking=True,
    )
    session_ids = fields.One2many(
        "elearning.exam.session",
        "exam_id",
        string="Sessions",
        copy=False,
    )
    active = fields.Boolean(default=True)

    @api.model_create_multi
    def create(self, vals_list):
        exams = super().create(vals_list)
        exams._check_learning_scope()
        exams._check_numeric_values()
        exams.filtered(lambda exam: exam.state == "published")._check_exam_ready()
        return exams

    def write(self, vals):
        result = super().write(vals)
        if {"program_id", "channel_id", "class_id"}.intersection(vals):
            self._check_learning_scope()
        if {"question_count", "time_limit_minutes", "attempt_limit", "passing_score"}.intersection(vals):
            self._check_numeric_values()
        if {"state", "question_bank_id", "question_count"}.intersection(vals):
            self.filtered(lambda exam: exam.state == "published")._check_exam_ready()
        return result

    def action_publish(self):
        self._check_exam_ready()
        self.write({"state": "published"})
        return True

    def action_close(self):
        self.write({"state": "closed"})
        return True

    def action_start_session(self):
        self.ensure_one()
        self.check_access("read")
        self._check_start_allowed(self.env.user.partner_id)
        questions = self._get_session_questions()
        employee = self._get_employee_for_partner(self.env.user.partner_id)
        session = self.env["elearning.exam.session"].sudo().create({
            "exam_id": self.id,
            "partner_id": self.env.user.partner_id.id,
            "employee_id": employee.id if employee else False,
            "line_ids": [(0, 0, {"question_id": question.id}) for question in questions],
        })
        return session.with_user(self.env.user)

    def action_start_exam(self):
        return self.action_start_session()

    @api.constrains("program_id", "channel_id", "class_id")
    def _check_learning_scope(self):
        for exam in self:
            if not exam.program_id and not exam.channel_id and not exam.class_id:
                raise ValidationError(_("An exam must belong to at least a program, course, or class."))

    @api.constrains("question_count", "time_limit_minutes", "attempt_limit", "passing_score")
    def _check_numeric_values(self):
        for exam in self:
            if exam.question_count < 0:
                raise ValidationError(_("Question count must be zero or greater."))
            if exam.time_limit_minutes < 0:
                raise ValidationError(_("Time limit must be zero or greater."))
            if exam.attempt_limit < 0:
                raise ValidationError(_("Attempt limit must be zero or greater."))
            if exam.passing_score < 0:
                raise ValidationError(_("Passing score must be zero or greater."))

    def _check_exam_ready(self):
        for exam in self:
            if exam.question_bank_id.state != "active":
                raise ValidationError(_("A published exam must use an active question bank."))
            active_questions = exam.question_bank_id.question_ids.filtered(lambda question: question.state == "active")
            if not active_questions:
                raise ValidationError(_("A published exam must have active questions."))
            if exam.question_count and len(active_questions) < exam.question_count:
                raise ValidationError(_("Question count cannot exceed the active questions in the bank."))

    def _check_start_allowed(self, partner):
        self.ensure_one()
        if self.state != "published":
            raise ValidationError(_("Learners can only start published exams."))
        self._check_exam_ready()
        self._check_attempt_limit(partner)

    def _check_attempt_limit(self, partner):
        self.ensure_one()
        if not self.attempt_limit or not partner:
            return
        attempt_count = self.env["elearning.exam.session"].sudo().search_count([
            ("exam_id", "=", self.id),
            ("partner_id", "=", partner.id),
        ])
        if attempt_count >= self.attempt_limit:
            raise ValidationError(_("This learner has reached the attempt limit for this exam."))

    def _get_session_questions(self):
        self.ensure_one()
        active_questions = self.question_bank_id.question_ids.filtered(lambda question: question.state == "active")
        question_count = self.question_count or len(active_questions)
        if question_count > len(active_questions):
            raise ValidationError(_("Question count cannot exceed the active questions in the bank."))
        question_ids = active_questions.ids
        if self.randomize_questions:
            question_ids = sample(question_ids, question_count)
        else:
            question_ids = question_ids[:question_count]
        return self.env["elearning.question"].browse(question_ids)

    def _get_employee_for_partner(self, partner):
        if not partner:
            return self.env["hr.employee"]
        return self.env["hr.employee"].sudo().search([
            ("user_id.partner_id", "=", partner.id),
        ], limit=1)


class ElearningExamSession(models.Model):
    _name = "elearning.exam.session"
    _description = "Exam Session"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "started_at desc, id desc"

    exam_id = fields.Many2one(
        "elearning.exam",
        required=True,
        ondelete="cascade",
        index=True,
        tracking=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        required=True,
        ondelete="cascade",
        index=True,
        tracking=True,
    )
    employee_id = fields.Many2one(
        "hr.employee",
        ondelete="set null",
        index=True,
        tracking=True,
    )
    exam_program_id = fields.Many2one(
        "elearning.program",
        related="exam_id.program_id",
        store=True,
        readonly=True,
        string="Program",
    )
    exam_channel_id = fields.Many2one(
        "slide.channel",
        related="exam_id.channel_id",
        store=True,
        readonly=True,
        string="Course",
    )
    exam_class_id = fields.Many2one(
        "elearning.class",
        related="exam_id.class_id",
        store=True,
        readonly=True,
        string="Class",
    )
    started_at = fields.Datetime(
        default=fields.Datetime.now,
        required=True,
        readonly=True,
        tracking=True,
    )
    submitted_at = fields.Datetime(readonly=True, tracking=True)
    state = fields.Selection(
        [
            ("in_progress", "In Progress"),
            ("submitted", "Submitted"),
            ("graded", "Graded"),
            ("expired", "Expired"),
        ],
        default="in_progress",
        required=True,
        tracking=True,
    )
    score = fields.Float(readonly=True, tracking=True)
    passed = fields.Boolean(readonly=True, tracking=True)
    line_ids = fields.One2many(
        "elearning.exam.session.line",
        "session_id",
        string="Answers",
        copy=False,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._prepare_session_values(vals)
            self._check_session_create_allowed(vals)
        sessions = super().create(vals_list)
        for session in sessions.filtered(lambda item: not item.line_ids):
            session.sudo()._generate_session_lines()
        return sessions

    def write(self, vals):
        self._check_learner_write_access(vals)
        return super().write(vals)

    def action_submit(self):
        for session in self:
            session._check_submit_allowed()
            session.line_ids._check_selected_answers_match_question()
            total_score = 0.0
            for line in session.line_ids.sudo():
                line_score, is_correct = line._calculate_official_score()
                total_score += line_score
                line.write({
                    "score": line_score,
                    "is_correct": is_correct,
                })
            session.with_context(corporate_lms_exam_state_update=True).write({
                "submitted_at": fields.Datetime.now(),
                "score": total_score,
                "passed": total_score >= session.exam_id.passing_score,
                "state": "graded",
            })
            session._sync_exam_gradebook_line()
        return True

    def action_expire(self):
        self.with_context(corporate_lms_exam_state_update=True).write({"state": "expired"})
        return True

    def _prepare_session_values(self, vals):
        partner_id = vals.get("partner_id") or self.env.user.partner_id.id
        vals["partner_id"] = partner_id
        if not vals.get("started_at"):
            vals["started_at"] = fields.Datetime.now()
        if not vals.get("employee_id") and partner_id:
            employee = self.env["hr.employee"].sudo().search([
                ("user_id.partner_id", "=", partner_id),
            ], limit=1)
            if employee:
                vals["employee_id"] = employee.id

    def _check_session_create_allowed(self, vals):
        exam = self.env["elearning.exam"].browse(vals.get("exam_id"))
        partner = self.env["res.partner"].browse(vals.get("partner_id"))
        if not exam or not partner:
            return
        if not self._is_training_role():
            if not self.env.user.has_group("corporate_lms_base.group_corporate_lms_learner"):
                return
            if partner != self.env.user.partner_id:
                raise AccessError(_("Learners can only create exam sessions for themselves."))
            exam.check_access("read")
        exam.sudo()._check_start_allowed(partner)

    def _check_learner_write_access(self, vals):
        if self.env.context.get("corporate_lms_exam_state_update") or self._is_training_role():
            return
        if not self.env.user.has_group("corporate_lms_base.group_corporate_lms_learner"):
            return
        raise AccessError(_("Learners cannot directly update exam session results."))

    def _check_submit_allowed(self):
        self.ensure_one()
        if self.state != "in_progress":
            raise ValidationError(_("Only in-progress exam sessions can be submitted."))
        if not self._is_training_role() and self.partner_id != self.env.user.partner_id:
            raise AccessError(_("Learners can only submit their own exam sessions."))

    def _generate_session_lines(self):
        self.ensure_one()
        questions = self.exam_id._get_session_questions()
        self.write({
            "line_ids": [(0, 0, {"question_id": question.id}) for question in questions],
        })

    def _sync_exam_gradebook_line(self):
        Gradebook = self.env["elearning.gradebook"]
        for session in self:
            Gradebook.upsert_exam_line(session)

    def _is_training_role(self):
        if self.env.su:
            return True
        return self.env.user.has_groups(
            "corporate_lms_base.group_corporate_lms_admin,"
            "corporate_lms_base.group_corporate_lms_training_manager,"
            "corporate_lms_base.group_corporate_lms_instructor"
        )


class ElearningExamSessionLine(models.Model):
    _name = "elearning.exam.session.line"
    _description = "Exam Session Line"
    _order = "session_id, id"

    session_id = fields.Many2one(
        "elearning.exam.session",
        required=True,
        ondelete="cascade",
        index=True,
    )
    question_id = fields.Many2one(
        "elearning.question",
        required=True,
        ondelete="restrict",
        index=True,
    )
    selected_answer_ids = fields.Many2many(
        "elearning.answer",
        "elearning_exam_session_line_answer_rel",
        "line_id",
        "answer_id",
        string="Selected Answers",
    )
    score = fields.Float(readonly=True)
    is_correct = fields.Boolean(readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.user.has_group("corporate_lms_base.group_corporate_lms_learner") and not self.env.su:
            raise AccessError(_("Learners cannot create exam session lines directly."))
        lines = super().create(vals_list)
        lines._check_selected_answers_match_question()
        return lines

    def write(self, vals):
        self._check_learner_write_access(vals)
        result = super().write(vals)
        if {"question_id", "selected_answer_ids"}.intersection(vals):
            self._check_selected_answers_match_question()
        return result

    @api.constrains("question_id", "selected_answer_ids")
    def _check_selected_answers_match_question(self):
        for line in self:
            invalid_answers = line.selected_answer_ids.filtered(
                lambda answer: answer.question_id != line.question_id
            )
            if invalid_answers:
                raise ValidationError(_("Selected answers must belong to the session question."))
            if line.question_id.question_type in ("single", "single_choice", "true_false") and len(line.selected_answer_ids) > 1:
                raise ValidationError(_("A single choice question can only have one selected answer."))

    def _calculate_official_score(self):
        self.ensure_one()
        correct_answer_ids = set(self.question_id.answer_ids.sudo().filtered("is_correct").ids)
        selected_answer_ids = set(self.selected_answer_ids.sudo().ids)
        is_correct = bool(correct_answer_ids) and selected_answer_ids == correct_answer_ids
        return (self.question_id.score if is_correct else 0.0), is_correct

    def _check_learner_write_access(self, vals):
        if self.env.su:
            return
        if not self.env.user.has_group("corporate_lms_base.group_corporate_lms_learner"):
            return
        if set(vals) - {"selected_answer_ids"}:
            raise AccessError(_("Learners can only select exam answers."))
        blocked = self.filtered(
            lambda line: line.session_id.partner_id != self.env.user.partner_id
            or line.session_id.state != "in_progress"
        )
        if blocked:
            raise AccessError(_("Learners can only answer their own in-progress exam sessions."))
