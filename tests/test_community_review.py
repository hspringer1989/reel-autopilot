import asyncio

import pytest
from sqlalchemy import select

import config
from src.community import comments as C
from src.community import dms as D
from src.storage.database import (
    CommentRow,
    DmMessageRow,
    DmThreadRow,
    session_scope,
)


@pytest.fixture(autouse=True)
def fake_api(monkeypatch):
    # get_api() returns the offline FakeCommunityAPI when the LLM stack is faked.
    monkeypatch.setattr(config, "LLM_PROVIDER", "fake")


def _run(coro):
    return asyncio.run(coro)


def _seed_comment(status="pending_review", draft="Danke 🙌", tg="555"):
    with session_scope() as session:
        row = CommentRow(
            ig_comment_id="c1", ig_media_id="m1", status=status,
            reply_text=draft, tg_message_id=tg, text="Frage?",
        )
        session.add(row)
        session.flush()
        return row.id


def _comment_status(cid):
    with session_scope() as session:
        return session.get(CommentRow, cid).status


# ── comment decisions ──────────────────────────────────────────────────────
def test_comment_approve_posts_and_marks_replied():
    cid = _seed_comment()
    ack = _run(C.resolve_review(cid, "approve"))
    assert "gepostet" in ack
    assert _comment_status(cid) == "replied"


def test_comment_double_decision_refused():
    cid = _seed_comment()
    _run(C.resolve_review(cid, "approve"))
    ack = _run(C.resolve_review(cid, "skip"))
    assert "bereits" in ack
    assert _comment_status(cid) == "replied"


def test_comment_skip_and_hide():
    a = _seed_comment()
    _run(C.resolve_review(a, "skip"))
    assert _comment_status(a) == "skipped"
    b_id = None
    with session_scope() as session:
        row = CommentRow(ig_comment_id="c2", status="pending_review", reply_text="x")
        session.add(row)
        session.flush()
        b_id = row.id
    ack = _run(C.resolve_review(b_id, "hide"))
    assert "Verborgen" in ack
    assert _comment_status(b_id) == "skipped"


def test_comment_approve_without_draft():
    cid = _seed_comment(draft="")
    ack = _run(C.resolve_review(cid, "approve"))
    assert "Kein Antworttext" in ack
    assert _comment_status(cid) == "pending_review"


def test_comment_missing_returns_none():
    assert _run(C.resolve_review(99999, "approve")) is None


# ── edit flow (reply-to-message) ───────────────────────────────────────────
def test_comment_edit_flow_posts_custom_text():
    cid = _seed_comment(tg="777")
    ack = _run(C.resolve_edit("777", "Meine eigene Antwort"))
    assert ack and "gepostet" in ack
    with session_scope() as session:
        row = session.get(CommentRow, cid)
        assert row.status == "replied"
        assert row.reply_text == "Meine eigene Antwort"


def test_comment_edit_unknown_tg_id_returns_none():
    _seed_comment(tg="777")
    assert _run(C.resolve_edit("does-not-exist", "text")) is None


# ── DM decisions ───────────────────────────────────────────────────────────
def _seed_dm(status="escalated", draft="Melde mich!", tg="888"):
    with session_scope() as session:
        thread = DmThreadRow(ig_thread_id="t1", participant_id="123", status="escalated")
        session.add(thread)
        session.flush()
        row = DmMessageRow(
            ig_message_id="m1", thread_id=thread.id, direction="in",
            status=status, reply_text=draft, tg_message_id=tg, text="Hallo",
        )
        session.add(row)
        session.flush()
        return row.id


def test_dm_approve_sends():
    did = _seed_dm()
    ack = _run(D.resolve_review(did, "approve"))
    assert "gesendet" in ack
    with session_scope() as session:
        assert session.get(DmMessageRow, did).status == "auto_replied"


def test_dm_edit_flow():
    did = _seed_dm(tg="999")
    ack = _run(D.resolve_edit("999", "Custom DM"))
    assert ack and "gesendet" in ack
    with session_scope() as session:
        row = session.get(DmMessageRow, did)
        assert row.status == "auto_replied"
        assert row.reply_text == "Custom DM"


def test_dm_edit_unknown_returns_none():
    _seed_dm(tg="999")
    assert _run(D.resolve_edit("nope", "x")) is None
