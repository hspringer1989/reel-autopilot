"""reel-autopilot CLI.

  python main.py collect            # collect + score trends only
  python main.py generate           # produce one reel end-to-end → review queue
  python main.py stocks             # build today's earnings + watchlist stories → review
  python main.py feedpost           # generate the next educational feed carousel → review
  python main.py weekplan           # send the Redaktionssitzung (topic list) → Telegram approval
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
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from loguru import logger
from sqlalchemy import func, select

import config
from src.storage.database import ApiUsageRow, FeedPostRow, ReelRow, StoryRow, init_db, session_scope

_LOOP_TICK_S = 60
_GENERATE_COOLDOWN_S = 3600
_INSIGHTS_SLOT = "07:00"
_MILESTONE_CHECK_S = 900  # follower-milestone check interval (~15 min) so a crossed mark is pushed to review promptly
_SITE_BUILD_S = 3600  # rebuild the static analysis-archive website hourly (cheap; only new cards copied)
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
    if not config.ENABLE_STOCKS:
        raise SystemExit("Für diesen Kanal deaktiviert (ENABLE_STOCKS=false)")
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


def cmd_weekplan() -> None:
    """Send the Redaktionssitzung now: draft next week's topics → Telegram approval.
    Nothing is generated until the ✅ button is pressed (handled by `main.py run`)."""
    from src.feedposts.editorial import send_editorial_reminder

    asyncio.run(send_editorial_reminder())
    print("Redaktionssitzung an Telegram gesendet — Beiträge entstehen nach der Freigabe.")


def cmd_stockreel(ticker: str, topic: str) -> None:
    if not config.ENABLE_STOCKS:
        raise SystemExit("Für diesen Kanal deaktiviert (ENABLE_STOCKS=false)")
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
    if not config.ENABLE_DIVIDEND:
        raise SystemExit("Für diesen Kanal deaktiviert (ENABLE_DIVIDEND=false)")
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


def cmd_buildsite() -> None:
    """Rebuild the static 'Link in Bio' analysis archive (see PROFILE.SITE_URL)."""
    from src.site.generator import build_site

    if not config.ENABLE_SITE:
        raise SystemExit("Website-Modul ist für diesen Kanal aus (ENABLE_SITE=false)")
    n = build_site()
    print(f"Website neu gebaut: {n} Analysen → {config.SITE_DIR}")


def cmd_biohint() -> None:
    """Post the fixed weekly 'Website-Hinweis' story now (also runs Fridays 20:00)."""
    from src.bio_hint import post_bio_hint_story

    mid = asyncio.run(post_bio_hint_story())
    if mid is None:
        raise SystemExit("Website-Hinweis-Story konnte nicht gepostet werden (siehe Logs)")
    print(f"Website-Hinweis-Story gepostet (IG media id {mid})")


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


def _slot_due(hhmm: str, slot: str, catchup_min: int) -> bool:
    """Ist dieser Slot faellig — jetzt oder im Nachholfenster danach?

    Die Schleife tickt nicht zuverlaessig jede Minute: sie schlaeft 60 s am ENDE des
    Durchlaufs, und der Tages-Story-Build braucht regelmaessig ueber drei Minuten.
    Eine exakte Minutengleichheit verliert den Slot dann fuer den ganzen Tag —
    am 21.08.2026 kostete das ein freigegebenes Reel.

    Verglichen wird in Minuten seit Mitternacht, nicht als Zeichenkette, damit das
    Fenster auch ueber eine volle Stunde hinweg richtig rechnet.
    """
    def _min(t: str) -> int:
        h, m = t.split(":")
        return int(h) * 60 + int(m)

    now, start = _min(hhmm), _min(slot)
    return start <= now < start + catchup_min


class _SlotLedger:
    """Was heute schon gelaufen ist — ueber Neustarts hinweg.

    Ohne diese Persistenz waere das Nachholfenster gefaehrlich: ein Neustart um 09:30
    wuerde den 09:00-Slot erneut ausloesen. Frueher lag das nur im Arbeitsspeicher,
    weshalb ein Neustart im Vormittagsfenster doppelte Watchlist-Stapel erzeugte.

    Bewusst eine kleine JSON-Datei statt einer Tabelle: der Inhalt ist pro Tag ein
    paar Dutzend Bytes, er wird beim Start gelesen und ueberlebt einen Absturz.
    """

    _KEEP_DAYS = 3

    def __init__(self, path: Path):
        self._path = path
        self._done: dict[str, set[str]] = {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            self._done = {d: set(v) for d, v in raw.items()}
        except Exception:  # noqa: BLE001 — fehlende oder kaputte Datei: leer starten
            self._done = {}

    def __contains__(self, key: tuple[str, str]) -> bool:
        day, label = key
        return label in self._done.get(day, set())

    def add(self, key: tuple[str, str]) -> None:
        day, label = key
        self._done.setdefault(day, set()).add(label)
        for old in sorted(self._done)[:-self._KEEP_DAYS]:
            del self._done[old]
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps({d: sorted(v) for d, v in self._done.items()},
                           ensure_ascii=False),
                encoding="utf-8")
        except Exception as exc:  # noqa: BLE001 — nicht schreiben zu koennen darf
            logger.warning(f"Slot-Merkliste nicht speicherbar: {exc}")  # den Lauf nicht kippen


# Nachholfenster je Slot-Art. Kurz, wo das Publikum die Uhrzeit merkt; laenger, wo
# der Slot nur intern etwas anstoesst.
_CATCHUP_POST_MIN = 90      # Veroeffentlichungen: lieber spaet als gar nicht
_CATCHUP_STORY_MIN = 45     # Story-Slots liegen dicht beieinander
_CATCHUP_INTERNAL_MIN = 180  # Bauen, Erinnerungen, Auswertungen


async def _run_evening_autogen() -> None:
    """Abend-Automatik: Rueckschau, dann ein Reel fuer morgen in die Freigabe-Warteschlange.

    Zuerst der volle Weg (Recherche, Faktencheck, Opener nach Augenschein) — er bildet
    die Handarbeit nach. Nur wenn der nichts Belegbares findet, greift der RSS-Trend als
    Sicherheitsnetz; ein Reel aus einem ungeprueften Trend ist immer noch besser als gar
    keins, aber es ist die zweite Wahl, nicht die erste.

    Jeder Ausgang wird nach Telegram gemeldet. Ein stiller Ausfall ist der schlimmste
    Fall: dann wartet man morgens auf ein Reel, das nie gebaut wurde.
    """
    from src.content.autoreel import generate_autonomous_reel
    from src.content.reel_feedback import analyse_last_reel
    from src.pipeline import generate_once
    from src.review.telegram_bot import review_configured, send_text

    try:
        feedback = await analyse_last_reel()
        if review_configured():
            await send_text(feedback.text)
    except Exception as exc:  # noqa: BLE001 — die Rueckschau darf die Produktion nie kippen
        logger.exception(f"Rueckschau fehlgeschlagen: {exc}")
        feedback = None

    target = feedback.target_seconds if feedback else 40

    note = ""
    try:
        result = await generate_autonomous_reel(target_seconds=target)
        if result.reel_id is not None:
            logger.info(f"Abend-Automatik: Reel #{result.reel_id} steht zur Freigabe")
            return
        note = result.note
        logger.warning(f"Recherche-Pfad ohne Ergebnis: {note}")
    except Exception as exc:  # noqa: BLE001
        note = str(exc)
        logger.exception(f"Recherche-Pfad fehlgeschlagen: {exc}")

    if review_configured():
        await send_text(f"ℹ️ Recherche-Pfad ohne Ergebnis ({note}) — "
                        f"versuche den RSS-Trend.")
    try:
        new_id = await generate_once(
            target_seconds=target,
            max_age_hours=config.REEL_AUTOGEN_MAX_TREND_AGE_H,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception(f"RSS-Pfad fehlgeschlagen: {exc}")
        new_id = None

    if new_id is None and review_configured():
        await send_text("⚠️ Abend-Automatik: heute kein Reel erzeugt. "
                        "Weder Recherche noch RSS-Trend lieferten etwas Belegbares.")


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

    # Ueberlebt Neustarts — sonst feuert ein Slot im Nachholfenster ein zweites Mal.
    done_slots = _SlotLedger(Path(config.DATA_DIR) / "slot_ledger.json")
    last_generate = 0.0
    last_community_poll = 0.0
    last_milestone_check = 0.0
    last_site_build = 0.0

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
                and any(_slot_due(now.strftime("%H:%M"), s, _CATCHUP_POST_MIN)
                        for s in config.POSTING_SLOTS)
                and slot_key not in done_slots
            ):
                done_slots.add(slot_key)
                published = await publish_next_approved()
                if published and review_configured():
                    await send_text(f"📤 Reel #{published} wurde gepostet.")

            # 4) daily stock stories (ENABLE_STOCKS channels only): build once at
            #    STOCK_STORY_SLOT, then post the approved cards at their slots
            #    (earnings/overview morning, candidates at their market's trading hours).
            hhmm = now.strftime("%H:%M")
            if config.ENABLE_STOCKS:
                if ((slot_key[0], "stocks_build") not in done_slots
                        and config.STOCK_STORY_SLOT <= hhmm < _STOCK_BUILD_CATCHUP_UNTIL):
                    done_slots.add((slot_key[0], "stocks_build"))
                    # Neustart-Schutz: nur bauen, wenn für HEUTE noch keine Stories existieren.
                    # Ein Service-Neustart im Build-Fenster (bis mittags) darf sonst den ganzen
                    # Tages-Batch ein zweites Mal erzeugen (Duplikate in der Review-Queue).
                    with session_scope() as _sess:
                        _have = _sess.execute(select(func.count()).select_from(StoryRow).where(
                            StoryRow.trade_date == now.strftime("%Y-%m-%d"),
                            StoryRow.kind.in_(("candidates", "earnings"))  # nur der echte Tages-Batch (Uebersicht/Earnings), nicht manuelle Einzel-Analysen,
                        )).scalar()
                    if _have:
                        logger.info(f"Tages-Stories existieren bereits ({_have}) — Build übersprungen")
                    else:
                        try:
                            story_ids = await asyncio.to_thread(build_daily_stories)
                            await send_stories_for_review(story_ids)
                        except Exception as exc:  # noqa: BLE001 — a build failure must never kill the loop
                            logger.exception(f"Tages-Story-Build fehlgeschlagen: {exc}")
                            if review_configured():
                                await send_text(f"⚠️ Tages-Story-Build fehlgeschlagen: {exc}")

                if publishing_configured():
                    if (_slot_due(hhmm, config.STORY_POST_EARNINGS_SLOT, _CATCHUP_STORY_MIN)
                            and (slot_key[0], "story_morning") not in done_slots):
                        done_slots.add((slot_key[0], "story_morning"))
                        for kinds in (["earnings"], ["candidates"]):
                            sid = await publish_next_story(kinds=kinds)
                            if sid and review_configured():
                                await send_text(f"📤 Story #{sid} wurde gepostet.")
                    elif hhmm > config.STORY_POST_EARNINGS_SLOT:
                        # Nachhol-Logik: Earnings/Watchlist erst NACH dem 09:30-Slot freigegeben →
                        # sofort nachposten. Nur der heutige Tag — publish_next_story ist auf
                        # trade_date==heute gelockt, postet also nie eine Story vom Vortag.
                        for kinds in (["earnings"], ["candidates"]):
                            sid = await publish_next_story(kinds=kinds)
                            if sid and review_configured():
                                await send_text(f"📤 Story #{sid} nachgeholt (nach dem 09:30-Slot freigegeben).")
                    for market, slots in (("EU", config.STORY_SLOTS_EU), ("US", config.STORY_SLOTS_US)):
                        key = (slot_key[0], f"story_{market}_{hhmm}")
                        if (any(_slot_due(hhmm, s, _CATCHUP_STORY_MIN) for s in slots)
                                and key not in done_slots):
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

            # 4b) follower milestones: check FREQUENTLY (not just once a day) so a freshly
            #     crossed mark is auto-created and pushed to Telegram review within minutes;
            #     the story posts immediately once you approve it there (no auto-post).
            if publishing_configured():
                loop_now = asyncio.get_event_loop().time()
                if loop_now - last_milestone_check >= _MILESTONE_CHECK_S:
                    last_milestone_check = loop_now
                    await check_follower_milestone()
                for sid in await publish_approved_milestones():
                    if review_configured():
                        await send_text(f"📤 Meilenstein-Story #{sid} wurde gepostet.")

            # 5) feed posts (2×/week): generate on a feed-slot day at the morning build
            #    tick, post at the exact slot time (weekday + HH:MM).
            feed_today = _feed_slots_today(now)
            if (feed_today
                    and _slot_due(hhmm, config.DAILY_BUILD_SLOT, _CATCHUP_INTERNAL_MIN)
                    and (slot_key[0], "feed_build") not in done_slots):
                done_slots.add((slot_key[0], "feed_build"))
                with session_scope() as session:
                    pending = session.execute(
                        select(func.count()).where(
                            FeedPostRow.status.in_(("pending_review", "rebuilding", "approved")))
                    ).scalar()
                if not pending:
                    pid = await asyncio.to_thread(build_next_feed_post)
                    if pid is not None:
                        await send_feed_for_review(pid)

            if publishing_configured():
                for slot in feed_today:
                    slot_time = slot.split()[1]
                    key = (slot_key[0], f"feed_post_{slot_time}")
                    if (_slot_due(hhmm, slot_time, _CATCHUP_POST_MIN)
                            and key not in done_slots):
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
                    and _slot_due(hhmm, config.FEED_EDITORIAL_TIME, _CATCHUP_INTERNAL_MIN)
                    and (slot_key[0], "editorial") not in done_slots):
                done_slots.add((slot_key[0], "editorial"))
                from src.feedposts.editorial import send_editorial_reminder

                await send_editorial_reminder()

            # 5c) evening reel automation: look back at the last reel, then draft
            #     tomorrow's and put it in the Telegram review queue. Catch-up window
            #     because an exact-minute match is lost whenever a tick straddles it.
            if (config.REEL_AUTOGEN_TIME
                    and config.REEL_AUTOGEN_TIME <= hhmm < config.REEL_AUTOGEN_CATCHUP_UNTIL
                    and (slot_key[0], "autogen") not in done_slots):
                done_slots.add((slot_key[0], "autogen"))
                await _run_evening_autogen()

            # 6) daily insights
            if (_slot_due(now.strftime("%H:%M"), _INSIGHTS_SLOT, _CATCHUP_INTERNAL_MIN)
                    and (slot_key[0], "insights") not in done_slots):
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
                        and _slot_due(hhmm, config.COMMUNITY_DIGEST_SLOT, _CATCHUP_INTERNAL_MIN)
                        and (slot_key[0], "digest") not in done_slots):
                    done_slots.add((slot_key[0], "digest"))
                    from src.community.digest import build_digest

                    await build_digest()

            # 8) rebuild the static analysis-archive website hourly so newly posted
            #    analyses appear; cheap (only new card images are copied).
            loop_now = asyncio.get_event_loop().time()
            if config.ENABLE_SITE and loop_now - last_site_build >= _SITE_BUILD_S:
                last_site_build = loop_now
                from src.site.generator import build_site

                await asyncio.to_thread(build_site)

            # 9) weekly 'Website-Hinweis' story — every Friday 20:00 (fixed card, auto-post)
            if (config.ENABLE_BIO_HINT and publishing_configured()
                    and now.weekday() == 4 and _slot_due(hhmm, "20:00", _CATCHUP_STORY_MIN)
                    and (slot_key[0], "bio_hint") not in done_slots):
                done_slots.add((slot_key[0], "bio_hint"))
                from src.bio_hint import post_bio_hint_story

                mid = await post_bio_hint_story()
                if mid and review_configured():
                    await send_text("📤 Wöchentliche Website-Hinweis-Story wurde gepostet.")

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
    sub.add_parser("weekplan")
    stockreel = sub.add_parser("stockreel")
    stockreel.add_argument("--ticker", required=True)
    stockreel.add_argument("--topic", default="")
    sub.add_parser("dividendpost")
    milestone = sub.add_parser("milestone")
    milestone.add_argument("--followers", type=int, default=None,
                           help="Follower-Zahl vorgeben statt sie von der API zu holen")
    sub.add_parser("verify-ig")
    sub.add_parser("community")
    sub.add_parser("buildsite")
    sub.add_parser("biohint")
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
    elif args.command == "weekplan":
        cmd_weekplan()
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
    elif args.command == "buildsite":
        cmd_buildsite()
    elif args.command == "biohint":
        cmd_biohint()
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
