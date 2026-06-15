# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ElearningRoleTrack(models.Model):
    _name = "elearning.role.track"
    _description = "Employee Role Track"
    _order = "name, id"

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, index=True)
    description = fields.Text(translate=True)
    active = fields.Boolean(default=True)

    @api.constrains("code", "active")
    def _check_unique_active_code(self):
        for track in self:
            if not track.active or not track.code:
                continue
            duplicate = self.with_context(active_test=False).search_count([
                ("id", "!=", track.id),
                ("code", "=", track.code),
                ("active", "=", True),
            ])
            if duplicate:
                raise ValidationError(_("An active role track with this code already exists."))

    def unlink(self):
        used_tracks = self.filtered(lambda track: track._is_used())
        if used_tracks:
            used_tracks.write({"active": False})
        return super(ElearningRoleTrack, self - used_tracks).unlink()

    def _is_used(self):
        self.ensure_one()
        return bool(
            self.env["hr.employee"].with_context(active_test=False).search_count([
                ("role_track_id", "=", self.id),
            ])
            or self.env["elearning.training.matrix"].with_context(active_test=False).search_count([
                ("role_track_id", "=", self.id),
            ])
        )
