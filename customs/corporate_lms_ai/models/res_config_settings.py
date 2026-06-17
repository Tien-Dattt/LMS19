# -*- coding: utf-8 -*-

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    corporate_lms_ai_provider = fields.Selection(
        [
            ("openai", "OpenAI"),
            ("google", "Google Gemini"),
        ],
        string="Corporate LMS AI Provider",
        config_parameter="corporate_lms_ai.provider",
        groups="base.group_system",
    )
    corporate_lms_ai_model = fields.Char(
        string="Corporate LMS AI Model",
        config_parameter="corporate_lms_ai.model",
        groups="base.group_system",
    )
    corporate_lms_ai_endpoint = fields.Char(
        string="Corporate LMS AI Endpoint",
        config_parameter="corporate_lms_ai.endpoint",
        groups="base.group_system",
    )
