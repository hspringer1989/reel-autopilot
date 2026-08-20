"""Tägliche Rückschau auf das zuletzt veröffentlichte Reel.

Läuft direkt VOR der abendlichen Reel-Erzeugung und beantwortet zwei Fragen:
wie ist das letzte Reel gelaufen, und welche Ziellänge bekommt das nächste.

Warum ausgerechnet die Sehdauer die Stellschraube ist: Bei diesem Kanal korreliert
`ig_reels_avg_watch_time` deutlich mit der Reichweite, Saves und Shares dagegen nicht.
Gemessen am 16.08.2026 über alle Reels — ø Sehdauer 19,0 s Ende Juli bei ~5.300
Konto-Reichweite pro Tag, 9,8 s Mitte August bei ~810. Die Länge ist der Hebel, den
eine Automatik sinnvoll selbst drehen kann; alles andere (Thema, Opener, Faktenlage)
bleibt Handarbeit bzw. Sache der Freigabe.

Bewusst KEIN LLM-Aufruf: Einem Modell "das letzte Reel lief schlecht, mach es besser"
zu sagen, ändert nichts Messbares. Die Ableitung ist eine Tabelle, das kostet nichts
und ist nachvollziehbar.
"""
from __future__ import annotations

from dataclasses import dataclass

from loguru import logger
from sqlalchemy import select

import config
from src.storage.database import ReelRow, session_scope

# Sehdauer (Sekunden) → Ziellänge des nächsten Reels. Wer früh abspringt, bekommt ein
# kürzeres Reel; wer lange bleibt, verträgt mehr. Die Grenzen stammen aus den eigenen
# Messwerten: unter 8 s lagen ausschließlich Reels jenseits der 60 Sekunden.
_LADDER: list[tuple[float, int]] = [
    (8.0, 30),
    (12.0, 35),
    (16.0, 40),
    (999.0, 45),
]


@dataclass
class ReelFeedback:
    """Ergebnis der Rückschau. `target_seconds` geht direkt in die Skript-Erzeugung."""
    reel_id: int | None
    views: int
    reach: int
    watch_seconds: float
    target_seconds: int
    text: str


def _target_for(watch_seconds: float) -> int:
    for limit, seconds in _LADDER:
        if watch_seconds < limit:
            return seconds
    return config.REEL_TARGET_SECONDS


async def analyse_last_reel() -> ReelFeedback:
    """Kennzahlen des zuletzt veröffentlichten Reels holen und die Ziellänge ableiten.

    Fällt immer weich zurück: Ohne Instagram-Anbindung, ohne veröffentlichtes Reel oder
    bei einem API-Fehler kommt die Standard-Ziellänge aus der Config zurück, damit die
    abendliche Erzeugung nie an der Rückschau scheitert.
    """
    default = ReelFeedback(None, 0, 0, 0.0, config.REEL_TARGET_SECONDS,
                           "Noch kein veröffentlichtes Reel zum Vergleich.")

    from src.publish.instagram import publishing_configured

    if not publishing_configured():
        return default

    with session_scope() as session:
        row = session.execute(
            select(ReelRow)
            .where(ReelRow.status == "published", ReelRow.ig_media_id.is_not(None))
            .order_by(ReelRow.id.desc())
        ).scalars().first()
        if row is None:
            return default
        reel_id, media_id = row.id, row.ig_media_id

    try:
        metrics = await _fetch_reel_metrics(media_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Rückschau auf Reel #{reel_id} fehlgeschlagen: {exc}")
        return default

    views = int(metrics.get("views") or 0)
    reach = int(metrics.get("reach") or 0)
    watch = float(metrics.get("ig_reels_avg_watch_time") or 0) / 1000.0
    target = _target_for(watch) if watch > 0 else config.REEL_TARGET_SECONDS

    text = (f"📊 Rückschau auf Reel #{reel_id}\n"
            f"· Aufrufe: {views}\n"
            f"· Erreichte Konten: {reach}\n"
            f"· Ø Sehdauer: {watch:.1f} s\n"
            f"→ Ziellänge für das nächste Reel: {target} s")
    logger.info(f"Rückschau Reel #{reel_id}: {views} Aufrufe, {watch:.1f} s Sehdauer "
                f"→ Ziellänge {target} s")
    return ReelFeedback(reel_id, views, reach, watch, target, text)


async def _fetch_reel_metrics(media_id: str) -> dict:
    """views/reach/Sehdauer für ein Medium. Eigene Abfrage statt fetch_insights, weil
    dort ig_reels_avg_watch_time nicht mit angefragt wird."""
    import httpx

    metrics = "views,reach,ig_reels_avg_watch_time"
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{config.GRAPH_BASE_URL}/{config.GRAPH_API_VERSION}/{media_id}/insights",
            params={"metric": metrics, "access_token": config.IG_ACCESS_TOKEN},
        )
        body = response.json()
    if "data" not in body:
        raise RuntimeError(str(body)[:200])
    return {e["name"]: (e.get("values") or [{}])[0].get("value") for e in body["data"]}
