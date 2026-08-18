"""Static 'Link in Bio' archive: the generator must stay channel-neutral (everything
brand/legal comes from the profile) and must not leak unpublished analyses."""
import json

import config
from src.site import generator
from src.storage.database import StoryRow, session_scope

_P = config.PROFILE


def _make_story(**kw) -> int:
    defaults = dict(
        kind="candidate", status="published", trade_date=_P.SITE_MIN_DATE,
        ticker="TST", image_path="", analysis_json=json.dumps({
            "metrics": {"name": "Testfirma", "ticker": "TST", "sector": "Tech",
                        "tech_score": 0.7, "fund_score": 0.5},
            "overall_text": "Ausgewogenes Bild.",
        }),
    )
    defaults.update(kw)
    with session_scope() as session:
        row = StoryRow(**defaults)
        session.add(row)
        session.flush()
        return row.id


def test_index_uses_profile_brand_and_palette():
    html = generator._render_index([])
    assert _P.SITE_BRAND in html
    assert _P.SITE_IG_URL in html
    assert _P.SITE_HEADLINE in html
    r, g, b = _P.PALETTE["BLUE"]
    assert f"#{r:02x}{g:02x}{b:02x}" in html      # brand accent, not a hardcoded blue


def test_impressum_comes_from_the_profile():
    html = generator._render_impressum()
    assert _P.SITE_IMPRESSUM_NAME in html
    assert _P.SITE_IMPRESSUM_EMAIL in html
    for line in _P.SITE_IMPRESSUM_ADDRESS:
        assert line in html


def test_impressum_optional_business_fields_render_when_set():
    """Owner/phone/VAT/MStV-responsible are optional keys — if the profile sets them,
    they must land in the imprint; without them the page must still render."""
    html = generator._render_impressum()
    for key in ("SITE_IMPRESSUM_OWNER", "SITE_IMPRESSUM_PHONE", "SITE_IMPRESSUM_VAT",
                "SITE_IMPRESSUM_RESPONSIBLE"):
        value = getattr(_P, key, "")
        if value:
            assert value in html, f"{key} fehlt im gerenderten Impressum"


def test_footer_legal_links_prefer_profile_urls():
    """External privacy/terms URLs (SITE_PRIVACY_URL/SITE_TERMS_URL) replace the
    local /datenschutz and /nutzungsbedingungen links in the footer."""
    html = generator._render_index([])
    privacy = getattr(_P, "SITE_PRIVACY_URL", "") or "/datenschutz"
    terms = getattr(_P, "SITE_TERMS_URL", "") or "/nutzungsbedingungen"
    assert f'href="{privacy}"' in html
    assert f'href="{terms}"' in html


def test_collect_only_takes_published_cards_from_the_cutoff_on():
    published = _make_story()
    _make_story(status="pending_review")                      # not public yet
    _make_story(trade_date="2000-01-01")                      # before the cutoff
    _make_story(kind="announce")                              # not an analysis

    ids = {it["id"] for it in generator._collect()}
    assert published in ids
    assert len(ids) == 1


def test_card_html_escapes_and_marks_trend():
    card = generator._card_html({
        "id": 1, "date": "2026-08-01", "image_path": "", "ticker": "T&T",
        "name": "<script>", "sector": "Tech", "tech": 0.7, "fund": 0.2,
        "overall": "Fazit", "chart": "", "fundamental": "", "currency": "EUR",
        "entry": None, "stop": None, "take": None, "is_trend": True,
    })
    assert "<script>" not in card and "&lt;script&gt;" in card   # escaped, not injected
    assert "T&amp;T" in card
    assert "TREND" in card
