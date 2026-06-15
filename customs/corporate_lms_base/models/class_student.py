# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ElearningClassStudent(models.Model):
    _name = "elearning.class.student"
    _description = "Class Student"
    _order = "class_id, partner_id, id"

    class_id = fields.Many2one(
        "elearning.class",
        required=True,
        ondelete="cascade",
        index=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        required=True,
        ondelete="cascade",
        index=True,
    )
    employee_id = fields.Many2one(
        "hr.employee",
        ondelete="set null",
        index=True,
    )
    program_partner_id = fields.Many2one(
        "elearning.program.partner",
        string="Program Enrollment",
        ondelete="set null",
        index=True,
    )
    state = fields.Selection(
        [
            ("invited", "Invited"),
            ("active", "Active"),
            ("completed", "Completed"),
            ("dropped", "Dropped"),
        ],
        default="invited",
        required=True,
        index=True,
    )

    @api.constrains("class_id", "partner_id")
    def _check_unique_student_per_class(self):
        for student in self:
            if not student.class_id or not student.partner_id:
                continue
            duplicate = self.search_count([
                ("id", "!=", student.id),
                ("class_id", "=", student.class_id.id),
                ("partner_id", "=", student.partner_id.id),
            ])
            if duplicate:
                raise ValidationError(_("A learner can only be assigned once to the same class."))

    @api.constrains("class_id", "state")
    def _check_class_capacity(self):
        self.mapped("class_id")._check_student_capacity()
