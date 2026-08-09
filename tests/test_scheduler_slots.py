"""Slot matching in the scheduler loop.

Regression cover for 09.08.2026: the loop compared the current minute to the slot with
`==`. Because the tick sleeps AFTER doing its work, the wake-up moment drifts forward and
a minute can be skipped entirely — the approved reel was silently never published and,
since the block was never entered, nothing was logged either.
"""
from datetime import datetime, timedelta, timezone

import main


def test_slot_matches_at_its_exact_minute():
    assert main._slot_due("09:00", "09:00")


def test_slot_still_due_shortly_after_a_skipped_tick():
    # the incident: tick at 08:59, next tick at 09:01 -> "09:00" never seen
    assert main._slot_due("09:01", "09:00")
    assert main._slot_due("09:14", "09:00")


def test_slot_not_due_before_its_time():
    assert not main._slot_due("08:59", "09:00")
    assert not main._slot_due("00:00", "09:00")


def test_slot_expires_after_the_grace_window():
    """A slot must not fire hours late — a 09:00 reel at 18:00 would be worse than none."""
    assert not main._slot_due("09:16", "09:00")
    assert not main._slot_due("18:00", "09:00")


def test_grace_window_is_shorter_than_the_gap_between_story_slots():
    """Guards against a grace so wide that one slot bleeds into the next one."""
    assert main._SLOT_GRACE_MIN < 90


def test_reel_guard_detects_a_post_from_the_same_local_day(monkeypatch):
    """Restart inside the catch-up window must not publish tomorrow's reel a day early."""
    posted = datetime.now(timezone.utc)
    day = posted.astimezone(main.ZoneInfo(main.config.TIMEZONE)).strftime("%Y-%m-%d")
    monkeypatch.setattr(main, "session_scope", _fake_scope([posted.isoformat()]))
    assert main._reel_already_posted_today(day)


def test_reel_guard_ignores_yesterdays_post(monkeypatch):
    posted = datetime.now(timezone.utc) - timedelta(days=1)
    day = datetime.now(timezone.utc).astimezone(
        main.ZoneInfo(main.config.TIMEZONE)).strftime("%Y-%m-%d")
    monkeypatch.setattr(main, "session_scope", _fake_scope([posted.isoformat()]))
    assert not main._reel_already_posted_today(day)


def test_reel_guard_survives_a_broken_timestamp(monkeypatch):
    """A malformed published_at must not crash the scheduler tick."""
    monkeypatch.setattr(main, "session_scope", _fake_scope(["not-a-date", None]))
    assert not main._reel_already_posted_today("2026-08-09")


def _fake_scope(stamps):
    """Minimal stand-in for session_scope() yielding the given published_at values."""
    class _Result:
        def scalars(self):
            return self

        def all(self):
            return stamps

    class _Session:
        def execute(self, *_args, **_kwargs):
            return _Result()

    class _Scope:
        def __enter__(self):
            return _Session()

        def __exit__(self, *_exc):
            return False

    return lambda: _Scope()
