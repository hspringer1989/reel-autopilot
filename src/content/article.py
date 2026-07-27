"""Fetches the source article behind a trend so the script agent has facts to work with.

Without this the agent sees only an RSS headline plus whatever `<description>` the feed
happens to carry — and some feeds carry nothing but the headline again. Asked to write
five segments from that, a model fills the gap with plausible-sounding invention.

Best effort by design: paywalls, timeouts, bot walls and odd markup all end in `None`,
and the caller falls back to the feed summary. A missing article must never stop a reel.
"""
from __future__ import annotations

import re

from loguru import logger

# Blocks that carry navigation/boilerplate rather than the article body.
_STRIP_TAGS = ("script", "style", "noscript", "nav", "header", "footer", "aside",
               "form", "figure", "iframe", "svg")
# Containers to try in order — the first one that holds real text wins.
_CONTENT_HINTS = ("article", "main", '[itemprop="articleBody"]', ".article-content",
                  ".entry-content", ".post-content")
_MIN_USEFUL_CHARS = 400
_USER_AGENT = "reel-autopilot/0.1 (+https://github.com/hspringer1989/reel-autopilot)"

# Einwilligungs- und Anmelde-Zwischenseiten. Sie liefern durchaus 1000+ Zeichen Text —
# der aber aus Cookie-Hinweisen besteht. Als "Faktengrundlage" waere das schlimmer als
# gar nichts: das Modell bekaeme Fuelltext, und der Abgleich liefe gegen einen Banner.
_INTERSTITIAL_HOSTS = ("consent.google.com", "consent.youtube.com", "accounts.google.com",
                       "consent.yahoo.com", "guce.yahoo.com")
_INTERSTITIAL_MARKERS = ("before you continue to google", "wenn du auf „alle akzeptieren",
                         "sign in to continue", "enable javascript and cookies")


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def looks_like_interstitial(text: str) -> bool:
    """True for consent/login walls. They yield plenty of text, so length alone does not
    protect us — and handing a cookie banner to the script agent as "the source" is worse
    than handing it nothing, because the fact-check would then compare against the banner."""
    lowered = text.lower()
    return any(marker in lowered for marker in _INTERSTITIAL_MARKERS)


def extract_text(html: str, max_chars: int = 6000) -> str | None:
    """Pull the readable body out of an HTML page. Returns None if nothing substantial."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:  # pragma: no cover — declared in requirements.txt
        logger.warning("beautifulsoup4 fehlt — Artikel-Extraktion übersprungen")
        return None

    soup = BeautifulSoup(html, "lxml")
    for tag in soup(list(_STRIP_TAGS)):
        tag.decompose()

    for selector in _CONTENT_HINTS:
        node = soup.select_one(selector)
        if node:
            text = _clean(node.get_text(" "))
            if len(text) >= _MIN_USEFUL_CHARS:
                return text[:max_chars]

    body = soup.body or soup
    text = _clean(body.get_text(" "))
    return text[:max_chars] if len(text) >= _MIN_USEFUL_CHARS else None


def fetch_article_text(url: str, max_chars: int = 6000) -> str | None:
    """Download `url` and return its readable body, or None on any failure.

    Google-News links are redirect blobs; following redirects lands on the publisher,
    which is both what we want to read and what a human needs to verify the claim.
    """
    if not url or not url.startswith(("http://", "https://")):
        return None
    try:
        import httpx

        response = httpx.get(url, timeout=15.0, follow_redirects=True,
                             headers={"User-Agent": _USER_AGENT})
        response.raise_for_status()
        if "html" not in response.headers.get("content-type", "").lower():
            return None
        if (response.url.host or "").lower() in _INTERSTITIAL_HOSTS:
            logger.info(f"Einwilligungs-Seite statt Artikel ({response.url.host}) — verworfen")
            return None
        text = extract_text(response.text, max_chars)
        if text and looks_like_interstitial(text):
            logger.info("Seite sieht nach Cookie-/Anmelde-Hinweis aus — verworfen")
            return None
    except Exception as exc:  # noqa: BLE001 — the article is optional, never fatal
        logger.info(f"Artikeltext nicht abrufbar ({url[:70]}): {type(exc).__name__}")
        return None

    if text:
        logger.info(f"Artikeltext geladen: {len(text)} Zeichen aus {url[:70]}")
    return text
