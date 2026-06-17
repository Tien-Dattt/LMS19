# -*- coding: utf-8 -*-

import os

from odoo import _
from odoo.exceptions import AccessError, UserError


AI_MANAGER_GROUPS = (
    "base.group_system",
    "corporate_lms_base.group_corporate_lms_admin",
    "corporate_lms_base.group_corporate_lms_training_manager",
)
AI_TRAINING_GROUPS = (
    *AI_MANAGER_GROUPS,
    "corporate_lms_base.group_corporate_lms_instructor",
)
AI_INSTRUCTOR_GROUP = "corporate_lms_base.group_corporate_lms_instructor"

AI_PROVIDER_API_CONFIG = {
    "openai": ("ai.openai_key", "ODOO_AI_CHATGPT_TOKEN"),
    "google": ("ai.google_key", "ODOO_AI_GEMINI_TOKEN"),
}


def _has_ai_manager_access(env, groups=None):
    groups = groups or AI_MANAGER_GROUPS
    return env.su or any(env.user.has_group(group) for group in groups)


def _check_ai_manager_access(record, groups=None, message=None):
    if _has_ai_manager_access(record.env, groups):
        return
    raise AccessError(_(message or "You are not allowed to run Corporate LMS AI actions."))


def _get_lms_ai_generation_config(record, agent=None):
    """Validate Corporate LMS AI generation prerequisites without mutating draft fields."""
    params = record.env["ir.config_parameter"].sudo()
    provider = (params.get_param("corporate_lms_ai.provider") or "").strip()
    model = (params.get_param("corporate_lms_ai.model") or "").strip()
    endpoint = (params.get_param("corporate_lms_ai.endpoint") or "").strip()

    if not provider:
        raise UserError(_("Configure the Corporate LMS AI provider before generating AI draft content."))
    if provider not in AI_PROVIDER_API_CONFIG:
        raise UserError(_("Unsupported Corporate LMS AI provider: %s.") % provider)
    if not model:
        raise UserError(_("Configure the Corporate LMS AI model before generating AI draft content."))
    if not endpoint:
        raise UserError(_("Configure the Corporate LMS AI endpoint before generating AI draft content."))

    api_key_param, api_key_env = AI_PROVIDER_API_CONFIG[provider]
    api_key = (params.get_param(api_key_param) or os.getenv(api_key_env) or "").strip()
    if not api_key:
        raise UserError(_("Configure the %s API key in Odoo AI settings before generating Corporate LMS AI draft content.") % provider)

    if agent and "llm_model" in agent._fields and not agent.llm_model:
        raise UserError(_("Configure an AI model on the selected AI Agent before generating Corporate LMS AI draft content."))

    return {
        "provider": provider,
        "model": model,
        "endpoint": endpoint,
    }


def _raise_ai_unavailable():
    raise UserError(_("AI generation is not configured for Corporate LMS yet. The existing draft fields were left unchanged."))
