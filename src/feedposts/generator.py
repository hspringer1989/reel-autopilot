"""Generates an educational carousel feed post from a topic via one budget-gated
Claude call (Sonnet). Same JSON-robustness discipline as the stock analyzer
(no inner quotes, strict=False, one retry). Compliance: educational, no advice."""
from __future__ import annotations

import json

from loguru import logger

import config
from src.content.llm import LLMProvider, parse_json_response
from src.content.usage import claude_budget_exceeded
from src.models import FeedPost, Slide

_DISCLAIMER = config.PROFILE.FEED_DISCLAIMER

_BANNED = config.PROFILE.FEED_BANNED_PHRASES

_SYSTEM_PROMPT = config.PROFILE.FEED_SYSTEM_PROMPT

_USER_TEMPLATE = """Erstelle einen edukativen Instagram-Carousel-Beitrag.

Thema: {title}
Inhaltliche Leitplanken: {brief}

Gib genau diese JSON-Struktur zurück:
{{
  "title": "knackiger Titel für Slide 1",
  "slides": [
    {{"heading": "kurze Überschrift", "body": "2-4 knappe, einfache Sätze"}}
  ],
  "caption": "Instagram-Caption (2-4 Zeilen) mit Disclaimer am Ende",
  "hashtags": [{hashtag_hint}]
}}
Die erste Slide ist der Hook, die letzte Slide die Zusammenfassung. 5-10 Slides — bei \
detaillierten Anleitungen lieber mehr und konkreter."""


def _sanitise(text: str) -> str:
    cleaned = text.strip()
    low = cleaned.lower()
    for bad in _BANNED:
        if bad in low:
            logger.warning(f"Feed-Text enthielt '{bad}' — neutralisiert")
            idx = low.find(bad)
            cleaned = cleaned[:idx] + "so funktioniert" + cleaned[idx + len(bad):]
            low = cleaned.lower()
    return cleaned


def build_feed_post(topic_slug: str, title: str, brief: str, llm: LLMProvider) -> FeedPost | None:
    """One budget-gated Claude call → a FeedPost, or None if unavailable/invalid."""
    if claude_budget_exceeded():
        logger.warning("Claude-Budget erschöpft — kein Feed-Post generiert")
        return None

    user = _USER_TEMPLATE.format(title=title, brief=brief,
                                 hashtag_hint=config.PROFILE.FEED_HASHTAG_HINT)
    data = None
    for attempt in range(2):
        try:
            raw = llm.complete(
                system=_SYSTEM_PROMPT, user=user,
                model=config.CLAUDE_MODEL, max_tokens=3400, purpose="feed_post",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Feed-Generierung fehlgeschlagen ({exc})")
            return None
        data = parse_json_response(raw)
        if isinstance(data, dict) and data.get("slides"):
            break
        logger.warning(f"Feed-JSON ungültig (Versuch {attempt + 1}/2)")
    if not isinstance(data, dict) or not data.get("slides"):
        return None

    slides = [
        Slide(heading=_sanitise(str(s.get("heading", "")).strip()),
              body=_sanitise(str(s.get("body", "")).strip()))
        for s in data["slides"]
        if isinstance(s, dict) and str(s.get("body", "")).strip()
    ]
    if len(slides) < 3:
        logger.warning("Feed-Post verworfen: weniger als 3 Slides")
        return None

    caption = _sanitise(str(data.get("caption", "")).strip())
    # A tappable @mention of our own profile — the real "link" to follow (feed-post
    # images can't carry a clickable button).
    if config.BRAND_HANDLE and config.BRAND_HANDLE.lower() not in caption.lower():
        caption = f"{caption}\n\nFolge {config.BRAND_HANDLE} für mehr 📈".strip()
    if config.PROFILE.DISCLAIMER_CHECK not in caption.lower():
        caption = f"{caption}\n\n⚠️ {_DISCLAIMER}".strip()

    hashtags = [
        h if h.startswith("#") else f"#{h}"
        for h in (str(x).strip() for x in data.get("hashtags", []))
        if h and " " not in h
    ]
    return FeedPost(
        topic_slug=topic_slug,
        title=_sanitise(str(data.get("title", title)).strip()) or title,
        slides=slides[:10],
        caption=caption,
        hashtags=hashtags[:12],
    )
