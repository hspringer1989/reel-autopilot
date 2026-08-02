"""Chefredakteur-Morgenbriefing (systemd-Timer, morgens): schickt per Telegram den
Tagesplan (Reel, Watchlist-Stories, Feed-Carousel), was noch fehlt/freizugeben ist,
und 1-2 aktuelle News-Themen als Reel-Vorschläge. Jede Sektion ist gekapselt — ein Fehler
darf das Briefing nicht verhindern. Alle genannten Uhrzeiten kommen aus config, damit
das Briefing zu jedem Kanal passt."""
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from loguru import logger
from sqlalchemy import select, func

import config
from src.storage.database import ReelRow, StoryRow, FeedPostRow, TrendRow, session_scope

_WD = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
_STORY_KINDS = ("candidate", "candidates", "earnings", "trend")


def _reel_slot() -> str:
    """First reel posting slot of the day (label only)."""
    return config.POSTING_SLOTS[0] if config.POSTING_SLOTS else "09:00"


def _today():
    return datetime.now(ZoneInfo(config.TIMEZONE))


def _reel_line() -> str:
    with session_scope() as s:
        appr = s.execute(select(ReelRow).where(ReelRow.status == "approved")
                         .order_by(ReelRow.id)).scalars().all()
        pend = s.execute(select(func.count()).select_from(ReelRow)
                         .where(ReelRow.status == "pending_review")).scalar()
    slot = _reel_slot()
    if appr:
        return f"🎬 Reel ({slot}): ✅ #{appr[0].id} freigegeben" + (
            f" (+{len(appr)-1} weitere freigegeben)" if len(appr) > 1 else "")
    if pend:
        return (f"🎬 Reel ({slot}): ⚠️ {pend} Reel(s) warten auf deine Freigabe — "
                f"sonst kein {slot}-Post!")
    return (f"🎬 Reel ({slot}): ⚠️ KEIN Reel bereit — heute läuft um {slot} nichts. "
            "Bitte eins beauftragen.")


def _stories_line(today: str) -> str:
    with session_scope() as s:
        rows = s.execute(select(StoryRow).where(
            StoryRow.trade_date == today, StoryRow.kind.in_(_STORY_KINDS))).scalars().all()
    if not rows:
        return (f"📊 Watchlist-Stories: werden ~{config.DAILY_BUILD_SLOT} gebaut → danach in "
                f"Telegram freigeben (Earnings {config.STORY_POST_EARNINGS_SLOT}, EU/US-Slots).")
    pend = [r for r in rows if r.status == "pending_review"]
    appr = [r for r in rows if r.status in ("approved", "published")]
    if pend:
        return f"📊 Watchlist-Stories: ⚠️ {len(pend)} Karte(n) warten auf Freigabe (posten sonst nicht). {len(appr)} bereits ok."
    return f"📊 Watchlist-Stories: ✅ {len(appr)} freigegeben/gepostet, nichts offen."


def _feed_line(today: str) -> str:
    with session_scope() as s:
        sched = s.execute(select(FeedPostRow).where(
            FeedPostRow.status == "approved",
            FeedPostRow.scheduled_at.like(f"{today}%"))).scalars().first()
        nxt = s.execute(select(FeedPostRow).where(
            FeedPostRow.status == "approved", FeedPostRow.scheduled_at == "")
            .order_by(FeedPostRow.id)).scalars().first()
        future = s.execute(select(FeedPostRow).where(
            FeedPostRow.status == "approved", FeedPostRow.scheduled_at > f"{today}%")
            .order_by(FeedPostRow.scheduled_at)).scalars().all()
    slot = config.FEED_DAILY_POST_TIME
    if sched:
        return f"📰 Feed-Carousel ({slot}): ✅ #{sched.id} eingeplant — {sched.title[:44]}"
    if nxt:
        return f"📰 Feed-Carousel ({slot}): ✅ #{nxt.id} (nächster) — {nxt.title[:44]}"
    if future:
        f0 = future[0]
        return (f"📰 Feed-Carousel ({slot}): heute nichts geplant · nächster: "
                f"{f0.scheduled_at[:10]} #{f0.id} ({len(future)} im Plan)")
    return (f"📰 Feed-Carousel ({slot}): ⚠️ Kein Beitrag im Vorrat — "
            "bitte in der Redaktion nachlegen.")


def _approvals_line(today: str) -> str:
    with session_scope() as s:
        r = s.execute(select(func.count()).select_from(ReelRow)
                      .where(ReelRow.status == "pending_review")).scalar()
        st = s.execute(select(func.count()).select_from(StoryRow).where(
            StoryRow.trade_date == today, StoryRow.status == "pending_review")).scalar()
        f = s.execute(select(func.count()).select_from(FeedPostRow)
                      .where(FeedPostRow.status == "pending_review")).scalar()
    total = (r or 0) + (st or 0) + (f or 0)
    if not total:
        return "⏳ Freigaben offen: keine — alles im grünen Bereich."
    return f"⏳ Freigaben offen: {r} Reel(s) · {st} Story-Karte(n) · {f} Feed-Post(s) → bitte in Telegram durchsehen."


def _proposals_block() -> str:
    """1-2 aktuelle News-Themen als Reel-Ideen. Frisch sammeln (budget-gated), sonst Bestand."""
    try:
        from src.pipeline import collect_and_score
        collect_and_score()
    except Exception as exc:  # noqa: BLE001 — Vorschläge sind optional
        logger.warning(f"Briefing: collect_and_score fehlgeschlagen: {exc}")
    cutoff = (datetime.now(ZoneInfo(config.TIMEZONE)) - timedelta(days=2)).isoformat()
    with session_scope() as s:
        top = s.execute(select(TrendRow).where(
            TrendRow.status == "scored",
            TrendRow.score_total >= config.MIN_TREND_SCORE,
            TrendRow.created_at >= cutoff,
        ).order_by(TrendRow.score_total.desc()).limit(2)).scalars().all()
        items = [(t.title, t.source, (t.score_reasoning or "").strip()) for t in top]
    if not items:
        return ("💡 Reel-Ideen (News): aktuell keine starken Themen im Radar — sag mir, wenn ich "
                "gezielt recherchieren soll.")
    out = ["💡 Reel-Ideen aus aktuellen News (sag mir, welches ich bauen soll):"]
    for i, (title, src, why) in enumerate(items, 1):
        line = f"  {i}. {title[:80]}"
        if why:
            line += f" — {why[:90]}"
        out.append(line)
    return "\n".join(out)


async def _main() -> None:
    now = _today()
    today = now.strftime("%Y-%m-%d")
    header = f"📋 REDAKTIONSPLAN — {_WD[now.weekday()]}, {now.strftime('%d.%m.%Y')}"
    parts = [header, ""]
    for fn in (lambda: _reel_line(), lambda: _stories_line(today), lambda: _feed_line(today),
               lambda: _approvals_line(today)):
        try:
            parts.append(fn())
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Briefing-Sektion fehlgeschlagen: {exc}")
    parts.append("")
    try:
        parts.append(_proposals_block())
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Briefing-Vorschläge fehlgeschlagen: {exc}")

    msg = "\n".join(parts)
    from src.review.telegram_bot import review_configured, send_text
    if review_configured():
        await send_text(msg)
        logger.info("Morgenbriefing an Telegram gesendet")
    else:
        print(msg)


if __name__ == "__main__":
    asyncio.run(_main())
