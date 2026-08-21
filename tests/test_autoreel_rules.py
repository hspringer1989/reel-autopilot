"""Tests fuer Regelpruefung, Telegram-Versand und Sonntags-Vorschau.

Anlass 21.08.2026: Reel #107 lag fertig gerendert in der Datenbank, ohne dass es je
verschickt wurde — und sein Skript hatte vier Gedankenstriche statt einem sowie das
ungeklaerte Kuerzel "PMI". Der Prompt verlangt beides, erzwungen wurde es nicht.
"""
from __future__ import annotations

import pytest

import datetime as dt

from src.content.autoreel import check_script_rules, ist_vorschautag

_ABBINDER = "Folge für Börse, die man versteht!"


def _ok_skript() -> list[str]:
    return [
        "Der deutsche Industrie-Einkaufsmanagerindex springt auf den höchsten Wert "
        "seit vier Jahren.",
        "Gleichzeitig schrumpft der Dienstleistungsbereich.",
        f"Der Aufschwung erreicht die meisten Beschäftigten also gar nicht. {_ABBINDER}",
    ]


class TestRegelpruefung:
    def test_sauberes_skript_ohne_beanstandung(self):
        assert check_script_rules(_ok_skript()) == []

    def test_ein_gedankenstrich_ist_erlaubt(self):
        t = _ok_skript()
        t[0] = "Die Industrie boomt — der Rest der Wirtschaft nicht."
        assert check_script_rules(t) == []

    def test_vier_gedankenstriche_werden_geruegt(self):
        """Genau der Fall von Reel #107."""
        t = _ok_skript()
        t[0] = "A — B — C — D."
        assert any("Gedankenstriche" in v for v in check_script_rules(t))

    def test_ziffern_werden_geruegt(self):
        t = _ok_skript()
        t[1] = "Der Wert liegt bei 54,1 Punkten."
        assert any("Ziffern" in v for v in check_script_rules(t))

    @pytest.mark.parametrize("kuerzel", ["PMI", "KGV", "ETF", "BIP"])
    def test_fachkuerzel_werden_geruegt(self, kuerzel):
        t = _ok_skript()
        t[0] = f"Der {kuerzel} steigt deutlich."
        assert any(kuerzel in v for v in check_script_rules(t))

    def test_zwei_doppelpunkte_werden_geruegt(self):
        t = _ok_skript()
        t[0] = "Klar ist: die Industrie boomt."
        t[1] = "Und klar ist auch: der Rest nicht."
        assert any("Doppelpunkt" in v for v in check_script_rules(t))

    def test_fehlender_abbinder_wird_geruegt(self):
        t = _ok_skript()
        t[-1] = "Der Aufschwung erreicht die meisten gar nicht."
        assert any("Abbinder" in v for v in check_script_rules(t))

    def test_mehrere_verstoesse_werden_alle_gemeldet(self):
        t = ["Der PMI steht bei 54,1 — historisch — hoch — wirklich."]
        v = check_script_rules(t)
        assert len(v) >= 4, v


class TestWochenvorschau:
    """Die Automatik baut abends fuer den FOLGETAG. Die Vorschau soll sonntags
    erscheinen — gebaut wird sie also im Samstag-Lauf. Ein Zahlendreher hier hiesse:
    Vorschau am falschen Tag, und das faellt erst am Sonntagmorgen auf."""

    @pytest.mark.parametrize("tag,erwartet", [
        (dt.datetime(2026, 8, 22), True),    # Samstag  -> baut die Sonntags-Vorschau
        (dt.datetime(2026, 8, 23), False),   # Sonntag  -> baut Montags-Tagesthema
        (dt.datetime(2026, 8, 21), False),   # Freitag
        (dt.datetime(2026, 8, 24), False),   # Montag
    ])
    def test_nur_samstags(self, tag, erwartet):
        assert ist_vorschautag(tag) is erwartet

    def test_jeder_samstag_im_jahr(self):
        """Kein Sonderfall ueber Monats- und Jahresgrenzen."""
        tag = dt.datetime(2026, 1, 1)
        samstage = 0
        for _ in range(365):
            if ist_vorschautag(tag):
                samstage += 1
                assert tag.strftime("%A") == "Saturday", tag
            tag += dt.timedelta(days=1)
        assert samstage == 52, samstage
