"""Datenframes für Reels — der Bildteil, der den Sprechtext trägt.

Bis hierher konnte nur die Handarbeit Frames mit Zahlen zeichnen; der automatische
Pfad legte hinter jedes Segment einen Farbverlauf. Dem Zuschauer fällt genau das auf:
„nach dem Anfangsvideo kommt nur noch Text". Die Zahl im Bild ist aber der Grund,
warum ein Finanz-Reel überhaupt funktioniert — gesprochene Zahlen behält niemand.

Dieses Modul zeichnet drei Grundformen, aus denen sich praktisch jedes Thema bauen
lässt. Sie sind bewusst wenige: ein Renderer mit zwanzig Layouts wird nie geprüft, drei
schon.

    rows     Kennzahlen untereinander            Label links, Wert rechts
    compare  zwei Größen nebeneinander           „du" gegen „der Staat"
    steps    Verlauf oder Ursachenkette          drei bis vier Stationen

Zwei Dinge macht der Renderer selbst, weil sie in der Handarbeit jedes Mal Fehler
verursacht haben:

* **Safe-Zone.** Inhalt nur zwischen y=290 (darüber steht auf Instagram der Profilname)
  und y=1250 (darunter beginnt das Band der eingebrannten Untertitel). Passt der Inhalt
  nicht, wird verkleinert statt überzulaufen.
* **Kollision Label/Wert.** In einer Zeile stoßen linker und rechter Text sonst
  aneinander. Das sieht man auf dem Quellbild kaum und im Video gar nicht mehr.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw

from src import branding

W, H = 1080, 1920
TOP = 290
BOTTOM = 1250            # darunter liegen die Untertitel
MARGIN = 60

F = branding.load_font
BG, CARD, FG, MUTED = branding.BG, branding.CARD, branding.FG, branding.MUTED
BLUE, BLUE_LIGHT = branding.BLUE, branding.BLUE_LIGHT
GREEN, AMBER, RED = branding.GREEN, branding.AMBER, branding.RED
WHITE = (255, 255, 255)

_AKZENTE = {"blue": BLUE, "green": GREEN, "amber": AMBER, "red": RED}
# Gedämpfte Flächen hinter farbigen Blöcken — dieselben Töne, stark abgedunkelt.
_FLAECHEN = {"blue": (18, 32, 48), "green": (20, 46, 32),
             "amber": (52, 40, 18), "red": (52, 24, 24)}


@dataclass
class FrameSpec:
    """Was auf einem Frame stehen soll — ohne jede Angabe zur Platzierung."""
    kind: str = "rows"                       # rows | compare | steps
    kicker: str = ""
    title: str = ""
    accent: str = "blue"
    rows: list[tuple[str, str]] = field(default_factory=list)
    highlight: str = ""                      # eine große Zahl über dem Inhalt
    highlight_sub: str = ""
    note_head: str = ""
    note_text: str = ""
    footer: str = "Keine Anlageberatung · KI-generiert"


def _passend(d, text: str, max_breite: int, groesse: int, bold: bool = False):
    """Groesste Schrift, mit der `text` noch in `max_breite` passt.

    Die Hoehenpruefung allein reicht nicht: bei Reel #112 lief "9 Stimmen" im
    Vergleichs-Frame ueber den Kartenrand hinaus, weil nur vertikal skaliert wurde.
    Breite muss pro Textstueck geprueft werden, nicht fuer den Frame als Ganzes.
    """
    f = F(groesse, bold=bold)
    while groesse > 16 and d.textlength(text, font=f) > max_breite:
        groesse -= 2
        f = F(groesse, bold=bold)
    return f


def _akzent(spec: FrameSpec):
    return _AKZENTE.get(spec.accent, BLUE), _FLAECHEN.get(spec.accent, _FLAECHEN["blue"])


def _kicker(d, text, farbe):
    if not text:
        return TOP
    f = F(34, bold=True)
    b = d.textlength(text, font=f)
    d.rounded_rectangle((MARGIN, TOP, MARGIN + b + 46, TOP + 62), radius=16, fill=farbe)
    d.text((MARGIN + 23, TOP + 12), text, font=f, fill=WHITE)
    return TOP + 62


def _titel(d, text, y, groesse=56):
    """Titel umbrechen. branding.wrap bricht nach ZEICHENZAHL, deshalb hier eine
    echte Pixelmessung — sonst reißen lange Wörter aus dem Bild."""
    if not text:
        return y
    f = F(groesse, bold=True)
    zeilen, rest = [], text.split()
    aktuell = ""
    for wort in rest:
        probe = f"{aktuell} {wort}".strip()
        if d.textlength(probe, font=f) <= W - 2 * MARGIN:
            aktuell = probe
        else:
            if aktuell:
                zeilen.append(aktuell)
            aktuell = wort
    if aktuell:
        zeilen.append(aktuell)
    for i, z in enumerate(zeilen[:3]):
        d.text((MARGIN, y + 22 + i * (groesse + 10)), z, font=f, fill=FG)
    return y + 22 + len(zeilen[:3]) * (groesse + 10)


def _zeile(d, y, h, label, wert, lf, wf, wert_farbe=FG) -> int:
    """Eine Zeile mit Label links und Wert rechts — inklusive Kollisionsprüfung.

    Kollidieren sie, wird zuerst der Wert kleiner gesetzt, dann das Label. Erst wenn
    beides nichts hilft, wird das Label gekürzt: ein abgeschnittenes Wort ist immer
    noch besser als zwei ineinander laufende Texte.
    """
    d.rounded_rectangle((MARGIN, y, W - MARGIN, y + h), radius=18, fill=CARD)
    lx, rx = MARGIN + 32, W - MARGIN - 32

    for _ in range(6):
        lb, wb = d.textlength(label, font=lf), d.textlength(wert, font=wf)
        if lx + lb + 24 <= rx - wb:
            break
        if wf.size > 24:
            wf = F(wf.size - 3, bold=True)
        elif lf.size > 20:
            lf = F(lf.size - 3)
        else:
            while label and lx + d.textlength(label + "…", font=lf) + 24 > rx - wb:
                label = label[:-1]
            label += "…"
            break

    d.text((lx, y + (h - lf.size) / 2 - 2), label, font=lf, fill=MUTED)
    d.text((rx - d.textlength(wert, font=wf), y + (h - wf.size) / 2 - 4),
           wert, font=wf, fill=wert_farbe)
    return y + h


def _notiz(d, y, kopf, text, farbe, flaeche, h) -> int:
    d.rounded_rectangle((MARGIN, y, W - MARGIN, y + h), radius=20, fill=flaeche)
    d.text((MARGIN + 32, y + 20), kopf, font=F(30, bold=True), fill=farbe)
    branding.wrap(d, text, F(31), MARGIN + 32, y + 70, 44, FG, 44)
    return y + h


def _footer(d, text):
    d.line((MARGIN, H - 118, W - MARGIN, H - 118), fill=MUTED, width=2)
    d.text((MARGIN, H - 102), text, font=F(22), fill=MUTED)


def _zeichne(spec: FrameSpec, skala: float) -> Image.Image:
    """Einen Durchlauf zeichnen. `skala` verkleinert alles Vertikale, wenn der Inhalt
    sonst in die Untertitel läuft."""
    farbe, flaeche = _akzent(spec)
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    y = _kicker(d, spec.kicker, farbe)
    y = _titel(d, spec.title, y, groesse=int(56 * min(1.0, skala + 0.1)))

    if spec.highlight:
        gr = int(96 * skala)
        f = _passend(d, spec.highlight, W - 2 * MARGIN, gr, bold=True)
        y += int(24 * skala)
        d.text(((W - d.textlength(spec.highlight, font=f)) / 2, y),
               spec.highlight, font=f, fill=farbe)
        y += gr + 8
        if spec.highlight_sub:
            fs = F(30)
            d.text(((W - d.textlength(spec.highlight_sub, font=fs)) / 2, y),
                   spec.highlight_sub, font=fs, fill=MUTED)
            y += 44

    y += int(28 * skala)

    if spec.kind == "compare" and len(spec.rows) >= 2:
        hoehe = int(360 * skala)
        breite = (W - 2 * MARGIN - 40) // 2
        for i, (label, wert) in enumerate(spec.rows[:2]):
            x0 = MARGIN + i * (breite + 40)
            bg = flaeche if i == 1 else CARD
            col = farbe if i == 1 else MUTED
            d.rounded_rectangle((x0, y, x0 + breite, y + hoehe), radius=22, fill=bg)
            cx = x0 + breite / 2
            innen = breite - 36
            fl = _passend(d, label, innen, int(34 * skala), bold=True)
            d.text((cx - d.textlength(label, font=fl) / 2, y + int(30 * skala)),
                   label, font=fl, fill=col)
            fw = _passend(d, wert, innen, int(80 * skala), bold=True)
            d.text((cx - d.textlength(wert, font=fw) / 2, y + int(120 * skala)),
                   wert, font=fw, fill=col)
        y += hoehe + 22

    elif spec.kind == "steps":
        hoehe = int(120 * skala)
        for i, (label, wert) in enumerate(spec.rows[:4]):
            d.rounded_rectangle((MARGIN, y, W - MARGIN, y + hoehe), radius=18, fill=CARD)
            nf = F(int(30 * skala), bold=True)
            d.ellipse((MARGIN + 26, y + hoehe / 2 - 22, MARGIN + 70, y + hoehe / 2 + 22),
                      fill=farbe)
            d.text((MARGIN + 40, y + hoehe / 2 - 18), str(i + 1), font=nf, fill=WHITE)
            d.text((MARGIN + 96, y + 24), label, font=F(int(28 * skala)), fill=MUTED)
            fw = _passend(d, wert, W - 2 * MARGIN - 130, int(34 * skala), bold=True)
            d.text((MARGIN + 96, y + 62), wert, font=fw, fill=FG)
            y += hoehe + 14

    else:                                            # rows
        hoehe = int(112 * skala)
        for label, wert in spec.rows[:5]:
            y = _zeile(d, y, hoehe, label, wert,
                       F(int(30 * skala)), F(int(36 * skala), bold=True), FG) + 12

    if spec.note_head or spec.note_text:
        y = _notiz(d, y + 6, spec.note_head, spec.note_text, farbe, flaeche,
                   int(170 * skala))

    _footer(d, spec.footer)
    return img


def _unterkante(img: Image.Image) -> int:
    """Unterste Bildzeile, die noch Inhalt trägt — der Footer zählt nicht mit."""
    grau = img.convert("L")
    px = grau.load()
    unten = 0
    for y in range(TOP, H - 160):
        summe = sum(px[x, y] for x in range(0, W, 6)) / (W / 6)
        if summe > 60:
            unten = y
    return unten


def render_data_frame(spec: FrameSpec, out_path: str) -> str:
    """Frame zeichnen und garantieren, dass er in der Safe-Zone bleibt.

    Statt Maße zu raten wird gezeichnet, gemessen und bei Bedarf verkleinert neu
    gezeichnet. Das kostet ein paar Millisekunden und erspart die Fehlerklasse, die in
    der Handarbeit am häufigsten war: Text, der unter den Untertiteln verschwindet.
    """
    img = None
    for skala in (1.0, 0.92, 0.84, 0.76, 0.68, 0.6):
        img = _zeichne(spec, skala)
        if _unterkante(img) <= BOTTOM:
            break
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, quality=92)
    return out_path
