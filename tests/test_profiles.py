"""Contract test for channel profiles: every channels/<name>/profile.py (except
_template) must expose the full attribute set the engine reads via config.PROFILE,
with the right shapes and prompt placeholders. This is what catches a channel
profile drifting from the contract when the engine gains a new profile key."""
import importlib
import re
from pathlib import Path

import pytest

_CHANNELS_DIR = Path(__file__).resolve().parents[1] / "channels"

_STR_KEYS = (
    "REEL_DISCLAIMER", "FEED_DISCLAIMER", "CARD_FOOTER_DISCLAIMER", "MILESTONE_FOOTER",
    "DISCLAIMER_CHECK", "WORDMARK", "MILESTONE_TAGLINE",
    "REEL_SYSTEM_PROMPT", "REEL_HASHTAG_HINT", "FEED_SYSTEM_PROMPT", "FEED_HASHTAG_HINT",
    "EDITORIAL_SYSTEM_PROMPT", "ADVICE_PATTERN", "SCORER_SYSTEM_PROMPT",
    "FEED_FOLLOW_CUE", "FEED_CAPTION_CTA",
    "COMMENT_SYSTEM", "DM_SYSTEM", "DIGEST_SYSTEM_PROMPT",
)
_PALETTE_KEYS = ("BLUE", "BLUE_LIGHT", "BLUE_DEEP", "BG", "CARD", "FG", "MUTED")


def _profiles():
    return sorted(
        p.parent.name
        for p in _CHANNELS_DIR.glob("*/profile.py")
        if not p.parent.name.startswith("_")
    )


@pytest.mark.parametrize("channel", _profiles())
def test_profile_contract(channel):
    prof = importlib.import_module(f"channels.{channel}.profile")

    for key in _STR_KEYS:
        value = getattr(prof, key)
        assert isinstance(value, str) and value.strip(), f"{channel}: {key} fehlt/leer"

    # palette: all keys present, RGB tuples
    for key in _PALETTE_KEYS:
        rgb = prof.PALETTE[key]
        assert len(rgb) == 3 and all(isinstance(v, int) and 0 <= v <= 255 for v in rgb), \
            f"{channel}: PALETTE[{key}] ist kein RGB-Tupel"

    # prompt placeholders the engine fills in
    assert "{brand}" in prof.REEL_SYSTEM_PROMPT and "{disclaimer}" in prof.REEL_SYSTEM_PROMPT, \
        f"{channel}: REEL_SYSTEM_PROMPT braucht {{brand}} und {{disclaimer}}"
    for key in ("COMMENT_SYSTEM", "DM_SYSTEM"):
        assert "{brand}" in getattr(prof, key) and "{handle}" in getattr(prof, key), \
            f"{channel}: {key} braucht {{brand}} und {{handle}}"
    assert "{brand}" in prof.DIGEST_SYSTEM_PROMPT, \
        f"{channel}: DIGEST_SYSTEM_PROMPT braucht {{brand}}"

    # the caption safety net only works if the check substring is in the disclaimers
    check = prof.DISCLAIMER_CHECK
    assert check == check.lower(), f"{channel}: DISCLAIMER_CHECK muss lowercase sein"
    assert check in prof.REEL_DISCLAIMER.lower(), \
        f"{channel}: DISCLAIMER_CHECK kommt nicht im REEL_DISCLAIMER vor"
    assert check in prof.FEED_DISCLAIMER.lower(), \
        f"{channel}: DISCLAIMER_CHECK kommt nicht im FEED_DISCLAIMER vor"

    # compliance regex must compile
    re.compile(prof.ADVICE_PATTERN, re.IGNORECASE)

    # wordmark for photo covers: exactly two banner words
    assert len(prof.PHOTO_WORDMARK) == 2 and all(w for w in prof.PHOTO_WORDMARK)

    # banned phrases + fallbacks
    assert all(isinstance(p, str) for p in prof.FEED_BANNED_PHRASES)
    assert "default" in prof.TEMPLATE_FALLBACKS and "spam" in prof.TEMPLATE_FALLBACKS
    for key, words in prof.FALLBACK_KEYWORDS:
        assert key in prof.TEMPLATE_FALLBACKS, \
            f"{channel}: FALLBACK_KEYWORDS verweist auf unbekanntes Template '{key}'"
        assert words, f"{channel}: leere Keyword-Liste für '{key}'"

    # feed topic seed: (slug, title, brief) triples with unique slugs
    slugs = [t[0] for t in prof.FEED_TOPIC_SEED]
    assert slugs and len(slugs) == len(set(slugs))
    assert all(len(t) == 3 and all(isinstance(x, str) and x for x in t)
               for t in prof.FEED_TOPIC_SEED)

    # Themenbeschaffung: ohne Quellen sammelt der Kanal nichts — und ohne diesen Test
    # fiele das erst im Betrieb auf (früher griffen stillschweigend Finanz-Defaults).
    sources = prof.SOURCES
    assert set(sources) >= {"rss", "reddit", "google_trends"}, \
        f"{channel}: SOURCES braucht die Schlüssel rss, reddit, google_trends"
    assert all(isinstance(u, str) and u.strip() for u in sources["rss"]), \
        f"{channel}: leerer Eintrag in SOURCES['rss']"
    assert all(isinstance(s, str) and s.strip() for s in sources["reddit"]), \
        f"{channel}: leerer Eintrag in SOURCES['reddit']"
    assert isinstance(sources["google_trends"], bool)
    assert sources["rss"] or sources["reddit"] or sources["google_trends"], \
        f"{channel}: keine einzige Themenquelle konfiguriert"

    # Gewichte der Bewertung: drei Anteile, Summe 1.0 (wie STOCK_W_TECH/STOCK_W_FUND)
    weights = prof.SCORER_WEIGHTS
    assert len(weights) == 3 and all(isinstance(w, (int, float)) and 0 <= w <= 1 for w in weights), \
        f"{channel}: SCORER_WEIGHTS braucht drei Anteile zwischen 0 und 1"
    assert abs(sum(weights) - 1.0) < 1e-9, \
        f"{channel}: SCORER_WEIGHTS summiert sich auf {sum(weights)}, erwartet 1.0"

    # Der Caption-CTA wird per .format(handle=…) gefüllt
    assert "{handle}" in prof.FEED_CAPTION_CTA, \
        f"{channel}: FEED_CAPTION_CTA braucht {{handle}}"

    # Die Fußnote der Abschluss-Slide DARF leer sein — eine Werbung-Kennzeichnung
    # gehört nur auf Beiträge, die auch Werbung enthalten. Deshalb steht sie nicht
    # in _STR_KEYS, muss aber ein String sein.
    assert isinstance(prof.FEED_SLIDE_DISCLAIMER, str)

    # module flags
    assert isinstance(prof.ENABLE_STOCKS, bool)
    assert isinstance(prof.ENABLE_DIVIDEND, bool)

    # profiles must stay import-cycle-free: no config/src imports
    source = (_CHANNELS_DIR / channel / "profile.py").read_text(encoding="utf-8")
    assert not re.search(r"^\s*(import config|from config|import src|from src)", source, re.M), \
        f"{channel}: Profil darf config/src nicht importieren"


def test_channel_assets_exist():
    """Every non-template channel needs the two feed templates the renderer loads."""
    for channel in _profiles():
        tpl = _CHANNELS_DIR / channel / "assets" / "templates"
        for name in ("feed_bg_title.png", "feed_bg_content.png"):
            assert (tpl / name).is_file(), f"{channel}: {tpl / name} fehlt"
