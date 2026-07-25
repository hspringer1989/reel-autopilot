"""Daily engagement digest: a Telegram list of relevant foreign posts/profiles to
engage with MANUALLY (ToS-compliant — the bot never auto-comments/likes/follows).

Primary source is IG hashtag search; on the Instagram-Login variant that edge is
usually unavailable, so it falls back to the configured profile handles plus a few
trending finance topics from the existing collectors as conversation starters.
"""
import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from loguru import logger
from sqlalchemy import select

import config
from src.community import guard
from src.community.api import CommunityAPI, get_api
from src.community.prompts import suggest_template
from src.content.llm import BudgetExceeded, LLMProvider, get_llm, parse_json_response
from src.storage.database import DigestItemRow, session_scope

_MAX_MEDIA_PER_HASHTAG = 3
_DIGEST_SYSTEM = config.PROFILE.DIGEST_SYSTEM_PROMPT


def _todays_hashtags() -> list[str]:
    """Rotate a small subset per day to stay well under 30 unique hashtags / 7 days."""
    tags = config.COMMUNITY_DIGEST_HASHTAGS
    per_day = max(1, config.COMMUNITY_DIGEST_HASHTAGS_PER_DAY)
    if not tags:
        return []
    doy = datetime.now(ZoneInfo(config.TIMEZONE)).timetuple().tm_yday
    start = (doy * per_day) % len(tags)
    picked: list[str] = []
    for i in range(min(per_day, len(tags))):
        tag = tags[(start + i) % len(tags)]
        if tag not in picked:
            picked.append(tag)
    return picked


async def _hashtag_items(api: CommunityAPI) -> list[dict]:
    """Return media items via hashtag search, or [] if the edge is unavailable."""
    items: list[dict] = []
    for tag in _todays_hashtags():
        hid = await api.find_hashtag_id(tag)
        if not hid:
            continue
        for media in (await api.hashtag_recent_media(hid))[:_MAX_MEDIA_PER_HASHTAG]:
            items.append({
                "uid": f"ht:{media['id']}", "source": "hashtag", "hashtag": tag,
                "permalink": media["permalink"], "caption": media["caption"][:200],
            })
    return items


def _topic_items() -> list[dict]:
    """Fallback conversation starters from the existing trend collectors."""
    from src.collectors.rss import active_collectors

    items: list[dict] = []
    seen: set[str] = set()
    for collector in active_collectors():
        for t in collector.safe_collect():
            if t.uid in seen:
                continue
            seen.add(t.uid)
            items.append({
                "uid": f"topic:{t.uid}", "source": "topic", "hashtag": "",
                "permalink": t.url, "caption": t.title[:200],
            })
            if len(items) >= 5:
                return items
    return items


def _profile_items() -> list[dict]:
    today = datetime.now(ZoneInfo(config.TIMEZONE)).strftime("%Y-%m-%d")
    items: list[dict] = []
    for handle in config.COMMUNITY_DIGEST_PROFILES:
        h = handle.lstrip("@")
        items.append({
            "uid": f"profile:{h}:{today}", "source": "profile", "hashtag": "",
            "permalink": f"https://instagram.com/{h}", "caption": f"Profil @{h} prüfen",
        })
    return items


def _draft_suggestions(items: list[dict], llm: LLMProvider) -> list[str]:
    """One batched Haiku call for comment suggestions; template fallback on budget/parse."""
    media = [it for it in items if it["source"] in ("hashtag", "topic")]
    fallback = {it["uid"]: suggest_template(it["caption"]) for it in items}
    if not media:
        return [fallback[it["uid"]] for it in items]
    listing = "\n".join(f"[{i}] {it['caption']}" for i, it in enumerate(media))
    try:
        raw = llm.complete(
            system=_DIGEST_SYSTEM.replace("{brand}", config.BRAND_NAME),
            user=f"Beiträge:\n{listing}",
            model=config.CLAUDE_MODEL_FAST, max_tokens=1200, purpose="community_digest",
        )
        data = parse_json_response(raw)
    except BudgetExceeded:
        logger.warning("Claude-Budget erschöpft — Digest nutzt Vorlagen-Vorschläge")
        data = None
    if isinstance(data, list):
        for entry in data:
            try:
                i = int(entry["i"])
                if 0 <= i < len(media):
                    fallback[media[i]["uid"]] = str(entry.get("comment", "")).strip() \
                        or fallback[media[i]["uid"]]
            except (KeyError, TypeError, ValueError):
                continue
    return [fallback[it["uid"]] for it in items]


async def build_digest(
    api: CommunityAPI | None = None, llm: LLMProvider | None = None
) -> int:
    """Assemble today's digest, persist new items, send one Telegram message.
    Returns the number of fresh items sent."""
    if not (guard.enabled() and config.COMMUNITY_DIGEST_ENABLED):
        return 0
    api = api or get_api()
    llm = llm or get_llm()

    items = await _hashtag_items(api)
    if not items:
        logger.info("Digest: Hashtag-Suche leer/nicht verfügbar → Profil-/Themen-Fallback")
        items = _profile_items() + _topic_items()
    if not items:
        return 0

    # Persist unseen items (dedup by uid) and only send those.
    fresh = _persist_new(items)
    if not fresh:
        logger.info("Digest: keine neuen Einträge")
        return 0

    suggestions = await asyncio.to_thread(_draft_suggestions, fresh, llm)
    for it, sug in zip(fresh, suggestions):
        it["suggested_comment"] = sug
        with session_scope() as session:
            row = session.execute(
                select(DigestItemRow).where(DigestItemRow.uid == it["uid"])
            ).scalar_one_or_none()
            if row is not None:
                row.suggested_comment = sug

    await _send_digest(fresh)
    return len(fresh)


def _persist_new(items: list[dict]) -> list[dict]:
    today = datetime.now(ZoneInfo(config.TIMEZONE)).strftime("%Y-%m-%d")
    fresh: list[dict] = []
    with session_scope() as session:
        for it in items:
            exists = session.execute(
                select(DigestItemRow).where(DigestItemRow.uid == it["uid"])
            ).scalar_one_or_none()
            if exists is not None:
                continue
            session.add(DigestItemRow(
                uid=it["uid"], source=it["source"], hashtag=it["hashtag"],
                permalink=it["permalink"], caption_excerpt=it["caption"], date=today,
            ))
            fresh.append(it)
    return fresh


async def _send_digest(items: list[dict]) -> None:
    from src.review.telegram_bot import review_configured, send_text

    if not review_configured():
        return
    lines = [f"📋 Engagement-Digest ({len(items)} Beiträge zum manuellen Kommentieren):\n"]
    for i, it in enumerate(items, 1):
        tag = f" #{it['hashtag']}" if it["hashtag"] else ""
        lines.append(
            f"{i}.{tag} {it['permalink']}\n   „{it['caption'][:80]}“\n"
            f"   💬 Vorschlag: {it.get('suggested_comment', '')}"
        )
    await send_text("\n".join(lines)[:4096])
