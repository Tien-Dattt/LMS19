# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.fields import Domain


class ElearningTrainingMatrix(models.Model):
    _name = "elearning.training.matrix"
    _description = "Training Matrix"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "active desc, name, id"

    name = fields.Char(required=True, tracking=True, translate=True)
    department_id = fields.Many2one("hr.department", string="Department", tracking=True)
    job_id = fields.Many2one("hr.job", string="Job Position", tracking=True)
    employee_level_id = fields.Many2one(
        "elearning.employee.level",
        string="Employee Level",
        tracking=True,
    )
    role_track_id = fields.Many2one(
        "elearning.role.track",
        string="Role Track",
        tracking=True,
    )
    program_id = fields.Many2one(
        "elearning.program",
        string="Program",
        required=True,
        ondelete="restrict",
        tracking=True,
    )
    mandatory = fields.Boolean(default=True, tracking=True)
    priority = fields.Selection(
        [
            ("required", "Required"),
            ("recommended", "Recommended"),
            ("optional", "Optional"),
        ],
        default="required",
        required=True,
        tracking=True,
    )
    deadline_days = fields.Integer(tracking=True)
    required_score = fields.Float(tracking=True)
    active = fields.Boolean(default=True)

    @api.constrains("deadline_days", "required_score")
    def _check_non_negative_values(self):
        for matrix in self:
            if matrix.deadline_days < 0:
                raise ValidationError(_("Deadline days must be zero or greater."))
            if matrix.required_score < 0:
                raise ValidationError(_("Required score must be zero or greater."))

    @api.model
    def _get_matching_matrices(self, employee, published_programs_only=False):
        employee.ensure_one()
        domain = Domain("active", "=", True)
        for matrix_field, employee_field in [
            ("department_id", "department_id"),
            ("job_id", "job_id"),
            ("employee_level_id", "employee_level_id"),
            ("role_track_id", "role_track_id"),
        ]:
            value = employee[employee_field]
            domain &= Domain.OR((
                Domain(matrix_field, "=", False),
                Domain(matrix_field, "=", value.id),
            ))

        matrices = self.search(domain)
        if published_programs_only:
            matrices = matrices.filtered(lambda matrix: matrix.program_id.state == "published")
        return matrices.sorted(key=lambda matrix: matrix._match_sort_key(), reverse=True)

    @api.model
    def _get_best_match_for_employee(self, employee, published_programs_only=False):
        return self._get_matching_matrices(
            employee,
            published_programs_only=published_programs_only,
        )[:1]

    def _matches_employee(self, employee):
        """Return True when every filled matrix condition matches employee."""
        self.ensure_one()
        employee.ensure_one()
        return all([
            not self.department_id or self.department_id == employee.department_id,
            not self.job_id or self.job_id == employee.job_id,
            not self.employee_level_id or self.employee_level_id == employee.employee_level_id,
            not self.role_track_id or self.role_track_id == employee.role_track_id,
        ])

    def _get_match_score_for_employee(self, employee):
        """Return a numeric specificity score for this employee, or -1 if not matched."""
        self.ensure_one()
        if not self._matches_employee(employee):
            return -1
        tier, specificity, _sequence = self._match_sort_key()
        return tier + specificity

    @api.model
    def get_matching_matrix_for_employee(self, employee):
        """Return the best active matching matrix whose program is published."""
        return self._get_best_match_for_employee(
            employee,
            published_programs_only=True,
        )

    def _match_sort_key(self):
        self.ensure_one()
        has_job = bool(self.job_id)
        has_department = bool(self.department_id)
        has_level = bool(self.employee_level_id)
        has_role = bool(self.role_track_id)

        if has_job and has_level and has_role:
            tier = 40
        elif has_job and has_level:
            tier = 30
        elif has_department and has_level:
            tier = 20
        elif has_level:
            tier = 10
        else:
            tier = 0

        specificity = sum([has_job, has_department, has_level, has_role])
        return (tier, specificity, -self.id)
