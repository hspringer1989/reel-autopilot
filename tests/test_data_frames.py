"""Tests für die Datenframes des automatischen Pfads.

Anlass 22.08.2026: Reel #107 zeigte nach dem Startvideo nur noch Text auf Farbverlauf.
Die Zahl im Bild ist aber der Grund, warum ein Finanz-Reel funktioniert.

Die Tests sichern vor allem die zwei Eigenschaften, die in der Handarbeit immer wieder
gebrochen sind: nichts läuft unter die Untertitel, und in einer Zeile stoßen linker und
rechter Text nie aneinander.
"""
from __future__ import annotations

import pytest

pytest.importorskip("PIL")

from PIL import Image  # noqa: E402

from src.render.data_frames import (BOTTOM, FrameSpec, _unterkante,  # noqa: E402
                                    render_data_frame)


def _bild(spec: FrameSpec, tmp_path) -> Image.Image:
    return Image.open(render_data_frame(spec, str(tmp_path / "f.jpg")))


class TestSafeZone:
    def test_normaler_frame_bleibt_im_band(self, tmp_path):
        spec = FrameSpec(kicker="HEUTE", title="Drei Zahlen",
                         rows=[("Umsatz", "1,2 Mrd."), ("Gewinn", "0,3 Mrd."),
                               ("Marge", "25 %")])
        assert _unterkante(_bild(spec, tmp_path)) <= BOTTOM

    def test_ueberladener_frame_wird_verkleinert(self, tmp_path):
        """Fünf Zeilen, lange Überschrift und ein Hinweiskasten — das passt in
        Originalgröße nicht und muss schrumpfen statt überzulaufen."""
        spec = FrameSpec(
            kicker="SEHR LANGE ÜBERSCHRIFT HIER",
            title="Eine ziemlich lange Bildüberschrift über mehrere Zeilen",
            highlight="+177 %", highlight_sub="an einem einzigen Tag",
            rows=[("Kennzahl eins", "1,1"), ("Kennzahl zwei", "2,2"),
                  ("Kennzahl drei", "3,3"), ("Kennzahl vier", "4,4"),
                  ("Kennzahl fünf", "5,5")],
            note_head="Warum das zählt",
            note_text="Ein längerer Hinweis, der über mehrere Zeilen läuft und den "
                      "Frame zusätzlich nach unten drückt.")
        assert _unterkante(_bild(spec, tmp_path)) <= BOTTOM

    @pytest.mark.parametrize("kind", ["rows", "compare", "steps"])
    def test_alle_formen_bleiben_im_band(self, kind, tmp_path):
        spec = FrameSpec(kind=kind, kicker="TEST", title="Überschrift",
                         rows=[("Erst", "eins"), ("Dann", "zwei"), ("Zuletzt", "drei")])
        assert _unterkante(_bild(spec, tmp_path)) <= BOTTOM


class TestKollision:
    def test_langes_label_kollidiert_nicht(self, tmp_path):
        """Genau der Fehler aus Reel #105: 'Inflationsgeschützte Bundesanleihe' lief in
        'knapp 20 Jahre Restlaufzeit' hinein."""
        spec = FrameSpec(rows=[("Inflationsgeschützte Bundesanleihe",
                                "knapp 20 Jahre Restlaufzeit")])
        img = _bild(spec, tmp_path)
        assert _unterkante(img) <= BOTTOM     # gerendert, nicht abgestürzt

    def test_extremfall_wird_gekuerzt_statt_zu_ueberlappen(self, tmp_path):
        spec = FrameSpec(rows=[("Ein außergewöhnlich langes Label, das niemals passt",
                                "und ein ebenso langer Wert daneben")])
        assert _bild(spec, tmp_path) is not None


class TestInhalt:
    def test_leerer_frame_stuerzt_nicht_ab(self, tmp_path):
        assert _bild(FrameSpec(), tmp_path) is not None

    def test_datei_wird_geschrieben(self, tmp_path):
        p = tmp_path / "unter" / "frame.jpg"
        out = render_data_frame(FrameSpec(rows=[("A", "1")]), str(p))
        assert p.exists() and out == str(p)

    def test_unbekannte_form_faellt_auf_rows_zurueck(self, tmp_path):
        spec = FrameSpec(kind="quatsch", rows=[("A", "1"), ("B", "2")])
        assert _unterkante(_bild(spec, tmp_path)) <= BOTTOM


class TestBauplaene:
    """_frames_bauen liest die Baupläne des Skripts. Ein kaputter Bauplan darf nie das
    Reel kosten — dann eben ein Farbverlauf an dieser Stelle."""

    def _bauen(self, daten, anzahl, tmp_path, monkeypatch):
        import config

        from src.content.autoreel import _frames_bauen
        monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path)
        return _frames_bauen(daten, anzahl, reel_id=1)

    def test_baut_einen_frame_je_segment(self, tmp_path, monkeypatch):
        daten = {"frames": [{"kind": "rows", "rows": [["A", "1"]]},
                            {"kind": "rows", "rows": [["B", "2"]]}]}
        out = self._bauen(daten, 2, tmp_path, monkeypatch)
        assert len(out) == 2 and all(out)

    def test_fehlender_bauplan_wird_zu_none(self, tmp_path, monkeypatch):
        out = self._bauen({"frames": [{"rows": [["A", "1"]]}]}, 3, tmp_path, monkeypatch)
        assert out[0] and out[1] is None and out[2] is None

    def test_frame_ohne_zahlen_wird_uebersprungen(self, tmp_path, monkeypatch):
        """Ein Frame ohne Zeilen und ohne grosse Zahl ist ein leeres Bild — dann lieber
        der Farbverlauf."""
        out = self._bauen({"frames": [{"kind": "rows", "title": "nur Text"}]},
                          1, tmp_path, monkeypatch)
        assert out == [None]

    def test_kaputter_bauplan_kippt_nicht(self, tmp_path, monkeypatch):
        daten = {"frames": [{"kind": "rows", "rows": "kein Array"},
                            {"rows": [["A", "1"]]}]}
        out = self._bauen(daten, 2, tmp_path, monkeypatch)
        assert out[0] is None and out[1]

    def test_ohne_frames_schluessel(self, tmp_path, monkeypatch):
        assert self._bauen({}, 3, tmp_path, monkeypatch) == [None, None, None]


class TestBreite:
    """Vorfall Reel #112: im Vergleichs-Frame lief "9 Stimmen" ueber den Kartenrand.
    Die Safe-Zone-Pruefung sieht das nicht — sie misst nur die Hoehe."""

    def _spalten_frei(self, img, x_von, x_bis, y_von, y_bis) -> bool:
        """Ist der senkrechte Streifen zwischen zwei Karten leer?"""
        px = img.convert("L").load()
        for y in range(y_von, y_bis, 3):
            for x in range(x_von, x_bis):
                if px[x, y] > 90:
                    return False
        return True

    def test_lange_werte_bleiben_in_den_karten(self, tmp_path):
        spec = FrameSpec(kind="compare", kicker="ABSTIMMUNG", title="Dissens",
                         accent="amber",
                         rows=[("Für unveränderte Zinsen", "9 Stimmen"),
                               ("Für Zinserhöhung", "3 Stimmen")])
        img = _bild(spec, tmp_path)
        # Der Spalt zwischen den beiden Karten ist 40 px breit, mittig bei x=540.
        assert self._spalten_frei(img, 528, 552, 500, 1000)

    def test_sehr_langer_wert_wird_klein_genug(self, tmp_path):
        spec = FrameSpec(kind="compare", rows=[("A", "einhundertvierundzwanzig Punkte"),
                                               ("B", "zweihundert Punkte")])
        img = _bild(spec, tmp_path)
        assert self._spalten_frei(img, 528, 552, 400, 1000)

    def test_lange_grosse_zahl_bleibt_im_bild(self, tmp_path):
        spec = FrameSpec(highlight="+1.234.567,89 Prozentpunkte",
                         rows=[("A", "1")])
        img = _bild(spec, tmp_path)
        px = img.convert("L").load()
        for y in range(300, 700, 2):          # Raender muessen frei bleiben
            assert px[8, y] < 90 and px[1071, y] < 90
