"""DM pipeline: poll conversations → dedup → classify each new inbound message with
thread context → auto-reply (non-sensitive, high confidence, within the 24h window) or
escalate to Telegram (sensitive / low confidence / window closed). Fully automatic per
the user's choice; sensitive cases are never auto-answered.
"""
import asyncio
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import select

import config
from src.community import guard
from src.community.api import CommunityAPI, CommunityAPIError, get_api
from src.community.classifier import Classification, classify_dm
from src.community.prompts import suggest_template
from src.content.llm import BudgetExceeded, LLMProvider, get_llm
from src.storage.database import DmMessageRow, DmThreadRow, session_scope


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _thread_context(thread_row_id: int, before_id: int) -> list[str]:
    """Prior messages of a thread (oldest first) for classification context."""
    with session_scope() as session:
        rows = session.execute(
            select(DmMessageRow).where(
                DmMessageRow.thread_id == thread_row_id, DmMessageRow.id < before_id
            ).order_by(DmMessageRow.id)
        ).scalars().all()
        return [f"{'wir' if r.direction == 'out' else 'Nutzer'}: {r.text}" for r in rows]


async def _ingest(api: CommunityAPI) -> list[int]:
    """Upsert threads + insert unseen messages. Returns new inbound message row ids."""
    new_ids: list[int] = []
    for thread in await api.fetch_conversations():
        with session_scope() as session:
            trow = session.execute(
                select(DmThreadRow).where(DmThreadRow.ig_thread_id == thread["id"])
            ).scalar_one_or_none()
            if trow is None:
                trow = DmThreadRow(
                    ig_thread_id=thread["id"], participant_id=thread["participant_id"],
                    participant_username=thread["participant_username"], status="open",
                )
                session.add(trow)
                session.flush()
            elif thread["participant_id"] and not trow.participant_id:
                trow.participant_id = thread["participant_id"]
            thread_row_id = trow.id

        for m in thread["messages"]:
            if not m["id"]:
                continue
            outbound = str(m["from_id"]) == str(config.IG_USER_ID)
            with session_scope() as session:
                exists = session.execute(
                    select(DmMessageRow.id).where(DmMessageRow.ig_message_id == m["id"])
                ).first()
                if exists:
                    continue
                row = DmMessageRow(
                    ig_message_id=m["id"], thread_id=thread_row_id,
                    direction="out" if outbound else "in",
                    text=m["text"], attachment_type=m["attachment_type"],
                    message_time=m["created_time"],
                    status="skipped" if outbound else "new",
                )
                session.add(row)
                session.flush()
                row_id = row.id
                if not outbound:
                    # Advance the reply-window clock to this inbound message.
                    trow = session.get(DmThreadRow, thread_row_id)
                    if m["created_time"] and m["created_time"] > trow.last_user_message_at:
                        trow.last_user_message_at = m["created_time"]
            if not outbound:
                new_ids.append(row_id)
    return new_ids


async def _send(row_id: int, api: CommunityAPI, text: str,
                ai_generated: bool = True) -> bool:
    """Send a DM reply and mark the row. False on API error.

    Automated replies carry the AI disclosure required by EU KI-VO Art. 50 Abs. 1;
    `ai_generated=False` is for text a human typed in the Telegram edit flow.
    """
    if ai_generated:
        from src.community.comments import mark_ai_reply

        text = mark_ai_reply(text)
    with session_scope() as session:
        row = session.get(DmMessageRow, row_id)
        thread = session.get(DmThreadRow, row.thread_id)
        recipient = thread.participant_id
    try:
        await api.send_dm(recipient, text)
    except CommunityAPIError as exc:
        with session_scope() as session:
            row = session.get(DmMessageRow, row_id)
            row.status = "failed"
            row.error = str(exc)[:500]
        logger.warning(f"DM-Antwort #{row_id} fehlgeschlagen: {exc}")
        return False
    with session_scope() as session:
        row = session.get(DmMessageRow, row_id)
        row.status = "auto_replied"
        row.reply_text = text
        row.replied_at = _utcnow()
    return True


async def _escalate(row_id: int, suggestion: str, window_open: bool) -> None:
    from src.review.telegram_bot import review_configured, send_dm_for_review

    with session_scope() as session:
        row = session.get(DmMessageRow, row_id)
        thread = session.get(DmThreadRow, row.thread_id)
        username, text, thread_row_id = thread.participant_username, row.text, row.thread_id
        row.status = "escalated"
        row.reply_text = suggestion
        thread.status = "escalated"
    if not review_configured():
        return
    context = "\n".join(_thread_context(thread_row_id, row_id))
    tg_id = await send_dm_for_review(row_id, username, text, context, suggestion, window_open)
    if tg_id is not None:
        with session_scope() as session:
            session.get(DmMessageRow, row_id).tg_message_id = str(tg_id)


async def _route(row_id: int, cl: Classification | None, api: CommunityAPI) -> str:
    from src.review.telegram_bot import review_configured, send_text

    with session_scope() as session:
        row = session.get(DmMessageRow, row_id)
        thread = session.get(DmThreadRow, row.thread_id)
        text, last_user_at = row.text, thread.last_user_message_at
    window_open = guard.within_dm_window(last_user_at)

    if cl is None:
        await _escalate(row_id, suggest_template(text), window_open)
        return "escalated"

    with session_scope() as session:
        row = session.get(DmMessageRow, row_id)
        row.classification = cl.classification
        row.confidence = cl.confidence

    if cl.classification == "spam":
        with session_scope() as session:
            session.get(DmMessageRow, row_id).status = "skipped"
        return "skipped"

    if guard.shadow_mode():
        with session_scope() as session:
            session.get(DmMessageRow, row_id).status = "shadow"
        if review_configured():
            await send_text(
                f"👻 Shadow-DM [{cl.classification} {cl.confidence:.2f}] „{text[:50]}“ → "
                f"hätte geantwortet: {cl.reply or '(eskaliert)'}"
            )
        return "shadow"

    auto_ok = (
        cl.classification in ("harmless", "substantive")
        and cl.confidence >= config.COMMUNITY_MIN_CONFIDENCE
        and bool(cl.reply)
        and window_open
        and not guard.rate_limit_reached()
    )
    if auto_ok:
        ok = await _send(row_id, api, cl.reply)
        return "auto_replied" if ok else "failed"

    await _escalate(row_id, cl.reply, window_open)
    return "escalated"


async def poll_dms(
    api: CommunityAPI | None = None, llm: LLMProvider | None = None
) -> dict[str, int]:
    if not (guard.enabled() and config.COMMUNITY_DM_ENABLED):
        return {}
    api = api or get_api()
    llm = llm or get_llm()

    new_ids = await _ingest(api)
    if not new_ids:
        return {"new": 0}

    summary: dict[str, int] = {"new": len(new_ids)}
    auto = 0
    for row_id in new_ids:
        with session_scope() as session:
            row = session.get(DmMessageRow, row_id)
            text, thread_id = row.text, row.thread_id
        context = _thread_context(thread_id, row_id)
        try:
            cl = await asyncio.to_thread(classify_dm, text, context, llm)
        except BudgetExceeded:
            logger.warning("Claude-Budget erschöpft — DM wird eskaliert")
            cl = None
        tag = await _route(row_id, cl, api)
        summary[tag] = summary.get(tag, 0) + 1
        if tag == "auto_replied":
            auto += 1

    from src.review.telegram_bot import review_configured, send_text

    if auto and not guard.shadow_mode() and review_configured():
        await send_text(f"🤖 {auto} DM(s) automatisch beantwortet.")
    logger.info(f"DM-Poll: {summary}")
    return summary


# ── Telegram callback + edit-flow entry points ─────────────────────────────
async def resolve_review(dm_id: int, action: str) -> str | None:
    api = get_api()
    with session_scope() as session:
        row = session.get(DmMessageRow, dm_id)
        if row is None:
            return None
        if row.status not in ("escalated", "pending_review"):
            return f"DM #{dm_id} ist bereits '{row.status}'"
        draft = row.reply_text

    if action == "skip":
        with session_scope() as session:
            session.get(DmMessageRow, dm_id).status = "skipped"
        return "❌ Übersprungen"
    if action == "approve":
        if not draft:
            return "⚠️ Kein Antworttext hinterlegt — bitte per Antwort auf die Nachricht formulieren."
        ok = await _send(dm_id, api, draft)
        return "✅ DM gesendet" if ok else "⚠️ DM konnte nicht gesendet werden"
    return None


async def resolve_edit(tg_message_id: str, custom_text: str) -> str | None:
    with session_scope() as session:
        row = session.execute(
            select(DmMessageRow).where(DmMessageRow.tg_message_id == str(tg_message_id))
        ).scalar_one_or_none()
        if row is None:
            return None
        if row.status not in ("escalated", "pending_review"):
            return f"DM #{row.id} ist bereits '{row.status}'"
        row_id = row.id
    ok = await _send(row_id, get_api(), custom_text, ai_generated=False)
    return "✅ Deine DM wurde gesendet" if ok else "⚠️ DM konnte nicht gesendet werden"
