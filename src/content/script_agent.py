"""Generates the German reel script (Sonnet): hook-first structure, retention
pacing, CTA — the channel-specific system prompt (tone, domain, compliance) comes
from the active channel profile."""
from loguru import logger

import config
from src.content.llm import LLMProvider, parse_json_response
from src.models import ReelScript, ScriptSegment, TrendItem

# German speech pace ≈ 2.4 words/second — keeps the voiceover inside the target length
_WORDS_PER_SECOND = 2.4

_DISCLAIMER = config.PROFILE.REEL_DISCLAIMER

_SYSTEM_PROMPT = config.PROFILE.REEL_SYSTEM_PROMPT

_USER_TEMPLATE = """Schreibe ein Reel-Skript zu diesem Trend-Thema:

Thema: {title}
Kontext: {summary}
Quelle: {source}

Ziellänge gesprochen: ~{target_words} Wörter (≈ {target_seconds} Sekunden).

Gib genau diese JSON-Struktur zurück:
{{
  "title": "interner Arbeitstitel",
  "segments": [
    {{"text": "Hook-Satz auf Deutsch", "broll": "english footage keywords"}},
    {{"text": "…", "broll": "…"}}
  ],
  "caption": "Instagram-Caption auf Deutsch, 2-4 Zeilen, mit Disclaimer am Ende",
  "hashtags": [{hashtag_hint}]
}}"""


def generate_script(trend: TrendItem, llm: LLMProvider) -> ReelScript | None:
    target_words = int(config.REEL_TARGET_SECONDS * _WORDS_PER_SECOND)
    raw = llm.complete(
        system=_SYSTEM_PROMPT.format(disclaimer=_DISCLAIMER, brand=config.BRAND_NAME),
        user=_USER_TEMPLATE.format(
            title=trend.title,
            summary=trend.summary or "(kein weiterer Kontext)",
            source=trend.source,
            target_words=target_words,
            target_seconds=config.REEL_TARGET_SECONDS,
            hashtag_hint=config.PROFILE.REEL_HASHTAG_HINT,
        ),
        model=config.CLAUDE_MODEL,
        max_tokens=1500,
        purpose="generate_script",
    )
    data = parse_json_response(raw)
    if not isinstance(data, dict):
        return None

    try:
        segments = [
            ScriptSegment(text=str(s["text"]).strip(), broll_query=str(s.get("broll", "")).strip())
            for s in data["segments"]
            if str(s.get("text", "")).strip()
        ]
    except (KeyError, TypeError):
        logger.warning("Skript verworfen: 'segments' fehlt oder ist fehlerhaft")
        return None
    if len(segments) < 2:
        logger.warning("Skript verworfen: weniger als 2 Segmente")
        return None

    caption = str(data.get("caption", "")).strip()
    # Compliance safety net: the disclaimer must survive even a sloppy model response
    if config.PROFILE.DISCLAIMER_CHECK not in caption.lower():
        caption = f"{caption}\n\n{_DISCLAIMER}".strip()

    hashtags = [
        h if h.startswith("#") else f"#{h}"
        for h in (str(x).strip() for x in data.get("hashtags", []))
        if h and " " not in h
    ]

    return ReelScript(
        hook=segments[0].text,
        segments=segments,
        caption=caption,
        hashtags=hashtags[:15],
        title=str(data.get("title", trend.title))[:120],
    )
