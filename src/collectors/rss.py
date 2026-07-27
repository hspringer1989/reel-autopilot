"""Headlines from German finance/business news feeds."""
import re

import config
from src.collectors.base import Collector
from src.models import TrendItem

_ENTRIES_PER_FEED = 15
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    return _TAG_RE.sub("", text or "").strip()


class RSSCollector(Collector):
    name = "rss"

    def __init__(self, feeds: list[str] | None = None):
        self.feeds = feeds if feeds is not None else config.RSS_FEEDS

    def collect(self) -> list[TrendItem]:
        import feedparser

        items: list[TrendItem] = []
        for feed_url in self.feeds:
            parsed = feedparser.parse(feed_url)
            for entry in parsed.entries[:_ENTRIES_PER_FEED]:
                title = _strip_html(entry.get("title", ""))
                if not title:
                    continue
                items.append(
                    TrendItem(
                        source=self.name,
                        title=title,
                        summary=_strip_html(entry.get("summary", ""))[:500],
                        url=entry.get("link", ""),
                        # news has no upvotes; freshness ordering acts as the hint
                        popularity=0.5,
                    )
                )
        return items


def active_collectors() -> list[Collector]:
    """All collectors whose credentials/config are present (trading-bot pattern:
    collectors only start if usable). Which sources a channel uses comes from its
    profile (PROFILE.SOURCES) — a collector without sources never starts, so a niche
    channel doesn't pay scoring tokens for topics it would discard anyway."""
    from src.collectors.google_trends import GoogleTrendsCollector
    from src.collectors.reddit import RedditCollector

    collectors: list[Collector] = []
    if config.GOOGLE_TRENDS_ENABLED:
        collectors.append(GoogleTrendsCollector())
    if config.RSS_FEEDS:
        collectors.append(RSSCollector())
    if config.REDDIT_CLIENT_ID and config.REDDIT_CLIENT_SECRET and config.REDDIT_SUBREDDITS:
        collectors.append(RedditCollector())
    return collectors
