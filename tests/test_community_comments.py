import asyncio
import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

import config
from src.community import comments as C
from src.community.api import FakeCommunityAPI
from src.content.llm import BudgetExceeded, FakeLLM, LLMProvider
from src.storage.database import CommentRow, ReelRow, session_scope


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(config, "COMMUNITY_ENABLED", True)
    monkeypatch.setattr(config, "COMMUNITY_SHADOW_MODE", False)
    monkeypatch.setattr(config, "LLM_PROVIDER", "fake")
    monkeypatch.setattr(config, "IG_USER_ID", "SELF")
    monkeypatch.setattr(config, "COMMUNITY_MAX_REPLIES_PER_HOUR", 10)
    monkeypatch.setattr(config, "COMMUNITY_MIN_CONFIDENCE", 0.75)


def _seed_reel(media_id="m1", caption="Test Reel"):
    with session_scope() as session:
        session.add(ReelRow(
            trend_id=1, status="published", ig_media_id=media_id, caption=caption,
            published_at=datetime.now(timezone.utc).isoformat(),
        ))


def _comment(cid="c1", text="Super Beitrag!", from_id="999", username="user1"):
    return {"id": cid, "text": text, "username": username,
            "from": {"id": from_id}, "timestamp": "2026-07-25T10:00:00+0000"}


def _llm(cls="harmless", conf=0.9, reply="Danke dir 🙌 Was wünschst du dir?"):
    return FakeLLM({"community_comments": json.dumps(
        [{"i": 0, "class": cls, "confidence": conf, "reply": reply}]
    )})


def _status(cid="c1"):
    with session_scope() as session:
        return session.execute(
            select(CommentRow).where(CommentRow.ig_comment_id == cid)
        ).scalar_one().status


def _run(coro):
    return asyncio.run(coro)


def test_harmless_auto_replied(enabled):
    _seed_reel()
    api = FakeCommunityAPI(comments={"m1": [_comment()]})
    _run(C.poll_comments(api=api, llm=_llm("harmless", 0.9)))
    assert _status() == "auto_replied"
    assert api.replied and api.replied[0][0] == "c1"


def test_sensitive_escalated_not_posted(enabled):
    _seed_reel()
    api = FakeCommunityAPI(comments={"m1": [_comment(text="Soll ich NVDA kaufen?")]})
    _run(C.poll_comments(api=api, llm=_llm("sensitive", 0.9, "Da muss ich passen 🙏")))
    assert _status() == "pending_review"
    assert api.replied == []


def test_spam_skipped(enabled):
    _seed_reel()
    api = FakeCommunityAPI(comments={"m1": [_comment(text="Trading-Signale im DM!")]})
    _run(C.poll_comments(api=api, llm=_llm("spam", 0.9, "")))
    assert _status() == "skipped"
    assert api.replied == []


def test_low_confidence_escalated(enabled):
    _seed_reel()
    api = FakeCommunityAPI(comments={"m1": [_comment()]})
    _run(C.poll_comments(api=api, llm=_llm("harmless", 0.4)))
    assert _status() == "pending_review"
    assert api.replied == []


def test_compliance_filter_forces_escalation(enabled):
    _seed_reel()
    api = FakeCommunityAPI(comments={"m1": [_comment()]})
    # A "harmless" reply that reads like advice must never auto-send.
    _run(C.poll_comments(api=api, llm=_llm("harmless", 0.95, "Ja, du solltest kaufen!")))
    assert _status() == "pending_review"
    assert api.replied == []


def test_dedup_second_poll(enabled):
    _seed_reel()
    api = FakeCommunityAPI(comments={"m1": [_comment()]})
    _run(C.poll_comments(api=api, llm=_llm()))
    _run(C.poll_comments(api=api, llm=_llm()))
    assert len(api.replied) == 1  # only replied once


def test_own_comment_ignored(enabled):
    _seed_reel()
    api = FakeCommunityAPI(comments={"m1": [_comment(from_id="SELF")]})
    summary = _run(C.poll_comments(api=api, llm=_llm()))
    assert summary == {"new": 0}


def test_rate_limit_escalates(enabled, monkeypatch):
    monkeypatch.setattr(config, "COMMUNITY_MAX_REPLIES_PER_HOUR", 0)
    _seed_reel()
    api = FakeCommunityAPI(comments={"m1": [_comment()]})
    _run(C.poll_comments(api=api, llm=_llm()))
    assert _status() == "pending_review"
    assert api.replied == []


def test_shadow_mode_never_posts(enabled, monkeypatch):
    monkeypatch.setattr(config, "COMMUNITY_SHADOW_MODE", True)
    _seed_reel()
    api = FakeCommunityAPI(comments={"m1": [_comment()]})
    _run(C.poll_comments(api=api, llm=_llm()))
    assert _status() == "shadow"
    assert api.replied == []


class _BudgetLLM(LLMProvider):
    def complete(self, system, user, model, max_tokens, purpose):
        raise BudgetExceeded("test")


def test_budget_exceeded_escalates(enabled):
    _seed_reel()
    api = FakeCommunityAPI(comments={"m1": [_comment()]})
    _run(C.poll_comments(api=api, llm=_BudgetLLM()))
    assert _status() == "pending_review"
    # A template suggestion is stored as the draft awaiting approval.
    with session_scope() as session:
        row = session.execute(
            select(CommentRow).where(CommentRow.ig_comment_id == "c1")
        ).scalar_one()
        assert row.reply_text  # non-empty template suggestion
    assert api.replied == []


def test_disabled_is_noop(monkeypatch):
    monkeypatch.setattr(config, "COMMUNITY_ENABLED", False)
    _seed_reel()
    api = FakeCommunityAPI(comments={"m1": [_comment()]})
    assert _run(C.poll_comments(api=api, llm=_llm())) == {}
