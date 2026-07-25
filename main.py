"""reel-autopilot CLI.

  python main.py collect            # collect + score trends only
  python main.py generate           # produce one reel end-to-end → review queue
  python main.py stocks             # build today's earnings + watchlist stories → review
  python main.py feedpost           # generate the next educational feed carousel → review
  python main.py dividendpost       # build the monthly-dividend post (yield + 2 lights) → review
  python main.py milestone          # check follower count; new milestone card → review
  python main.py verify-ig          # read-only check of the IG token/account/permissions
  python main.py run                # scheduler loop: review bot + slots + insights
  python main.py publish --reel 3   # manually publish a specific reel
  python main.py post-story --story 7  # manually publish a specific story card
  python main.py post-feed --post 2 # manually publish a specific feed carousel
  python main.py status             # queue counts, budget, last posts
"""
import argparse
import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from loguru import logger
from sqlalchemy import func, select

import config
from src.storage.database import ApiUsageRow, FeedPostRow, ReelRow, init_db, session_scope

_LOOP_TICK_S = 60
_GENERATE_COOLDOWN_S = 3600
_INSIGHTS_SLOT = "07:00"
# The daily stock build normally fires exactly at STOCK_STORY_SLOT. If the process
# is down at that minute (crash/restart/deploy), catch it up on the next tick as long
# as we are still before this cutoff — so a restart just after 09:00 no longer loses
# the whole day's watchlist + analyses.
_STOCK_BUILD_CATCHUP_UNTIL = "12:00"
_WEEKDAYS = {"MON": 0, "TUE": 1, "WED": 2, "THU": 3, "FRI": 4, "SAT": 5, "SUN": 6}


def _feed_slots_today(now: datetime) -> list[str]:
    """FEED_POST_SLOTS entries ("TUE 17:00") whose weekday matches `now`."""
    return [s for s in config.FEED_POST_SLOTS
            if _WEEKDAYS.get(s.split()[0].upper()) == now.weekday()]


def _now_local() -> datetime:
    return datetime.now(ZoneInfo(config.TIMEZONE))


def cmd_collect() -> None:
    from src.pipeline import collect_and_score

    collect_and_score()


def cmd_generate() -> None:
    from src.pipeline import generate_once

    reel_id = asyncio.run(generate_once())
    if reel_id is None:
        raise SystemExit(1)
    print(f"Reel #{reel_id} erstellt und in die Review-Queue gestellt.")


def cmd_stocks() -> None:
    from src.stocks.pipeline import build_daily_stories, send_stories_for_review

    async def _run() -> list[int]:
        ids = await asyncio.to_thread(build_daily_stories)
        await send_stories_for_review(ids)
        return ids

    ids = asyncio.run(_run())
    if not ids:
        raise SystemExit("Keine Stories erstellt")
    print(f"{len(ids)} Story-Card(s) erstellt und in die Review-Queue gestellt: {ids}")


def cmd_feedpost() -> None:
    from src.feedposts.pipeline import build_next_feed_post, send_feed_for_review

    async def _run() -> int | None:
        pid = await asyncio.to_thread(build_next_feed_post)
        if pid is not None:
            await send_feed_for_review(pid)
        return pid

    pid = asyncio.run(_run())
    if pid is None:
        raise SystemExit("Kein Feed-Beitrag erstellt (Queue leer oder Generierung fehlgeschlagen)")
    print(f"Feed-Beitrag #{pid} erstellt und in die Review-Queue gestellt.")


def cmd_stockreel(ticker: str, topic: str) -> None:
    from src.stocks.stock_reel import build_stock_reel

    async def _run() -> int | None:
        rid = await asyncio.to_thread(build_stock_reel, ticker, topic)
        if rid is None:
            return None
        from src.review.telegram_bot import review_configured, send_for_review

        if review_configured():
            with session_scope() as session:
                reel = session.get(ReelRow, rid)
            await send_for_review(rid, reel.video_path, reel.caption)
        return rid

    rid = asyncio.run(_run())
    if rid is None:
        raise SystemExit("Aktien-Reel konnte nicht erstellt werden (siehe Logs)")
    print(f"Aktien-Reel #{rid} erstellt und in die Review-Queue gestellt.")


def cmd_dividendpost() -> None:
    from src.feedposts.dividend import build_dividend_post
    from src.feedposts.pipeline import send_feed_for_review

    async def _run() -> int | None:
        pid = await asyncio.to_thread(build_dividend_post)
        if pid is not None:
            await send_feed_for_review(pid)
        return pid

    pid = asyncio.run(_run())
    if pid is None:
        raise SystemExit("Dividenden-Post konnte nicht erstellt werden (zu wenige Daten)")
    print(f"Dividenden-Post #{pid} erstellt und in die Review-Queue gestellt.")


def cmd_post_feed(post_id: int) -> None:
    from src.feedposts.pipeline import publish_feed_post_by_id

    with session_scope() as session:
        post = session.get(FeedPostRow, post_id)
        if post is None:
            raise SystemExit(f"Feed-Post #{post_id} existiert nicht")
        if post.status not in ("approved", "pending_review"):
            raise SystemExit(f"Feed-Post #{post_id} hat Status '{post.status}' — nicht postbar")
    result = asyncio.run(publish_feed_post_by_id(post_id))
    if result is None:
        raise SystemExit(f"Feed-Post #{post_id} konnte nicht gepostet werden (siehe Logs)")
    print(f"Feed-Post #{post_id} veröffentlicht (+ New-Post-Story).")


def cmd_community() -> None:
    """One manual poll cycle (comments + DMs + digest) — for local dry-runs and
    Phase-1 validation. No-op unless COMMUNITY_ENABLED (per-part gates still apply)."""
    from src.community.comments import poll_comments
    from src.community.digest import build_digest
    from src.community.dms import poll_dms

    if not config.COMMUNITY_ENABLED:
        print("Hinweis: COMMUNITY_ENABLED=false — Pipelines sind deaktiviert (No-Op).")

    async def _run() -> tuple[dict, dict, int]:
        comments = await poll_comments()
        dms = await poll_dms()
        digest = await build_digest()
        return comments, dms, digest

    comments, dms, digest = asyncio.run(_run())
    print(f"Kommentare: {comments or 'deaktiviert'}")
    print(f"DMs:        {dms or 'deaktiviert'}")
    print(f"Digest:     {digest} neue Einträge")


def cmd_verify_ig() -> None:
    from src.publish.instagram import verify_credentials

    result = asyncio.run(verify_credentials())
    if not result["ok"]:
        print(f"❌ IG-Token-Check fehlgeschlagen: {result['error']}")
        raise SystemExit(1)

    print("✅ Token gültig")
    print(f"   Konto:      @{result['username']}  (user_id {result['user_id']})")
    if result["matches_config"] is True:
        print("   IG_USER_ID: stimmt mit .env überein")
    elif result["matches_config"] is False:
        print(f"   ⚠️ IG_USER_ID in .env ({config.IG_USER_ID}) ≠ Token-user_id ({result['user_id']})")
    print(f"   API-Pfad:   {result['graph_base']}"
          f"  ({'Instagram-Login' if result['is_ig_login'] else 'Facebook-Login'})")

    perms = result["permissions"]
    if perms is None:
        print("   Rechte:     über diesen API-Pfad nicht auslesbar — "
              "Posten scheitert sonst mit einem Rechte-Fehler (dann App Review / Scope prüfen)")
    else:
        need = "instagram_business_content_publish"
        mark = "✅" if need in perms else "❌ FEHLT"
        print(f"   Rechte:     {mark} {need}")
        print(f"               (erteilt: {', '.join(perms) or 'keine'})")

    if not result["publishing_configured"]:
        print("   Hinweis:    PUBLIC_MEDIA_BASE_URL/PUBLIC_MEDIA_DIR fehlen noch "
              "(für echtes Posten in Slice 2 nötig)")

    # Community edges (Kommentare/DMs/Hashtag-Suche) — nur Edge-Probing ist in der
    # Instagram-Login-Variante verlässlich, da /me/permissions dort fehlt.
    from src.community.api import GraphCommunityAPI

    try:
        probe = asyncio.run(GraphCommunityAPI().probe())
    except Exception as exc:  # noqa: BLE001 — Diagnose soll nie hart abbrechen
        probe = None
        print(f"   Community:  Probe fehlgeschlagen ({type(exc).__name__}: {exc})")
    if probe is not None:
        def _mark(ok: bool | None) -> str:
            return "✅" if ok else "❌ FEHLT"
        print(f"   DMs:        {_mark(probe['messaging'])} /me/conversations "
              "(Recht instagram_business_manage_messages + Nachrichten-Zugriff in der IG-App)")
        print(f"   Hashtags:   {_mark(probe['hashtag_search'])} ig_hashtag_search "
              "(in der Instagram-Login-Variante oft nicht verfügbar → Digest nutzt Fallback)")


def cmd_milestone(followers: int | None = None) -> None:
    """Check the follower count now; a newly crossed milestone goes to Telegram review."""
    from src.milestones import check_follower_milestone

    sid = asyncio.run(check_follower_milestone(followers))
    if sid is None:
        print("Kein neuer Meilenstein erreicht (oder Follower-Abruf nicht möglich)")
    else:
        print(f"Meilenstein-Story #{sid} wartet in Telegram auf Freigabe — "
              "nach ✅ postet der Scheduler sie sofort")


def cmd_post_story(story_id: int) -> None:
    from src.publish.instagram import publish_story
    from src.storage.database import StoryRow

    with session_scope() as session:
        story = session.get(StoryRow, story_id)
        if story is None:
            raise SystemExit(f"Story #{story_id} existiert nicht")
        image_path, status = story.image_path, story.status
    if status not in ("approved", "pending_review"):
        raise SystemExit(f"Story #{story_id} hat Status '{status}' — nicht postbar")

    media_id = asyncio.run(publish_story(image_path))
    with session_scope() as session:
        row = session.get(StoryRow, story_id)
        row.status = "published"
        row.ig_media_id = media_id
        row.published_at = datetime.now(timezone.utc).isoformat()
    print(f"Story #{story_id} veröffentlicht (IG media id {media_id})")


def cmd_publish(reel_id: int) -> None:
    from src.publish.instagram import publish_reel
    from src.pipeline import announce_new_reel

    with session_scope() as session:
        reel = session.get(ReelRow, reel_id)
        if reel is None:
            raise SystemExit(f"Reel #{reel_id} existiert nicht")

    async def _run() -> str:
        media_id = await publish_reel(reel.video_path, reel.caption)
        with session_scope() as session:
            row = session.get(ReelRow, reel_id)
            row.status = "published"
            row.ig_media_id = media_id
            row.published_at = datetime.now(timezone.utc).isoformat()
        await announce_new_reel(reel_id)  # auto "NEUES REEL" story
        return media_id

    media_id = asyncio.run(_run())
    print(f"Reel #{reel_id} veröffentlicht (IG media id {media_id}) + Ankündigungs-Story")


def cmd_status() -> None:
    with session_scope() as session:
        counts = dict(session.execute(
            select(ReelRow.status, func.count()).group_by(ReelRow.status)
        ).all())
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        spent = session.execute(
            select(func.sum(ApiUsageRow.cost_eur))
            .where(ApiUsageRow.provider == "claude", ApiUsageRow.date == today)
        ).scalar() or 0.0
        last = session.execute(
            select(ReelRow).where(ReelRow.status == "published")
            .order_by(ReelRow.published_at.desc()).limit(5)
        ).scalars().all()

    print("Reel-Queue:", counts or "leer")
    print(f"Claude heute: {spent:.2f} € / {config.CLAUDE_DAILY_BUDGET_EUR:.2f} €")
    for reel in last:
        print(f"  veröffentlicht {reel.published_at[:16]}  #{reel.id}  {reel.ig_media_id}")


async def _fetch_daily_insights() -> None:
    from src.publish.instagram import fetch_insights
    from src.storage.database import MetricRow

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with session_scope() as session:
        published = session.execute(
            select(ReelRow).where(ReelRow.status == "published", ReelRow.ig_media_id != "")
            .order_by(ReelRow.id.desc()).limit(30)
        ).scalars().all()
    for reel in published:
        data = await fetch_insights(reel.ig_media_id)
        if not data:
            continue
        with session_scope() as session:
            session.add(MetricRow(
                reel_id=reel.id, date=today,
                plays=data.get("views", 0), reach=data.get("reach", 0),
                likes=data.get("likes", 0), comments=data.get("comments", 0),
                saves=data.get("saved", 0), shares=data.get("shares", 0),
            ))
    logger.info(f"Insights für {len(published)} Reels abgerufen")


async def _run_loop() -> None:
    from src.pipeline import generate_once, handle_regenerates, publish_next_approved
    from src.publish.instagram import publishing_configured
    from src.review.telegram_bot import build_application, review_configured, send_text
    from src.feedposts.pipeline import (
        build_next_feed_post,
        publish_due_scheduled_feed_posts,
        publish_next_feed_post,
        send_feed_for_review,
    )
    from src.milestones import check_follower_milestone, publish_approved_milestones
    from src.stocks.pipeline import (
        build_daily_stories,
        publish_next_candidate_group,
        publish_next_story,
        send_stories_for_review,
    )

    telegram_app = None
    if review_configured():
        telegram_app = build_application()
        await telegram_app.initialize()
        await telegram_app.start()
        await telegram_app.updater.start_polling()
        logger.info("Telegram-Review-Bot lauscht")

    done_slots: set[tuple[str, str]] = set()  # (date, HH:MM) already handled
    last_generate = 0.0
    last_community_poll = 0.0

    try:
        while True:
            now = _now_local()
            slot_key = (now.strftime("%Y-%m-%d"), now.strftime("%H:%M"))

            # 1) reviewer asked for a re-generation
            regenerated = await asyncio.to_thread(handle_regenerates)
            for reel_id in regenerated:
                with session_scope() as session:
                    reel = session.get(ReelRow, reel_id)
                if review_configured():
                    from src.review.telegram_bot import send_for_review

                    await send_for_review(reel_id, reel.video_path, reel.caption)

            # 2) keep the review queue filled for the coming slots
            with session_scope() as session:
                queued = session.execute(
                    select(func.count()).where(ReelRow.status.in_(("pending_review", "approved")))
                ).scalar()
            if (
                queued < len(config.POSTING_SLOTS)
                and asyncio.get_event_loop().time() - last_generate > _GENERATE_COOLDOWN_S
            ):
                last_generate = asyncio.get_event_loop().time()
                await generate_once()

            # 3) posting slots
            if (
                publishing_configured()
                and now.strftime("%H:%M") in config.POSTING_SLOTS
                and slot_key not in done_slots
            ):
                done_slots.add(slot_key)
                published = await publish_next_approved()
                if published and review_configured():
                    await send_text(f"📤 Reel #{published} wurde gepostet.")

            # 4) daily stock stories: build once at STOCK_STORY_SLOT, then post the
            #    approved cards at their slots (earnings/overview morning, candidates
            #    at their market's trading hours).
            hhmm = now.strftime("%H:%M")
            if ((slot_key[0], "stocks_build") not in done_slots
                    and config.STOCK_STORY_SLOT <= hhmm < _STOCK_BUILD_CATCHUP_UNTIL):
                done_slots.add((slot_key[0], "stocks_build"))
                try:
                    story_ids = await asyncio.to_thread(build_daily_stories)
                    await send_stories_for_review(story_ids)
                except Exception as exc:  # noqa: BLE001 — a build failure must never kill the loop
                    logger.exception(f"Tages-Story-Build fehlgeschlagen: {exc}")
                    if review_configured():
                        await send_text(f"⚠️ Tages-Story-Build fehlgeschlagen: {exc}")

            if publishing_configured():
                if hhmm == config.STORY_POST_EARNINGS_SLOT and (slot_key[0], "story_morning") not in done_slots:
                    done_slots.add((slot_key[0], "story_morning"))
                    for kinds in (["earnings"], ["candidates"]):
                        sid = await publish_next_story(kinds=kinds)
                        if sid and review_configured():
                            await send_text(f"📤 Story #{sid} wurde gepostet.")
                for market, slots in (("EU", config.STORY_SLOTS_EU), ("US", config.STORY_SLOTS_US)):
                    key = (slot_key[0], f"story_{market}_{hhmm}")
                    if hhmm in slots and key not in done_slots:
                        done_slots.add(key)
                        posted = await publish_next_candidate_group(market=market)
                        trend = await publish_next_candidate_group(market=market, kind="trend")
                        if posted and review_configured():
                            await send_text(
                                f"📤 Kandidaten-Story ({market}, {len(posted)} Cards) gepostet."
                            )
                        if trend and review_configured():
                            await send_text(
                                f"📤 Trend-Aktien-Story ({market}, {len(trend)} Cards) gepostet."
                            )

            # 4b) follower milestones: daily check at the morning build slot; an
            #     approved milestone card posts IMMEDIATELY on the next tick
            #     (a thank-you story shouldn't wait for a stock-story slot).
            if (publishing_configured() and hhmm == config.STOCK_STORY_SLOT
                    and (slot_key[0], "milestone_check") not in done_slots):
                done_slots.add((slot_key[0], "milestone_check"))
                await check_follower_milestone()
            if publishing_configured():
                for sid in await publish_approved_milestones():
                    if review_configured():
                        await send_text(f"📤 Meilenstein-Story #{sid} wurde gepostet.")

            # 5) feed posts (2×/week): generate on a feed-slot day at the morning build
            #    tick, post at the exact slot time (weekday + HH:MM).
            feed_today = _feed_slots_today(now)
            if (feed_today and hhmm == config.STOCK_STORY_SLOT
                    and (slot_key[0], "feed_build") not in done_slots):
                done_slots.add((slot_key[0], "feed_build"))
                with session_scope() as session:
                    pending = session.execute(
                        select(func.count()).where(
                            FeedPostRow.status.in_(("pending_review", "approved")))
                    ).scalar()
                if not pending:
                    pid = await asyncio.to_thread(build_next_feed_post)
                    if pid is not None:
                        await send_feed_for_review(pid)

            if publishing_configured():
                for slot in feed_today:
                    slot_time = slot.split()[1]
                    key = (slot_key[0], f"feed_post_{slot_time}")
                    if hhmm == slot_time and key not in done_slots:
                        done_slots.add(key)
                        pid = await publish_next_feed_post()
                        if pid and review_configured():
                            await send_text(f"📤 Feed-Beitrag #{pid} wurde gepostet.")

                # time-scheduled feed posts whose moment has arrived
                for pid in await publish_due_scheduled_feed_posts(now.strftime("%Y-%m-%d %H:%M")):
                    if review_configured():
                        await send_text(f"📤 Geplanter Feed-Beitrag #{pid} wurde gepostet.")

            # 5b) weekly editorial reminder + auto topic proposal (Sunday)
            if (now.weekday() == _WEEKDAYS.get(config.FEED_EDITORIAL_DAY.upper(), 6)
                    and hhmm == config.FEED_EDITORIAL_TIME
                    and (slot_key[0], "editorial") not in done_slots):
                done_slots.add((slot_key[0], "editorial"))
                from src.feedposts.editorial import send_editorial_reminder

                await send_editorial_reminder()

            # 6) daily insights
            if now.strftime("%H:%M") == _INSIGHTS_SLOT and (slot_key[0], "insights") not in done_slots:
                done_slots.add((slot_key[0], "insights"))
                if publishing_configured():
                    await _fetch_daily_insights()

            # 7) community: poll comments (+ DMs) on an interval, digest once daily.
            #    LLM work inside the pollers runs via asyncio.to_thread, so the tick
            #    and the Telegram poller stay responsive.
            if config.COMMUNITY_ENABLED:
                loop_now = asyncio.get_event_loop().time()
                if loop_now - last_community_poll >= config.COMMUNITY_POLL_MINUTES * 60:
                    last_community_poll = loop_now
                    from src.community.comments import poll_comments

                    await poll_comments()
                    if config.COMMUNITY_DM_ENABLED:
                        from src.community.dms import poll_dms

                        await poll_dms()
                if (config.COMMUNITY_DIGEST_ENABLED
                        and hhmm == config.COMMUNITY_DIGEST_SLOT
                        and (slot_key[0], "digest") not in done_slots):
                    done_slots.add((slot_key[0], "digest"))
                    from src.community.digest import build_digest

                    await build_digest()

            await asyncio.sleep(_LOOP_TICK_S)
    finally:
        if telegram_app is not None:
            await telegram_app.updater.stop()
            await telegram_app.stop()
            await telegram_app.shutdown()


def _force_utf8_output() -> None:
    """Windows consoles default to cp1252 and choke on emoji/→ in our output."""
    import sys

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def main() -> None:
    _force_utf8_output()
    parser = argparse.ArgumentParser(description="Instagram Reel-Autopilot")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("collect")
    sub.add_parser("generate")
    sub.add_parser("stocks")
    sub.add_parser("feedpost")
    stockreel = sub.add_parser("stockreel")
    stockreel.add_argument("--ticker", required=True)
    stockreel.add_argument("--topic", default="")
    sub.add_parser("dividendpost")
    milestone = sub.add_parser("milestone")
    milestone.add_argument("--followers", type=int, default=None,
                           help="Follower-Zahl vorgeben statt sie von der API zu holen")
    sub.add_parser("verify-ig")
    sub.add_parser("community")
    sub.add_parser("run")
    sub.add_parser("status")
    publish = sub.add_parser("publish")
    publish.add_argument("--reel", type=int, required=True)
    post_story = sub.add_parser("post-story")
    post_story.add_argument("--story", type=int, required=True)
    post_feed = sub.add_parser("post-feed")
    post_feed.add_argument("--post", type=int, required=True)
    args = parser.parse_args()

    init_db()
    if args.command == "collect":
        cmd_collect()
    elif args.command == "generate":
        cmd_generate()
    elif args.command == "stocks":
        cmd_stocks()
    elif args.command == "feedpost":
        cmd_feedpost()
    elif args.command == "stockreel":
        cmd_stockreel(args.ticker, args.topic)
    elif args.command == "dividendpost":
        cmd_dividendpost()
    elif args.command == "milestone":
        cmd_milestone(args.followers)
    elif args.command == "verify-ig":
        cmd_verify_ig()
    elif args.command == "community":
        cmd_community()
    elif args.command == "run":
        asyncio.run(_run_loop())
    elif args.command == "status":
        cmd_status()
    elif args.command == "publish":
        cmd_publish(args.reel)
    elif args.command == "post-story":
        cmd_post_story(args.story)
    elif args.command == "post-feed":
        cmd_post_feed(args.post)


if __name__ == "__main__":
    main()
