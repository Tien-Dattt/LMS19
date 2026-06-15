# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError


class ElearningAssignment(models.Model):
    _name = "elearning.assignment"
    _description = "Assignment"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "due_date desc, name, id"

    name = fields.Char(required=True, tracking=True, translate=True)
    description = fields.Html(required=True, translate=True)
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
    due_date = fields.Datetime(tracking=True)
    submission_type = fields.Selection(
        [
            ("text", "Text"),
            ("file", "File"),
            ("url", "URL"),
            ("mixed", "Mixed"),
        ],
        default="text",
        required=True,
        tracking=True,
    )
    max_score = fields.Float(default=100.0, required=True, tracking=True)
    rubric_id = fields.Many2one(
        "elearning.rubric",
        ondelete="set null",
        tracking=True,
    )
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
    submission_ids = fields.One2many(
        "elearning.assignment.submission",
        "assignment_id",
        string="Submissions",
        copy=False,
    )
    active = fields.Boolean(default=True)

    @api.model_create_multi
    def create(self, vals_list):
        assignments = super().create(vals_list)
        assignments._check_learning_scope()
        return assignments

    def write(self, vals):
        result = super().write(vals)
        if {"program_id", "channel_id", "class_id"}.intersection(vals):
            self._check_learning_scope()
        return result

    @api.constrains("program_id", "channel_id", "class_id")
    def _check_learning_scope(self):
        for assignment in self:
            if not assignment.program_id and not assignment.channel_id and not assignment.class_id:
                raise ValidationError(_("An assignment must belong to at least a program, course, or class."))

    @api.constrains("max_score")
    def _check_max_score(self):
        for assignment in self:
            if assignment.max_score < 0:
                raise ValidationError(_("Assignment maximum score must be zero or greater."))

    def action_publish(self):
        self.write({"state": "published"})
        return True

    def action_close(self):
        self.write({"state": "closed"})
        return True


class ElearningAssignmentSubmission(models.Model):
    _name = "elearning.assignment.submission"
    _description = "Assignment Submission"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "submitted_at desc, id desc"

    assignment_id = fields.Many2one(
        "elearning.assignment",
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
    assignment_program_id = fields.Many2one(
        "elearning.program",
        related="assignment_id.program_id",
        store=True,
        readonly=True,
        string="Program",
    )
    assignment_channel_id = fields.Many2one(
        "slide.channel",
        related="assignment_id.channel_id",
        store=True,
        readonly=True,
        string="Course",
    )
    assignment_class_id = fields.Many2one(
        "elearning.class",
        related="assignment_id.class_id",
        store=True,
        readonly=True,
        string="Class",
    )
    text_answer = fields.Html()
    attachment_ids = fields.Many2many(
        "ir.attachment",
        "elearning_assignment_submission_attachment_rel",
        "submission_id",
        "attachment_id",
        string="Attachments",
    )
    external_url = fields.Char()
    submitted_at = fields.Datetime(readonly=True, tracking=True)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("submitted", "Submitted"),
            ("graded", "Graded"),
            ("returned", "Returned"),
            ("late", "Late"),
        ],
        default="draft",
        required=True,
        tracking=True,
    )
    score = fields.Float(tracking=True)
    feedback = fields.Html()
    grader_id = fields.Many2one(
        "res.users",
        string="Grader",
        readonly=True,
        tracking=True,
    )
    ai_feedback_draft = fields.Html(string="AI Feedback Draft")
    ai_strengths = fields.Html(string="AI Strengths")
    ai_weaknesses = fields.Html(string="AI Weaknesses")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._prepare_submission_values(vals)
            self._check_learner_create_values(vals)
        submissions = super().create(vals_list)
        submissions._check_score_limits()
        return submissions

    def write(self, vals):
        self._check_learner_write_access(vals)
        result = super().write(vals)
        if "score" in vals or "assignment_id" in vals:
            self._check_score_limits()
        if "score" in vals and any(submission.state == "graded" for submission in self):
            self.filtered(lambda submission: submission.state == "graded")._sync_assignment_gradebook_line()
        return result

    def action_submit(self):
        for submission in self:
            submission._check_submission_allowed()
            submission._validate_submission_payload()
            assignment = submission.assignment_id.sudo()
            state = "submitted"
            if assignment.due_date and fields.Datetime.now() > assignment.due_date:
                state = "late"
            submission.with_context(corporate_lms_submission_state_update=True).write({
                "state": state,
                "submitted_at": fields.Datetime.now(),
            })
        return True

    def action_return(self):
        self.write({"state": "returned"})
        return True

    def action_grade(self):
        self._check_score_limits()
        self.write({
            "state": "graded",
            "grader_id": self.env.user.id,
        })
        self._sync_assignment_gradebook_line()
        return True

    @api.constrains("assignment_id", "partner_id")
    def _check_unique_submission_per_assignment_partner(self):
        for submission in self:
            if not submission.assignment_id or not submission.partner_id:
                continue
            duplicate = self.search_count([
                ("id", "!=", submission.id),
                ("assignment_id", "=", submission.assignment_id.id),
                ("partner_id", "=", submission.partner_id.id),
            ])
            if duplicate:
                raise ValidationError(_("A learner can only have one submission per assignment."))

    @api.constrains("score", "assignment_id")
    def _check_score_limits(self):
        for submission in self:
            if submission.score < 0:
                raise ValidationError(_("Submission score must be zero or greater."))
            if submission.assignment_id.max_score and submission.score > submission.assignment_id.max_score:
                raise ValidationError(_("Submission score cannot exceed the assignment maximum score."))

    def _prepare_submission_values(self, vals):
        partner_id = vals.get("partner_id") or self.env.user.partner_id.id
        vals["partner_id"] = partner_id
        if not vals.get("employee_id") and partner_id:
            employee = self.env["hr.employee"].sudo().search([
                ("user_id.partner_id", "=", partner_id),
            ], limit=1)
            if employee:
                vals["employee_id"] = employee.id

    def _check_learner_create_values(self, vals):
        if self._is_training_role():
            return
        if not self.env.user.has_group("corporate_lms_base.group_corporate_lms_learner"):
            return
        if vals.get("partner_id") != self.env.user.partner_id.id:
            raise AccessError(_("Learners can only create submissions for themselves."))
        assignment = self.env["elearning.assignment"].browse(vals.get("assignment_id"))
        if assignment:
            assignment.check_access("read")
            if assignment.state != "published":
                raise ValidationError(_("Learners can only submit published assignments."))

    def _check_learner_write_access(self, vals):
        if self.env.context.get("corporate_lms_submission_state_update") or self._is_training_role():
            return
        if not self.env.user.has_group("corporate_lms_base.group_corporate_lms_learner"):
            return
        allowed_fields = {"text_answer", "attachment_ids", "external_url"}
        if set(vals) - allowed_fields:
            raise AccessError(_("Learners can only edit submission answer fields."))
        blocked = self.filtered(lambda submission: submission.state not in ("draft", "returned"))
        if blocked:
            raise AccessError(_("Learners can only edit submissions in draft or returned state."))

    def _check_submission_allowed(self):
        self.ensure_one()
        assignment = self.assignment_id.sudo()
        if assignment.state == "published":
            return
        if self._is_training_role():
            return
        if assignment.state == "closed":
            raise ValidationError(_("This assignment is closed."))
        raise ValidationError(_("Learners can only submit published assignments."))

    def _validate_submission_payload(self):
        self.ensure_one()
        submission_type = self.assignment_id.submission_type
        has_text = bool((self.text_answer or "").strip())
        has_file = bool(self.attachment_ids)
        has_url = bool((self.external_url or "").strip())
        if submission_type == "text" and not has_text:
            raise ValidationError(_("Text submissions require an answer."))
        if submission_type == "file" and not has_file:
            raise ValidationError(_("File submissions require an attachment."))
        if submission_type == "url" and not has_url:
            raise ValidationError(_("URL submissions require an external URL."))
        if submission_type == "mixed" and not (has_text or has_file or has_url):
            raise ValidationError(_("Mixed submissions require text, an attachment, or an external URL."))

    def _sync_assignment_gradebook_line(self):
        Gradebook = self.env["elearning.gradebook"]
        for submission in self:
            Gradebook.upsert_assignment_line(submission)

    def _is_training_role(self):
        return self.env.user.has_groups(
            "corporate_lms_base.group_corporate_lms_admin,"
            "corporate_lms_base.group_corporate_lms_training_manager,"
            "corporate_lms_base.group_corporate_lms_instructor"
        )
