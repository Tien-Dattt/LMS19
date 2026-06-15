# -*- coding: utf-8 -*-

from odoo import fields, models


class ElearningAutoEnrollmentLog(models.Model):
    _name = "elearning.auto.enrollment.log"
    _description = "Auto Enrollment Log"
    _order = "run_date desc, id desc"

    employee_id = fields.Many2one("hr.employee", ondelete="set null", index=True)
    partner_id = fields.Many2one("res.partner", ondelete="set null", index=True)
    matrix_id = fields.Many2one("elearning.training.matrix", ondelete="set null", index=True)
    program_id = fields.Many2one("elearning.program", ondelete="set null", index=True)
    status = fields.Selection(
        [
            ("success", "Success"),
            ("skipped", "Skipped"),
            ("error", "Error"),
        ],
        required=True,
        index=True,
    )
    message = fields.Text(required=True)
    run_date = fields.Datetime(default=fields.Datetime.now, required=True, index=True)
