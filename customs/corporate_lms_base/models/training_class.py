# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ElearningClass(models.Model):
    _name = "elearning.class"
    _description = "Training Class"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_start desc, name, id"

    _TRAINER_GROUPS = (
        "corporate_lms_base.group_corporate_lms_instructor",
        "corporate_lms_base.group_corporate_lms_training_manager",
        "corporate_lms_base.group_corporate_lms_manager",
        "corporate_lms_base.group_corporate_lms_admin",
    )

    name = fields.Char(required=True, tracking=True, translate=True)
    code = fields.Char(required=True, index=True, tracking=True)
    program_id = fields.Many2one(
        "elearning.program",
        string="Program",
        ondelete="restrict",
        tracking=True,
    )
    channel_id = fields.Many2one(
        "slide.channel",
        string="Course",
        ondelete="restrict",
        tracking=True,
    )
    trainer_ids = fields.Many2many(
        "res.users",
        "elearning_class_trainer_rel",
        "class_id",
        "user_id",
        string="Trainers",
        tracking=True,
    )
    student_ids = fields.One2many(
        "elearning.class.student",
        "class_id",
        string="Students",
        copy=False,
    )
    date_start = fields.Date(tracking=True)
    date_end = fields.Date(tracking=True)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("open", "Open"),
            ("running", "Running"),
            ("done", "Done"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
        required=True,
        tracking=True,
    )
    max_students = fields.Integer(tracking=True)
    active = fields.Boolean(default=True)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._check_program_or_channel()
        records._check_student_capacity()
        return records

    def write(self, vals):
        result = super().write(vals)
        if "program_id" in vals or "channel_id" in vals:
            self._check_program_or_channel()
        if "max_students" in vals:
            self._check_student_capacity()
        return result

    @api.constrains("program_id", "channel_id")
    def _check_program_or_channel(self):
        for training_class in self:
            if not training_class.program_id and not training_class.channel_id:
                raise ValidationError(_("A class must have at least a program or a course."))

    @api.constrains("date_start", "date_end")
    def _check_dates(self):
        for training_class in self:
            if (
                training_class.date_start
                and training_class.date_end
                and training_class.date_end < training_class.date_start
            ):
                raise ValidationError(_("Class end date must be on or after start date."))

    @api.constrains("trainer_ids")
    def _check_trainer_groups(self):
        group_spec = ",".join(self._TRAINER_GROUPS)
        for training_class in self:
            invalid_trainers = training_class.trainer_ids.filtered(
                lambda user: not user.has_groups(group_spec)
            )
            if invalid_trainers:
                raise ValidationError(_(
                    "Class trainers must be Corporate LMS instructors or managers."
                ))

    @api.constrains("max_students", "student_ids")
    def _check_max_students(self):
        for training_class in self:
            training_class._check_student_capacity()

    def _check_student_capacity(self):
        for training_class in self:
            if training_class.max_students < 0:
                raise ValidationError(_("Maximum students must be zero or greater."))
            if not training_class.max_students:
                continue
            student_count = len(training_class.student_ids.filtered(
                lambda student: student.state != "dropped"
            ))
            if student_count > training_class.max_students:
                raise ValidationError(_("This class exceeds the configured maximum students."))
