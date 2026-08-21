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

Belege jeden Fakt SOFORT, solange du suchst: zu jedem Fakt gehört in "evidence" ein
wörtliches Zitat aus der Quelle, das genau die genannte Zahl enthält. Es gibt keinen
zweiten Suchlauf — was du hier nicht belegst, wird verworfen. Lieber drei wasserdichte
Fakten als sechs halbgare.

Beginne die Antwort unmittelbar mit der geschweiften Klammer. Keine Vorrede, kein
Kommentar, kein Text danach. Meldet die Websuche ein Limit, ist das KEIN Grund, die
Antwort abzubrechen — gib dann das JSON aus dem aus, was du bereits belegt hast, und
nimm lieber weniger Fakten auf.

Antworte ausschließlich mit diesem JSON:
{{
  "topic": "kurzer Themenzuschnitt, kein Firmenname als Hauptsache",
  "title": "Arbeitstitel für die Ankündigungs-Story",
  "why_now": "welches abgeschlossene Ereignis der Aufhänger ist, mit Datum",
  "loudness": "warum das im Mainstream läuft und nicht nur im Wirtschaftsteil",
  "facts": ["je ein belegter Fakt mit Zahl und Datum", "..."],
  "evidence": {{"exakt derselbe Fakt-Text wie oben":
                "Quelle + Datum + WÖRTLICHES Zitat, das genau diese Zahl trägt"}},
  "aha": "der überraschende Schlussgedanke, der die naheliegende Deutung dreht",
  "relevance": "was das für das Geld/den Alltag eines Normalverdieners heißt",
  "sources": ["Quellenname oder URL", "..."],
  "rejected": ["kurz: welche Themen du verworfen hast und warum"]
}}"""

_VERIFY_SYSTEM = """Du bist Faktenprüfer für einen Finanz-Kanal. Du bekommst eine
Liste behaupteter Fakten, die BEREITS recherchiert wurden und jeweils Quelle und
wörtliches Zitat mitbringen.

Du suchst NICHT. Deine Aufgabe ist die Prüfung am mitgelieferten Beleg — genau deshalb
verlangt der erste Schritt Zitate. (Ein zweiter Suchlauf direkt nach dem ersten läuft
ins Websuch-Ratenlimit und blockiert die Automatik minutenlang; gemessen 20.08.2026.)

Verwirf einen Fakt, wenn eines davon zutrifft:
- Es fehlt Quelle oder Zitat, oder das Zitat trägt die Behauptung nicht.
- Die Zahl im Fakt steht so nicht im Zitat, sondern ist daraus abgeleitet oder gerundet
  über das hinaus, was das Zitat hergibt.
- Datum und Wochentag passen nicht zusammen, oder das Datum liegt in der Zukunft.
- Es riecht nach einer Zahl, deren Veröffentlichung noch aussteht.
- Zwei Fakten widersprechen sich zahlenmäßig.

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


_WEEK_SYSTEM = """Du baust die woechentliche Vorschau auf die kommende Boersenwoche
fuer einen deutschen Finanz-Instagram-Kanal (Zielgruppe: Berufstaetige 25-45 ohne oder
mit ungenutztem Depot).

DAS WICHTIGSTE ZUERST: Das wird ein TERMINKALENDER MIT NUTZWERT, keine Prognose.
Gemessen an diesem Kanal: reine Vorschauen ("was der Markt naechste Woche macht")
lagen bei 0,47x der Followerzahl, ein konkreter Wochen-Fahrplan mit Terminen bei 5,9x.
Der Unterschied ist, dass man den Fahrplan speichern kann. Sage also, WAS WANN
ansteht und WORAUF man achten kann — niemals, was daraufhin passieren wird.

REGELN
- Vier bis fuenf Termine, jeder mit Wochentag UND Datum.
- Nur Termine, die bereits offiziell angesetzt sind. Nichts Vermutetes.
- Mische die Ebenen: Notenbank oder Konjunkturdaten, ein bis zwei grosse
  Quartalszahlen, ein Termin mit Alltagsbezug (Preise, Energie, Arbeitsmarkt).
- Keine Kauf- oder Verkaufsempfehlung, keine Kursziele, keine Erwartung formulieren
  wie "duerfte steigen".
- Zu jedem Termin gehoert in einem Halbsatz, warum er jemanden ohne Depot angeht.
- Das Aha ist der eine Termin, den fast niemand auf dem Zettel hat, der aber am
  meisten aussagt.

Beginne die Antwort unmittelbar mit der geschweiften Klammer, keine Vorrede. Meldet
die Websuche ein Limit, gib trotzdem das JSON aus dem aus, was du schon hast.

{
  "topic": "Boersenwoche <Datum bis Datum>: die Termine",
  "title": "Arbeitstitel fuer die Ankuendigungs-Story",
  "why_now": "welcher Zeitraum abgedeckt wird, mit Datum",
  "loudness": "welcher Termin der Woche am breitesten laeuft",
  "facts": ["Wochentag, Datum: Termin — warum er zaehlt", "..."],
  "evidence": {"exakt derselbe Termin-Text wie oben":
               "Quelle + woertliches Zitat, das Datum und Termin belegt"},
  "aha": "der unterschaetzte Termin und was er verraet",
  "relevance": "was die Woche fuer das Geld eines Normalverdieners bedeutet",
  "sources": ["Quellenname oder URL", "..."],
  "rejected": []
}"""


def _verify_facts(llm: LLMProvider, data: dict, day_label: str) -> dict | None:
    """Zweiter Pass: die Fakten gegen die mitgelieferten Belege pruefen — OHNE Websuche.

    Das ist der Kern der Beschleunigung. Frueher suchte dieser Pass erneut und lief
    dabei ins Ratenlimit des ersten Passes: gemessen am 20.08.2026 ueber 22 Minuten
    ohne Ergebnis, waehrend der erste Pass nur 2:20 brauchte. Geprueft wird jetzt an
    dem woertlichen Zitat, das der erste Pass ohnehin liefern muss.
    """
    belege = data.get("evidence") or {}
    zeilen = []
    for f in data["facts"]:
        beleg = belege.get(f) if isinstance(belege, dict) else None
        zeilen.append(f"- {f}")
        if beleg:
            zeilen.append(f"    Beleg: {beleg}")
    quellen = "; ".join(str(q) for q in (data.get("sources") or [])[:6])
    kopf = f"Thema: {data['topic']}"
    user = chr(10).join([kopf, f"Stand: {day_label}", "",
                      "Zu pruefende Fakten mit Belegen:", *zeilen, "",
                      f"Quellen des ersten Durchgangs: {quellen}"])

    try:
        raw = llm.complete(          # complete(), nicht research(): keine Websuche
            system=_VERIFY_SYSTEM,
            user=user,
            model=config.CLAUDE_MODEL,
            max_tokens=2000,
            purpose="reel_fact_verify",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Faktencheck fehlgeschlagen: {exc}")
        return None
    checked = parse_json_response(raw)
    return checked if isinstance(checked, dict) else None


def research_week_ahead(llm: LLMProvider, day_label: str) -> Research:
    """Die Sonntags-Vorschau: Termine der kommenden Boersenwoche.

    Laeuft ueber denselben Faktencheck wie die Tagesrecherche — bei einer Vorschau ist
    das sogar wichtiger, weil Wochenvorschauen Termine notorisch falsch datieren.
    """
    raw = llm.research(
        system=_WEEK_SYSTEM,
        user=(f"Heute ist der {day_label}. Das Reel erscheint morgen frueh um 09:00, "
              f"also am Sonntag. Recherchiere die offiziell angesetzten Termine der "
              f"kommenden Handelswoche (Montag bis Freitag) und baue daraus den "
              f"Fahrplan."),
        model=config.CLAUDE_MODEL,
        max_tokens=8000,
        purpose="reel_week_ahead",
        max_searches=5,
    )
    data = parse_json_response(raw)
    if not isinstance(data, dict) or not data.get("facts"):
        logger.warning("Wochenvorschau lieferte kein brauchbares JSON")
        return Research(ok=False, note="Wochenvorschau ohne verwertbares Ergebnis")

    logger.info(f"Wochenvorschau: {data.get('topic')}")
    checked = _verify_facts(llm, data, day_label)
    if not isinstance(checked, dict):
        logger.warning("Faktencheck der Wochenvorschau ohne Ergebnis")
        return Research(ok=False, note="Faktencheck der Wochenvorschau fehlgeschlagen")

    verified = [str(f) for f in (checked.get("verified") or []) if str(f).strip()]
    dropped = [str(f) for f in (checked.get("dropped") or [])]
    if len(verified) < 3:
        # Ein Fahrplan mit zwei Terminen ist kein Fahrplan.
        logger.warning(f"Wochenvorschau nur {len(verified)} belegte Termine")
        return Research(ok=False, dropped=dropped,
                        note=f"Wochenvorschau: nur {len(verified)} belegte Termine")

    return Research(
        ok=True,
        topic=str(data.get("topic") or "Boersenwoche"),
        title=str(data.get("title") or data.get("topic") or "Die Woche"),
        facts=verified,
        aha=str(data.get("aha") or ""),
        relevance=str(data.get("relevance") or ""),
        why_now=str(data.get("why_now") or ""),
        sources=[str(q) for q in (data.get("sources") or [])],
        dropped=dropped,
    )


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
        # Grosszuegig: die woertlichen Zitate in "evidence" machen die Antwort lang.
        # Mit 2500 brach das JSON mitten im Schreiben ab (20.08.2026).
        max_tokens=8000,
        purpose="reel_topic_research",
        max_searches=5,     # acht Suchen reissen das Kontingent des Kontos
    )
    data = parse_json_response(raw)
    if not isinstance(data, dict) or not data.get("topic") or not data.get("facts"):
        logger.warning("Themenrecherche lieferte kein brauchbares JSON")
        return Research(ok=False, note="Themenrecherche ohne verwertbares Ergebnis")

    logger.info(f"Themenvorschlag: {data['topic']}")
    if data.get("rejected"):
        logger.info(f"Verworfen: {'; '.join(str(x) for x in data['rejected'][:3])}")

    checked = _verify_facts(llm, data, day_label)
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
