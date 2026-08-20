"""Pipeline orchestration: collect → score → script → voiceover → render →
review queue. Every stage is behind a port interface so the whole chain runs
offline with fakes (LLM_PROVIDER=fake, TTS_PROVIDER=fake, no Pexels key)."""
import asyncio
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger
from sqlalchemy import select

import config
from src.collectors.rss import active_collectors
from src.content.article import fetch_article_text
from src.content.factcheck import check_script
from src.content.llm import LLMProvider, get_llm
from src.content.scorer import score_trends
from src.content.script_agent import generate_script
from src.models import ReelScript, ScriptSegment, TrendItem
from src.render.broll import PexelsBroll
from src.render.renderer import pick_music, render_reel
from src.storage.database import ReelRow, TrendRow, session_scope, trend_uid_known
from src.tts.base import get_tts


def collect_and_score(llm: LLMProvider | None = None) -> int:
    """Run all collectors, insert unseen trends, batch-score them. Returns #scored."""
    llm = llm or get_llm()
    fresh: list[TrendItem] = []
    with session_scope() as session:
        for collector in active_collectors():
            for item in collector.safe_collect():
                if trend_uid_known(session, item.uid) or any(f.uid == item.uid for f in fresh):
                    continue
                fresh.append(item)
                session.add(TrendRow(
                    uid=item.uid, source=item.source, title=item.title,
                    summary=item.summary, url=item.url, popularity=item.popularity,
                ))

    if not fresh:
        logger.info("Keine neuen Trends gefunden")
        return 0

    scores = score_trends(fresh, llm)
    scored = 0
    with session_scope() as session:
        for item, score in zip(fresh, scores):
            row = session.execute(
                select(TrendRow).where(TrendRow.uid == item.uid)
            ).scalar_one()
            if score is None:
                row.status = "skipped"
                continue
            row.status = "scored"
            row.score_total = score.total(config.SCORER_WEIGHTS)
            row.score_viral = score.viral_potential
            row.score_fit = score.niche_fit
            row.score_monetization = score.monetization
            row.score_reasoning = score.reasoning
            scored += 1
    logger.info(f"{len(fresh)} neue Trends, {scored} bewertet")
    return scored


def pick_best_trend(max_age_hours: int | None = None) -> TrendRow | None:
    """Highest-scored unused trend above the threshold.

    `max_age_hours` limits the pick to recent trends. Without it the query returns the
    all-time best leftover — when this was written the top-scored open trend was nine
    days old. That is fine for filling a queue on demand, but wrong for a DAILY reel,
    where stale news is worse than no news.
    """
    from datetime import datetime, timedelta, timezone

    with session_scope() as session:
        query = select(TrendRow).where(
            TrendRow.status == "scored", TrendRow.score_total >= config.MIN_TREND_SCORE
        )
        if max_age_hours:
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).isoformat()
            query = query.where(TrendRow.created_at >= cutoff)
        return session.execute(query.order_by(TrendRow.score_total.desc())).scalars().first()


def _script_to_json(script: ReelScript) -> str:
    return json.dumps(asdict(script), ensure_ascii=False)


def script_from_json(raw: str) -> ReelScript:
    data = json.loads(raw)
    data["segments"] = [ScriptSegment(**s) for s in data["segments"]]
    return ReelScript(**data)


def produce_reel(trend: TrendRow, llm: LLMProvider | None = None,
                 target_seconds: int | None = None) -> int | None:
    """Script → TTS → render for one trend. Returns the reel id (pending_review)
    or None if a stage failed (trend is then released for another attempt)."""
    llm = llm or get_llm()
    # Den Quellartikel holen, BEVOR geschrieben wird: manche Feeds liefern als
    # <description> nur die Überschrift, und aus einer Überschrift fünf Segmente zu
    # schreiben ist genau die Situation, in der ein Modell Details erfindet.
    article = fetch_article_text(trend.url) if trend.url else None
    script = generate_script(
        TrendItem(source=trend.source, title=trend.title, summary=trend.summary, url=trend.url),
        llm,
        article=article,
        target_seconds=target_seconds,
    )
    if script is None:
        logger.warning(f"Kein Skript für Trend #{trend.id} — übersprungen")
        with session_scope() as session:
            session.get(TrendRow, trend.id).status = "skipped"
        return None

    # normalise each segment for natural German TTS (%, currency, decimals, dashes) so the
    # voice flows; done per-segment to keep the burned-in subtitles in sync with the words
    from src.stocks.stock_reel import _spoken_de

    for seg in script.segments:
        seg.text = _spoken_de(seg.text, "", "")
    if script.segments:
        script.hook = script.segments[0].text

    # Gegen die Quelle abgleichen. Beratend: das Ergebnis geht an den Menschen in die
    # Telegram-Freigabe, es verwirft nichts von selbst.
    findings = check_script(script, article, llm)

    with session_scope() as session:
        reel = ReelRow(
            trend_id=trend.id, script_json=_script_to_json(script),
            caption=f"{script.caption}\n\n{' '.join(script.hashtags)}".strip(),
            fact_check="\n".join(findings),
            status="draft",
        )
        session.add(reel)
        session.flush()
        reel_id = reel.id
        session.get(TrendRow, trend.id).status = "used"

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    base = Path(config.OUTPUT_DIR) / f"reel_{reel_id}_{stamp}"
    try:
        tts = get_tts().synthesize(script.full_text, base.with_suffix(".mp3"))
        broll = PexelsBroll()
        min_len = max(2.0, tts.duration / max(len(script.segments), 1))
        clips = [broll.fetch(seg.broll_query, min_len) for seg in script.segments]
        video_path = render_reel(script, tts, clips, base.with_suffix(".mp4"), pick_music())
    except Exception as exc:  # noqa: BLE001 — record the failure, don't crash the loop
        logger.error(f"Reel #{reel_id} fehlgeschlagen: {exc}")
        with session_scope() as session:
            row = session.get(ReelRow, reel_id)
            row.status = "failed"
            row.error = str(exc)[:2000]
        return None

    with session_scope() as session:
        row = session.get(ReelRow, reel_id)
        row.audio_path = tts.audio_path
        row.video_path = str(video_path)
        row.status = "pending_review"
    logger.info(f"Reel #{reel_id} fertig gerendert: {video_path}")
    return reel_id


async def generate_once(collect: bool = True,
                        target_seconds: int | None = None,
                        max_age_hours: int | None = None) -> int | None:
    """Full chain for one reel; sends it to the Telegram review queue if configured.
    `target_seconds` overrides the configured length — the evening automation derives it
    from how long viewers actually watched the previous reel."""
    llm = get_llm()
    trend = pick_best_trend(max_age_hours)
    if trend is None and collect:
        # to_thread: rendering/HTTP must not stall the Telegram poller in `run`
        await asyncio.to_thread(collect_and_score, llm)
        trend = pick_best_trend(max_age_hours)
    if trend is None:
        age_note = f", jünger als {max_age_hours} h" if max_age_hours else ""
        logger.warning(
            f"Kein Trend über Score-Schwelle {config.MIN_TREND_SCORE}{age_note} verfügbar"
        )
        return None
    logger.info(f"Bester Trend (#{trend.id}, Score {trend.score_total:.2f}): {trend.title}")

    reel_id = await asyncio.to_thread(produce_reel, trend, llm, target_seconds)
    if reel_id is None:
        return None

    from src.review.telegram_bot import review_configured, send_for_review

    if review_configured():
        with session_scope() as session:
            reel = session.get(ReelRow, reel_id)
        await send_for_review(reel_id, reel.video_path, reel.caption)
    else:
        logger.info("Telegram nicht konfiguriert — Reel bleibt in der Review-Queue (DB)")
    return reel_id


def handle_regenerates() -> list[int]:
    """Re-produce reels the reviewer sent back with 🔄 (same trend, new script)."""
    with session_scope() as session:
        stale = session.execute(
            select(ReelRow).where(ReelRow.status == "regenerate")
        ).scalars().all()
        trends = {r.id: session.get(TrendRow, r.trend_id) for r in stale}
        for reel in stale:
            reel.status = "rejected"
            if trends[reel.id] is not None:
                trends[reel.id].status = "scored"  # release the trend for a fresh attempt

    new_ids = []
    for reel in stale:
        trend = trends[reel.id]
        if trend is None:
            continue
        new_id = produce_reel(trend)
        if new_id is not None:
            new_ids.append(new_id)
    return new_ids


def _announcement_exists(path_marker: str) -> bool:
    """Gibt es zu diesem Beitrag schon eine Ankuendigungs-Story?

    Erkannt am Dateinamen (announce_reel_<id>_… bzw. announce_<id>_…), damit dafuer
    keine Schema-Aenderung noetig ist. Verhindert, dass ein wiederholt ausgeloester
    Slot denselben Beitrag mehrfach ankuendigt.
    """
    from src.storage.database import StoryRow

    with session_scope() as session:
        row = session.execute(
            select(StoryRow).where(
                StoryRow.kind == "announce",
                StoryRow.image_path.contains(path_marker),
                StoryRow.status == "published",
            )
        ).scalars().first()
    return row is not None


async def announce_new_reel(reel_id: int) -> str | None:
    """Auto-post a striking 'NEUES REEL' story after a reel goes live — same idea as the
    feed-post announcement. Best-effort: a failure never affects the reel itself."""
    import config
    from zoneinfo import ZoneInfo

    if not config.FEED_ANNOUNCE_STORY:
        return None
    from src.publish.instagram import publish_story, publishing_configured
    from src.stocks.story_cards import render_new_post_story
    from src.storage.database import StoryRow

    if not publishing_configured():
        return None

    # ⛔ Drei Sperren gegen Ankuendigungen ins Leere (Vorfall 20.08.2026).
    from src.publish.instagram import media_exists

    with session_scope() as session:
        reel = session.get(ReelRow, reel_id)
        if reel is None:
            logger.warning(f"Ankuendigung fuer Reel #{reel_id} verweigert: existiert nicht")
            return None
        raw = reel.script_json or "{}"
        status, media = reel.status, (reel.ig_media_id or "")

    if status != "published" or not media:
        logger.warning(f"Ankuendigung fuer Reel #{reel_id} verweigert: Status "
                       f"'{status}', Medien-ID '{media or "-"}'")
        return None
    if _announcement_exists(f"announce_reel_{reel_id}_"):
        logger.warning(f"Ankuendigung fuer Reel #{reel_id} verweigert: gibt es schon")
        return None
    if not await media_exists(media):
        logger.warning(f"Ankuendigung fuer Reel #{reel_id} verweigert: Medien-ID "
                       f"{media} ist bei Instagram nicht auffindbar")
        return None

    data = json.loads(raw) if raw else {}
    # Use the reel's short title — NEVER the full hook (a long hook overflowed the
    # announcement card). render_new_post_story also shrink-fits as a safety net.
    title = data.get("title") or "Neues Reel"
    day = datetime.now(ZoneInfo(config.TIMEZONE))
    stamp = day.strftime("%Y%m%d_%H%M%S")
    path = render_new_post_story(
        title, str(config.STORY_DIR / f"announce_reel_{reel_id}_{stamp}.jpg"),
        badge="NEUES REEL", sub="gerade als Reel gepostet",
    )
    try:
        media_id = await publish_story(path)
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Neues-Reel-Story fehlgeschlagen: {exc}")
        return None
    with session_scope() as session:
        session.add(StoryRow(
            kind="announce", trade_date=day.strftime("%Y-%m-%d"), image_path=path,
            caption=f"Neues Reel: {title}", status="published", ig_media_id=media_id,
            published_at=datetime.now(timezone.utc).isoformat(),
        ))
    logger.info(f"Neues-Reel-Story gepostet (IG media id {media_id})")
    return media_id


async def publish_next_approved() -> int | None:
    """Publish the oldest approved reel; returns its id or None if queue is empty."""
    from src.publish.instagram import publish_reel

    with session_scope() as session:
        reel = session.execute(
            select(ReelRow).where(ReelRow.status == "approved").order_by(ReelRow.id)
        ).scalars().first()
    if reel is None:
        return None

    try:
        media_id = await publish_reel(reel.video_path, reel.caption)
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Publish von Reel #{reel.id} fehlgeschlagen: {exc}")
        with session_scope() as session:
            row = session.get(ReelRow, reel.id)
            row.status = "failed"
            row.error = str(exc)[:2000]
        return None

    with session_scope() as session:
        row = session.get(ReelRow, reel.id)
        row.status = "published"
        row.ig_media_id = media_id
        row.published_at = datetime.now(timezone.utc).isoformat()
    await announce_new_reel(reel.id)
    return reel.id
