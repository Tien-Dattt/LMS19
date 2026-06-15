# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ElearningEmployeeLevel(models.Model):
    _name = "elearning.employee.level"
    _description = "Employee Training Level"
    _order = "sequence, name, id"

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, index=True)
    sequence = fields.Integer(default=10)
    description = fields.Text(translate=True)
    active = fields.Boolean(default=True)

    @api.constrains("code", "active")
    def _check_unique_active_code(self):
        for level in self:
            if not level.active or not level.code:
                continue
            duplicate = self.with_context(active_test=False).search_count([
                ("id", "!=", level.id),
                ("code", "=", level.code),
                ("active", "=", True),
            ])
            if duplicate:
                raise ValidationError(_("An active employee level with this code already exists."))

    def unlink(self):
        used_levels = self.filtered(lambda level: level._is_used())
        if used_levels:
            used_levels.write({"active": False})
        return super(ElearningEmployeeLevel, self - used_levels).unlink()

    def _is_used(self):
        self.ensure_one()
        return bool(
            self.env["hr.employee"].with_context(active_test=False).search_count([
                ("employee_level_id", "=", self.id),
            ])
            or self.env["elearning.training.matrix"].with_context(active_test=False).search_count([
                ("employee_level_id", "=", self.id),
            ])
        )
