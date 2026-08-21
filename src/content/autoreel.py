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
from src.content.research import Research, research_topic, research_week_ahead
from src.models import ReelScript, ScriptSegment
from src.storage.database import ReelRow, session_scope

_SCRIPT_SYSTEM = """Du schreibst das Sprechskript für ein deutsches Finanz-Reel.

HARTE REGELN (aus der Auswertung des Kanals, jede einzeln belegt):

LÄNGE UND AUFBAU
- Ziellänge wird vorgegeben. Rechne mit rund 1,95 gesprochenen Wörtern pro Sekunde
  (ausgeschriebene Zahlwörter kosten Zeit). Lieber kürzer als länger.
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


def ist_vorschautag(jetzt: datetime) -> bool:
    """Wird an diesem Abend die Sonntags-Wochenvorschau gebaut?

    Die Automatik baut abends fuer den FOLGETAG. Die Vorschau soll sonntags
    erscheinen, gebaut wird sie also am Samstag. weekday(): Montag 0 ... Samstag 5.
    """
    return jetzt.weekday() == 5


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


_EINER = ("", "ein", "zwei", "drei", "vier", "fünf", "sechs", "sieben", "acht", "neun")
_ZEHNER = ("", "zehn", "zwanzig", "dreißig", "vierzig", "fünfzig",
           "sechzig", "siebzig", "achtzig", "neunzig")
_TEENS = ("zehn", "elf", "zwölf", "dreizehn", "vierzehn", "fünfzehn",
          "sechzehn", "siebzehn", "achtzehn", "neunzehn")


def jahr_als_wort(jahr: int) -> str:
    """Jahreszahl ab 2000 als deutsches Zahlwort, so wie es gesprochen wird."""
    rest = jahr - 2000
    if rest == 0:
        return "zweitausend"
    if rest < 10:
        return "zweitausend" + _EINER[rest]
    if rest < 20:
        return "zweitausend" + _TEENS[rest - 10]
    zehner, einer = divmod(rest, 10)
    if einer == 0:
        return "zweitausend" + _ZEHNER[zehner]
    return f"zweitausend{_EINER[einer]}und{_ZEHNER[zehner]}"


def _norm_jahr(wort: str) -> str:
    """Schreibvarianten desselben Jahres angleichen.

    Das Modell schreibt mal "zweitausendsechsundzwanzig", mal
    "zweitausendundsechsundzwanzig". Dieselbe Zahl — ohne Angleichung gaebe das
    einen Fehlalarm, und ein Fehlalarm pro Lauf kostet einen Korrekturdurchgang.
    """
    w = wort.lower().replace("ß", "ss")
    if w.startswith("zweitausendund"):
        w = "zweitausend" + w[len("zweitausendund"):]
    return w


def _jahre_im_text(text: str) -> set[str]:
    """Alle ausgeschriebenen 'zweitausend…'-Formen im Sprechtext."""
    gefunden: set[str] = set()
    klein = text.lower()
    start = 0
    while (i := klein.find("zweitausend", start)) != -1:
        ende = i + len("zweitausend")
        while ende < len(klein) and klein[ende].isalpha():
            ende += 1
        gefunden.add(klein[i:ende])
        start = ende
    return gefunden


def check_script_rules(texts: list[str], facts: list[str] | None = None) -> list[str]:
    """Prueft die harten Sprechregeln nach. Gibt die Verstoesse in Klartext zurueck.

    Der Prompt bittet um diese Regeln, aber eine Bitte ist keine Zusicherung: das
    Skript von Reel #107 (21.08.2026) hatte vier Gedankenstriche statt einem und
    benutzte "PMI" ungeklaert. Beides sind belegte Ursachen — Gedankenstriche fuer
    schiefe Betonung, Fachbegriffe fuer Abspringen in den ersten Sekunden.
    """
    voll = " ".join(texts)
    verstoesse: list[str] = []

    striche = voll.count("—") + voll.count(" – ")
    if striche > 1:
        verstoesse.append(
            f"{striche} Gedankenstriche, erlaubt ist einer. Ersetze sie durch "
            f"eigene Saetze oder durch 'nicht X, sondern Y'.")

    if any(ch.isdigit() for ch in voll):
        ziffern = "".join(ch if ch.isdigit() else " " for ch in voll).split()
        verstoesse.append(
            f"Ziffern im Sprechtext ({', '.join(ziffern[:5])}). Zahlen werden "
            f"ausgeschrieben; die Ziffern stehen im Bild.")

    for kuerzel in ("PMI", "KGV", "RSI", "ETF", "BIP", "EBIT", "ROI", "IPO"):
        if kuerzel in voll:
            verstoesse.append(
                f"'{kuerzel}' ist ein Fachkuerzel. Umschreibe es in Alltagssprache, "
                f"die Schreibweise kann auf dem Bild stehen.")

    if voll.count(":") > 1:
        verstoesse.append("Mehr als ein Doppelpunkt-Einstieg — klingt wie eine Liste.")

    # Ausgeschriebene Jahreszahlen gegen die belegten Fakten halten. Bei #108 wurde
    # aus 2026 beim Ausschreiben "zweitausendundzwanzig" — Form korrekt, Jahr falsch.
    if facts:
        erlaubt = set()
        for f in facts:
            for i in range(len(f) - 3):
                stueck = f[i:i + 4]
                if stueck.isdigit() and 2000 <= int(stueck) <= 2099:
                    erlaubt.add(_norm_jahr(jahr_als_wort(int(stueck))))
        if erlaubt:
            for gesprochen in _jahre_im_text(voll):
                if _norm_jahr(gesprochen) not in erlaubt:
                    verstoesse.append(
                        f"'{gesprochen}' kommt in den belegten Fakten nicht vor. "
                        f"Belegt sind: {', '.join(sorted(erlaubt))}. Schreibe die "
                        f"Jahreszahl genau so aus.")

    if not texts[-1].rstrip().endswith("Folge für Börse, die man versteht!"):
        verstoesse.append("Das letzte Segment endet nicht mit dem festen Abbinder.")

    return verstoesse


def _write_script(llm: LLMProvider, research: Research,
                  target_seconds: int) -> dict | None:
    # 1,95 statt 2,3 Woerter/Sekunde: gemessen an Reel #108 (104 Woerter -> 53,4 s).
    # Ausgeschriebene Zahlwoerter brauchen deutlich laenger als normale Woerter, und
    # dieser Kanal schreibt jede Zahl aus.
    words = int(target_seconds * 1.95)
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

    # Einmal nachbessern lassen. Zweimal lohnt nicht: wer die Regeln nach einer
    # konkreten Ruege nicht einhaelt, haelt sie auch beim dritten Mal nicht ein.
    verstoesse = check_script_rules([str(s) for s in data["segments"]], research.facts)
    if verstoesse:
        logger.warning("Skript verletzt Sprechregeln, fordere Korrektur an: "
                       + " | ".join(verstoesse))
        korrektur = parse_json_response(llm.complete(
            system=_SCRIPT_SYSTEM,
            user=(user + "\n\nDEIN ENTWURF WAR:\n"
                  + "\n".join(str(s) for s in data["segments"])
                  + "\n\nER VERLETZT DIESE REGELN:\n"
                  + "\n".join(f"- {v}" for v in verstoesse)
                  + "\n\nGib dasselbe Skript korrigiert zurueck. Inhalt und Zahlen "
                    "bleiben, nur die Form aendert sich."),
            model=config.CLAUDE_MODEL, max_tokens=2500,
            purpose="auto_reel_script_fix",
        ))
        if isinstance(korrektur, dict) and korrektur.get("segments"):
            rest = check_script_rules([str(s) for s in korrektur["segments"]],
                                      research.facts)
            if len(rest) < len(verstoesse):
                if rest:
                    logger.warning("Nach Korrektur noch offen: " + " | ".join(rest))
                return korrektur
        logger.warning("Korrektur brachte nichts — Entwurf wird so verwendet")
    return data


async def generate_autonomous_reel(target_seconds: int = 40) -> AutoReel:
    """Der volle Weg. Gibt bei jedem Abbruch eine Begründung zurück, die per
    Telegram gemeldet werden kann — ein stiller Ausfall wäre schlimmer als keiner."""
    from src.render.renderer import pick_music, render_reel
    from src.tts.base import get_tts

    llm = get_llm()
    day_label = datetime.now().strftime("%d.%m.%Y")

    if ist_vorschautag(datetime.now()):
        logger.info("Samstag — es wird die Sonntags-Wochenvorschau gebaut")
        research = research_week_ahead(llm, day_label)
        if not research.ok:
            # Lieber ein normales Tagesthema als gar kein Sonntagsreel.
            logger.warning(f"Wochenvorschau fehlgeschlagen ({research.note}) — "
                           f"weiche auf ein Tagesthema aus")
            research = research_topic(llm, day_label, recent_topics=_recent_topics())
    else:
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

    # Ohne diesen Versand passiert nach aussen nichts: das Reel liegt fertig in der
    # Datenbank und niemand erfaehrt davon (Vorfall 21.08.2026, Reel #107).
    from src.review.telegram_bot import review_configured, send_for_review

    if review_configured():
        await send_for_review(reel_id, str(video), caption)
    else:
        logger.warning(f"Reel #{reel_id} fertig, aber keine Telegram-Freigabe "
                       f"konfiguriert — es wird niemand danach fragen")

    logger.info(f"Autonomes Reel #{reel_id} fertig: {research.topic}")
    return AutoReel(reel_id, f"{research.topic} (Opener {choice.video_id})")
