# -*- coding: utf-8 -*-

from odoo import fields, models, _
from odoo.exceptions import AccessError, ValidationError


class ElearningProgram(models.Model):
    _name = "elearning.program"
    _description = "Learning Program"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name, id"

    name = fields.Char(required=True, tracking=True, translate=True)
    code = fields.Char(required=True, index=True, tracking=True)
    description = fields.Html(translate=True)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("published", "Published"),
            ("archived", "Archived"),
        ],
        default="draft",
        required=True,
        tracking=True,
    )
    target_level_ids = fields.Many2many(
        "elearning.employee.level",
        "elearning_program_target_level_rel",
        "program_id",
        "level_id",
        string="Target Levels",
    )
    target_role_track_ids = fields.Many2many(
        "elearning.role.track",
        "elearning_program_target_role_track_rel",
        "program_id",
        "role_track_id",
        string="Target Role Tracks",
    )
    line_ids = fields.One2many(
        "elearning.program.line",
        "program_id",
        string="Courses",
        copy=True,
    )
    enrollment_ids = fields.One2many(
        "elearning.program.partner",
        "program_id",
        string="Enrollments",
        copy=False,
    )
    passing_score = fields.Float(tracking=True)
    active = fields.Boolean(default=True)

    def action_publish(self):
        for program in self:
            if not program.line_ids.filtered("mandatory"):
                raise ValidationError(_("A program must have at least one mandatory course before publishing."))
        self.write({"state": "published", "active": True})
        return True

    def action_archive(self):
        self.write({"state": "archived", "active": False})
        return True

    def action_reset_to_draft(self):
        if not self._can_manage_program_state():
            raise AccessError(_("Only LMS administrators or training managers can reset programs to draft."))
        self.write({"state": "draft", "active": True})
        return True

    def action_view_enrollments(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Program Enrollments"),
            "res_model": "elearning.program.partner",
            "view_mode": "list,form",
            "domain": [("program_id", "=", self.id)],
            "context": {"default_program_id": self.id},
        }

    def _can_manage_program_state(self):
        if self.env.su:
            return True
        return any(
            self.env.user.has_group(group)
            for group in (
                "corporate_lms_base.group_corporate_lms_admin",
                "corporate_lms_base.group_corporate_lms_training_manager",
            )
        )
