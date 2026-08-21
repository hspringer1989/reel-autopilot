"""Tests fuer Slot-Nachholfenster und Slot-Merkliste (Vorfall 21.08.2026).

Reel #106 war freigegeben und wurde um 09:00 nicht gepostet, weil kein Tick in genau
diese Minute fiel — der Tages-Story-Build hatte den Durchlauf ueber drei Minuten
aufgehalten. Vorher war aus demselben Grund schon die Redaktionssitzung ausgefallen.

Die Tests halten beide Halbheiten fest, die zusammen die Loesung ergeben:
faellig bleiben (Nachholfenster) UND genau einmal laufen (Merkliste ueber Neustarts).
"""
from __future__ import annotations

import json

import pytest

from main import _slot_due, _SlotLedger


class TestSlotDue:
    def test_punkt_auf_der_slotzeit(self):
        assert _slot_due("09:00", "09:00", 90)

    def test_uebersprungene_minute_wird_nachgeholt(self):
        """Der eigentliche Vorfall: der Tick landete auf 09:01, nicht auf 09:00."""
        assert _slot_due("09:01", "09:00", 90)

    def test_langer_build_haelt_den_slot_am_leben(self):
        """Der Story-Build lief am 21.08. von 09:01:52 bis 09:05:16."""
        assert _slot_due("09:06", "09:00", 90)

    def test_vor_der_slotzeit_nicht_faellig(self):
        assert not _slot_due("08:59", "09:00", 90)

    def test_nach_dem_fenster_nicht_mehr(self):
        """Ein Neustart am Abend darf den Morgen-Slot nicht nachholen."""
        assert not _slot_due("20:00", "09:00", 90)

    def test_fenster_rechnet_ueber_die_stunde(self):
        """In Minuten seit Mitternacht, nicht als Zeichenkette — sonst waere
        '10:15' kleiner als '09:00' + 90 nicht korrekt bestimmbar."""
        assert _slot_due("10:29", "09:00", 90)
        assert not _slot_due("10:30", "09:00", 90)

    def test_grenze_ist_exklusiv(self):
        assert _slot_due("09:44", "09:00", 45)
        assert not _slot_due("09:45", "09:00", 45)


class TestSlotLedger:
    def test_merkt_sich_gelaufene_slots(self, tmp_path):
        led = _SlotLedger(tmp_path / "l.json")
        assert ("2026-08-21", "post") not in led
        led.add(("2026-08-21", "post"))
        assert ("2026-08-21", "post") in led

    def test_ueberlebt_neustart(self, tmp_path):
        """Der Kern: ohne Persistenz wuerde ein Neustart um 09:30 den 09:00-Slot
        im Nachholfenster ein zweites Mal ausloesen und doppelt posten."""
        p = tmp_path / "l.json"
        _SlotLedger(p).add(("2026-08-21", "post"))
        assert ("2026-08-21", "post") in _SlotLedger(p)

    def test_trennt_die_tage(self, tmp_path):
        led = _SlotLedger(tmp_path / "l.json")
        led.add(("2026-08-20", "post"))
        assert ("2026-08-21", "post") not in led

    def test_alte_tage_werden_aufgeraeumt(self, tmp_path):
        p = tmp_path / "l.json"
        led = _SlotLedger(p)
        for day in ("2026-08-17", "2026-08-18", "2026-08-19", "2026-08-20", "2026-08-21"):
            led.add((day, "post"))
        gespeichert = json.loads(p.read_text(encoding="utf-8"))
        assert sorted(gespeichert) == ["2026-08-19", "2026-08-20", "2026-08-21"]

    def test_kaputte_datei_kippt_den_start_nicht(self, tmp_path):
        p = tmp_path / "l.json"
        p.write_text("das ist kein JSON", encoding="utf-8")
        led = _SlotLedger(p)
        assert ("2026-08-21", "post") not in led
        led.add(("2026-08-21", "post"))
        assert ("2026-08-21", "post") in led

    def test_nicht_schreibbarer_pfad_wirft_nicht(self, tmp_path):
        """Lieber ein Slot ohne Gedaechtnis als ein abgestuerzter Dienst."""
        blocker = tmp_path / "blocker"
        blocker.write_text("x", encoding="utf-8")
        led = _SlotLedger(blocker / "unter" / "l.json")
        led.add(("2026-08-21", "post"))
        assert ("2026-08-21", "post") in led


@pytest.mark.parametrize("slot", ["00:00", "23:30"])
def test_randzeiten(slot):
    assert _slot_due(slot, slot, 30)
