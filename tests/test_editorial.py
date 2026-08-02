"""Weekly editorial workflow: slot computation, topic proposal, batch scheduling,
and the Telegram approval loop (plan persists → ✅ builds → each post reviewed alone)."""
import asyncio
from datetime import date, datetime, timedelta

import pytest

from src.content.llm import builtin_fake
from src.feedposts import editorial
from src.storage.database import FeedPostRow, WeekPlanRow, session_scope


def test_next_week_slots_are_next_monday_onwards():
    slots = editorial.next_week_slots("17:00", 7)
    assert len(slots) == 7
    first = datetime.strptime(slots[0], "%Y-%m-%d %H:%M")
    assert first.weekday() == 0                     # starts on a Monday
    assert first.date() > datetime.now().date()     # strictly in the future
    assert all(s.endswith("17:00") for s in slots)
    days = [datetime.strptime(s, "%Y-%m-%d %H:%M").date() for s in slots]
    assert (days[-1] - days[0]).days == 6           # 7 consecutive days


def test_propose_week_topics():
    topics = editorial.propose_week_topics(builtin_fake(), 7)
    assert len(topics) == 7
    assert all(t["title"] and t["brief"] and t["slug"] for t in topics)


def test_schedule_week_creates_scheduled_review_posts(monkeypatch):
    pytest.importorskip("PIL")

    async def _noop(_pid):
        return None
    monkeypatch.setattr(editorial, "send_feed_for_review", _noop)

    topics = editorial.propose_week_topics(builtin_fake(), 3)
    ids = editorial.schedule_week(topics, builtin_fake())
    assert len(ids) == 3
    with session_scope() as session:
        for i in ids:
            row = session.get(FeedPostRow, i)
            assert row.status == "pending_review"
            assert row.scheduled_at                  # each got a slot


# ── Approval loop ──────────────────────────────────────────────────────────
def test_plan_slots_never_land_in_the_past():
    """A plan approved late must not make its posts publish immediately."""
    stale = str(date.today() - timedelta(days=10))
    slots = editorial.plan_slots(stale, 3, "17:00")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    assert all(s > now for s in slots)
    assert len(set(slots)) == 3                      # one distinct day each


def test_plan_slots_keep_a_future_week_start():
    start = date.today() + timedelta(days=14)
    slots = editorial.plan_slots(str(start), 2, "17:00")
    assert slots[0] == f"{start} 17:00"


def test_save_and_read_plan():
    topics = editorial.propose_week_topics(builtin_fake(), 2)
    plan_id = editorial.save_plan(topics)
    plan = editorial.get_plan(plan_id)
    assert plan["status"] == "pending_review"
    assert len(plan["topics"]) == 2

    editorial.set_plan_message(plan_id, 4711)
    assert editorial.plan_by_tg_message("4711")["id"] == plan_id
    # only pending plans are reachable by reply
    editorial.set_plan_status(plan_id, "built")
    assert editorial.plan_by_tg_message("4711") is None


def test_plan_message_lists_topics_with_dates():
    topics = editorial.propose_week_topics(builtin_fake(), 3)
    text = editorial.plan_message(topics, str(date.today() + timedelta(days=3)))
    assert "Redaktionssitzung" in text
    for t in topics:
        assert t["title"] in text
    assert text.count("(") >= 3                      # a date per topic


def test_parse_topics_text_reads_a_handwritten_list():
    topics = editorial.parse_topics_text(
        "1. Dividenden verstehen — Was eine Ausschüttung wirklich bedeutet\n"
        "2. ETF-Sparplan aufsetzen\n", 7)
    assert [t["title"] for t in topics] == ["Dividenden verstehen", "ETF-Sparplan aufsetzen"]
    assert topics[0]["brief"].startswith("Was eine Ausschüttung")
    assert editorial.parse_topics_text("nur eine Zeile") == []   # not a list


def test_revise_falls_back_to_the_current_plan(monkeypatch):
    """Budget exhausted + an instruction that is not a list → keep the plan intact."""
    monkeypatch.setattr(editorial, "claude_budget_exceeded", lambda: True)
    topics = editorial.propose_week_topics(builtin_fake(), 2)
    assert editorial.revise_week_topics(topics, "mach es spannender") == topics


def test_approved_plan_builds_posts_and_sends_them_individually(monkeypatch):
    pytest.importorskip("PIL")
    sent: list[int] = []

    async def _capture(pid):
        sent.append(pid)
    monkeypatch.setattr(editorial, "send_feed_for_review", _capture)
    monkeypatch.setattr(editorial, "get_llm", builtin_fake)

    topics = editorial.propose_week_topics(builtin_fake(), 2)
    plan_id = editorial.save_plan(topics)
    ids = asyncio.run(editorial.build_approved_plan(plan_id, builtin_fake()))

    assert len(ids) == 2
    assert sent == ids                               # every post reviewed on its own
    with session_scope() as session:
        assert session.get(WeekPlanRow, plan_id).status == "built"
        for i in ids:
            row = session.get(FeedPostRow, i)
            assert row.status == "pending_review" and row.scheduled_at
            assert row.brief                         # kept for later rebuilds
