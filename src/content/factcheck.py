"""Checks a finished script against the source article and reports unsupported claims.

Deliberately advisory, not a gate: the result is shown to the human reviewer in Telegram
instead of auto-rejecting the reel. A model judging another model's output is not ground
truth — but "these two sentences aren't in the article" is exactly the hint a reviewer
needs, and it points at the segment instead of making them re-read everything.

Runs on the cheap model and only when a source text actually exists; checking a script
against a bare headline would flag everything and teach the reviewer to ignore it.
"""
from __future__ import annotations

from loguru import logger

import config
from src.content.llm import LLMProvider, parse_json_response
from src.models import ReelScript

_MIN_SOURCE_CHARS = 400

_SYSTEM_PROMPT = """Du prüfst, ob ein Video-Skript durch seinen Quelltext gedeckt ist.

Für JEDES Segment: steht die Aussage so im Quelltext, oder lässt sie sich zwanglos daraus \
ableiten? Melde ein Segment NUR, wenn es eine überprüfbare Tatsachenbehauptung enthält, \
die der Quelltext nicht hergibt — etwa erfundene Zahlen, Hersteller, Produktnamen, \
Mechanismen, Angriffswege oder Zuschreibungen wie "laut X".

NICHT melden: Zuspitzungen, Vereinfachungen, direkte Ansprache, rhetorische Fragen, \
Erklärungen allgemein bekannter Fachbegriffe, Aufrufe zum Folgen, Meinungen ohne \
Tatsachenkern. Sei streng bei Fakten und großzügig beim Ton.

Antworte AUSSCHLIESSLICH mit einem gültigen JSON-Array. Leeres Array, wenn alles gedeckt ist:
[{"i": 2, "claim": "die konkrete unbelegte Aussage", "why": "kurz, warum ungedeckt"}]"""

_USER_TEMPLATE = """QUELLTEXT:
{source}

SKRIPT-SEGMENTE:
{segments}"""


def check_script(script: ReelScript, source_text: str | None,
                 llm: LLMProvider) -> list[str]:
    """Returns one human-readable finding per unsupported segment (empty = all clear)."""
    if not source_text or len(source_text) < _MIN_SOURCE_CHARS:
        return []

    segments = "\n".join(f"[{i}] {s.text}" for i, s in enumerate(script.segments))
    raw = llm.complete(
        system=_SYSTEM_PROMPT,
        user=_USER_TEMPLATE.format(source=source_text[:6000], segments=segments),
        model=config.CLAUDE_MODEL_FAST,
        max_tokens=800,
        purpose="fact_check",
    )
    data = parse_json_response(raw)
    if not isinstance(data, list):
        logger.warning("Faktencheck verworfen (keine JSON-Liste)")
        return []

    findings: list[str] = []
    for entry in data:
        try:
            index = int(entry["i"])
            if not 0 <= index < len(script.segments):
                continue
            claim = str(entry.get("claim", "")).strip()
            why = str(entry.get("why", "")).strip()
        except (KeyError, TypeError, ValueError):
            continue
        findings.append(f"Segment {index + 1}: „{claim[:110]}“ — {why[:110]}")

    if findings:
        logger.warning(f"Faktencheck: {len(findings)} von {len(script.segments)} "
                       f"Segmenten nicht durch die Quelle gedeckt")
    return findings
