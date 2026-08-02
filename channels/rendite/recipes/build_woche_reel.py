"""Custom REEL: outlook on the trading week 3–7 August 2026 — built deliberately as a
USE-VALUE CALENDAR (dates + what the market watches), not as a prediction, because the
engagement data shows preview reels flop when they only speculate (#35: 353 views) while
concrete, saveable content performs.

Opener: NYSE facade with flag (instantly readable as "stock market").
CTA: Holi colour festival (bright, colourful — deliberately NOT the paint/confetti clips).

Sources (verified 01.08.2026): CNBC week-ahead 03.–07.08.2026 (jobs report Friday,
+87.500 expected vs 57.000 prior, unemployment 4.3% vs 4.2%, Fed funds 3.50–3.75%,
earnings calendar Mon–Fri), it-boltwise/boerse.de (EU CPI, ISM, German factory orders).
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

# ── voice: neue verbindliche Settings aus reference/voiceover.md (01.08.2026).
# style runter auf 0.05 = ruhige, gleichmäßige Betonung; speed 0.95 = souveräner.
config.ELEVENLABS_STABILITY = 0.40
config.ELEVENLABS_SIMILARITY = 0.80
config.ELEVENLABS_STYLE = 0.05
config.ELEVENLABS_SPEED = 0.95

_OPENER_ID = int(os.getenv("OPENER_ID", "5995617"))   # NYSE facade + flag, daylight
_CTA_ID = int(os.getenv("CTA_ID", "5834559"))         # NY street, yellow cabs — bright, on-theme

W, H = 1080, 1920
F = branding.load_font
BG, CARD, BLUE, BLUEL, FG, MUTED = (branding.BG, branding.CARD, branding.BLUE,
                                    branding.BLUE_LIGHT, branding.FG, branding.MUTED)
RED, GREEN, AMBER = branding.RED, branding.GREEN, branding.AMBER


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


TOP = 290  # safe band: content stays inside y≈290–1250


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


def _note(d, y, head, text, head_col, bg, h=186):
    d.rounded_rectangle((60, y, W - 60, y + h), radius=20, fill=bg)
    d.text((92, y + 20), head, font=F(30, bold=True), fill=head_col)
    branding.wrap(d, text, F(31), 92, y + 70, 44, FG, 44)
    return y + h


def _save(img, name) -> str:
    out = Path(config.OUTPUT_DIR) / name
    img.save(out, quality=92)
    return str(out)


def frame_calendar() -> str:
    """The week at a glance — the saveable core of the reel."""
    img, d = _canvas()
    _kicker(d, "DIE WOCHE IM ÜBERBLICK")
    _title(d, "3. bis 7. August 2026")
    d.text((60, TOP + 158), "Quartalszahlen und Termine, auf die der Markt schaut",
           font=F(26), fill=MUTED)
    rows = [("MO 3.8.", "Palantir · Snap", BLUEL),
            ("DI 4.8.", "AMD · Pfizer · Caterpillar", AMBER),
            ("MI 5.8.", "Disney · Eli Lilly · Uber", BLUEL),
            ("DO 6.8.", "Airbnb · Warner Bros. · Lyft", BLUEL),
            ("FR 7.8.", "US-Arbeitsmarktbericht", RED)]
    y, ch, gap = 500, 118, 12
    for day, what, col in rows:
        d.rounded_rectangle((60, y, W - 60, y + ch), radius=20, fill=CARD)
        d.text((92, y + 38), day, font=F(40, bold=True), fill=col)
        d.text((330, y + 42), what, font=F(31), fill=FG)
        y += ch + gap
    _footer(d)
    return _save(img, "wk_frame_calendar.jpg")


def frame_amd() -> str:
    """Tuesday: the first real test after the July chip crash."""
    img, d = _canvas()
    _kicker(d, "DIENSTAG: DER TEST", AMBER)
    _title(d, "AMD nach dem")
    _title(d, "Chip-Absturz", y=TOP + 150)
    rows = [("Juli: Chip-Sektor", "schlechtester Monat seit 2008", RED),
            ("Dienstag, 4. August", "AMD legt Quartalszahlen vor", AMBER)]
    y, ch, gap = 530, 130, 16
    for name, sub, col in rows:
        d.rounded_rectangle((60, y, W - 60, y + ch), radius=20, fill=CARD)
        d.text((92, y + 24), name, font=F(36, bold=True), fill=FG)
        d.text((92, y + 76), sub, font=F(29), fill=col)
        y += ch + gap
    _note(d, y + 10, "Die Frage dahinter",
          "Bröckelt die Nachfrage nach KI-Chips wirklich — oder waren "
          "nur die Kurse übertrieben?", AMBER, (44, 36, 20))
    _footer(d)
    return _save(img, "wk_frame_amd.jpg")


def frame_jobs() -> str:
    """Friday: the week's main event, with the concrete expectations."""
    img, d = _canvas()
    _kicker(d, "FREITAG: DER HÖHEPUNKT", RED)
    _title(d, "US-Arbeitsmarkt,")
    _title(d, "7. August", y=TOP + 150)
    rows = [("Neue Stellen erwartet", "+87.500", GREEN),
            ("Im Juni waren es", "57.000", MUTED),
            ("Arbeitslosenquote", "4,3 % erwartet", AMBER),
            ("US-Leitzins aktuell", "3,50 – 3,75 %", BLUEL)]
    y, ch, gap = 530, 118, 12
    for name, val, col in rows:
        d.rounded_rectangle((60, y, W - 60, y + ch), radius=20, fill=CARD)
        d.text((92, y + 38), name, font=F(34, bold=True), fill=FG)
        _rtext(d, W - 92, y + 32, val, F(42, bold=True), col)
        y += ch + gap
    _footer(d)
    return _save(img, "wk_frame_jobs.jpg")


def frame_aha() -> str:
    """The saveable principle: why weak jobs data can lift share prices."""
    img, d = _canvas()
    _kicker(d, "GUT ZU WISSEN", GREEN)
    _title(d, "Warum schlechte Zahlen")
    _title(d, "die Kurse heben können", y=TOP + 150)
    rows = [("Schwacher Arbeitsmarkt", "Zinssenkung wird wahrscheinlicher", GREEN),
            ("Starker Arbeitsmarkt", "Zinsen bleiben länger oben", RED)]
    y, ch, gap = 530, 140, 16
    for name, sub, col in rows:
        d.rounded_rectangle((60, y, W - 60, y + ch), radius=20, fill=CARD)
        d.text((92, y + 28), name, font=F(36, bold=True), fill=FG)
        d.text((92, y + 82), sub, font=F(29), fill=col)
        y += ch + gap
    _note(d, y + 10, "Faustregel für diesen Freitag",
          "An Arbeitsmarkt-Tagen gilt oft: schlechte Nachrichten sind "
          "gute Nachrichten — weil billiges Geld die Kurse stützt.",
          GREEN, (20, 40, 32))
    _footer(d)
    return _save(img, "wk_frame_aha.jpg")


# Voiceover: numbers as words, concrete dates spoken.
# Nach reference/voiceover.md: kurze Sätze, ein Gedanke pro Satz, Pausen über — und …,
# rhythmische Aufzählung, kein Floskel-Einstieg, Zahlen als Wörter, Palantir → Palantier.
_TEXTS = [
    "Diese Woche wird spannend … und der wichtigste Termin kommt gleich am Freitag. "
    "Dann nämlich der amerikanische Arbeitsmarktbericht — und der bewegt die Kurse mehr "
    "als jede Quartalszahl. Hier ist dein Fahrplan.",

    "Montag geht es los. Palantier und Snap machen den Anfang. Dienstag folgen Ah Em De und "
    "Caterpillar. Mittwoch Disney und Eli Lilly. Und am Donnerstag Airbnb.",

    "Der spannendste Termin — Dienstag. Da legt Ah Em De seine Zahlen vor. Ausgerechnet nach "
    "dem schlechtesten Chipmonat seit zweitausendacht. Es ist der erste echte Test: Bröckelt "
    "die Nachfrage nach KI-Chips wirklich? Oder waren nur die Kurse übertrieben?",

    "Am Freitag geht es um den Arbeitsmarkt. Erwartet werden rund siebenundachtzigtausend"
    "fünfhundert neue Stellen. Im Juni waren es nur siebenundfünfzigtausend. "
    "Die Arbeitslosenquote? Die soll leicht steigen — auf vier Komma drei Prozent.",

    "Und jetzt kommt der Punkt, den die meisten übersehen. An diesem Tag gilt oft: "
    "Schlechte Nachrichten sind gute Nachrichten. Klingt verrückt … ist aber so. "
    "Ein schwacher Arbeitsmarkt macht Zinssenkungen wahrscheinlicher. Und billiges Geld "
    "stützt die Kurse. Starke Zahlen heißen umgekehrt: Die Zinsen bleiben oben.",

    "Welchen Termin hast du dir markiert? Schreib es in die Kommentare — und folge für den "
    "echten Durchblick an der Börse!",
]

_TITLE = "Die neue Börsenwoche: Dein Fahrplan für den 3. bis 7. August"

_CAPTION = (
    "🗓️ Die neue Börsenwoche: 3. bis 7. August 2026 — dein Fahrplan zum Speichern.\n\n"
    "📊 Quartalszahlen:\n"
    "MO 3.8. — Palantir, Snap, Marriott\n"
    "DI 4.8. — AMD, Pfizer, Caterpillar, Spotify\n"
    "MI 5.8. — Disney, Eli Lilly, Uber, Shopify, SanDisk\n"
    "DO 6.8. — Airbnb, Warner Bros. Discovery, Lyft, Roku\n"
    "FR 7.8. — Take-Two, Under Armour\n\n"
    "🔥 Der spannendste Termin: AMD am Dienstag. Nach dem schlechtesten Chip-Monat seit 2008 "
    "ist das der erste echte Test, ob die KI-Nachfrage bröckelt — oder ob nur die Kurse "
    "übertrieben haben.\n\n"
    "🇺🇸 Der Höhepunkt: US-Arbeitsmarktbericht am Freitag, 7. August\n"
    "· erwartet: +87.500 neue Stellen (Juni: 57.000)\n"
    "· Arbeitslosenquote: 4,3 % erwartet (zuvor 4,2 %)\n"
    "· US-Leitzins: 3,50–3,75 % (Fed hielt am 29.07. still)\n\n"
    "🇪🇺 Dazu in Europa: Arbeitslosenquote und BIP, in Deutschland die Werksaufträge.\n\n"
    "🧠 Faustregel für Arbeitsmarkt-Tage: Schlechte Nachrichten sind oft gute Nachrichten. "
    "Schwache Jobzahlen machen Zinssenkungen wahrscheinlicher — und billigeres Geld stützt "
    "die Kurse. Starke Zahlen heißen umgekehrt: Die Zinsen bleiben länger oben.\n\n"
    "Welchen Termin hast du dir markiert? 👇\n\n"
    "⚠️ Keine Anlageberatung — nur Bildung & Unterhaltung. Kein Kauf-/Verkaufsaufruf. "
    "Keine Prognose, sondern eine Termin-Übersicht.\n"
    "Quellen: CNBC, boerse.de (Stand 01.08.2026)\n"
    "#börsenwoche #aktien #börse #amd #arbeitsmarkt #zinsen #quartalszahlen #investieren "
    "#finanzwissen #wochenausblick"
)


async def _main() -> None:
    opener = _ensure_clip(_OPENER_ID)
    cta = _ensure_clip(_CTA_ID)
    frames = [frame_calendar(), frame_amd(), frame_jobs(), frame_aha()]
    broll_paths = [opener, frames[0], frames[1], frames[2], frames[3], cta]

    segments = [ScriptSegment(text=t, broll_query="") for t in _TEXTS]
    script = ReelScript(hook=_TEXTS[0], segments=segments, caption=_CAPTION,
                        hashtags=[], title=_TITLE)

    with session_scope() as s:
        reel = ReelRow(trend_id=0,
                       script_json=json.dumps({"topic": "trading week 3-7 august 2026",
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
    print(f"Börsenwochen-Reel #{rid} fertig: {video}")


if __name__ == "__main__":
    asyncio.run(_main())
