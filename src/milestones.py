"""Follower-milestone stories: once the account crosses a mark from
config.FOLLOWER_MILESTONES, a thank-you story card (design:
channels/<CHANNEL>/assets/templates/story-meilenstein.png) is rendered and queued for Telegram
review. Approved milestone cards are posted IMMEDIATELY on the next scheduler
tick — a thank-you shouldn't wait for a stock-story slot.

Announced milestones are tracked in the stories table itself (kind='milestone',
ticker=<mark>), so no extra state: a rejected card frees the mark again."""
from __future__ import annotations

from zoneinfo import ZoneInfo
from datetime import datetime

from loguru import logger
from sqlalchemy import select

import config
from src.storage.database import StoryRow, session_scope

_DISCLAIMER = "⚠️ Keine Anlageberatung — nur Bildung & Unterhaltung. Werbung."


def announced_milestones() -> set[int]:
    """Marks that already have a non-rejected milestone story (any status)."""
    with session_scope() as session:
        rows = session.execute(
            select(StoryRow.ticker).where(
                StoryRow.kind == "milestone", StoryRow.status != "rejected",
            )
        ).scalars().all()
    return {int(t) for t in rows if t.isdigit()}


def milestone_reached(followers: int, announced: set[int],
                      milestones: list[int] | None = None) -> int | None:
    """Highest configured mark ≤ followers that has not been announced yet."""
    milestones = config.FOLLOWER_MILESTONES if milestones is None else milestones
    reached = [m for m in milestones if m <= followers and m not in announced]
    return max(reached) if reached else None


def next_goal(milestone: int, milestones: list[int] | None = None) -> int:
    """The mark after `milestone` (fallback: double it, so the card always has
    a next goal even beyond the configured list)."""
    milestones = config.FOLLOWER_MILESTONES if milestones is None else milestones
    return next((m for m in sorted(milestones) if m > milestone), milestone * 2)


async def check_follower_milestone(followers: int | None = None) -> int | None:
    """Fetch the follower count (unless given) and, if a new mark is crossed,
    render the milestone card and send it to Telegram review. Returns the new
    StoryRow id, or None if there is nothing to announce."""
    from src.publish.instagram import fetch_follower_count
    from src.stocks.pipeline import send_stories_for_review
    from src.stocks.story_cards import render_milestone_story

    if followers is None:
        followers = await fetch_follower_count()
    if not followers:
        return None
    milestone = milestone_reached(followers, announced_milestones())
    if milestone is None:
        return None

    goal = next_goal(milestone)
    today = datetime.now(ZoneInfo(config.TIMEZONE))
    path = render_milestone_story(
        milestone, goal,
        str(config.STORY_DIR / f"milestone_{milestone}_{today.strftime('%Y%m%d')}.jpg"),
        current=followers,
    )
    caption = (f"🎉 Meilenstein: {milestone} Follower geknackt (aktuell {followers})!\n"
               f"Nach ✅ wird die Story sofort gepostet.\n\n{_DISCLAIMER}")
    with session_scope() as session:
        row = StoryRow(kind="milestone", ticker=str(milestone), image_path=path,
                       caption=caption, trade_date=today.strftime("%Y-%m-%d"),
                       status="pending_review")
        session.add(row)
        session.flush()
        sid = row.id
    logger.info(f"Meilenstein-Story #{sid} ({milestone} Follower) → Review")
    await send_stories_for_review([sid])
    return sid


async def publish_approved_milestones() -> list[int]:
    """Post every approved milestone story right away (no fixed slot)."""
    from src.stocks.pipeline import _publish_one

    with session_scope() as session:
        ids = session.execute(
            select(StoryRow.id).where(
                StoryRow.kind == "milestone", StoryRow.status == "approved",
            ).order_by(StoryRow.id)
        ).scalars().all()
    posted = []
    for sid in ids:
        if await _publish_one(sid) is not None:
            posted.append(sid)
    return posted
