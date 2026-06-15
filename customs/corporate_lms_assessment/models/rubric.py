# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ElearningRubric(models.Model):
    _name = "elearning.rubric"
    _description = "Rubric"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name, id"

    name = fields.Char(required=True, tracking=True, translate=True)
    description = fields.Html(translate=True)
    criteria_ids = fields.One2many(
        "elearning.rubric.criteria",
        "rubric_id",
        string="Criteria",
        copy=True,
    )
    max_score = fields.Float(
        compute="_compute_max_score",
        store=True,
        tracking=True,
    )
    active = fields.Boolean(default=True)

    @api.depends("criteria_ids.max_score")
    def _compute_max_score(self):
        for rubric in self:
            rubric.max_score = sum(rubric.criteria_ids.mapped("max_score"))


class ElearningRubricCriteria(models.Model):
    _name = "elearning.rubric.criteria"
    _description = "Rubric Criteria"
    _order = "rubric_id, sequence, id"

    rubric_id = fields.Many2one(
        "elearning.rubric",
        required=True,
        ondelete="cascade",
        index=True,
    )
    name = fields.Char(required=True, translate=True)
    description = fields.Text(translate=True)
    max_score = fields.Float(required=True)
    sequence = fields.Integer(default=10)

    @api.constrains("max_score")
    def _check_max_score(self):
        for criteria in self:
            if criteria.max_score < 0:
                raise ValidationError(_("Criteria maximum score must be zero or greater."))
