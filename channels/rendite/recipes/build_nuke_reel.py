"""Custom REEL: das Atomkraft-Comeback durch KI-Strombedarf (Stand Ende Juli 2026) — der
Treiber, die Big-Tech-Atomdeals, die 4 Wege es zu spielen (Minen/Anreicherung/Versorger/SMR)
und Chance/Risiko. Opener: Kühlturm + blauer Himmel (hell). Vier Marken-Frames im Safe-Band,
fluente Stimme, Titel im script_json. Zeitbezüge mit Datum. Educational only."""
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

# Gleiche Stimme + gleiche Settings wie die Reels der letzten Tage (bewährt). Flüssiger wird es
# durch den TEXT: Zahlen ausgeschrieben und 'Uran' phonetisch (Uraan) — das waren die Stolperstellen.
config.ELEVENLABS_STABILITY = 0.40
config.ELEVENLABS_STYLE = 0.30  # weniger dramatisch -> Satzende faellt
config.ELEVENLABS_SPEED = 1.08  # kleines Mueh langsamer (User)

_OPENER_ID = int(os.getenv("OPENER_ID", "35640621"))  # vivid multicolor energy (bunter Eyecatcher)
_CTA_ID = int(os.getenv("CTA_ID", "35044924"))         # gold energy burst (anderer CTA)
_TITLE = "Atomkraft-Comeback: Der wahre Gewinner des KI-Booms?"

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


def frame_driver() -> str:
    img, d = _canvas()
    _kicker(d, "DER TREIBER")
    _title(d, "Strom ist das neue Öl")
    rows = [("KI-Rechenzentren", "gigantischer Strombedarf", BLUEL),
            ("Uranpreis (Juli 2026)", "~86 $/lb", BLUEL),
            ("Analystenziel (Citi)", "100–125 $", GREEN)]
    y, ch, gap = 476, 130, 15
    for label, val, col in rows:
        d.rounded_rectangle((60, y, W - 60, y + ch), radius=20, fill=CARD)
        d.text((92, y + 44), label, font=F(32, bold=True), fill=FG)
        _rtext(d, W - 92, y + 40, val, F(38, bold=True), col)
        y += ch + gap
    y += 8
    d.rounded_rectangle((60, y, W - 60, y + 160), radius=20, fill=(30, 30, 40))
    branding.wrap(d, "Nuklear-ETFs zeigen dreistellige Renditen — der Sektor läuft heiß, "
                     "getrieben vom Strom-Hunger der KI.",
                  F(33), 92, y + 30, 42, FG, 46)
    _footer(d)
    return _save(img, "nuke_frame_driver.jpg")


def frame_deals() -> str:
    img, d = _canvas()
    _kicker(d, "DIE BIG-TECH-DEALS")
    _title(d, "Tech kauft Atomstrom")
    rows = [("Microsoft", "startet Three Mile Island neu — für KI"),
            ("Meta & Amazon", "sichern sich eigene Atom-Deals")]
    y, ch, gap = 476, 175, 20
    for name, sub in rows:
        d.rounded_rectangle((60, y, W - 60, y + ch), radius=20, fill=CARD)
        d.text((92, y + 34), name, font=F(44, bold=True), fill=FG)
        branding.wrap(d, sub, F(30), 92, y + 100, 46, MUTED, 40)
        y += ch + gap
    y += 10
    d.rounded_rectangle((60, y, W - 60, y + 150), radius=20, fill=(30, 30, 40))
    branding.wrap(d, "Manche Tech-Konzerne finanzieren inzwischen sogar Uran-Projekte "
                     "direkt — so knapp wird der Strom.",
                  F(33), 92, y + 30, 42, FG, 46)
    _footer(d)
    return _save(img, "nuke_frame_deals.jpg")


def frame_players() -> str:
    img, d = _canvas()
    _kicker(d, "DIE 4 WEGE")
    _title(d, "So spielt man den Boom")
    rows = [("Uran-Minen", "Cameco"), ("Anreicherung", "Centrus"),
            ("Atom-Versorger", "Constellation"), ("Mini-Reaktoren (SMR)", "NuScale")]
    y, ch, gap = 476, 130, 16
    for seg, name in rows:
        d.rounded_rectangle((60, y, W - 60, y + ch), radius=20, fill=CARD)
        d.text((92, y + 44), seg, font=F(34, bold=True), fill=FG)
        _rtext(d, W - 92, y + 40, name, F(38, bold=True), BLUEL)
        y += ch + gap
    _footer(d)
    return _save(img, "nuke_frame_players.jpg")


def frame_stakes() -> str:
    img, d = _canvas()
    _kicker(d, "CHANCE & RISIKO")
    _title(d, "Megatrend oder Hype?")
    rows = [("Chance", "KI-Strombedarf = Megatrend fürs Jahrzehnt", GREEN),
            ("Risiko", "Hohe Bewertung, lange Bauzeiten, Politik", RED)]
    y, ch, gap = 476, 170, 20
    for tag, txt, col in rows:
        d.rounded_rectangle((60, y, W - 60, y + ch), radius=20, fill=CARD)
        d.ellipse((92, y + 40, 92 + 34, y + 74), fill=col)
        d.text((150, y + 34), tag, font=F(40, bold=True), fill=col)
        d.text((92, y + 96), txt, font=F(28), fill=FG)
        y += ch + gap
    y += 14
    branding.wrap(d, "Struktureller Rückenwind fürs ganze Jahrzehnt — aber der Sektor ist "
                     "heiß gelaufen und schwankt stark. Beobachten, nicht hinterherlaufen.",
                  F(31), 90, y, 44, MUTED, 42)
    _footer(d)
    return _save(img, "nuke_frame_stakes.jpg")


_TEXTS = [
    "Atomkraft-Comeback. Der wahre Gewinner des KI-Booms ist gar nicht der Chip, sondern der "
    "Strom, und genau das ändert gerade alles.",
    "KI-Rechenzentren verschlingen so viel Strom, dass Atomkraft plötzlich wieder gefragt "
    "ist. Der Preis für Uraan liegt Ende Juli 2026 bei rund sechsundachtzig Dollar, Analysten "
    "sehen ihn Richtung hundertfünfundzwanzig Dollar.",
    "Die Tech-Giganten machen Ernst: Microsoft lässt sogar das stillgelegte Kraftwerk Three "
    "Mile Island wieder anfahren, Meta und Amazon sichern sich ebenfalls Atomstrom für ihre KI.",
    "Für Anleger gibt es vier Wege: die Uraan-Minen wie Cameco, die Anreicherung wie Centrus, "
    "die Atom-Versorger wie Constellation, und die Mini-Reaktoren, allen voran NuScale.",
    "Unterm Strich: Der Strombedarf der KI ist ein Megatrend für ein ganzes Jahrzehnt. Das "
    "Risiko sind hohe Bewertungen, lange Bauzeiten und politische Unsicherheit.",
    "Setzt du auf den Atom-Boom, ja oder nein? Schreib es in die Kommentare und folge für "
    "die Trends, die die Börse bewegen.",
]

_CAPTION = (
    "⚛️ Das Atomkraft-Comeback: der wahre Gewinner des KI-Booms?\n\n"
    "KI-Rechenzentren verschlingen Strom — und plötzlich ist Atomkraft der heißeste Trade. "
    "Stand Ende Juli 2026:\n\n"
    "🔋 Uranpreis ~86 $/lb (Citi-Ziel 100–125 $), Nuklear-ETFs mit dreistelligen Renditen\n"
    "🤝 Microsoft startet Three Mile Island neu (für KI), Meta & Amazon sichern sich "
    "Atomstrom, Tech finanziert Uran-Projekte\n\n"
    "4 Wege, es zu spielen:\n"
    "⛏️ Uran-Minen: Cameco\n"
    "🧪 Anreicherung: Centrus\n"
    "⚡ Versorger: Constellation\n"
    "🔩 Mini-Reaktoren (SMR): NuScale\n\n"
    "🧭 Fazit: Megatrend fürs Jahrzehnt — aber heiß gelaufen (hohe Bewertung, lange Bauzeiten).\n\n"
    "Setzt du auf den Atom-Boom? 👇\n\n"
    "⚠️ Keine Anlageberatung — nur Bildung & Unterhaltung. Kein Kauf-/Verkaufsaufruf.\n"
    "#atomkraft #uran #kernenergie #ki #aktien #börse #nuscale #cameco #investieren"
)


async def _main() -> None:
    opener = _ensure_clip(_OPENER_ID)
    cta = _ensure_clip(_CTA_ID)
    frames = [frame_driver(), frame_deals(), frame_players(), frame_stakes()]
    broll_paths = [opener, frames[0], frames[1], frames[2], frames[3], cta]

    segments = [ScriptSegment(text=t, broll_query="") for t in _TEXTS]
    script = ReelScript(hook=_TEXTS[0], segments=segments, caption=_CAPTION,
                        hashtags=[], title=_TITLE)

    with session_scope() as s:
        reel = ReelRow(trend_id=0, script_json=json.dumps({"title": _TITLE,
                       "topic": "atomkraft-ki", "texts": _TEXTS}, ensure_ascii=False),
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
    print(f"Atomkraft-Reel #{rid} fertig: {video}")

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
