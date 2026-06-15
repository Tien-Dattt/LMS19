# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import api, fields, models, _


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    _LMS_AUTO_ENROLLMENT_TRIGGER_FIELDS = {
        "user_id",
        "department_id",
        "job_id",
        "employee_level_id",
        "role_track_id",
    }

    employee_level_id = fields.Many2one(
        "elearning.employee.level",
        string="Employee Level",
        tracking=True,
        groups=(
            "hr.group_hr_user,"
            "corporate_lms_base.group_corporate_lms_admin,"
            "corporate_lms_base.group_corporate_lms_training_manager,"
            "corporate_lms_base.group_corporate_lms_hr_officer"
        ),
    )
    role_track_id = fields.Many2one(
        "elearning.role.track",
        string="Role Track",
        tracking=True,
        groups=(
            "hr.group_hr_user,"
            "corporate_lms_base.group_corporate_lms_admin,"
            "corporate_lms_base.group_corporate_lms_training_manager,"
            "corporate_lms_base.group_corporate_lms_hr_officer"
        ),
    )

    @api.model_create_multi
    def create(self, vals_list):
        employees = super().create(vals_list)
        if not self.env.context.get("skip_corporate_lms_auto_enrollment"):
            employees._run_corporate_lms_auto_enrollment()
        return employees

    def write(self, vals):
        trigger_auto_enrollment = bool(
            self._LMS_AUTO_ENROLLMENT_TRIGGER_FIELDS.intersection(vals)
        )
        result = super().write(vals)
        if (
            trigger_auto_enrollment
            and not self.env.context.get("skip_corporate_lms_auto_enrollment")
        ):
            self._run_corporate_lms_auto_enrollment()
        return result

    def action_corporate_lms_auto_enroll(self):
        self._run_corporate_lms_auto_enrollment()
        return True

    def action_apply_training_matrix(self):
        return self.action_corporate_lms_auto_enroll()

    @api.model
    def _cron_corporate_lms_auto_enrollment(self, limit=None):
        domain = [("active", "=", True)]
        employees = self.search(domain, limit=limit)
        employees._run_corporate_lms_auto_enrollment()
        return True

    def _run_corporate_lms_auto_enrollment(self):
        original_env = self.env
        Matrix = self.env["elearning.training.matrix"].sudo()
        Enrollment = self.env["elearning.program.partner"].sudo()
        active_states = Enrollment._ACTIVE_STATES

        for employee in self.sudo():
            partner = employee.user_id.partner_id
            if not partner:
                employee._create_corporate_lms_auto_enrollment_log(
                    "skipped",
                    "skipped_no_user_partner",
                )
                continue

            matrix = Matrix._get_best_match_for_employee(
                employee,
                published_programs_only=False,
            )
            if not matrix:
                employee._create_corporate_lms_auto_enrollment_log(
                    "skipped",
                    "no_matrix_matched",
                    partner=partner,
                )
                continue

            program = matrix.program_id
            if program.state != "published":
                employee._create_corporate_lms_auto_enrollment_log(
                    "skipped",
                    "program_not_published",
                    partner=partner,
                    matrix=matrix,
                    program=program,
                )
                continue

            enrollment = Enrollment.search([
                ("program_id", "=", program.id),
                ("partner_id", "=", partner.id),
                ("state", "in", active_states),
            ], limit=1)

            try:
                if not enrollment:
                    enrollment = Enrollment.create({
                        "program_id": program.id,
                        "partner_id": partner.id,
                        "employee_id": employee.id,
                        "deadline_date": employee._get_corporate_lms_deadline_date(matrix),
                        "source": "matrix",
                    })
                    message = "program_enrollment_created"
                else:
                    message = "program_enrollment_exists"

                employee._action_enroll_required_courses_from_auto_enrollment(
                    enrollment,
                    original_env,
                )
            except Exception as error:
                employee._create_corporate_lms_auto_enrollment_log(
                    "error",
                    _("course_enrollment_error: %s") % error,
                    partner=partner,
                    matrix=matrix,
                    program=program,
                )
                continue

            employee._create_corporate_lms_auto_enrollment_log(
                "success",
                message,
                partner=partner,
                matrix=matrix,
                program=program,
            )
        return True

    def _action_enroll_required_courses_from_auto_enrollment(self, enrollment, original_env):
        self.ensure_one()
        required_channels = enrollment.program_id.line_ids.filtered("mandatory").mapped("channel_id")
        if required_channels:
            required_channels.with_env(original_env)._action_add_members(
                enrollment.partner_id.with_env(original_env),
                raise_on_access=True,
            )
        if enrollment.state == "assigned":
            enrollment.state = "in_progress"

    def _get_corporate_lms_deadline_date(self, matrix):
        self.ensure_one()
        if matrix.deadline_days <= 0:
            return False
        return fields.Date.context_today(self) + timedelta(days=matrix.deadline_days)

    def _create_corporate_lms_auto_enrollment_log(
        self,
        status,
        message,
        partner=False,
        matrix=False,
        program=False,
    ):
        self.ensure_one()
        return self.env["elearning.auto.enrollment.log"].sudo().create({
            "employee_id": self.id,
            "partner_id": partner.id if partner else False,
            "matrix_id": matrix.id if matrix else False,
            "program_id": program.id if program else False,
            "status": status,
            "message": message,
        })
