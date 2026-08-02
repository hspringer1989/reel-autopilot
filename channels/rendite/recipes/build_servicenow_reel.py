"""Custom REEL: ServiceNow stellt sein Lizenzmodell um — vom Preis pro Kopf zum Preis pro
Verbrauch — und was das für die Aktie bedeutet.

Bewusst als BRANCHEN-Thema aufgezogen, nicht als Einzelaktien-Analyse: ServiceNow allein ist
ein Nischenname (Learning: Nischenfirmen deckeln die Reichweite bei ~1.500). Der Rahmen
"KI-Agenten kippen das Preismodell der Software-Branche" ist dagegen breit anschlussfähig.

Quellen (geprüft 02.08.2026): 09.04.2026 fünf alte Tarife (Standard/Pro/Pro Plus/Enterprise/
Enterprise Plus) → drei KI-Pakete (Foundation/Advanced/Prime); ab 01.07.2026 kein Verkauf alter
Lizenzen mehr; Umstellung pro Kopf → nutzungsbasiert (Tokens/Konnektoren), im April rund 50 %
der neuen Vertragswerte nutzungsbasiert; Now Assist in jedem Tier gebündelt; KI-Sparte > 1 Mrd. $
Jahresvertragswert; Aktie 2026 rund −36 % (von ~207 $ auf ~108 $), Q1 am 22.04. über Erwartung
(3.770 vs. 3.746 Mio. $) und am Folgetag −17,75 %; Abo-Umsatz +22 % (19 % währungsbereinigt).

Vertonung nach reference/voiceover.md.
"""
import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx
from PIL import Image, ImageDraw

import config
from src import branding
from src.models import ReelScript, ScriptSegment
from src.render import broll as broll_mod
from src.render.broll import _pick_file
from src.render.renderer import pick_music, render_reel
from src.storage.database import ReelRow, session_scope

# ── voice: verbindliche Settings aus reference/voiceover.md (vom User bestätigt) ──
config.ELEVENLABS_STABILITY = 0.40
config.ELEVENLABS_SIMILARITY = 0.80
config.ELEVENLABS_STYLE = 0.05
config.ELEVENLABS_SPEED = 0.98   # „ein Mü schneller" (User 02.08.2026)

_OPENER_ID = int(os.getenv("OPENER_ID", "8979495"))   # Roboterarm auf knallblauem Grund
_CTA_ID = int(os.getenv("CTA_ID", "8513109"))         # Frau am Laptop, hell und freundlich

W, H = 1080, 1920
F = branding.load_font
BG, CARD, BLUE, BLUEL, FG, MUTED = (branding.BG, branding.CARD, branding.BLUE,
                                    branding.BLUE_LIGHT, branding.FG, branding.MUTED)
RED, GREEN, AMBER = branding.RED, branding.GREEN, branding.AMBER

STAND = "Stand: 2. August 2026"


def _ensure_clip(vid: int) -> str:
    cache = Path(config.BROLL_CACHE_DIR)
    for p in cache.glob(f"pexels_{vid}_*.mp4"):
        return str(p)
    r = httpx.get(f"https://api.pexels.com/videos/videos/{vid}",
                  headers={"Authorization": config.PEXELS_API_KEY}, timeout=30)
    r.raise_for_status()
    fl = _pick_file(r.json())
    if not fl:
        raise SystemExit(f"kein Portrait-File für {vid}")
    target = cache / f"pexels_{vid}_{fl['height']}.mp4"
    if not target.exists():
        data = httpx.get(fl["link"], timeout=120, follow_redirects=True)
        data.raise_for_status()
        cache.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data.content)
    return str(target)


def _canvas():
    img = Image.new("RGB", (W, H), BG)
    return img, ImageDraw.Draw(img)


TOP = 290  # Safe-Band y≈290–1250


def _kicker(d, text, color=BLUE):
    f = F(34, bold=True)
    tw = d.textlength(text, font=f)
    d.rounded_rectangle((60, TOP, 60 + tw + 46, TOP + 62), radius=16, fill=color)
    d.text((60 + 23, TOP + 12), text, font=f, fill=(255, 255, 255))


def _title(d, text, y=TOP + 84, size=56, color=FG):
    d.text((60, y), text, font=F(size, bold=True), fill=color)


def _footer(d):
    d.line((60, H - 118, W - 60, H - 118), fill=MUTED, width=2)
    d.text((60, H - 102), "Keine Anlageberatung · keine Kauf-/Verkaufsempfehlung · Werbung",
           font=F(23), fill=MUTED)


def _rtext(d, right_x, y, text, font, fill):
    d.text((right_x - d.textlength(text, font=font), y), text, font=font, fill=fill)


def _ctext(d, cx, y, text, font, fill):
    d.text((cx - d.textlength(text, font=font) / 2, y), text, font=font, fill=fill)


def _note(d, y, head, text, head_col, bg, h=186):
    d.rounded_rectangle((60, y, W - 60, y + h), radius=20, fill=bg)
    d.text((92, y + 20), head, font=F(30, bold=True), fill=head_col)
    branding.wrap(d, text, F(31), 92, y + 70, 44, FG, 44)
    return y + h


def _save(img, name) -> str:
    out = Path(config.OUTPUT_DIR) / name
    img.save(out, quality=92)
    return str(out)


def frame_umbau() -> str:
    """Was konkret passiert ist. Layout: 530 + 2*(146+16) + 186 = 1040 ✓"""
    img, d = _canvas()
    _kicker(d, "DER UMBAU")
    _title(d, "Fünf Tarife raus —")
    _title(d, "drei KI-Pakete rein", y=TOP + 150)
    rows = [("Bis April 2026", "Standard · Pro · Pro Plus · Enterprise · Enterprise Plus", MUTED),
            ("Seit April 2026", "Foundation · Advanced · Prime — KI fest eingebaut", BLUEL)]
    y, ch, gap = 530, 146, 16
    for name, sub, col in rows:
        d.rounded_rectangle((60, y, W - 60, y + ch), radius=20, fill=CARD)
        d.text((92, y + 26), name, font=F(36, bold=True), fill=FG)
        branding.wrap(d, sub, F(28), 92, y + 80, 46, col, 34)
        y += ch + gap
    _note(d, y + 10, "Stichtag 1. Juli 2026",
          "Seitdem verkauft ServiceNow die alten Lizenzen gar nicht mehr.",
          AMBER, (44, 36, 20), h=150)
    _footer(d)
    return _save(img, "sn_frame_umbau.jpg")


def frame_preis() -> str:
    """Der eigentliche Bruch: pro Kopf → pro Verbrauch."""
    img, d = _canvas()
    _kicker(d, "DER PREIS-SCHWENK", AMBER)
    _title(d, "Nicht mehr pro Kopf —")
    _title(d, "sondern pro Verbrauch", y=TOP + 150)
    rows = [("Früher", "Preis je Mitarbeiter mit Zugang", MUTED),
            ("Jetzt", "Preis nach tatsächlicher Nutzung", GREEN),
            ("Im April 2026", "rund 50 % der neuen Verträge schon so", BLUEL)]
    y, ch, gap = 530, 130, 16
    for name, sub, col in rows:
        d.rounded_rectangle((60, y, W - 60, y + ch), radius=20, fill=CARD)
        d.text((92, y + 24), name, font=F(36, bold=True), fill=FG)
        d.text((92, y + 76), sub, font=F(29), fill=col)
        y += ch + gap
    _note(d, y + 10, "Warum das der Kern ist",
          "Wenn KI-Agenten die Arbeit machen, braucht es weniger Zugänge — "
          "aber mehr Rechenleistung.", AMBER, (44, 36, 20))
    _footer(d)
    return _save(img, "sn_frame_preis.jpg")


def frame_aktie() -> str:
    """Die Reaktion der Börse."""
    img, d = _canvas()
    _kicker(d, "DIE BÖRSE", RED)
    _title(d, "Abgestraft —")
    _title(d, "trotz Wachstum", y=TOP + 150)
    # Name links, Wert rechts — beide Spalten schmal halten, sonst überlappen sie
    # (Fehler in #62: „Quartalszahlen im April" lief in „über den Erwartungen").
    rows = [("Kurs 2026", "rund −36 %", RED),
            ("Vom Hoch", "207 $ → 108 $", RED),
            ("Q1-Zahlen im April", "über Erwartung", GREEN),
            ("Tag danach", "−17,75 %", RED)]
    y, ch, gap = 530, 118, 12
    for name, val, col in rows:
        d.rounded_rectangle((60, y, W - 60, y + ch), radius=20, fill=CARD)
        d.text((92, y + 40), name, font=F(31, bold=True), fill=FG)
        _rtext(d, W - 92, y + 36, val, F(36, bold=True), col)
        y += ch + gap
    _footer(d)
    return _save(img, "sn_frame_aktie.jpg")


def frame_aha() -> str:
    """Der Widerspruch — das Merkbare."""
    img, d = _canvas()
    _kicker(d, "DER WIDERSPRUCH", GREEN)
    _title(d, "Umsatz rauf,")
    _title(d, "Kurs runter", y=TOP + 150)
    cards = [("Abo-Umsatz", "+22 %", GREEN), ("Aktienkurs 2026", "−36 %", RED)]
    y, ch, gap = 540, 150, 18
    for name, val, col in cards:
        d.rounded_rectangle((60, y, W - 60, y + ch), radius=22, fill=CARD)
        d.text((92, y + 50), name, font=F(38, bold=True), fill=FG)
        _rtext(d, W - 92, y + 38, val, F(64, bold=True), col)
        y += ch + gap
    _note(d, y + 12, "Die Wette dahinter",
          "Die Börse fürchtet, dass KI die Software-Umsätze auffrisst. "
          "Geht die Rechnung auf, zahlen Kunden künftig mehr, je mehr "
          "die KI arbeitet.", GREEN, (20, 40, 32), h=224)
    _footer(d)
    return _save(img, "sn_frame_aha.jpg")


# Voiceover nach reference/voiceover.md: kurze Sätze, ein Gedanke pro Satz, Pausen,
# Zahlen als Wörter, kein Floskel-Einstieg.
_TEXTS = [
    "Software wurde jahrzehntelang pro Mitarbeiter bezahlt. Mehr Leute, mehr Lizenzen. "
    "Aber was passiert, wenn die Arbeit plötzlich KI-Agenten übernehmen?",

    "ServiceNow gibt darauf eine radikale Antwort. Im April flogen fünf alte Tarife raus. "
    "Seit dem ersten Juli gibt es nur noch drei Pakete — mit KI fest eingebaut.",

    "Der eigentliche Bruch steckt im Preis. Weg von der Abrechnung pro Kopf … hin zur "
    "Abrechnung nach Verbrauch. Schon im April kam die Hälfte der neuen Verträge aus "
    "diesem Modell.",

    "Und wie reagiert die Börse darauf? Sie straft das brutal ab. Rund sechsunddreißig "
    "Prozent Minus in diesem Jahr. Im April lagen die Zahlen sogar über den Erwartungen — "
    "die Aktie fiel danach trotzdem um fast achtzehn Prozent.",

    "Und jetzt der Widerspruch. Der Abo-Umsatz wächst um zweiundzwanzig Prozent. Die Börse "
    "fürchtet, dass KI die Software-Umsätze auffrisst — und bestraft ausgerechnet die Firma, "
    "die ihr Modell genau deswegen umbaut. Geht die Rechnung auf, zahlen Kunden mehr, je "
    "mehr die KI arbeitet.",

    "Frisst die KI die Software-Umsätze? Oder macht sie sie sogar größer? Schreib es in die "
    "Kommentare und folge für den echten Durchblick an der Börse!",
]

_TITLE = "Wenn die KI arbeitet — wer zahlt dann für die Software?"

_CAPTION = (
    "🤖 Wenn KI-Agenten die Arbeit machen — wer zahlt dann noch für Software-Lizenzen?\n\n"
    "ServiceNow gibt darauf gerade eine radikale Antwort und baut sein komplettes "
    "Preismodell um:\n\n"
    "📦 Der Umbau\n"
    "· April 2026: die fünf alten Tarife (Standard, Pro, Pro Plus, Enterprise, Enterprise Plus) "
    "wurden gestrichen\n"
    "· Neu: nur noch Foundation, Advanced und Prime — KI ist in jedem Paket fest eingebaut\n"
    "· Seit 1. Juli 2026 werden die alten Lizenzen gar nicht mehr verkauft\n\n"
    "💸 Der eigentliche Bruch: der Preis\n"
    "· früher: Preis je Mitarbeiter mit Zugang\n"
    "· jetzt: Abrechnung nach tatsächlicher Nutzung\n"
    "· im April kamen schon rund 50 % der neuen Vertragswerte aus diesem Modell\n\n"
    "📉 Die Börse straft das ab\n"
    "· Kurs 2026: rund −36 % (von ~207 $ auf ~108 $)\n"
    "· Q1-Zahlen im April über den Erwartungen — Aktie am Tag danach −17,75 %\n"
    "· gleichzeitig: Abo-Umsatz +22 %, KI-Sparte über 1 Mrd. $ Jahresvertragswert\n\n"
    "🧠 Der Widerspruch: Die Börse fürchtet, dass KI die Software-Umsätze auffrisst — und "
    "bestraft ausgerechnet die Firma, die ihr Modell genau deswegen umbaut. Geht die Rechnung "
    "auf, zahlen Kunden künftig mehr, je mehr die KI für sie arbeitet. Genau das ist die Wette.\n\n"
    "Was denkst du: frisst KI die Software-Umsätze oder vergrößert sie sie? 👇\n\n"
    "⚠️ Keine Anlageberatung — nur Bildung & Unterhaltung. Kein Kauf-/Verkaufsaufruf.\n"
    "#servicenow #softwareaktien #ki #aktien #börse #saas #techaktien #investieren "
    "#finanzwissen #künstlicheintelligenz"
)


async def _main() -> None:
    opener = _ensure_clip(_OPENER_ID)
    cta = _ensure_clip(_CTA_ID)
    frames = [frame_umbau(), frame_preis(), frame_aktie(), frame_aha()]
    broll_paths = [opener, frames[0], frames[1], frames[2], frames[3], cta]

    segments = [ScriptSegment(text=t, broll_query="") for t in _TEXTS]
    script = ReelScript(hook=_TEXTS[0], segments=segments, caption=_CAPTION,
                        hashtags=[], title=_TITLE)

    with session_scope() as s:
        reel = ReelRow(trend_id=0,
                       script_json=json.dumps({"topic": "servicenow licensing shift",
                                               "title": _TITLE, "texts": _TEXTS},
                                              ensure_ascii=False),
                       caption=_CAPTION, status="draft")
        s.add(reel); s.flush(); rid = reel.id

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    base = Path(config.OUTPUT_DIR) / f"reel_{rid}_{stamp}"
    from src.tts.base import get_tts
    tts = get_tts().synthesize(script.full_text, base.with_suffix(".mp3"))
    video = render_reel(script, tts, broll_paths, base.with_suffix(".mp4"), pick_music())

    with session_scope() as s:
        r = s.get(ReelRow, rid)
        r.audio_path = tts.audio_path
        r.video_path = str(video)
        r.status = "pending_review"
    print(f"ServiceNow-Reel #{rid} fertig: {video}")


if __name__ == "__main__":
    asyncio.run(_main())
