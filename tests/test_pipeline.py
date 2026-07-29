"""End-to-end pipeline test with fakes only: no network, no ffmpeg."""
from pathlib import Path

import pytest
from sqlalchemy import select

import src.pipeline as pipeline
from src.collectors.base import Collector
from src.content.llm import builtin_fake
from src.models import TrendItem
from src.storage.database import ReelRow, TrendRow, session_scope


class StubCollector(Collector):
    name = "stub"

    def collect(self):
        return [
            TrendItem(source="stub", title="EZB senkt Leitzins überraschend"),
            TrendItem(source="stub", title="Neue Depot-Gebühren bei Neobrokern"),
        ]


class BrokenCollector(Collector):
    name = "broken"

    def collect(self):
        raise ConnectionError("Quelle nicht erreichbar")


def _fake_render(script, tts, broll_paths, out_path, music_path=None):
    Path(out_path).write_bytes(b"fake mp4")
    return Path(out_path)


@pytest.fixture(autouse=True)
def fakes(monkeypatch):
    monkeypatch.setattr(pipeline, "active_collectors", lambda: [StubCollector(), BrokenCollector()])
    monkeypatch.setattr(pipeline, "get_llm", builtin_fake)
    monkeypatch.setattr(pipeline, "render_reel", _fake_render)
    monkeypatch.setattr(pipeline.PexelsBroll, "fetch", lambda self, q, m: None)


def test_collect_and_score_dedups_and_survives_broken_source():
    assert pipeline.collect_and_score(builtin_fake()) == 2
    # second run: everything already known
    assert pipeline.collect_and_score(builtin_fake()) == 0
    with session_scope() as session:
        rows = session.execute(select(TrendRow)).scalars().all()
    assert len(rows) == 2
    assert all(r.status == "scored" and r.score_total > 0 for r in rows)


async def test_generate_once_end_to_end():
    reel_id = await pipeline.generate_once()
    assert reel_id is not None

    with session_scope() as session:
        reel = session.get(ReelRow, reel_id)
        trend = session.get(TrendRow, reel.trend_id)

    assert reel.status == "pending_review"
    assert Path(reel.video_path).exists()
    assert "Anlageberatung" in reel.caption
    assert "#finanzen" in reel.caption
    assert trend.status == "used"
    # the highest-scored trend was picked (builtin_fake scores index 0 highest)
    assert trend.title == "EZB senkt Leitzins überraschend"


async def test_regenerate_produces_new_reel_for_same_trend():
    reel_id = await pipeline.generate_once()
    with session_scope() as session:
        session.get(ReelRow, reel_id).status = "regenerate"

    new_ids = pipeline.handle_regenerates()
    assert len(new_ids) == 1
    with session_scope() as session:
        old = session.get(ReelRow, reel_id)
        new = session.get(ReelRow, new_ids[0])
    assert old.status == "rejected"
    assert new.status == "pending_review"
    assert new.trend_id == old.trend_id


async def test_no_trend_above_threshold(monkeypatch):
    import config

    monkeypatch.setattr(config, "MIN_TREND_SCORE", 0.99)
    assert await pipeline.generate_once() is None


async def test_publish_failure_keeps_reel_in_queue(monkeypatch):
    """Ein transienter Instagram-Fehler darf ein freigegebenes Reel nicht endgültig
    verwerfen: bis zur Obergrenze bleibt es 'approved' (Retry am nächsten Slot),
    erst danach 'failed'. Vorher wurde aus jedem Schluckauf ein stiller Totalausfall."""
    from src.publish import instagram

    with session_scope() as session:
        session.add(ReelRow(trend_id=0, video_path="x.mp4", caption="c", status="approved"))
        session.flush()
        reel_id = session.execute(select(ReelRow.id)).scalar_one()

    async def boom(video_path, caption):
        raise instagram.PublishError("Instagram meldet Verarbeitungsfehler (status ERROR)")
    monkeypatch.setattr(instagram, "publish_reel", boom)

    for attempt in (1, 2):
        assert await pipeline.publish_next_approved() is None
        with session_scope() as session:
            row = session.get(ReelRow, reel_id)
            assert row.status == "approved", f"nach Versuch {attempt} nicht mehr in der Queue"
            assert row.publish_attempts == attempt
            assert "Verarbeitungsfehler" in row.error

    assert await pipeline.publish_next_approved() is None
    with session_scope() as session:
        row = session.get(ReelRow, reel_id)
        assert row.status == "failed"
        assert row.publish_attempts == 3


async def test_publish_success_after_failure(monkeypatch):
    """Der Normalfall des Retrys: erster Versuch scheitert, zweiter geht durch."""
    from src.publish import instagram

    with session_scope() as session:
        session.add(ReelRow(trend_id=0, video_path="x.mp4", caption="c", status="approved"))
        session.flush()
        reel_id = session.execute(select(ReelRow.id)).scalar_one()

    calls = {"n": 0}

    async def flaky(video_path, caption):
        calls["n"] += 1
        if calls["n"] == 1:
            raise instagram.PublishError("transient")
        return "IG_MEDIA_1"
    monkeypatch.setattr(instagram, "publish_reel", flaky)
    monkeypatch.setattr(pipeline, "announce_new_reel", _noop_announce)

    assert await pipeline.publish_next_approved() is None
    assert await pipeline.publish_next_approved() == reel_id
    with session_scope() as session:
        row = session.get(ReelRow, reel_id)
        assert row.status == "published"
        assert row.ig_media_id == "IG_MEDIA_1"


async def _noop_announce(reel_id):
    return None
