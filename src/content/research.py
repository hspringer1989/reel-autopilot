"""Themenrecherche und Faktenprüfung für die abendliche Reel-Automatik.

Bildet den Rechercheteil der Handarbeit nach: aktuelles Thema finden, Zahlen
gegen Quellen prüfen, und das Ganze so zuschneiden, dass es zu den belegten
Reichweitenregeln des Kanals passt.

Die Regeln stammen aus der Auswertung aller bisherigen Reels
(~/.claude/skills/reel-redakteur/) und sind hier bewusst als Prompt-Text
hinterlegt statt als Code — sie ändern sich mit jeder Auswertung, und ein
Redakteur soll sie lesen und anpassen können, ohne Python zu schreiben.

Läuft in zwei Schritten, weil ein einziger Aufruf beides schlechter macht:
  1. THEMENWAHL  — was ist heute laut, und was davon trägt ein Reel?
  2. FAKTENCHECK — die Zahlen des gewählten Themas einzeln gegenprüfen.
Schritt 2 hat in der Handarbeit wiederholt Fehler gefunden, die Schritt 1
plausibel fand (falsch datierte Wochenvorschauen, widersprüchliche Kurse).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from loguru import logger

import config
from src.content.llm import LLMProvider, parse_json_response

# Belegte Reichweitenregeln. Reihenfolge = Wichtigkeit.
_RULES = """\
BELEGTE REGELN FÜR DIESEN KANAL (aus der Auswertung von rund 30 Reels):

1. LAUTSTÄRKE ENTSCHEIDET. Die Reichweite folgt dem Medienecho des Posting-Tags,
   und zwar im MAINSTREAM, nicht in der Fachpresse. Fed-Entscheid und
   Chipmarkt-Einbruch liefen 25- und 15-fach; ein Großkampftag im Wirtschaftsteil
   (Siemens-Zahlen) floppte. Frage zuerst: steht das heute in der Tagesschau?
2. AUSWERTUNG STATT VORSCHAU. Ein abgeschlossenes Ereignis auswerten (Faktor 25)
   schlägt eine Vorschau darauf (Faktor 0,5) um Größenordnungen. Zahlen, deren
   Veröffentlichung noch aussteht, sind tabu — egal wie plausibel ein Treffer aussieht.
3. KEIN FIRMENNAME ALS HAUPTSACHE. Einzelaktien-Reels liegen ausnahmslos unter
   Faktor 0,6, auch bei Top-Aktualität. Eine Firma darf Anlass sein, nie das Thema.
   Auf die übergeordnete Frage heben und mehrere Player zeigen.
4. BETROFFENHEIT. Das Thema muss jemanden erreichen, der kein Depot hat. Übersetze
   das Marktereignis in "was heißt das für dein Geld / deinen Alltag".
5. EIN FRISCHES AHA. Ein themenspezifischer Überraschungsfakt zum Schluss, der die
   naheliegende Deutung dreht. Nie generisches "Streuung/Klumpenrisiko".
6. DATUM NENNEN. Bei jedem Zeitbezug das konkrete Datum, weil Reels dauerhaft
   online bleiben.
7. NICHTS WIEDERHOLEN. Ein Thema, das der Kanal in den letzten zwei Wochen hatte,
   ist ausgeschlossen — auch in anderer Verpackung. Themenermüdung ist gemessen:
   dasselbe Format sieben Tage später brachte ein Zehntel der Reichweite.
8. FRISCH. Der Aufhänger darf höchstens rund drei Tage alt sein. Ein abgeschlossenes
   Ereignis von letzter Woche ist zwar auswertbar, aber im Mainstream längst
   verklungen — dann lieber ein kleineres, dafür heutiges Thema.
"""

_TOPIC_SYSTEM = f"""Du bist Chefredakteur eines deutschen Finanz-Instagram-Kanals
(Renditeradar, rund 900 Follower, Zielgruppe: Berufstätige 25–45 ohne oder mit
ungenutztem Depot).

{_RULES}

Du recherchierst mit Websuche und schlägst GENAU EIN Thema für das Reel von morgen
früh vor. Prüfe mehrere Kandidaten, bevor du dich entscheidest.

Antworte ausschließlich mit diesem JSON, ohne Vorrede:
{{
  "topic": "kurzer Themenzuschnitt, kein Firmenname als Hauptsache",
  "title": "Arbeitstitel für die Ankündigungs-Story",
  "why_now": "welches abgeschlossene Ereignis der Aufhänger ist, mit Datum",
  "loudness": "warum das im Mainstream läuft und nicht nur im Wirtschaftsteil",
  "facts": ["je ein belegter Fakt mit Zahl und Datum", "..."],
  "aha": "der überraschende Schlussgedanke, der die naheliegende Deutung dreht",
  "relevance": "was das für das Geld/den Alltag eines Normalverdieners heißt",
  "sources": ["Quellenname oder URL", "..."],
  "rejected": ["kurz: welche Themen du verworfen hast und warum"]
}}"""

_VERIFY_SYSTEM = """Du bist Faktenprüfer für einen Finanz-Kanal. Du bekommst eine
Liste behaupteter Fakten und prüfst JEDEN einzeln mit Websuche.

Sei streng. Häufige Fehler, auf die du besonders achtest:
- Kurse und Rohstoffpreise streuen zwischen Quellen. Immer zweitquelle suchen.
  Bei Rohstoffen englischsprachig suchen, deutsche Quellen sind oft ungenau.
- Wochenvorschauen datieren Termine regelmäßig falsch. Wochentag gegen das
  Kalenderdatum prüfen.
- Zahlen, deren Veröffentlichung noch aussteht, kursieren teils schon als
  vermeintliche Ergebnisse. Solche Fakten immer verwerfen.
- Leitzinsen und Ähnliches: Ratgeberseiten schleppen alte Stände monatelang mit.

Antworte ausschließlich mit diesem JSON:
{
  "verified": ["Fakt in korrigierter Fassung, mit Zahl und Datum", "..."],
  "dropped": ["verworfener Fakt + Grund", "..."],
  "verdict": "ok" | "unusable"
}
Setze "unusable", wenn der Kern des Themas nicht belegbar ist."""


@dataclass
class Research:
    """Ergebnis der Recherche. `ok=False` heißt: nicht bauen."""
    ok: bool
    topic: str = ""
    title: str = ""
    facts: list[str] = field(default_factory=list)
    aha: str = ""
    relevance: str = ""
    why_now: str = ""
    sources: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    note: str = ""


def research_topic(llm: LLMProvider, day_label: str,
                   recent_topics: list[str] | None = None) -> Research:
    """Thema finden und die Fakten gegenprüfen. Gibt bei jedem Zweifel `ok=False`
    zurück — ein Reel mit falschen Zahlen ist teurer als ein Tag ohne Reel.

    `recent_topics` sind die zuletzt veröffentlichten Reel-Themen. Ohne sie schlägt
    die Recherche zuverlässig wieder das zuletzt Naheliegende vor (im ersten Livelauf
    ein Thema, das fünf Tage zuvor bereits lief und floppte).
    """
    recent_block = ""
    if recent_topics:
        recent_block = ("\n\nDIESE THEMEN HATTE DER KANAL GERADE ERST — alle "
                        "ausgeschlossen, auch in anderer Verpackung:\n"
                        + "\n".join(f"- {t}" for t in recent_topics))
    raw = llm.research(
        system=_TOPIC_SYSTEM,
        user=(f"Heute ist der {day_label}. Das Reel erscheint morgen früh um 09:00.\n"
              f"Recherchiere die aktuelle Nachrichtenlage und schlage das Thema vor."
              + recent_block),
        model=config.CLAUDE_MODEL,
        max_tokens=2500,
        purpose="reel_topic_research",
        max_searches=8,
    )
    data = parse_json_response(raw)
    if not isinstance(data, dict) or not data.get("topic") or not data.get("facts"):
        logger.warning("Themenrecherche lieferte kein brauchbares JSON")
        return Research(ok=False, note="Themenrecherche ohne verwertbares Ergebnis")

    logger.info(f"Themenvorschlag: {data['topic']}")
    if data.get("rejected"):
        logger.info(f"Verworfen: {'; '.join(str(x) for x in data['rejected'][:3])}")

    checked = parse_json_response(llm.research(
        system=_VERIFY_SYSTEM,
        user=(f"Thema: {data['topic']}\nStand: {day_label}\n\n"
              f"Zu prüfende Fakten:\n"
              + "\n".join(f"- {f}" for f in data["facts"])),
        model=config.CLAUDE_MODEL,
        max_tokens=2000,
        purpose="reel_fact_verify",
        max_searches=8,
    ))
    if not isinstance(checked, dict):
        logger.warning("Faktencheck lieferte kein brauchbares JSON — Thema verworfen")
        return Research(ok=False, note="Faktencheck ohne verwertbares Ergebnis")

    verified = [str(f) for f in (checked.get("verified") or []) if str(f).strip()]
    dropped = [str(f) for f in (checked.get("dropped") or [])]
    if dropped:
        logger.info(f"Faktencheck verwarf {len(dropped)}: {'; '.join(dropped[:3])}")

    if checked.get("verdict") == "unusable" or len(verified) < 2:
        logger.warning(f"Thema nach Faktencheck unbrauchbar ({len(verified)} belegte Fakten)")
        return Research(ok=False, dropped=dropped,
                        note=f"Faktencheck: nur {len(verified)} belegte Fakten")

    return Research(
        ok=True,
        topic=str(data["topic"]),
        title=str(data.get("title") or data["topic"]),
        facts=verified,
        aha=str(data.get("aha", "")),
        relevance=str(data.get("relevance", "")),
        why_now=str(data.get("why_now", "")),
        sources=[str(s) for s in (data.get("sources") or [])],
        dropped=dropped,
    )
