"""Safety gates shared by the comment + DM pipelines: kill-switch, shadow mode,
own-account filter, and a combined hourly outbound rate limit."""
from datetime import datetime, timedelta, timezone

from loguru import logger

import config
from src.storage.database import replies_sent_since, session_scope


def enabled() -> bool:
    return config.COMMUNITY_ENABLED


def shadow_mode() -> bool:
    """Phase 1: classify + notify but never write to Instagram."""
    return config.COMMUNITY_SHADOW_MODE


def is_own(author_id: str, username: str) -> bool:
    """True if a comment/message is from our own account (never reply to ourselves)."""
    if author_id and str(author_id) == str(config.IG_USER_ID):
        return True
    handle = config.BRAND_HANDLE.lstrip("@").lower()
    return bool(username) and username.lower() == handle


def rate_limit_reached() -> bool:
    """True once COMMUNITY_MAX_REPLIES_PER_HOUR outbound replies (comments + DMs)
    have gone out in the last 60 minutes — then queue/escalate instead of sending."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    with session_scope() as session:
        sent = replies_sent_since(session, cutoff)
    if sent >= config.COMMUNITY_MAX_REPLIES_PER_HOUR:
        logger.warning(
            f"Community-Rate-Limit erreicht ({sent}/{config.COMMUNITY_MAX_REPLIES_PER_HOUR} "
            "Antworten in der letzten Stunde) — weitere Antworten werden eskaliert"
        )
        return True
    return False


def within_dm_window(last_user_message_at: str) -> bool:
    """Instagram only allows a reply within COMMUNITY_DM_WINDOW_HOURS of the user's
    last message. Empty/unparseable timestamp → treat as outside the window (escalate)."""
    if not last_user_message_at:
        return False
    try:
        ts = datetime.fromisoformat(last_user_message_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - ts
    return age <= timedelta(hours=config.COMMUNITY_DM_WINDOW_HOURS)
