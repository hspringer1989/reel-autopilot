"""Regressionstest fuer den Vorfall 18.-20.08.2026 (LYFT an drei Tagen in Folge).

Der Kern: wenn ALLE Ticker im Cooldown stehen, darf der Notbetrieb nicht nach Score
auswaehlen — sonst gewinnt jeden Tag derselbe Ticker, weil sich der Score kaum bewegt.
Er muss den Ticker nehmen, der am laengsten nicht zu sehen war.
"""
from __future__ import annotations

import pytest

from src.stocks.analyzer import select_candidates


class _FakeMD:
    """Minimaler MarketData-Ersatz — analyze_ticker wird ohnehin gemonkeypatcht."""


class _M:
    def __init__(self, ticker: str, blended: float, sector: str):
        self.ticker = ticker
        self.blended = blended
        self.sector = sector

    def __repr__(self) -> str:            # nur fuer lesbare Fehlermeldungen
        return f"<{self.ticker} {self.blended}>"


# LYFT hat den hoechsten Score — genau die Konstellation, die den Vorfall ausgeloest hat.
_UNIVERSE = {
    "LYFT": _M("LYFT", 0.91, "Transport"),
    "ADBE": _M("ADBE", 0.88, "Tech"),
    "JPM": _M("JPM", 0.84, "Banken"),
    "KO": _M("KO", 0.60, "Konsum"),
}


@pytest.fixture(autouse=True)
def _patch_analyze(monkeypatch):
    monkeypatch.setattr("src.stocks.analyzer.analyze_ticker",
                        lambda md, t: _UNIVERSE.get(t.upper()))


def _pick(count, exclude, last_seen):
    return [m.ticker for m in select_candidates(
        _FakeMD(), list(_UNIVERSE), count, exclude=exclude, last_seen=last_seen)]


def test_frische_ticker_gehen_vor():
    """Solange es freie Ticker gibt, bleibt der Cooldown unangetastet."""
    picked = _pick(2, exclude={"LYFT", "ADBE"}, last_seen={"LYFT": "2026-08-19"})
    assert "LYFT" not in picked
    assert "ADBE" not in picked


def test_notbetrieb_nimmt_den_aeltesten_nicht_den_besten():
    """Alles im Cooldown: KO war am laengsten weg und muss vor LYFT kommen,
    obwohl LYFT den hoechsten Score hat."""
    everything = set(_UNIVERSE)
    last_seen = {"LYFT": "2026-08-19", "ADBE": "2026-08-18",
                 "JPM": "2026-08-10", "KO": "2026-07-02"}
    picked = _pick(1, exclude=everything, last_seen=last_seen)
    assert picked == ["KO"], picked


def test_kein_ticker_an_zwei_tagen_hintereinander():
    """Der eigentliche Vorwurf: dreimal LYFT. Mit LRU rotiert die Auswahl."""
    everything = set(_UNIVERSE)
    last_seen = {"LYFT": "2026-08-17", "ADBE": "2026-08-16",
                 "JPM": "2026-08-15", "KO": "2026-08-14"}
    tag1 = _pick(2, exclude=everything, last_seen=last_seen)
    for t in tag1:
        last_seen[t] = "2026-08-18"          # heute gezeigt
    tag2 = _pick(2, exclude=everything, last_seen=last_seen)
    assert not set(tag1) & set(tag2), f"Wiederholung: {tag1} / {tag2}"


def test_nie_gezeigter_ticker_kommt_zuerst():
    """Ein Ticker ohne Historie gilt als 'am laengsten weg'."""
    everything = set(_UNIVERSE)
    picked = _pick(1, exclude=everything,
                   last_seen={"LYFT": "2026-08-19", "ADBE": "2026-08-18",
                              "JPM": "2026-08-17"})   # KO fehlt = nie gezeigt
    assert picked == ["KO"], picked


def test_notbetrieb_wird_protokolliert():
    """Der Notbetrieb darf nicht mehr lautlos sein — genau das hat den Vorfall
    wochenlang verdeckt."""
    from loguru import logger

    seen: list[str] = []
    sink_id = logger.add(lambda m: seen.append(str(m)), level="WARNING")
    try:
        _pick(2, exclude=set(_UNIVERSE), last_seen={})
    finally:
        logger.remove(sink_id)

    assert any("Cooldown erschoepft" in s for s in seen), seen


def test_ohne_notbetrieb_keine_warnung():
    """Im Normalbetrieb bleibt das Log ruhig."""
    from loguru import logger

    seen: list[str] = []
    sink_id = logger.add(lambda m: seen.append(str(m)), level="WARNING")
    try:
        _pick(2, exclude=set(), last_seen={})
    finally:
        logger.remove(sink_id)

    assert not any("Cooldown erschoepft" in s for s in seen), seen
