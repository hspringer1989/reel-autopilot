import asyncio

import pytest
from sqlalchemy import select

import config
from src.community import digest as G
from src.community.api import FakeCommunityAPI
from src.content.llm import builtin_fake
from src.storage.database import DigestItemRow, session_scope


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(config, "COMMUNITY_ENABLED", True)
    monkeypatch.setattr(config, "COMMUNITY_DIGEST_ENABLED", True)
    monkeypatch.setattr(config, "LLM_PROVIDER", "fake")
    monkeypatch.setattr(config, "COMMUNITY_DIGEST_HASHTAGS", ["finanzen"])
    monkeypatch.setattr(config, "COMMUNITY_DIGEST_HASHTAGS_PER_DAY", 1)
    monkeypatch.setattr(config, "COMMUNITY_DIGEST_PROFILES", [])


def _run(coro):
    return asyncio.run(coro)


def _count_items():
    with session_scope() as session:
        return len(session.execute(select(DigestItemRow)).scalars().all())


def test_todays_hashtags_respects_per_day(monkeypatch):
    monkeypatch.setattr(config, "COMMUNITY_DIGEST_HASHTAGS",
                        ["a", "b", "c", "d", "e"])
    monkeypatch.setattr(config, "COMMUNITY_DIGEST_HASHTAGS_PER_DAY", 2)
    tags = G._todays_hashtags()
    assert len(tags) == 2
    assert len(set(tags)) == 2  # unique


def test_hashtag_source_used_when_available(enabled):
    api = FakeCommunityAPI(
        hashtag_available=True,
        hashtag_media={"hid_finanzen": [
            {"id": "p1", "permalink": "https://insta/p1", "caption": "ETF-Sparplan Tipp"},
        ]},
    )
    n = _run(G.build_digest(api=api, llm=builtin_fake()))
    assert n == 1
    with session_scope() as session:
        row = session.execute(select(DigestItemRow)).scalar_one()
        assert row.source == "hashtag"
        assert row.suggested_comment  # a suggestion was drafted


def test_fallback_to_profiles_when_hashtag_unavailable(enabled, monkeypatch):
    monkeypatch.setattr(config, "COMMUNITY_DIGEST_PROFILES", ["finanzfluss", "aktienlust"])
    api = FakeCommunityAPI(hashtag_available=False)
    n = _run(G.build_digest(api=api, llm=builtin_fake()))
    assert n >= 2
    with session_scope() as session:
        sources = {r.source for r in session.execute(select(DigestItemRow)).scalars().all()}
    assert "profile" in sources


def test_dedup_second_run(enabled):
    api = FakeCommunityAPI(
        hashtag_available=True,
        hashtag_media={"hid_finanzen": [
            {"id": "p1", "permalink": "https://insta/p1", "caption": "Tipp"},
        ]},
    )
    _run(G.build_digest(api=api, llm=builtin_fake()))
    n2 = _run(G.build_digest(api=api, llm=builtin_fake()))
    assert n2 == 0
    assert _count_items() == 1


def test_disabled_is_noop(monkeypatch):
    monkeypatch.setattr(config, "COMMUNITY_ENABLED", False)
    api = FakeCommunityAPI(hashtag_available=True)
    assert _run(G.build_digest(api=api, llm=builtin_fake())) == 0
