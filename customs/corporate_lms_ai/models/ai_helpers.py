# -*- coding: utf-8 -*-

import re

from markupsafe import escape

from odoo import _
from odoo.exceptions import AccessError, UserError
from odoo.tools.mail import html_to_inner_content


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


def _has_ai_manager_access(env, groups=None):
    groups = groups or AI_MANAGER_GROUPS
    return env.su or any(env.user.has_group(group) for group in groups)


def _check_ai_manager_access(record, groups=None, message=None):
    if _has_ai_manager_access(record.env, groups):
        return
    raise AccessError(_(message or "You are not allowed to run Corporate LMS AI actions."))


def _get_lms_ai_generation_config(record, agent=None):
    if not agent:
        raise UserError(_("Set an AI Agent before generating Corporate LMS AI draft content."))

    agent.ensure_one()

    if "llm_model" in agent._fields and not agent.llm_model:
        raise UserError(_(
            "Configure an AI model on the selected AI Agent before generating Corporate LMS AI draft content."
        ))

    try:
        provider = agent._get_provider() if hasattr(agent, "_get_provider") else "odoo_ai_agent"
    except Exception as error:
        raise UserError(_(
            "The selected AI Agent cannot resolve a provider from its AI model. "
            "Please check the AI Agent model configuration. Details: %s"
        ) % error)

    return {
        "provider": provider,
        "model": agent.llm_model if "llm_model" in agent._fields else "",
        "endpoint": "managed_by_odoo_ai_agent",
    }


_HTML_TAG_RE = re.compile(
    r"</?(p|br|ul|ol|li|h[1-6]|div|section|article|strong|b|em|i|table|thead|tbody|tr|td|th)\b",
    re.IGNORECASE,
)

_CODE_FENCE_RE = re.compile(
    r"```(?:json|html|text)?\s*(.*?)```",
    flags=re.DOTALL | re.IGNORECASE,
)

_BULLET_RE = re.compile(r"^\s*(?:[-*•])\s+(.+)")
_NUMBER_RE = re.compile(r"^\s*(?:\d+[\.\)]|[a-zA-Z][\.\)])\s+(.+)")


def _strip_ai_code_fence(value):
    text = str(value or "").strip()
    fence_match = _CODE_FENCE_RE.search(text)
    if fence_match:
        text = fence_match.group(1).strip()
    return text


def _normalize_ai_whitespace(value):
    text = _strip_ai_code_fence(value)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _looks_like_html(value):
    return bool(_HTML_TAG_RE.search(value or ""))


def _format_ai_html(value):
    """
    Format LLM output for fields.Html.

    If AI returns HTML, keep it.
    If AI returns plain text, convert it into readable HTML:
    paragraphs, bullet lists, numbered lists and emphasized labels.
    """
    text = _normalize_ai_whitespace(value)
    if not text:
        return ""

    if _looks_like_html(text):
        return text

    html_parts = []
    paragraph_lines = []
    list_type = None
    list_items = []

    def flush_paragraph():
        nonlocal paragraph_lines

        if not paragraph_lines:
            return

        raw_joined = " ".join(paragraph_lines).strip()
        paragraph = "<br/>".join(str(escape(line)) for line in paragraph_lines)

        if len(paragraph_lines) == 1 and raw_joined.endswith(":") and len(raw_joined) <= 90:
            html_parts.append("<p><strong>%s</strong></p>" % escape(raw_joined))
        else:
            html_parts.append("<p>%s</p>" % paragraph)

        paragraph_lines = []

    def flush_list():
        nonlocal list_type, list_items

        if not list_items:
            return

        tag = list_type or "ul"
        items_html = "".join(
            "<li>%s</li>" % escape(item)
            for item in list_items
            if item
        )
        html_parts.append("<%s>%s</%s>" % (tag, items_html, tag))

        list_type = None
        list_items = []

    for raw_line in text.splitlines() + [""]:
        line = raw_line.strip()

        if not line:
            flush_paragraph()
            flush_list()
            continue

        bullet_match = _BULLET_RE.match(line)
        number_match = _NUMBER_RE.match(line)

        if bullet_match:
            flush_paragraph()
            if list_type and list_type != "ul":
                flush_list()
            list_type = "ul"
            list_items.append(bullet_match.group(1).strip())
            continue

        if number_match:
            flush_paragraph()
            if list_type and list_type != "ol":
                flush_list()
            list_type = "ol"
            list_items.append(number_match.group(1).strip())
            continue

        if list_items:
            flush_list()

        paragraph_lines.append(line)

    return "\n".join(html_parts)


def _format_ai_text(value):
    """
    Format LLM output for fields.Text.
    """
    text = _normalize_ai_whitespace(value)
    if not text:
        return ""

    if _looks_like_html(text):
        text = html_to_inner_content(text)

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _format_ai_short_text(value, max_length=None):
    """
    Format LLM output for fields.Char.
    """
    text = _format_ai_text(value)
    text = re.sub(r"\s+", " ", text).strip()

    if max_length and len(text) > max_length:
        text = text[:max_length].rstrip() + "..."

    return text