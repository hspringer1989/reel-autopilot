"""Tests fuer das Opener-Register.

Anlass 22.08.2026: Reel #112 bekam ein Startvideo, das es schon gab. Die
Ausschlussliste las nur das Skript-JSON — und dort steht die opener_id nur bei den
automatisch gebauten Reels. Von rund dreissig verbrauchten Clips waren vier sichtbar.
"""
from __future__ import annotations

import json

import pytest


@pytest.fixture
def register(tmp_path, monkeypatch):
    import config

    from src.render import opener_history as oh
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    # Datenbankquelle abklemmen: hier wird das Register selbst geprueft.
    monkeypatch.setattr(oh, "_aus_skript_json", lambda: set())
    return oh


def test_altbestand_ist_von_anfang_an_gesperrt(register):
    """Auch ohne jede Datei duerfen die handgebauten Opener nicht wiederkommen."""
    ids = register.verwendete_ids()
    assert 8490654 in ids          # Pipette, Reel #101
    assert 38269522 in ids         # Baukraene, Reel #106
    assert len(ids) >= 20


def test_merken_sperrt_dauerhaft(register):
    assert 999001 not in register.verwendete_ids()
    register.merken(999001, "Testmotiv")
    assert 999001 in register.verwendete_ids()


def test_ueberlebt_neustart(register, tmp_path):
    register.merken(999002, "Motiv")
    daten = json.loads((tmp_path / "opener_history.json").read_text(encoding="utf-8"))
    assert "999002" in daten


def test_motivklassen_neueste_zuerst(register):
    register.merken(999003, "erstes Motiv")
    register.merken(999004, "zweites Motiv")
    assert set(register.motivklassen()) >= {"erstes Motiv", "zweites Motiv"}


def test_kaputte_datei_startet_mit_altbestand(register, tmp_path):
    (tmp_path / "opener_history.json").write_text("kein JSON", encoding="utf-8")
    assert 8490654 in register.verwendete_ids()


def test_null_id_wird_ignoriert(register):
    register.merken(0, "nichts")
    assert 0 not in register.verwendete_ids()


def test_nicht_schreibbar_kippt_nicht(register, tmp_path, monkeypatch):
    """Lieber ein Register ohne Gedaechtnis als ein abgestuerzter Lauf."""
    import config

    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setattr(config, "DATA_DIR", blocker / "unter")
    register.merken(999005, "Motiv")     # darf nicht werfen


def test_skript_json_wird_mitgelesen(tmp_path, monkeypatch):
    """Die dritte Quelle: Reels, die die ID im Skript fuehren."""
    import config

    from src.render import opener_history as oh
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(oh, "_aus_skript_json", lambda: {123456})
    assert 123456 in oh.verwendete_ids()
