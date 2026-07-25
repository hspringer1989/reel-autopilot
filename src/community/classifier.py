"""Haiku-based classification + reply drafting for comments and DMs.

One batched call per comment poll cycle (like scorer.py); one call per new DM with
thread context. Budget-gated through the existing LLMProvider — on BudgetExceeded the
caller escalates with a template suggestion instead of bypassing the cap.

Safety net: any drafted reply that reads like advice (prompts.violates_compliance)
is stripped and the item forced to `sensitive` so it can only go out via human review.
"""
from dataclasses import dataclass

from loguru import logger

import config
from src.community import prompts
from src.content.llm import LLMProvider, parse_json_response
from src.storage.database import COMMUNITY_CLASSES

_MAX_BATCH = 20


@dataclass
class Classification:
    classification: str          # harmless | substantive | sensitive | spam
    confidence: float            # 0.0–1.0
    reply: str                   # drafted German reply ("" for spam)


def _sanitise(cls: str, confidence: float, reply: str) -> Classification:
    """Clamp/validate model output and apply the compliance safety net."""
    cls = cls if cls in COMMUNITY_CLASSES else "sensitive"
    conf = min(1.0, max(0.0, float(confidence)))
    reply = (reply or "").strip()
    if cls == "spam":
        reply = ""
    elif reply and prompts.violates_compliance(reply):
        # A reply that reads like advice must never auto-send: force human review.
        logger.warning("Community-Antwort als Anlageberatung erkannt → eskaliert")
        cls, conf, reply = "sensitive", min(conf, 0.0), ""
    return Classification(cls, conf, reply)


def _brand_system(base: str) -> str:
    # .replace (not .format) so the literal JSON braces in the prompts stay intact.
    return base.replace("{brand}", config.BRAND_NAME).replace("{handle}", config.BRAND_HANDLE)


def classify_comments(
    items: list[dict], llm: LLMProvider
) -> list[Classification | None]:
    """items: [{text, media_context}]. Returns one Classification per item
    (None where the model skipped/failed). Batched to keep costs down."""
    results: list[Classification | None] = [None] * len(items)
    for offset in range(0, len(items), _MAX_BATCH):
        batch = items[offset:offset + _MAX_BATCH]
        listing = "\n".join(
            f"[{i}] (unter: {it.get('media_context', '')[:80]}) {it['text']}"
            for i, it in enumerate(batch)
        )
        user = (
            "Klassifiziere und beantworte diese Kommentare:\n\n" + listing +
            '\n\nGib genau dieses JSON zurück (ein Objekt pro Kommentar):\n'
            '[{"i": 0, "class": "harmless", "confidence": 0.9, "reply": "…"}]'
        )
        raw = llm.complete(
            system=_brand_system(prompts.COMMENT_SYSTEM),
            user=user,
            model=config.CLAUDE_MODEL_FAST,
            max_tokens=2000,
            purpose="community_comments",
        )
        data = parse_json_response(raw)
        if not isinstance(data, list):
            logger.warning("Community-Kommentar-Batch verworfen (keine JSON-Liste)")
            continue
        for entry in data:
            try:
                i = int(entry["i"])
                if not 0 <= i < len(batch):
                    continue
                results[offset + i] = _sanitise(
                    str(entry.get("class", "")),
                    entry.get("confidence", 0.0),
                    str(entry.get("reply", "")),
                )
            except (KeyError, TypeError, ValueError):
                continue
    return results


def classify_dm(
    text: str, thread_context: list[str], llm: LLMProvider
) -> Classification | None:
    """Classify + draft a reply for one inbound DM, given prior thread messages."""
    context = "\n".join(f"- {m}" for m in thread_context[-6:]) or "(keine Vorgeschichte)"
    user = (
        f"Bisheriger Verlauf:\n{context}\n\n"
        f"Neue Nachricht des Nutzers:\n{text}\n\n"
        'Gib genau dieses JSON zurück: '
        '{"class": "harmless", "confidence": 0.9, "reply": "…"}'
    )
    raw = llm.complete(
        system=_brand_system(prompts.DM_SYSTEM),
        user=user,
        model=config.CLAUDE_MODEL_FAST,
        max_tokens=800,
        purpose="community_dm",
    )
    data = parse_json_response(raw)
    if not isinstance(data, dict):
        logger.warning("Community-DM-Antwort verworfen (kein JSON-Objekt)")
        return None
    return _sanitise(
        str(data.get("class", "")),
        data.get("confidence", 0.0),
        str(data.get("reply", "")),
    )
