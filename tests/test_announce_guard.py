"""Tests fuer die Ankuendigungs-Sperren (Vorfall 20.08.2026).

Am 20.08.2026 erschienen drei Stories, die einen neuen Beitrag ankuendigten, obwohl
keiner veroeffentlicht wurde. Diese Tests halten fest, dass jede der drei Sperren
allein ausreicht, um das zu verhindern — und dass der Normalfall weiterhin durchgeht.
"""
from __future__ import annotations

import pytest

from src.pipeline import announce_new_reel
from src.storage.database import ReelRow, StoryRow, session_scope


@pytest.fixture
def posted(monkeypatch):
    """Faengt jeden Story-Upload ab und protokolliert ihn."""
    calls: list[str] = []

    async def _publish_story(path):
        calls.append(str(path))
        return "media-neu"

    async def _exists(media_id):
        return media_id == "live-123"

    monkeypatch.setattr("src.publish.instagram.publish_story", _publish_story)
    monkeypatch.setattr("src.publish.instagram.publishing_configured", lambda: True)
    monkeypatch.setattr("src.publish.instagram.media_exists", _exists)
    monkeypatch.setattr("src.stocks.story_cards.render_new_post_story",
                        lambda *a, **k: a[1] if len(a) > 1 else "x.jpg")
    return calls


def _reel(status: str, media: str) -> int:
    with session_scope() as s:
        r = ReelRow(trend_id=0, script_json='{"title": "Test"}', caption="c",
                    status=status, ig_media_id=media or None)
        s.add(r); s.flush()
        return r.id


@pytest.mark.asyncio
async def test_kein_post_ohne_veroeffentlichung(posted):
    """Sperre 1: Ein Reel im Entwurf darf nie angekuendigt werden.
    Das ist der Kern des Vorfalls."""
    rid = _reel("pending_review", "")
    assert await announce_new_reel(rid) is None
    assert posted == [], posted


@pytest.mark.asyncio
async def test_kein_post_ohne_medien_id(posted):
    """Sperre 1b: 'published' ohne Medien-ID ist kein Beleg — die Zeile kann von
    einem abgebrochenen Lauf stammen."""
    rid = _reel("published", "")
    assert await announce_new_reel(rid) is None
    assert posted == [], posted


@pytest.mark.asyncio
async def test_kein_post_wenn_instagram_die_id_nicht_kennt(posted):
    """Sperre 2: Die Datenbank sagt 'published', Instagram kennt die ID nicht —
    zum Beispiel, weil der Beitrag geloescht wurde."""
    rid = _reel("published", "geloescht-999")
    assert await announce_new_reel(rid) is None
    assert posted == [], posted


@pytest.mark.asyncio
async def test_keine_zweite_ankuendigung(posted):
    """Sperre 3: Ein zweites Mal aufgerufen (doppelter Slot nach Neustart) darf
    derselbe Beitrag nicht erneut angekuendigt werden."""
    rid = _reel("published", "live-123")
    with session_scope() as s:
        s.add(StoryRow(kind="announce", trade_date="2026-08-20",
                       image_path=f"/x/announce_reel_{rid}_20260820.jpg",
                       caption="schon da", status="published",
                       ig_media_id="alt-1", published_at="2026-08-20T09:00:00+00:00"))
    assert await announce_new_reel(rid) is None
    assert posted == [], posted


@pytest.mark.asyncio
async def test_echte_veroeffentlichung_wird_angekuendigt(posted):
    """Gegenprobe: Der Normalfall muss weiterhin durchgehen, sonst haette die
    Absicherung die Funktion nur kaputtgemacht."""
    rid = _reel("published", "live-123")
    assert await announce_new_reel(rid) is not None
    assert len(posted) == 1, posted
