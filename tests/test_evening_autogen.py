"""Tests fuer die Abend-Automatik (_run_evening_autogen).

Der Anlass: der Automatismus lief wochenlang nicht, und niemand hat es gemerkt, weil
er im Fehlerfall schwieg. Diese Tests halten drei Zusagen fest:

  1. Der Recherche-Pfad hat Vorrang. Klappt er, wird der RSS-Pfad NICHT angefasst.
  2. Klappt er nicht, uebernimmt der RSS-Pfad.
  3. Klappt keiner von beiden, kommt eine Telegram-Meldung — Schweigen ist verboten.
"""
from __future__ import annotations

import pytest

import main
from src.content.autoreel import AutoReel


class _Feedback:
    text = "Rueckschau"
    target_seconds = 35


@pytest.fixture
def wiring(monkeypatch):
    """Haengt alle Aussenkanten ab und protokolliert, was aufgerufen wurde."""
    calls: dict[str, list] = {"telegram": [], "rss": [], "auto": []}

    async def _analyse():
        return _Feedback()

    async def _send(text):
        calls["telegram"].append(text)

    # Die Symbole werden in _run_evening_autogen funktionslokal importiert, also
    # muss am Herkunftsmodul gepatcht werden, nicht an main.
    monkeypatch.setattr("src.content.reel_feedback.analyse_last_reel", _analyse)
    monkeypatch.setattr("src.review.telegram_bot.send_text", _send)
    monkeypatch.setattr("src.review.telegram_bot.review_configured", lambda: True)
    return calls


def _set_auto(monkeypatch, calls, result):
    async def _auto(target_seconds=40):
        calls["auto"].append(target_seconds)
        if isinstance(result, Exception):
            raise result
        return result
    monkeypatch.setattr("src.content.autoreel.generate_autonomous_reel", _auto)


def _set_rss(monkeypatch, calls, result):
    async def _rss(target_seconds=None, max_age_hours=None):
        calls["rss"].append(target_seconds)
        if isinstance(result, Exception):
            raise result
        return result
    monkeypatch.setattr("src.pipeline.generate_once", _rss)


@pytest.mark.asyncio
async def test_recherchepfad_hat_vorrang(monkeypatch, wiring):
    """Klappt die Recherche, bleibt der RSS-Pfad unangetastet."""
    _set_auto(monkeypatch, wiring, AutoReel(77, "Thema X"))
    _set_rss(monkeypatch, wiring, 99)

    await main._run_evening_autogen()

    assert wiring["auto"] == [35], "Ziellaenge aus der Rueckschau nicht durchgereicht"
    assert wiring["rss"] == [], "RSS-Pfad haette nicht laufen duerfen"


@pytest.mark.asyncio
async def test_rss_faengt_die_recherche_auf(monkeypatch, wiring):
    """Findet die Recherche nichts Belegbares, uebernimmt der RSS-Trend."""
    _set_auto(monkeypatch, wiring, AutoReel(None, "kein belastbares Thema"))
    _set_rss(monkeypatch, wiring, 88)

    await main._run_evening_autogen()

    assert wiring["rss"] == [35]
    assert any("RSS" in t for t in wiring["telegram"])


@pytest.mark.asyncio
async def test_absturz_der_recherche_kippt_nicht_den_slot(monkeypatch, wiring):
    """Eine Ausnahme im Recherche-Pfad darf den Abend nicht beenden."""
    _set_auto(monkeypatch, wiring, RuntimeError("API weg"))
    _set_rss(monkeypatch, wiring, 88)

    await main._run_evening_autogen()

    assert wiring["rss"] == [35]


@pytest.mark.asyncio
async def test_kein_stiller_ausfall(monkeypatch, wiring):
    """Der eigentliche Punkt: scheitern beide Wege, MUSS eine Meldung kommen."""
    _set_auto(monkeypatch, wiring, AutoReel(None, "nichts gefunden"))
    _set_rss(monkeypatch, wiring, None)

    await main._run_evening_autogen()

    assert any("kein Reel erzeugt" in t for t in wiring["telegram"]), wiring["telegram"]


@pytest.mark.asyncio
async def test_defekte_rueckschau_stoppt_die_produktion_nicht(monkeypatch, wiring):
    """Die Rueckschau ist Beiwerk. Faellt sie aus, wird trotzdem ein Reel gebaut —
    dann eben mit der Standard-Ziellaenge."""
    async def _boom():
        raise RuntimeError("Insights-API weg")
    monkeypatch.setattr("src.content.reel_feedback.analyse_last_reel", _boom)
    _set_auto(monkeypatch, wiring, AutoReel(77, "Thema X"))
    _set_rss(monkeypatch, wiring, 99)

    await main._run_evening_autogen()

    assert wiring["auto"] == [40], "Standard-Ziellaenge erwartet"
    assert wiring["rss"] == []
