"""System prompts + compliance guardrails for community auto-replies.

All channel-specific content (prompts, advice-pattern regex, fallback templates)
lives in the active channel profile (config.PROFILE); this module keeps the stable
API — violates_compliance, COMMENT_SYSTEM, DM_SYSTEM, suggest_template — so the
classifier/guard/pipelines stay channel-agnostic.
"""
import re

import config

# Words that make a reply read like advice — a hard code-level safety net (mirrors
# the disclaimer append in script_agent.py). Any auto-reply matching these is
# discarded and the item is escalated to Telegram instead.
_ADVICE_PATTERNS = re.compile(config.PROFILE.ADVICE_PATTERN, re.IGNORECASE)


def violates_compliance(text: str) -> bool:
    """True if a drafted reply reads like a buy/sell/target recommendation."""
    return bool(_ADVICE_PATTERNS.search(text or ""))


COMMENT_SYSTEM = config.PROFILE.COMMENT_SYSTEM

DM_SYSTEM = config.PROFILE.DM_SYSTEM

# Zero-LLM fallback templates (keyword-matched) when the Claude budget is exhausted.
# Only ever used to *suggest* a reply in a Telegram escalation, never auto-sent.
TEMPLATE_FALLBACKS = config.PROFILE.TEMPLATE_FALLBACKS


def suggest_template(text: str) -> str:
    """Pick a keyword-matched fallback suggestion (budget-exhausted path).
    Keyword groups come from the profile; first matching group wins."""
    low = (text or "").lower()
    for key, words in config.PROFILE.FALLBACK_KEYWORDS:
        if any(w in low for w in words):
            return TEMPLATE_FALLBACKS[key]
    return TEMPLATE_FALLBACKS["default"]
