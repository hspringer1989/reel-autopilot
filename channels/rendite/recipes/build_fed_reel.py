"""Custom REEL: Auswertung des 29.07.2026-Abends — Fed-Zinsentscheid (hawkischer Hold,
9:3, 3 Dissens für Hike) + Microsoft (+2 %) vs Meta (−10 %, KI-Kosten) + Marktreaktion
(Dow −2,2 %, Nasdaq-100 in Korrektur) und was das für Anleger heißt. Opener NYSE+Flagge.
Vier Marken-Frames im Safe-Band, fluente Stimme, Titel im script_json. Educational only."""
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

config.ELEVENLABS_STABILITY = 0.40
config.ELEVENLABS_STYLE = 0.40
config.ELEVENLABS_SPEED = 1.06

_OPENER_ID = int(os.getenv("OPENER_ID", "5635831"))   # NYSE + US flag (hell, ikonisch)
_CTA_ID = int(os.getenv("CTA_ID", "9668305"))          # bright colorful paint
_TITLE = "Fed & Big Tech: Was der Abend für die Märkte bedeutet"

W, H = 1080, 1920
F = branding.load_font
BG, CARD, BLUE, BLUEL, FG, MUTED = (branding.BG, branding.CARD, branding.BLUE,
                                    branding.BLUE_LIGHT, branding.FG, branding.MUTED)
RED, GREEN = branding.RED, branding.GREEN
TOP = 290


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


def _kicker(d, text, color=BLUE):
    f = F(34, bold=True)
    tw = d.textlength(text, font=f)
    d.rounded_rectangle((60, TOP, 60 + tw + 46, TOP + 62), radius=16, fill=color)
    d.text((60 + 23, TOP + 12), text, font=f, fill=(255, 255, 255))


def _title(d, text, size=54, color=FG):
    d.text((60, TOP + 84), text, font=F(size, bold=True), fill=color)


def _footer(d):
    d.line((60, H - 118, W - 60, H - 118), fill=MUTED, width=2)
    d.text((60, H - 102), "Keine Anlageberatung · keine Kauf-/Verkaufsempfehlung · Werbung",
           font=F(23), fill=MUTED)


def _rtext(d, right_x, y, text, font, fill):
    d.text((right_x - d.textlength(text, font=font), y), text, font=font, fill=fill)


def _save(img, name) -> str:
    out = Path(config.OUTPUT_DIR) / name
    img.save(out, quality=92)
    return str(out)


def frame_fed() -> str:
    img, d = _canvas()
    _kicker(d, "DIE FED-ENTSCHEIDUNG")
    _title(d, "Hawkischer als erwartet")
    rows = [("Leitzins", "3,50–3,75 % gehalten", BLUEL),
            ("Votum", "9:3 — drei wollten erhöhen", RED)]
    y, ch, gap = 476, 132, 16
    for label, val, col in rows:
        d.rounded_rectangle((60, y, W - 60, y + ch), radius=20, fill=CARD)
        d.text((92, y + 42), label, font=F(34, bold=True), fill=FG)
        _rtext(d, W - 92, y + 42, val, F(34, bold=True), col)
        y += ch + gap
    y += 12
    d.rounded_rectangle((60, y, W - 60, y + 220), radius=20, fill=(30, 30, 40))
    d.text((92, y + 24), "Der Ton", font=F(30, bold=True), fill=BLUEL)
    branding.wrap(d, "Erstmals seit Langem drei Gegenstimmen für eine Erhöhung. Der Markt "
                     "preist jetzt zwei Zinsschritte bis Dezember ein.",
                  F(33), 92, y + 78, 42, FG, 46)
    _footer(d)
    return _save(img, "fed_frame_fed.jpg")


def frame_bigtech() -> str:
    img, d = _canvas()
    _kicker(d, "MICROSOFT vs META")
    _title(d, "Zwei Welten")
    rows = [("Microsoft", "+2 %", GREEN, "Cloud so stark wie seit 4 Jahren nicht"),
            ("Meta", "−10 %", RED, "Umsatz gut, aber Gewinn-Miss — KI-Kosten")]
    y, ch, gap = 476, 175, 20
    for name, pct, col, sub in rows:
        d.rounded_rectangle((60, y, W - 60, y + ch), radius=20, fill=CARD)
        d.text((92, y + 28), name, font=F(44, bold=True), fill=FG)
        _rtext(d, W - 92, y + 26, pct, F(52, bold=True), col)
        d.text((92, y + 100), sub, font=F(28), fill=MUTED)
        y += ch + gap
    y += 10
    d.rounded_rectangle((60, y, W - 60, y + 150), radius=20, fill=(30, 30, 40))
    branding.wrap(d, "Beide geben Milliarden für KI aus — der Markt belohnt aber nur, wer "
                     "trotzdem liefert.",
                  F(33), 92, y + 32, 42, FG, 46)
    _footer(d)
    return _save(img, "fed_frame_bigtech.jpg")


def frame_market() -> str:
    img, d = _canvas()
    _kicker(d, "DIE MARKTREAKTION", RED)
    _title(d, "Rot auf breiter Front", color=RED)
    rows = [("Dow Jones", "−2,2 %"), ("S&P 500", "−1,5 %"), ("Nasdaq", "−1,7 %")]
    y, ch, gap = 476, 118, 15
    for name, pct in rows:
        d.rounded_rectangle((60, y, W - 60, y + ch), radius=18, fill=CARD)
        d.text((92, y + 38), name, font=F(40, bold=True), fill=FG)
        _rtext(d, W - 92, y + 34, pct, F(46, bold=True), RED)
        y += ch + gap
    y += 8
    d.rounded_rectangle((60, y, W - 60, y + 200), radius=20, fill=(34, 24, 28))
    d.text((92, y + 24), "Das Alarmsignal", font=F(30, bold=True), fill=RED)
    branding.wrap(d, "Der Nasdaq-100 ist in Korrektur — 11 % unter dem Hoch. Die "
                     "Anleiherenditen sprangen auf den höchsten Stand seit 2007.",
                  F(32), 92, y + 78, 42, FG, 44)
    _footer(d)
    return _save(img, "fed_frame_market.jpg")


def frame_stakes() -> str:
    img, d = _canvas()
    _kicker(d, "WAS DAS FÜR ANLEGER HEISST")
    _title(d, "Gewinne schlagen Versprechen")
    rows = [("Gegenwind", "Teureres Geld (Fed) + Zweifel an KI-Ausgaben", RED),
            ("Die Lehre", "Der Markt belohnt Gewinne, nicht nur Wachstum", GREEN)]
    y, ch, gap = 476, 170, 20
    for tag, txt, col in rows:
        d.rounded_rectangle((60, y, W - 60, y + ch), radius=20, fill=CARD)
        d.ellipse((92, y + 40, 92 + 34, y + 74), fill=col)
        d.text((150, y + 34), tag, font=F(40, bold=True), fill=col)
        d.text((92, y + 96), txt, font=F(28), fill=FG)
        y += ch + gap
    y += 14
    branding.wrap(d, "Qualität und Cash-Flow zählen wieder mehr als reine Zukunftsfantasie — "
                     "Microsoft gegen Meta zeigt genau das.",
                  F(31), 90, y, 44, MUTED, 42)
    _footer(d)
    return _save(img, "fed_frame_stakes.jpg")


_TEXTS = [
    "Gestern Abend fielen gleich mehrere große Entscheidungen an der Börse, und die Märkte "
    "reagierten heftig. Hier ist, was du wissen musst.",
    "Die Fed ließ die Zinsen unverändert, aber erstmals seit Langem stimmten drei Mitglieder "
    "für eine Erhöhung. Ein deutlich schärferer Ton, der Markt rechnet jetzt mit zwei "
    "Zinsschritten bis Dezember.",
    "Bei den Tech-Riesen könnten die Zahlen kaum unterschiedlicher sein: Microsoft legte um "
    "zwei Prozent zu, die Cloud wuchs so schnell wie seit vier Jahren nicht. Meta dagegen "
    "stürzte zehn Prozent ab, weil die hohen KI-Ausgaben den Gewinn auffraßen.",
    "Die Wall Street reagierte klar: Der Dow verlor über zwei Prozent, der technologielastige "
    "Nasdaq rutschte in eine Korrektur, elf Prozent unter seinem Hoch. Die Anleiherenditen "
    "sprangen auf den höchsten Stand seit 2007.",
    "Unterm Strich: Teureres Geld von der Fed trifft auf wachsende Zweifel an den gigantischen "
    "KI-Ausgaben. Der Markt belohnt jetzt Gewinne, nicht mehr nur Wachstumsversprechen.",
    "Wie positionierst du dich in so einem Umfeld? Schreib es in die Kommentare und folge für "
    "den täglichen Durchblick an der Börse!",
]

_CAPTION = (
    "🚨 Fed, Microsoft & Meta: der Abend, der die Märkte bewegte.\n\n"
    "🏦 Fed: Zins bleibt bei 3,50–3,75 %, ABER 9:3 — drei Mitglieder wollten erhöhen. "
    "Deutlich hawkischer Ton, der Markt preist jetzt zwei Zinsschritte bis Dezember.\n"
    "💻 Microsoft +2 % (Cloud stark) vs. Meta −10 % (Gewinn-Miss, KI-Kosten fressen den Gewinn).\n"
    "📉 Wall Street: Dow −2,2 %, S&P −1,5 %, Nasdaq −1,7 % — Nasdaq-100 in Korrektur (−11 %), "
    "Anleiherenditen so hoch wie seit 2007 nicht.\n\n"
    "🧭 Fazit: Teureres Geld + KI-Kosten-Skepsis. Der Markt belohnt wieder Gewinne statt "
    "reiner Wachstumsversprechen.\n\n"
    "Wie positionierst du dich? 👇\n\n"
    "⚠️ Keine Anlageberatung — nur Bildung & Unterhaltung. Kein Kauf-/Verkaufsaufruf.\n"
    "#fed #zinsen #microsoft #meta #ki #börse #aktien #nasdaq #investieren"
)


async def _main() -> None:
    opener = _ensure_clip(_OPENER_ID)
    cta = _ensure_clip(_CTA_ID)
    frames = [frame_fed(), frame_bigtech(), frame_market(), frame_stakes()]
    broll_paths = [opener, frames[0], frames[1], frames[2], frames[3], cta]

    segments = [ScriptSegment(text=t, broll_query="") for t in _TEXTS]
    script = ReelScript(hook=_TEXTS[0], segments=segments, caption=_CAPTION,
                        hashtags=[], title=_TITLE)

    with session_scope() as s:
        reel = ReelRow(trend_id=0, script_json=json.dumps({"title": _TITLE,
                       "topic": "fed-bigtech", "texts": _TEXTS}, ensure_ascii=False),
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
    print(f"Fed-Reel #{rid} fertig: {video}")

    if os.getenv("SEND_REVIEW") == "1":
        from src.review.telegram_bot import review_configured, send_for_review
        if review_configured():
            with session_scope() as s:
                r = s.get(ReelRow, rid)
                vp, cap = r.video_path, r.caption
            await send_for_review(rid, vp, cap)
            print("An Telegram-Review gesendet.")


if __name__ == "__main__":
    asyncio.run(_main())
