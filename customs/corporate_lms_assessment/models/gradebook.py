# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError


class ElearningGradebook(models.Model):
    _name = "elearning.gradebook"
    _description = "Gradebook"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "program_id, class_id, partner_id, id"

    program_id = fields.Many2one(
        "elearning.program",
        ondelete="restrict",
        tracking=True,
    )
    class_id = fields.Many2one(
        "elearning.class",
        ondelete="restrict",
        tracking=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        required=True,
        ondelete="cascade",
        tracking=True,
    )
    employee_id = fields.Many2one(
        "hr.employee",
        ondelete="set null",
        tracking=True,
    )
    line_ids = fields.One2many(
        "elearning.gradebook.line",
        "gradebook_id",
        string="Grade Lines",
        copy=True,
    )
    final_score = fields.Float(
        compute="_compute_final_score",
        store=True,
        tracking=True,
    )
    passed = fields.Boolean(
        compute="_compute_passed",
        store=True,
        tracking=True,
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("open", "Open"),
            ("locked", "Locked"),
        ],
        default="draft",
        required=True,
        tracking=True,
    )

    @api.depends("line_ids.weighted_score")
    def _compute_final_score(self):
        for gradebook in self:
            gradebook.final_score = sum(gradebook.line_ids.mapped("weighted_score"))

    @api.depends("final_score", "program_id.passing_score", "state")
    def _compute_passed(self):
        for gradebook in self:
            gradebook.passed = (
                gradebook.state == "locked"
                and bool(gradebook.program_id)
                and gradebook.final_score >= gradebook.program_id.passing_score
            )

    def write(self, vals):
        if self._locked_edit_blocked():
            raise AccessError(_("Locked gradebooks can only be edited by LMS administrators or training managers."))
        return super().write(vals)

    def action_finalize(self):
        ProgramEnrollment = self.env["elearning.program.partner"].sudo()
        for gradebook in self:
            gradebook.with_context(corporate_lms_gradebook_lock_update=True).state = "locked"
            if not gradebook.program_id:
                continue
            passed = gradebook.final_score >= gradebook.program_id.passing_score
            enrollment = ProgramEnrollment.search([
                ("program_id", "=", gradebook.program_id.id),
                ("partner_id", "=", gradebook.partner_id.id),
                ("state", "!=", "cancelled"),
            ], limit=1)
            if enrollment:
                enrollment.write({
                    "final_score": gradebook.final_score,
                    "state": "completed" if passed else "failed",
                })
        return True

    @api.model
    def _get_or_create_gradebook(self, partner, program=False, class_id=False, employee=False):
        if not partner:
            raise ValidationError(_("A gradebook requires a learner."))
        program = self.env["elearning.program"].browse(program) if isinstance(program, int) else program
        class_record = self.env["elearning.class"].browse(class_id) if isinstance(class_id, int) else class_id
        if not program and class_record:
            program = class_record.program_id
        domain = [
            ("partner_id", "=", partner.id),
            ("program_id", "=", program.id if program else False),
            ("class_id", "=", class_record.id if class_record else False),
        ]
        gradebook = self.sudo().search(domain, limit=1)
        if gradebook:
            return gradebook
        return self.sudo().create({
            "program_id": program.id if program else False,
            "class_id": class_record.id if class_record else False,
            "partner_id": partner.id,
            "employee_id": employee.id if employee else False,
            "state": "open",
        })

    @api.model
    def upsert_assignment_line(self, submission):
        GradebookLine = self.env["elearning.gradebook.line"].sudo()
        assignment = submission.assignment_id
        program = assignment.program_id or assignment.class_id.program_id
        if not program:
            return self.env["elearning.gradebook.line"]
        gradebook = self._get_or_create_gradebook(
            submission.partner_id,
            program=program,
            class_id=assignment.class_id,
            employee=submission.employee_id,
        )
        gradebook.with_user(self.env.user)._check_locked_line_edit_allowed()
        values = {
            "gradebook_id": gradebook.id,
            "source_type": "assignment",
            "submission_id": submission.id,
            "score": submission.score,
            "weight": 1.0,
            "note": assignment.name,
        }
        line = GradebookLine.search([
            ("source_type", "=", "assignment"),
            ("submission_id", "=", submission.id),
        ], limit=1)
        if line:
            line.write(values)
            return line
        return GradebookLine.create(values)

    @api.model
    def upsert_exam_line(self, exam_session):
        GradebookLine = self.env["elearning.gradebook.line"].sudo()
        exam = exam_session.exam_id
        program = exam.program_id or exam.class_id.program_id
        if not program:
            return self.env["elearning.gradebook.line"]
        gradebook = self._get_or_create_gradebook(
            exam_session.partner_id,
            program=program,
            class_id=exam.class_id,
            employee=exam_session.employee_id,
        )
        gradebook.with_user(self.env.user)._check_locked_line_edit_allowed()
        values = {
            "gradebook_id": gradebook.id,
            "source_type": "exam",
            "exam_session_id": exam_session.id,
            "score": exam_session.score,
            "weight": 1.0,
            "note": exam.name,
        }
        line = GradebookLine.search([
            ("source_type", "=", "exam"),
            ("exam_session_id", "=", exam_session.id),
        ], limit=1)
        if line:
            line.write(values)
            return line
        return GradebookLine.create(values)

    def _locked_edit_blocked(self):
        if self.env.context.get("corporate_lms_gradebook_lock_update") or self.env.su:
            return False
        if not self.filtered(lambda gradebook: gradebook.state == "locked"):
            return False
        return not any(
            self.env.user.has_group(group)
            for group in (
                "corporate_lms_base.group_corporate_lms_admin",
                "corporate_lms_base.group_corporate_lms_training_manager",
            )
        )

    def _check_locked_line_edit_allowed(self):
        if self._locked_edit_blocked():
            raise AccessError(_("Locked gradebook lines can only be edited by LMS administrators or training managers."))


class ElearningGradebookLine(models.Model):
    _name = "elearning.gradebook.line"
    _description = "Gradebook Line"
    _order = "gradebook_id, id"

    gradebook_id = fields.Many2one(
        "elearning.gradebook",
        required=True,
        ondelete="cascade",
        index=True,
    )
    source_type = fields.Selection(
        [
            ("exam", "Exam"),
            ("assignment", "Assignment"),
            ("manual", "Manual"),
        ],
        default="manual",
        required=True,
        index=True,
    )
    submission_id = fields.Many2one(
        "elearning.assignment.submission",
        string="Submission",
        ondelete="set null",
        index=True,
    )
    exam_session_id = fields.Many2one(
        "elearning.exam.session",
        string="Exam Session",
        ondelete="set null",
        index=True,
    )
    score = fields.Float(required=True)
    weight = fields.Float(default=1.0, required=True)
    weighted_score = fields.Float(
        compute="_compute_weighted_score",
        store=True,
    )
    note = fields.Text()

    @api.model_create_multi
    def create(self, vals_list):
        gradebook_ids = [vals.get("gradebook_id") for vals in vals_list if vals.get("gradebook_id")]
        self.env["elearning.gradebook"].browse(gradebook_ids)._check_locked_line_edit_allowed()
        return super().create(vals_list)

    def write(self, vals):
        self.mapped("gradebook_id")._check_locked_line_edit_allowed()
        return super().write(vals)

    def unlink(self):
        self.mapped("gradebook_id")._check_locked_line_edit_allowed()
        return super().unlink()

    @api.depends("score", "weight")
    def _compute_weighted_score(self):
        for line in self:
            line.weighted_score = line.score * line.weight

    @api.constrains("score", "weight")
    def _check_non_negative_values(self):
        for line in self:
            if line.score < 0:
                raise ValidationError(_("Gradebook line score must be zero or greater."))
            if line.weight < 0:
                raise ValidationError(_("Gradebook line weight must be zero or greater."))

    @api.constrains("source_type", "submission_id", "exam_session_id")
    def _check_source_reference(self):
        for line in self:
            if line.source_type == "assignment" and not line.submission_id:
                raise ValidationError(_("Assignment gradebook lines must reference a submission."))
            if line.source_type != "assignment" and line.submission_id:
                raise ValidationError(_("Only assignment gradebook lines can reference a submission."))
            if line.source_type == "exam" and not line.exam_session_id:
                raise ValidationError(_("Exam gradebook lines must reference an exam session."))
            if line.source_type != "exam" and line.exam_session_id:
                raise ValidationError(_("Only exam gradebook lines can reference an exam session."))
