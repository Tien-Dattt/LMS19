# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ElearningProgramLine(models.Model):
    _name = "elearning.program.line"
    _description = "Learning Program Line"
    _order = "program_id, sequence, id"

    program_id = fields.Many2one(
        "elearning.program",
        required=True,
        ondelete="cascade",
        index=True,
    )
    channel_id = fields.Many2one(
        "slide.channel",
        string="Course",
        required=True,
        ondelete="restrict",
    )
    sequence = fields.Integer(default=10)
    mandatory = fields.Boolean(default=True)
    unlock_policy = fields.Selection(
        [
            ("always", "Always"),
            ("open_after_previous_completed", "Open After Previous Completed"),
            ("manual", "Manual"),
        ],
        default="always",
        required=True,
    )
    weight = fields.Float(default=1.0)

    @api.constrains("program_id", "channel_id")
    def _check_unique_channel_in_program(self):
        for line in self:
            if not line.program_id or not line.channel_id:
                continue
            duplicate = self.search_count([
                ("id", "!=", line.id),
                ("program_id", "=", line.program_id.id),
                ("channel_id", "=", line.channel_id.id),
            ])
            if duplicate:
                raise ValidationError(_("A course can only appear once in the same program."))
