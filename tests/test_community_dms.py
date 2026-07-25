import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

import config
from src.community import dms as D
from src.community import guard
from src.community.api import FakeCommunityAPI
from src.content.llm import FakeLLM
from src.storage.database import DmMessageRow, DmThreadRow, session_scope


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(config, "COMMUNITY_ENABLED", True)
    monkeypatch.setattr(config, "COMMUNITY_DM_ENABLED", True)
    monkeypatch.setattr(config, "COMMUNITY_SHADOW_MODE", False)
    monkeypatch.setattr(config, "LLM_PROVIDER", "fake")
    monkeypatch.setattr(config, "IG_USER_ID", "SELF")
    monkeypatch.setattr(config, "COMMUNITY_MAX_REPLIES_PER_HOUR", 10)
    monkeypatch.setattr(config, "COMMUNITY_MIN_CONFIDENCE", 0.75)
    monkeypatch.setattr(config, "COMMUNITY_DM_WINDOW_HOURS", 24)


def _iso(hours_ago=0):
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()


def _thread(msgs, tid="t1", participant="u1", pid="123"):
    return {"id": tid, "participant_id": pid, "participant_username": participant,
            "updated_time": _iso(), "messages": msgs}


def _msg(mid, text, from_id="123", created=None, attachment=""):
    return {"id": mid, "from_id": from_id, "text": text,
            "created_time": created or _iso(0), "attachment_type": attachment}


def _llm(cls="harmless", conf=0.9, reply="Danke für deine Nachricht 🙌"):
    return FakeLLM({"community_dm": json.dumps(
        {"class": cls, "confidence": conf, "reply": reply}
    )})


def _run(coro):
    return asyncio.run(coro)


def _dm_status(mid):
    with session_scope() as session:
        return session.execute(
            select(DmMessageRow).where(DmMessageRow.ig_message_id == mid)
        ).scalar_one().status


def test_window_open_auto_replies(enabled):
    api = FakeCommunityAPI(threads=[_thread([_msg("m1", "Hallo!", created=_iso(0))])])
    _run(D.poll_dms(api=api, llm=_llm()))
    assert _dm_status("m1") == "auto_replied"
    assert api.sent_dms and api.sent_dms[0][0] == "123"


def test_window_closed_escalates(enabled):
    api = FakeCommunityAPI(threads=[_thread([_msg("m1", "Hallo!", created=_iso(48))])])
    _run(D.poll_dms(api=api, llm=_llm()))
    assert _dm_status("m1") == "escalated"
    assert api.sent_dms == []


def test_spam_skipped(enabled):
    api = FakeCommunityAPI(threads=[_thread([_msg("m1", "Kauf meine Signale")])])
    _run(D.poll_dms(api=api, llm=_llm("spam", 0.9, "")))
    assert _dm_status("m1") == "skipped"


def test_sensitive_escalated(enabled):
    api = FakeCommunityAPI(threads=[_thread([_msg("m1", "Kooperationsanfrage")])])
    _run(D.poll_dms(api=api, llm=_llm("sensitive", 0.9, "Melde mich!")))
    assert _dm_status("m1") == "escalated"
    assert api.sent_dms == []


def test_own_message_logged_not_replied(enabled):
    api = FakeCommunityAPI(threads=[_thread([_msg("m1", "unsere Antwort", from_id="SELF")])])
    summary = _run(D.poll_dms(api=api, llm=_llm()))
    assert summary == {"new": 0}
    assert _dm_status("m1") == "skipped"  # outbound message logged as skipped


def test_story_reply_attachment_stored(enabled):
    api = FakeCommunityAPI(threads=[
        _thread([_msg("m1", "🔥", attachment="story_reply", created=_iso(0))])
    ])
    _run(D.poll_dms(api=api, llm=_llm()))
    with session_scope() as session:
        row = session.execute(
            select(DmMessageRow).where(DmMessageRow.ig_message_id == "m1")
        ).scalar_one()
        assert row.attachment_type == "story_reply"


def test_dedup_second_poll(enabled):
    api = FakeCommunityAPI(threads=[_thread([_msg("m1", "Hallo", created=_iso(0))])])
    _run(D.poll_dms(api=api, llm=_llm()))
    _run(D.poll_dms(api=api, llm=_llm()))
    assert len(api.sent_dms) == 1


def test_thread_context_orders_prior_messages(enabled):
    api = FakeCommunityAPI(threads=[_thread([
        _msg("m1", "erste Frage", created=_iso(1)),
        _msg("m2", "zweite Frage", created=_iso(0)),
    ])])
    _run(D.poll_dms(api=api, llm=_llm()))
    with session_scope() as session:
        thread = session.execute(select(DmThreadRow)).scalar_one()
        m2 = session.execute(
            select(DmMessageRow).where(DmMessageRow.ig_message_id == "m2")
        ).scalar_one()
    context = D._thread_context(thread.id, m2.id)
    assert any("erste Frage" in c for c in context)


def test_within_dm_window_helper(enabled):
    assert guard.within_dm_window(_iso(1)) is True
    assert guard.within_dm_window(_iso(30)) is False
    assert guard.within_dm_window("") is False
