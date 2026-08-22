"""Register der bereits verwendeten Startvideos.

Ein Opener darf sich nie wiederholen: er ist das Vorschaubild im Instagram-Raster, und
zwei gleiche Kacheln lassen den Kanal wie eine Wiederholungsschleife aussehen.

Bisher stand die Ausschlussliste im Skript-JSON der Reels — und genau das hat am
22.08.2026 versagt. Nur der automatische Pfad schreibt dort `opener_id` hinein; alle
von Hand gebauten Reels schreiben ihn nicht. Von rund dreissig verwendeten Clips waren
der Automatik also vier bekannt, und sie griff prompt zu einem, den es schon gab.

Deshalb liegt das Register jetzt an einer eigenen Stelle, unabhaengig davon, wer das
Reel gebaut hat: eine Datei, in die JEDER Weg eintraegt. Ein Register, das nur eine
von zwei Produktionsarten kennt, ist kein Register.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from loguru import logger

import config

# Handgebaute Reels vor dem 22.08.2026. Diese IDs stehen in LEARNINGS.md und in den
# build_*.py-Skripten, waren aber nirgends maschinenlesbar. Einmalige Starthilfe,
# damit das Register nicht bei null anfaengt.
_ALTBESTAND: dict[int, str] = {
    8516369: "glitzernde Goldflaeche",
    26329253: "Tanker und Frachter",
    27924767: "rote Tram",
    6201679: "Ladenlokal mit Schild",
    37669831: "gruener Container auf LKW",
    36639391: "gelbes Smiley-Sparschwein",
    28962441: "orange Sonnenschirme am Meer",
    7191510: "Frau packt Laptop aus",
    35025004: "Strommast vor blauem Himmel",
    9909256: "Haende mit Fernglas",
    8102763: "aufgereihte Dominosteine",
    8490654: "blaue Pipette in Petrischale",
    38269522: "Baukraene ueber Altbau",
    5635831: "NYSE-Fassade",
    # als Abbinder verwendet, taugen damit auch nicht mehr als Opener
    5839043: "illustrierte Petrischale (CTA)",
    12405681: "CTA",
    37357040: "CTA",
    8516638: "CTA",
    5834559: "CTA",
    7579426: "Hand mit Haustuerschluessel (CTA)",
}


def _pfad() -> Path:
    return Path(config.DATA_DIR) / "opener_history.json"


def _laden() -> dict:
    try:
        return json.loads(_pfad().read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — fehlt oder kaputt: mit dem Altbestand starten
        return {}


def verwendete_ids() -> set[int]:
    """Alle je verwendeten Clip-IDs — Register plus Altbestand plus Skript-JSON.

    Die drei Quellen werden vereinigt und nicht gegeneinander abgewogen: eine ID, die
    irgendwo auftaucht, ist verbraucht. Lieber ein Kandidat zu viel ausgeschlossen als
    ein Vorschaubild doppelt.
    """
    ids = set(_ALTBESTAND)
    for k in _laden():
        try:
            ids.add(int(k))
        except (TypeError, ValueError):
            continue
    ids |= _aus_skript_json()
    return ids


def _aus_skript_json() -> set[int]:
    """Nachtraeglich auch die Reels beruecksichtigen, die die ID im Skript fuehren."""
    from sqlalchemy import select

    from src.storage.database import ReelRow, session_scope

    ids: set[int] = set()
    try:
        with session_scope() as session:
            rows = session.execute(
                select(ReelRow.script_json).where(ReelRow.script_json.is_not(None))
                .order_by(ReelRow.id.desc()).limit(200)
            ).scalars().all()
    except Exception:  # noqa: BLE001 — ohne Datenbank reicht das Register
        return ids
    for raw in rows:
        try:
            vid = json.loads(raw).get("opener_id")
        except Exception:  # noqa: BLE001
            continue
        if isinstance(vid, int):
            ids.add(vid)
    return ids


def motivklassen(limit: int = 12) -> list[str]:
    """Die zuletzt verwendeten Motivbeschreibungen, neueste zuerst.

    Gehen als Prosa in den Auswahl-Prompt: die ID-Sperre verhindert denselben Clip,
    nicht dasselbe Motiv. Ein zweiter Sonnenuntergang mit anderer ID faellt dem
    Zuschauer genauso auf.
    """
    eintraege = sorted(_laden().items(), key=lambda kv: kv[1].get("datum", ""),
                       reverse=True)
    return [str(v.get("motiv", "")) for _, v in eintraege[:limit] if v.get("motiv")]


def merken(video_id: int, motiv: str = "") -> None:
    """Einen verwendeten Clip eintragen. Fehlschlaege sind nicht fatal, aber laut."""
    if not video_id:
        return
    reg = _laden()
    reg[str(int(video_id))] = {"datum": date.today().isoformat(), "motiv": motiv[:180]}
    try:
        p = _pfad()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(reg, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Opener-Register nicht speicherbar: {exc} — "
                       f"Clip {video_id} kann sich wiederholen")
