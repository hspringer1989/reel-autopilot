"""Custom REEL: der 'Super-Mittwoch' (29.07.2026) — Fed-Zinsentscheid + Microsoft & Meta
Quartalszahlen am selben Tag, mitten im KI-/Chip-Ausverkauf. Heller, farbenfroher Opener
(Sonnenaufgang-Skyline) + Blumenfeld-CTA, vier Marken-Frames im Safe-Band, fluente Stimme.
Educational only."""
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

_OPENER_ID = int(os.getenv("OPENER_ID", "12715038"))  # HERO: scarlet macaw close-up (hell+bunt)
_CTA_ID = int(os.getenv("CTA_ID", "9668305"))          # bright colorful paint

W, H = 1080, 1920
F = branding.load_font
BG, CARD, BLUE, BLUEL, FG, MUTED = (branding.BG, branding.CARD, branding.BLUE,
                                    branding.BLUE_LIGHT, branding.FG, branding.MUTED)
RED, GREEN, AMBER = branding.RED, branding.GREEN, branding.AMBER
TOP = 290  # keep top free for the IG profile-name overlay; content band y≈290–1250


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


def _title(d, text, size=56, color=FG):
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


def frame_overview() -> str:
    img, d = _canvas()
    _kicker(d, "DER SUPER-MITTWOCH")
    _title(d, "3 Markt-Bomben, 1 Tag")
    rows = [("20:00 Uhr", "Fed-Zinsentscheid", "hält die Fed still — oder erhöht sie?"),
            ("Nachbörslich", "Microsoft", "Quartalszahlen — KI-Ausgaben im Fokus"),
            ("Nachbörslich", "Meta", "Quartalszahlen — KI-Ausgaben im Fokus")]
    y, ch, gap = 478, 224, 24
    for when, ev, sub in rows:
        d.rounded_rectangle((60, y, W - 60, y + ch), radius=22, fill=CARD)
        d.text((92, y + 26), when, font=F(30, bold=True), fill=BLUEL)
        d.text((92, y + 74), ev, font=F(50, bold=True), fill=FG)
        d.text((92, y + 150), sub, font=F(30), fill=MUTED)
        y += ch + gap
    _footer(d)
    return _save(img, "sm_frame_overview.jpg")


def frame_fed() -> str:
    img, d = _canvas()
    _kicker(d, "DIE FED · 20:00 UHR")
    _title(d, "Zins-Poker")
    rows = [("Zinsen bleiben (3,50–3,75 %)", "62 %", BLUEL),
            ("Zinserhöhung — Hike-Risiko!", "38 %", RED)]
    y, ch, gap = 478, 132, 16
    for label, val, col in rows:
        d.rounded_rectangle((60, y, W - 60, y + ch), radius=20, fill=CARD)
        d.text((92, y + 42), label, font=F(34, bold=True), fill=FG)
        _rtext(d, W - 92, y + 34, val, F(50, bold=True), col)
        y += ch + gap
    y += 12
    d.rounded_rectangle((60, y, W - 60, y + 220), radius=20, fill=(30, 30, 40))
    d.text((92, y + 24), "Warum nervös?", font=F(30, bold=True), fill=BLUEL)
    branding.wrap(d, "Neuer Fed-Chef Kevin Warsh, keine Guidance mehr — und hartnäckige "
                     "Inflation durch Öl bei rund 100 Dollar.",
                  F(33), 92, y + 78, 42, FG, 46)
    _footer(d)
    return _save(img, "sm_frame_fed.jpg")


def frame_bigtech() -> str:
    img, d = _canvas()
    _kicker(d, "MICROSOFT & META")
    _title(d, "Das KI-Referendum")
    rows = [("Microsoft", "erwartet ~4,23 $ Gewinn · ~87 Mrd $ Umsatz"),
            ("Meta", "erwartet ~7,2 $ Gewinn je Aktie")]
    y, ch, gap = 478, 150, 18
    for name, exp in rows:
        d.rounded_rectangle((60, y, W - 60, y + ch), radius=20, fill=CARD)
        d.text((92, y + 28), name, font=F(46, bold=True), fill=FG)
        d.text((92, y + 90), exp, font=F(29), fill=MUTED)
        y += ch + gap
    y += 12
    d.rounded_rectangle((60, y, W - 60, y + 200), radius=20, fill=(30, 30, 40))
    d.text((92, y + 24), "Der Knackpunkt", font=F(30, bold=True), fill=BLUEL)
    branding.wrap(d, "Die zwei größten Geldgeber des KI-Booms liefern Zahlen — genau jetzt, "
                     "wo der Markt über die hohen KI-Kosten streitet.",
                  F(33), 92, y + 78, 42, FG, 46)
    _footer(d)
    return _save(img, "sm_frame_bigtech.jpg")


def frame_stakes() -> str:
    img, d = _canvas()
    _kicker(d, "WAS HEUTE ENTSCHEIDET")
    _title(d, "Rally oder Ausverkauf?")
    rows = [("Chance", "Entwarnung → Erleichterungs-Rally", GREEN),
            ("Risiko", "Zins-Schock + KI-Enttäuschung → Ausverkauf", RED)]
    y, ch, gap = 478, 170, 20
    for tag, txt, col in rows:
        d.rounded_rectangle((60, y, W - 60, y + ch), radius=20, fill=CARD)
        d.ellipse((92, y + 40, 92 + 34, y + 74), fill=col)
        d.text((150, y + 34), tag, font=F(40, bold=True), fill=col)
        d.text((92, y + 96), txt, font=F(30), fill=FG)
        y += ch + gap
    y += 14
    branding.wrap(d, "Die Fed gibt den Ton bei den Zinsen vor, Microsoft & Meta beim KI-Boom. "
                     "Nach dem Chip-Crash zeigt heute Abend die Richtung.",
                  F(31), 90, y, 44, MUTED, 42)
    _footer(d)
    return _save(img, "sm_frame_stakes.jpg")


_TEXTS = [
    "Heute ist der wichtigste Börsentag des Sommers. Gleich drei Ereignisse an einem "
    "einzigen Tag entscheiden, wohin die Märkte laufen.",
    "Am Abend die Fed mit ihrem Zinsentscheid, und nachbörslich legen Microsoft und Meta "
    "ihre Zahlen vor. Drei Schwergewichte, ein Tag.",
    "Die Fed dürfte die Zinsen wohl halten, aber der Markt sieht fast vierzig Prozent Chance "
    "auf eine Erhöhung, wegen hartnäckiger Inflation und Öl bei hundert Dollar. Ungewöhnlich nervös.",
    "Microsoft und Meta sind die zwei größten Geldgeber des KI-Booms. Genau jetzt, wo der "
    "Markt über die hohen KI-Kosten streitet, müssen ihre Zahlen liefern.",
    "Kurz gesagt: Die Fed gibt den Ton bei den Zinsen vor, Microsoft und Meta beim KI-Boom. "
    "Nach dem Chip-Crash entscheidet heute Abend die Richtung, Rally oder nächster Ausverkauf.",
    "Rechnest du heute Abend mit Grün oder Rot? Schreib es in die Kommentare und folge für "
    "den echten Durchblick an der Börse!",
]

_CAPTION = (
    "🚨 Heute entscheidet sich alles: der Super-Mittwoch an der Börse.\n\n"
    "Drei Schwergewichte an EINEM Tag:\n"
    "🏦 Fed-Zinsentscheid (20:00) — 62 % halten, aber 38 % Chance auf eine Zinserhöhung "
    "(Öl bei 100 $ + hartnäckige Inflation)\n"
    "💻 Microsoft & Meta Quartalszahlen (nachbörslich) — die zwei größten KI-Ausgeber, "
    "mitten im Streit um die KI-Kosten\n\n"
    "Nach dem Chip-Crash entscheidet heute Abend die Richtung: Erleichterungs-Rally oder "
    "nächste Runde Ausverkauf?\n\n"
    "Grün oder Rot heute Abend? 👇\n\n"
    "⚠️ Keine Anlageberatung — nur Bildung & Unterhaltung. Kein Kauf-/Verkaufsaufruf.\n"
    "#börse #fed #zinsen #microsoft #meta #ki #aktien #earnings #investieren"
)


async def _main() -> None:
    opener = _ensure_clip(_OPENER_ID)
    cta = _ensure_clip(_CTA_ID)
    frames = [frame_overview(), frame_fed(), frame_bigtech(), frame_stakes()]
    broll_paths = [opener, frames[0], frames[1], frames[2], frames[3], cta]

    segments = [ScriptSegment(text=t, broll_query="") for t in _TEXTS]
    script = ReelScript(hook=_TEXTS[0], segments=segments, caption=_CAPTION,
                        hashtags=[], title="Super-Mittwoch — Fed + Microsoft + Meta")

    with session_scope() as s:
        reel = ReelRow(trend_id=0, script_json=json.dumps({"topic": "super-mittwoch",
                       "texts": _TEXTS}, ensure_ascii=False), caption=_CAPTION, status="draft")
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
    print(f"Super-Mittwoch-Reel #{rid} fertig: {video}")

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
