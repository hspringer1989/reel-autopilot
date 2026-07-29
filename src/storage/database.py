"""SQLite persistence (SQLAlchemy ORM), pattern borrowed from trading-bot."""
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import Float, Integer, String, Text, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

import config

# Reel lifecycle: draft → pending_review → approved → published
#                              └→ rejected / regenerate       └→ failed
REEL_STATUSES = (
    "draft", "pending_review", "approved", "rejected", "regenerate", "published", "failed",
)


class Base(DeclarativeBase):
    pass


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class TrendRow(Base):
    __tablename__ = "trends"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    source: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str] = mapped_column(Text, default="")
    popularity: Mapped[float] = mapped_column(Float, default=0.0)
    # new → scored → used | skipped
    status: Mapped[str] = mapped_column(String(16), default="new", index=True)
    score_total: Mapped[float] = mapped_column(Float, default=0.0)
    score_viral: Mapped[float] = mapped_column(Float, default=0.0)
    score_fit: Mapped[float] = mapped_column(Float, default=0.0)
    score_monetization: Mapped[float] = mapped_column(Float, default=0.0)
    score_reasoning: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(40), default=_utcnow)


class ReelRow(Base):
    __tablename__ = "reels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trend_id: Mapped[int] = mapped_column(Integer, index=True)
    script_json: Mapped[str] = mapped_column(Text, default="")
    audio_path: Mapped[str] = mapped_column(Text, default="")
    video_path: Mapped[str] = mapped_column(Text, default="")
    caption: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    error: Mapped[str] = mapped_column(Text, default="")
    # Befunde des Quellen-Abgleichs (src/content/factcheck.py), eine Zeile je ungedecktem
    # Segment. Rein beratend: sie erscheinen in der Telegram-Freigabe, blockieren nichts.
    fact_check: Mapped[str] = mapped_column(Text, default="")
    # Gescheiterte Publish-Versuche: unterhalb der Obergrenze bleibt das Reel 'approved'
    # (Retry am nächsten Slot), weil Instagrams Verarbeitung transient scheitern kann.
    publish_attempts: Mapped[int] = mapped_column(Integer, default=0)
    ig_media_id: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[str] = mapped_column(String(40), default=_utcnow)
    published_at: Mapped[str] = mapped_column(String(40), default="")


class StoryRow(Base):
    """A rendered Instagram-story card in the review/posting queue.
    kind: earnings | candidates | candidate. Same status flow as reels."""
    __tablename__ = "stories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), index=True)
    part: Mapped[str] = mapped_column(String(12), default="", index=True)  # candidate: chart|fundamental|overall
    ticker: Mapped[str] = mapped_column(String(16), default="")  # only for kind='candidate'
    market: Mapped[str] = mapped_column(String(4), default="")   # US | EU
    image_path: Mapped[str] = mapped_column(Text, default="")
    caption: Mapped[str] = mapped_column(Text, default="")
    analysis_json: Mapped[str] = mapped_column(Text, default="")
    trade_date: Mapped[str] = mapped_column(String(10), index=True, default="")  # YYYY-MM-DD
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    error: Mapped[str] = mapped_column(Text, default="")
    ig_media_id: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[str] = mapped_column(String(40), default=_utcnow)
    published_at: Mapped[str] = mapped_column(String(40), default="")


class FeedTopicRow(Base):
    """Backlog of educational feed-post topics (seeded once). status: queued | used."""
    __tablename__ = "feed_topics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(Text)
    brief: Mapped[str] = mapped_column(Text, default="")   # guidance for the generator
    position: Mapped[int] = mapped_column(Integer, default=0, index=True)
    status: Mapped[str] = mapped_column(String(12), default="queued", index=True)


class FeedPostRow(Base):
    """A generated multi-slide carousel feed post. Same review flow as stories."""
    __tablename__ = "feed_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic_slug: Mapped[str] = mapped_column(String(64), index=True, default="")
    title: Mapped[str] = mapped_column(Text, default="")
    slides_json: Mapped[str] = mapped_column(Text, default="")        # [{heading, body}, …]
    image_paths_json: Mapped[str] = mapped_column(Text, default="")   # [path, …] in order
    caption: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    error: Mapped[str] = mapped_column(Text, default="")
    ig_media_id: Mapped[str] = mapped_column(String(64), default="")
    scheduled_at: Mapped[str] = mapped_column(String(20), default="", index=True)  # local "YYYY-MM-DD HH:MM"
    created_at: Mapped[str] = mapped_column(String(40), default=_utcnow)
    published_at: Mapped[str] = mapped_column(String(40), default="")


# Seed backlog comes from the channel profile (seeding is idempotent by slug, so an
# existing DB is never re-seeded with another channel's topics).
_FEED_TOPIC_SEED = config.PROFILE.FEED_TOPIC_SEED


class MetricRow(Base):
    __tablename__ = "metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reel_id: Mapped[int] = mapped_column(Integer, index=True)
    date: Mapped[str] = mapped_column(String(10), index=True)  # YYYY-MM-DD
    plays: Mapped[int] = mapped_column(Integer, default=0)
    reach: Mapped[int] = mapped_column(Integer, default=0)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    comments: Mapped[int] = mapped_column(Integer, default=0)
    saves: Mapped[int] = mapped_column(Integer, default=0)
    shares: Mapped[int] = mapped_column(Integer, default=0)


class ApiUsageRow(Base):
    __tablename__ = "api_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[str] = mapped_column(String(10), index=True)  # YYYY-MM-DD (UTC)
    provider: Mapped[str] = mapped_column(String(20), index=True)  # claude | elevenlabs
    purpose: Mapped[str] = mapped_column(String(40), default="")
    cost_eur: Mapped[float] = mapped_column(Float, default=0.0)
    units: Mapped[int] = mapped_column(Integer, default=0)  # tokens or characters
    created_at: Mapped[str] = mapped_column(String(40), default=_utcnow)


# ── Community (DM-/Kommentar-Automatisierung + Engagement-Digest) ───────────
# Classification is the routing decision for a comment/DM:
#   harmless   → auto-reply (thanks, emoji, simple praise)
#   substantive→ Telegram approval (finance question, discussion, correction)
#   sensitive  → Telegram approval, NEVER auto (buy/sell/target, complaint, legal, cooperation)
#   spam       → skip/hide, never reply
COMMUNITY_CLASSES = ("harmless", "substantive", "sensitive", "spam")

# Comment status flow:
#   new → auto_replied            (harmless, live mode)
#       → pending_review → replied (substantive/sensitive, after Telegram ✅)
#       → skipped                  (spam or ❌)
#       → escalated                (budget/rate-limit → handled manually in Telegram)
#       → shadow                   (Phase 1: classified + notified, never acted on)
#       → failed                   (API error while replying)
COMMENT_STATUSES = (
    "new", "auto_replied", "pending_review", "replied", "skipped",
    "escalated", "shadow", "failed",
)


class CommentRow(Base):
    """A comment on one of our own published media (reel/feed), tracked for
    auto-reply / escalation. Deduped by the Instagram comment id."""
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ig_comment_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    ig_media_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    parent_ig_comment_id: Mapped[str] = mapped_column(String(64), default="")  # thread reply
    media_kind: Mapped[str] = mapped_column(String(8), default="")  # reel | feed
    author_id: Mapped[str] = mapped_column(String(64), default="")
    author_username: Mapped[str] = mapped_column(String(64), default="")
    text: Mapped[str] = mapped_column(Text, default="")
    comment_time: Mapped[str] = mapped_column(String(40), default="")  # IG timestamp
    classification: Mapped[str] = mapped_column(String(16), default="", index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(20), default="new", index=True)
    reply_text: Mapped[str] = mapped_column(Text, default="")   # draft or posted reply
    reply_ig_id: Mapped[str] = mapped_column(String(64), default="")
    tg_message_id: Mapped[str] = mapped_column(String(32), default="", index=True)  # edit-flow lookup
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(40), default=_utcnow)
    replied_at: Mapped[str] = mapped_column(String(40), default="")  # set when a reply is sent


class DmThreadRow(Base):
    """One Instagram direct-message conversation. `last_user_message_at` drives the
    24h reply-window check; status open|escalated|muted."""
    __tablename__ = "dm_threads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ig_thread_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    participant_id: Mapped[str] = mapped_column(String(64), default="")  # IGSID of the user
    participant_username: Mapped[str] = mapped_column(String(64), default="")
    last_user_message_at: Mapped[str] = mapped_column(String(40), default="")  # IG timestamp
    status: Mapped[str] = mapped_column(String(12), default="open", index=True)
    updated_at: Mapped[str] = mapped_column(String(40), default=_utcnow)


# DM message status flow mirrors comments (no pending_review batch — DMs auto-reply
# or escalate directly, per the user's "vollautomatisch" choice).
DM_STATUSES = ("new", "auto_replied", "escalated", "skipped", "shadow", "failed")


class DmMessageRow(Base):
    """One direct message inside a thread. Inbound messages get classified and
    answered; outbound messages are logged for thread context. Deduped by IG id."""
    __tablename__ = "dm_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ig_message_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    thread_id: Mapped[int] = mapped_column(Integer, index=True)  # FK → dm_threads.id
    direction: Mapped[str] = mapped_column(String(4), default="in")  # in | out
    text: Mapped[str] = mapped_column(Text, default="")
    attachment_type: Mapped[str] = mapped_column(String(24), default="")  # e.g. story_reply, share
    classification: Mapped[str] = mapped_column(String(16), default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(16), default="new", index=True)
    reply_text: Mapped[str] = mapped_column(Text, default="")
    tg_message_id: Mapped[str] = mapped_column(String(32), default="", index=True)
    error: Mapped[str] = mapped_column(Text, default="")
    message_time: Mapped[str] = mapped_column(String(40), default="")  # IG timestamp
    created_at: Mapped[str] = mapped_column(String(40), default=_utcnow)
    replied_at: Mapped[str] = mapped_column(String(40), default="")


class DigestItemRow(Base):
    """One entry of the daily engagement digest (relevant foreign post / profile to
    engage with MANUALLY). Deduped by uid; status sent|dismissed."""
    __tablename__ = "digest_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    source: Mapped[str] = mapped_column(String(16), default="")  # hashtag | profile | topic
    hashtag: Mapped[str] = mapped_column(String(48), default="")
    permalink: Mapped[str] = mapped_column(Text, default="")
    caption_excerpt: Mapped[str] = mapped_column(Text, default="")
    suggested_comment: Mapped[str] = mapped_column(Text, default="")
    date: Mapped[str] = mapped_column(String(10), index=True, default="")  # YYYY-MM-DD (local)
    status: Mapped[str] = mapped_column(String(12), default="sent", index=True)
    created_at: Mapped[str] = mapped_column(String(40), default=_utcnow)


_engine = None
_session_factory = None


def _migrate(engine) -> None:
    """Lightweight additive migrations for SQLite (create_all never ALTERs)."""
    with engine.begin() as conn:
        story_cols = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(stories)").fetchall()}
        if story_cols and "part" not in story_cols:
            conn.exec_driver_sql("ALTER TABLE stories ADD COLUMN part VARCHAR(12) DEFAULT ''")
        feed_cols = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(feed_posts)").fetchall()}
        if feed_cols and "scheduled_at" not in feed_cols:
            conn.exec_driver_sql("ALTER TABLE feed_posts ADD COLUMN scheduled_at VARCHAR(20) DEFAULT ''")
        reel_cols = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(reels)").fetchall()}
        if reel_cols and "fact_check" not in reel_cols:
            conn.exec_driver_sql("ALTER TABLE reels ADD COLUMN fact_check TEXT DEFAULT ''")
        if reel_cols and "publish_attempts" not in reel_cols:
            conn.exec_driver_sql("ALTER TABLE reels ADD COLUMN publish_attempts INTEGER DEFAULT 0")


def _seed_feed_topics(session_factory) -> None:
    """Insert the seed feed-post topics once (idempotent by slug)."""
    session = session_factory()
    try:
        existing = {s for (s,) in session.execute(select(FeedTopicRow.slug)).all()}
        for pos, (slug, title, brief) in enumerate(_FEED_TOPIC_SEED):
            if slug not in existing:
                session.add(FeedTopicRow(slug=slug, title=title, brief=brief, position=pos))
        session.commit()
    finally:
        session.close()


def init_db(db_path: str | None = None) -> None:
    global _engine, _session_factory
    path = db_path or str(config.DB_PATH)
    _engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(_engine)
    _migrate(_engine)
    _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
    _seed_feed_topics(_session_factory)


@contextmanager
def session_scope():
    if _session_factory is None:
        init_db()
    session: Session = _session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def trend_uid_known(session: Session, uid: str) -> bool:
    return session.execute(select(TrendRow.id).where(TrendRow.uid == uid)).first() is not None


def daily_usage_eur(session: Session, provider: str, date: str) -> float:
    total = session.execute(
        select(func.sum(ApiUsageRow.cost_eur))
        .where(ApiUsageRow.provider == provider, ApiUsageRow.date == date)
    ).scalar()
    return float(total or 0.0)


def daily_usage_units(session: Session, provider: str, date: str) -> int:
    total = session.execute(
        select(func.sum(ApiUsageRow.units))
        .where(ApiUsageRow.provider == provider, ApiUsageRow.date == date)
    ).scalar()
    return int(total or 0)


def replies_sent_since(session: Session, iso_cutoff: str) -> int:
    """Count outbound community replies (comments + DMs) sent at/after `iso_cutoff`
    (ISO-8601 UTC). Drives the combined hourly rate limit in the community guard."""
    comments = session.execute(
        select(func.count()).where(
            CommentRow.replied_at != "", CommentRow.replied_at >= iso_cutoff
        )
    ).scalar()
    dms = session.execute(
        select(func.count()).where(
            DmMessageRow.replied_at != "", DmMessageRow.replied_at >= iso_cutoff
        )
    ).scalar()
    return int(comments or 0) + int(dms or 0)
