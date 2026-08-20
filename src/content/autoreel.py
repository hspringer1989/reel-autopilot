"""Vollautomatische Reel-Produktion: Recherche → Skript → Opener → Rendern.

Das ist der Pfad, der die Handarbeit nachbildet. Der bestehende `generate_once()`
bleibt daneben unangetastet — er baut aus einem RSS-Trend, ohne Recherche und ohne
Opener-Urteil, und ist weiterhin das Sicherheitsnetz, wenn dieser Pfad nichts findet.

Ablauf und die Stelle, an der jeweils abgebrochen wird:
  1. Rückschau  → Ziellänge aus der Sehdauer des letzten Reels
  2. Recherche  → Thema + geprüfte Fakten     (kein Thema belegbar → Abbruch)
  3. Skript     → Segmente aus DIESEN Fakten  (kein Skript → Abbruch)
  4. Opener     → per Augenschein gewählt     (kein Kandidat → Abbruch)
  5. Rendern    → Video + Telegram-Freigabe

Jeder Abbruch ist bewusst hart: Ein Tag ohne Reel kostet wenig, ein Reel mit
falschen Zahlen oder einem themenfremden Startbild kostet Vertrauen.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger
from sqlalchemy import select

import config
from src.content.llm import LLMProvider, get_llm, parse_json_response
from src.content.opener import pick_opener
from src.content.research import Research, research_topic
from src.models import ReelScript, ScriptSegment
from src.storage.database import ReelRow, session_scope

_SCRIPT_SYSTEM = """Du schreibst das Sprechskript für ein deutsches Finanz-Reel.

HARTE REGELN (aus der Auswertung des Kanals, jede einzeln belegt):

LÄNGE UND AUFBAU
- Ziellänge wird vorgegeben. Rechne mit rund 2,3 gesprochenen Wörtern pro Sekunde.
- Die AUFLÖSUNG steht in den ersten zehn Sekunden, nicht der Aufbau. Erst die
  Pointe, dann der Beleg. Gemessen: die Sehdauer entscheidet über die Reichweite,
  und wer erst aufbaut, verliert die Zuschauer vor der Pointe.
- Der erste Satz ist kürzer als zwölf Wörter und nennt die überraschende oder
  schlechte Seite zuerst, nie die harmlose Entwarnung.

SPRECHBARKEIT (das häufigste Problem, viermal vom Nutzer kritisiert)
- Nur vollständige Sätze. Keine verblosen Bruchstücke — die Engine rät sonst die
  Betonung und rät hörbar falsch.
- Höchstens EIN Gedankenstrich im ganzen Skript. Kontraste über "nicht X, sondern Y".
- Jede Zahl als WORT ausschreiben, nie als Ziffer.
- Keine Zahl ohne Einheit ("zwei Komma acht Prozent", nicht "zwei Komma acht").
- Keine Wortungetüme. Lieber runden: "ein Komma fünfundneunzig Prozent" wird zu
  "knapp zwei Prozent". Die genaue Zahl steht ohnehin im Bild.
- Kein ausgelassenes Verb im zweiten Teilsatz.
- Höchstens ein Doppelpunkt-Einstieg. Keine Floskeln wie "Heute zeige ich euch".

INHALT
- Nur die übergebenen Fakten verwenden. Nichts dazuerfinden, nichts ausschmücken.
- Bei Zeitbezügen das konkrete Datum nennen.
- Das letzte Segment enthält das Aha und endet mit "Folge für Börse, die man versteht!"

Antworte ausschließlich mit diesem JSON:
{"title": "Titel für die Ankündigungs-Story",
 "segments": ["Segment 1", "Segment 2", "..."],
 "caption": "Instagram-Caption mit Zahlen, Quellen und Disclaimer",
 "opener_queries": ["englische Pexels-Suchbegriffe für ein helles, thematisch
   passendes Startbild mit klarem Motiv", "..."]}"""


@dataclass
class AutoReel:
    reel_id: int | None
    note: str


def _recent_topics(limit: int = 12) -> list[str]:
    """Zuletzt gebaute Themen — Ausschlussliste gegen Wiederholung."""
    topics: list[str] = []
    with session_scope() as session:
        rows = session.execute(
            select(ReelRow).where(ReelRow.script_json.is_not(None))
            .order_by(ReelRow.id.desc()).limit(limit)
        ).scalars().all()
        for row in rows:
            try:
                data = json.loads(row.script_json)
            except Exception:  # noqa: BLE001
                continue
            label = data.get("topic") or data.get("title")
            if label:
                topics.append(str(label))
    return topics


def _used_opener_ids(limit: int = 40) -> set[int]:
    """Bereits verwendete Opener-Clips. Harter Filter; die Motivklassen-Regel
    kommt zusätzlich als Prosa in den Auswahl-Prompt."""
    used: set[int] = set()
    with session_scope() as session:
        rows = session.execute(
            select(ReelRow).where(ReelRow.script_json.is_not(None))
            .order_by(ReelRow.id.desc()).limit(limit)
        ).scalars().all()
        for row in rows:
            try:
                vid = json.loads(row.script_json).get("opener_id")
            except Exception:  # noqa: BLE001
                continue
            if isinstance(vid, int):
                used.add(vid)
    return used


def _opener_history_note(limit: int = 10) -> str:
    """Motivklassen der letzten Opener in Prosa, für den Auswahl-Prompt."""
    notes: list[str] = []
    with session_scope() as session:
        rows = session.execute(
            select(ReelRow).where(ReelRow.script_json.is_not(None))
            .order_by(ReelRow.id.desc()).limit(limit)
        ).scalars().all()
        for row in rows:
            try:
                data = json.loads(row.script_json)
            except Exception:  # noqa: BLE001
                continue
            if data.get("opener_look"):
                notes.append(str(data["opener_look"]))
    return "\n".join(f"- {n}" for n in notes)


def _write_script(llm: LLMProvider, research: Research,
                  target_seconds: int) -> dict | None:
    words = int(target_seconds * 2.3)
    user = (
        f"Thema: {research.topic}\n"
        f"Aufhänger: {research.why_now}\n"
        f"Alltagsrelevanz: {research.relevance}\n"
        f"Das Aha zum Schluss: {research.aha}\n\n"
        f"GEPRÜFTE FAKTEN (nur diese verwenden):\n"
        + "\n".join(f"- {f}" for f in research.facts)
        + f"\n\nQuellen für die Caption: {'; '.join(research.sources[:4])}\n"
        f"\nZiellänge: rund {target_seconds} Sekunden, also etwa {words} Wörter "
        f"gesprochen, verteilt auf vier Segmente.\n"
        f"Disclaimer für die Caption: {config.PROFILE.REEL_DISCLAIMER}"
    )
    data = parse_json_response(llm.complete(
        system=_SCRIPT_SYSTEM, user=user, model=config.CLAUDE_MODEL,
        max_tokens=2500, purpose="auto_reel_script",
    ))
    if not isinstance(data, dict) or not data.get("segments"):
        return None
    return data


async def generate_autonomous_reel(target_seconds: int = 40) -> AutoReel:
    """Der volle Weg. Gibt bei jedem Abbruch eine Begründung zurück, die per
    Telegram gemeldet werden kann — ein stiller Ausfall wäre schlimmer als keiner."""
    from src.render.renderer import pick_music, render_reel
    from src.tts.base import get_tts

    llm = get_llm()
    day_label = datetime.now().strftime("%d.%m.%Y")

    research = research_topic(llm, day_label, recent_topics=_recent_topics())
    if not research.ok:
        return AutoReel(None, f"Kein belastbares Thema: {research.note}")

    script_data = _write_script(llm, research, target_seconds)
    if script_data is None:
        return AutoReel(None, f"Skript fehlgeschlagen (Thema: {research.topic})")

    queries = [str(q) for q in (script_data.get("opener_queries") or [])][:5]
    if not queries:
        queries = [research.topic]
    choice = pick_opener(
        llm, research.topic, queries,
        exclude_ids=_used_opener_ids(), history_note=_opener_history_note(),
    )
    if choice.path is None:
        return AutoReel(None, f"Kein passender Opener gefunden: {choice.reason}")

    texts = [str(s) for s in script_data["segments"] if str(s).strip()]
    title = str(script_data.get("title") or research.title)
    caption = str(script_data.get("caption") or research.topic)

    segments = [ScriptSegment(text=t, broll_query="") for t in texts]
    script = ReelScript(hook=texts[0], segments=segments, caption=caption,
                        hashtags=[], title=title)

    with session_scope() as session:
        reel = ReelRow(
            trend_id=0,
            script_json=json.dumps({
                "topic": research.topic, "title": title, "texts": texts,
                "facts": research.facts, "sources": research.sources,
                "opener_id": choice.video_id, "opener_look": choice.reason,
                "autonomous": True,
            }, ensure_ascii=False),
            caption=caption, status="draft")
        session.add(reel); session.flush(); reel_id = reel.id

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    base = Path(config.OUTPUT_DIR) / f"reel_{reel_id}_{stamp}"
    tts = get_tts().synthesize(script.full_text, base.with_suffix(".mp3"))

    # Ein B-Roll-Eintrag je Segment: Opener zuerst, danach der Rest als Farbverlauf.
    # Gezeichnete Datenframes wie in der Handarbeit kann dieser Pfad noch nicht —
    # siehe Hinweis in der PR-Beschreibung.
    broll = [choice.path] + [None] * (len(texts) - 1)
    video = render_reel(script, tts, broll, base.with_suffix(".mp4"), pick_music())

    with session_scope() as session:
        row = session.get(ReelRow, reel_id)
        row.audio_path = tts.audio_path
        row.video_path = str(video)
        row.status = "pending_review"

    logger.info(f"Autonomes Reel #{reel_id} fertig: {research.topic}")
    return AutoReel(reel_id, f"{research.topic} (Opener {choice.video_id})")
