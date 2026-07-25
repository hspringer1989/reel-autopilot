"""Comment pipeline: poll comments on our own recent media → dedup → classify →
auto-reply (harmless, high confidence) / escalate to Telegram (substantive/sensitive
or low confidence) / skip (spam). Shadow mode classifies + notifies but never posts.

resolve_review()/resolve_edit() are the Telegram callback + edit-flow entry points.
"""
import asyncio
from datetime import datetime, timedelta, timezone

from loguru import logger
from sqlalchemy import select

import config
from src.community import guard
from src.community.api import CommunityAPI, CommunityAPIError, get_api
from src.community.classifier import Classification, classify_comments
from src.community.prompts import suggest_template
from src.content.llm import BudgetExceeded, LLMProvider, get_llm
from src.storage.database import (
    CommentRow,
    FeedPostRow,
    ReelRow,
    session_scope,
)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _target_media() -> list[tuple[str, str, str]]:
    """Own published media within the lookback window: (ig_media_id, kind, context)."""
    cutoff = (datetime.now(timezone.utc)
              - timedelta(days=config.COMMUNITY_COMMENT_LOOKBACK_DAYS)).isoformat()
    targets: list[tuple[str, str, str]] = []
    with session_scope() as session:
        reels = session.execute(
            select(ReelRow).where(
                ReelRow.status == "published", ReelRow.ig_media_id != "",
                ReelRow.published_at >= cutoff,
            )
        ).scalars().all()
        for r in reels:
            targets.append((r.ig_media_id, "reel", (r.caption or "")[:80]))
        posts = session.execute(
            select(FeedPostRow).where(
                FeedPostRow.status == "published", FeedPostRow.ig_media_id != "",
                FeedPostRow.published_at >= cutoff,
            )
        ).scalars().all()
        for p in posts:
            targets.append((p.ig_media_id, "feed", (p.title or "")[:80]))
    return targets


async def _ingest(api: CommunityAPI) -> list[int]:
    """Fetch comments on target media, insert unseen non-own ones. Returns new row ids."""
    new_ids: list[int] = []
    for media_id, kind, context in _target_media():
        for c in await api.fetch_comments(media_id):
            if not c["id"] or guard.is_own(c["from_id"], c["username"]):
                continue
            with session_scope() as session:
                exists = session.execute(
                    select(CommentRow.id).where(CommentRow.ig_comment_id == c["id"])
                ).first()
                if exists:
                    continue
                row = CommentRow(
                    ig_comment_id=c["id"], ig_media_id=media_id, media_kind=kind,
                    parent_ig_comment_id=c["parent_id"], author_id=c["from_id"],
                    author_username=c["username"], text=c["text"],
                    comment_time=c["timestamp"], status="new",
                    reply_text=context,  # temp: carry media context for classification
                )
                session.add(row)
                session.flush()
                new_ids.append(row.id)
    return new_ids


async def _post_reply(row_id: int, api: CommunityAPI, text: str) -> bool:
    """Post a reply to the comment and mark the row replied. False on API error."""
    with session_scope() as session:
        row = session.get(CommentRow, row_id)
        ig_id = row.ig_comment_id
    try:
        reply_ig = await api.reply_to_comment(ig_id, text)
    except CommunityAPIError as exc:
        with session_scope() as session:
            row = session.get(CommentRow, row_id)
            row.status = "failed"
            row.error = str(exc)[:500]
        logger.warning(f"Kommentar-Antwort #{row_id} fehlgeschlagen: {exc}")
        return False
    with session_scope() as session:
        row = session.get(CommentRow, row_id)
        row.status = "replied" if row.status != "new" else "auto_replied"
        row.reply_text = text
        row.reply_ig_id = reply_ig
        row.replied_at = _utcnow()
    return True


async def _escalate(row_id: int, suggestion: str) -> None:
    """Send a comment to Telegram for approval; store the tg message id for edit-flow."""
    from src.review.telegram_bot import review_configured, send_comment_for_review

    with session_scope() as session:
        row = session.get(CommentRow, row_id)
        author, text, context = row.author_username, row.text, row.reply_text
        row.status = "pending_review"
        row.reply_text = suggestion  # the draft awaiting ✅
    if not review_configured():
        return
    tg_id = await send_comment_for_review(row_id, author, text, context, suggestion)
    if tg_id is not None:
        with session_scope() as session:
            session.get(CommentRow, row_id).tg_message_id = str(tg_id)


async def _route(row_id: int, cl: Classification | None, api: CommunityAPI) -> str:
    """Apply the routing decision for one classified comment. Returns an outcome tag."""
    from src.review.telegram_bot import review_configured, send_text

    # Budget exhausted / parse failure → escalate with a template suggestion.
    if cl is None:
        with session_scope() as session:
            text = session.get(CommentRow, row_id).text
        await _escalate(row_id, suggest_template(text))
        return "escalated"

    with session_scope() as session:
        row = session.get(CommentRow, row_id)
        row.classification = cl.classification
        row.confidence = cl.confidence

    if cl.classification == "spam":
        with session_scope() as session:
            session.get(CommentRow, row_id).status = "skipped"
        return "skipped"

    if guard.shadow_mode():
        with session_scope() as session:
            row = session.get(CommentRow, row_id)
            row.status = "shadow"
            row.reply_text = cl.reply
        if review_configured():
            await send_text(
                f"👻 Shadow [{cl.classification} {cl.confidence:.2f}] auf „{row.text[:50]}“ → "
                f"hätte geantwortet: {cl.reply or '(eskaliert)'}"
            )
        return "shadow"

    auto_ok = (
        cl.classification == "harmless"
        and cl.confidence >= config.COMMUNITY_MIN_CONFIDENCE
        and bool(cl.reply)
        and not guard.rate_limit_reached()
    )
    if auto_ok:
        ok = await _post_reply(row_id, api, cl.reply)
        return "auto_replied" if ok else "failed"

    await _escalate(row_id, cl.reply)
    return "escalated"


async def poll_comments(
    api: CommunityAPI | None = None, llm: LLMProvider | None = None
) -> dict[str, int]:
    """One poll cycle. Returns a small outcome summary for logging/notifications."""
    if not guard.enabled():
        return {}
    api = api or get_api()
    llm = llm or get_llm()

    new_ids = await _ingest(api)
    if not new_ids:
        return {"new": 0}

    with session_scope() as session:
        rows = [session.get(CommentRow, rid) for rid in new_ids]
        items = [{"text": r.text, "media_context": r.reply_text} for r in rows]

    try:
        # LLM call blocks; run off the event loop so the Telegram poller stays live.
        classifications = await asyncio.to_thread(classify_comments, items, llm)
    except BudgetExceeded:
        logger.warning("Claude-Budget erschöpft — Kommentare werden eskaliert")
        classifications = [None] * len(new_ids)

    summary: dict[str, int] = {"new": len(new_ids)}
    auto_count = 0
    for row_id, cl in zip(new_ids, classifications):
        tag = await _route(row_id, cl, api)
        summary[tag] = summary.get(tag, 0) + 1
        if tag == "auto_replied":
            auto_count += 1

    from src.review.telegram_bot import review_configured, send_text

    if auto_count and not guard.shadow_mode() and review_configured():
        await send_text(f"🤖 {auto_count} Kommentar(e) automatisch beantwortet.")
    logger.info(f"Kommentar-Poll: {summary}")
    return summary


# ── Telegram callback + edit-flow entry points ─────────────────────────────
async def resolve_review(comment_id: int, action: str) -> str | None:
    """Handle a cmt: button. approve → post the stored draft; skip → skipped;
    hide → hide on IG + skipped. Mirrors apply_decision's double-action guard."""
    api = get_api()
    with session_scope() as session:
        row = session.get(CommentRow, comment_id)
        if row is None:
            return None
        if row.status not in ("pending_review", "escalated"):
            return f"Kommentar #{comment_id} ist bereits '{row.status}'"
        ig_id, draft = row.ig_comment_id, row.reply_text

    if action == "skip":
        with session_scope() as session:
            session.get(CommentRow, comment_id).status = "skipped"
        return "❌ Übersprungen"
    if action == "hide":
        await api.hide_comment(ig_id, True)
        with session_scope() as session:
            session.get(CommentRow, comment_id).status = "skipped"
        return "🙈 Verborgen"
    if action == "approve":
        if not draft:
            return "⚠️ Kein Antworttext hinterlegt — bitte per Antwort auf die Nachricht formulieren."
        ok = await _post_reply(comment_id, api, draft)
        return "✅ Antwort gepostet" if ok else "⚠️ Antwort konnte nicht gepostet werden"
    return None


async def resolve_edit(tg_message_id: str, custom_text: str) -> str | None:
    """Handle a Telegram reply-to-message: post `custom_text` as the reply.
    Returns None if no comment maps to this Telegram message (so DMs can be tried)."""
    with session_scope() as session:
        row = session.execute(
            select(CommentRow).where(CommentRow.tg_message_id == str(tg_message_id))
        ).scalar_one_or_none()
        if row is None:
            return None
        if row.status not in ("pending_review", "escalated"):
            return f"Kommentar #{row.id} ist bereits '{row.status}'"
        row_id = row.id
    ok = await _post_reply(row_id, get_api(), custom_text)
    return "✅ Deine Antwort wurde gepostet" if ok else "⚠️ Antwort konnte nicht gepostet werden"
