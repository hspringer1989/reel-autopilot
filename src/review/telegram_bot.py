"""Review queue via Telegram: every rendered reel is sent with inline buttons.
Approval decisions update the reel status; the scheduler only publishes
status='approved'. (Same notification channel pattern as trading-bot.)"""
from pathlib import Path

from loguru import logger
from sqlalchemy import select
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import config
from src.storage.database import FeedPostRow, ReelRow, StoryRow, TrendRow, session_scope

_DECISIONS = {
    "approve": ("approved", "✅ Freigegeben — wird zum nächsten Slot gepostet"),
    "reject": ("rejected", "❌ Verworfen"),
    "regen": ("regenerate", "🔄 Wird neu generiert"),
}

_STORY_DECISIONS = {
    "approve": ("approved", "✅ Freigegeben — wird zur passenden Handelszeit gepostet"),
    "reject": ("rejected", "❌ Verworfen"),
}

_FEED_DECISIONS = {
    "approve": ("approved", "✅ Freigegeben — wird zum nächsten Feed-Slot gepostet"),
    "reject": ("rejected", "❌ Verworfen"),
}


def review_configured() -> bool:
    return bool(config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID)


def _keyboard(reel_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Posten", callback_data=f"approve:{reel_id}"),
        InlineKeyboardButton("🔄 Neu", callback_data=f"regen:{reel_id}"),
        InlineKeyboardButton("❌ Verwerfen", callback_data=f"reject:{reel_id}"),
    ]])


def _story_keyboard(story_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Posten", callback_data=f"story:approve:{story_id}"),
        InlineKeyboardButton("❌ Verwerfen", callback_data=f"story:reject:{story_id}"),
    ]])


def _provenance(reel_id: int) -> str:
    """Source link + fact-check block for a reel, assembled from the DB.

    Without the link a reviewer cannot check a claim without hunting for the article;
    the fact-check lines point at the segments the source does not cover. Returns ""
    when there is nothing to show."""
    with session_scope() as session:
        reel = session.get(ReelRow, reel_id)
        if reel is None:
            return ""
        trend = session.get(TrendRow, reel.trend_id) if reel.trend_id else None
        findings = reel.fact_check
        source = None
        if trend is not None:
            source = (trend.title, trend.url, trend.score_total,
                      trend.score_viral, trend.score_fit, trend.score_reasoning)

    lines: list[str] = []
    if source:
        title, url, total, viral, fit, reasoning = source
        lines.append("📄 Quelle")
        lines.append(title)
        if url:
            lines.append(url)
        if total:
            lines.append(f"Score {total:.2f}  (viral {viral:.2f} · fit {fit:.2f})")
        if reasoning:
            lines.append(f"„{reasoning[:200]}“")
    if findings:
        count = len(findings.splitlines())
        lines += ["", f"⚠️ Quellen-Abgleich: {count} Aussage(n) nicht durch die Quelle gedeckt"]
        lines += findings.splitlines()
        lines += ["", "Das ist ein Hinweis, kein Urteil — bitte im Artikel nachlesen."]
    return "\n".join(lines)


async def send_for_review(reel_id: int, video_path: str, caption: str) -> None:
    """One-shot send (usable from the CLI without the polling loop running;
    the button callback is processed once `python main.py run` polls).

    The video carries caption + buttons; source and fact-check follow as a SEPARATE
    message: the video caption is capped at 1024 characters, and appending to it would
    truncate the very text the reviewer is meant to approve."""
    bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
    text = f"🎬 Reel #{reel_id} wartet auf Freigabe\n\n{caption}"
    provenance = _provenance(reel_id)
    async with bot:
        with open(video_path, "rb") as video:
            await bot.send_video(
                chat_id=config.TELEGRAM_CHAT_ID,
                video=video,
                caption=text[:1024],
                reply_markup=_keyboard(reel_id),
                width=config.REEL_WIDTH,
                height=config.REEL_HEIGHT,
                supports_streaming=True,
                read_timeout=120,
                write_timeout=300,
            )
        if provenance:
            await bot.send_message(
                chat_id=config.TELEGRAM_CHAT_ID,
                text=provenance[:4096],
                disable_web_page_preview=True,
            )
    logger.info(f"Reel #{reel_id} zur Freigabe an Telegram gesendet")


async def send_photo_for_review(story_id: int, image_path: str, caption: str) -> None:
    """Send a rendered story card as a photo with ✅/❌ review buttons."""
    bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
    text = f"🖼 Story #{story_id} wartet auf Freigabe\n\n{caption}"
    async with bot:
        with open(image_path, "rb") as photo:
            await bot.send_photo(
                chat_id=config.TELEGRAM_CHAT_ID,
                photo=photo,
                caption=text[:1024],
                reply_markup=_story_keyboard(story_id),
                read_timeout=120,
                write_timeout=300,
            )
    logger.info(f"Story #{story_id} zur Freigabe an Telegram gesendet")


def _feed_keyboard(post_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Posten", callback_data=f"feed:approve:{post_id}"),
        InlineKeyboardButton("❌ Verwerfen", callback_data=f"feed:reject:{post_id}"),
    ]])


async def send_feed_review_prompt(post_id: int, title: str, caption: str) -> None:
    """After the slides, one text message with the caption and ✅/❌ buttons."""
    bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
    text = f"📰 Feed-Beitrag #{post_id} wartet auf Freigabe\n\n{title}\n\n{caption}"
    async with bot:
        await bot.send_message(
            chat_id=config.TELEGRAM_CHAT_ID, text=text[:4096],
            reply_markup=_feed_keyboard(post_id),
        )
    logger.info(f"Feed-Post #{post_id} zur Freigabe an Telegram gesendet")


async def send_photo_plain(image_path: str, caption: str) -> None:
    """Send a story card as context (no review buttons) — used for the chart and
    fundamental frames of a candidate; the overall frame carries the approval."""
    bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
    async with bot:
        with open(image_path, "rb") as photo:
            await bot.send_photo(
                chat_id=config.TELEGRAM_CHAT_ID,
                photo=photo,
                caption=caption[:1024],
                read_timeout=120,
                write_timeout=300,
            )


async def send_text(text: str) -> None:
    bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
    async with bot:
        await bot.send_message(chat_id=config.TELEGRAM_CHAT_ID, text=text[:4096])


def apply_decision(reel_id: int, action: str) -> str | None:
    """Pure DB part of a review decision (unit-testable without Telegram)."""
    if action not in _DECISIONS:
        return None
    status, ack = _DECISIONS[action]
    with session_scope() as session:
        reel = session.get(ReelRow, reel_id)
        if reel is None:
            return None
        if reel.status not in ("pending_review", "regenerate"):
            return f"Reel #{reel_id} ist bereits '{reel.status}'"
        reel.status = status
    logger.info(f"Review-Entscheidung für Reel #{reel_id}: {status}")
    return ack


def apply_story_decision(story_id: int, action: str) -> str | None:
    """Pure DB part of a story review decision (unit-testable without Telegram).
    For a candidate the decision cascades to ALL cards of that ticker+date (the 3
    frames are approved/rejected together via the button on the overall frame)."""
    if action not in _STORY_DECISIONS:
        return None
    status, ack = _STORY_DECISIONS[action]
    with session_scope() as session:
        story = session.get(StoryRow, story_id)
        if story is None:
            return None
        if story.status != "pending_review":
            return f"Story #{story_id} ist bereits '{story.status}'"
        if story.kind in ("candidate", "trend") and story.ticker:
            rows = session.execute(
                select(StoryRow).where(
                    StoryRow.kind == story.kind,
                    StoryRow.ticker == story.ticker,
                    StoryRow.trade_date == story.trade_date,
                    StoryRow.status == "pending_review",
                )
            ).scalars().all()
            for row in rows:
                row.status = status
            count = len(rows)
        else:
            story.status = status
            count = 1
    logger.info(f"Review-Entscheidung für Story #{story_id}: {status} ({count} Card(s))")
    return ack


def apply_feed_decision(post_id: int, action: str) -> str | None:
    """Pure DB part of a feed-post review decision (unit-testable without Telegram)."""
    if action not in _FEED_DECISIONS:
        return None
    status, ack = _FEED_DECISIONS[action]
    with session_scope() as session:
        post = session.get(FeedPostRow, post_id)
        if post is None:
            return None
        if post.status != "pending_review":
            return f"Feed-Post #{post_id} ist bereits '{post.status}'"
        post.status = status
    logger.info(f"Review-Entscheidung für Feed-Post #{post_id}: {status}")
    return ack


# ── Community: comment + DM escalation ─────────────────────────────────────
def _comment_keyboard(comment_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Antworten", callback_data=f"cmt:approve:{comment_id}"),
        InlineKeyboardButton("❌ Überspringen", callback_data=f"cmt:skip:{comment_id}"),
        InlineKeyboardButton("🙈 Verbergen", callback_data=f"cmt:hide:{comment_id}"),
    ]])


def _dm_keyboard(dm_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Senden", callback_data=f"dm:approve:{dm_id}"),
        InlineKeyboardButton("❌ Überspringen", callback_data=f"dm:skip:{dm_id}"),
    ]])


async def send_comment_for_review(
    comment_id: int, author: str, comment_text: str, media_context: str, suggestion: str
) -> int | None:
    """Escalate a comment to Telegram with an editable reply suggestion. Returns the
    Telegram message id (stored so a reply-to-message can drive the edit flow)."""
    bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
    text = (
        f"💬 Kommentar von @{author} unter „{media_context[:60]}“:\n"
        f"„{comment_text}“\n\n"
        f"Vorschlag: {suggestion or '(kein Entwurf — bitte selbst formulieren)'}\n\n"
        "↩️ Zum Anpassen einfach auf diese Nachricht antworten."
    )
    async with bot:
        msg = await bot.send_message(
            chat_id=config.TELEGRAM_CHAT_ID, text=text[:4096],
            reply_markup=_comment_keyboard(comment_id),
        )
    return msg.message_id


async def send_dm_for_review(
    dm_id: int, username: str, dm_text: str, context: str, suggestion: str,
    window_open: bool = True,
) -> int | None:
    """Escalate a DM to Telegram. `window_open=False` warns that the 24h reply
    window has closed (a reply would be rejected by Instagram)."""
    bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
    warn = "" if window_open else "\n⚠️ 24h-Antwortfenster geschlossen — Antwort ggf. nicht zustellbar."
    ctx = f"\nVerlauf:\n{context}\n" if context else "\n"
    text = (
        f"✉️ DM von @{username}:\n„{dm_text}“{ctx}"
        f"Vorschlag: {suggestion or '(kein Entwurf — bitte selbst formulieren)'}{warn}\n\n"
        "↩️ Zum Anpassen einfach auf diese Nachricht antworten."
    )
    async with bot:
        msg = await bot.send_message(
            chat_id=config.TELEGRAM_CHAT_ID, text=text[:4096],
            reply_markup=_dm_keyboard(dm_id),
        )
    return msg.message_id


async def _finish_callback(query, note: str) -> None:
    """Strip buttons and append the outcome note to the reviewed message."""
    msg = query.message
    if msg.caption is not None:  # photo message (reel/story)
        await query.edit_message_caption(
            caption=f"{msg.caption}\n\n{note}"[:1024], reply_markup=None
        )
    else:  # text message (feed/community prompt)
        await query.edit_message_text(
            text=f"{msg.text or ''}\n\n{note}"[:4096], reply_markup=None
        )


async def _on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    # Community comment/DM decisions post immediately (or skip/hide) via the
    # community pipelines, then annotate the message. Handled up front and returned.
    if query.data.startswith(("cmt:", "dm:")):
        try:
            prefix, action, raw_id = query.data.split(":", 2)
            item_id = int(raw_id)
        except (ValueError, AttributeError):
            await _finish_callback(query, "⚠️ Unbekannte Aktion")
            return
        if prefix == "cmt":
            from src.community import comments as community_comments

            ack = await community_comments.resolve_review(item_id, action)
        else:
            from src.community import dms as community_dms

            ack = await community_dms.resolve_review(item_id, action)
        await _finish_callback(query, ack or "⚠️ Unbekannte Aktion")
        return

    kind, action, item_id, ack = None, None, None, None
    try:
        if query.data.startswith("story:"):
            _, action, raw_id = query.data.split(":", 2)
            kind, item_id = "story", int(raw_id)
            ack = apply_story_decision(item_id, action)
        elif query.data.startswith("feed:"):
            _, action, raw_id = query.data.split(":", 2)
            kind, item_id = "feed", int(raw_id)
            ack = apply_feed_decision(item_id, action)
        else:
            action, raw_id = query.data.split(":", 1)
            kind, item_id = "reel", int(raw_id)
            ack = apply_decision(item_id, action)
    except (ValueError, AttributeError):
        ack = None
    await _finish_callback(query, ack or "⚠️ Unbekannte Aktion")

    # On approval a feed post publishes IMMEDIATELY (+ announcement story) — UNLESS it has
    # a future scheduled_at, in which case the scheduler posts it at that time.
    if kind == "feed" and action == "approve" and ack and "bereits" not in ack:
        from datetime import datetime
        from zoneinfo import ZoneInfo

        now_local = datetime.now(ZoneInfo(config.TIMEZONE)).strftime("%Y-%m-%d %H:%M")
        with session_scope() as session:
            post = session.get(FeedPostRow, item_id)
            scheduled = post.scheduled_at if post else ""
        if scheduled and scheduled > now_local:
            await send_text(f"🕒 Feed-Beitrag #{item_id} freigegeben — wird am {scheduled} Uhr gepostet.")
        else:
            from src.feedposts.pipeline import publish_feed_post_by_id

            posted = await publish_feed_post_by_id(item_id)
            await send_text(
                f"📤 Feed-Beitrag #{item_id} wurde gepostet (+ Ankündigungs-Story)."
                if posted else
                f"⚠️ Feed-Beitrag #{item_id} konnte nicht gepostet werden (siehe Logs)."
            )


async def _on_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Edit flow: replying (Telegram "Reply") to a community escalation with custom
    text posts THAT text as the comment/DM reply. Restricted to the review chat."""
    msg = update.message
    if msg is None or msg.reply_to_message is None:
        return
    if str(msg.chat_id) != str(config.TELEGRAM_CHAT_ID):
        return
    target_tg_id = str(msg.reply_to_message.message_id)
    custom = (msg.text or "").strip()
    if not custom:
        return

    from src.community import comments as community_comments
    from src.community import dms as community_dms

    ack = await community_comments.resolve_edit(target_tg_id, custom)
    if ack is None:
        ack = await community_dms.resolve_edit(target_tg_id, custom)
    if ack is not None:
        await msg.reply_text(ack)


def build_application() -> Application:
    """Polling application for `python main.py run` — processes review buttons."""
    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CallbackQueryHandler(_on_callback))
    app.add_handler(MessageHandler(filters.TEXT & filters.REPLY, _on_reply))
    return app
