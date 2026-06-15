# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ElearningProgramPartner(models.Model):
    _name = "elearning.program.partner"
    _description = "Program Enrollment"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "program_id, partner_id, id"

    _ACTIVE_STATES = ("assigned", "in_progress")

    program_id = fields.Many2one(
        "elearning.program",
        required=True,
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
    department_id = fields.Many2one(
        "hr.department",
        related="employee_id.department_id",
        store=True,
        readonly=True,
        string="Department",
    )
    employee_level_id = fields.Many2one(
        "elearning.employee.level",
        related="employee_id.employee_level_id",
        store=True,
        readonly=True,
        string="Employee Level",
    )
    role_track_id = fields.Many2one(
        "elearning.role.track",
        related="employee_id.role_track_id",
        store=True,
        readonly=True,
        string="Role Track",
    )
    state = fields.Selection(
        [
            ("assigned", "Assigned"),
            ("in_progress", "In Progress"),
            ("completed", "Completed"),
            ("failed", "Failed"),
            ("cancelled", "Cancelled"),
        ],
        default="assigned",
        required=True,
        tracking=True,
    )
    progress = fields.Float(compute="_compute_progress", store=True, string="Progress")
    deadline_date = fields.Date(tracking=True)
    final_score = fields.Float(tracking=True)
    source = fields.Selection(
        [
            ("manual", "Manual"),
            ("auto", "Auto"),
            ("matrix", "Matrix"),
            ("import", "Import"),
        ],
        default="manual",
        required=True,
        tracking=True,
    )
    assigned_date = fields.Date(default=fields.Date.context_today, tracking=True)
    completed_date = fields.Date(tracking=True)

    @api.constrains("program_id", "partner_id", "state")
    def _check_unique_active_program_enrollment(self):
        for enrollment in self:
            if (
                not enrollment.program_id
                or not enrollment.partner_id
                or enrollment.state not in self._ACTIVE_STATES
            ):
                continue
            duplicate = self.search_count([
                ("id", "!=", enrollment.id),
                ("program_id", "=", enrollment.program_id.id),
                ("partner_id", "=", enrollment.partner_id.id),
                ("state", "in", self._ACTIVE_STATES),
            ])
            if duplicate:
                raise ValidationError(_("A learner already has an active enrollment for this program."))

    @api.depends("program_id", "program_id.line_ids", "program_id.line_ids.mandatory", "program_id.line_ids.channel_id", "partner_id")
    def _compute_progress(self):
        SlideChannelPartner = self.env["slide.channel.partner"].sudo()
        for enrollment in self:
            required_channels = enrollment.program_id.line_ids.filtered("mandatory").mapped("channel_id")
            if not enrollment.partner_id or not required_channels:
                enrollment.progress = 0.0
                continue

            memberships = SlideChannelPartner.search([
                ("channel_id", "in", required_channels.ids),
                ("partner_id", "=", enrollment.partner_id.id),
                ("member_status", "!=", "invited"),
                ("active", "=", True),
            ])
            completion_by_channel = {
                membership.channel_id.id: 100.0
                for membership in memberships
                if membership.member_status == "completed" or membership.completion >= 100.0
            }
            enrollment.progress = sum(
                completion_by_channel.get(channel.id, 0.0)
                for channel in required_channels
            ) / len(required_channels)

    def write(self, vals):
        result = super().write(vals)
        if vals.get("state") == "completed":
            today = fields.Date.context_today(self)
            self.filtered(lambda enrollment: not enrollment.completed_date).write({
                "completed_date": today,
            })
        return result

    def action_enroll_courses(self):
        for enrollment in self:
            required_channels = enrollment.program_id.line_ids.filtered("mandatory").mapped("channel_id")
            if required_channels:
                required_channels._action_add_members(
                    enrollment.partner_id,
                    raise_on_access=True,
                )
            if enrollment.state == "assigned":
                enrollment.state = "in_progress"
        return True

    def _compute_state_from_progress_and_score(self):
        today = fields.Date.context_today(self)
        for enrollment in self:
            if enrollment.state == "cancelled":
                continue
            if enrollment.progress < 100.0:
                if enrollment.state == "assigned":
                    continue
                enrollment.state = "in_progress"
                continue
            if enrollment.program_id.passing_score and enrollment.final_score < enrollment.program_id.passing_score:
                enrollment.state = "failed"
                continue
            enrollment.write({
                "state": "completed",
                "completed_date": enrollment.completed_date or today,
            })
        return True


class SlideChannelPartner(models.Model):
    _inherit = "slide.channel.partner"

    @api.model_create_multi
    def create(self, vals_list):
        memberships = super().create(vals_list)
        memberships._recompute_corporate_lms_program_progress()
        return memberships

    def write(self, vals):
        affected = self
        result = super().write(vals)
        if {"channel_id", "partner_id", "member_status", "completion", "active"}.intersection(vals):
            affected._recompute_corporate_lms_program_progress()
        return result

    def unlink(self):
        enrollment_domain = self._get_corporate_lms_program_enrollment_domain()
        result = super().unlink()
        self.env["elearning.program.partner"].sudo().search(enrollment_domain)._compute_progress()
        return result

    def _recompute_corporate_lms_program_progress(self):
        domain = self._get_corporate_lms_program_enrollment_domain()
        if domain:
            self.env["elearning.program.partner"].sudo().search(domain)._compute_progress()

    def _get_corporate_lms_program_enrollment_domain(self):
        channel_ids = self.mapped("channel_id").ids
        partner_ids = self.mapped("partner_id").ids
        if not channel_ids or not partner_ids:
            return [("id", "=", 0)]
        return [
            ("partner_id", "in", partner_ids),
            ("program_id.line_ids.channel_id", "in", channel_ids),
        ]
