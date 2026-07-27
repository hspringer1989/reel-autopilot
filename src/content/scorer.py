"""Scores trend candidates in one cheap batch call (Haiku):
viral potential × niche fit × monetizability. What those three mean — and which topics
count as off-niche — comes from the active channel profile, so the same code serves a
finance channel and an IT channel."""
from loguru import logger

import config
from src.content.llm import LLMProvider, parse_json_response
from src.models import TrendItem, TrendScore

_MAX_BATCH = 25

# Nische, Ausschlusskriterien und Tonfall der Bewertung sind kanalabhängig und stehen
# im aktiven Profil (channels/<CHANNEL>/profile.py).
_SYSTEM_PROMPT = config.PROFILE.SCORER_SYSTEM_PROMPT

_USER_TEMPLATE = """Bewerte diese Themen-Kandidaten:

{items}

Gib genau diese JSON-Struktur zurück (ein Objekt pro Kandidat, "i" = Index aus der Liste):
[{{"i": 0, "viral": 0.7, "fit": 0.9, "monetization": 0.6, "reasoning": "1 Satz auf Deutsch"}}]"""


def score_trends(trends: list[TrendItem], llm: LLMProvider) -> list[TrendScore | None]:
    """Returns one score per input trend (None where the model skipped/failed)."""
    scores: list[TrendScore | None] = [None] * len(trends)
    for offset in range(0, len(trends), _MAX_BATCH):
        batch = trends[offset:offset + _MAX_BATCH]
        listing = "\n".join(
            f"[{i}] ({t.source}) {t.title}" + (f" — {t.summary[:150]}" if t.summary else "")
            for i, t in enumerate(batch)
        )
        raw = llm.complete(
            system=_SYSTEM_PROMPT,
            user=_USER_TEMPLATE.format(items=listing),
            model=config.CLAUDE_MODEL_FAST,
            max_tokens=2500,
            purpose="score_trends",
        )
        data = parse_json_response(raw)
        if not isinstance(data, list):
            logger.warning("Trend-Scoring-Batch verworfen (keine JSON-Liste)")
            continue
        for entry in data:
            try:
                i = int(entry["i"])
                if not 0 <= i < len(batch):
                    continue
                scores[offset + i] = TrendScore(
                    viral_potential=min(1.0, max(0.0, float(entry["viral"]))),
                    niche_fit=min(1.0, max(0.0, float(entry["fit"]))),
                    monetization=min(1.0, max(0.0, float(entry["monetization"]))),
                    reasoning=str(entry.get("reasoning", "")),
                )
            except (KeyError, TypeError, ValueError):
                continue
    return scores
