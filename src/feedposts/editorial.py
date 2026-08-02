"""Weekly editorial workflow: plan + create the coming week's feed posts together, then
publish them at one fixed daily slot (Mon–Sun).

Full loop, all of it inside Telegram:
  1. `send_editorial_reminder` proposes topics, PERSISTS them as a WeekPlanRow and sends
     the list with [✅ Beiträge erstellen | 🔄 Neue Themen | ❌ Verwerfen] buttons.
  2. Replying to that message with free text revises the list (Claude) and re-asks.
  3. On ✅ the posts are generated, each pinned to its day's slot, and each goes through
     its OWN single-post review (approve / adjust by reply / reject).
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from loguru import logger
from sqlalchemy import select

import config
from src.content.llm import LLMProvider, get_llm, parse_json_response
from src.content.usage import claude_budget_exceeded
from src.feedposts.generator import build_feed_post
from src.feedposts.pipeline import _full_caption, _stamp, send_feed_for_review
from src.feedposts.renderer import render_feed_slides
from src.storage.database import FeedPostRow, WeekPlanRow, session_scope


def _now() -> datetime:
    return datetime.now(ZoneInfo(config.TIMEZONE))


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def next_week_start() -> date:
    """The next Monday strictly in the future."""
    today = _now()
    ahead = (0 - today.weekday()) % 7 or 7
    return (today + timedelta(days=ahead)).date()


def next_week_slots(post_time: str | None = None, days: int | None = None) -> list[str]:
    """The coming Mon..(Mon+days-1) at `post_time`, as 'YYYY-MM-DD HH:MM' local strings.
    Always the NEXT Monday strictly in the future."""
    post_time = post_time or config.FEED_DAILY_POST_TIME
    days = days or config.FEED_WEEKLY_POSTS
    monday = next_week_start()
    return [f"{monday + timedelta(days=i)} {post_time}" for i in range(days)]


def plan_slots(week_start: str, n: int, post_time: str | None = None) -> list[str]:
    """Slots for a plan that was proposed for `week_start` (YYYY-MM-DD).

    Slots already in the past are skipped forward — approving a plan late must not make
    posts publish instantly (`publish_due_scheduled_feed_posts` fires on scheduled_at <= now).
    """
    post_time = post_time or config.FEED_DAILY_POST_TIME
    try:
        start = datetime.strptime(week_start, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        start = next_week_start()
    now = _now()
    earliest = now.date() if now.strftime("%H:%M") < post_time else now.date() + timedelta(days=1)
    day = max(start, earliest)
    return [f"{day + timedelta(days=i)} {post_time}" for i in range(n)]


def recent_titles(limit: int = 40) -> list[str]:
    with session_scope() as session:
        return [t for (t,) in session.execute(
            select(FeedPostRow.title).order_by(FeedPostRow.id.desc()).limit(limit)
        ).all() if t]


_PROPOSE_SYSTEM = config.PROFILE.EDITORIAL_SYSTEM_PROMPT

_PROPOSE_USER = """Schlage {n} Beitragsthemen für die kommende Woche vor (ein Beitrag pro Tag).
Vermeide diese kürzlich behandelten Themen: {avoid}

Gib genau diese JSON-Struktur zurück:
{{"topics": [
  {{"slug": "kurz-kebab-case", "title": "knackiger Titel", "brief": "1-2 Sätze: worum es geht, welche Entscheidungslogik/Anwendbarkeit"}}
]}}"""

_REVISE_USER = """Das ist der aktuelle Themenplan für die kommende Woche:
{current}

Der Redakteur wünscht folgende Änderung:
„{instruction}"

Setze den Wunsch um und gib den KOMPLETTEN, aktualisierten Plan mit genau {n} Themen zurück.
Themen, die nicht betroffen sind, bleiben unverändert (gleicher slug, gleicher Titel).
Vermeide diese kürzlich behandelten Themen: {avoid}

Gib genau diese JSON-Struktur zurück:
{{"topics": [
  {{"slug": "kurz-kebab-case", "title": "knackiger Titel", "brief": "1-2 Sätze: worum es geht, welche Entscheidungslogik/Anwendbarkeit"}}
]}}"""


def _clean_topics(raw: object, n: int) -> list[dict]:
    """Normalise an LLM topic list into [{slug, title, brief}] (max n entries)."""
    topics = raw.get("topics", []) if isinstance(raw, dict) else []
    out: list[dict] = []
    for t in topics[:n]:
        if isinstance(t, dict) and t.get("title") and t.get("brief"):
            out.append({
                "slug": str(t.get("slug") or t["title"]).strip().lower().replace(" ", "-")[:60],
                "title": str(t["title"]).strip(),
                "brief": str(t["brief"]).strip(),
            })
    return out


def propose_week_topics(llm: LLMProvider | None = None, n: int | None = None) -> list[dict]:
    """One budget-gated Claude call → a list of {slug, title, brief} topic proposals."""
    n = n or config.FEED_WEEKLY_POSTS
    llm = llm or get_llm()
    if claude_budget_exceeded():
        return []
    try:
        raw = llm.complete(
            system=_PROPOSE_SYSTEM,
            user=_PROPOSE_USER.format(n=n, avoid="; ".join(recent_titles()) or "—"),
            model=config.CLAUDE_MODEL_FAST, max_tokens=1200, purpose="week_plan",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Themenvorschlag fehlgeschlagen: {exc}")
        return []
    return _clean_topics(parse_json_response(raw), n)


def parse_topics_text(text: str, n: int | None = None) -> list[dict]:
    """Parse a hand-written topic list ('1. Titel — Leitplanke' per line) into topics.
    Offline fallback for `revise_week_topics`; a single line is NOT treated as a list."""
    n = n or config.FEED_WEEKLY_POSTS
    lines = [ln.strip(" -•\t") for ln in (text or "").splitlines() if ln.strip(" -•\t")]
    if len(lines) < 2:
        return []
    out: list[dict] = []
    for line in lines[:n]:
        head = line.split(".", 1)
        body = head[1].strip() if len(head) == 2 and head[0].isdigit() else line
        title, _, brief = body.partition("—")
        if not title.strip():
            continue
        title = title.strip()
        out.append({
            "slug": title.lower().replace(" ", "-")[:60],
            "title": title,
            "brief": brief.strip() or title,
        })
    return out


def revise_week_topics(
    topics: list[dict], instruction: str, llm: LLMProvider | None = None, n: int | None = None
) -> list[dict]:
    """Apply a free-text wish ('Thema 3 raus, dafür was zu Dividenden') to a topic list.
    Falls back to parsing the instruction as a plain list of titles when Claude is
    unavailable (budget/API), so the user is never stuck."""
    n = n or len(topics) or config.FEED_WEEKLY_POSTS
    llm = llm or get_llm()
    current = "\n".join(f"{i + 1}. {t['title']} — {t['brief']}" for i, t in enumerate(topics))
    if not claude_budget_exceeded():
        try:
            raw = llm.complete(
                system=_PROPOSE_SYSTEM,
                user=_REVISE_USER.format(
                    current=current or "—", instruction=instruction.strip(), n=n,
                    avoid="; ".join(recent_titles()) or "—",
                ),
                model=config.CLAUDE_MODEL_FAST, max_tokens=1400, purpose="week_plan",
            )
            revised = _clean_topics(parse_json_response(raw), n)
            if revised:
                return revised
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Themen-Revision fehlgeschlagen: {exc}")
    return parse_topics_text(instruction, n) or topics


# ── Plan persistence ───────────────────────────────────────────────────────
def save_plan(topics: list[dict], week_start: str | None = None) -> int:
    """Persist a proposed plan as pending_review. Returns the plan id."""
    with session_scope() as session:
        row = WeekPlanRow(
            week_start=week_start or str(next_week_start()),
            topics_json=json.dumps(topics, ensure_ascii=False),
            status="pending_review",
        )
        session.add(row)
        session.flush()
        return row.id


def get_plan(plan_id: int) -> dict | None:
    with session_scope() as session:
        row = session.get(WeekPlanRow, plan_id)
        if row is None:
            return None
        return {
            "id": row.id, "week_start": row.week_start, "status": row.status,
            "topics": json.loads(row.topics_json or "[]"),
            "tg_message_id": row.tg_message_id,
        }


def plan_by_tg_message(tg_message_id: str) -> dict | None:
    """The pending plan a Telegram reply refers to (reply-to-message edit flow)."""
    with session_scope() as session:
        row = session.execute(
            select(WeekPlanRow).where(
                WeekPlanRow.tg_message_id == str(tg_message_id),
                WeekPlanRow.status == "pending_review",
            )
        ).scalars().first()
        if row is None:
            return None
        return {
            "id": row.id, "week_start": row.week_start, "status": row.status,
            "topics": json.loads(row.topics_json or "[]"),
        }


def set_plan_topics(plan_id: int, topics: list[dict]) -> None:
    with session_scope() as session:
        row = session.get(WeekPlanRow, plan_id)
        if row is not None:
            row.topics_json = json.dumps(topics, ensure_ascii=False)


def set_plan_status(plan_id: int, status: str, error: str = "") -> None:
    with session_scope() as session:
        row = session.get(WeekPlanRow, plan_id)
        if row is not None:
            row.status = status
            row.decided_at = _utcnow()
            if error:
                row.error = error[:2000]


def set_plan_message(plan_id: int, tg_message_id: str | int) -> None:
    with session_scope() as session:
        row = session.get(WeekPlanRow, plan_id)
        if row is not None:
            row.tg_message_id = str(tg_message_id)


def plan_message(topics: list[dict], week_start: str | None = None) -> str:
    """The Telegram text of a Redaktionssitzung proposal."""
    start = week_start or str(next_week_start())
    slots = plan_slots(start, len(topics) or config.FEED_WEEKLY_POSTS)
    lines = ["🗓️ Redaktionssitzung — Plan für die kommende Woche",
             f"({len(topics)} Beiträge, je {config.FEED_DAILY_POST_TIME} Uhr)\n"]
    if topics:
        for i, t in enumerate(topics):
            day = slots[i][:10] if i < len(slots) else ""
            lines.append(f"{i + 1}. {t['title']}  ({day})")
            lines.append(f"    {t['brief']}")
        lines.append(
            "\n✅ = ich erstelle alle Beiträge; jeder kommt danach einzeln zur Freigabe."
            "\n↩️ Änderungswunsch? Einfach auf diese Nachricht antworten "
            "(z. B. „Thema 3 raus, dafür etwas zu Dividenden“)."
        )
    else:
        lines.append("Womit wollen wir die Woche füllen? Antworte auf diese Nachricht "
                     "mit deinen Themen (eine Zeile pro Beitrag).")
    return "\n".join(lines)


# ── Generation (after approval) ────────────────────────────────────────────
def generate_week_posts(topics: list[dict], llm: LLMProvider | None = None,
                        week_start: str | None = None) -> list[int]:
    """Blocking part: generate + render every topic and pin it to its day's slot.
    Returns the created post ids (pending_review, not yet sent to Telegram)."""
    llm = llm or get_llm()
    slots = plan_slots(week_start or str(next_week_start()), len(topics))
    created: list[int] = []
    for topic, slot in zip(topics, slots):
        try:
            post = build_feed_post(topic["slug"], topic["title"], topic["brief"], llm)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Thema '{topic['slug']}' fehlgeschlagen: {exc}")
            continue
        if post is None:
            logger.warning(f"Thema '{topic['slug']}' konnte nicht generiert werden")
            continue
        paths = render_feed_slides(post, str(config.FEED_DIR), _stamp())
        with session_scope() as session:
            row = FeedPostRow(
                topic_slug=topic["slug"], title=post.title, brief=topic["brief"],
                slides_json=json.dumps([asdict(s) for s in post.slides], ensure_ascii=False),
                image_paths_json=json.dumps(paths, ensure_ascii=False),
                caption=_full_caption(post.caption, post.hashtags),
                status="pending_review", scheduled_at=slot,
            )
            session.add(row)
            session.flush()
            pid = row.id
        created.append(pid)
        logger.info(f"Wochen-Post #{pid} '{topic['slug']}' geplant fuer {slot}")
    return created


def schedule_week(topics: list[dict], llm: LLMProvider | None = None) -> list[int]:
    """Sync convenience wrapper (CLI/tests): generate the week AND send every post to
    the Telegram review queue. Inside the running bot use `build_approved_plan`."""
    import asyncio

    created = generate_week_posts(topics, llm)

    async def _send() -> None:
        for pid in created:
            await send_feed_for_review(pid)
    asyncio.run(_send())
    return created


async def build_approved_plan(plan_id: int, llm: LLMProvider | None = None) -> list[int]:
    """Async path used by the Telegram button: generate the approved plan off the event
    loop (Claude + Pillow are blocking), then send each post to its own review."""
    plan = get_plan(plan_id)
    if plan is None or not plan["topics"]:
        return []
    set_plan_status(plan_id, "building")
    try:
        created = await asyncio.to_thread(
            generate_week_posts, plan["topics"], llm, plan["week_start"]
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Wochenplan #{plan_id} fehlgeschlagen: {exc}")
        set_plan_status(plan_id, "failed", str(exc))
        return []

    with session_scope() as session:
        row = session.get(WeekPlanRow, plan_id)
        if row is not None:
            row.post_ids_json = json.dumps(created)
            row.status = "built"
            row.decided_at = _utcnow()

    for pid in created:
        await send_feed_for_review(pid)
    logger.info(f"Wochenplan #{plan_id}: {len(created)} Beiträge zur Einzelfreigabe gesendet")
    return created


# ── Telegram entry points ──────────────────────────────────────────────────
async def send_plan_for_review(plan_id: int) -> None:
    """(Re)send a stored plan with its approval buttons and remember the message id."""
    from src.review.telegram_bot import send_plan_review_prompt

    plan = get_plan(plan_id)
    if plan is None:
        return
    msg_id = await send_plan_review_prompt(
        plan_id, plan_message(plan["topics"], plan["week_start"])
    )
    if msg_id:
        set_plan_message(plan_id, msg_id)


async def send_editorial_reminder() -> None:
    """Editorial day: draft next week's topics, persist them and ask for approval."""
    from src.review.telegram_bot import review_configured

    if not review_configured():
        return
    topics = propose_week_topics()
    plan_id = save_plan(topics)
    await send_plan_for_review(plan_id)
    logger.info(f"Redaktions-Reminder (Plan #{plan_id}, {len(topics)} Themen) an Telegram gesendet")


async def resolve_plan_edit(tg_message_id: str, instruction: str) -> str | None:
    """A reply to the plan message: revise the topics and re-ask for approval.
    Returns an ack, or None if the reply did not target a pending plan."""
    plan = plan_by_tg_message(tg_message_id)
    if plan is None:
        return None
    revised = await asyncio.to_thread(revise_week_topics, plan["topics"], instruction)
    set_plan_topics(plan["id"], revised)
    await send_plan_for_review(plan["id"])
    return "✏️ Plan angepasst — die neue Liste steht zur Freigabe."
